"""Private travel journals with editable results and resumable generation."""
import io
import json
import logging
import os
import secrets
import threading
import time
import uuid
import warnings
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path

from flask import Flask, Response, jsonify, render_template, request, session, send_file
from PIL import Image, ImageOps, UnidentifiedImageError
from werkzeug.exceptions import HTTPException
from config import ALLOWED_EXTENSIONS, UPLOAD_FOLDER
from services.errors import GenerationError
from services.hall_service import HallError, HallService, normalize_topic, payload_fingerprint, public_post
from services.image_render_service import _parse_journal_sections, render_journal_to_bytes
from services.map_service import reverse_geocode
from services.storage_service import JournalStore, PHOTO_NAME
from services.text_service import STYLES, TONES, generate_journal, regenerate_journal
from services.vision_service import analyze_images_batch
from utils.image_utils import extract_datetime, extract_gps

BASE_DIR = Path(__file__).resolve().parent
app = Flask(__name__)
app.config.update(MAX_CONTENT_LENGTH=50 * 1024 * 1024,
                  UPLOAD_FOLDER=str((BASE_DIR / UPLOAD_FOLDER).resolve()),
                  JOURNAL_DB_PATH=str(BASE_DIR / 'instance' / 'journal.sqlite3'),
                  HALL_MEDIA_FOLDER=str(BASE_DIR / 'instance' / 'hall-media'),
                  SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax',
                  SESSION_COOKIE_SECURE=os.environ.get('JOURNAL_HTTPS') == '1',
                  PERMANENT_SESSION_LIFETIME=timedelta(days=365), JOBS_INLINE=False)
MAX_PHOTOS, MAX_PHOTO_BYTES, MAX_PIXELS, MAX_TEXT = 9, 16 * 1024 * 1024, 30_000_000, 12_000
executor = ThreadPoolExecutor(max_workers=3, thread_name_prefix='journal')
_stores, _cleanup_times = {}, {}
_store_lock = threading.Lock()
logger = logging.getLogger(__name__)


def _session_key():
    if os.environ.get('JOURNAL_SECRET_KEY'):
        return os.environ['JOURNAL_SECRET_KEY']
    directory = BASE_DIR / 'instance'
    directory.mkdir(exist_ok=True)
    path = directory / '.session-key'
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w') as handle:
            handle.write(secrets.token_hex(32))
    except FileExistsError:
        pass
    return path.read_text().strip()


app.secret_key = _session_key()


def _store():
    key = (app.config['JOURNAL_DB_PATH'], app.config['UPLOAD_FOLDER'])
    with _store_lock:
        if key not in _stores:
            store = JournalStore(*key)
            store.recover_interrupted_jobs()
            _stores[key] = store
        return _stores[key]


def _owner():
    session.permanent = True
    if 'owner_id' not in session:
        session['owner_id'] = uuid.uuid4().hex
    return session['owner_id']


def _hall():
    # Read the live configuration so test and deployment overrides stay isolated.
    return HallService(_store(), app.config['HALL_MEDIA_FOLDER'])


@app.before_request
def prepare_session():
    _owner()
    store = _store()
    now = time.monotonic()
    with _store_lock:
        due = now - _cleanup_times.get(store.path, -3601) > 3600
        if due:
            _cleanup_times[store.path] = now
    if due:
        store.cleanup()


@app.errorhandler(HTTPException)
def http_error(error):
    message = {400: '请求内容不完整，请检查后重试。', 404: '照片或任务已过期，请重新选择照片。',
               413: '照片合计不能超过 50MB，每张不能超过 16MB。',
               429: '已有任务正在生成，请稍后再试。'}.get(error.code, '请求失败，请稍后重试。')
    if request.path.startswith(('/api/', '/uploads/')):
        return jsonify(error=message), error.code
    return render_template('index.html', error=message), error.code


@app.errorhandler(HallError)
def hall_error(error):
    return jsonify(error=error.message), error.status


