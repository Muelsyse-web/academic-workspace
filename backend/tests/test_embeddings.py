import time
from fastapi.testclient import TestClient
from workspace.app import create_app
from workspace.embeddings import semantic_search
from workspace.providers import ProviderError
from test_core import login
from test_documents import upload

class MockEmbedding:
    def embed(self,texts):
        return [[1.,0.] if ('car' in t or 'automobile' in t) else [0.,1.] for t in texts]


def test_semantic_synonyms_scope_and_model_change(tmp_path):
    app=create_app(tmp_path);app.state.provider_override=MockEmbedding()
    with TestClient(app,base_url='http://localhost') as c:
        login(c)
        course=c.post('/api/v1/courses',json={'name':'Transport'}).json()
        target=upload(c,'transport.txt',b'An automobile is a motor vehicle.',course['id'])
        other=upload(c,'botany.txt',b'Trees have roots and leaves.')
        c.put('/api/v1/settings/provider',json={'embedding_model':'mock-multilingual'})
        response=c.post('/api/v1/embeddings/reindex')
        assert response.status_code==202,response.text
        for _ in range(100):
            state=c.get('/api/v1/embeddings/status').json()
            if state['status'] not in ('queued','processing'):break
            time.sleep(.01)
        assert state['status']=='done',state
        result=semantic_search(app,'car',course_id=course['id'])
        assert result['mode']=='semantic'
        assert result['hits'][0]['document_id']==target['id']
        assert all(hit['document_id']!=other['id'] for hit in result['hits'])
        c.put('/api/v1/settings/provider',json={'embedding_model':'new-model'})
        result=semantic_search(app,'car')
        assert result['mode']=='keyword'
        assert result['warning']


def test_embedding_failure_preserves_old_index(tmp_path):
    app=create_app(tmp_path);app.state.provider_override=MockEmbedding()
    with TestClient(app,base_url='http://localhost') as c:
        login(c);upload(c,'transport.txt',b'An automobile moves.')
        c.put('/api/v1/settings/provider',json={'embedding_model':'mock'})
        for fail in (False,True):
            if fail:
                class Failing:
                    def embed(self,texts):raise ProviderError('Offline')
                app.state.provider_override=Failing()
            c.post('/api/v1/embeddings/reindex')
            for _ in range(100):
                state=c.get('/api/v1/embeddings/status').json()
                if state['status'] not in ('queued','processing'):break
                time.sleep(.01)
            assert state['status']==('failed' if fail else 'done')
        assert app.state.db.one('SELECT count(*) n FROM embeddings')['n']==1


def test_model_configuration_and_transport_are_one_snapshot(tmp_path,monkeypatch):
    from workspace import embeddings, configuration
    app=create_app(tmp_path)
    with TestClient(app,base_url='http://localhost') as c:
        login(c)
        c.put('/api/v1/settings/provider',json={'embedding_model':'model-A'})
        captured={}
        real=configuration.provider_config
        def racing_config(db):
            config=real(db)
            with db.connect() as con:
                import json
                con.execute("UPDATE settings SET value=? WHERE key='provider'",(json.dumps({**config,'embedding_model':'model-B'}),))
            return config
        monkeypatch.setattr(configuration,'provider_config',racing_config)
        monkeypatch.setattr(embeddings,'provider_config',racing_config)
        def capture(identifier,config,provider):captured.update(config=config,provider=provider)
        monkeypatch.setattr(app.state.embedding_worker,'submit',capture)
        c.post('/api/v1/embeddings/reindex')
        assert captured['config']['embedding_model']=='model-A'
        assert captured['provider'].embedding_model=='model-A'


def test_source_change_during_rebuild_does_not_publish_obsolete_vectors(tmp_path):
    app=create_app(tmp_path)
    with TestClient(app,base_url='http://localhost') as c:
        login(c)
        doc=upload(c,'changing.txt',b'automobile evidence '*4000)
        c.put('/api/v1/settings/provider',json={'embedding_model':'mock'})
        class ChangeSource(MockEmbedding):
            def embed(self,texts):
                with app.state.db.connect() as con:
                    con.execute('UPDATE documents SET active_version=NULL WHERE id=?',(doc['id'],))
                return super().embed(texts)
        app.state.provider_override=ChangeSource()
        c.post('/api/v1/embeddings/reindex')
        for _ in range(200):
            state=c.get('/api/v1/embeddings/status').json()
            if state['status'] not in ('queued','processing'):break
            time.sleep(.01)
        assert state['status']=='failed'
        assert app.state.db.one('SELECT count(*) n FROM embeddings')['n']==0
