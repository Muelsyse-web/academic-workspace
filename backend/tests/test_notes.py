"""Real SQLite/API tests for source-linked notes, with synthetic source data."""
from io import BytesIO
import json
from pathlib import Path
from zipfile import ZipFile

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from workspace.db import Database, now
from workspace.notes import router


def note_client(root):
    db = Database(root)
    db.initialize()
    schema = Path(__file__).parents[1] / 'workspace' / 'notes_schema.sql'
    with db.connect() as con:
        con.executescript(schema.read_text())
    app = FastAPI()
    app.state.db = db
    app.include_router(router)
    return TestClient(app), db


@pytest.fixture
def notes(tmp_path):
    client, db = note_client(tmp_path)
    with db.connect() as con:
        con.execute("INSERT INTO courses VALUES ('course','AI','AI','2026','#000000',?)", (now(),))
        con.execute("INSERT INTO blobs VALUES ('hash',12,'pdf',?)", (now(),))
        con.execute("INSERT INTO documents(id,blob_hash,title,filename,kind,created_at) VALUES ('doc','hash','Source 文档','source.pdf','pdf',?)", (now(),))
        con.execute("INSERT INTO document_versions VALUES ('v1','doc',?,'test')", (now(),))
        con.execute("INSERT INTO source_units VALUES ('u1','v1','page',2,'','A real source quote 原文摘录.')")
    return client, db


def create(client, **values):
    response = client.post('/api/v1/notes', json={'title':'Test', **values})
    assert response.status_code == 201, response.text
    return response.json()


def ref(**values):
    return {'document_id':'doc','version_id':'v1','locator_type':'page','locator':2,'quote':'real source quote', **values}


def test_crud_and_persistence(notes):
    client, db = notes
    row = create(client, title='笔记', body='A **note** with $x^2$', course_id='course', topic='概率', tags=['复习'], sources=[ref()])
    assert row['id'] and row['created_at'] and row['updated_at']
    assert row['sources'][0]['quote'] == 'real source quote'
    updated = client.patch('/api/v1/notes/'+row['id'], json={'title':'Renamed','tags':['math'],'course_id':None}).json()
    assert updated['title'] == 'Renamed' and updated['course_id'] is None
    fresh, _ = note_client(db.root)
    assert fresh.get('/api/v1/notes/'+row['id']).json()['tags'] == ['math']
    assert fresh.delete('/api/v1/notes/'+row['id']).status_code == 204
    assert fresh.get('/api/v1/notes/'+row['id']).status_code == 404


@pytest.mark.parametrize('source', [ref(quote='fabricated'),ref(quote=''),ref(quote=' '),ref(locator=1),ref(version_id='missing'),ref(document_id='other'),ref(locator_type='paragraph')])
def test_reject_invalid_source(notes, source):
    client, _ = notes
    assert client.post('/api/v1/notes', json={'title':'Bad','sources':[source]}).status_code == 422
    assert client.get('/api/v1/notes').json() == []


def test_bad_edit_rolls_back_note_and_links(notes):
    client, _ = notes
    target = create(client, title='Target')
    row = create(client, body='[[Target]]',sources=[ref()])
    bad = client.patch('/api/v1/notes/'+row['id'], json={'body':'changed','sources':[ref(quote='invented')]})
    assert bad.status_code == 422
    actual = client.get('/api/v1/notes/'+row['id']).json()
    assert actual == row
    assert client.get('/api/v1/notes/'+target['id']).json()['backlinks'][0]['id'] == row['id']


def test_links_rename_stability_and_delete(notes):
    client, _ = notes
    target = create(client, title='目标')
    row = create(client, body='[[目标]] and [[Missing]]')
    assert row['outgoing_links'][0]['id'] == target['id']
    assert row['unresolved_links'] == [{'raw_title':'Missing','reason':'missing'}]
    client.patch('/api/v1/notes/'+target['id'], json={'title':'New title'})
    edited = client.patch('/api/v1/notes/'+row['id'], json={'body':'Edited [[目标]] and [[Missing]]'}).json()
    assert edited['outgoing_links'][0]['id'] == target['id']
    assert edited['outgoing_links'][0]['title'] == 'New title'
    client.delete('/api/v1/notes/'+target['id'])
    actual = client.get('/api/v1/notes/'+row['id']).json()
    assert actual['outgoing_links'] == []
    assert {'raw_title':'目标','reason':'deleted'} in actual['unresolved_links']


def test_ambiguity_and_later_resolution(notes):
    client, _ = notes
    one = create(client,title='Same')
    two = create(client,title='Same')
    row = create(client,body='[[Same]] [[Later]]')
    assert row['outgoing_links'] == []
    assert {'raw_title':'Same','reason':'ambiguous'} in row['unresolved_links']
    later = create(client,title='Later')
    client.delete('/api/v1/notes/'+two['id'])
    actual = client.get('/api/v1/notes/'+row['id']).json()
    assert {r['id'] for r in actual['outgoing_links']} == {one['id'],later['id']}
    assert actual['unresolved_links'] == []
    client.patch('/api/v1/notes/'+row['id'],json={'body':'No links'})
    assert client.get('/api/v1/notes/'+one['id']).json()['backlinks'] == []


def test_literal_bilingual_search_and_filters(notes):
    client, _ = notes
    a = create(client,title='Probability',body='条件概率 100% _exact_',course_id='course',topic='Math')
    create(client,title='Other',body='Nothing',topic='Other')
    for query in ['probability','条件概率','%','_exact_']:
        assert [r['id'] for r in client.get('/api/v1/notes',params={'q':query}).json()] == [a['id']]
    assert len(client.get('/api/v1/notes',params={'course_id':'course','topic':'Math'}).json()) == 1
    assert client.get('/api/v1/notes',params={'q':'Probability','topic':'Other'}).json() == []
    assert client.get('/api/v1/notes',params={'course_id':'missing'}).json() == []