def _hall_publication_fields():
    if request.files:
        raise HallError('请发布当前手帐作品，不要另行上传公开图片。')
    form = request.form
    if form.get('public_confirm', '').strip() != 'true':
        raise HallError('请先确认将这篇手帐公开到大厅。')
    fields = {}
    for name, maximum, required, label in (
        ('title', 100, True, '发布标题'), ('caption', 2000, False, '发布说明'),
        ('author_name', 30, True, '作者昵称'),
    ):
        value = form.get(name, '').strip()
        if (required and not value) or len(value) > maximum:
            raise HallError(f'{label}' + (f'需要填写，最多 {maximum} 字。' if required else f'最多 {maximum} 字。'))
        fields[name] = value
    key = form.get('idempotency_key', '').strip()
    try:
        if not key or len(key) > 36:
            raise ValueError
        key = str(uuid.UUID(key))
    except (ValueError, AttributeError):
        raise HallError('发布标识无效，请重新打开发布窗口。') from None
    try:
        topics = json.loads(form.get('topics', '[]'))
    except (ValueError, TypeError):
        raise HallError('话题格式不正确，请重新填写。') from None
    if not isinstance(topics, list) or len(topics) > 5 or any(not isinstance(topic, str) for topic in topics):
        raise HallError('最多添加 5 个话题，每个话题为 1–20 字。')
    fields['topics'], seen = [], set()
    for raw in topics:
        topic = normalize_topic(raw)
        if not topic or len(topic) > 20:
            raise HallError('每个话题需要填写 1–20 字。')
        if topic.casefold() not in seen:
            fields['topics'].append(topic)
            seen.add(topic.casefold())

    text = form.get('journal_text', '')
    if 'sections' in form:
        try:
            sections = json.loads(form['sections'])
        except (ValueError, TypeError):
            raise HallError('手帐内容格式不正确，请重新编辑。') from None
        if (not isinstance(sections, dict) or not isinstance(sections.get('title'), str)
                or not isinstance(sections.get('body'), str) or not isinstance(sections.get('tags'), list)
                or len(sections['tags']) > 100 or any(not isinstance(tag, str) for tag in sections['tags'])):
            raise HallError('手帐标题、正文或标签格式不正确。')
        sections = {name: sections[name] for name in ('title', 'body', 'tags')}
    else:
        if not text.strip() or len(text) > MAX_TEXT:
            raise HallError('手帐内容不能为空，最多 12000 字。')
        sections = _parse_journal_sections(text)
    content_length = len(sections['title']) + len(sections['body']) + sum(len(tag) for tag in sections['tags'])
    sections['tags'] = [tag.strip() for tag in sections['tags'] if tag.strip().lstrip('#＃').strip()]
    if (content_length > MAX_TEXT
            or not (sections['title'].strip() or sections['body'].strip() or sections['tags'])):
        raise HallError('手帐内容不能为空，最多 12000 字。')
    # Reject pathological line-per-character layouts before allocating a canvas.
    if sections['title'].count('\n') + sections['body'].count('\n') > 400:
        raise HallError('手帐分行过多，请合并部分段落后再发布。')
    fields['sections'] = sections
    fields['style'] = form.get('style', 'xiaohongshu').strip()
    if fields['style'] not in STYLES:
        raise HallError('请选择支持的手帐风格。')
    for name, maximum in (('address', 500), ('datetime_str', 100), ('date', 10), ('weather', 50)):
        value = form.get(name, '').strip()
        if len(value) > maximum:
            raise HallError('日期、地点或天气内容过长。')
        fields[name] = value
    if fields['date']:
        from datetime import date
        try:
            date.fromisoformat(fields['date'])
        except ValueError:
            raise HallError('请选择有效的旅行日期。') from None
    raw_names = form.get('image_filenames', '')
    if len(raw_names) > 500:
        raise HallError('照片信息不正确，请重新选择作品。')
    filenames = [value.strip() for value in raw_names.split(',') if value.strip()]
    if len(filenames) > MAX_PHOTOS or any(not PHOTO_NAME.fullmatch(name) for name in filenames):
        raise HallError('每次最多使用 9 张有效照片。')
    fields['image_filenames'] = filenames
    return key, fields


