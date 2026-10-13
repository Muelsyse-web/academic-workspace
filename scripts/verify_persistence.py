#!/usr/bin/env python3
"""Verify synthetic data across actual uvicorn exits and backup/restore.

Run from this repository: TMPDIR="$PWD/.cache/tmp" .venv/bin/python scripts/verify_persistence.py
No TestClient, model service, private input, or external server is used.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
from pathlib import Path
import platform
import signal
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import traceback
from datetime import datetime, timezone
from zipfile import ZipFile

import httpx

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / 'scripts'))
from generate_fixtures import generate


def sha(data):
    return hashlib.sha256(data).hexdigest()


def code_identity():
    files = sorted((PROJECT / 'backend/workspace').rglob('*.py')) + sorted((PROJECT / 'backend/workspace').rglob('*.sql'))
    return {str(p.relative_to(PROJECT)): sha(p.read_bytes()) for p in files}


def database_snapshot(path):
    """Digest every logical table except deliberately scrubbed token credentials."""
    with sqlite3.connect(f'{path.as_uri()}?mode=ro', uri=True) as con:
        assert con.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        assert con.execute('PRAGMA foreign_key_check').fetchall() == []
        names = [row[0] for row in con.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        result = {}
        for name in names:
            if name == 'agent_tokens' or name.startswith(('sqlite_', 'chunks_fts_', 'notes_fts_')):
                continue
            rows = con.execute('SELECT * FROM "' + name.replace('"', '""') + '"').fetchall()
            encoded = sorted(json.dumps(row, ensure_ascii=False, sort_keys=True) for row in rows)
            result[name] = {'count': len(rows), 'sha256': sha('\n'.join(encoded).encode())}
        return result


class Server:
    def __init__(self, root, report):
        self.root, self.report = root, report
        self.proc = self.client = self.log = None

    def start(self):
        with socket.socket() as probe:
            probe.bind(('127.0.0.1', 0))
            port = probe.getsockname()[1]
        base = f'http://127.0.0.1:{port}'
        command = [str(PROJECT / '.venv/bin/python'), '-m', 'uvicorn', 'workspace.app:create_app', '--factory', '--app-dir', 'backend', '--host', '127.0.0.1', '--port', str(port), '--no-access-log']
        entry = {'command': command, 'data_root': str((self.root / 'data').relative_to(PROJECT)), 'bind': base}
        self.report['processes'].append(entry)
        self.log = (self.root / f'server-{len(self.report["processes"])}.log').open('wb')
        env = {**os.environ, 'WORKSPACE_DATA_DIR': str(self.root / 'data'), 'TMPDIR': str(PROJECT / '.cache/tmp'), 'PYTHONDONTWRITEBYTECODE': '1'}
        self.proc = subprocess.Popen(command, cwd=PROJECT, env=env, stdout=self.log, stderr=subprocess.STDOUT)
        entry['pid'] = self.proc.pid
        self.client = httpx.Client(base_url=base, headers={'Host': f'localhost:{port}', 'Origin': f'http://localhost:{port}'}, timeout=30, trust_env=False)
        started = time.perf_counter()
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if self.proc.poll() is not None:
                raise AssertionError(f'Owned server exited before health: {self.proc.returncode}; inspect project log')
            try:
                if self.client.get('/api/v1/health').status_code == 200:
                    break
            except httpx.TransportError:
                pass
            time.sleep(.1)
        else:
            raise AssertionError('Owned server health deadline exceeded')
        entry['health_seconds'] = round(time.perf_counter() - started, 4)
        self.session()

    def session(self):
        response = self.request('POST', '/session')
        self.client.headers['x-csrf-token'] = response.json()['csrf_token']

    def request(self, method, path, expected=200, **kwargs):
        response = self.client.request(method, '/api/v1' + path, **kwargs)
        assert response.status_code == expected, f'{method} {path}: expected {expected}, received {response.status_code}: {response.text[:400]}'
        return response

    def json(self, method, path, expected=200, **kwargs):
        return self.request(method, path, expected, **kwargs).json()

    def stop(self):
        if self.client:
            self.client.close()
            self.client = None
        if self.proc:
            entry = self.report['processes'][-1]
            started = time.perf_counter()
            if self.proc.poll() is None:
                self.proc.send_signal(signal.SIGTERM)
                try:
                    self.proc.wait(timeout=20)
                except subprocess.TimeoutExpired:
                    self.proc.kill()
                    self.proc.wait(timeout=10)
                    entry['forced_kill'] = True
            entry['exit_code'] = self.proc.returncode
            entry['exit_seconds'] = round(time.perf_counter() - started, 4)
            self.proc = None
        if self.log:
            self.log.close()
            self.log = None


def run(server, root, report):
    generate(root / 'fixtures')
    fixtures = [root / 'fixtures' / f'synthetic-foundations.{kind}' for kind in ('pdf', 'pptx', 'docx')]
    expected_bytes = {p.name: p.read_bytes() for p in fixtures}
    server.start()
    course = server.json('POST', '/courses', 201, json={'name': 'Synthetic persistence course', 'code': 'VERIFY', 'semester': '2026'})
    imported = server.json('POST', '/documents', 202, data={'course_id': course['id']}, files=[('files', (name, data, 'application/octet-stream')) for name, data in expected_bytes.items()])
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        jobs = server.json('GET', '/jobs')
        if all(job['status'] not in ('queued', 'processing') for job in jobs):
            break
        time.sleep(.1)
    assert len(jobs) == 3 and all(job['status'] == 'done' for job in jobs), jobs
    documents = server.json('GET', '/documents')
    assert len(documents) == 3
    sources, units_by_doc = [], {}
    for doc in documents:
        units = server.json('GET', f'/documents/{doc["id"]}/units')
        units_by_doc[doc['id']] = units
        expected_type, expected_count = {'pdf': ('page', 3), 'pptx': ('slide', 3), 'docx': ('paragraph', 13)}[doc['kind']]
        assert len(units) == expected_count, (doc['kind'], len(units))
        assert [u['locator'] for u in units] == list(range(1, expected_count + 1))
        assert all(u['locator_type'] == expected_type for u in units)
        unit = next(u for u in units if 'Gradient descent' in u['text'])
        sources.append({'document_id': doc['id'], 'version_id': doc['active_version'], 'locator_type': unit['locator_type'], 'locator': unit['locator'], 'quote': 'Gradient descent'})
    note = server.json('POST', '/notes', 201, json={'title': 'Synthetic evidence note', 'body': 'Retain actual source positions.', 'course_id': course['id'], 'sources': sources})
    linked = server.json('POST', '/notes', 201, json={'title': 'Synthetic linked note', 'body': '[[Synthetic evidence note]]', 'course_id': course['id']})
    card = server.json('POST', '/flashcards', 201, json={'front': 'What method minimizes an objective?', 'back': 'Gradient descent', 'course_id': course['id'], 'sources': sources})
    server.json('POST', f'/flashcards/{card["id"]}/review', json={'rating': 'good', 'idempotency_key': 'verification-review'})
    quiz = server.json('POST', '/quizzes', 201, json={'title': 'Synthetic verification quiz', 'course_id': course['id'], 'questions': [{'kind': 'single', 'prompt': 'Choose the optimization method.', 'options': ['Gradient descent', 'A distractor'], 'correct_indices': [0], 'sources': sources}]})
    attempt = server.json('POST', f'/quizzes/{quiz["id"]}/attempts', 201, json={'answers': [{'question_id': quiz['questions'][0]['id'], 'selected': [0]}], 'idempotency_key': 'verification-attempt'})
    assert attempt['score'] == 1
    conv = server.json('POST', '/conversations', 201, json={'title': 'Synthetic no-evidence history', 'course_id': course['id']})
    answer = server.json('POST', f'/conversations/{conv["id"]}/messages', json={'content': 'zxqvplmnoevidencezz'})
    assert answer['status'] == 'evidence_insufficient' and answer['sources'] == []
    token = server.json('POST', '/agent-tokens', 201, json={'name': 'Synthetic verification agent', 'scope': 'read'})
    token_value = token.pop('token')
    report['ids'] = {'course': course['id'], 'documents': [d['id'] for d in documents], 'notes': [note['id'], linked['id']], 'card': card['id'], 'quiz': quiz['id'], 'attempt': attempt['id'], 'conversation': conv['id'], 'agent_token_id': token['id']}
    report['source_positions'] = [{**source, 'kind': next(d['kind'] for d in documents if d['id'] == source['document_id'])} for source in sources]
    endpoints = ['/documents', '/notes/' + note['id'], '/notes/' + linked['id'], '/flashcards/' + card['id'], '/reviews', '/quizzes/' + quiz['id'], '/attempts', '/conversations/' + conv['id']]
    api_baseline = {path: server.json('GET', path) for path in endpoints}
    baseline = database_snapshot(root / 'data/workspace.sqlite3')
    report['logical_tables'] = baseline
    report['counts'] = {table: data['count'] for table, data in baseline.items()}

    def verify(phase):
        assert database_snapshot(root / 'data/workspace.sqlite3') == baseline, f'{phase}: logical table content changed'
        for path, expected in api_baseline.items():
            assert server.json('GET', path) == expected, f'{phase}: API state changed for {path}'
        hashes = []
        for doc in documents:
            assert server.json('GET', f'/documents/{doc["id"]}/units') == units_by_doc[doc['id']]
            actual = server.request('GET', f'/documents/{doc["id"]}/original').content
            expected = expected_bytes[doc['filename']]
            assert actual == expected and sha(actual) == doc['blob_hash']
            assert sha((root / 'data/originals' / doc['blob_hash']).read_bytes()) == sha(expected)
            hashes.append({'kind': doc['kind'], 'sha256': sha(actual), 'bytes': len(actual), 'http_and_disk_match': True})
        hit = server.json('GET', '/search', params={'q': 'Gradient descent', 'course_id': course['id']})
        assert {h['document_id'] for h in hit['hits']} == {d['id'] for d in documents}
        report['checks'][phase] = {'passed': True, 'all_logical_tables_equal': True, 'api_snapshots_equal': True, 'source_units_equal': True, 'search_matches_all_three_documents': True, 'originals': hashes}

    verify('before_restart')
    server.stop()
    assert report['processes'][-1]['exit_code'] in (0, -signal.SIGTERM)
    server.start()
    verify('after_process_restart')
    assert [row['id'] for row in server.json('GET', '/agent-tokens')] == [token['id']]
    archive = server.request('GET', '/backup').content
    (root / 'backup.zip').write_bytes(archive)
    with ZipFile(io.BytesIO(archive)) as z:
        manifest = json.loads(z.read('manifest.json'))
        for name, meta in manifest['files'].items():
            assert sha(z.read(name)) == meta['sha256'] and len(z.read(name)) == meta['size']
        snapshot = root / 'backup-snapshot.sqlite3'
        snapshot.write_bytes(z.read('workspace.sqlite3'))
    with sqlite3.connect(snapshot) as con:
        assert con.execute('SELECT count(*) FROM agent_tokens').fetchone()[0] == 0
    extra_course = server.json('POST', '/courses', 201, json={'name': 'Extra post-backup course'})
    extra_note = server.json('POST', '/notes', 201, json={'title': 'Extra post-backup note', 'course_id': extra_course['id']})
    assert len(server.json('GET', '/courses')) == 2
    restored = server.json('POST', '/restore', data={'confirm': 'RESTORE'}, files={'archive': ('backup.zip', archive, 'application/zip')})
    server.request('GET', '/courses', expected=401)
    server.session()
    verify('after_restore')
    assert server.json('GET', '/agent-tokens') == []
    server.request('GET', '/courses', expected=401, headers={'Authorization': 'Bearer ' + token_value})
    assert [row['id'] for row in server.json('GET', '/courses')] == [course['id']]
    server.request('GET', '/notes/' + extra_note['id'], expected=404)
    recovery = root / 'data' / restored['recovery_path']
    assert recovery.resolve().is_relative_to(root.resolve())
    with sqlite3.connect(f'{(recovery / "workspace.sqlite3").as_uri()}?mode=ro', uri=True) as con:
        assert con.execute('SELECT count(*) FROM courses WHERE id=?', (extra_course['id'],)).fetchone()[0] == 1
        assert con.execute('SELECT count(*) FROM notes WHERE id=?', (extra_note['id'],)).fetchone()[0] == 1
    report['restore'] = {'recovery_root': str(recovery.relative_to(PROJECT)), 'extra_state_removed': True, 'extra_state_in_recovery': True, 'sessions_invalidated': True, 'agent_tokens_scrubbed_from_backup_and_restore': True, 'old_agent_token_rejected': True, 'backup_sha256': sha(archive)}
    server.stop()
    assert report['processes'][-1]['exit_code'] in (0, -signal.SIGTERM)
    server.start()
    verify('after_restored_process_restart')
    assert server.json('GET', '/agent-tokens') == []


def main():
    (PROJECT / '.cache/tmp').mkdir(parents=True, exist_ok=True)
    os.environ['TMPDIR'] = str(PROJECT / '.cache/tmp')
    tempfile.tempdir = os.environ['TMPDIR']
    parent = PROJECT / '.cache/system-verification'
    parent.mkdir(parents=True, exist_ok=True)
    root = Path(tempfile.mkdtemp(prefix='process-', dir=parent))
    report_dir = PROJECT / 'docs/verification'
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / (root.name + '.json')
    report = {'scope': 'Actual loopback uvicorn process persistence and HTTP backup/restore; synthetic PDF/PPTX/DOCX only; no inference', 'started_at': datetime.now(timezone.utc).isoformat(), 'environment': {'python': platform.python_version(), 'platform': platform.platform(), 'sqlite': sqlite3.sqlite_version}, 'working_tree_tested': True, 'commit_claim': None, 'source_sha256_before': code_identity(), 'command': 'TMPDIR="$PWD/.cache/tmp" .venv/bin/python scripts/verify_persistence.py', 'artifact_root': str(root.relative_to(PROJECT)), 'processes': [], 'checks': {}, 'passed': False}
    server = Server(root, report)
    start = time.perf_counter()
    try:
        run(server, root, report)
        report['passed'] = True
    except Exception as exc:
        report['error'] = f'{type(exc).__name__}: {exc}'
        report['traceback'] = traceback.format_exc()
    finally:
        server.stop()
        report['source_sha256_after'] = code_identity()
        report['source_unchanged_during_run'] = report['source_sha256_before'] == report['source_sha256_after']
        report['duration_seconds'] = round(time.perf_counter() - start, 4)
        report['all_owned_servers_stopped'] = all('exit_code' in entry for entry in report['processes'])
        report['passed'] = report['passed'] and all(entry.get('exit_code') in (0, -signal.SIGTERM) and not entry.get('forced_kill') for entry in report['processes'])
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
        print(json.dumps({'passed': report['passed'], 'report': str(report_path.relative_to(PROJECT)), 'duration_seconds': report['duration_seconds'], 'error': report.get('error')}, ensure_ascii=False))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
