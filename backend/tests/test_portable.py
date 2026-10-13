"""Portable merge exercises real SQLite, originals and immutable snapshots."""
from io import BytesIO
import hashlib
import json
import stat
import zipfile

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
from workspace.db import Database, now


def client(root):
    from workspace.portable import router
    db = Database(root)
    db.initialize()
    app = FastAPI()
    app.state.db = db
    app.include_router(router)
    return TestClient(app), db


def insert(con, table, **row):
    con.execute(f'INSERT INTO {table} ({",".join(row)}) VALUES ({",".join("?" for _ in row)})', tuple(row.values()))


def seed(db, prefix=''):
    t = now()
    h = hashlib.sha256(b'original pdf bytes').hexdigest()
    (db.root/'originals').mkdir(exist_ok=True)
    (db.root/'originals'/h).write_bytes(b'original pdf bytes')
    def ident(name): return prefix+name
    source = dict(document_id=ident('doc'), version_id=ident('version'), locator_type='page', locator=1, quote='real evidence')
    question = dict(kind='short',prompt='Why?',options=[],correct_indices=[],answer='Because',explanation='',topic='topic',sources=[source])
    with db.connect() as con:
        insert(con,'courses',id=ident('course'),name='Shared name',created_at=t)
        insert(con,'blobs',hash=h,size=18,kind='pdf',created_at=t)
        insert(con,'documents',id=ident('doc'),blob_hash=h,title='Shared title',filename='source.pdf',kind='pdf',status='ready',active_version=ident('version'),created_at=t)
        insert(con,'document_versions',id=ident('version'),document_id=ident('doc'),created_at=t,parser_version='test')
        insert(con,'source_units',id=ident('unit'),version_id=ident('version'),locator_type='page',locator=1,text='Some real evidence here.')
        insert(con,'chunks',id=ident('chunk'),unit_id=ident('unit'),version_id=ident('version'),document_id=ident('doc'),text='Some real evidence here.',ordinal=0)
        insert(con,'document_courses',document_id=ident('doc'),course_id=ident('course'))
        insert(con,'notes',id=ident('note'),title='Shared title',body='[[Deleted]]',course_id=ident('course'),created_at=t,updated_at=t)
        insert(con,'note_sources',note_id=ident('note'),ordinal=0,**source)
        insert(con,'note_links',source_id=ident('note'),raw_title='Deleted',deleted_target_id=ident('deleted-note'))
        insert(con,'note_links',source_id=ident('note'),raw_title='Shared title',target_id=ident('note'))
        insert(con,'conversations',id=ident('conversation'),title='Chat',course_id=ident('course'),document_ids=json.dumps([ident('doc')]),created_at=t,updated_at=t)
        insert(con,'messages',id=ident('message'),conversation_id=ident('conversation'),role='assistant',content='Evidence',status='complete',sources=json.dumps([dict(source,chunk_id=ident('chunk'),text='Some real evidence here.')]),created_at=t)
        insert(con,'flashcards',id=ident('card'),front='Q',back='A',course_id=ident('course'),sources=json.dumps([source]),due_at=t,created_at=t,updated_at=t)
        for card in ['card','deleted-card']:
            insert(con,'reviews',id=ident('review-'+card),flashcard_id=ident(card),course_id=ident('course'),topic='topic',rating='good',reviewed_at=t,due_at=t,ease=2.5,repetitions=1,interval_days=1,idempotency_key='same-key')
        insert(con,'quizzes',id=ident('quiz'),title='Quiz',course_id=ident('course'),created_at=t)
        insert(con,'quiz_questions',id=ident('question'),quiz_id=ident('quiz'),ordinal=0,content=json.dumps(question))
        for q in ['quiz','deleted-quiz']:
            qid = ident('question' if q=='quiz' else 'deleted-question')
            answer = dict(question_id=qid,selected=[],text='answer',self_correct=True)
            insert(con,'attempts',id=ident('attempt-'+q),quiz_id=ident(q),quiz_title='Quiz',course_id=ident('course'),score=1,total=1,created_at=t,idempotency_key='same-key',request_json=json.dumps([answer]))
            insert(con,'attempt_answers',attempt_id=ident('attempt-'+q),question_id=qid,ordinal=0,topic='topic',selected='[]',text='answer',self_correct=1,correct=1,question=json.dumps(dict(question,id=qid)))
        insert(con,'activities',id=ident('activity'),kind='test',description='History',created_at=t)
        insert(con,'settings',key='provider',value='PRIVATE-SETTING')
        insert(con,'agent_tokens',id=ident('token'),name='secret',token_hash='SECRET-TOKEN',scope='read',created_at=t)
    return h


