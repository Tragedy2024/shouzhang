"""核心函数单元测试：``app.py`` 的校验层与路由层。

被测单元
--------
纯函数（不需要请求上下文）
    ``allowed_file``        上传扩展名白名单
    ``_fields``             生成参数校验（风格、长度、日期）
    ``_public_job``         任务状态的对外白名单（绝不泄漏 owner 与照片记录）

依赖请求上下文的函数
    ``_hall_pagination``    分页 / 话题 / 搜索参数校验
    ``http_error``          HTTP 异常 → 统一文案（API 出 JSON，页面出 HTML）

路由
    ``/``、``/hall``、``/api/styles``、``/api/tones``、``/api/sample/<style>``
    ``POST /api/generate``、``/api/jobs``、``/api/regenerate``、``/api/export-image``
    ``/api/hall/*`` 的校验分支与完整发布→撤回闭环

打桩策略
--------
视觉、写作、改写、逆地理编码四个外部服务用 ``unittest.mock`` 替换
（它们各自的真实行为由 ``test_core_vision_service`` 等模块负责）。
文件系统用 ``tmp_path`` 隔离，测试不会碰到项目真实的 ``instance/``。
"""

import io
import json
import uuid
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from PIL import Image
from PIL.ExifTags import Base, GPS, IFD
from PIL.TiffImagePlugin import IFDRational
from werkzeug.exceptions import (
    BadRequest,
    InternalServerError,
    NotFound,
    RequestEntityTooLarge,
    TooManyRequests,
)

import app as project
from services.errors import GenerationError
from services.hall_service import HallError
from services.text_service import STYLES, TONES

PNG_MAGIC = b'\x89PNG\r\n\x1a\n'


# --------------------------------------------------------------------------- #
# 夹具与构造工具
# --------------------------------------------------------------------------- #

@pytest.fixture
def providers(monkeypatch):
    """替换四个外部服务。

    ``app.py`` 用的是 ``from services.x import y``，所以必须打在 ``app``
    这个命名空间上——打在被导入的模块里是不会生效的。
    """
    stubs = SimpleNamespace(
        vision=Mock(return_value='海面和一条船。'),
        writing=Mock(return_value='海边散步\n\n风吹过海面。\n\n#旅行 #海边'),
        rewriting=Mock(return_value='海风来信\n\n风吹过海面。\n\n#旅行'),
        geocode=Mock(return_value='海边'),
    )
    monkeypatch.setattr(project, 'analyze_images_batch', stubs.vision)
    monkeypatch.setattr(project, 'generate_journal', stubs.writing)
    monkeypatch.setattr(project, 'regenerate_journal', stubs.rewriting)
    monkeypatch.setattr(project, 'reverse_geocode', stubs.geocode)
    return stubs


@pytest.fixture
def client(tmp_path, monkeypatch, providers):
    """离线、隔离的 Flask 测试客户端（``JOBS_INLINE`` 让任务同步跑完）。"""
    monkeypatch.setitem(project.app.config, 'TESTING', True)
    monkeypatch.setitem(project.app.config, 'JOBS_INLINE', True)
    monkeypatch.setitem(project.app.config, 'UPLOAD_FOLDER', str(tmp_path / 'uploads'))
    monkeypatch.setitem(project.app.config, 'JOURNAL_DB_PATH', str(tmp_path / 'journal.sqlite3'))
    monkeypatch.setitem(project.app.config, 'HALL_MEDIA_FOLDER', str(tmp_path / 'hall-media'))
    with project.app.test_client() as test_client:
        yield test_client


def jpeg(size=(120, 80), color='#7799aa', fmt='JPEG'):
    """一张可以真的被流水线读进去的图片字节。"""
    buffer = io.BytesIO()
    Image.new('RGB', size, color).save(buffer, fmt)
    return buffer.getvalue()


def gps_jpeg(latitude, longitude, timestamp='2026:10:01 08:30:00'):
    """一张带真实 GPS 与拍摄时间 EXIF 的 JPEG 字节。

    EXIF 的度分秒是有理数，必须用 ``IFDRational``；直接塞 float 会让 Pillow
    在写 GPS IFD 时抛 ``TypeError``。
    """
    exif = Image.Exif()
    exif[IFD.GPSInfo] = {
        GPS.GPSLatitudeRef: 'N',
        GPS.GPSLatitude: tuple(IFDRational(value, 1) for value in (latitude, 0, 0)),
        GPS.GPSLongitudeRef: 'E',
        GPS.GPSLongitude: tuple(IFDRational(value, 1) for value in (longitude, 0, 0)),
    }
    exif[Base.DateTimeOriginal] = timestamp
    buffer = io.BytesIO()
    Image.new('RGB', (60, 40), '#7799aa').save(buffer, 'JPEG', exif=exif)
    return buffer.getvalue()


def upload_photo(client, name='coast.jpg'):
    """走一次完整生成，把上传成功后的照片文件名取出来。"""
    response = client.post('/api/jobs', data={'image': (io.BytesIO(jpeg()), name)})
    assert response.status_code == 202
    job = client.get('/api/jobs/' + response.get_json()['job_id']).get_json()
    assert job['status'] == 'completed'
    return job['result']['image_filenames']


def publish_form(filenames=(), **overrides):
    """一份合法的公开发布表单。"""
    form = {
        'public_confirm': 'true',
        'title': '海边散步',
        'caption': '旅行记录',
        'author_name': '作者',
        'style': 'film',
        'topics': json.dumps(['旅行'], ensure_ascii=False),
        'idempotency_key': str(uuid.uuid4()),
        'journal_text': '海边散步\n\n风吹过海面。\n\n#旅行',
        'image_filenames': ','.join(filenames),
    }
    form.update(overrides)
    return form


# --------------------------------------------------------------------------- #
# 纯函数：上传文件名
# --------------------------------------------------------------------------- #

class TestAllowedFile:
    """扩展名白名单。"""

    @pytest.mark.parametrize('name', [
        'coast.jpg', 'coast.JPG', 'coast.jpeg', 'coast.png', 'coast.WEBP',
        '照片.png', 'my.trip.2026.jpg',
    ])
    def test_allowed_file_accepts_supported_extensions(self, name):
        assert project.allowed_file(name)

    @pytest.mark.parametrize('name', [
        'coast.gif', 'coast.txt', 'coast', 'coast.', 'coast.jpg.exe', '', 'archive.tar.gz',
    ])
    def test_allowed_file_rejects_unsupported_names(self, name):
        assert not project.allowed_file(name)


# --------------------------------------------------------------------------- #
# 纯函数：生成参数校验
# --------------------------------------------------------------------------- #

