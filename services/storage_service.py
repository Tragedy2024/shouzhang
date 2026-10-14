"""Small, persistent store for private photos and resumable journal jobs."""

import json
import re
import sqlite3
import time
from pathlib import Path


PHOTO_NAME = re.compile(r"^[a-f0-9]{32}\.jpg$")
RETENTION_SECONDS = 7 * 24 * 60 * 60


class JournalStore:
    def __init__(self, database_path, upload_directory):
        self.path = str(database_path)
        self.upload_directory = Path(upload_directory).resolve()
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.upload_directory.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("""CREATE TABLE IF NOT EXISTS photos (
                filename TEXT PRIMARY KEY, owner TEXT NOT NULL,
                created_at REAL NOT NULL, metadata TEXT NOT NULL)""")
            conn.execute("""CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY, owner TEXT NOT NULL,
                created_at REAL NOT NULL, updated_at REAL NOT NULL,
                status TEXT NOT NULL, record TEXT NOT NULL)""")
            # Creating these tables also migrates existing private-only stores.
            # Published media has its own directory and no photo-expiry dependency.
            conn.execute("""CREATE TABLE IF NOT EXISTS hall_posts (
                id TEXT PRIMARY KEY, owner TEXT NOT NULL,
                idempotency_key TEXT NOT NULL, payload_hash TEXT NOT NULL,
                title TEXT NOT NULL, caption TEXT NOT NULL,
                author_name TEXT NOT NULL, style TEXT NOT NULL,
                created_at REAL NOT NULL, status TEXT NOT NULL DEFAULT 'active',
                image_filename TEXT NOT NULL, thumbnail_filename TEXT NOT NULL,
                image_width INTEGER NOT NULL, image_height INTEGER NOT NULL,
                UNIQUE(owner, idempotency_key))""")
            conn.execute("""CREATE TABLE IF NOT EXISTS hall_topics (
                id INTEGER PRIMARY KEY, name TEXT NOT NULL,
                topic_key TEXT NOT NULL UNIQUE)""")
            conn.execute("""CREATE TABLE IF NOT EXISTS hall_post_topics (
                post_id TEXT NOT NULL, topic_id INTEGER NOT NULL,
                position INTEGER NOT NULL,
                PRIMARY KEY(post_id, topic_id),
                FOREIGN KEY(post_id) REFERENCES hall_posts(id),
                FOREIGN KEY(topic_id) REFERENCES hall_topics(id))""")
            conn.execute("CREATE INDEX IF NOT EXISTS hall_posts_feed ON hall_posts(status, created_at DESC, id DESC)")
            conn.execute("CREATE INDEX IF NOT EXISTS hall_posts_owner ON hall_posts(owner, created_at DESC)")
            conn.execute("CREATE INDEX IF NOT EXISTS hall_post_topics_topic ON hall_post_topics(topic_id, post_id)")

    def connect(self):
        return sqlite3.connect(self.path, timeout=15)

    def add_photo(self, filename, owner, metadata):
        with self.connect() as conn:
            conn.execute("INSERT INTO photos VALUES (?, ?, ?, ?)",
                         (filename, owner, time.time(), json.dumps(metadata, ensure_ascii=False)))

    def photo(self, filename, owner):
        if not PHOTO_NAME.fullmatch(filename):
            return None
        with self.connect() as conn:
            row = conn.execute(
                "SELECT metadata FROM photos WHERE filename=? AND owner=? AND created_at>?",
                (filename, owner, time.time() - RETENTION_SECONDS),
            ).fetchone()
        if not row:
            return None
        # Resolve again to reject symlinks as well as traversal.
        candidate = self.upload_directory / filename
        if candidate.is_symlink():
            return None
        path = candidate.resolve()
        if path.parent != self.upload_directory or not path.is_file():
            return None
        return {"path": str(path), "metadata": json.loads(row[0])}

    def remove_photo(self, filename, owner):
        with self.connect() as conn:
            deleted = conn.execute("DELETE FROM photos WHERE filename=? AND owner=?", (filename, owner)).rowcount
        if not deleted:
            return
        if PHOTO_NAME.fullmatch(filename):
            path = self.upload_directory / filename
            if path.resolve().parent == self.upload_directory:
                path.unlink(missing_ok=True)

    def create_job(self, record, active_limit=2):
        now = time.time()
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            count = conn.execute(
                "SELECT COUNT(*) FROM jobs WHERE owner=? AND status IN ('queued', 'running')",
                (record["owner"],),
            ).fetchone()[0]
            total = conn.execute(
                "SELECT COUNT(*) FROM jobs WHERE status IN ('queued', 'running')"
            ).fetchone()[0]
            if count >= active_limit or total >= 12:
                return False
            conn.execute("INSERT INTO jobs VALUES (?, ?, ?, ?, ?, ?)",
                         (record["job_id"], record["owner"], now, now, record["status"],
                          json.dumps(record, ensure_ascii=False)))
        return True

    def job(self, job_id, owner):
        with self.connect() as conn:
            row = conn.execute("SELECT record FROM jobs WHERE id=? AND owner=?",
                               (job_id, owner)).fetchone()
        return json.loads(row[0]) if row else None

    def save_job(self, record):
        with self.connect() as conn:
            conn.execute("UPDATE jobs SET record=?, status=?, updated_at=? WHERE id=? AND owner=?",
                         (json.dumps(record, ensure_ascii=False), record["status"], time.time(),
                          record["job_id"], record["owner"]))

    def claim_retry(self, job_id, owner):
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT record FROM jobs WHERE id=? AND owner=?", (job_id, owner)).fetchone()
            if not row:
                return None
            record = json.loads(row[0])
            if record["status"] != "failed" or not record.get("retryable"):
                return None
            active = conn.execute(
                "SELECT COUNT(*) FROM jobs WHERE status IN ('queued', 'running') AND owner=?",
                (owner,),
            ).fetchone()[0]
            total = conn.execute(
                "SELECT COUNT(*) FROM jobs WHERE status IN ('queued', 'running')"
            ).fetchone()[0]
            if active >= 2 or total >= 12:
                return None
            record.update(status="queued", message="准备重试，已完成的步骤会保留。")
            record.pop("error", None)
            conn.execute("UPDATE jobs SET record=?, status='queued', updated_at=? WHERE id=?",
                         (json.dumps(record, ensure_ascii=False), time.time(), job_id))
        return record

    def recover_interrupted_jobs(self):
        with self.connect() as conn:
            rows = conn.execute("SELECT id, record FROM jobs WHERE status IN ('queued', 'running')").fetchall()
            for job_id, encoded in rows:
                record = json.loads(encoded)
                record.update(status="failed", error="服务重新启动，点击重试可继续已完成的步骤。",
                              message="生成已中断", retryable=True)
                conn.execute("UPDATE jobs SET status='failed', record=?, updated_at=? WHERE id=?",
                             (json.dumps(record, ensure_ascii=False), time.time(), job_id))

    def cleanup(self):
        """Expire only photos registered here; never touch pre-existing user files."""
        cutoff = time.time() - RETENTION_SECONDS
        with self.connect() as conn:
            rows = conn.execute("SELECT filename, owner FROM photos WHERE created_at<?", (cutoff,)).fetchall()
            conn.execute("DELETE FROM jobs WHERE created_at<? AND status NOT IN ('queued', 'running')", (cutoff,))
        for filename, owner in rows:
            self.remove_photo(filename, owner)
