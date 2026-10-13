import httpx
import pytest
import zlib
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


@pytest.mark.parametrize('compressed', [False, True])
def test_provider_stops_reading_at_response_limit(compressed):
    class LargeStream(httpx.SyncByteStream):
        chunks_read = 0
        closed = False

        def __iter__(self):
            compressor = zlib.compressobj(wbits=31)
            for _ in range(12):
                self.chunks_read += 1
                chunk = b'x' * (1024 * 1024)
                yield compressor.compress(chunk) + compressor.flush(zlib.Z_SYNC_FLUSH) if compressed else chunk

        def close(self):
            self.closed = True

    stream = LargeStream()
    provider = LocalProvider(transport=httpx.MockTransport(
        lambda request: httpx.Response(200, stream=stream, headers={'Content-Encoding': 'gzip'} if compressed else {})))
    with pytest.raises(ProviderError, match='8 MiB'):
        provider.models()
    assert stream.chunks_read == 9
    assert stream.closed