class TestFields:
    """``_fields`` 只接受普通 dict，因此可以完全脱离请求上下文验证。"""

    def test_fields_defaults_to_xiaohongshu_style(self):
        assert project._fields({})['style'] == 'xiaohongshu'

    def test_fields_strips_surrounding_whitespace(self):
        assert project._fields({'location': '  西湖  '})['location'] == '西湖'

    def test_fields_only_returns_known_keys(self):
        assert set(project._fields({'evil': 'x'})) == \
            {'location', 'mood', 'feelings', 'style', 'date', 'weather'}

    def test_fields_rejects_an_unknown_style(self):
        with pytest.raises(ValueError, match='请选择支持的手帐风格。'):
            project._fields({'style': 'nope'})

    @pytest.mark.parametrize('style', sorted(STYLES))
    def test_fields_accepts_every_defined_style(self, style):
        assert project._fields({'style': style})['style'] == style

    @pytest.mark.parametrize('key,limit,value', [
        ('location', 200, 'x' * 200),
        ('mood', 100, 'x' * 100),
        ('feelings', 2000, 'x' * 2000),
        ('weather', 50, 'x' * 50),
        ('date', 10, '2026-10-01'),
    ])
    def test_fields_accepts_values_at_the_limit(self, key, limit, value):
        assert len(value) == limit
        assert project._fields({key: value})[key] == value

    @pytest.mark.parametrize('key,limit', [
        ('location', 200), ('mood', 100), ('feelings', 2000),
        ('weather', 50), ('date', 10),
    ])
    def test_fields_rejects_values_over_the_limit(self, key, limit):
        with pytest.raises(ValueError, match='补充内容过长，请适当缩短。'):
            project._fields({key: 'x' * (limit + 1)})

    def test_fields_accepts_a_valid_iso_date(self):
        assert project._fields({'date': '2026-10-01'})['date'] == '2026-10-01'

    @pytest.mark.parametrize('value', ['2026-02-30', '2026/10/01', '十月一日', '2026-13-01'])
    def test_fields_rejects_an_invalid_date(self, value):
        with pytest.raises(ValueError, match='请选择有效的旅行日期。'):
            project._fields({'date': value})


# --------------------------------------------------------------------------- #
# 纯函数：任务状态的对外模型
# --------------------------------------------------------------------------- #

class TestPublicJob:
    """任务状态白名单：``owner`` / ``fields`` / ``photos`` 都不能出去。"""

    RECORD = {'job_id': 'a' * 32, 'owner': 'secret-owner', 'status': 'queued',
              'stage': 'upload', 'message': '准备生成。', 'retryable': False,
              'fields': {'location': '私密地点'}, 'photos': [{'filename': 'x.jpg'}]}

    def test_public_job_exposes_only_the_whitelist(self):
        assert set(project._public_job(self.RECORD)) == \
            {'job_id', 'status', 'stage', 'message', 'retryable'}

    def test_public_job_never_leaks_private_fields(self):
        view = project._public_job(self.RECORD)

        for secret in ('owner', 'fields', 'photos'):
            assert secret not in view
        assert 'secret-owner' not in json.dumps(view)

    def test_public_job_omits_absent_keys_instead_of_nulling_them(self):
        # 尚未产生 result / error 时不能凭空补一个 None，前端会误判。
        assert 'result' not in project._public_job(self.RECORD)

    def test_public_job_passes_through_result_and_error_when_present(self):
        view = project._public_job({**self.RECORD, 'result': {'journal': 'x'}, 'error': 'y'})

        assert view['result'] == {'journal': 'x'} and view['error'] == 'y'


# --------------------------------------------------------------------------- #
# 请求上下文：分页参数
# --------------------------------------------------------------------------- #

def paginate(query=''):
    """在请求上下文里调用 ``_hall_pagination``。"""
    with project.app.test_request_context('/api/hall/posts' + query):
        return project._hall_pagination()


class TestHallPagination:
    """分页 / 话题 / 搜索参数校验。"""

    def test_hall_pagination_defaults(self):
        assert paginate() == {'page': 1, 'page_size': 12, 'topic': '',
                              'query': '', 'mine': False}

    def test_hall_pagination_reads_the_query_string(self):
        params = paginate('?page=3&page_size=24&q=海&mine=1')

        assert (params['page'], params['page_size'], params['query'], params['mine']) == \
            (3, 24, '海', True)

    def test_hall_pagination_normalizes_the_topic(self):
        assert paginate('?topic=%23%E6%97%85%E8%A1%8C')['topic'] == '旅行'

    @pytest.mark.parametrize('query', ['?page=abc', '?page=', '?page=1.5', '?page=-1'])
    def test_hall_pagination_rejects_non_decimal_numbers(self, query):
        with pytest.raises(Exception, match='分页参数不正确。'):
            paginate(query)

    def test_hall_pagination_rejects_an_over_long_number(self):
        with pytest.raises(Exception, match='分页参数不正确。'):
            paginate('?page=123456789')

    @pytest.mark.parametrize('query', ['?page=0', '?page=1000001', '?page_size=0', '?page_size=51'])
    def test_hall_pagination_rejects_out_of_range_numbers(self, query):
        with pytest.raises(Exception, match='分页参数超出允许范围。'):
            paginate(query)

    def test_hall_pagination_rejects_an_over_long_topic(self):
        with pytest.raises(Exception, match='话题或搜索内容过长。'):
            paginate('?topic=' + 'x' * 21)

    def test_hall_pagination_rejects_an_over_long_query(self):
        with pytest.raises(Exception, match='话题或搜索内容过长。'):
            paginate('?q=' + 'x' * 201)

    def test_hall_pagination_rejects_an_unknown_mine_flag(self):
        with pytest.raises(Exception, match='请选择有效的浏览范围。'):
            paginate('?mine=yes')


# --------------------------------------------------------------------------- #
# 请求上下文：HTTP 异常 → 统一文案
# --------------------------------------------------------------------------- #

def handle_http_error(exception, path):
    """在指定路径的请求上下文里调用错误处理器。"""
    with project.app.test_request_context(path):
        return project.http_error(exception)