def _hall_pagination():
    numbers = {}
    for name, default, maximum in (('page', '1', 1_000_000), ('page_size', '12', 50)):
        value = request.args.get(name, default)
        if not value.isdecimal() or len(value) > 8:
            raise HallError('分页参数不正确。')
        number = int(value)
        if not 1 <= number <= maximum:
            raise HallError('分页参数超出允许范围。')
        numbers[name] = number
    topic = normalize_topic(request.args.get('topic', ''))
    query = request.args.get('q', '').strip()
    if len(topic) > 20 or len(query) > 200:
        raise HallError('话题或搜索内容过长。')
    mine = request.args.get('mine', '0')
    if mine not in ('0', '1'):
        raise HallError('请选择有效的浏览范围。')
    return {**numbers, 'topic': topic, 'query': query, 'mine': mine == '1'}


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def _fields(form):
    fields = {key: form.get(key, '').strip() for key in ('location', 'mood', 'feelings', 'style', 'date', 'weather')}
    fields['style'] = fields['style'] or 'xiaohongshu'
    if fields['style'] not in STYLES:
        raise ValueError('请选择支持的手帐风格。')
    limits = {'location': 200, 'mood': 100, 'feelings': 2000, 'date': 10, 'weather': 50}
    if any(len(fields[key]) > limit for key, limit in limits.items()):
        raise ValueError('补充内容过长，请适当缩短。')
    if fields['date']:
        from datetime import date
        try:
            date.fromisoformat(fields['date'])
        except ValueError:
            raise ValueError('请选择有效的旅行日期。') from None
    return fields


def _save_uploaded_images(files, owner):
    files = [file for file in files if file.filename]
    if not files:
        raise ValueError('请选择至少一张图片。')
    if len(files) > MAX_PHOTOS:
        raise ValueError('每次最多上传 9 张照片。')
    saved, store = [], _store()
    try:
        for file in files:
            if not allowed_file(file.filename):
                raise ValueError('请上传 JPG、PNG 或 WebP 格式的照片。')
            raw = file.stream.read(MAX_PHOTO_BYTES + 1)
            if not raw or len(raw) > MAX_PHOTO_BYTES:
                raise ValueError('每张照片不能超过 16MB。')
            metadata = {'datetime_str': extract_datetime(io.BytesIO(raw)), 'gps': extract_gps(io.BytesIO(raw))}
            with warnings.catch_warnings():
                warnings.simplefilter('error', Image.DecompressionBombWarning)
                with Image.open(io.BytesIO(raw)) as original:
                    if original.format not in ('JPEG', 'PNG', 'WEBP'):
                        raise ValueError('照片格式与文件名不符，请重新选择。')
                    if original.width * original.height > MAX_PIXELS:
                        raise ValueError('照片分辨率过高，请压缩到 3000 万像素以内。')
                    image = ImageOps.exif_transpose(original)
                    if image.mode in ('RGBA', 'LA') or 'transparency' in image.info:
                        rgba = image.convert('RGBA')
                        image = Image.alpha_composite(Image.new('RGBA', rgba.size, 'white'), rgba).convert('RGB')
                    else:
                        image = image.convert('RGB')
                    filename = f'{uuid.uuid4().hex}.jpg'
                    path = store.upload_directory / filename
                    image.save(path, 'JPEG', quality=93, optimize=True, exif=b'')
            metadata['filename'] = filename
            try:
                store.add_photo(filename, owner, metadata)
            except Exception:
                path.unlink(missing_ok=True)
                raise
            saved.append(metadata)
        return saved
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        for item in saved:
            store.remove_photo(item['filename'], owner)
        raise ValueError('有照片无法读取，请更换文件后重试。') from None
    except Exception:
        for item in saved:
            store.remove_photo(item['filename'], owner)
        raise


def _photo_paths(filenames, owner):
    if len(filenames) > MAX_PHOTOS:
        raise ValueError('每次最多使用 9 张照片。')
    paths = []
    for filename in filenames:
        photo = _store().photo(filename, owner)
        if not photo:
            raise ValueError('有照片已过期或无法访问，请重新选择照片。')
        paths.append(photo['path'])
    return paths


def _public_job(record):
    return {key: record[key] for key in ('job_id', 'status', 'stage', 'message', 'result', 'error', 'retryable') if key in record}


def _update(record, stage, message):
    record.update(status='running', stage=stage, message=message)
    _store().save_job(record)


