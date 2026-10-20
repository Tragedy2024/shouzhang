r"""实体类单元测试：``services.storage_service.JournalStore``。

被测单元
--------
``JournalStore`` 是"私有照片 + 可续跑任务"的持久化实体，直接持有 sqlite
连接与磁盘文件，因此三条业务不变量必须在这里钉死：

1. **访问控制**：照片只能被上传它的 owner 读到，且文件名必须匹配
   ``^[a-f0-9]{32}\.jpg$``，符号链接与路径穿越一律拒绝。
2. **保留期**：照片 7 天后失效；``cleanup()`` 只删自己登记过的文件，
   绝不误删用户既有文件。
3. **任务并发**：同一 owner 最多 2 个进行中任务，全局最多 12 个。

为什么不用 Mock 替换 sqlite
---------------------------
SQL 约束、WAL 模式、文件句柄这些正是风险所在，mock 掉就测不到了。
本模块用 ``tmp_path`` 提供真实临时目录，只在需要"拨动时间"的地方
用 ``unittest.mock.patch`` 替换 ``storage_service.time.time``。
"""

import os
import sqlite3
import time
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest

from services.storage_service import PHOTO_NAME, RETENTION_SECONDS, JournalStore


def registered_name():
    """造一个符合 ``PHOTO_NAME`` 的合法文件名。"""
    return f'{uuid.uuid4().hex}.jpg'


def job_record(owner='owner-1', status='queued', job_id=None, **extra):
    """造一条最小可用的任务记录（``create_job`` 只强制要求这三个键）。"""
    return {'job_id': job_id or uuid.uuid4().hex, 'owner': owner, 'status': status, **extra}


def seed_photo(store, owner='owner-1', filename=None, metadata=None):
    """登记一张照片，并在磁盘上放一个真实文件。"""
    filename = filename or registered_name()
    (store.upload_directory / filename).write_bytes(b'jpeg-bytes')
    store.add_photo(filename, owner, metadata or {})
    return filename