class TestHttpError:
    """同一个异常，API 路径出 JSON，浏览器路径出页面。"""

    @pytest.mark.parametrize('exception,expected', [
        (BadRequest(), '请求内容不完整，请检查后重试。'),
        (NotFound(), '照片或任务已过期，请重新选择照片。'),
        (RequestEntityTooLarge(), '照片合计不能超过 50MB，每张不能超过 16MB。'),
        (TooManyRequests(), '已有任务正在生成，请稍后再试。'),
        (InternalServerError(), '请求失败，请稍后重试。'),
    ])
    def test_http_error_maps_status_codes_to_json(self, exception, expected):
        response, status = handle_http_error(exception, '/api/jobs')

        assert status == exception.code
        assert response.get_json()['error'] == expected

    def test_http_error_also_covers_upload_paths(self):
        response, status = handle_http_error(NotFound(), '/uploads/abc.jpg')

        assert status == 404 and response.get_json()['error'].startswith('照片或任务')

    def test_http_error_renders_html_for_browser_paths(self):
        body, status = handle_http_error(NotFound(), '/')

        assert status == 404
        assert isinstance(body, str) and body.lstrip().startswith('<')


# --------------------------------------------------------------------------- #
# 静态与只读路由
# --------------------------------------------------------------------------- #

class TestStaticRoutes:
    def test_index_renders_the_single_page_ui(self, client):
        response = client.get('/')

        assert response.status_code == 200 and response.mimetype == 'text/html'

    def test_hall_page_renders(self, client):
        assert client.get('/hall').status_code == 200

    def test_api_styles_lists_every_style(self, client):
        payload = client.get('/api/styles').get_json()

        assert set(payload) == set(STYLES)
        assert set(payload['film']) == {'name', 'description'}

    def test_api_tones_lists_every_tone_label(self, client):
        assert client.get('/api/tones').get_json() == \
            {key: item['label'] for key, item in TONES.items()}

    def test_sample_returns_a_png_for_a_known_style(self, client):
        response = client.get('/api/sample/muji')

        assert response.status_code == 200
        assert response.data[:8] == PNG_MAGIC

    def test_sample_rejects_an_unknown_style(self, client):
        response = client.get('/api/sample/不存在的风格')

        assert response.status_code == 404 and 'error' in response.get_json()

    def test_uploads_rejects_an_unregistered_photo(self, client):
        assert client.get('/uploads/' + 'a' * 32 + '.jpg').status_code == 404

    def test_unknown_path_returns_the_json_error_for_api_prefixes(self, client):
        response = client.get('/api/does-not-exist')

        assert response.status_code == 404 and 'error' in response.get_json()


# --------------------------------------------------------------------------- #
# 生成路由
# --------------------------------------------------------------------------- #

class TestUploadValidation:
    """上传校验：张数、扩展名、体积、像素与真实格式。"""

    def test_missing_image_is_rejected(self, client):
        response = client.post('/api/jobs', data={})

        assert response.status_code == 400
        assert response.get_json()['error'] == '请选择至少一张图片。'

    def test_too_many_photos_are_rejected(self, client):
        files = [(io.BytesIO(jpeg()), f'{index}.jpg') for index in range(project.MAX_PHOTOS + 1)]

        response = client.post('/api/jobs', data={'image': files})

        assert response.status_code == 400
        assert '最多上传 9 张' in response.get_json()['error']

    def test_unsupported_extension_is_rejected(self, client):
        response = client.post('/api/jobs', data={'image': (io.BytesIO(jpeg()), 'notes.txt')})

        assert response.status_code == 400
        assert 'JPG、PNG 或 WebP' in response.get_json()['error']

    def test_empty_file_is_rejected(self, client):
        response = client.post('/api/jobs', data={'image': (io.BytesIO(b''), 'empty.jpg')})

        assert response.status_code == 400
        assert '16MB' in response.get_json()['error']

    def test_extension_that_lies_about_the_format_is_rejected(self, client):
        # 扩展名说是 jpg，内容其实是 GIF —— 必须看真实格式，不能只看文件名。
        response = client.post('/api/jobs',
                               data={'image': (io.BytesIO(jpeg(fmt='GIF')), 'fake.jpg')})

        assert response.status_code == 400
        assert '格式与文件名不符' in response.get_json()['error']

    def test_a_broken_photo_rolls_back_the_whole_batch(self, client, tmp_path):
        files = [(io.BytesIO(jpeg()), 'good.jpg'), (io.BytesIO(b'not an image'), 'bad.jpg')]

        response = client.post('/api/jobs', data={'image': files})

        assert response.status_code == 400
        # 失败后不能留下"半个批次"的照片。
        assert not list((tmp_path / 'uploads').glob('*.jpg'))

    def test_oversized_dimensions_are_rejected(self, client):
        # 超过 3000 万像素的图先拦下，避免渲染时吃光内存。
        huge = jpeg(size=(6000, 5001), fmt='PNG')

        response = client.post('/api/jobs', data={'image': (io.BytesIO(huge), 'huge.png')})

        assert response.status_code == 400
        assert '分辨率过高' in response.get_json()['error']

    def test_invalid_generation_fields_are_rejected(self, client, providers):
        response = client.post('/api/jobs',
                               data={'image': (io.BytesIO(jpeg()), 'coast.jpg'), 'style': 'nope'})

        assert response.status_code == 400
        providers.vision.assert_not_called()

    def test_corrupt_photo_extension_is_rejected_by_allowed_file(self, client):
        response = client.post('/api/jobs', data={'image': (io.BytesIO(jpeg()), 'no-extension')})

        assert response.status_code == 400


class TestJobRoutes:
    """任务接口：202 提交、轮询、重试。"""

    def test_create_job_returns_a_public_job_and_completes_inline(self, client, providers):
        response = client.post('/api/jobs', data={'image': (io.BytesIO(jpeg()), 'coast.jpg')})

        assert response.status_code == 202
        payload = response.get_json()
        assert set(payload) <= {'job_id', 'status', 'stage', 'message', 'result',
                                'error', 'retryable'}
        assert 'owner' not in payload and 'photos' not in payload
        providers.vision.assert_called_once()

        job = client.get('/api/jobs/' + payload['job_id']).get_json()
        assert job['status'] == 'completed'
        assert job['result']['sections']['title'] == '海边散步'

    def test_get_job_rejects_an_unknown_identifier(self, client):
        response = client.get('/api/jobs/' + 'f' * 32)

        assert response.status_code == 404 and 'error' in response.get_json()

    def test_retry_rejects_a_completed_job(self, client):
        response = client.post('/api/jobs', data={'image': (io.BytesIO(jpeg()), 'coast.jpg')})
        job_id = response.get_json()['job_id']

        retry = client.post(f'/api/jobs/{job_id}/retry')

        assert retry.status_code == 409

    def test_retry_requeues_a_retryable_failure(self, client, providers):
        providers.writing.side_effect = GenerationError('写作暂时失败', 'writing')
        response = client.post('/api/jobs', data={'image': (io.BytesIO(jpeg()), 'coast.jpg')})
        job_id = response.get_json()['job_id']
        failed = client.get('/api/jobs/' + job_id).get_json()
        assert failed['status'] == 'failed' and failed['retryable'] is True

        providers.writing.side_effect = None
        assert client.post(f'/api/jobs/{job_id}/retry').status_code == 202

        assert client.get('/api/jobs/' + job_id).get_json()['status'] == 'completed'
        # 重试不重复调用视觉模型：已完成的步骤要保留。
        assert providers.vision.call_count == 1


