"""Backup archives are validated before the live library is changed."""
import hashlib
import io
import json
import sqlite3
import threading
import zipfile
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from workspace.db import Database, now


def client_for(root, migrations=None):
    from workspace.backup import router
    db = Database(root, migrations=migrations)
    db.initialize()
    app = FastAPI()
    app.state.db = db
    app.state.sessions = {'old-session': {}}
    app.state.conversation_locks = {}
    app.include_router(router)
    return TestClient(app), db


def populate(db, name='Synthetic source'):
    content = b'Synthetic backup fixture, no personal documents.\n'
    sha = hashlib.sha256(content).hexdigest()
    (db.root/'originals').mkdir(exist_ok=True)
    (db.root/'originals'/sha).write_bytes(content)
    with db.connect() as con:
        con.execute('INSERT INTO courses(id,name,created_at) VALUES (?,?,?)', ('course', name, now()))
        con.execute('INSERT INTO blobs VALUES (?,?,?,?)', (sha, len(content), 'txt', now()))
        con.execute("INSERT INTO documents(id,blob_hash,title,filename,kind,status,created_at) VALUES (?,?,?,?,?,'ready',?)", ('doc',sha,name,'fixture.txt','txt',now()))
        con.execute('INSERT INTO document_versions VALUES (?,?,?,?)', ('version','doc',now(),'fixture'))
        con.execute("UPDATE documents SET active_version='version' WHERE id='doc'")
        con.execute("INSERT INTO source_units VALUES ('unit','version','line',1,'','Synthetic text')")
        con.execute("INSERT INTO chunks VALUES ('chunk','unit','version','doc','Synthetic text',0)")
        con.execute("INSERT INTO chunks_fts VALUES ('chunk','Synthetic text')")
        con.execute("INSERT INTO notes(id,title,body,created_at,updated_at) VALUES ('note','Note','Retained note',?,?)", (now(),now()))
        con.execute("INSERT INTO agent_tokens VALUES ('token','Agent','secret-hash-must-not-survive','read',?)", (now(),))
    (db.root/'provider-secret.json').write_text('{"api_key":"secret-do-not-export"}')
    return sha


def rewrite_archive(payload, changes=None, db_edit=None, tmp_path=None):
    with zipfile.ZipFile(io.BytesIO(payload)) as z:
        entries = {n: z.read(n) for n in z.namelist()}
    manifest = json.loads(entries['manifest.json'])
    if db_edit:
        path = tmp_path/'edit.sqlite3'
        path.write_bytes(entries['workspace.sqlite3'])
        with sqlite3.connect(path) as con:
            db_edit(con)
        entries['workspace.sqlite3'] = path.read_bytes()
        manifest['files']['workspace.sqlite3'] = {'sha256':hashlib.sha256(entries['workspace.sqlite3']).hexdigest(),'size':len(entries['workspace.sqlite3'])}
        entries['manifest.json'] = json.dumps(manifest).encode()
    if changes:
        changes(entries)
    result = io.BytesIO()
    with zipfile.ZipFile(result, 'w') as z:
        for name, data in entries.items():
            z.writestr(name, data)
    return result.getvalue()


def restore(client, payload, confirm='RESTORE'):
    return client.post('/api/v1/restore',files={'archive':('backup.zip',payload,'application/zip')},data={'confirm':confirm})


def test_backup_contains_verified_originals_and_scrubbed_snapshot(tmp_path):
    c, db = client_for(tmp_path/'source')
    sha = populate(db)
    r = c.get('/api/v1/backup')
    assert r.status_code == 200, r.text
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        assert set(z.namelist()) == {'manifest.json','workspace.sqlite3','originals/'+sha}
        manifest = json.loads(z.read('manifest.json'))
        assert manifest['format_version'] == 1
        for name, entry in manifest['files'].items():
            data = z.read(name)
            assert hashlib.sha256(data).hexdigest() == entry['sha256']
            assert len(data) == entry['size']
        snapshot = z.read('workspace.sqlite3')
        assert b'secret-hash-must-not-survive' not in snapshot
        assert b'secret-do-not-export' not in r.content
    assert db.one('SELECT count(*) n FROM agent_tokens')['n'] == 1
    assert not list((db.root/'backup-tmp').iterdir())