class TestSchema:
    """建表：私有表与公共表必须同时存在，且启用 WAL。"""

    def test_schema_creates_private_and_public_tables(self, store):
        with store.connect() as connection:
            names = {row[0] for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}

        assert {'photos', 'jobs', 'hall_posts', 'hall_topics', 'hall_post_topics'} <= names

    def test_schema_creates_feed_indexes(self, store):
        with store.connect() as connection:
            names = {row[0] for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='index'")}

        assert {'hall_posts_feed', 'hall_posts_owner', 'hall_post_topics_topic'} <= names

    def test_schema_uses_write_ahead_logging(self, store):
        with store.connect() as connection:
            mode = connection.execute('PRAGMA journal_mode').fetchone()[0]

        assert mode.lower() == 'wal'

    def test_store_creates_missing_directories(self, tmp_path):
        # 首次部署时 instance/ 与 uploads/ 可能都还不存在。
        database = tmp_path / 'deep' / 'nested' / 'journal.sqlite3'
        uploads = tmp_path / 'deep' / 'photos'

        store = JournalStore(database, uploads)

        assert Path(store.path).parent.is_dir() and store.upload_directory.is_dir()


class TestConnectionLifetime:
    """连接生命周期：这是 Windows 兼容性的回归防线。"""

    def test_connect_closes_the_connection_after_the_block(self, store):
        """``connect()`` 必须真的关闭句柄。

        sqlite3 自带的 ``with connection`` 只负责提交/回滚，**从不 close**。
        早期版本因此泄漏句柄，在 Windows 上锁住 journal.sqlite3 及其
        ``-wal``/``-shm`` 旁文件，导致临时目录清理和移动项目文件夹失败。
        """
        with store.connect() as connection:
            assert connection.execute('SELECT 1').fetchone()[0] == 1

        with pytest.raises(sqlite3.ProgrammingError):
            connection.execute('SELECT 1')

    def test_connect_rolls_back_on_exception_and_still_closes(self, store):
        with pytest.raises(RuntimeError):
            with store.connect() as connection:
                connection.execute('INSERT INTO photos VALUES (?,?,?,?)',
                                   (registered_name(), 'owner-1', time.time(), '{}'))
                raise RuntimeError('业务代码炸了')

        with store.connect() as connection:
            assert connection.execute('SELECT COUNT(*) FROM photos').fetchone()[0] == 0

    def test_store_leaves_no_write_ahead_log_behind(self, store):
        # 最后一个连接正常关闭时 sqlite 会删掉 -wal 旁文件；
        # 如果它还在，说明某个连接没有关闭。
        seed_photo(store)

        assert not Path(store.path + '-wal').exists()

    def test_database_file_is_releasable_after_use(self, store):
        # 句柄全部释放后，数据库文件应当可以被重命名（Windows 上的真实症状）。
        seed_photo(store)
        moved = Path(store.path + '.moved')

        os.replace(store.path, moved)

        assert moved.exists()


class TestPhotoAccess:
    """照片读取：owner 隔离 + 文件名白名单 + 符号链接防护。"""

    def test_photo_returns_resolved_path_and_metadata(self, store):
        filename = seed_photo(store, metadata={'datetime_str': '2026-10-01 08:00:00'})

        photo = store.photo(filename, 'owner-1')

        assert photo['path'] == str((store.upload_directory / filename).resolve())
        assert photo['metadata']['datetime_str'] == '2026-10-01 08:00:00'

    @pytest.mark.parametrize('filename', [
        '../../config.py',      # 路径穿越
        'a/b.jpg',              # 子目录
        'ABC.jpg',              # 非小写十六进制
        'a' * 31 + '.jpg',      # 长度不足
        'a' * 32 + '.png',      # 扩展名不符
        'not-a-hash.jpg',
        '',
    ])
    def test_photo_rejects_names_outside_the_registry_pattern(self, store, filename):
        # 文件名白名单是第一道闸门：格式不对的直接当作不存在，连查询都不发。
        assert PHOTO_NAME.fullmatch(filename) is None
        assert store.photo(filename, 'owner-1') is None

    def test_photo_is_scoped_to_the_uploading_owner(self, store):
        filename = seed_photo(store, owner='owner-1')

        assert store.photo(filename, 'owner-1') is not None
        # 换一个浏览器身份（owner）不能读到别人的照片。
        assert store.photo(filename, 'owner-2') is None

    def test_photo_expires_after_the_retention_window(self, store):
        filename = seed_photo(store)
        just_inside = time.time() + RETENTION_SECONDS - 60

        with patch('services.storage_service.time.time', return_value=just_inside):
            assert store.photo(filename, 'owner-1') is not None

        just_outside = time.time() + RETENTION_SECONDS + 1
        with patch('services.storage_service.time.time', return_value=just_outside):
            assert store.photo(filename, 'owner-1') is None

    def test_photo_returns_none_when_the_file_is_gone(self, store):
        # 数据库里有记录、磁盘上没文件（被外部删掉）时不能抛异常。
        filename = registered_name()
        store.add_photo(filename, 'owner-1', {})

        assert store.photo(filename, 'owner-1') is None

    def test_photo_rejects_a_symlinked_upload(self, store, tmp_path):
        outside = tmp_path / 'outside.jpg'
        outside.write_bytes(b'not yours')
        link = store.upload_directory / registered_name()
        try:
            link.symlink_to(outside)
        except (OSError, NotImplementedError):
            pytest.skip('创建符号链接需要管理员权限或开发者模式')
        store.add_photo(link.name, 'owner-1', {})

        assert store.photo(link.name, 'owner-1') is None


class TestPhotoRemoval:
    """照片删除：只删自己登记过的文件。"""

    def test_remove_photo_deletes_row_and_file(self, store):
        filename = seed_photo(store)

        store.remove_photo(filename, 'owner-1')

        assert not (store.upload_directory / filename).exists()
        assert store.photo(filename, 'owner-1') is None

    def test_remove_photo_leaves_unregistered_files_alone(self, store):
        # 清理逻辑绝不能碰用户自己放进 uploads/ 的文件。
        bystander = store.upload_directory / registered_name()
        bystander.write_bytes(b'user-owned file')

        store.remove_photo(bystander.name, 'owner-1')

        assert bystander.exists()

    def test_remove_photo_ignores_another_owners_registration(self, store):
        filename = seed_photo(store, owner='owner-1')

        store.remove_photo(filename, 'owner-2')

        assert store.photo(filename, 'owner-1') is not None


class TestJobLifecycle:
    """任务并发与状态流转。"""

    def test_create_job_persists_the_record(self, store):
        record = job_record()

        assert store.create_job(record) is True
        assert store.job(record['job_id'], record['owner'])['job_id'] == record['job_id']

    def test_job_is_only_visible_to_its_owner(self, store):
        record = job_record(owner='owner-1')
        store.create_job(record)

        assert store.job(record['job_id'], 'owner-2') is None
        assert store.job('missing-id', 'owner-1') is None

    def test_create_job_enforces_the_per_owner_active_limit(self, store):
        # 同一浏览器身份最多 2 个进行中任务，避免一个人占满线程池。
        assert store.create_job(job_record(owner='owner-1')) is True
        assert store.create_job(job_record(owner='owner-1')) is True

        assert store.create_job(job_record(owner='owner-1')) is False
        # 别人不受影响。
        assert store.create_job(job_record(owner='owner-2')) is True

    def test_create_job_enforces_the_global_active_limit(self, store):
        # 全局上限 12：12 个不同 owner 各占 1 个名额后，第 13 个被拒。
        for index in range(12):
            assert store.create_job(job_record(owner=f'owner-{index}')) is True

        assert store.create_job(job_record(owner='owner-late')) is False

    def test_create_job_ignores_finished_jobs_in_the_quota(self, store):
        store.create_job(job_record(owner='owner-1', status='completed'))
        store.create_job(job_record(owner='owner-1', status='failed'))

        # 已结束的任务不占名额。
        assert store.create_job(job_record(owner='owner-1')) is True
        assert store.create_job(job_record(owner='owner-1')) is True
        assert store.create_job(job_record(owner='owner-1')) is False

    def test_create_job_accepts_a_raised_active_limit(self, store):
        # 调用方可以放宽单个 owner 的名额（claim_retry 的用例会用到）。
        for _ in range(4):
            assert store.create_job(job_record(owner='owner-1'), active_limit=5) is True

    def test_save_job_replaces_record_and_status(self, store):
        record = job_record()
        store.create_job(record)

        record.update(status='completed', message='手账已生成')
        store.save_job(record)

        stored = store.job(record['job_id'], record['owner'])
        assert stored['status'] == 'completed' and stored['message'] == '手账已生成'

    def test_save_job_cannot_touch_another_owners_job(self, store):
        record = job_record(owner='owner-1')
        store.create_job(record)

        store.save_job({**record, 'owner': 'owner-2', 'status': 'completed'})

        assert store.job(record['job_id'], 'owner-1')['status'] == 'queued'


class TestRetry:
    """重试领取：只有 failed 且可重试的任务才能被重新排队。"""

    def test_claim_retry_requeues_and_clears_the_error(self, store):
        record = job_record(status='failed')
        store.create_job(record)
        store.save_job({**record, 'retryable': True, 'error': '写作出错', 'result': {'journal': 'a'}})

        claimed = store.claim_retry(record['job_id'], record['owner'])

        assert claimed['status'] == 'queued'
        assert 'error' not in claimed
        # 已完成的步骤（result）必须保留，重试不该从头再来。
        assert claimed['result'] == {'journal': 'a'}

    @pytest.mark.parametrize('status,retryable', [
        ('queued', True),        # 正在排队
        ('running', True),       # 正在生成
        ('completed', True),     # 已经完成
        ('failed', False),       # 失败但不可重试（例如照片已损坏）
    ])
    def test_claim_retry_refuses_ineligible_jobs(self, store, status, retryable):
        record = job_record(status=status)
        store.create_job(record)
        store.save_job({**record, 'retryable': retryable})

        assert store.claim_retry(record['job_id'], record['owner']) is None

    def test_claim_retry_refuses_an_unknown_job(self, store):
        assert store.claim_retry('missing', 'owner-1') is None

    def test_claim_retry_refuses_when_the_owner_is_at_capacity(self, store):
        # 先放宽名额塞进 3 个任务：2 个进行中 + 1 个失败可重试。
        store.create_job(job_record(owner='owner-1', status='queued'), active_limit=5)
        store.create_job(job_record(owner='owner-1', status='running'), active_limit=5)
        failed = job_record(owner='owner-1', status='failed')
        store.create_job(failed, active_limit=5)
        store.save_job({**failed, 'retryable': True})

        assert store.claim_retry(failed['job_id'], 'owner-1') is None


class TestRecoveryAndCleanup:
    """进程重启恢复与 7 天保留期清理。"""

    def test_recover_interrupted_jobs_fails_queued_and_running(self, store):
        # 先建"已完成"的任务：create_job 限制同一 owner 最多 2 个进行中的任务，
        # 把 completed 排在 queued/running 之后会被并发闸门挡掉。
        done = job_record(status='completed')
        queued, running = (job_record(status=status) for status in ('queued', 'running'))
        for record in (done, queued, running):
            store.create_job(record)

        store.recover_interrupted_jobs()

        for record in (queued, running):
            stored = store.job(record['job_id'], record['owner'])
            assert stored['status'] == 'failed'
            assert stored['retryable'] is True
            assert '重新启动' in stored['error']
        # 已经完成的任务不受重启影响。
        assert store.job(done['job_id'], done['owner'])['status'] == 'completed'

    def test_cleanup_expires_old_photos_but_keeps_fresh_ones(self, store):
        fresh, expired = seed_photo(store), seed_photo(store)
        with store.connect() as connection:
            connection.execute('UPDATE photos SET created_at=? WHERE filename=?',
                               (time.time() - RETENTION_SECONDS - 1, expired))

        store.cleanup()

        assert (store.upload_directory / fresh).exists()
        assert not (store.upload_directory / expired).exists()

    def test_cleanup_deletes_finished_jobs_but_not_active_ones(self, store):
        finished = job_record(status='completed')
        active = job_record(status='queued')
        for record in (finished, active):
            store.create_job(record)
        with store.connect() as connection:
            connection.execute('UPDATE jobs SET created_at=? WHERE id=?',
                               (time.time() - RETENTION_SECONDS - 1, finished['job_id']))

        store.cleanup()

        assert store.job(finished['job_id'], finished['owner']) is None
        assert store.job(active['job_id'], active['owner']) is not None
