import json
from fastapi.testclient import TestClient
from workspace.app import create_app
from workspace.providers import ProviderError
from test_core import login
from test_documents import upload


class MockProvider:
    def __init__(self,mode='valid'):
        self.mode=mode
        self.calls=[]
    def chat(self,messages):
        self.calls.append(messages)
        if self.mode=='offline':
            raise ProviderError('Local model offline')
        evidence=json.loads(messages[-1]['content'])['evidence'][0]
        identifier=evidence['chunk_id'] if self.mode!='fake' else 'invented'
        quote=evidence['text'][:35] if self.mode!='bad_quote' else 'This quote does not exist'
        return json.dumps({'answer':'梯度下降使用导数更新参数。 [1]','citations':[{'id':identifier,'quote':quote}],'insufficient_evidence':False})


def test_grounded_answer_persists_real_sources_and_scope(tmp_path):
    app=create_app(tmp_path)
    app.state.provider_override=MockProvider()
    with TestClient(app,base_url='http://localhost') as c:
        login(c)
        course=c.post('/api/v1/courses',json={'name':'ML'}).json()
        doc=upload(c,'ml.md','# Gradient descent\n梯度下降使用导数更新参数'.encode(),course['id'])
        upload(c,'other.md',b'Gradient descent in an unrelated course')
        conversation=c.post('/api/v1/conversations',json={'title':'Study','course_id':course['id']}).json()
        r=c.post('/api/v1/conversations/'+conversation['id']+'/messages',json={'content':'什么是梯度下降？'})
        assert r.status_code==200,r.text
        answer=r.json()
        assert answer['status']=='citations_verified'
        assert answer['sources'][0]['document_id']==doc['id']
        assert answer['sources'][0]['version_id']==doc['active_version']
        sent=json.loads(app.state.provider_override.calls[0][-1]['content'])['evidence']
        assert all(source['document_id']==doc['id'] for source in sent)
        detail=c.get('/api/v1/conversations/'+conversation['id']).json()
        assert len(detail['messages'])==2
    with TestClient(create_app(tmp_path),base_url='http://localhost') as c:
        login(c)
        assert c.get('/api/v1/conversations/'+conversation['id']).json()['messages'][1]['sources']==answer['sources']


def test_invalid_citations_are_not_displayed_as_verified(tmp_path):
    app=create_app(tmp_path)
    with TestClient(app,base_url='http://localhost') as c:
        login(c);upload(c,'lesson.txt',b'Gradient descent uses derivatives.')
        for mode in ('fake','bad_quote'):
            app.state.provider_override=MockProvider(mode)
            conversation=c.post('/api/v1/conversations',json={}).json()
            answer=c.post('/api/v1/conversations/'+conversation['id']+'/messages',json={'content':'gradient'}).json()
            assert answer['status']=='unverified'
            assert answer['sources']==[]


def test_no_evidence_does_not_call_model_and_offline_keeps_history(tmp_path):
    app=create_app(tmp_path);app.state.provider_override=MockProvider('offline')
    with TestClient(app,base_url='http://localhost') as c:
        login(c)
        conversation=c.post('/api/v1/conversations',json={}).json()
        answer=c.post('/api/v1/conversations/'+conversation['id']+'/messages',json={'content':'unknown'}).json()
        assert answer['status']=='evidence_insufficient'
        assert app.state.provider_override.calls==[]
        upload(c,'evidence.txt',b'Gradient descent uses derivatives.')
        answer=c.post('/api/v1/conversations/'+conversation['id']+'/messages',json={'content':'gradient'}).json()
        assert answer['status']=='provider_error'
        assert len(c.get('/api/v1/conversations/'+conversation['id']).json()['messages'])==4


def test_provider_config_disallows_remote_and_masks_api_key(tmp_path):
    with TestClient(create_app(tmp_path),base_url='http://localhost') as c:
        login(c)
        assert c.put('/api/v1/settings/provider',json={'base_url':'https://paid.example/v1'}).status_code==422
        assert c.put('/api/v1/settings/provider',json={'model':'local','api_key':'local-secret'}).status_code==200
        result=c.get('/api/v1/settings/provider').json()
        assert result['model']=='local'
        assert result['has_api_key'] is True
        assert 'local-secret' not in json.dumps(result)
        assert 'local-secret' not in (tmp_path/'workspace.sqlite3').read_bytes().decode(errors='ignore')
        assert (tmp_path/'provider-secret.json').stat().st_mode & 0o777 == 0o600


def test_multi_document_evidence_merge_uses_rank_not_incompatible_raw_scores(tmp_path,monkeypatch):
    from workspace.ai import retrieve_evidence
    from workspace import embeddings
    app=create_app(tmp_path)
    def results(app,q,course_id,document_id,limit):
        return {'mode':'hybrid','hits':[{'chunk_id':document_id+str(i),'document_id':document_id,'text':'source evidence','score':(1-i*.01) if document_id=='strong' else (.6-i*.01),'relevance_score':(1-i*.01) if document_id=='strong' else (.6-i*.01)} for i in range(6)]}
    monkeypatch.setattr(embeddings,'hybrid_search',results)
    evidence=retrieve_evidence(app.state.db,'query',document_ids=['strong','weak'],app=app)
    assert all(hit['document_id']=='strong' for hit in evidence)


def test_mixed_indexed_and_unindexed_documents_share_ranking_scale(tmp_path):
    from workspace.ai import retrieve_evidence
    from workspace.db import now
    class Embed:
        def embed(self,texts):return [[1.,0.] for _ in texts]
    app=create_app(tmp_path);app.state.provider_override=Embed()
    with TestClient(app,base_url='http://localhost') as c:
        login(c)
        indexed=upload(c,'indexed.txt',b'gradient descent '*1000)
        unindexed=upload(c,'unindexed.txt',b'gradient descent '*1000+b'new')
        c.put('/api/v1/settings/provider',json={'embedding_model':'m'})
        with app.state.db.connect() as con:
            con.execute('INSERT INTO embeddings SELECT id,?,?,2,?,? FROM chunks WHERE document_id=?',('http://127.0.0.1:1234/v1','m','[1,0]',now(),indexed['id']))
        evidence=retrieve_evidence(app.state.db,'gradient',document_ids=[indexed['id'],unindexed['id']],app=app)
        assert all(hit['document_id']==indexed['id'] for hit in evidence)


def test_cancellation_releases_conversation_before_provider_timeout(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    import threading
    from workspace.providers import ProviderCancelled
    entered=threading.Event()
    class SlowProvider:
        def chat(self,messages):
            entered.set()
            threading.Event().wait(2)
            return '{}'
        def chat_cancellable(self,messages,cancel_event):
            entered.set()
            cancel_event.wait(2)
            raise ProviderCancelled('cancelled')
    app=create_app(tmp_path);app.state.provider_override=SlowProvider()
    with TestClient(app,base_url='http://localhost') as c:
        login(c);upload(c,'slow.txt',b'Gradient descent uses derivatives')
        conversation=c.post('/api/v1/conversations',json={}).json()
        path='/api/v1/conversations/'+conversation['id']
        with ThreadPoolExecutor(max_workers=1) as pool:
            future=pool.submit(c.post,path+'/messages',json={'content':'gradient'})
            assert entered.wait(timeout=1)
            assert c.post(path+'/cancel').status_code==200
            assert future.result(timeout=.8).json()['status']=='cancelled'
        assert not app.state.conversation_locks[conversation['id']].locked()