def _run_job(job_id, owner):
    with app.app_context():
        record = _store().job(job_id, owner)
        if not record:
            return
        fields = record['fields']
        try:
            paths = _photo_paths([item['filename'] for item in record['photos']], owner)
            if 'image_description' not in record:
                _update(record, 'vision', '正在分析照片，寻找这段旅程的细节。')
                description = analyze_images_batch(paths)
                if not description.strip():
                    raise GenerationError('照片分析未完成，请点击重试。', 'vision', True)
                record['image_description'] = description
                _store().save_job(record)
            if 'location_data' not in record:
                _update(record, 'location', '正在整理照片的日期和地点。')
                addresses, notes = {}, []
                for item in record['photos']:
                    gps = item.get('gps')
                    if gps and not fields['location']:
                        coord = tuple(round(value, 4) for value in gps)
                        if coord not in addresses:
                            addresses[coord] = reverse_geocode(*gps)
                        item['address'] = addresses[coord]
                known = list(dict.fromkeys(address for address in addresses.values() if address))
                dates = list(dict.fromkeys(item['datetime_str'][:10] for item in record['photos'] if item.get('datetime_str')))
                if len(dates) > 1:
                    notes.append('照片来自不同日期，请在编辑区确认旅行日期。')
                if len(known) > 1:
                    notes.append('照片包含多个拍摄地点，请确认手帐地点。')
                if addresses and not known:
                    notes.append('自动定位暂时不可用，可以手动补充地点。')
                if not fields['location'] and not known:
                    notes.append('未确认具体地点，手帐仅依据照片和你填写的内容。')
                record['location_data'] = {
                    'address': fields['location'] or ' / '.join(known) or None,
                    'datetime_str': next((item['datetime_str'] for item in record['photos'] if item.get('datetime_str')), None),
                    'date': fields['date'] or (dates[0] if len(dates) == 1 else ''), 'warnings': notes}
                _store().save_job(record)
            _update(record, 'writing', '正在撰写手帐，保留你提供的真实细节。')
            location_data = record['location_data']
            metadata_context = '\n'.join(
                f"照片{i + 1}：拍摄时间{item.get('datetime_str') or '未知'}，地点{item.get('address') or fields['location'] or '未确认'}"
                for i, item in enumerate(record['photos']))
            journal = generate_journal(record['image_description'] + '\n\n逐张照片线索：\n' + metadata_context,
                                       location_data['address'], [], location_data['datetime_str'],
                                       **{**fields, 'date': location_data['date']})
            if not journal.strip() or journal.startswith(('生成手账时出错：', '重新生成时出错：')):
                raise GenerationError('手帐生成暂时失败，请点击重试。', 'writing', True)
            filenames = [item['filename'] for item in record['photos']]
            record['result'] = {**fields, **location_data, 'journal': journal, 'sections': _parse_journal_sections(journal),
                                'style_name': STYLES[fields['style']]['name'], 'image_description': record['image_description'],
                                'image_filenames': filenames, 'image_urls': [f'/uploads/{filename}' for filename in filenames],
                                'image_metadata': [{key: item.get(key) for key in ('filename', 'datetime_str', 'address')} for item in record['photos']]}
            record.update(status='completed', stage='done', message='手帐已生成，可以编辑并保存成品。', retryable=False)
        except GenerationError as error:
            record.update(status='failed', stage=error.stage, error=error.message,
                          message='这一步暂时未完成，已有作品和成功步骤会保留。', retryable=error.retryable)
        except ValueError as error:
            record.update(status='failed', error=str(error), message='请重新选择照片。', retryable=False)
        except Exception:
            logger.error('Journal job failed unexpectedly', exc_info=False)
            record.update(status='failed', error='生成暂时失败，请稍后重试。', message='生成暂时中断。', retryable=True)
        _store().save_job(record)


def _dispatch(record):
    if app.config['JOBS_INLINE']:
        _run_job(record['job_id'], record['owner'])
    else:
        executor.submit(_run_job, record['job_id'], record['owner'])


def _new_job():
    fields, owner = _fields(request.form), _owner()
    photos = _save_uploaded_images(request.files.getlist('image'), owner)
    record = {'job_id': uuid.uuid4().hex, 'owner': owner, 'fields': fields, 'photos': photos,
              'status': 'queued', 'stage': 'upload', 'message': '照片已保存，准备生成。', 'retryable': False}
    if not _store().create_job(record):
        for item in photos:
            _store().remove_photo(item['filename'], owner)
        return None
    return record


@app.get('/')
def index():
    return render_template('index.html')


@app.get('/hall')
def hall_page():
    return render_template('hall.html')