class TestApiGenerate:
    """``POST /api/generate``：一次性返回结果的旧接口。"""

    def test_api_generate_returns_the_completed_result(self, client, providers):
        response = client.post('/api/generate', data={
            'image': (io.BytesIO(jpeg()), 'coast.jpg'), 'location': '用户地点',
            'style': 'film', 'date': '2026-10-01'})

        assert response.status_code == 200
        payload = response.get_json()
        assert payload['sections']['title'] == '海边散步'
        assert payload['address'] == '用户地点'
        assert payload['style'] == 'film'

    def test_api_generate_reports_a_writing_failure_as_bad_gateway(self, client, providers):
        providers.writing.side_effect = GenerationError('写作暂时失败', 'writing', True)

        response = client.post('/api/generate', data={'image': (io.BytesIO(jpeg()), 'c.jpg')})

        assert response.status_code == 502
        assert response.get_json()['retryable'] is True

    def test_api_generate_reports_a_permanent_failure_as_bad_request(self, client, providers):
        providers.writing.side_effect = GenerationError('照片无法读取', 'vision', False)

        response = client.post('/api/generate', data={'image': (io.BytesIO(jpeg()), 'c.jpg')})

        assert response.status_code == 400

    def test_api_generate_rejects_invalid_fields(self, client):
        response = client.post('/api/generate', data={
            'image': (io.BytesIO(jpeg()), 'c.jpg'), 'mood': 'x' * 101})

        assert response.status_code == 400
        assert '补充内容过长' in response.get_json()['error']


class TestRegenerate:
    """``POST /api/regenerate``：语气改写接口。"""

    def test_regenerate_returns_the_rewritten_journal(self, client, providers):
        response = client.post('/api/regenerate', json={
            'original_text': '原标题\n\n正文', 'tone': 'literary', 'style': 'film'})

        assert response.status_code == 200
        payload = response.get_json()
        assert payload['journal'] == '海风来信\n\n风吹过海面。\n\n#旅行'
        assert payload['sections']['title'] == '海风来信'
        assert payload['tone_label'] == TONES['literary']['label']

    @pytest.mark.parametrize('body', [[], 'text', 42, None])
    def test_regenerate_rejects_a_non_object_body(self, client, body):
        response = client.post('/api/regenerate', json=body)

        assert response.status_code == 400
        assert response.get_json()['error'] == '请提供有效的请求内容。'

    @pytest.mark.parametrize('text', ['', '   ', None, 'x' * (project.MAX_TEXT + 1)])
    def test_regenerate_rejects_unusable_text(self, client, text):
        response = client.post('/api/regenerate',
                               json={'original_text': text, 'tone': 'literary'})

        assert response.status_code == 400
        assert '请输入有效的手帐内容' in response.get_json()['error']

    @pytest.mark.parametrize('field,value', [
        ('tone', '不存在的语气'),
        ('style', '不存在的风格'),
    ])
    def test_regenerate_rejects_unknown_tone_or_style(self, client, field, value):
        body = {'original_text': '原标题\n\n正文', 'tone': 'literary', 'style': 'film'}
        body[field] = value

        response = client.post('/api/regenerate', json=body)

        assert response.status_code == 400
        assert response.get_json()['error'] == '请选择支持的语气和风格。'

    def test_regenerate_reports_a_provider_failure(self, client, providers):
        providers.rewriting.side_effect = GenerationError('语气调整暂时失败', 'writing', True)

        response = client.post('/api/regenerate',
                               json={'original_text': '原标题\n\n正文', 'tone': 'literary'})

        assert response.status_code == 502
        assert response.get_json()['retryable'] is True


class TestExportImage:
    """``POST /api/export-image``：长图导出的全部校验分支。"""

    def export(self, client, **form):
        return client.post('/api/export-image', data=form)

    def test_export_returns_a_png(self, client):
        response = self.export(client, journal_text='标题\n\n正文\n\n#旅行', style='muji')

        assert response.status_code == 200 and response.data[:8] == PNG_MAGIC
        assert 'attachment' in response.headers['Content-Disposition']

    @pytest.mark.parametrize('text', ['', '   ', 'x' * (project.MAX_TEXT + 1)])
    def test_export_rejects_unusable_text(self, client, text):
        response = self.export(client, journal_text=text)

        assert response.status_code == 400
        assert '手帐内容不能为空' in response.get_json()['error']

    def test_export_rejects_an_unknown_style(self, client):
        response = self.export(client, journal_text='标题\n正文', style='nope')

        assert response.status_code == 400
        assert response.get_json()['error'] == '请选择支持的手帐风格。'

    @pytest.mark.parametrize('scale', ['0', '3', '4', '100'])
    def test_export_rejects_an_out_of_range_scale(self, client, scale):
        response = self.export(client, journal_text='标题\n正文', scale=scale)

        assert response.status_code == 400

    def test_export_rejects_a_non_numeric_scale(self, client):
        response = self.export(client, journal_text='标题\n正文', scale='高清')

        assert response.status_code == 400 and 'error' in response.get_json()

    def test_export_rejects_unparseable_sections(self, client):
        response = self.export(client, sections='{不是 JSON}', style='muji')

        assert response.status_code == 400
        assert response.get_json()['error'] == '手帐内容格式不正确，请重新编辑。'

    @pytest.mark.parametrize('sections', [
        '[]',
        json.dumps({'title': 1, 'body': '正文', 'tags': []}),
        json.dumps({'title': '标题', 'body': None, 'tags': []}),
        json.dumps({'title': '标题', 'body': '正文', 'tags': 'x'}),
        json.dumps({'title': '标题', 'body': '正文', 'tags': [1]}),
        json.dumps({'title': '标题', 'body': '正文', 'tags': ['x'] * 101}),
    ])
    def test_export_rejects_malformed_sections(self, client, sections):
        response = self.export(client, sections=sections, style='muji')

        assert response.status_code == 400
        assert response.get_json()['error'] == '标题、正文或标签格式不正确。'

    def test_export_rejects_empty_sections(self, client):
        empty = json.dumps({'title': '', 'body': '', 'tags': []})

        response = self.export(client, sections=empty, style='muji')

        assert response.status_code == 400
        assert '手帐内容不能为空' in response.get_json()['error']

    def test_export_rejects_over_long_metadata(self, client):
        response = self.export(client, journal_text='标题\n正文', address='x' * 501)

        assert response.status_code == 400
        assert response.get_json()['error'] == '日期、地点或天气内容过长。'

    def test_export_accepts_a_valid_sections_payload(self, client):
        sections = json.dumps({'title': '标题', 'body': '正文', 'tags': ['旅行']},
                              ensure_ascii=False)

        response = self.export(client, sections=sections, style='film', scale='1')

        assert response.status_code == 200 and response.data[:8] == PNG_MAGIC

    def test_export_uses_the_photos_owned_by_this_session(self, client):
        filenames = upload_photo(client)

        response = self.export(client, journal_text='标题\n正文', scale='1',
                               image_filenames=','.join(filenames))

        assert response.status_code == 200 and response.data[:8] == PNG_MAGIC

    def test_export_rejects_photos_owned_by_someone_else(self, client):
        filenames = upload_photo(client)
        with project.app.test_client() as stranger:
            stranger.get('/')          # 建立另一个浏览器身份
            response = stranger.post('/api/export-image', data={
                'journal_text': '标题\n正文', 'image_filenames': ','.join(filenames)})

        assert response.status_code == 400

    def test_export_rejects_more_photos_than_allowed(self, client):
        response = self.export(client, journal_text='标题\n正文',
                               image_filenames=','.join(['a' * 32 + '.jpg'] * (project.MAX_PHOTOS + 1)))

        assert response.status_code == 400
        assert '最多使用 9 张照片' in response.get_json()['error']


