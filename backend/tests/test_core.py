from fastapi.testclient import TestClient
from workspace.app import create_app


def login(client):
    r = client.post('/api/v1/session')
    assert r.status_code == 200, r.text
    client.headers['X-CSRF-Token'] = r.json()['csrf_token']


def test_courses_auth_validation_and_persistence(tmp_path):
    with TestClient(create_app(tmp_path), base_url='http://localhost') as c:
        assert c.get('/api/v1/courses').status_code == 401
        login(c)
        assert c.post('/api/v1/courses', json={'name':'   '}).status_code == 422
        r = c.post('/api/v1/courses', json={'name':'Machine Learning','code':'COMP3340','semester':'2026 Fall'})
        assert r.status_code == 201, r.text
        course = r.json()
        assert c.get('/api/v1/courses').json()[0]['code'] == 'COMP3340'
        assert c.patch('/api/v1/courses/'+course['id'], json={'name':'机器学习'}).status_code == 200
        assert c.get('/api/v1/dashboard').json()['courses'] == 1
    with TestClient(create_app(tmp_path), base_url='http://localhost') as c:
        login(c)
        assert c.get('/api/v1/courses').json()[0]['name'] == '机器学习'
        assert c.delete('/api/v1/courses/'+course['id']).status_code == 204


def test_browser_origin_host_and_csrf(tmp_path):
    with TestClient(create_app(tmp_path), base_url='http://localhost') as c:
        assert c.post('/api/v1/session', headers={'Origin':'https://evil.example'}).status_code == 403
        assert c.get('/api/v1/health', headers={'Host':'evil.example'}).status_code == 400
        login(c)
        del c.headers['X-CSRF-Token']
        assert c.post('/api/v1/courses', json={'name':'Bad'}).status_code == 403
        assert c.get('/api/v1/courses', headers={'Sec-Fetch-Site':'cross-site'}).status_code == 403


def test_agent_tokens_are_scoped_and_revocable(tmp_path):
    with TestClient(create_app(tmp_path), base_url='http://localhost') as browser:
        login(browser)
        token = browser.post('/api/v1/agent-tokens', json={'name':'Codex','scope':'read'}).json()
        with TestClient(browser.app, base_url='http://localhost') as agent:
            agent.headers['Authorization'] = 'Bearer '+token['token']
            assert agent.get('/api/v1/courses').status_code == 200
            assert agent.post('/api/v1/courses', json={'name':'Denied'}).status_code == 403
            assert agent.get('/api/v1/agent-tokens').status_code == 403
            assert browser.delete('/api/v1/agent-tokens/'+token['id']).status_code == 204
            assert agent.get('/api/v1/courses').status_code == 401


def test_request_limit_rejects_before_multipart_spooling(tmp_path):
    with TestClient(create_app(tmp_path), base_url='http://localhost') as c:
        login(c)
        r = c.post('/api/v1/documents',content=b'bad',headers={'content-type':'multipart/form-data; boundary=x','content-length':str(300*1024*1024)})
        assert r.status_code == 413


def test_invalid_course_patch_returns_validation_error(tmp_path):
    with TestClient(create_app(tmp_path), base_url='http://localhost') as c:
        login(c)
        course=c.post('/api/v1/courses',json={'name':'Course'}).json()
        assert c.patch('/api/v1/courses/'+course['id'],json={'color':'blue'}).status_code==422


def test_chunked_body_limit_without_content_length(tmp_path):
    from workspace.limits import RequestLimits
    app=create_app(tmp_path)
    app.add_middleware(RequestLimits,max_bytes=50)
    with TestClient(app,base_url='http://localhost') as c:
        login(c)
        def body():
            yield b'--x\r\nContent-Disposition: form-data; name="files"; filename="a.txt"\r\n\r\n'
            yield b'x'*60+b'\r\n--x--\r\n'
        r=c.post('/api/v1/documents',content=body(),headers={'Content-Type':'multipart/form-data; boundary=x'})
        assert r.status_code==413