def export(c, **params):
    result = c.get('/api/v1/portable/export',params=params)
    assert result.status_code == 200, result.text
    return result.content


def upload(c, archive, confirm=''):
    return c.post('/api/v1/portable/import', files={'archive':('portable.zip',archive,'application/zip')},data={'confirm':confirm})


def rewrite(archive, mutate=None, extra=None, omit=None):
    with zipfile.ZipFile(BytesIO(archive)) as z: files = {n:z.read(n) for n in z.namelist()}
    if mutate:
        data = json.loads(files['data.json'])
        mutate(data['tables'])
        files['data.json'] = json.dumps(data).encode()
        manifest = json.loads(files['manifest.json'])
        manifest['files']['data.json'] = {'sha256':hashlib.sha256(files['data.json']).hexdigest(),'size':len(files['data.json'])}
        files['manifest.json'] = json.dumps(manifest).encode()
    if omit: files.pop(omit)
    out = BytesIO()
    with zipfile.ZipFile(out,'w') as z:
        for n,b in files.items(): z.writestr(n,b)
        if extra: z.writestr(*extra)
    return out.getvalue()


def snapshot(db):
    from workspace.portable import TABLES
    return {t:db.all(f'SELECT * FROM {t}') for t in TABLES}


def test_roundtrip_all_core_data_remaps_nested_and_orphan_history(tmp_path):
    src, sdb = client(tmp_path/'src'); digest = seed(sdb)
    archive = export(src)
    with zipfile.ZipFile(BytesIO(archive)) as z:
        assert set(z.namelist()) == {'manifest.json','data.json','originals/'+digest}
        assert b'SECRET-TOKEN' not in z.read('data.json') and b'PRIVATE-SETTING' not in z.read('data.json')
        assert json.loads(z.read('manifest.json'))['format'] == 'academic-workspace-portable'
    dst, db = client(tmp_path/'dst')
    preview = upload(dst,archive)
    assert preview.status_code == 200, preview.text
    assert preview.json()['status'] == 'preview'
    assert db.all('SELECT * FROM documents') == []
    result = upload(dst,archive,'IMPORT')
    assert result.status_code == 200, result.text
    mappings = result.json()['mappings']
    assert mappings['documents']['doc'] != 'doc'
    for table,rows in snapshot(sdb).items(): assert len(snapshot(db)[table]) == len(rows), table
    assert (db.root/'originals'/digest).read_bytes() == b'original pdf bytes'
    assert db.one('SELECT count(*) n FROM chunks_fts')['n'] == 1
    assert db.one('SELECT count(*) n FROM notes_fts')['n'] == 1
    assert not db.all('SELECT * FROM settings') and not db.all('SELECT * FROM agent_tokens')
    source = json.loads(db.one('SELECT sources FROM messages')['sources'])[0]
    assert source['chunk_id'] == mappings['chunks']['chunk']
    assert source['version_id'] == mappings['document_versions']['version']
    assert source['document_id'] == mappings['documents']['doc']
    for row in db.all('SELECT * FROM attempt_answers'):
        assert json.loads(row['question'])['id'] == row['question_id']
        req = json.loads(db.one('SELECT request_json FROM attempts WHERE id=?',(row['attempt_id'],))['request_json'])
        assert req[0]['question_id'] == row['question_id']
    assert db.one("SELECT deleted_target_id FROM note_links WHERE raw_title='Deleted'")['deleted_target_id'] == mappings['notes']['deleted-note']