# --------------------------------------------------------------------------- #
# 大厅路由
# --------------------------------------------------------------------------- #

class TestHallRoutes:
    """``/api/hall/*``：只读接口 + 发布 → 浏览 → 撤回闭环。"""

    def test_hall_posts_returns_an_empty_feed(self, client):
        payload = client.get('/api/hall/posts').get_json()

        assert payload['total'] == 0 and payload['posts'] == []
        assert payload['page'] == 1 and payload['has_more'] is False

    def test_hall_posts_reports_pagination_errors_as_json(self, client):
        response = client.get('/api/hall/posts?page=0')

        assert response.status_code == 400
        assert response.get_json()['error'] == '分页参数超出允许范围。'

    def test_hall_post_rejects_an_unknown_identifier(self, client):
        response = client.get('/api/hall/posts/' + 'f' * 32)

        assert response.status_code == 404 and 'error' in response.get_json()

    def test_hall_topics_is_empty_before_anything_is_published(self, client):
        assert client.get('/api/hall/topics').get_json() == {'topics': []}

    def test_hall_image_returns_not_found_for_an_unknown_post(self, client):
        assert client.get('/api/hall/posts/' + 'f' * 32 + '/image').status_code == 404
        assert client.get('/api/hall/posts/' + 'f' * 32 + '/thumbnail').status_code == 404