def test_new_tab_bootstrap_keeps_existing_tabs_csrf_valid(tmp_path):
    with TestClient(create_app(tmp_path),base_url='http://localhost') as c:
        login(c)
        old_csrf=c.headers['X-CSRF-Token']
        old_cookie=c.cookies.get('workspace_session')
        new_tab=c.post('/api/v1/session')
        assert new_tab.json()['csrf_token']==old_csrf
        assert c.cookies.get('workspace_session')==old_cookie
        assert c.post('/api/v1/courses',json={'name':'Older tab still saves'}).status_code==201


def test_restore_cannot_overtake_an_admitted_request(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    import threading
    from fastapi import APIRouter
    app=create_app(tmp_path)
    entered=threading.Event();release=threading.Event()
    router=APIRouter()
    @router.post('/api/v1/held-request')
    def held():
        entered.set()
        release.wait(timeout=5)
        return {'done':True}
    app.router.routes[0:0]=router.routes
    with TestClient(app,base_url='http://localhost') as c:
        login(c)
        with ThreadPoolExecutor(max_workers=1) as pool:
            future=pool.submit(c.post,'/api/v1/held-request')
            assert entered.wait(timeout=3)
            try:
                response=c.post('/api/v1/restore',files={'archive':('unused.zip',b'not-read')},data={'confirm':'RESTORE'})
                assert response.status_code==409
            finally:
                release.set()
            assert future.result(timeout=3).status_code==200


def test_new_requests_are_rejected_while_restore_owns_admission(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    import threading
    from fastapi import APIRouter
    app=create_app(tmp_path)
    entered=threading.Event();release=threading.Event()
    router=APIRouter()
    @router.post('/api/v1/restore')
    def held_restore():
        entered.set();release.wait(timeout=5)
        return {'status':'test-only'}
    app.router.routes[0:0]=router.routes
    with TestClient(app,base_url='http://localhost') as c:
        login(c)
        with ThreadPoolExecutor(max_workers=1) as pool:
            future=pool.submit(c.post,'/api/v1/restore')
            assert entered.wait(timeout=3)
            try:assert c.get('/api/v1/courses').status_code==409
            finally:release.set()
            assert future.result(timeout=3).status_code==200
        assert c.get('/api/v1/courses').status_code==200


def test_course_progress_comes_from_actual_learning_records(tmp_path):
    with TestClient(create_app(tmp_path),base_url='http://localhost') as c:
        login(c)
        course=c.post('/api/v1/courses',json={'name':'Progress'}).json()
        c.post('/api/v1/notes',json={'title':'Understanding','course_id':course['id']})
        card=c.post('/api/v1/flashcards',json={'front':'Question','back':'Answer','course_id':course['id']}).json()
        quiz=c.post('/api/v1/quizzes',json={'title':'Check','course_id':course['id'],'questions':[{'kind':'single','prompt':'Choose A','options':['A','B'],'correct_indices':[0]}]}).json()
        c.post('/api/v1/quizzes/'+quiz['id']+'/attempts',json={'answers':[{'question_id':quiz['questions'][0]['id'],'selected':[0]}]})
        progress=c.get('/api/v1/courses').json()[0]
        assert progress['note_count']==1
        assert progress['due_count']==1
        assert progress['answered_count']==1 and progress['correct_count']==1
        c.post('/api/v1/flashcards/'+card['id']+'/review',json={'rating':'good'})
        assert c.get('/api/v1/courses').json()[0]['due_count']==0
        activity=c.get('/api/v1/dashboard').json()['activities']
        assert any(row['kind']=='review' for row in activity)


def test_security_headers_and_sanitized_rotating_diagnostics(tmp_path):
    from fastapi import APIRouter
    app=create_app(tmp_path)
    route=APIRouter()
    @route.get('/api/v1/test-error')
    def test_error():raise ValueError('PRIVATE_COURSE_SECRET')
    app.router.routes[0:0]=route.routes
    with TestClient(app,base_url='http://localhost',raise_server_exceptions=False) as c:
        login(c)
        health=c.get('/api/v1/health')
        assert "script-src 'self'" in health.headers['content-security-policy']
        assert health.headers['x-content-type-options']=='nosniff'
        error=c.get('/api/v1/test-error')
        assert error.status_code==500
        assert 'PRIVATE_COURSE_SECRET' not in error.text
    logs=(tmp_path/'logs'/'workspace.log').read_text()
    assert 'ValueError' in logs and 'PRIVATE_COURSE_SECRET' not in logs