def test_exports_have_markdown_and_manifest_only(notes):
    client, _ = notes
    row = create(client,title='../unsafe/中文',body='## 中文正文\n$x^2$',sources=[ref()])
    single = client.get('/api/v1/notes/'+row['id']+'/export')
    assert single.status_code == 200 and 'text/markdown' in single.headers['content-type']
    assert '# ../unsafe/中文' in single.text and 'Source 文档' in single.text
    assert 'page 2' in single.text and 'v1' in single.text and 'real source quote' in single.text
    bulk = client.get('/api/v1/notes/export')
    assert bulk.status_code == 200 and 'application/zip' in bulk.headers['content-type']
    with ZipFile(BytesIO(bulk.content)) as archive:
        assert set(archive.namelist()) == {row['id']+'.md','manifest.json'}
        manifest = json.loads(archive.read('manifest.json'))
        assert manifest['version'] == 1
        assert manifest['notes'][0]['id'] == row['id']
        assert manifest['notes'][0]['sources'][0]['version_id'] == 'v1'
        assert archive.read(row['id']+'.md').decode('utf-8') == single.text


@pytest.mark.parametrize('payload',[{'title':' '},{'title':None},{'body':None},{'sources':None},{'tags':None},{'course_id':'missing'}])
def test_bad_patch_is_422_and_retains_state(notes,payload):
    client, _ = notes
    row = create(client,body='Original')
    response = client.patch('/api/v1/notes/'+row['id'],json=payload)
    assert response.status_code == 422
    assert client.get('/api/v1/notes/'+row['id']).json() == row


def test_sources_use_immutable_version_not_active_version(notes):
    client, db = notes
    with db.connect() as con:
        con.execute("INSERT INTO document_versions VALUES ('v2','doc',?,'test2')", (now(),))
        con.execute("INSERT INTO source_units VALUES ('u2','v2','page',2,'','Changed source text')")
        con.execute("UPDATE documents SET active_version='v2' WHERE id='doc'")
    row = create(client, sources=[ref()])
    assert row['sources'][0]['version_id'] == 'v1'
    assert client.patch('/api/v1/notes/'+row['id'],json={'sources':[ref(version_id='v2')]}).status_code == 422
    assert client.get('/api/v1/notes/'+row['id']).json()['sources'][0]['version_id'] == 'v1'


def test_resolved_link_survives_later_duplicate_and_restart(notes):
    client, db = notes
    first = create(client,title='Original')
    row = create(client,body='[[Original]]')
    create(client,title='Original')
    restarted, _ = note_client(db.root)
    assert restarted.get('/api/v1/notes/'+row['id']).json()['outgoing_links'][0]['id'] == first['id']
    restarted.patch('/api/v1/notes/'+first['id'],json={'title':'Renamed'})
    assert restarted.get('/api/v1/notes/'+row['id']).json()['outgoing_links'][0]['id'] == first['id']


@pytest.mark.parametrize('method,path,payload',[
    ('get','/api/v1/notes/missing',None),
    ('get','/api/v1/notes/missing/export',None),
    ('patch','/api/v1/notes/missing',{'title':'New'}),
    ('delete','/api/v1/notes/missing',None),
])
def test_missing_notes_are_404(notes,method,path,payload):
    client, _ = notes
    assert client.request(method,path,**({'json':payload} if payload else {})).status_code == 404


def test_fts_follows_note_edits_and_deletes(notes):
    client, db = notes
    row = create(client,title='Initial term',body='Body')
    assert db.one('SELECT note_id FROM notes_fts WHERE notes_fts MATCH ?',('Initial',))['note_id'] == row['id']
    client.patch('/api/v1/notes/'+row['id'],json={'title':'Changed'})
    assert db.all('SELECT note_id FROM notes_fts WHERE notes_fts MATCH ?',('Initial',)) == []
    assert db.one('SELECT note_id FROM notes_fts WHERE notes_fts MATCH ?',('Changed',))['note_id'] == row['id']
    client.delete('/api/v1/notes/'+row['id'])
    assert db.all('SELECT * FROM notes_fts') == []


@pytest.mark.parametrize('duplicate_before_delete', [True, False])
def test_deleted_target_never_silently_retargets_same_title(notes, duplicate_before_delete):
    client, db = notes
    original = create(client, title='Same')
    linked = create(client, body='[[Same]]')
    assert linked['outgoing_links'][0]['id'] == original['id']
    if duplicate_before_delete:
        replacement = create(client, title='Same')
    assert client.delete('/api/v1/notes/'+original['id']).status_code == 204
    if not duplicate_before_delete:
        replacement = create(client, title='Same')
    client.patch('/api/v1/notes/'+linked['id'], json={'body':'Edited [[Same]]'})
    restarted, _ = note_client(db.root)
    actual = restarted.get('/api/v1/notes/'+linked['id']).json()
    assert actual['outgoing_links'] == []
    assert actual['unresolved_links'] == [{'raw_title':'Same','reason':'deleted'}]
    assert restarted.get('/api/v1/notes/'+replacement['id']).json()['backlinks'] == []
    # Removing and then recreating a link intentionally establishes a new binding.
    restarted.patch('/api/v1/notes/'+linked['id'], json={'body':'No links'})
    recreated = restarted.patch('/api/v1/notes/'+linked['id'], json={'body':'[[Same]]'}).json()
    assert recreated['outgoing_links'][0]['id'] == replacement['id']
