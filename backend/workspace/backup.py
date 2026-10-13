"""Versioned, bounded library backups and staged replacement restores.

Limits: 4 GiB expanded payload, 20,000 ZIP entries, 8 MiB manifest,
16 MiB ZIP central directory. Temporary files and recovery points stay under
Database.root. Provider credentials, caches, logs and Agent credentials are
never exported. Recovery folders are local snapshots, not downloadable ZIPs.
"""
from contextlib import closing
import hashlib
import json
from pathlib import Path
import re
import shutil
import sqlite3
import stat
import struct
import tempfile
from typing import Annotated
import zipfile

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from .db import Database, new_id, now

router = APIRouter(prefix='/api/v1')
MAX_EXPANDED_BYTES = 4 * 1024**3
MAX_ARCHIVE_BYTES = MAX_EXPANDED_BYTES + 32 * 1024**2
MAX_ENTRIES = 20_000
MAX_MANIFEST_BYTES = 8 * 1024**2
MAX_DIRECTORY_BYTES = 16 * 1024**2
BLOCK = 1024**2
HASH = re.compile(r'^[0-9a-f]{64}$')


class RollbackFailure(OSError):
    """Keep both staging and recovery data after a second filesystem failure."""


def _temporary(db, prefix):
    parent = db.root/'backup-tmp'
    parent.mkdir(exist_ok=True)
    return Path(tempfile.mkdtemp(prefix=prefix, dir=parent))


def _hash(path):
    checksum, size = hashlib.sha256(), 0
    with path.open('rb') as stream:
        while data := stream.read(BLOCK):
            checksum.update(data)
            size += len(data)
    return {'sha256': checksum.hexdigest(), 'size': size}


def _snapshot(db, path, scrub=True):
    with db.connect() as source, closing(sqlite3.connect(path)) as target:
        source.backup(target)
        if scrub:
            target.execute('PRAGMA secure_delete=ON')
            target.execute('DELETE FROM agent_tokens')
            target.commit()
            # Removes deleted rows from free pages, including historical hashes.
            target.execute('VACUUM')
        target.execute('PRAGMA journal_mode=DELETE')


def _blobs(con):
    result = {}
    for row in con.execute('SELECT hash,size FROM blobs'):
        checksum, size = row[0], row[1]
        if not isinstance(checksum, str) or not HASH.fullmatch(checksum) or not isinstance(size, int) or size < 0:
            raise ValueError('Invalid original metadata')
        result['originals/'+checksum] = {'sha256': checksum, 'size': size}
    return result


@router.get('/backup')
def backup(request: Request):
    db = request.app.state.db
    stage = _temporary(db, 'backup-')
    try:
        snapshot = stage/'workspace.sqlite3'
        with db.maintenance:
            if (db.root/'originals').is_symlink():
                raise HTTPException(409, 'Originals directory must be inside the library')
            _snapshot(db, snapshot)
            with closing(sqlite3.connect(snapshot)) as con:
                originals = _blobs(con)
                version = con.execute('PRAGMA user_version').fetchone()[0]
            files = {'workspace.sqlite3': _hash(snapshot)}
            files.update(originals)
            manifest = {'format':'academic-workspace','format_version':1,'schema_version':version,'created_at':now(),'files':files}
            manifest_bytes = json.dumps(manifest, ensure_ascii=False).encode('utf-8')
            if len(manifest_bytes) > MAX_MANIFEST_BYTES:
                raise HTTPException(413, 'Backup manifest exceeds 8 MiB limit')
            if len(files) + 1 > MAX_ENTRIES or sum(f['size'] for f in files.values()) + len(manifest_bytes) > MAX_EXPANDED_BYTES:
                raise HTTPException(413, 'Library exceeds backup limits: 4 GiB expanded or 20,000 entries')
            archive = stage/'library.zip'
            with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6, allowZip64=True) as z:
                z.write(snapshot, 'workspace.sqlite3')
                for name, expected in originals.items():
                    path = db.root/name
                    if path.is_symlink() or not path.is_file() or _hash(path) != expected:
                        raise HTTPException(409, 'An original is missing or corrupt; backup was not created')
                    z.write(path, name)
                z.writestr('manifest.json', manifest_bytes)
        return FileResponse(archive, media_type='application/zip', filename='academic-workspace-backup.zip', background=BackgroundTask(shutil.rmtree, stage, True))
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise


def _preflight_zip(path):
    """Bound directory allocation before ZipFile creates its in-memory index."""
    size = path.stat().st_size
    if size > MAX_ARCHIVE_BYTES:
        raise ValueError('Archive exceeds upload size limit')
    with path.open('rb') as stream:
        stream.seek(max(0, size - 65557))
        tail = stream.read()
        offset = tail.rfind(b'PK\x05\x06')
        if offset < 0 or len(tail) - offset < 22:
            raise ValueError('Invalid ZIP archive')
        end = struct.unpack('<4s4H2LH', tail[offset:offset+22])
        if end[1] or end[2] or end[3] != end[4] or len(tail)-offset != 22+end[7]:
            raise ValueError('Invalid or multi-disk ZIP archive')
        count, directory_size = end[4], end[5]
        if count == 65535 or directory_size == 0xffffffff or end[6] == 0xffffffff:
            absolute = max(0, size - 65557) + offset
            if absolute < 20:
                raise ValueError('Invalid ZIP64 archive')
            stream.seek(absolute-20)
            locator = struct.unpack('<4sLQL', stream.read(20))
            if locator[0] != b'PK\x06\x07' or locator[1] or locator[3] != 1:
                raise ValueError('Invalid ZIP64 locator')
            stream.seek(locator[2])
            record = stream.read(56)
            if len(record) != 56:
                raise ValueError('Invalid ZIP64 directory')
            fields = struct.unpack('<4sQ2H2L4Q', record)
            if fields[0] != b'PK\x06\x06' or fields[4] or fields[5] or fields[6] != fields[7]:
                raise ValueError('Invalid ZIP64 directory')
            count, directory_size = fields[7], fields[8]
        if count > MAX_ENTRIES or directory_size > MAX_DIRECTORY_BYTES:
            raise ValueError('Archive has too many entries or an oversized directory')


