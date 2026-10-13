"""Local, bounded diagnostics and browser response protections."""
import logging
from logging.handlers import RotatingFileHandler
import time
from starlette.responses import JSONResponse

CSP = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self'; connect-src 'self'; frame-src 'self' blob:; object-src 'self'; frame-ancestors 'self'; base-uri 'none'; form-action 'self'"


def install_log(root):
    directory=root/'logs'
    if directory.is_symlink():raise RuntimeError('Log directory must be local')
    directory.mkdir(exist_ok=True)
    path=directory/'workspace.log'
    if path.is_symlink():raise RuntimeError('Log file must be local')
    path.touch(mode=0o600,exist_ok=True)
    handler=RotatingFileHandler(path,maxBytes=1024*1024,backupCount=3,encoding='utf-8')
    formatter=logging.Formatter('%(asctime)sZ %(levelname)s %(message)s')
    formatter.converter=time.gmtime
    handler.setFormatter(formatter)
    logging.getLogger('workspace').addHandler(handler)
    return handler


def close_log(handler):
    logging.getLogger('workspace').removeHandler(handler)
    handler.close()


class Diagnostics:
    def __init__(self,app):self.app=app
    async def __call__(self,scope,receive,send):
        if scope['type']!='http':return await self.app(scope,receive,send)
        started=False
        async def protected_send(message):
            nonlocal started
            if message['type']=='http.response.start':
                started=True
                headers=list(message.get('headers',[]))
                present={key.lower() for key,_ in headers}
                for key,value in [(b'content-security-policy',CSP.encode()),(b'x-content-type-options',b'nosniff'),(b'x-frame-options',b'SAMEORIGIN'),(b'referrer-policy',b'no-referrer')]:
                    if key not in present:headers.append((key,value))
                message={**message,'headers':headers}
            await send(message)
        try:
            await self.app(scope,receive,protected_send)
        except Exception as exc:
            # Exception arguments may contain source text or credentials. Log
            # only the class and registered route template, never raw input.
            template=getattr(scope.get('route'),'path','/unmatched')
            logging.getLogger('workspace').error('request_failed route=%s type=%s',template,type(exc).__name__)
            if not started:
                await JSONResponse({'detail':'Unexpected local error. Check logs/workspace.log and retry.'},500)(scope,receive,protected_send)
