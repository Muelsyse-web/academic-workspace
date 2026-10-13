"""Durable, bounded document indexing with immutable source versions."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import hashlib
import logging
from .db import new_id, now
from .search import index_text

logger = logging.getLogger(__name__)


class IndexWorker:
    def __init__(self, db):
        self.db = db
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='index')

    def recover(self):
        with self.db.connect() as con:
            con.execute("UPDATE jobs SET status='queued' WHERE status='processing'")
        for row in self.db.all("SELECT id FROM jobs WHERE status='queued'"):
            self.submit(row['id'])

    def submit(self, job_id):
        self.pool.submit(self.run, job_id)

    def close(self):
        self.pool.shutdown(wait=True)

    def run(self, job_id):
        db = self.db
        with db.connect() as con:
            job = con.execute("SELECT * FROM jobs WHERE id=? AND status='queued'", (job_id,)).fetchone()
            if job is None:
                return
            doc = dict(con.execute('SELECT * FROM documents WHERE id=?',(job['document_id'],)).fetchone())
            con.execute("UPDATE jobs SET status='processing',progress=5,attempts=attempts+1,updated_at=? WHERE id=?",(now(),job_id))
            con.execute("UPDATE documents SET status='processing' WHERE id=?",(doc['id'],))
        try:
            from .parsing import parse_document
            path = db.root/'originals'/doc['blob_hash']
            with path.open('rb') as stream:
                actual = hashlib.file_digest(stream,'sha256').hexdigest()
            if actual != doc['blob_hash']:
                raise ValueError('Original checksum mismatch; restore the original from backup.')
            units = parse_document(path,doc['kind'])
            version_id = new_id()
            has_text = any(unit['text'].strip() for unit in units)
            title = doc['title']
            if doc['active_version'] is None and title == Path(doc['filename']).stem:
                title = next((unit['heading'].strip() for unit in units if unit['heading'].strip() and unit['heading'] != doc['blob_hash'] and len(unit['heading']) <= 150), title)
            with db.connect() as con:
                con.execute('INSERT INTO document_versions VALUES (?,?,?,?)',(version_id,doc['id'],now(),'1'))
                for unit in units:
                    if unit['heading'] == doc['blob_hash']:
                        unit['heading'] = doc['title']
                    unit_id = new_id()
                    con.execute('INSERT INTO source_units VALUES (?,?,?,?,?,?)',(unit_id,version_id,unit['locator_type'],unit['locator'],unit['heading'],unit['text']))
                    text = unit['text']
                    for ordinal,start in enumerate(range(0,len(text),1600)):
                        chunk = text[start:start+1800]
                        if not chunk.strip():
                            continue
                        chunk_id = new_id()
                        con.execute('INSERT INTO chunks VALUES (?,?,?,?,?,?)',(chunk_id,unit_id,version_id,doc['id'],chunk,ordinal))
                        con.execute('INSERT INTO chunks_fts VALUES (?,?)',(chunk_id,index_text(chunk)))
                con.execute('UPDATE documents SET active_version=?,status=?,title=CASE WHEN title=? THEN ? ELSE title END WHERE id=?',(version_id,'ready' if has_text else 'needs_attention',doc['title'],title,doc['id']))
                con.execute("UPDATE jobs SET status='done',progress=100,error=NULL,updated_at=? WHERE id=?",(now(),job_id))
                db.activity(con,'import','完成索引：'+doc['title'])
        except Exception as exc:
            message = str(exc)[:400] if isinstance(exc, ValueError) else 'Document processing failed. Check format and retry.'
            logger.warning('Index failure job=%s type=%s', job_id,type(exc).__name__)
            with db.connect() as con:
                con.execute("UPDATE jobs SET status='failed',error=?,updated_at=? WHERE id=?",(message,now(),job_id))
                con.execute("UPDATE documents SET status='failed' WHERE id=?",(doc['id'],))
