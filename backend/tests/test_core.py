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
