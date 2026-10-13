"""OpenAI-compatible local transport. No storage or retrieval responsibilities."""
import math
from urllib.parse import urlsplit
import httpx


class ProviderError(RuntimeError):
    """A safe, user-facing model service failure."""


class LocalProvider:
    def __init__(self, base_url='http://127.0.0.1:1234/v1',model='',embedding_model='',timeout=60,api_key='',transport=None):
        parsed = urlsplit(base_url)
        if parsed.scheme not in ('http','https') or parsed.hostname not in ('127.0.0.1','localhost','::1') or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError('Only a local loopback model endpoint is allowed.')
        self.base_url = base_url.rstrip('/')
        self.model, self.embedding_model = model, embedding_model
        self.timeout = min(max(float(timeout),3),180)
        self.api_key = api_key
        self.transport = transport

    def _request(self,path,payload=None):
        headers = {'Authorization':'Bearer '+self.api_key} if self.api_key else {}
        try:
            with httpx.Client(timeout=self.timeout,trust_env=False,follow_redirects=False,transport=self.transport) as client:
                response = client.request('GET' if payload is None else 'POST',self.base_url+path,json=payload,headers=headers)
                if response.is_redirect:
                    raise ProviderError('Model endpoint redirects are not allowed.')
                response.raise_for_status()
                if len(response.content)>8*1024*1024:
                    raise ProviderError('Model response exceeds the 8 MiB limit.')
                return response.json()
        except httpx.TimeoutException as exc:
            raise ProviderError('Local model timed out. Reduce context or increase timeout.') from exc
        except httpx.HTTPStatusError as exc:
            raise ProviderError(f'Local model returned HTTP {exc.response.status_code}. Check the selected model and server settings.') from exc
        except httpx.RequestError as exc:
            raise ProviderError('Cannot connect to local model. Start LM Studio/Ollama server and check its port.') from exc
        except ValueError as exc:
            raise ProviderError('Local model returned invalid JSON.') from exc

    def models(self):
        data = self._request('/models')
        try:
            return [str(row['id']) for row in data['data']]
        except (KeyError,TypeError) as exc:
            raise ProviderError('Unexpected model-list response.') from exc

    def chat(self,messages):
        if not self.model:
            raise ProviderError('Select a local chat model in Settings first.')
        data = self._request('/chat/completions',{'model':self.model,'messages':messages,'temperature':0.15,'stream':False,'max_tokens':2048})
        try:
            content = data['choices'][0]['message']['content']
            if not isinstance(content,str) or not content.strip():
                raise ValueError()
            return content
        except (KeyError,IndexError,TypeError,ValueError) as exc:
            raise ProviderError('Model returned no usable answer.') from exc

    def embed(self,texts):
        if not self.embedding_model:
            raise ProviderError('Select a local embedding model first.')
        data = self._request('/embeddings',{'model':self.embedding_model,'input':texts})
        try:
            entries = data['data']
            if len(entries) != len(texts) or sorted(row['index'] for row in entries) != list(range(len(texts))):
                raise ValueError()
            vectors = [row['embedding'] for row in sorted(entries,key=lambda row:row['index'])]
            dimension = len(vectors[0])
            if not dimension or dimension>16384 or any(len(v)!=dimension or not all(isinstance(x,(int,float)) and not isinstance(x,bool) and math.isfinite(x) for x in v) for v in vectors):
                raise ValueError()
            return vectors
        except (KeyError,IndexError,TypeError,ValueError) as exc:
            raise ProviderError('Invalid embedding vectors: check count, dimension and numeric values.') from exc