class TestHallPublishFlow:
    """公开发布的完整闭环，以及它的每一条前置校验。"""

    def test_publish_requires_an_explicit_confirmation(self, client):
        response = client.post('/api/hall/posts', data=publish_form(public_confirm='false'))

        assert response.status_code == 400
        assert '请先确认' in response.get_json()['error']

    def test_publish_rejects_a_separate_public_image_upload(self, client):
        response = client.post('/api/hall/posts',
                               data={**publish_form(), 'image': (io.BytesIO(jpeg()), 'x.jpg')})

        assert response.status_code == 400
        assert '不要另行上传公开图片' in response.get_json()['error']

    @pytest.mark.parametrize('field,value', [
        ('title', ''), ('title', 'x' * 101),
        ('author_name', ''), ('author_name', 'x' * 31),
        ('caption', 'x' * 2001),
    ])
    def test_publish_enforces_text_limits(self, client, field, value):
        response = client.post('/api/hall/posts', data=publish_form(**{field: value}))

        assert response.status_code == 400

    @pytest.mark.parametrize('key', ['', 'not-a-uuid', 'x' * 37])
    def test_publish_rejects_an_invalid_idempotency_key(self, client, key):
        response = client.post('/api/hall/posts', data=publish_form(idempotency_key=key))

        assert response.status_code == 400
        assert '发布标识无效' in response.get_json()['error']

    def test_publish_rejects_unparseable_topics(self, client):
        response = client.post('/api/hall/posts', data=publish_form(topics='{不是 JSON}'))

        assert response.status_code == 400
        assert '话题格式不正确' in response.get_json()['error']

    @pytest.mark.parametrize('topics', [
        json.dumps(['1', '2', '3', '4', '5', '6']),      # 超过 5 个
        json.dumps(['x' * 21]),                          # 单个话题超过 20 字
        json.dumps(['']),                                # 空话题
        json.dumps([1]),                                 # 非文本
        json.dumps({'不是': '列表'}),
    ])
    def test_publish_rejects_malformed_topics(self, client, topics):
        response = client.post('/api/hall/posts', data=publish_form(topics=topics))

        assert response.status_code == 400

    def test_publish_rejects_an_unparseable_sections_field(self, client):
        response = client.post('/api/hall/posts',
                               data=publish_form(sections='{不是 JSON}'))

        assert response.status_code == 400
        assert '手帐内容格式不正确' in response.get_json()['error']

    @pytest.mark.parametrize('sections', [
        '[]',
        json.dumps({'title': 1, 'body': '正文', 'tags': []}),
        json.dumps({'title': '标题', 'body': '正文', 'tags': [1]}),
        json.dumps({'title': '标题', 'body': '正文', 'tags': ['x'] * 101}),
    ])
    def test_publish_rejects_malformed_sections(self, client, sections):
        response = client.post('/api/hall/posts', data=publish_form(sections=sections))

        assert response.status_code == 400
        assert '格式不正确' in response.get_json()['error']

    def test_publish_rejects_an_empty_journal(self, client):
        response = client.post('/api/hall/posts',
                               data=publish_form(journal_text='   '))

        assert response.status_code == 400
        assert '手帐内容不能为空' in response.get_json()['error']

    def test_publish_rejects_a_pathological_line_count(self, client):
        # 一行一个字的排版会在渲染时生成巨量文本块，必须先拒绝。
        response = client.post('/api/hall/posts',
                               data=publish_form(journal_text='\n'.join(['字'] * 500)))

        assert response.status_code == 400
        assert '分行过多' in response.get_json()['error']

    def test_publish_rejects_an_unknown_style(self, client):
        response = client.post('/api/hall/posts', data=publish_form(style='nope'))

        assert response.status_code == 400
        assert response.get_json()['error'] == '请选择支持的手帐风格。'

    @pytest.mark.parametrize('field,value', [
        ('address', 'x' * 501), ('datetime_str', 'x' * 101),
        ('date', 'x' * 11), ('weather', 'x' * 51),
    ])
    def test_publish_rejects_over_long_metadata(self, client, field, value):
        response = client.post('/api/hall/posts', data=publish_form(**{field: value}))

        assert response.status_code == 400
        assert response.get_json()['error'] == '日期、地点或天气内容过长。'

    def test_publish_rejects_an_invalid_travel_date(self, client):
        response = client.post('/api/hall/posts', data=publish_form(date='2026-02-30'))

        assert response.status_code == 400
        assert response.get_json()['error'] == '请选择有效的旅行日期。'

    def test_publish_rejects_an_over_long_photo_list(self, client):
        response = client.post('/api/hall/posts',
                               data=publish_form(image_filenames='a' * 501))

        assert response.status_code == 400
        assert response.get_json()['error'] == '照片信息不正确，请重新选择作品。'

    def test_publish_rejects_oversized_editor_sections(self, client):
        # 编辑区的三段内容加起来超过 12000 字也必须拒掉，否则渲染会吃光内存。
        sections = json.dumps({'title': '标' * 100, 'body': '文' * (project.MAX_TEXT + 100),
                               'tags': []}, ensure_ascii=False)

        response = client.post('/api/hall/posts', data=publish_form(sections=sections))

        assert response.status_code == 400
        assert '手帐内容不能为空，最多 12000 字。' in response.get_json()['error']

    def test_publish_rejects_a_malformed_photo_name(self, client):
        # 文件名连白名单都过不了 —— 属于请求本身不合法，400。
        response = client.post('/api/hall/posts',
                               data=publish_form(image_filenames='not-a-hash.jpg'))

        assert response.status_code == 400
        assert '最多使用 9 张有效照片' in response.get_json()['error']

    def test_publish_rejects_unregistered_photos(self, client):
        # 名字合法但从未登记（或属于别人）：是权限问题，403。
        response = client.post('/api/hall/posts',
                               data=publish_form(image_filenames='a' * 32 + '.jpg'))

        assert response.status_code == 403
        assert '已过期或无法访问' in response.get_json()['error']

    def test_publish_rejects_photos_that_expired(self, client):
        filenames = upload_photo(client)
        store = project._store()
        for name in filenames:
            store.remove_photo(name, project._owner())

        response = client.post('/api/hall/posts', data=publish_form(filenames))

        assert response.status_code == 403
        assert '已过期' in response.get_json()['error']

    def test_publish_then_browse_then_withdraw(self, client):
        filenames = upload_photo(client)
        form = publish_form(filenames)

        created = client.post('/api/hall/posts', data=form)
        assert created.status_code == 201
        post = created.get_json()['post']
        assert post['title'] == '海边散步' and post['is_owner'] is True
        assert post['topics'] == ['旅行']

        # 同一个 idempotency_key 重发：返回原帖而不是新建。
        repeated = client.post('/api/hall/posts', data=form)
        assert repeated.status_code == 200
        assert repeated.get_json()['post']['id'] == post['id']

        feed = client.get('/api/hall/posts').get_json()
        assert feed['total'] == 1 and feed['posts'][0]['id'] == post['id']
        assert client.get('/api/hall/topics').get_json()['topics'] == [{'name': '旅行', 'count': 1}]

        detail = client.get('/api/hall/posts/' + post['id'])
        assert detail.status_code == 200 and detail.get_json()['post']['title'] == '海边散步'

        image = client.get('/api/hall/posts/' + post['id'] + '/image')
        assert image.status_code == 200 and image.data[:8] == PNG_MAGIC
        assert image.headers['Cache-Control'] == 'no-store'

        thumbnail = client.get('/api/hall/posts/' + post['id'] + '/thumbnail')
        assert thumbnail.status_code == 200 and thumbnail.mimetype == 'image/jpeg'

        withdrawn = client.post('/api/hall/posts/' + post['id'] + '/withdraw')
        assert withdrawn.status_code == 200 and withdrawn.get_json()['withdrawn'] is True
        assert client.get('/api/hall/posts/' + post['id']).status_code == 404

    def test_publish_accepts_editor_sections_without_raw_text(self, client):
        # 前端在编辑区改过正文后只发 sections；此时 journal_text 可以为空，
        # 服务端必须走 sections 分支而不是当成"内容为空"拒掉。
        sections = json.dumps({'title': '编辑后的标题', 'body': '编辑后的正文',
                               'tags': ['#编辑']}, ensure_ascii=False)

        created = client.post('/api/hall/posts',
                              data=publish_form(journal_text='', sections=sections))

        assert created.status_code == 201

    def test_publish_renders_the_editor_sections_into_the_image(self, client):
        # 发布说明（title 字段）与作品标题（sections.title）是两回事，
        # 后者只体现在渲染出来的长图上，所以用图片字节来验证。
        filenames = upload_photo(client)
        edited = json.dumps({'title': '完全不同的标题', 'body': '完全不同的正文',
                             'tags': ['#编辑']}, ensure_ascii=False)

        first = client.post('/api/hall/posts', data=publish_form(filenames))
        second = client.post('/api/hall/posts',
                             data=publish_form(filenames, sections=edited))
        assert (first.status_code, second.status_code) == (201, 201)

        original = client.get('/api/hall/posts/' + first.get_json()['post']['id'] + '/image')
        modified = client.get('/api/hall/posts/' + second.get_json()['post']['id'] + '/image')

        assert original.data[:8] == PNG_MAGIC
        assert modified.data != original.data

    def test_another_identity_cannot_withdraw_someone_elses_post(self, client):
        filenames = upload_photo(client)
        post = client.post('/api/hall/posts', data=publish_form(filenames)).get_json()['post']

        with project.app.test_client() as stranger:
            stranger.get('/')          # 建立另一个浏览器身份
            response = stranger.post('/api/hall/posts/' + post['id'] + '/withdraw')

        assert response.status_code == 403

    def test_publish_reports_an_unexpected_render_failure(self, client, monkeypatch):
        # 渲染炸了要变成 500，不能把堆栈或半张图交出去。
        monkeypatch.setattr(project, 'render_journal_to_bytes',
                            Mock(side_effect=RuntimeError('画布炸了')))

        response = client.post('/api/hall/posts', data=publish_form())

        assert response.status_code == 500
        assert response.get_json()['error'] == '作品发布暂时失败，请稍后重试。'

    def test_publish_lets_a_hall_error_through_untouched(self, client, monkeypatch):
        # 业务错误（如配额用尽）要原样冒泡到 hall_error 处理器，
        # 不能被宽泛的 except Exception 降级成一句"发布失败"。
        monkeypatch.setattr(project, 'render_journal_to_bytes',
                            Mock(side_effect=HallError('今天发布得太频繁了。', 429)))

        response = client.post('/api/hall/posts', data=publish_form())

        assert response.status_code == 429
        assert response.get_json()['error'] == '今天发布得太频繁了。'


