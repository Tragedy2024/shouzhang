"""Public journal sharing, persistence, ownership and snapshot regressions."""
import io
import json
import time
import uuid
from pathlib import Path

import pytest
from PIL import Image
import app as project
from services.storage_service import RETENTION_SECONDS
from tests.test_app_offline import client, submit, result_for


@pytest.fixture
def hall_client(client, tmp_path, monkeypatch):
    monkeypatch.setitem(project.app.config, 'HALL_MEDIA_FOLDER', str(tmp_path / 'hall-media'))
    return client


def payload_for(client, **changes):
    result = result_for(client, submit(client))['result']
    fields = {key: result.get(key, '') or '' for key in ('style', 'date', 'weather', 'address', 'datetime_str')}
    fields.update(title='海边的周末', caption='留住海风吹过的这一页。', author_name='旅行记录者',
                  topics=json.dumps(['海边旅行', '周末出游']), public_confirm='true',
                  idempotency_key=str(uuid.uuid4()), sections=json.dumps(result['sections']),
                  journal_text=result['journal'], image_filenames=','.join(result['image_filenames']))
    fields.update(changes)
    return fields


def publish(client, payload=None, **changes):
    data = payload if payload is not None else payload_for(client, **changes)
    response = client.post('/api/hall/posts', data=data)
    assert response.status_code == 201, response.json
    return response.json['post']


def test_public_hall_is_empty_and_has_working_page(hall_client):
    page = hall_client.get('/hall')
    assert page.status_code == 200
    assert '手帐大厅' in page.text
    response = hall_client.get('/api/hall/posts')
    assert response.status_code == 200
    assert response.json['posts'] == [] and response.json['total'] == 0
    assert hall_client.get('/api/hall/topics').json['topics'] == []


def test_post_is_visible_to_other_users_without_private_identifiers(hall_client):
    post = publish(hall_client)
    assert post['is_owner'] is True
    assert post['topics'] == ['海边旅行', '周末出游']
    assert post['detail_url'].startswith('/hall?post=')
    assert post['title'] == '海边的周末'
    assert post['image_width'] == 1500 and post['image_height'] > 300
    with project.app.test_client() as stranger:
        feed = stranger.get('/api/hall/posts').json
        assert feed['total'] == 1 and feed['posts'][0]['is_owner'] is False
        detail = stranger.get('/api/hall/posts/' + post['id']).json['post']
        assert detail['title'] == post['title'] and detail['is_owner'] is False
        assert stranger.get('/api/hall/posts?mine=1').json['posts'] == []
        for url in (post['image_url'], post['thumbnail_url']):
            image = stranger.get(url)
            assert image.status_code == 200 and image.mimetype.startswith('image/')
            with Image.open(io.BytesIO(image.data)) as rendered:
                assert not rendered.getexif()
        encoded = json.dumps(detail)
        for private_key in ('owner_id', 'image_filenames', 'image_metadata', 'gps', 'image_paths', 'database_path'):
            assert private_key not in detail and private_key not in encoded
        assert '/uploads/' not in encoded


def test_public_images_survive_private_photo_cleanup(hall_client):
    fields = payload_for(hall_client)
    private_name = fields['image_filenames']
    post = publish(hall_client, fields)
    store = project._store()
    with store.connect() as conn:
        conn.execute('UPDATE photos SET created_at=?', (time.time() - RETENTION_SECONDS - 1,))
    store.cleanup()
    assert hall_client.get('/uploads/' + private_name).status_code == 404
    assert hall_client.get(post['image_url']).status_code == 200
    assert hall_client.get(post['thumbnail_url']).status_code == 200
    assert hall_client.get('/api/hall/posts/' + post['id']).status_code == 200
    replay = hall_client.post('/api/hall/posts', data=fields)
    assert replay.status_code == 200
    assert replay.json['post']['id'] == post['id']


def test_published_snapshot_is_immutable_from_later_draft_changes(hall_client):
    fields = payload_for(hall_client)
    post = publish(hall_client, fields)
    original = hall_client.get(post['image_url']).data
    fields['sections'] = json.dumps({'title': '后来修改的标题', 'body': '新的草稿正文', 'tags': []})
    edited = hall_client.post('/api/export-image', data={**fields, 'scale': '2'})
    assert edited.status_code == 200
    assert edited.data != original
    assert hall_client.get(post['image_url']).data == original
    assert hall_client.get('/api/hall/posts/' + post['id']).json['post']['title'] == '海边的周末'


def test_duplicate_submit_is_idempotent(hall_client):
    fields = payload_for(hall_client)
    first = hall_client.post('/api/hall/posts', data=fields)
    second = hall_client.post('/api/hall/posts', data=fields)
    assert first.status_code == 201 and second.status_code == 200
    assert first.json['post']['id'] == second.json['post']['id']
    assert hall_client.get('/api/hall/posts').json['total'] == 1
    fields['caption'] = '改了发布内容'
    conflict = hall_client.post('/api/hall/posts', data=fields)
    assert conflict.status_code == 409
    assert hall_client.get('/api/hall/posts').json['total'] == 1


def test_replaying_a_withdrawn_post_does_not_republish(hall_client):
    fields = payload_for(hall_client)
    post = publish(hall_client, fields)
    hall_client.post('/api/hall/posts/' + post['id'] + '/withdraw')
    replay = hall_client.post('/api/hall/posts', data=fields)
    assert replay.status_code == 409
    assert hall_client.get('/api/hall/posts').json['total'] == 0


