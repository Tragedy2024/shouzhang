"""End-to-end API regressions without model or map requests."""
import io
import time
from pathlib import Path
from unittest.mock import Mock

import pytest
from PIL import Image
import app as project
from services.errors import GenerationError
from services.storage_service import RETENTION_SECONDS


def photo_bytes(date=None, orientation=None):
    image = Image.new('RGB', (120, 80), '#7799aa')
    exif = Image.Exif()
    if date:
        exif[36867] = date
    if orientation:
        exif[274] = orientation
    out = io.BytesIO()
    image.save(out, 'JPEG', exif=exif)
    return out.getvalue()


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setitem(project.app.config, 'TESTING', True)
    monkeypatch.setitem(project.app.config, 'JOBS_INLINE', True)
    monkeypatch.setitem(project.app.config, 'UPLOAD_FOLDER', str(tmp_path / 'photos'))
    monkeypatch.setitem(project.app.config, 'JOURNAL_DB_PATH', str(tmp_path / 'state.sqlite3'))
    monkeypatch.setattr(project, 'analyze_images_batch', Mock(return_value='海岸线和一艘船。'))
    monkeypatch.setattr(project, 'generate_journal', Mock(return_value='海边散步\n\n风吹过海面。\n\n#旅行 #海边'))
    monkeypatch.setattr(project, 'regenerate_journal', Mock(return_value='海风来信\n\n风吹过海面。\n\n#旅行'))
    monkeypatch.setattr(project, 'reverse_geocode', Mock(return_value='海边'))
    with project.app.test_client() as result:
        yield result


def submit(client, **fields):
    return client.post('/api/jobs', data={'image': (io.BytesIO(photo_bytes()), 'coast.jpg'), **fields})


def result_for(client, response):
    assert response.status_code == 202
    return client.get('/api/jobs/' + response.json['job_id']).json


def test_generate_preserves_snapshot_and_private_photo(client):
    response = submit(client, location='用户地点', date='2026-10-01', weather='晴天', style='film')
    job = result_for(client, response)
    assert job['status'] == 'completed'
    result = job['result']
    assert result['sections']['title'] == '海边散步'
    assert result['date'] == '2026-10-01'
    assert result['weather'] == '晴天'
    assert result['address'] == '用户地点'
    assert result['style'] == 'film'
    assert 'gps' not in result and 'gps' not in result['image_metadata'][0]
    photo = client.get(result['image_urls'][0])
    assert photo.status_code == 200
    assert 'private' in photo.headers['Cache-Control']
    with Image.open(io.BytesIO(photo.data)) as image:
        assert not image.getexif()
    with project.app.test_client() as stranger:
        assert stranger.get(result['image_urls'][0]).status_code == 404
        assert stranger.get('/api/jobs/' + job['job_id']).status_code == 404
        denied = stranger.post('/api/export-image', data={'journal_text': '标题\n正文', 'image_filenames': result['image_filenames'][0]})
        assert denied.status_code == 400


def test_failed_writing_can_retry_without_reanalyzing(client, monkeypatch):
    fake = Mock(side_effect=GenerationError('写作暂时失败', 'writing'))
    monkeypatch.setattr(project, 'generate_journal', fake)
    job = result_for(client, submit(client))
    assert job['status'] == 'failed' and job['retryable']
    assert 'result' not in job
    assert project.analyze_images_batch.call_count == 1
    monkeypatch.setattr(project, 'generate_journal', Mock(return_value='新标题\n\n正文'))
    retry = client.post('/api/jobs/' + job['job_id'] + '/retry')
    assert retry.status_code == 202
    completed = client.get('/api/jobs/' + job['job_id']).json
    assert completed['status'] == 'completed'
    assert project.analyze_images_batch.call_count == 1
    assert client.post('/api/jobs/' + job['job_id'] + '/retry').status_code == 409


def test_vision_failure_does_not_write_fiction(client, monkeypatch):
    monkeypatch.setattr(project, 'analyze_images_batch', Mock(return_value=''))
    job = result_for(client, submit(client))
    assert job['status'] == 'failed' and job['stage'] == 'vision'
    project.generate_journal.assert_not_called()


@pytest.mark.parametrize('name', ['../outside.jpg', '/tmp/outside.jpg', 'not-registered.jpg', '../../config.py'])
def test_export_rejects_unregistered_or_escaping_paths(client, name):
    response = client.post('/api/export-image', data={'journal_text': '标题\n正文', 'image_filenames': name})
    assert response.status_code == 400
    assert 'error' in response.json


def test_export_is_real_high_resolution_png(client):
    result = result_for(client, submit(client))['result']
    response = client.post('/api/export-image', data={
        'journal_text': result['journal'], 'image_filenames': ','.join(result['image_filenames']),
        'style': 'film', 'date': '2026-10-01', 'weather': '晴天', 'scale': '2'})
    assert response.status_code == 200 and response.mimetype == 'image/png'
    with Image.open(io.BytesIO(response.data)) as image:
        assert image.width == 1500