# --------------------------------------------------------------------------- #
# 会话密钥
# --------------------------------------------------------------------------- #

class TestSessionKey:
    """会话密钥来源：环境变量优先，其次落盘持久化。"""

    def test_session_key_prefers_the_environment_variable(self, monkeypatch):
        monkeypatch.setenv('JOURNAL_SECRET_KEY', 'unit-test-secret')

        assert project._session_key() == 'unit-test-secret'

    def test_session_key_persists_a_generated_key(self, tmp_path, monkeypatch):
        # 没有环境变量时自己生成一个并写盘：重启后签名密钥不能变，
        # 否则所有用户会话会被静默清空。
        monkeypatch.delenv('JOURNAL_SECRET_KEY', raising=False)
        monkeypatch.setattr(project, 'BASE_DIR', tmp_path)

        first = project._session_key()
        second = project._session_key()

        assert first == second and len(first) == 64
        stored = (tmp_path / 'instance' / '.session-key').read_text(encoding='utf-8').strip()
        assert stored == first


# --------------------------------------------------------------------------- #
# 上传落盘与回滚
# --------------------------------------------------------------------------- #

class TestUploadPersistence:
    """上传落盘：透明通道处理，以及登记失败时的整批回滚。"""

    def test_transparent_png_is_flattened_and_accepted(self, client):
        # 带透明通道的截图很常见；存成 JPEG 前必须先铺白底，否则会变全黑。
        buffer = io.BytesIO()
        Image.new('RGBA', (40, 40), (0, 0, 0, 0)).save(buffer, 'PNG')

        response = client.post('/api/jobs',
                               data={'image': (io.BytesIO(buffer.getvalue()), 'shot.png')})

        assert response.status_code == 202

    def test_registry_failure_removes_the_written_file(self, client, tmp_path, monkeypatch):
        # 文件已落盘但登记失败时，不能留下一个数据库里没有的孤儿文件。
        monkeypatch.setattr(project._store(), 'add_photo',
                            Mock(side_effect=RuntimeError('disk full')))

        with pytest.raises(RuntimeError):
            client.post('/api/jobs', data={'image': (io.BytesIO(jpeg()), 'coast.jpg')})

        assert not list((tmp_path / 'uploads').glob('*.jpg'))

    def test_a_failure_on_a_later_photo_rolls_back_the_earlier_ones(self, client, tmp_path,
                                                                    monkeypatch):
        # 第一张成功、第二张失败：已登记的那张也必须撤销，保持批次原子性。
        # 第一次调用放行到真实的 add_photo（真的写进数据库），第二次才炸，
        # 否则"回滚"无从谈起——数据库里根本没有可撤销的记录。
        store, calls = project._store(), {'count': 0}
        register = store.add_photo

        def flaky(filename, owner, metadata):
            calls['count'] += 1
            if calls['count'] == 2:
                raise RuntimeError('disk full')
            return register(filename, owner, metadata)

        monkeypatch.setattr(store, 'add_photo', flaky)
        files = [(io.BytesIO(jpeg()), 'first.jpg'), (io.BytesIO(jpeg()), 'second.jpg')]

        with pytest.raises(RuntimeError):
            client.post('/api/jobs', data={'image': files})

        assert not list((tmp_path / 'uploads').glob('*.jpg'))


# --------------------------------------------------------------------------- #
# 任务失败路径与并发闸门
# --------------------------------------------------------------------------- #

class TestJobFailurePaths:
    """任务执行中的每条失败分支都必须落到一个可重试 / 不可重试的终态。"""

    def test_an_unknown_job_identifier_is_a_no_op(self, client):
        # 后台线程可能拿到一个已被清理的任务；这里必须安静返回而不是抛异常。
        project._run_job('f' * 32, 'nobody')

        assert project._store().job('f' * 32, 'nobody') is None

    def test_an_empty_vision_description_fails_the_job(self, client, providers):
        providers.vision.return_value = '   '

        response = client.post('/api/jobs', data={'image': (io.BytesIO(jpeg()), 'coast.jpg')})
        job = client.get('/api/jobs/' + response.get_json()['job_id']).get_json()

        assert job['status'] == 'failed' and job['stage'] == 'vision'
        assert job['retryable'] is True
        providers.writing.assert_not_called()

    def test_an_empty_journal_fails_the_job(self, client, providers):
        providers.writing.return_value = '  '

        response = client.post('/api/jobs', data={'image': (io.BytesIO(jpeg()), 'coast.jpg')})
        job = client.get('/api/jobs/' + response.get_json()['job_id']).get_json()

        assert job['status'] == 'failed' and job['stage'] == 'writing'
        assert job['retryable'] is True

    def test_a_value_error_marks_the_job_as_permanently_failed(self, client, providers):
        providers.writing.side_effect = ValueError('照片已过期')

        response = client.post('/api/jobs', data={'image': (io.BytesIO(jpeg()), 'coast.jpg')})
        job = client.get('/api/jobs/' + response.get_json()['job_id']).get_json()

        assert (job['status'], job['retryable']) == ('failed', False)
        assert job['message'] == '请重新选择照片。'

    def test_an_unexpected_error_marks_the_job_as_retryable(self, client, providers):
        providers.writing.side_effect = RuntimeError('意料之外')

        response = client.post('/api/jobs', data={'image': (io.BytesIO(jpeg()), 'coast.jpg')})
        job = client.get('/api/jobs/' + response.get_json()['job_id']).get_json()

        assert (job['status'], job['retryable']) == ('failed', True)
        assert job['message'] == '生成暂时中断。'


class TestFullQueue:
    """并发闸门已满：三个提交入口都要给出 429，并且不留垃圾文件。"""

    @pytest.fixture
    def exhausted(self, monkeypatch):
        """模拟并发闸门已满：``create_job`` 一律返回 None。"""
        monkeypatch.setattr(project._store(), 'create_job', Mock(return_value=None))

    def test_jobs_endpoint_reports_a_full_queue(self, client, exhausted):
        response = client.post('/api/jobs', data={'image': (io.BytesIO(jpeg()), 'coast.jpg')})

        assert response.status_code == 429
        assert response.get_json()['error'] == '已有任务正在生成，请稍后再试。'

    def test_generate_endpoint_reports_a_full_queue(self, client, exhausted):
        response = client.post('/api/generate', data={'image': (io.BytesIO(jpeg()), 'c.jpg')})

        assert response.status_code == 429

    def test_a_rejected_job_discards_its_photos(self, client, exhausted, tmp_path):
        # 排队被拒时，刚存进去的照片不能留在磁盘上占空间。
        client.post('/api/jobs', data={'image': (io.BytesIO(jpeg()), 'coast.jpg')})

        assert not list((tmp_path / 'uploads').glob('*.jpg'))


