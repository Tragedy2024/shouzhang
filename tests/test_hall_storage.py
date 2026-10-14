"""Concurrency, quota and durable media checks for public journal snapshots."""
import io
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from PIL import Image
from services.hall_service import HallError, HallService, payload_fingerprint
from services.storage_service import JournalStore


@pytest.fixture
def hall(tmp_path):
    store = JournalStore(tmp_path / 'state.sqlite3', tmp_path / 'private-photos')
    return HallService(store, tmp_path / 'public-media')


def publish(hall, key=None, owner='author', payload=None):
    payload = payload or {'title': '海边', 'caption': '旅行记录', 'author_name': '作者', 'style': 'film', 'topics': ['旅行']}
    image = Image.new('RGB', (750, 500), '#7aaabb')
    output = io.BytesIO()
    image.save(output, 'PNG')
    return hall.publish(owner, key or str(uuid.uuid4()), payload_fingerprint(payload), payload, output.getvalue())


def test_daily_limit_counts_withdrawn_posts_and_idempotent_retries(hall):
    first_key = str(uuid.uuid4())
    first, _ = publish(hall, key=first_key)
    repeated, created = publish(hall, key=first_key)
    assert repeated['id'] == first['id'] and created is False
    for _ in range(19):
        publish(hall)
    hall.withdraw(first['id'], 'author')
    with pytest.raises(HallError) as error:
        publish(hall)
    assert error.value.status == 429
    # Each other browser identity has its own quota.
    assert publish(hall, owner='other')[1] is True


def test_concurrent_same_key_creates_one_post(hall):
    key = str(uuid.uuid4())
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: publish(hall, key=key), range(2)))
    assert len({record['id'] for record, created in results}) == 1
    assert sum(created for record, created in results) == 1
    assert hall.list_posts('author')['total'] == 1
    assert len(list(hall.media_directory.glob('*'))) == 2


def test_posts_and_images_survive_database_reopen(hall):
    record, _ = publish(hall)
    reopened_store = JournalStore(hall.store.path, hall.store.upload_directory)
    reopened = HallService(reopened_store, hall.media_directory)
    assert reopened.post(record['id'])['title'] == '海边'
    assert reopened.media(record['id']).is_file()
    assert reopened.media(record['id'], thumbnail=True).is_file()


@pytest.mark.parametrize('target_inside', [True, False])
def test_media_rejects_symlink_targets(hall, tmp_path, target_inside):
    record, _ = publish(hall)
    path = hall.media(record['id'])
    target = (hall.media_directory if target_inside else tmp_path) / 'other.png'
    target.write_bytes(path.read_bytes())
    path.unlink()
    try:
        path.symlink_to(target)
    except (OSError, NotImplementedError):
        # Windows needs administrator rights or Developer Mode for symlinks.
        pytest.skip('creating symlinks requires privileges on this system')
    assert hall.media(record['id']) is None


def test_failed_database_insert_rolls_back_media(hall):
    bad = {'title': '海边', 'caption': '旅行记录', 'style': 'film', 'topics': ['旅行']}
    with pytest.raises(KeyError):
        publish(hall, payload=bad)
    assert hall.list_posts('author')['total'] == 0
    assert not list(hall.media_directory.glob('*'))