@app.post('/api/hall/posts')
def hall_publish():
    key, fields = _hall_publication_fields()
    owner, hall = _owner(), _hall()
    fingerprint = payload_fingerprint(fields)
    existing = hall.preflight(owner, key, fingerprint)
    if existing:
        return jsonify(post=public_post(existing, owner)), 200
    paths = []
    for filename in fields['image_filenames']:
        photo = _store().photo(filename, owner)
        if not photo:
            raise HallError('有照片已过期或无法访问，请重新选择自己的作品。', 403)
        paths.append(photo['path'])
    try:
        png = render_journal_to_bytes(
            '', paths, style=fields['style'], scale=2, sections=fields['sections'],
            **{name: fields[name] for name in ('address', 'datetime_str', 'date', 'weather')},
        )
        record, created = hall.publish(owner, key, fingerprint, fields, png)
    except HallError:
        raise
    except Exception:
        logger.error('Public journal publication failed', exc_info=False)
        return jsonify(error='作品发布暂时失败，请稍后重试。'), 500
    return jsonify(post=public_post(record, owner)), 201 if created else 200


@app.get('/api/hall/posts')
def hall_posts():
    return jsonify(_hall().list_posts(_owner(), **_hall_pagination()))


@app.get('/api/hall/topics')
def hall_topics():
    return jsonify(topics=_hall().topics())


@app.get('/api/hall/posts/<post_id>')
def hall_post(post_id):
    record = _hall().post(post_id)
    if not record:
        raise HallError('这篇手帐不存在或已撤回。', 404)
    return jsonify(post=public_post(record, _owner()))


def _hall_image_response(post_id, thumbnail=False):
    path = _hall().media(post_id, thumbnail)
    if not path:
        raise HallError('这篇手帐不存在或已撤回。', 404)
    response = send_file(path, mimetype='image/jpeg' if thumbnail else 'image/png',
                         conditional=True, max_age=0,
                         download_name='journal-preview.jpg' if thumbnail else 'journal.png')
    response.headers['Cache-Control'] = 'no-store'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    return response


@app.get('/api/hall/posts/<post_id>/image')
def hall_image(post_id):
    return _hall_image_response(post_id)


@app.get('/api/hall/posts/<post_id>/thumbnail')
def hall_thumbnail(post_id):
    return _hall_image_response(post_id, thumbnail=True)


@app.post('/api/hall/posts/<post_id>/withdraw')
def hall_withdraw(post_id):
    _hall().withdraw(post_id, _owner())
    return jsonify(id=post_id, withdrawn=True)


@app.post('/api/jobs')
def create_job():
    try:
        record = _new_job()
    except ValueError as error:
        return jsonify(error=str(error)), 400
    if not record:
        return jsonify(error='已有任务正在生成，请稍后再试。'), 429
    _dispatch(record)
    return jsonify(_public_job(record)), 202


@app.get('/api/jobs/<job_id>')
def get_job(job_id):
    record = _store().job(job_id, _owner())
    if not record:
        return jsonify(error='任务不存在或已过期，请重新生成。'), 404
    return jsonify(_public_job(record))


@app.post('/api/jobs/<job_id>/retry')
def retry_job(job_id):
    record = _store().claim_retry(job_id, _owner())
    if not record:
        return jsonify(error='任务无法重试，可能正在生成或已过期。'), 409
    _dispatch(record)
    return jsonify(_public_job(record)), 202


@app.post('/api/generate')
def api_generate():
    try:
        record = _new_job()
    except ValueError as error:
        return jsonify(error=str(error)), 400
    if not record:
        return jsonify(error='已有任务正在生成，请稍后再试。'), 429
    _run_job(record['job_id'], record['owner'])
    completed = _store().job(record['job_id'], record['owner'])
    if completed['status'] != 'completed':
        return jsonify(_public_job(completed)), 502 if completed['retryable'] else 400
    return jsonify(completed['result'])


@app.post('/upload')
def upload():
    try:
        record = _new_job()
    except ValueError as error:
        return render_template('index.html', error=str(error)), 400
    if not record:
        return render_template('index.html', error='请等待当前任务完成。'), 429
    _run_job(record['job_id'], record['owner'])
    completed = _store().job(record['job_id'], record['owner'])
    if completed['status'] != 'completed':
        return render_template('index.html', error=completed['error']), 502
    return render_template('result.html', **completed['result'])


