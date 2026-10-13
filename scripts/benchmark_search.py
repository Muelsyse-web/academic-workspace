#!/usr/bin/env python3
"""Measure search-only latency for 10,000 coherent synthetic indexed chunks.

TMPDIR="$PWD/.cache/tmp" .venv/bin/python scripts/benchmark_search.py
This directly seeds the production schema and FTS index. It does not benchmark
import/parsing, embedding, model inference, HTTP transport, or browser rendering.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import resource
import sqlite3
import statistics
import sys
import tempfile
import time
import traceback

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / 'backend'))
from workspace.db import Database, now
from workspace.search import index_text, search

TOPICS = [
    'Gradient descent 梯度下降 minimizes a differentiable objective using its gradient. The update subtracts learning rate times gradient.',
    'Conditional probability 条件概率 is P(A given B) = P(A and B) / P(B). For 0.2 and 0.5 the result is 0.4.',
    'An eigenvector 特征向量 satisfies Av = lambda v. For the diagonal matrix with entries 2 and 3, vector (1, 0) has eigenvalue 2.',
    'The derivative 导数 of x squared is twice x. At x = 3 its value is 6, describing the local rate of change.',
    'A graph 图 contains vertices and edges. A path follows connected edges between vertices; breadth first traversal uses a queue.',
]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_identity():
    files = sorted((PROJECT / 'backend/workspace').glob('*.sql')) + sorted((PROJECT / 'backend/workspace/migrations').glob('*.sql'))
    files += [PROJECT / 'backend/workspace/search.py', PROJECT / 'backend/workspace/db.py']
    return {str(p.relative_to(PROJECT)): digest(p) for p in files}


def percentile(values, quantile):
    """Linear interpolation between adjacent sorted samples (inclusive)."""
    values = sorted(values)
    position = (len(values) - 1) * quantile
    lower, upper = math.floor(position), math.ceil(position)
    return values[lower] + (values[upper] - values[lower]) * (position - lower)


def summary(values):
    return {'calls': len(values), 'p50_ms': round(statistics.median(values), 3), 'p95_ms': round(percentile(values, .95), 3), 'min_ms': round(min(values), 3), 'max_ms': round(max(values), 3)}


def seed(db):
    originals = db.root / 'originals'
    originals.mkdir()
    timestamp = now()
    with db.connect() as con:
        for index in range(3):
            con.execute('INSERT INTO courses(id,name,created_at) VALUES (?,?,?)', (f'course-{index}', f'Synthetic course {index}', timestamp))
        for document in range(200):
            doc_id, version = f'doc-{document:05d}', f'version-{document:05d}'
            lines = [f'Synthetic document {document}, exercise {unit + 1}: {TOPICS[unit % len(TOPICS)]}' for unit in range(50)]
            payload = ('\n'.join(lines) + '\n').encode()
            checksum = hashlib.sha256(payload).hexdigest()
            (originals / checksum).write_bytes(payload)
            kind = 'txt' if document % 2 == 0 else 'md'
            tag = 'foundation' if document % 2 == 0 else 'practice'
            filename = doc_id + '.' + kind
            con.execute('INSERT INTO blobs VALUES (?,?,?,?)', (checksum, len(payload), kind, timestamp))
            con.execute("INSERT INTO documents(id,blob_hash,title,filename,kind,status,active_version,tags,created_at,relative_path) VALUES (?,?,?,?,?,'ready',?,?,?,?)", (doc_id, checksum, f'Synthetic lessons {document}', filename, kind, version, json.dumps([tag]), timestamp, filename))
            con.execute('INSERT INTO document_courses VALUES (?,?)', (doc_id, f'course-{document % 3}'))
            con.execute('INSERT INTO document_versions VALUES (?,?,?,?)', (version, doc_id, timestamp, 'benchmark-synthetic-lines-v1'))
            for ordinal, text in enumerate(lines):
                unit, chunk = f'{doc_id}-unit-{ordinal}', f'{doc_id}-chunk-{ordinal}'
                con.execute('INSERT INTO source_units VALUES (?,?,?,?,?,?)', (unit, version, 'line', ordinal + 1, f'Synthetic exercise {ordinal + 1}', text))
                con.execute('INSERT INTO chunks VALUES (?,?,?,?,?,?)', (chunk, unit, version, doc_id, text, ordinal))
                con.execute('INSERT INTO chunks_fts VALUES (?,?)', (chunk, index_text(text)))
        assert con.execute('PRAGMA foreign_key_check').fetchall() == []
    for blob in db.all('SELECT hash,size FROM blobs'):
        path = originals / blob['hash']
        assert digest(path) == blob['hash'] and path.stat().st_size == blob['size']
    assert db.one('SELECT count(*) n FROM chunks')['n'] == 10000
    assert db.one('SELECT count(*) n FROM chunks_fts')['n'] == 10000


def benchmark(db, report):
    cases = [
        {'name': 'english_gradient', 'params': {'q': 'gradient'}, 'expected_total': 2000, 'candidate_chunks': 10000},
        {'name': 'english_probability', 'params': {'q': 'probability'}, 'expected_total': 2000, 'candidate_chunks': 10000},
        {'name': 'han_single_character', 'params': {'q': '概'}, 'expected_total': 2000, 'candidate_chunks': 10000},
        {'name': 'han_spaced_terms', 'params': {'q': '条件 概率'}, 'expected_total': 2000, 'candidate_chunks': 10000},
        {'name': 'course_kind_tag_scope', 'params': {'q': 'gradient', 'course_id': 'course-0', 'kind': 'txt', 'tag': 'foundation'}, 'expected_total': 340, 'candidate_chunks': 1700},
        {'name': 'document_scope', 'params': {'q': 'probability', 'document_id': 'doc-00017'}, 'expected_total': 10, 'candidate_chunks': 50},
    ]
    samples = []
    # Exactly 30 measured calls, round-robin: first samples include first-use cost;
    # subsequent samples reuse OS caches. No warm-up calls are excluded.
    for iteration in range(5):
        for case in cases:
            start = time.perf_counter_ns()
            result = search(db, **case['params'], limit=20)
            elapsed = (time.perf_counter_ns() - start) / 1_000_000
            assert result['total'] == case['expected_total'], (case['name'], result['total'])
            assert len(result['hits']) == min(20, case['expected_total'])
            for hit in result['hits']:
                doc_number = int(hit['document_id'].split('-')[1])
                if 'course_id' in case['params']:
                    assert doc_number % 3 == 0 and doc_number % 2 == 0 and hit['kind'] == 'txt'
                if 'document_id' in case['params']:
                    assert hit['document_id'] == case['params']['document_id']
                assert hit['version_id'] == f'version-{doc_number:05d}' and hit['locator_type'] == 'line'
                assert 1 <= hit['locator'] <= 50
            samples.append({'case': case['name'], 'iteration': iteration + 1, 'elapsed_ms': elapsed, 'total_hits': result['total'], 'returned_hits': len(result['hits'])})
    report['cases'] = [{**case, **summary([row['elapsed_ms'] for row in samples if row['case'] == case['name']])} for case in cases]
    report['overall'] = summary([row['elapsed_ms'] for row in samples])
    report['samples'] = samples
    report['checks'] = {'expected_totals': True, 'scope_filters': True, 'source_metadata': True, 'originals_sha256_and_sizes': True, 'foreign_keys': True, 'fts_rows_equal_chunks': True}


def main():
    (PROJECT / '.cache/tmp').mkdir(parents=True, exist_ok=True)
    os.environ['TMPDIR'] = str(PROJECT / '.cache/tmp')
    tempfile.tempdir = os.environ['TMPDIR']
    parent = PROJECT / '.cache/system-verification'
    parent.mkdir(parents=True, exist_ok=True)
    root = Path(tempfile.mkdtemp(prefix='search-', dir=parent))
    directory = PROJECT / 'docs/verification'
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / ('search-benchmark-' + root.name.removeprefix('search-') + '.json')
    report = {'scope': 'Search-only: direct production search() over synthetic SQLite/FTS index; no import, model, embedding, HTTP, or UI benchmark', 'started_at': datetime.now(timezone.utc).isoformat(), 'environment': {'platform': platform.platform(), 'machine': platform.machine(), 'python': platform.python_version(), 'sqlite': sqlite3.sqlite_version, 'cpu_count': os.cpu_count()}, 'working_tree_tested': True, 'commit_claim': None, 'source_sha256_before': source_identity(), 'command': 'TMPDIR="$PWD/.cache/tmp" .venv/bin/python scripts/benchmark_search.py', 'artifact_root': str(root.relative_to(PROJECT)), 'scale': {'courses': 3, 'documents': 200, 'versions': 200, 'source_units': 10000, 'chunks': 10000, 'fts_rows': 10000, 'synthetic_originals': 200}, 'measurement': {'total_calls': 30, 'calls_per_case': 5, 'warmup_calls': 0, 'limit': 20, 'cache_state': 'Uncontrolled OS cache; fresh database just seeded, first-use cost included, subsequent repeats warm', 'quantiles': 'p50 median; p95 linear interpolation between sorted observations', 'threshold': None, 'threshold_note': 'Descriptive local measurements; no invented acceptance threshold', 'rss_scope': 'Peak RSS of entire benchmark process, including imports and seed, not search-only incremental RSS'}, 'passed': False}
    start = time.perf_counter()
    try:
        db = Database(root / 'data')
        db.initialize()
        before_seed = time.perf_counter()
        seed(db)
        report['seed_seconds'] = round(time.perf_counter() - before_seed, 4)
        benchmark(db, report)
        report['database_bytes'] = db.path.stat().st_size
        report['original_bytes'] = sum(p.stat().st_size for p in (db.root / 'originals').iterdir())
        report['passed'] = True
    except Exception as exc:
        report['error'] = f'{type(exc).__name__}: {exc}'
        report['traceback'] = traceback.format_exc()
    finally:
        rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        report['process_peak_rss_bytes'] = int(rss if sys.platform == 'darwin' else rss * 1024)
        report['source_sha256_after'] = source_identity()
        report['source_unchanged_during_run'] = report['source_sha256_before'] == report['source_sha256_after']
        report['duration_seconds'] = round(time.perf_counter() - start, 4)
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
        print(json.dumps({'passed': report['passed'], 'report': str(path.relative_to(PROJECT)), 'overall': report.get('overall'), 'process_peak_rss_bytes': report['process_peak_rss_bytes'], 'error': report.get('error')}, ensure_ascii=False))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