def _no_duplicates(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate manifest key')
        result[key] = value
    return result


def _extract(archive, stage):
    _preflight_zip(archive)
    with zipfile.ZipFile(archive) as z:
        infos = z.infolist()
        names = [entry.filename for entry in infos]
        if len(infos) > MAX_ENTRIES or len(set(names)) != len(names):
            raise ValueError('Duplicate paths or too many archive entries')
        if sum(entry.file_size for entry in infos) > MAX_EXPANDED_BYTES:
            raise ValueError('Archive exceeds 4 GiB expanded limit')
        for entry in infos:
            name = entry.filename
            mode = entry.external_attr >> 16
            if name != 'manifest.json' and name != 'workspace.sqlite3' and not re.fullmatch(r'originals/[0-9a-f]{64}', name):
                raise ValueError('Unexpected or unsafe archive path')
            if entry.is_dir() or (stat.S_IFMT(mode) not in (0, stat.S_IFREG)) or entry.flag_bits & 1:
                raise ValueError('Archive links, special files and encrypted entries are unsupported')
            if entry.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
                raise ValueError('Unsupported ZIP compression')
        if 'manifest.json' not in names or z.getinfo('manifest.json').file_size > MAX_MANIFEST_BYTES:
            raise ValueError('Missing or oversized manifest')
        manifest = json.loads(z.read('manifest.json'), object_pairs_hook=_no_duplicates)
        if not isinstance(manifest, dict) or manifest.get('format') != 'academic-workspace' or manifest.get('format_version') != 1:
            raise ValueError('Unsupported backup format')
        files = manifest.get('files')
        if not isinstance(files, dict) or set(files) != set(names)-{'manifest.json'} or 'workspace.sqlite3' not in files:
            raise ValueError('Manifest and archive files do not match')
        (stage/'originals').mkdir()
        total = 0
        for name, expected in files.items():
            if not isinstance(expected, dict) or not isinstance(expected.get('sha256'), str) or not HASH.fullmatch(expected['sha256']) or type(expected.get('size')) is not int or expected['size'] < 0:
                raise ValueError('Invalid file metadata')
            if z.getinfo(name).file_size != expected['size']:
                raise ValueError('File size mismatch')
            checksum, size = hashlib.sha256(), 0
            with z.open(name) as source, (stage/name).open('xb') as target:
                while block := source.read(BLOCK):
                    size += len(block)
                    total += len(block)
                    if total > MAX_EXPANDED_BYTES or size > expected['size']:
                        raise ValueError('Expanded file exceeds budget')
                    checksum.update(block)
                    target.write(block)
            if size != expected['size'] or checksum.hexdigest() != expected['sha256']:
                raise ValueError('Backup checksum mismatch')
        return manifest


def _schema(con):
    return con.execute('SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name').fetchall()


def _validate_database(db, stage, manifest):
    snapshot = stage/'workspace.sqlite3'
    # No archive triggers or application SQL are executed before schema equality.
    with closing(sqlite3.connect(f'{snapshot.as_uri()}?mode=ro&immutable=1', uri=True)) as con:
        con.execute('PRAGMA trusted_schema=OFF')
        version = con.execute('PRAGMA user_version').fetchone()[0]
        if version not in db.migrations or version > max(db.migrations):
            raise ValueError('Unsupported or newer database schema')
        if manifest.get('schema_version') != version:
            raise ValueError('Manifest schema version does not match database')
        older = {key:value for key,value in db.migrations.items() if key <= version}
        reference = Database(stage/'schema-reference', migrations=older)
        reference.initialize()
        with reference.connect() as trusted:
            if _schema(con) != [tuple(row) for row in _schema(trusted)]:
                raise ValueError('Database schema differs from the registered application schema')
        if [row[0] for row in con.execute('SELECT version FROM schema_migrations ORDER BY version')] != sorted(older):
            raise ValueError('Invalid database migration history')
        if con.execute('PRAGMA integrity_check').fetchall() != [('ok',)] or con.execute('PRAGMA foreign_key_check').fetchone():
            raise ValueError('Database integrity or foreign key check failed')
        originals = _blobs(con)
        actual = {key:value for key,value in manifest['files'].items() if key.startswith('originals/')}
        if originals != actual:
            raise ValueError('Database originals do not match the archive')
    staged = Database(stage, migrations=db.migrations)
    staged.initialize()
    reference.migrations = db.migrations
    reference.initialize()
    with staged.connect() as con, reference.connect() as trusted:
        if _schema(con) != _schema(trusted):
            raise ValueError('Migrated database schema differs from application schema')
        if con.execute('PRAGMA foreign_key_check').fetchone() or con.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise ValueError('Migrated database integrity check failed')
        con.execute('PRAGMA secure_delete=ON')
        con.execute('DELETE FROM agent_tokens')
        con.execute("UPDATE documents SET status='failed' WHERE id IN (SELECT document_id FROM jobs WHERE status IN ('queued','processing'))")
        interrupted = con.execute("UPDATE jobs SET status='failed',error='Interrupted by restore; retry indexing',updated_at=? WHERE status IN ('queued','processing')", (now(),)).rowcount
        if con.execute("SELECT 1 FROM sqlite_master WHERE name='embedding_runs' AND type='table'").fetchone():
            interrupted += con.execute("UPDATE embedding_runs SET status='failed',error='Interrupted by restore; retry indexing' WHERE status IN ('queued','processing')").rowcount
            con.execute('DELETE FROM embedding_staging WHERE run_id IN (SELECT id FROM embedding_runs WHERE error=?)', ('Interrupted by restore; retry indexing',))
    with closing(sqlite3.connect(snapshot)) as con:
        con.execute('VACUUM')
        con.execute('PRAGMA wal_checkpoint(TRUNCATE)')
        con.execute('PRAGMA journal_mode=DELETE')
    return interrupted


def _assert_idle(request):
    db = request.app.state.db
    for table in ('jobs','embedding_runs'):
        if db.one("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)) and db.one(f"SELECT 1 FROM {table} WHERE status IN ('queued','processing') LIMIT 1"):
            raise HTTPException(409, 'Wait for indexing and embedding work to finish before restoring')
    if any(lock.locked() for lock in getattr(request.app.state, 'conversation_locks', {}).values()):
        raise HTTPException(409, 'Wait for active conversations to finish before restoring')


def _install(request, stage):
    db = request.app.state.db
    with db.maintenance:
        _assert_idle(request)
        recovery = db.root/'recovery'/new_id()
        recovery.mkdir(parents=True)
        _snapshot(db, recovery/'workspace.sqlite3')
        # All application connections have closed under maintenance. Checkpoint
        # before rename so no old WAL can ever replay onto the restored database.
        with db.connect() as con:
            checkpoint = con.execute('PRAGMA wal_checkpoint(TRUNCATE)').fetchone()
            if checkpoint[0]:
                raise HTTPException(409, 'Database is busy; retry restore after readers finish')
        old_db = stage/'previous.sqlite3'
        originals = db.root/'originals'
        secret = db.root/'provider-secret.json'
        moved_db = moved_originals = installed_originals = moved_secret = False
        try:
            db.path.replace(old_db)
            moved_db = True
            if originals.exists():
                originals.replace(recovery/'originals')
                moved_originals = True
            else:
                (recovery/'originals').mkdir()
            if secret.exists() or secret.is_symlink():
                # Rename preserves restrictive file permissions. Credentials
                # remain available for local recovery, but are never exported
                # or reused with the restored provider configuration.
                secret.replace(recovery/'provider-secret.json')
                moved_secret = True
            (stage/'workspace.sqlite3').replace(db.path)
            (stage/'originals').replace(originals)
            installed_originals = True
        except Exception:
            rollback_errors = []
            # Try both repairs independently; an unavailable originals folder
            # must not prevent restoring the old database and credentials.
            try:
                if moved_db:
                    old_db.replace(db.path)
            except OSError as exc:
                rollback_errors.append(exc)
            try:
                if installed_originals:
                    shutil.rmtree(originals)
                if moved_originals:
                    (recovery/'originals').replace(originals)
            except OSError as exc:
                rollback_errors.append(exc)
            try:
                if moved_secret:
                    (recovery/'provider-secret.json').replace(secret)
            except OSError as exc:
                rollback_errors.append(exc)
            if rollback_errors:
                raise RollbackFailure(f'Manual recovery required; preserved {recovery.relative_to(db.root)} and {stage.relative_to(db.root)}') from rollback_errors[0]
            raise
        request.app.state.sessions.clear()
        return {'status':'restored','recovery_path':str(recovery.relative_to(db.root)),'reauthenticate':True}


@router.post('/restore')
def restore(request: Request, archive: Annotated[UploadFile, File()], confirm: Annotated[str, Form()]):
    if confirm != 'RESTORE':
        raise HTTPException(422, 'Type RESTORE to confirm library replacement')
    db = request.app.state.db
    stage = _temporary(db, 'restore-')
    preserve_stage = False
    try:
        uploaded = stage/'upload.zip'
        size = 0
        with uploaded.open('wb') as target:
            while block := archive.file.read(BLOCK):
                size += len(block)
                if size > MAX_ARCHIVE_BYTES:
                    raise HTTPException(413, 'Backup archive exceeds upload limit')
                target.write(block)
        try:
            manifest = _extract(uploaded, stage)
            interrupted = _validate_database(db, stage, manifest)
        except (ValueError, TypeError, KeyError, sqlite3.Error, zipfile.BadZipFile, EOFError, RuntimeError, struct.error, UnicodeError) as exc:
            raise HTTPException(422, 'Invalid backup: '+str(exc)) from exc
        try:
            result = _install(request, stage)
            result['interrupted_jobs'] = interrupted
            return result
        except RollbackFailure as exc:
            preserve_stage = True
            raise HTTPException(500, str(exc)) from exc
        except OSError as exc:
            raise HTTPException(500, 'Restore installation failed; existing library was retained') from exc
    finally:
        archive.file.close()
        if not preserve_stage:
            shutil.rmtree(stage, ignore_errors=True)