def test_topics_normalize_deduplicate_and_filter_exactly(hall_client):
    publish(hall_client, topics=json.dumps([' #海边旅行 ', '海边旅行', '#周末']))
    publish(hall_client, topics=json.dumps(['海边旅行攻略']), title='另一段旅程')
    names = {row['name']: row['count'] for row in hall_client.get('/api/hall/topics').json['topics']}
    assert names == {'海边旅行': 1, '周末': 1, '海边旅行攻略': 1}
    filtered = hall_client.get('/api/hall/posts', query_string={'topic': '海边旅行'}).json
    assert filtered['total'] == 1
    assert filtered['posts'][0]['topics'] == ['海边旅行', '周末']


def test_search_pagination_and_mine_do_not_leak_other_owners(hall_client):
    first_fields = payload_for(hall_client)
    first = publish(hall_client, first_fields)
    second = publish(hall_client, title='山间散步', caption='青绿色的回忆', topics=json.dumps(['山间']))
    page1 = hall_client.get('/api/hall/posts?page=1&page_size=1').json
    page2 = hall_client.get('/api/hall/posts?page=2&page_size=1').json
    assert page1['total'] == 2 and page1['has_more'] is True
    assert page2['has_more'] is False
    assert page1['posts'][0]['id'] == second['id']
    assert page2['posts'][0]['id'] == first['id']
    assert hall_client.get('/api/hall/posts', query_string={'q': '青绿色'}).json['total'] == 1
    assert hall_client.get('/api/hall/posts', query_string={'q': "' OR 1=1 --"}).json['total'] == 0
    with project.app.test_client() as other:
        other_post = publish(other, title='另一个用户的记录')
        assert other.get('/api/hall/posts?mine=1').json['total'] == 1
    own_feed = hall_client.get('/api/hall/posts?mine=1').json
    assert own_feed['total'] == 2
    assert other_post['id'] not in [item['id'] for item in own_feed['posts']]


def test_only_owner_can_withdraw_and_public_images_stop_working(hall_client):
    post = publish(hall_client)
    with project.app.test_client() as stranger:
        response = stranger.post('/api/hall/posts/' + post['id'] + '/withdraw')
        assert response.status_code in (403, 404)
        assert stranger.get(post['image_url']).status_code == 200
    assert hall_client.post('/api/hall/posts/' + post['id'] + '/withdraw').status_code == 200
    assert hall_client.get('/api/hall/posts').json['total'] == 0
    assert hall_client.get('/api/hall/posts?mine=1').json['total'] == 0
    assert hall_client.get('/api/hall/topics').json['topics'] == []
    assert hall_client.get('/api/hall/posts/' + post['id']).status_code == 404
    assert hall_client.get(post['image_url']).status_code == 404
    assert hall_client.get(post['thumbnail_url']).status_code == 404


@pytest.mark.parametrize('field,value', [
    ('public_confirm', ''), ('public_confirm', 'false'), ('title', ''), ('title', 'x' * 101),
    ('caption', 'x' * 2001), ('author_name', ''), ('author_name', 'x' * 31),
    ('topics', '[1]'), ('topics', '"topic"'), ('topics', 'not-json'),
    ('topics', json.dumps(['x' * 21])), ('topics', json.dumps([f'话题{i}' for i in range(6)])),
    ('idempotency_key', ''), ('idempotency_key', '../file'), ('style', 'unknown'),
    ('sections', '[]'), ('sections', '{broken}'),
])
def test_invalid_publication_is_rejected_before_writing_media(hall_client, field, value):
    fields = payload_for(hall_client)
    fields[field] = value
    response = hall_client.post('/api/hall/posts', data=fields)
    assert response.status_code == 400, response.json
    assert 'error' in response.json
    assert hall_client.get('/api/hall/posts').json['total'] == 0
    assert not list(Path(project.app.config['HALL_MEDIA_FOLDER']).glob('*.*'))


def test_publish_cannot_reuse_another_users_private_photos(hall_client):
    fields = payload_for(hall_client)
    with project.app.test_client() as stranger:
        response = stranger.post('/api/hall/posts', data=fields)
        assert response.status_code in (400, 403)
        assert stranger.get('/api/hall/posts').json['total'] == 0


@pytest.mark.parametrize('filename', ['../../config.py', '/tmp/arbitrary.jpg', 'unknown.jpg'])
def test_publish_rejects_path_traversal(hall_client, filename):
    fields = payload_for(hall_client, image_filenames=filename)
    response = hall_client.post('/api/hall/posts', data=fields)
    assert response.status_code == 400
    assert hall_client.get('/api/hall/posts').json['total'] == 0


def test_hall_content_is_escaped_in_page_not_injected_into_html(hall_client):
    text = '<script>window.stolen=true</script>'
    post = publish(hall_client, title=text, caption=text, author_name='<b>旅行者</b>', topics=json.dumps(['<img>']))
    assert hall_client.get('/api/hall/posts/' + post['id']).json['post']['caption'] == text
    assert text not in hall_client.get('/hall?post=' + post['id']).text


def test_missing_posts_and_invalid_pagination_return_json(hall_client):
    for path in ('/api/hall/posts/missing', '/api/hall/posts/missing/image', '/api/hall/posts/missing/thumbnail'):
        response = hall_client.get(path)
        assert response.status_code == 404 and 'error' in response.json
    for params in ({'page': 'abc'}, {'page': '0'}, {'page_size': '-1'}):
        response = hall_client.get('/api/hall/posts', query_string=params)
        assert response.status_code == 400 and 'error' in response.json