def test_preview_no_changes_and_merge_dedup_preserves_existing(tmp_path):
    src,sdb=client(tmp_path/'src'); digest=seed(sdb)
    dst,db=client(tmp_path/'dst'); seed(db,'local-')
    before=snapshot(db)
    archive=export(src)
    response=upload(dst,archive)
    assert response.status_code==200,response.text
    assert response.json()['conflicts']['original_hashes'] == [digest]
    assert response.json()['conflicts']['courses'] and response.json()['conflicts']['titles']
    assert snapshot(db)==before
    result=upload(dst,archive,'IMPORT'); assert result.status_code==200,result.text
    assert result.json()['mappings']['documents']['doc']=='local-doc'
    assert db.all('SELECT * FROM documents')==before['documents']
    assert len(db.all('SELECT * FROM document_versions'))==2
    assert len(db.all('SELECT * FROM courses'))==2
    assert len(db.all('SELECT * FROM notes'))==2
    assert len(db.all('SELECT * FROM document_courses'))==2


def test_optional_originals_require_local_checksum(tmp_path):
    src,sdb=client(tmp_path/'src'); seed(sdb)
    archive=export(src,include_originals='false')
    dst,db=client(tmp_path/'dst')
    assert upload(dst,archive,'IMPORT').status_code==422
    seed(db,'local-')
    assert upload(dst,archive,'IMPORT').status_code==200


@pytest.mark.parametrize('mutation',[
    lambda t:t['note_sources'][0].update(quote='fabricated'),
    lambda t:t['messages'][0].update(sources='{}'),
    lambda t:t['messages'][0].update(sources=json.dumps([dict(document_id='doc',version_id='version',locator_type='page',locator=1,quote='real evidence',chunk_id='missing')])),
    lambda t:t['chunks'][0].update(unit_id='missing'),
    lambda t:t['documents'][0].update(active_version='missing'),
    lambda t:t['notes'][0].update(tags='{}'),
    lambda t:t['quiz_questions'][0].update(content='[]'),
    lambda t:t.update(settings=[]),
    lambda t:t['notes'][0].update(unexpected_column='oops'),
])
def test_invalid_payload_is_noop(tmp_path,mutation):
    src,sdb=client(tmp_path/'src'); seed(sdb)
    dst,db=client(tmp_path/'dst')
    response=upload(dst,rewrite(export(src),mutation),'IMPORT')
    assert response.status_code==422,response.text
    assert not db.all('SELECT * FROM courses')
    assert not list((db.root/'originals').glob('*')) if (db.root/'originals').exists() else True


@pytest.mark.parametrize('kind',['traversal','duplicate','symlink','checksum','missing'])
@pytest.mark.filterwarnings("ignore:Duplicate name:UserWarning")
def test_unsafe_archives_rejected(tmp_path,kind):
    src,sdb=client(tmp_path/'src'); digest=seed(sdb); archive=export(src)
    if kind=='traversal': archive=rewrite(archive,extra=('../outside',b'evil'))
    if kind=='duplicate': archive=rewrite(archive,extra=('data.json',b'{}'))
    if kind=='symlink':
        info=zipfile.ZipInfo('originals/'+'0'*64); info.external_attr=(stat.S_IFLNK|0o777)<<16
        archive=rewrite(archive,extra=(info,b'../outside'))
    if kind=='checksum': archive=rewrite(archive,extra=('originals/'+'0'*64,b'bad'))
    if kind=='missing': archive=rewrite(archive,omit='originals/'+digest)
    dst,db=client(tmp_path/'dst')
    assert upload(dst,archive,'IMPORT').status_code==422
    assert not db.all('SELECT * FROM courses')


def add_second_document(db):
    h=hashlib.sha256(b'second original').hexdigest()
    (db.root/'originals'/h).write_bytes(b'second original')
    with db.connect() as con:
        insert(con,'blobs',hash=h,size=15,kind='txt',created_at=now())
        insert(con,'documents',id='second-doc',blob_hash=h,title='Second',filename='second.txt',kind='txt',created_at=now())
        insert(con,'document_links',source_id='doc',target_id='second-doc')
    return h


