from fastapi.testclient import TestClient
from workspace.app import create_app
from test_core import login
from test_documents import upload


def test_bilingual_search_filters_and_safe_queries(tmp_path):
    with TestClient(create_app(tmp_path),base_url='http://localhost') as c:
        login(c)
        first = c.post('/api/v1/courses',json={'name':'Machine Learning'}).json()
        other = c.post('/api/v1/courses',json={'name':'Statistics'}).json()
        doc = upload(c,'gradient.md','# Gradient Descent\n梯度下降使用导数优化参数. The learning rate controls convergence.'.encode(),first['id'])
        upload(c,'other.txt',b'Gradient descent alternative.',other['id'])
        for query in ['梯','梯度','梯度下降','learning rate','gradient']:
            r = c.get('/api/v1/search',params={'q':query,'course_id':first['id']})
            assert r.status_code == 200, r.text
            result = r.json()
            assert result['hits'], query
            assert all(h['document_id'] == doc['id'] for h in result['hits'])
            assert result['hits'][0]['locator'] == 1
        assert c.get('/api/v1/search',params={'q':'梯度','kind':'pdf'}).json()['hits'] == []
        assert c.get('/api/v1/search',params={'q':'gradient','document_id':doc['id']}).json()['total'] == 1
        assert c.get('/api/v1/search',params={'q':'gradient','limit':1,'offset':1}).json()['hits']
        for query in ['"','%',"' OR 1=1 --",'NEAR(','*']:
            assert c.get('/api/v1/search',params={'q':query}).status_code == 200


def test_scoped_search_is_not_crowded_out_by_global_candidates(tmp_path):
    from workspace.db import new_id, now
    from workspace.search import search
    app=create_app(tmp_path)
    db=app.state.db
    with db.connect() as con:
        for index in range(1005):
            key=str(index)
            con.execute('INSERT INTO blobs VALUES (?,?,?,?)',(key,1,'txt',now()))
            con.execute('INSERT INTO documents(id,blob_hash,title,filename,kind,created_at,active_version) VALUES (?,?,?,?,?,?,?)',(key,key,key,key,'txt',now(),key))
            con.execute('INSERT INTO document_versions VALUES (?,?,?,?)',(key,key,now(),'1'))
            con.execute('INSERT INTO source_units VALUES (?,?,?,?,?,?)',(key,key,'line',1,'','gradient and descent'))
            con.execute('INSERT INTO chunks VALUES (?,?,?,?,?,?)',(key,key,key,key,'gradient and descent',0))
            con.execute('INSERT INTO chunks_fts VALUES (?,?)',(key,'gradient and descent'))
    result=search(db,'gradient descent',document_id='1004')
    assert result['total']==1
    # Exercise the same variable-limit failure without allocating 33k documents.
    from contextlib import contextmanager
    import sqlite3
    original_connect=db.connect
    @contextmanager
    def limited_connection():
        with original_connect() as con:
            con.setlimit(sqlite3.SQLITE_LIMIT_VARIABLE_NUMBER,100)
            yield con
    db.connect=limited_connection
    assert len(search(db,'gradient',limit=20)['hits'])==20


def test_spaced_chinese_terms_match_continuous_source_text(tmp_path):
    with TestClient(create_app(tmp_path),base_url='http://localhost') as c:
        login(c)
        doc=upload(c,'chinese.txt','梯度下降使用导数优化参数'.encode())
        result=c.get('/api/v1/search',params={'q':'梯度 参数'}).json()
        assert result['hits'][0]['document_id']==doc['id']


def test_natural_chinese_question_uses_indexed_character_fragments(tmp_path):
    with TestClient(create_app(tmp_path),base_url='http://localhost') as c:
        login(c)
        doc=upload(c,'concept.txt','梯度下降利用导数优化参数。'.encode())
        result=c.get('/api/v1/search',params={'q':'什么是梯度下降？'}).json()
        assert result['hits'] and result['hits'][0]['document_id']==doc['id']
