import time
from fastapi.testclient import TestClient
from workspace.app import create_app
from test_core import login


def wait_document(c, identifier):
    for _ in range(100):
        doc = c.get('/api/v1/documents/'+identifier).json()
        if doc['status'] not in ('queued','processing'):
            return doc
        time.sleep(.02)
    raise AssertionError('Index job did not finish')


def upload(c, name, content, course_id=''):
    r = c.post('/api/v1/documents',files=[('files',(name,content))],data={'course_id':course_id})
    assert r.status_code == 202, r.text
    return wait_document(c,r.json()[0]['id'])


def test_import_dedup_versions_original_and_relations(tmp_path):
    with TestClient(create_app(tmp_path), base_url='http://localhost') as c:
        login(c)
        course = c.post('/api/v1/courses',json={'name':'ML'}).json()
        original = '# Gradient Descent\n梯度下降 learns parameters with derivatives.'.encode()
        doc = upload(c,'lesson.md',original,course['id'])
        assert doc['status'] == 'ready', doc
        assert c.get('/api/v1/documents/'+doc['id']+'/original').content == original
        units = c.get('/api/v1/documents/'+doc['id']+'/units').json()
        assert units[0]['locator_type'] == 'line'
        assert '梯度下降' in units[0]['text']
        duplicate = upload(c,'renamed.md',original)
        assert duplicate['id'] == doc['id']
        assert len(list((tmp_path/'originals').iterdir())) == 1
        assert c.post('/api/v1/documents/'+doc['id']+'/reindex').status_code == 202
        new = wait_document(c,doc['id'])
        assert new['active_version'] != doc['active_version']
        old = c.get('/api/v1/documents/'+doc['id']+'/units',params={'version_id':doc['active_version']}).json()
        assert old == units
        updated = c.patch('/api/v1/documents/'+doc['id'],json={'favorite':True,'tags':['optimization','中文'],'topic':'Gradient','course_ids':[course['id']]}).json()
        assert updated['favorite'] and updated['tags'] == ['optimization','中文']
        assert c.get('/api/v1/documents',params={'course_id':course['id']}).json()[0]['id'] == doc['id']
        assert c.get('/api/v1/jobs').json()[0]['status'] == 'done'


def test_reject_invalid_upload_and_report_parse_failure(tmp_path):
    with TestClient(create_app(tmp_path), base_url='http://localhost') as c:
        login(c)
        assert c.post('/api/v1/documents',files={'files':('malware.exe',b'bad')}).status_code == 422
        assert c.post('/api/v1/documents',files={'files':('a.md',b'ok')},data={'course_id':'missing'}).status_code == 404
        bad = upload(c,'corrupt.pdf',b'not a pdf')
        assert bad['status'] == 'failed'
        jobs = c.get('/api/v1/jobs').json()
        assert jobs[0]['error']
        empty = upload(c,'empty.txt',b'   ')
        assert empty['status'] == 'needs_attention'


def test_failed_reindex_keeps_previous_sources(tmp_path):
    with TestClient(create_app(tmp_path), base_url='http://localhost') as c:
        login(c)
        doc = upload(c,'safe.txt',b'Useful evidence')
        (tmp_path/'originals'/doc['blob_hash']).write_bytes(b'\xff\xfe\x00')
        c.post('/api/v1/documents/'+doc['id']+'/reindex')
        failed = wait_document(c,doc['id'])
        assert failed['active_version'] == doc['active_version']
        assert c.get('/api/v1/documents/'+doc['id']+'/units').json()[0]['text'] == 'Useful evidence'


def test_corrected_extension_recovers_failed_import(tmp_path):
    with TestClient(create_app(tmp_path),base_url='http://localhost') as c:
        login(c)
        first=upload(c,'mistake.pdf',b'This is a text lesson')
        assert first['status']=='failed'
        recovered=upload(c,'correct.txt',b'This is a text lesson')
        assert recovered['id']==first['id']
        assert recovered['status']=='ready'
        assert recovered['kind']=='txt'


def test_plain_document_heading_uses_filename_not_storage_hash(tmp_path):
    from docx import Document
    from io import BytesIO
    doc=Document();doc.add_paragraph('A lesson without a heading style.')
    data=BytesIO();doc.save(data)
    with TestClient(create_app(tmp_path),base_url='http://localhost') as c:
        login(c)
        uploaded=upload(c,'Lesson.docx',data.getvalue())
        unit=c.get('/api/v1/documents/'+uploaded['id']+'/units').json()[0]
        assert unit['heading']=='Lesson'


def test_extracted_title_and_topic_filter_preserve_manual_title(tmp_path):
    with TestClient(create_app(tmp_path),base_url='http://localhost') as c:
        login(c)
        doc=upload(c,'untitled-upload.md',b'# Bayesian inference\nBayes combines likelihood and prior.')
        assert doc['title']=='Bayesian inference'
        c.patch('/api/v1/documents/'+doc['id'],json={'title':'My edited title','topic':'Probability'})
        assert c.get('/api/v1/documents',params={'topic':'Other'}).json()==[]
        assert c.get('/api/v1/documents',params={'topic':'Probability'}).json()[0]['id']==doc['id']
        c.post('/api/v1/documents/'+doc['id']+'/reindex')
        assert wait_document(c,doc['id'])['title']=='My edited title'


def test_folder_relative_path_is_metadata_not_storage_path(tmp_path):
    with TestClient(create_app(tmp_path),base_url='http://localhost') as c:
        login(c)
        doc=upload(c,'semester/course/lecture.md',b'# Folder lecture\nLocal source')
        assert doc['relative_path']=='semester/course/lecture.md'
        assert doc['filename']=='lecture.md'
        assert c.get('/api/v1/documents/'+doc['id']+'/original').content==b'# Folder lecture\nLocal source'
        assert c.post('/api/v1/documents',files={'files':('../escape.md',b'bad')}).status_code==422