@app.post('/api/regenerate')
def api_regenerate():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify(error='请提供有效的请求内容。'), 400
    text, tone, style = (data.get(key, '') for key in ('original_text', 'tone', 'style'))
    style = style or 'xiaohongshu'
    if not isinstance(text, str) or not text.strip() or len(text) > MAX_TEXT:
        return jsonify(error='请输入有效的手帐内容，最多 12000 字。'), 400
    if not isinstance(tone, str) or tone not in TONES or not isinstance(style, str) or style not in STYLES:
        return jsonify(error='请选择支持的语气和风格。'), 400
    try:
        journal = regenerate_journal(text, tone, style)
        if not journal.strip() or journal.startswith('重新生成时出错：'):
            raise GenerationError('语气调整暂时失败，请稍后重试。', 'writing', True)
    except GenerationError as error:
        return jsonify(error=error.message, retryable=error.retryable), 502
    return jsonify(journal=journal, sections=_parse_journal_sections(journal), tone=tone, tone_label=TONES[tone]['label'])


@app.post('/api/export-image')
def api_export_image():
    text, style = request.form.get('journal_text', '').strip(), request.form.get('style', 'xiaohongshu').strip()
    sections = None
    if request.form.get('sections'):
        try:
            sections = json.loads(request.form['sections'])
        except (ValueError, TypeError):
            return jsonify(error='手帐内容格式不正确，请重新编辑。'), 400
        if (not isinstance(sections, dict)
                or not isinstance(sections.get('title'), str)
                or not isinstance(sections.get('body'), str)
                or not isinstance(sections.get('tags'), list)
                or any(not isinstance(tag, str) for tag in sections['tags'])
                or len(sections['tags']) > 100):
            return jsonify(error='标题、正文或标签格式不正确。'), 400
        sections = {key: sections[key] for key in ('title', 'body', 'tags')}
        content_length = len(sections['title']) + len(sections['body']) + sum(len(tag) for tag in sections['tags'])
        if content_length == 0 or content_length > MAX_TEXT:
            return jsonify(error='手帐内容不能为空，最多 12000 字。'), 400
    elif not text or len(text) > MAX_TEXT:
        return jsonify(error='手帐内容不能为空，最多 12000 字。'), 400
    if style not in STYLES:
        return jsonify(error='请选择支持的手帐风格。'), 400
    filenames = [value.strip() for value in request.form.get('image_filenames', '').split(',') if value.strip()]
    try:
        paths = _photo_paths(filenames, _owner())
        scale = int(request.form.get('scale', '2'))
        if scale not in (1, 2):
            raise ValueError('请选择普通或高清导出。')
        metadata = {key: request.form.get(key, '').strip() for key in ('address', 'datetime_str', 'date', 'weather')}
        if any(len(value) > 500 for value in metadata.values()):
            raise ValueError('日期、地点或天气内容过长。')
        content = render_journal_to_bytes(text, paths, style=style, scale=scale, sections=sections, **metadata)
    except ValueError as error:
        return jsonify(error=str(error)), 400
    except Exception:
        logger.error('Journal export failed', exc_info=False)
        return jsonify(error='长图生成失败，请稍后重试。'), 500
    return Response(content, mimetype='image/png', headers={
        'Content-Disposition': 'attachment; filename=travel_journal.png', 'Cache-Control': 'private, no-store'})


@app.get('/api/sample/<style>')
def sample(style):
    if style not in STYLES:
        return jsonify(error='未知手帐风格。'), 404
    from services.sample_service import sample_journal
    return Response(sample_journal(style), mimetype='image/png', headers={'Cache-Control': 'public, max-age=3600'})


@app.get('/api/styles')
def api_styles():
    return jsonify({key: {'name': item['name'], 'description': item['description']} for key, item in STYLES.items()})


@app.get('/api/tones')
def api_tones():
    return jsonify({key: item['label'] for key, item in TONES.items()})


@app.get('/uploads/<filename>')
def serve_upload(filename):
    photo = _store().photo(filename, _owner())
    if not photo:
        return jsonify(error='照片已过期或无法访问，请重新选择照片。'), 404
    response = send_file(photo['path'], mimetype='image/jpeg', conditional=True, max_age=0, download_name=filename)
    response.headers['Cache-Control'] = 'private, no-store'
    return response


if __name__ == '__main__':
    app.run(host=os.environ.get('JOURNAL_HOST', '127.0.0.1'), port=5001, debug=False)