def test_multiple_originals_links_and_rollback_on_install_failure(tmp_path,monkeypatch):
    import workspace.portable as portable
    src,sdb=client(tmp_path/'src'); seed(sdb); add_second_document(sdb)
    archive=export(src)
    dst,db=client(tmp_path/'dst')
    original_link=portable.os.link
    count=0
    def fail_second(source,target):
        nonlocal count
        count+=1
        if count==2: raise OSError('simulated full disk')
        original_link(source,target)
    monkeypatch.setattr(portable.os,'link',fail_second)
    assert upload(dst,archive,'IMPORT').status_code==500
    assert not db.all('SELECT * FROM courses')
    assert not list((db.root/'originals').iterdir())
    monkeypatch.setattr(portable.os,'link',original_link)
    result=upload(dst,archive,'IMPORT')
    assert result.status_code==200,result.text
    assert len(db.all('SELECT * FROM document_links'))==1


@pytest.mark.parametrize('mutate',[
    lambda t:t['messages'][0].update(sources=json.dumps([dict(document_id='doc',version_id='version',locator_type='page',locator=1,quote='real evidence',unit_id='invented-unit')])),
    lambda t:t['attempts'][0].update(request_json=json.dumps([dict(question_id='question',selected=[],text='tampered answer',self_correct=True)])),
    lambda t:t['attempt_answers'][0].update(question=json.dumps(dict(kind='short',prompt='Why?',options=[],correct_indices=[],answer='Because',explanation='',topic='topic',sources=[],id='wrong-question'))),
    lambda t:t['note_links'][0].update(target_id='note'),
])
def test_inconsistent_history_or_source_rejected(tmp_path,mutate):
    src,sdb=client(tmp_path/'src'); seed(sdb)
    dst,db=client(tmp_path/'dst')
    response=upload(dst,rewrite(export(src),mutate),'IMPORT')
    assert response.status_code==422,response.text
    assert not db.all('SELECT * FROM courses')


def test_data_size_budget_rejects_before_parsing(tmp_path,monkeypatch):
    import workspace.portable as portable
    src,sdb=client(tmp_path/'src'); seed(sdb); archive=export(src)
    dst,db=client(tmp_path/'dst')
    monkeypatch.setattr(portable,'MAX_DATA_BYTES',20)
    assert upload(dst,archive,'IMPORT').status_code==422


def test_original_bytes_bad_checksum_is_noop(tmp_path):
    src,sdb=client(tmp_path/'src'); digest=seed(sdb)
    archive=export(src)
    with zipfile.ZipFile(BytesIO(archive)) as z: files={n:z.read(n) for n in z.namelist()}
    files['originals/'+digest]=b'X'*18
    out=BytesIO()
    with zipfile.ZipFile(out,'w') as z:
        for n,b in files.items(): z.writestr(n,b)
    dst,db=client(tmp_path/'dst')
    assert upload(dst,out.getvalue(),'IMPORT').status_code==422
    assert not db.all('SELECT * FROM courses')


def test_existing_document_links_are_deduplicated(tmp_path):
    src,sdb=client(tmp_path/'src'); seed(sdb); add_second_document(sdb)
    dst,db=client(tmp_path/'dst')
    archive=export(src)
    assert upload(dst,archive,'IMPORT').status_code==200
    response=upload(dst,archive,'IMPORT')
    assert response.status_code==200,response.text
    assert len(db.all('SELECT * FROM document_links'))==1
    assert len(db.all('SELECT * FROM document_versions'))==2
    assert len(db.all('SELECT * FROM reviews'))==4


def test_rebuilt_fts_retains_chinese_tokenization(tmp_path):
    src,sdb=client(tmp_path/'src'); seed(sdb)
    with sdb.connect() as con:
        insert(con,'source_units',id='chinese-unit',version_id='version',locator_type='page',locator=2,text='数学科学')
        insert(con,'chunks',id='chinese-chunk',unit_id='chinese-unit',version_id='version',document_id='doc',text='数学科学',ordinal=1)
    dst,db=client(tmp_path/'dst')
    assert upload(dst,export(src),'IMPORT').status_code==200
    assert db.one("SELECT count(*) n FROM chunks_fts WHERE chunks_fts MATCH '数学'")['n']==1


