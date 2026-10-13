"""Loopback origin protection, ephemeral browser sessions and scoped Agent tokens."""
import hashlib
import hmac
import secrets
import time
from urllib.parse import urlsplit
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from .db import now, new_id


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


class LocalSecurity(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        hostname = urlsplit('http://' + request.headers.get('host', '')).hostname
        if hostname not in ('localhost', '127.0.0.1', '::1'):
            return JSONResponse({'detail':'Untrusted Host'}, status_code=400)
        origin = request.headers.get('origin')
        allowed = {str(request.base_url).rstrip('/'), 'http://localhost:5173', 'http://127.0.0.1:5173'}
        if (origin and origin not in allowed) or request.headers.get('sec-fetch-site') == 'cross-site':
            return JSONResponse({'detail':'Foreign origin denied'}, status_code=403)
        if request.client and request.client.host not in ('127.0.0.1', '::1', 'testclient'):
            return JSONResponse({'detail':'Local connections only'}, status_code=403)
        path = request.url.path
        if not path.startswith('/api/') or path in ('/api/v1/health','/api/v1/session'):
            return await call_next(request)
        bearer = request.headers.get('authorization', '')
        if bearer.startswith('Bearer '):
            row = request.app.state.db.one('SELECT * FROM agent_tokens WHERE token_hash=?', (digest(bearer[7:]),))
            if not row:
                return JSONResponse({'detail':'Invalid Agent token'}, status_code=401)
            if path.startswith(('/api/v1/agent-tokens','/api/v1/settings','/api/v1/backup','/api/v1/restore','/api/v1/portable')):
                return JSONResponse({'detail':'Browser administrator session required'}, status_code=403)
            if request.method not in ('GET','HEAD','OPTIONS') and row['scope'] != 'write':
                return JSONResponse({'detail':'Read-only Agent token'}, status_code=403)
        else:
            token = request.cookies.get('workspace_session', '')
            session = request.app.state.sessions.get(digest(token))
            if not session or session['expires'] < time.time():
                return JSONResponse({'detail':'Local session required'}, status_code=401)
            if request.method not in ('GET','HEAD','OPTIONS') and not hmac.compare_digest(request.headers.get('x-csrf-token',''), session['csrf']):
                return JSONResponse({'detail':'CSRF token required'}, status_code=403)
        response = await call_next(request)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['Cache-Control'] = 'no-store'
        return response


router = APIRouter(prefix='/api/v1')


@router.post('/session')
def session(request: Request, response: Response):
    # Bootstrapping is restricted by LocalSecurity before any cookie is issued.
    sessions = request.app.state.sessions
    existing = sessions.get(digest(request.cookies.get('workspace_session', '')))
    if existing and existing['expires'] > time.time():
        return {'csrf_token':existing['csrf']}
    expired = [key for key,value in sessions.items() if value['expires'] < time.time()]
    for key in expired:
        sessions.pop(key, None)
    token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    sessions[digest(token)] = {'csrf':csrf, 'expires':time.time()+86400}
    response.set_cookie('workspace_session', token, httponly=True, samesite='strict', max_age=86400)
    return {'csrf_token':csrf}


class TokenInput(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    scope: str = 'read'


@router.get('/agent-tokens')
def list_tokens(request: Request):
    return request.app.state.db.all('SELECT id,name,scope,created_at FROM agent_tokens ORDER BY created_at DESC')


@router.post('/agent-tokens', status_code=201)
def create_token(body: TokenInput, request: Request):
    if body.scope not in ('read','write'):
        raise HTTPException(422, 'scope must be read or write')
    token, identifier = secrets.token_urlsafe(36), new_id()
    with request.app.state.db.connect() as con:
        con.execute('INSERT INTO agent_tokens VALUES (?,?,?,?,?)',(identifier,body.name,digest(token),body.scope,now()))
    return {'id':identifier,'name':body.name,'scope':body.scope,'token':token}


@router.delete('/agent-tokens/{identifier}', status_code=204)
def delete_token(identifier: str, request: Request):
    with request.app.state.db.connect() as con:
        con.execute('DELETE FROM agent_tokens WHERE id=?',(identifier,))
