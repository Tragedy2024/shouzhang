"""实体类单元测试：``services.hall_service``。

被测单元
--------
``HallService`` 是"公开手帐大厅"的领域实体：发布、撤回、分页浏览、话题聚合、
缩略图与每日配额。它自带 sqlite 与磁盘副作用，所以主体用真实临时目录
（``tmp_path``，由 ``hall`` 夹具提供）；只有 **当前时间** 用
``unittest.mock.patch`` 拨动，用来验证「每天 20 篇、按中国时区 0 点重置」这类
无法靠等待验证的边界。

另外三个模块级纯函数也一并覆盖：
``normalize_topic`` / ``payload_fingerprint`` / ``public_post``。
"""

import io
import time
import uuid

import pytest
from PIL import Image

from services.hall_service import (
    DAILY_POST_LIMIT,
    HallError,
    HallService,
    normalize_topic,
    payload_fingerprint,
    public_post,
)

# 一份最小可发布的载荷；测试按需覆盖其中若干字段。
PAYLOAD = {
    'title': '海边', 'caption': '旅行记录', 'author_name': '作者',
    'style': 'film', 'topics': ['旅行', '海边'],
}

PUBLIC_FIELDS = {
    'id', 'title', 'caption', 'author_name', 'topics', 'created_at', 'style',
    'image_width', 'image_height', 'is_owner', 'image_url', 'thumbnail_url', 'detail_url',
}

PRIVATE_COLUMNS = {'owner', 'idempotency_key', 'payload_hash', 'image_filename',
                   'thumbnail_filename', 'status'}


@pytest.fixture
def publish(png_bytes):
    """发布一篇手帐，返回 ``(record, created)``；默认参数可被关键字覆盖。"""

    def run(hall, owner='author', key=None, image=None, **overrides):
        payload = {**PAYLOAD, **overrides}
        return hall.publish(owner, key or str(uuid.uuid4()),
                            payload_fingerprint(payload), payload,
                            image if image is not None else png_bytes())

    return run


# --------------------------------------------------------------------------- #
# 模块级纯函数
# --------------------------------------------------------------------------- #

class TestNormalizeTopic:
    """话题规范化：NFKC 折叠 + 去空白 + 去前导 #。"""

    def test_normalize_topic_strips_whitespace_and_leading_hash(self):
        assert normalize_topic('  # 旅行 ') == '旅行'

    def test_normalize_topic_folds_full_width_characters(self):
        # 用户从中文输入法打出的全角 # 和全角字母都要折成半角。
        assert normalize_topic('＃ＦＯＯＤ') == 'FOOD'

    def test_normalize_topic_keeps_inner_hashes(self):
        assert normalize_topic('旅行#日记') == '旅行#日记'

    @pytest.mark.parametrize('value', ['', '   ', '#', '###'])
    def test_normalize_topic_of_empty_input_stays_empty(self, value):
        assert normalize_topic(value) == ''


class TestPayloadFingerprint:
    """幂等指纹：与键顺序无关，与内容强相关。"""

    def test_payload_fingerprint_is_order_independent(self):
        assert payload_fingerprint({'title': 'A', 'topics': ['x']}) == \
               payload_fingerprint({'topics': ['x'], 'title': 'A'})

    def test_payload_fingerprint_changes_with_any_field(self):
        base = {'title': 'A', 'topics': ['x']}
        assert payload_fingerprint(base) != payload_fingerprint({**base, 'title': 'B'})
        assert payload_fingerprint(base) != payload_fingerprint({**base, 'topics': ['y']})

    def test_payload_fingerprint_is_a_sha256_hex_digest(self):
        digest = payload_fingerprint({'title': 'A'})

        assert len(digest) == 64
        assert all(char in '0123456789abcdef' for char in digest)


class TestPublicPost:
    """公开展示模型：只暴露展示字段，绝不暴露隐私列。"""

    def test_public_post_exposes_exactly_the_display_fields(self, hall, publish):
        record, _ = publish(hall)

        view = public_post(record, 'author')

        assert set(view) == PUBLIC_FIELDS

    def test_public_post_never_leaks_private_columns(self, hall, publish):
        record, _ = publish(hall)

        view = public_post(record, 'author')

        assert PRIVATE_COLUMNS.isdisjoint(view)

    def test_public_post_reports_ownership_and_urls(self, hall, publish):
        record, _ = publish(hall)

        owner_view = public_post(record, 'author')
        stranger_view = public_post(record, 'someone-else')

        assert owner_view['is_owner'] is True and stranger_view['is_owner'] is False
        assert owner_view['image_url'] == f"/api/hall/posts/{record['id']}/image"
        assert owner_view['thumbnail_url'] == f"/api/hall/posts/{record['id']}/thumbnail"
        assert owner_view['detail_url'] == f"/hall?post={record['id']}"

    def test_public_post_timestamp_is_utc_iso8601(self, hall, publish):
        record, _ = publish(hall)

        stamp = public_post(record, 'author')['created_at']

        assert stamp.endswith('Z') and 'T' in stamp