def test_bad_image_rolls_back_all_saved_files(client):
    response = client.post('/api/jobs', data={'image': [(io.BytesIO(photo_bytes()), 'good.jpg'), (io.BytesIO(b'not an image'), 'bad.jpg')]})
    assert response.status_code == 400
    assert not list(Path(project.app.config['UPLOAD_FOLDER']).glob('*.jpg'))
    project.analyze_images_batch.assert_not_called()


def test_count_and_per_photo_limits(client):
    response = client.post('/api/jobs', data={'image': [(io.BytesIO(photo_bytes()), f'{i}.jpg') for i in range(10)]})
    assert response.status_code == 400
    assert '9' in response.json['error']
    response = client.post('/api/jobs', data={'image': (io.BytesIO(b'x' * (project.MAX_PHOTO_BYTES + 1)), 'large.jpg')})
    assert response.status_code == 400
    assert '16MB' in response.json['error']


def test_413_returns_json(client, monkeypatch):
    monkeypatch.setitem(project.app.config, 'MAX_CONTENT_LENGTH', 1024)
    response = client.post('/api/jobs', data={'image': (io.BytesIO(b'x' * 2048), 'large.jpg')})
    assert response.status_code == 413 and 'error' in response.json


def test_multiday_metadata_and_orientation_are_preserved_then_stripped(client):
    response = client.post('/api/jobs', data={'image': [
        (io.BytesIO(photo_bytes('2026:10:01 09:00:00', 6)), 'one.jpg'),
        (io.BytesIO(photo_bytes('2026:10:02 10:00:00')), 'two.jpg')]})
    result = result_for(client, response)['result']
    assert result['date'] == ''
    assert any('不同日期' in text for text in result['warnings'])
    assert result['image_metadata'][1]['datetime_str'].startswith('2026-10-02')
    image_response = client.get(result['image_urls'][0])
    with Image.open(io.BytesIO(image_response.data)) as image:
        assert image.size == (80, 120)
        assert not image.getexif()


def test_regenerate_rejects_errors_and_invalid_types(client, monkeypatch):
    for data in ([], {'original_text': ['wrong'], 'tone': 'healing'}, {'original_text': '正文', 'tone': 'unknown'}):
        assert client.post('/api/regenerate', json=data).status_code == 400
    monkeypatch.setattr(project, 'regenerate_journal', Mock(side_effect=GenerationError('暂时失败', 'writing')))
    failed = client.post('/api/regenerate', json={'original_text': '正文', 'tone': 'healing', 'style': 'film'})
    assert failed.status_code == 502 and 'journal' not in failed.json


def test_samples_use_same_renderer(client):
    for style in project.STYLES:
        response = client.get('/api/sample/' + style)
        assert response.status_code == 200 and response.data.startswith(b'\x89PNG')
    assert client.get('/api/sample/unknown').status_code == 404


def test_expiration_never_deletes_preexisting_files(client):
    result = result_for(client, submit(client))['result']
    store = project._store()
    unrelated = store.upload_directory / 'existing-user-photo.png'
    unrelated.write_bytes(b'existing')
    with store.connect() as conn:
        conn.execute('UPDATE photos SET created_at=?', (time.time() - RETENTION_SECONDS - 1,))
    store.cleanup()
    assert unrelated.read_bytes() == b'existing'
    assert client.get(result['image_urls'][0]).status_code == 404


def test_interrupted_jobs_preserve_completed_steps(client):
    job = result_for(client, submit(client))
    store = project._store()
    with client.session_transaction() as session:
        owner = session['owner_id']
    record = store.job(job['job_id'], owner)
    record['status'] = 'running'
    store.save_job(record)
    store.recover_interrupted_jobs()
    recovered = store.job(job['job_id'], owner)
    assert recovered['status'] == 'failed' and recovered['retryable']
    assert recovered['image_description']
    assert recovered['location_data']


def test_html_fallback_escapes_journal(client, monkeypatch):
    monkeypatch.setattr(project, 'generate_journal', Mock(return_value='<script>alert(1)</script>\n正文'))
    response = client.post('/upload', data={'image': (io.BytesIO(photo_bytes()), 'coast.jpg')})
    assert response.status_code == 200
    assert b'<script>alert(1)</script>' not in response.data
    assert b'&lt;script&gt;' in response.data


def test_remove_photo_requires_owner_even_in_storage(client):
    result = result_for(client, submit(client))['result']
    filename = result['image_filenames'][0]
    project._store().remove_photo(filename, 'stranger')
    assert client.get(result['image_urls'][0]).status_code == 200


def test_structured_export_preserves_empty_title(client, monkeypatch):
    import json
    renderer = Mock(return_value=b'png')
    monkeypatch.setattr(project, 'render_journal_to_bytes', renderer)
    sections = {'title': '', 'body': '正文第一行\n\n正文第二段', 'tags': []}
    response = client.post('/api/export-image', data={'sections': json.dumps(sections)})
    assert response.status_code == 200
    assert renderer.call_args.kwargs['sections'] == sections
    for invalid in ('[1, 2]', '{bad json}', '{"title":[],"body":"正文","tags":[]}'):
        assert client.post('/api/export-image', data={'sections': invalid}).status_code == 400