def test_restore_roundtrip_existing_recovery_and_restart(tmp_path):
    source, source_db = client_for(tmp_path/'source')
    sha = populate(source_db)
    payload = source.get('/api/v1/backup').content
    target, db = client_for(tmp_path/'target')
    populate(db, 'Old data')
    result = restore(target, payload)
    assert result.status_code == 200, result.text
    assert db.one('SELECT name FROM courses')['name'] == 'Synthetic source'
    assert db.one('SELECT body FROM notes')['body'] == 'Retained note'
    assert db.one('SELECT count(*) n FROM agent_tokens')['n'] == 0
    assert target.app.state.sessions == {}
    recovery = db.root / result.json()['recovery_path']
    with sqlite3.connect(recovery/'workspace.sqlite3') as con:
        assert con.execute('SELECT name FROM courses').fetchone()[0] == 'Old data'
    assert (recovery/'originals'/sha).read_bytes() == (db.root/'originals'/sha).read_bytes()
    reopened = Database(db.root)
    reopened.initialize()
    assert reopened.one('SELECT name FROM courses')['name'] == 'Synthetic source'
    fresh, fresh_db = client_for(tmp_path/'fresh')
    assert restore(fresh,payload).status_code == 200
    assert fresh_db.one('SELECT count(*) n FROM chunks')['n'] == 1


@pytest.mark.parametrize('mode',['checksum','traversal','missing','unknown','duplicate','symlink','bad_zip','schema','newer','foreign_key'])
@pytest.mark.filterwarnings("ignore:Duplicate name:UserWarning")
def test_invalid_archives_leave_current_library_unchanged(tmp_path, mode):
    c, db = client_for(tmp_path/'source')
    sha = populate(db)
    payload = c.get('/api/v1/backup').content
    if mode == 'checksum':
        payload = rewrite_archive(payload, lambda e: e.__setitem__('originals/'+sha,b'corrupt'))
    elif mode == 'traversal':
        payload = rewrite_archive(payload, lambda e: e.__setitem__('../escaped.txt',b'bad'))
    elif mode == 'missing':
        payload = rewrite_archive(payload, lambda e: e.pop('originals/'+sha))
    elif mode == 'unknown':
        payload = rewrite_archive(payload, lambda e: e.__setitem__('provider-secret.json',b'bad'))
    elif mode in ('duplicate','symlink'):
        stream = io.BytesIO(payload)
        with zipfile.ZipFile(stream,'a') as z:
            info = zipfile.ZipInfo('manifest.json' if mode == 'duplicate' else 'link')
            if mode == 'symlink':
                info.create_system = 3
                info.external_attr = 0o120777 << 16
            z.writestr(info,b'bad')
        payload = stream.getvalue()
    elif mode == 'bad_zip':
        payload = b'bad'
    elif mode == 'schema':
        payload = rewrite_archive(payload,db_edit=lambda con: con.execute('CREATE TABLE impostor(secret TEXT)'),tmp_path=tmp_path)
    elif mode == 'newer':
        payload = rewrite_archive(payload,db_edit=lambda con: con.execute('PRAGMA user_version=999'),tmp_path=tmp_path)
    elif mode == 'foreign_key':
        payload = rewrite_archive(payload,db_edit=lambda con: con.execute("INSERT INTO document_courses VALUES ('missing','course')"),tmp_path=tmp_path)
    result = restore(c,payload)
    assert result.status_code == 422, result.text
    assert db.one('SELECT name FROM courses')['name'] == 'Synthetic source'
    assert db.one('SELECT count(*) n FROM agent_tokens')['n'] == 1
    assert (db.root/'originals'/sha).is_file()
    assert c.app.state.sessions
    assert not (db.root.parent/'escaped.txt').exists()