# --------------------------------------------------------------------------- #
# 缩略图
# --------------------------------------------------------------------------- #

class TestThumbnail:
    """``_thumbnail`` 是纯函数（静态方法），可以完全脱离数据库单独验证。"""

    def test_thumbnail_rejects_non_png_payloads(self):
        # 服务端渲染器必须产出 PNG；传 JPEG 说明调用方搞错了，不能静默接受。
        buffer = io.BytesIO()
        Image.new('RGB', (40, 30), 'red').save(buffer, 'JPEG')

        with pytest.raises(ValueError, match='PNG'):
            HallService._thumbnail(buffer.getvalue())

    def test_thumbnail_returns_original_size_and_jpeg_bytes(self, png_bytes):
        width, height, data = HallService._thumbnail(png_bytes(size=(1500, 1000)))

        assert (width, height) == (1500, 1000)
        with Image.open(io.BytesIO(data)) as preview:
            assert preview.format == 'JPEG'

    def test_thumbnail_downscales_wide_images_to_the_preview_width(self, png_bytes):
        _, _, data = HallService._thumbnail(png_bytes(size=(1500, 1000)))

        with Image.open(io.BytesIO(data)) as preview:
            assert preview.width == 640
            assert preview.height == round(1000 * 640 / 1500)

    def test_thumbnail_does_not_upscale_small_images(self, png_bytes):
        _, _, data = HallService._thumbnail(png_bytes(size=(400, 300)))

        with Image.open(io.BytesIO(data)) as preview:
            assert (preview.width, preview.height) == (400, 300)

    def test_thumbnail_crops_tall_previews_to_keep_the_heading_visible(self, png_bytes):
        # 顶部裁剪：手帐标题和第一张照片必须留在预览里。
        _, _, data = HallService._thumbnail(png_bytes(size=(750, 3000)))

        with Image.open(io.BytesIO(data)) as preview:
            assert preview.height == 900

    def test_thumbnail_strips_metadata(self, png_bytes):
        _, _, data = HallService._thumbnail(png_bytes())

        with Image.open(io.BytesIO(data)) as preview:
            assert not preview.getexif()


# --------------------------------------------------------------------------- #
# 每日配额
# --------------------------------------------------------------------------- #

