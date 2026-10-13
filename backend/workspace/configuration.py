"""Local provider configuration; credentials stay out of database/export data."""
import json
import os
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from .providers import LocalProvider, ProviderError

router = APIRouter(prefix='/api/v1/settings')
DEFAULTS = {'base_url':'http://127.0.0.1:1234/v1','model':'','embedding_model':'','timeout':60}


def provider_config(db):
    row=db.one("SELECT value FROM settings WHERE key='provider'")
    return {**DEFAULTS,**(json.loads(row['value']) if row else {})}


def provider_snapshot(app):
    db=app.state.db
    with db.maintenance:
        config=provider_config(db)
        override=getattr(app.state,'provider_override',None)
        if override is not None:
            return config,override
        secret=db.root/'provider-secret.json'
        key=json.loads(secret.read_text()).get('api_key','') if secret.is_file() else ''
        return config,LocalProvider(**config,api_key=key)


def get_provider(app):
    return provider_snapshot(app)[1]


class ProviderInput(BaseModel):
    model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
    base_url: str | None = None
    model: str | None = Field(default=None,max_length=300)
    embedding_model: str | None = Field(default=None,max_length=300)
    timeout: int | None = Field(default=None,ge=3,le=180)
    api_key: str | None = Field(default=None,max_length=2000)


@router.get('/provider')
def get_config(request: Request):
    db=request.app.state.db
    result=provider_config(db)
    secret=db.root/'provider-secret.json'
    result['has_api_key']=bool(json.loads(secret.read_text()).get('api_key')) if secret.is_file() else False
    return result


@router.put('/provider')
def put_config(body: ProviderInput,request: Request):
    db=request.app.state.db
    data=body.model_dump(exclude_none=True)
    key=data.pop('api_key',None)
    config={**provider_config(db),**data}
    try:
        LocalProvider(**config)
    except ValueError as exc:
        raise HTTPException(422,str(exc)) from exc
    with db.connect() as con:
        if key is not None:
            temporary=db.root/'provider-secret.tmp'
            fd=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
            with os.fdopen(fd,'w') as stream:
                json.dump({'api_key':key},stream)
            temporary.chmod(0o600)
            temporary.replace(db.root/'provider-secret.json')
        con.execute("INSERT INTO settings VALUES ('provider',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(json.dumps(config),))
    return get_config(request)


@router.post('/provider/test')
def test_config(request: Request):
    try:
        return {'available':True,'models':get_provider(request.app).models()}
    except ProviderError as exc:
        return {'available':False,'models':[],'error':str(exc)}
