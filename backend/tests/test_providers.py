import httpx
import pytest
from workspace.providers import LocalProvider, ProviderError


@pytest.mark.parametrize('url',['https://api.openai.com/v1','http://192.168.1.10:1234/v1','http://localhost.evil.test/v1','http://user:secret@localhost:1234/v1','file:///etc/passwd'])
def test_provider_rejects_nonlocal_or_credential_urls(url):
    with pytest.raises(ValueError):
        LocalProvider(base_url=url)


def test_provider_wire_models_chat_and_embeddings():
    seen=[]
    def handle(request):
        seen.append(request)
        if request.url.path.endswith('/models'):
            return httpx.Response(200,json={'data':[{'id':'local-model'}]})
        if request.url.path.endswith('/embeddings'):
            return httpx.Response(200,json={'data':[{'index':0,'embedding':[1.,0.]}]})
        return httpx.Response(200,json={'choices':[{'message':{'content':'Grounded answer'}}]})
    p=LocalProvider(model='local-model',embedding_model='multilingual',transport=httpx.MockTransport(handle))
    assert p.models()==['local-model']
    assert p.chat([{'role':'user','content':'Explain gradient descent'}])=='Grounded answer'
    assert p.embed(['梯度下降'])==[[1.,0.]]
    assert all(request.url.host=='127.0.0.1' for request in seen)


@pytest.mark.parametrize('payload',[{'data':[]},{'data':[{'index':0,'embedding':[float('nan')]}]},{'data':[{'index':0,'embedding':[]}]}])
def test_provider_rejects_bad_embedding_payload(payload):
    import json
    p=LocalProvider(embedding_model='embed',transport=httpx.MockTransport(lambda request:httpx.Response(200,content=json.dumps(payload))))
    with pytest.raises(ProviderError):
        p.embed(['a'])


def test_provider_does_not_follow_remote_redirect():
    p=LocalProvider(transport=httpx.MockTransport(lambda req:httpx.Response(302,headers={'location':'https://example.com/collect'})))
    with pytest.raises(ProviderError):
        p.models()
