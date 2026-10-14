"""Persistent, explicitly published journal snapshots and public discovery."""

import hashlib
import io
import json
import re
import sqlite3
import time
import unicodedata
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image

POST_ID = re.compile(r"^[a-f0-9]{32}$")
DAILY_POST_LIMIT = 20


class HallError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.message = message
        self.status = status


def normalize_topic(value):
    return unicodedata.normalize('NFKC', value).strip().lstrip('#').strip()


def payload_fingerprint(payload):
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')
    return hashlib.sha256(encoded).hexdigest()


def public_post(record, owner):
    """Expose only display fields; never private photo records or disk paths."""
    post_id = record['id']
    return {
        'id': post_id, 'title': record['title'], 'caption': record['caption'],
        'author_name': record['author_name'], 'topics': record['topics'],
        'created_at': datetime.fromtimestamp(record['created_at'], timezone.utc).isoformat().replace('+00:00', 'Z'),
        'style': record['style'], 'image_width': record['image_width'],
        'image_height': record['image_height'], 'is_owner': record['owner'] == owner,
        'image_url': f'/api/hall/posts/{post_id}/image',
        'thumbnail_url': f'/api/hall/posts/{post_id}/thumbnail',
        'detail_url': f'/hall?post={post_id}',
    }


class HallService:
    def __init__(self, store, media_directory):
        self.store = store
        self.media_directory = Path(media_directory).resolve()
        self.media_directory.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def _connect(self):
        connection = self.store.connect()
        connection.row_factory = sqlite3.Row
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    @staticmethod
    def _with_topics(connection, rows):
        records = [dict(row) for row in rows]
        if not records:
            return records
        by_id = {record['id']: record for record in records}
        for record in records:
            record['topics'] = []
        placeholders = ','.join('?' for _ in records)
        topics = connection.execute(
            f'''SELECT relation.post_id, topic.name FROM hall_post_topics relation
                JOIN hall_topics topic ON topic.id=relation.topic_id
                WHERE relation.post_id IN ({placeholders})
                ORDER BY relation.position''', tuple(by_id),
        ).fetchall()
        for topic in topics:
            by_id[topic['post_id']]['topics'].append(topic['name'])
        return records

    def _idempotent(self, connection, owner, key, fingerprint):
        row = connection.execute(
            'SELECT * FROM hall_posts WHERE owner=? AND idempotency_key=?', (owner, key),
        ).fetchone()
        if not row:
            return None
        if row['payload_hash'] != fingerprint:
            raise HallError('这次发布内容已改变，请重新确认后发布。', 409)
        if row['status'] != 'active':
            raise HallError('这篇手帐已撤回，如需重新发布请再次确认。', 409)
        return self._with_topics(connection, [row])[0]

    @staticmethod
    def _check_quota(connection, owner, now):
        # Reset at local midnight in China; withdrawing does not reset the quota.
        day_start = ((now + 8 * 3600) // 86400) * 86400 - 8 * 3600
        count = connection.execute(
            'SELECT COUNT(*) FROM hall_posts WHERE owner=? AND created_at>=? AND created_at<?',
            (owner, day_start, day_start + 86400),
        ).fetchone()[0]
        if count >= DAILY_POST_LIMIT:
            raise HallError('每天最多发布 20 篇手帐，请明天再来。', 429)

    def preflight(self, owner, key, fingerprint):
        """Allow retries even after the original private photos have expired."""
        with self._connect() as connection:
            existing = self._idempotent(connection, owner, key, fingerprint)
            if existing:
                return existing
            self._check_quota(connection, owner, time.time())
        return None

    @staticmethod
    def _thumbnail(png_bytes):
        with Image.open(io.BytesIO(png_bytes)) as original:
            if original.format != 'PNG':
                raise ValueError('The server renderer must return PNG')
            width, height = original.size
            if width < 1 or height < 1:
                raise ValueError('The server renderer returned an empty image')
            preview_width = min(width, 640)
            preview_height = max(1, round(height * preview_width / width))
            with original.convert('RGB') as rgb:
                with rgb.resize((preview_width, preview_height), Image.Resampling.LANCZOS) as resized:
                    # A top crop keeps the journal heading and first photo visible.
                    with resized.crop((0, 0, preview_width, min(preview_height, 900))) as preview:
                        output = io.BytesIO()
                        preview.save(output, format='JPEG', quality=88, optimize=True, exif=b'')
            return width, height, output.getvalue()

    def publish(self, owner, key, fingerprint, payload, png_bytes):
        width, height, thumbnail = self._thumbnail(png_bytes)
        created_paths = []
        try:
            with self._connect() as connection:
                connection.execute('BEGIN IMMEDIATE')
                existing = self._idempotent(connection, owner, key, fingerprint)
                if existing:
                    return existing, False
                now = time.time()
                self._check_quota(connection, owner, now)
                post_id = uuid.uuid4().hex
                image_filename, thumbnail_filename = post_id + '.png', post_id + '.thumb.jpg'
                for filename, content in ((image_filename, png_bytes), (thumbnail_filename, thumbnail)):
                    path = self.media_directory / filename
                    # Exclusive creation prevents following any pre-existing symlink.
                    with path.open('xb') as handle:
                        created_paths.append(path)
                        handle.write(content)
                connection.execute(
                    '''INSERT INTO hall_posts
                       (id,owner,idempotency_key,payload_hash,title,caption,author_name,style,
                        created_at,status,image_filename,thumbnail_filename,image_width,image_height)
                       VALUES (?,?,?,?,?,?,?,?,?,'active',?,?,?,?)''',
                    (post_id, owner, key, fingerprint, payload['title'], payload['caption'],
                     payload['author_name'], payload['style'], now, image_filename,
                     thumbnail_filename, width, height),
                )
                for position, name in enumerate(payload['topics']):
                    topic_key = name.casefold()
                    connection.execute(
                        'INSERT OR IGNORE INTO hall_topics(name,topic_key) VALUES (?,?)', (name, topic_key),
                    )
                    topic_id = connection.execute(
                        'SELECT id FROM hall_topics WHERE topic_key=?', (topic_key,),
                    ).fetchone()[0]
                    connection.execute(
                        'INSERT INTO hall_post_topics(post_id,topic_id,position) VALUES (?,?,?)',
                        (post_id, topic_id, position),
                    )
                row = connection.execute('SELECT * FROM hall_posts WHERE id=?', (post_id,)).fetchone()
                record = self._with_topics(connection, [row])[0]
            return record, True
        except Exception:
            for path in created_paths:
                path.unlink(missing_ok=True)
            raise

    def post(self, post_id):
        if not POST_ID.fullmatch(post_id):
            return None
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM hall_posts WHERE id=? AND status='active'", (post_id,),
            ).fetchone()
            return self._with_topics(connection, [row])[0] if row else None

    def list_posts(self, owner, page=1, page_size=12, topic='', query='', mine=False):
        clauses, values = ["post.status='active'"], []
        if mine:
            clauses.append('post.owner=?')
            values.append(owner)
        if topic:
            clauses.append('''EXISTS (SELECT 1 FROM hall_post_topics relation
                JOIN hall_topics topic ON topic.id=relation.topic_id
                WHERE relation.post_id=post.id AND topic.topic_key=?)''')
            values.append(normalize_topic(topic).casefold())
        if query:
            # Treat %, _ and backslashes literally rather than as wildcards.
            needle = '%' + query.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%'
            clauses.append('''(post.title LIKE ? ESCAPE '\\' OR post.caption LIKE ? ESCAPE '\\'
                OR post.author_name LIKE ? ESCAPE '\\' OR EXISTS (
                    SELECT 1 FROM hall_post_topics relation JOIN hall_topics topic ON topic.id=relation.topic_id
                    WHERE relation.post_id=post.id AND topic.name LIKE ? ESCAPE '\\'))''')
            values.extend([needle] * 4)
        where = ' AND '.join(clauses)
        with self._connect() as connection:
            total = connection.execute(f'SELECT COUNT(*) FROM hall_posts post WHERE {where}', values).fetchone()[0]
            rows = connection.execute(
                f'''SELECT post.* FROM hall_posts post WHERE {where}
                    ORDER BY post.created_at DESC, post.id DESC LIMIT ? OFFSET ?''',
                (*values, page_size, (page - 1) * page_size),
            ).fetchall()
            records = self._with_topics(connection, rows)
        return {'posts': [public_post(record, owner) for record in records],
                'page': page, 'page_size': page_size, 'total': total,
                'has_more': page * page_size < total}

    def topics(self):
        with self._connect() as connection:
            rows = connection.execute('''SELECT topic.name, COUNT(*) AS count FROM hall_topics topic
                JOIN hall_post_topics relation ON relation.topic_id=topic.id
                JOIN hall_posts post ON post.id=relation.post_id AND post.status='active'
                GROUP BY topic.id ORDER BY count DESC, topic.name ASC''').fetchall()
            return [dict(row) for row in rows]

    def media(self, post_id, thumbnail=False):
        record = self.post(post_id)
        if not record:
            return None
        field = 'thumbnail_filename' if thumbnail else 'image_filename'
        expected = post_id + ('.thumb.jpg' if thumbnail else '.png')
        if record[field] != expected:
            return None
        candidate = self.media_directory / record[field]
        if candidate.is_symlink():
            return None
        path = candidate.resolve()
        if path.parent != self.media_directory or not path.is_file():
            return None
        return path

    def withdraw(self, post_id, owner):
        if not POST_ID.fullmatch(post_id):
            raise HallError('这篇手帐不存在或已撤回。', 404)
        with self._connect() as connection:
            connection.execute('BEGIN IMMEDIATE')
            row = connection.execute('SELECT owner FROM hall_posts WHERE id=?', (post_id,)).fetchone()
            if not row:
                raise HallError('这篇手帐不存在或已撤回。', 404)
            if row['owner'] != owner:
                raise HallError('你只能撤回自己发布的手帐。', 403)
            connection.execute("UPDATE hall_posts SET status='withdrawn' WHERE id=? AND owner=?", (post_id, owner))