class TestDailyQuota:
    """发布配额：每天 20 篇，按中国时区 0 点重置，撤回不退还名额。"""

    def test_quota_allows_exactly_the_daily_limit(self, hall, publish):
        for _ in range(DAILY_POST_LIMIT):
            assert publish(hall)[1] is True

        with pytest.raises(HallError) as error:
            publish(hall)

        assert error.value.status == 429
        assert '明天' in error.value.message

    def test_quota_counts_withdrawn_posts(self, hall, publish):
        record, _ = publish(hall)
        hall.withdraw(record['id'], 'author')
        for _ in range(DAILY_POST_LIMIT - 1):
            publish(hall)

        with pytest.raises(HallError) as error:
            publish(hall)

        assert error.value.status == 429

    def test_quota_resets_at_local_midnight_in_china(self, hall, publish):
        for _ in range(DAILY_POST_LIMIT):
            publish(hall)
        # 把全部记录推到"中国时间今天 0 点"之前一秒，等价于跨了一天。
        day_start = ((time.time() + 8 * 3600) // 86400) * 86400 - 8 * 3600
        with hall.store.connect() as connection:
            connection.execute('UPDATE hall_posts SET created_at=?', (day_start - 1,))

        assert publish(hall)[1] is True

    def test_quota_is_per_browser_identity(self, hall, publish):
        for _ in range(DAILY_POST_LIMIT):
            publish(hall, owner='author')

        assert publish(hall, owner='other')[1] is True


# --------------------------------------------------------------------------- #
# 幂等发布
# --------------------------------------------------------------------------- #

class TestIdempotentPublish:
    """同一个 idempotency_key 重复提交只能产生一篇手帐。"""

    def test_same_key_and_payload_returns_the_original_post(self, hall, publish):
        key = str(uuid.uuid4())

        first, created = publish(hall, key=key)
        again, recreated = publish(hall, key=key)

        assert first['id'] == again['id']
        assert (created, recreated) == (True, False)
        assert hall.list_posts('author')['total'] == 1
        # 图片 + 缩略图，重复发布不会再写文件。
        assert len(list(hall.media_directory.glob('*'))) == 2

    def test_same_key_with_a_changed_payload_is_a_conflict(self, hall, publish):
        key = str(uuid.uuid4())
        publish(hall, key=key)

        with pytest.raises(HallError) as error:
            publish(hall, key=key, title='改过的标题')

        assert error.value.status == 409

    def test_same_key_after_withdraw_is_a_conflict(self, hall, publish):
        key = str(uuid.uuid4())
        record, _ = publish(hall, key=key)
        hall.withdraw(record['id'], 'author')

        with pytest.raises(HallError) as error:
            publish(hall, key=key)

        assert error.value.status == 409

    def test_preflight_returns_the_existing_post_without_writing(self, hall, publish):
        # 预检的意义就是：原图早就过期了，重试也要能拿回原来那篇。
        key = str(uuid.uuid4())
        first, _ = publish(hall, key=key)

        existing = hall.preflight('author', key, payload_fingerprint(PAYLOAD))

        assert existing['id'] == first['id']
        assert len(list(hall.media_directory.glob('*'))) == 2

    def test_preflight_raises_when_the_quota_is_used_up(self, hall, publish):
        for _ in range(DAILY_POST_LIMIT):
            publish(hall)

        with pytest.raises(HallError) as error:
            hall.preflight('author', str(uuid.uuid4()), 'a' * 64)

        assert error.value.status == 429


class TestPublishRollback:
    """发布失败时必须回滚已经写下的媒体文件。"""

    def test_failed_insert_removes_the_media_it_wrote(self, hall, png_bytes):
        # 故意漏掉 author_name，让 INSERT 抛 KeyError。
        broken = {'title': '海边', 'caption': '记录', 'style': 'film', 'topics': ['旅行']}

        with pytest.raises(KeyError):
            hall.publish('author', str(uuid.uuid4()), payload_fingerprint(broken), broken,
                         png_bytes())

        assert hall.list_posts('author')['total'] == 0
        assert not list(hall.media_directory.glob('*'))

    def test_publish_reuses_one_topic_row_per_normalized_name(self, hall, publish):
        publish(hall, topics=['Travel'])
        publish(hall, topics=['travel'])

        with hall.store.connect() as connection:
            assert connection.execute('SELECT COUNT(*) FROM hall_topics').fetchone()[0] == 1

    def test_publish_keeps_topic_order(self, hall, publish):
        record, _ = publish(hall, topics=['甲', '乙', '丙'])

        assert record['topics'] == ['甲', '乙', '丙']


# --------------------------------------------------------------------------- #
# 读取模型
# --------------------------------------------------------------------------- #

class TestPostLookup:
    """单篇读取：非法 id、已撤回、不存在都返回 None（上层再翻成 404）。"""

    @pytest.mark.parametrize('post_id', ['../../etc/passwd', 'nope', 'A' * 32, 'f' * 31, ''])
    def test_post_rejects_identifiers_outside_the_pattern(self, hall, post_id):
        assert hall.post(post_id) is None

    def test_post_returns_none_for_an_unknown_identifier(self, hall):
        assert hall.post('f' * 32) is None

    def test_post_hides_withdrawn_posts(self, hall, publish):
        record, _ = publish(hall)
        hall.withdraw(record['id'], 'author')

        assert hall.post(record['id']) is None


class TestListPosts:
    """列表读取：排序、分页、归属过滤、话题过滤、搜索。"""

    def test_list_posts_orders_newest_first(self, hall, publish):
        records = [publish(hall, title=f'第{index}篇')[0] for index in range(3)]
        with hall.store.connect() as connection:
            for offset, record in enumerate(records):
                connection.execute('UPDATE hall_posts SET created_at=? WHERE id=?',
                                   (1000 + offset, record['id']))

        titles = [post['title'] for post in hall.list_posts('author')['posts']]

        assert titles == ['第2篇', '第1篇', '第0篇']

    def test_list_posts_paginates_without_overlap(self, hall, publish):
        for index in range(5):
            publish(hall, title=f'第{index}篇')

        first = hall.list_posts('author', page=1, page_size=2)
        second = hall.list_posts('author', page=2, page_size=2)
        last = hall.list_posts('author', page=3, page_size=2)

        assert (first['total'], first['page_size']) == (5, 2)
        assert first['has_more'] is True and last['has_more'] is False
        assert len(first['posts']) == len(second['posts']) == 2 and len(last['posts']) == 1
        assert {post['id'] for post in first['posts']} \
            .isdisjoint({post['id'] for post in second['posts']})

    def test_list_posts_mine_filters_by_owner(self, hall, publish):
        publish(hall, owner='author')
        publish(hall, owner='other')

        assert hall.list_posts('author', mine=True)['total'] == 1
        assert hall.list_posts('author', mine=False)['total'] == 2

    def test_list_posts_topic_filter_uses_the_normalized_key(self, hall, publish):
        publish(hall, topics=['旅行'])

        assert hall.list_posts('author', topic='#旅行')['total'] == 1
        assert hall.list_posts('author', topic='美食')['total'] == 0

    def test_list_posts_search_treats_wildcards_literally(self, hall, publish):
        # % 和 _ 必须当普通字符，否则用户输入 % 会命中全部记录。
        publish(hall, title='进度 100% 达成')
        publish(hall, title='普通标题')

        assert hall.list_posts('author', query='%')['total'] == 1
        assert hall.list_posts('author', query='_')['total'] == 0

    def test_list_posts_search_matches_author_name(self, hall, publish):
        publish(hall, author_name='阿岛')

        assert hall.list_posts('author', query='阿岛')['total'] == 1
        assert hall.list_posts('author', query='不存在的人')['total'] == 0

    def test_list_posts_hides_withdrawn_posts(self, hall, publish):
        record, _ = publish(hall)
        hall.withdraw(record['id'], 'author')

        assert hall.list_posts('author')['total'] == 0


class TestTopics:
    """话题聚合：只统计在架手帐，按热度降序。"""

    def test_topics_counts_active_posts_ordered_by_popularity(self, hall, publish):
        publish(hall, topics=['旅行', '美食'])
        publish(hall, topics=['旅行'])

        assert hall.topics() == [{'name': '旅行', 'count': 2}, {'name': '美食', 'count': 1}]

    def test_topics_excludes_withdrawn_posts(self, hall, publish):
        record, _ = publish(hall, topics=['旅行'])
        hall.withdraw(record['id'], 'author')

        assert hall.topics() == []


class TestMedia:
    """媒体文件解析：只返回本目录下的真实文件。"""

    def test_media_returns_paths_for_image_and_thumbnail(self, hall, publish):
        record, _ = publish(hall)

        assert hall.media(record['id']).name == record['id'] + '.png'
        assert hall.media(record['id'], thumbnail=True).name == record['id'] + '.thumb.jpg'

    @pytest.mark.parametrize('post_id', ['f' * 32, 'nope', ''])
    def test_media_returns_none_for_unknown_or_invalid_ids(self, hall, post_id):
        assert hall.media(post_id) is None

    def test_media_returns_none_for_a_withdrawn_post(self, hall, publish):
        record, _ = publish(hall)
        hall.withdraw(record['id'], 'author')

        assert hall.media(record['id']) is None

    @pytest.mark.parametrize('inside_media_directory', [True, False])
    def test_media_rejects_symlinked_files(self, hall, publish, tmp_path,
                                           inside_media_directory):
        record, _ = publish(hall)
        path = hall.media(record['id'])
        target = (hall.media_directory if inside_media_directory else tmp_path) / 'other.png'
        target.write_bytes(path.read_bytes())
        path.unlink()
        try:
            path.symlink_to(target)
        except (OSError, NotImplementedError):
            pytest.skip('创建符号链接需要管理员权限或开发者模式')

        assert hall.media(record['id']) is None

    def test_media_rejects_a_tampered_filename_column(self, hall, publish):
        # 即使数据库里的文件名被改成越界路径，也不能读到目录外的文件。
        record, _ = publish(hall)
        with hall.store.connect() as connection:
            connection.execute('UPDATE hall_posts SET image_filename=? WHERE id=?',
                               ('../../config.py', record['id']))

        assert hall.media(record['id']) is None

    def test_media_returns_none_when_the_media_file_is_gone(self, hall, publish):
        # 磁盘上的文件被外部删掉时，接口要返回"找不到"，而不是抛异常。
        record, _ = publish(hall)
        hall.media(record['id']).unlink()

        assert hall.media(record['id']) is None


class TestWithdraw:
    """撤回：只有作者本人能撤回。"""

    def test_withdraw_hides_the_post(self, hall, publish):
        record, _ = publish(hall)

        hall.withdraw(record['id'], 'author')

        assert hall.post(record['id']) is None

    def test_withdraw_rejects_another_identity(self, hall, publish):
        record, _ = publish(hall)

        with pytest.raises(HallError) as error:
            hall.withdraw(record['id'], 'someone-else')

        assert error.value.status == 403
        assert hall.post(record['id']) is not None

    @pytest.mark.parametrize('post_id', ['f' * 32, 'not-an-id'])
    def test_withdraw_rejects_unknown_identifiers(self, hall, post_id):
        with pytest.raises(HallError) as error:
            hall.withdraw(post_id, 'author')

        assert error.value.status == 404

    def test_withdraw_is_idempotent(self, hall, publish):
        record, _ = publish(hall)
        hall.withdraw(record['id'], 'author')

        # 重复撤回不再报错，只是无事发生。
        assert hall.withdraw(record['id'], 'author') is None