@pytest.mark.parametrize('active',['job','embedding','conversation'])
def test_restore_refuses_live_work(tmp_path, active):
    c, db = client_for(tmp_path/'source')
    populate(db)
    payload = c.get('/api/v1/backup').content
    if active == 'conversation':
        lock = threading.Lock()
        lock.acquire()
        c.app.state.conversation_locks['conversation'] = lock
    else:
        with db.connect() as con:
            if active == 'job':
                con.execute("INSERT INTO jobs(id,document_id,status,created_at,updated_at) VALUES ('job','doc','processing',?,?)",(now(),now()))
            else:
                con.execute("INSERT INTO embedding_runs(id,status,provider,model,created_at) VALUES ('run','queued','local','model',?)",(now(),))
    assert restore(c,payload).status_code == 409
    assert db.one('SELECT count(*) n FROM agent_tokens')['n'] == 1


def test_confirmation_required_and_expansion_bounded(tmp_path, monkeypatch):
    from workspace import backup
    c, db = client_for(tmp_path/'source')
    populate(db)
    payload = c.get('/api/v1/backup').content
    assert restore(c,payload,confirm='yes').status_code == 422
    monkeypatch.setattr(backup,'MAX_EXPANDED_BYTES',10)
    assert restore(c,payload).status_code == 422


def test_install_failure_rolls_back_database_and_originals(tmp_path, monkeypatch):
    c, db = client_for(tmp_path/'source')
    sha = populate(db)
    payload = c.get('/api/v1/backup').content
    with db.connect() as con:
        con.execute("UPDATE courses SET name='Current data'")
    original_replace = Path.replace
    def failing_replace(path, target):
        if path.name == 'originals' and 'restore-' in str(path) and Path(target) == db.root/'originals':
            raise OSError('Synthetic final install failure')
        return original_replace(path, target)
    monkeypatch.setattr(Path,'replace',failing_replace)
    result = restore(c,payload)
    assert result.status_code == 500
    assert db.one('SELECT name FROM courses')['name'] == 'Current data'
    assert (db.root/'originals'/sha).exists()
    assert c.app.state.sessions


def test_restore_genuine_older_schema_migrates_using_registered_migrations(tmp_path):
    latest = Database(tmp_path/'latest-schema')
    migrations = {key:value for key,value in latest.migrations.items() if key <= 2}
    older, old_db = client_for(tmp_path/'older', migrations=migrations)
    populate(old_db)
    payload = older.get('/api/v1/backup').content
    target, db = client_for(tmp_path/'target')
    result = restore(target,payload)
    assert result.status_code == 200, result.text
    assert db.one('PRAGMA user_version')['user_version'] == max(latest.migrations)
    assert db.one('SELECT name FROM courses')['name'] == 'Synthetic source'
    assert db.one('SELECT body FROM notes')['body'] == 'Retained note'


def test_rejects_malicious_trigger_without_executing_it(tmp_path):
    c, db = client_for(tmp_path/'source')
    populate(db)
    payload = c.get('/api/v1/backup').content
    def poison(con):
        con.execute('CREATE TRIGGER hostile AFTER DELETE ON agent_tokens BEGIN DELETE FROM courses; END;')
    payload = rewrite_archive(payload, db_edit=poison,tmp_path=tmp_path)
    response = restore(c,payload)
    assert response.status_code == 422
    assert 'schema' in response.json()['detail']
    assert db.one('SELECT count(*) n FROM courses')['n'] == 1


def test_missing_or_modified_original_prevents_incomplete_backup(tmp_path):
    c, db = client_for(tmp_path/'source')
    sha = populate(db)
    (db.root/'originals'/sha).write_bytes(b'corrupt')
    assert c.get('/api/v1/backup').status_code == 409
    (db.root/'originals'/sha).unlink()
    assert c.get('/api/v1/backup').status_code == 409
    assert not list((db.root/'backup-tmp').iterdir())


def test_backup_rejects_original_directory_symlink(tmp_path):
    c, db = client_for(tmp_path/'source')
    populate(db)
    (db.root/'originals').rename(tmp_path/'elsewhere')
    (db.root/'originals').symlink_to(tmp_path/'elsewhere', target_is_directory=True)
    assert c.get('/api/v1/backup').status_code == 409