@pytest.mark.parametrize('status',['queued','processing'])
def test_pending_document_import_requires_manual_retry_and_preserves_sources(tmp_path,status):
    src,sdb=client(tmp_path/'src'); seed(sdb)
    with sdb.connect() as con: con.execute('UPDATE documents SET status=?',(status,))
    dst,db=client(tmp_path/'dst')
    result=upload(dst,export(src),'IMPORT')
    assert result.status_code==200,result.text
    doc=db.one('SELECT * FROM documents')
    assert doc['status']=='failed'
    assert result.json()['retry_required_document_ids']==[doc['id']]
    assert doc['active_version']==result.json()['mappings']['document_versions']['version']
    assert json.loads(db.one('SELECT sources FROM messages')['sources'])[0]['version_id']==doc['active_version']
    assert not db.all('SELECT * FROM jobs')
    # Reimport never changes the metadata/state of the existing same-hash doc.
    with db.connect() as con: con.execute("UPDATE documents SET status='ready'")
    again=upload(dst,export(src),'IMPORT')
    assert again.status_code==200,again.text
    assert db.one('SELECT status FROM documents')['status']=='ready'
    assert again.json()['retry_required_document_ids']==[]


def mutate_grading(tables,case,deleted):
    identifier='attempt-deleted-quiz' if deleted else 'attempt-quiz'
    attempt=next(r for r in tables['attempts'] if r['id']==identifier)
    answer=next(r for r in tables['attempt_answers'] if r['attempt_id']==identifier)
    request=json.loads(attempt['request_json'])
    if case=='wrong_grade':
        answer['correct']=0; attempt['score']=0
    elif case=='short_selected':
        answer['selected']='[999]'; request[0]['selected']=[999]
    elif case=='choice_out_of_range':
        question=json.loads(answer['question'])
        question.update(kind='single',options=['A','B'],correct_indices=[0])
        answer.update(question=json.dumps(question),selected='[999]',self_correct=None,correct=0)
        request[0].update(selected=[999],self_correct=None); attempt['score']=0
    elif case=='invalid_self_correct':
        answer['self_correct']=2
    elif case=='wrong_topic':
        answer['topic']='invented-topic'
    attempt['request_json']=json.dumps(request)


@pytest.mark.parametrize('case',['wrong_grade','short_selected','choice_out_of_range','invalid_self_correct','wrong_topic'])
@pytest.mark.parametrize('deleted',[False,True])
def test_attempt_snapshot_regraded_and_invalid_answers_rejected(tmp_path,case,deleted):
    src,sdb=client(tmp_path/'src'); seed(sdb)
    archive=rewrite(export(src),lambda t:mutate_grading(t,case,deleted))
    dst,db=client(tmp_path/'dst')
    response=upload(dst,archive,'IMPORT')
    assert response.status_code==422,response.text
    assert not db.all('SELECT * FROM courses')


def test_attempt_validation_uses_immutable_snapshot_after_quiz_edit(tmp_path):
    src,sdb=client(tmp_path/'src'); seed(sdb)
    with sdb.connect() as con:
        live=json.loads(con.execute("SELECT content FROM quiz_questions WHERE id='question'").fetchone()['content'])
        live.update(kind='single',options=['A','B'],correct_indices=[1])
        con.execute("DELETE FROM quiz_questions WHERE id='question'")
        insert(con,'quiz_questions',id='replacement-question',quiz_id='quiz',ordinal=0,content=json.dumps(live))
    dst,db=client(tmp_path/'dst')
    response=upload(dst,export(src),'IMPORT')
    assert response.status_code==200,response.text
    assert len(db.all('SELECT * FROM attempts'))==2
    assert all(json.loads(r['question'])['kind']=='short' for r in db.all('SELECT question FROM attempt_answers'))