class TestLocationCollection:
    """定位线索的收集：同坐标只查一次，冲突与失败都要提醒用户确认。"""

    def test_photos_with_the_same_gps_share_a_single_lookup(self, client, providers):
        # 同一次旅行拍的照片坐标几乎一样，逐张调用地图接口既慢又费额度。
        files = [(io.BytesIO(gps_jpeg(30.5, 120.25)), f'coast-{index}.jpg')
                 for index in range(2)]

        response = client.post('/api/jobs', data={'image': files})

        assert response.status_code == 202
        assert providers.geocode.call_count == 1

    def test_photos_from_different_places_ask_for_confirmation(self, client, providers):
        providers.geocode.side_effect = ['北京', '杭州']
        files = [(io.BytesIO(gps_jpeg(39.9, 116.4)), 'north.jpg'),
                 (io.BytesIO(gps_jpeg(30.2, 120.1)), 'south.jpg')]

        job = client.post('/api/jobs', data={'image': files}).get_json()
        result = client.get('/api/jobs/' + job['job_id']).get_json()['result']

        assert providers.geocode.call_count == 2
        assert '照片包含多个拍摄地点，请确认手帐地点。' in result['warnings']

    def test_photos_from_different_dates_ask_for_confirmation(self, client, providers):
        files = [(io.BytesIO(gps_jpeg(30.5, 120.25, '2026:10:01 08:30:00')), 'day1.jpg'),
                 (io.BytesIO(gps_jpeg(30.5, 120.25, '2026:10:05 09:00:00')), 'day2.jpg')]

        job = client.post('/api/jobs', data={'image': files}).get_json()
        result = client.get('/api/jobs/' + job['job_id']).get_json()['result']

        assert '照片来自不同日期，请在编辑区确认旅行日期。' in result['warnings']

    def test_an_unavailable_geocoder_asks_the_user_to_fill_it_in(self, client, providers):
        providers.geocode.return_value = None

        job = client.post('/api/jobs',
                          data={'image': (io.BytesIO(gps_jpeg(30.5, 120.25)), 'coast.jpg')}
                          ).get_json()
        result = client.get('/api/jobs/' + job['job_id']).get_json()['result']

        assert '自动定位暂时不可用，可以手动补充地点。' in result['warnings']
        assert result['address'] is None


class TestBackgroundDispatch:
    """``JOBS_INLINE = False`` 时任务应交给线程池，接口立刻返回排队中。"""

    def test_background_mode_hands_the_job_to_the_executor(self, client, monkeypatch):
        submitted = []
        monkeypatch.setitem(project.app.config, 'JOBS_INLINE', False)
        monkeypatch.setattr(project, 'executor', SimpleNamespace(
            submit=lambda function, *arguments: submitted.append((function, arguments))))

        response = client.post('/api/jobs', data={'image': (io.BytesIO(jpeg()), 'coast.jpg')})

        assert response.status_code == 202
        assert response.get_json()['status'] == 'queued'
        # 不在请求线程里跑生成，接口才能在长任务下保持响应。
        assert len(submitted) == 1 and submitted[0][0] is project._run_job


class TestLegacyUploadRoute:
    """``POST /upload``：无 JavaScript 时的服务端渲染兜底。"""

    def test_upload_renders_the_result_page(self, client):
        response = client.post('/upload', data={'image': (io.BytesIO(jpeg()), 'coast.jpg')})

        assert response.status_code == 200 and response.mimetype == 'text/html'
        assert '海边散步' in response.get_data(as_text=True)

    def test_upload_renders_the_error_on_the_index_page(self, client):
        # 注意：``index.html`` 目前只暴露一个由脚本填充的 #errorMsg 节点，
        # 模板并不渲染 error 变量，所以这里只能断言"回到首页并给出 400"。
        response = client.post('/upload', data={'image': (io.BytesIO(jpeg()), 'notes.txt')})

        assert response.status_code == 400 and response.mimetype == 'text/html'

    def test_upload_reports_a_full_queue(self, client, monkeypatch):
        monkeypatch.setattr(project._store(), 'create_job', Mock(return_value=None))

        response = client.post('/upload', data={'image': (io.BytesIO(jpeg()), 'coast.jpg')})

        assert response.status_code == 429 and response.mimetype == 'text/html'

    def test_upload_reports_a_failed_generation(self, client, providers):
        providers.writing.side_effect = GenerationError('写作暂时失败', 'writing', True)

        response = client.post('/upload', data={'image': (io.BytesIO(jpeg()), 'coast.jpg')})

        assert response.status_code == 502 and response.mimetype == 'text/html'


# --------------------------------------------------------------------------- #
# 其余失败出口
# --------------------------------------------------------------------------- #

class TestRemainingFailurePaths:
    """改写返回空白、导出渲染崩溃、私有照片读取。"""

    def test_regenerate_fails_when_the_provider_returns_nothing(self, client, providers):
        # 改写拿到空白不是"成功"，不能把空内容写回编辑区覆盖掉用户的原稿。
        providers.rewriting.return_value = '   '

        response = client.post('/api/regenerate',
                               json={'original_text': '原标题\n\n正文', 'tone': 'literary'})

        assert response.status_code == 502
        assert response.get_json()['error'] == '语气调整暂时失败，请稍后重试。'

    def test_export_reports_an_unexpected_render_failure(self, client, monkeypatch):
        monkeypatch.setattr(project, 'render_journal_to_bytes',
                            Mock(side_effect=RuntimeError('画布炸了')))

        response = client.post('/api/export-image', data={'journal_text': '标题\n正文'})

        assert response.status_code == 500
        assert response.get_json()['error'] == '长图生成失败，请稍后重试。'

    def test_uploads_serves_a_photo_owned_by_this_session(self, client):
        filenames = upload_photo(client)

        response = client.get('/uploads/' + filenames[0])

        assert response.status_code == 200 and response.mimetype == 'image/jpeg'
        # 私有照片绝不能被中间层缓存，否则换个人打开就是别人的旅行照。
        assert response.headers['Cache-Control'] == 'private, no-store'