def test_secondary_rollback_failure_keeps_recoverable_database(tmp_path, monkeypatch):
    c, db = client_for(tmp_path/'source')
    populate(db)
    payload = c.get('/api/v1/backup').content
    original_replace = Path.replace
    def fail_install_and_rollback(path, target):
        if path.name == 'originals' and Path(target) == db.root/'originals':
            raise OSError('Synthetic unavailable originals directory')
        return original_replace(path,target)
    monkeypatch.setattr(Path,'replace',fail_install_and_rollback)
    result = restore(c,payload)
    assert result.status_code == 500
    assert db.one('SELECT count(*) n FROM agent_tokens')['n'] == 1
    assert 'manual recovery' in result.json()['detail'].lower()
    assert list((db.root/'backup-tmp').glob('restore-*'))
    assert list((db.root/'recovery').glob('*/originals/*'))


def test_restored_active_jobs_are_interrupted_without_resuming_services(tmp_path):
    source, source_db = client_for(tmp_path/'source')
    populate(source_db)
    with source_db.connect() as con:
        con.execute("UPDATE documents SET status='processing'")
        con.execute("INSERT INTO jobs(id,document_id,status,created_at,updated_at) VALUES ('job','doc','processing',?,?)",(now(),now()))
        con.execute("INSERT INTO embedding_runs(id,status,provider,model,created_at) VALUES ('run','queued','local','model',?)",(now(),))
    payload = source.get('/api/v1/backup').content
    target, db = client_for(tmp_path/'target')
    result = restore(target,payload)
    assert result.status_code == 200, result.text
    assert result.json()['interrupted_jobs'] == 2
    assert db.one('SELECT status,error FROM jobs') == {'status':'failed','error':'Interrupted by restore; retry indexing'}
    assert db.one('SELECT status FROM embedding_runs')['status'] == 'failed'
    assert db.one('SELECT active_version,status FROM documents') == {'active_version':'version','status':'failed'}
    assert source_db.one('SELECT status FROM jobs')['status'] == 'processing'


@pytest.mark.parametrize('failure',[None,'originals','secret'])
def test_restore_provider_credentials_are_recovery_only_and_rollback_safe(tmp_path, monkeypatch, failure):
    c, db = client_for(tmp_path/'source')
    populate(db)
    secret = db.root/'provider-secret.json'
    secret.chmod(0o600)
    before = secret.read_bytes()
    payload = c.get('/api/v1/backup').content
    original_replace = Path.replace
    def fail_install(path, target):
        if failure == 'originals' and path.name == 'originals' and 'restore-' in str(path) and Path(target) == db.root/'originals':
            raise OSError('Synthetic originals installation failure')
        if failure == 'secret' and path == secret:
            raise OSError('Synthetic credential move failure')
        return original_replace(path,target)
    monkeypatch.setattr(Path,'replace',fail_install)
    result = restore(c,payload)
    if failure:
        assert result.status_code == 500
        assert secret.read_bytes() == before
        assert secret.stat().st_mode & 0o777 == 0o600
        assert db.one('SELECT count(*) n FROM agent_tokens')['n'] == 1
    else:
        assert result.status_code == 200, result.text
        assert not secret.exists()
        recovery_secret = db.root/result.json()['recovery_path']/'provider-secret.json'
        assert recovery_secret.read_bytes() == before
        assert recovery_secret.stat().st_mode & 0o777 == 0o600
        from workspace.configuration import router as configuration_router
        c.app.include_router(configuration_router)
        assert c.get('/api/v1/settings/provider').json()['has_api_key'] is False
        with zipfile.ZipFile(io.BytesIO(c.get('/api/v1/backup').content)) as archive:
            assert 'provider-secret.json' not in archive.namelist()


def test_backup_budget_includes_manifest_so_generated_archives_can_restore(tmp_path, monkeypatch):
    from workspace import backup
    c, db = client_for(tmp_path/'source')
    populate(db)
    initial = c.get('/api/v1/backup')
    with zipfile.ZipFile(io.BytesIO(initial.content)) as archive:
        file_bytes = sum(info.file_size for info in archive.infolist() if info.filename != 'manifest.json')
    monkeypatch.setattr(backup, 'MAX_EXPANDED_BYTES', file_bytes + 1)
    assert c.get('/api/v1/backup').status_code == 413
    monkeypatch.setattr(backup, 'MAX_EXPANDED_BYTES', 4 * 1024**3)
    monkeypatch.setattr(backup, 'MAX_MANIFEST_BYTES', 1)
    assert c.get('/api/v1/backup').status_code == 413
