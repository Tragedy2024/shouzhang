"""核心函数单元测试：``services.vision_service``。

被测单元
--------
``encode_image``          图片 → 旋转校正、限幅缩放、去 EXIF 的 JPEG base64
``_image_content``        打包成 OpenAI 兼容的 image_url 内容块
``_request_description``  一次视觉调用 + 异常翻译
``analyze_image``         单张照片的描述
``analyze_images_batch``  多张照片合并成**一次**请求

打桩策略
--------
图片处理是纯 Pillow 操作，用真实图片验证（这才是它的价值所在）；
只有 ``requests.post`` 用 ``unittest.mock`` 打桩——单元测试绝不调用付费模型。
"""

import base64
import io
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import requests
from PIL import Image
from PIL.ExifTags import Base

from services.errors import GenerationError
from services.vision_service import (
    MAX_IMAGE_SIDE,
    VISION_RULES,
    _image_content,
    _request_description,
    analyze_image,
    analyze_images,
    analyze_images_batch,
    encode_image,
)


@pytest.fixture
def http_post(monkeypatch):
    """把 ``requests.post`` 换成 Mock，返回 (调用桩, 响应桩)。"""
    response = Mock()
    response.status_code = 200
    response.raise_for_status.return_value = None
    poster = Mock(return_value=response)
    monkeypatch.setattr(requests, 'post', poster)
    return SimpleNamespace(post=poster, response=response)


def reply(text):
    return {'choices': [{'message': {'content': text}}]}


def write_image(tmp_path, name='photo.jpg', size=(60, 40), color='red',
                mode='RGB', fmt='JPEG', exif=None):
    """写一张真实图片到临时目录，返回路径。

    只在 ``exif`` 非 None 时才把它交给 Pillow：显式传 ``exif=None`` 会被当作
    "指定了一个空的 EXIF 块"，保存时对 None 求长度而报 ``TypeError``。
    """
    path = tmp_path / name
    options = {} if exif is None else {'exif': exif}
    Image.new(mode, size, color).save(path, fmt, **options)
    return path


def decoded(encoded):
    """把 base64 还原成 PIL 图片（调用方负责关闭）。"""
    return Image.open(io.BytesIO(base64.b64decode(encoded)))


class TestEncodeImage:
    """图片规范化：给模型的永远是一张干净的、不过大的 JPEG。"""

    def test_encode_image_returns_decodable_jpeg_base64(self, tmp_path):
        encoded = encode_image(str(write_image(tmp_path)))

        assert base64.b64decode(encoded)[:3] == b'\xff\xd8\xff'   # JPEG SOI
        with decoded(encoded) as image:
            assert image.format == 'JPEG'

    def test_encode_image_downscales_oversized_photos(self, tmp_path):
        # 3200x800 缩到长边 1600，比例保持不变。
        path = write_image(tmp_path, size=(3200, 800))

        with decoded(encode_image(str(path))) as image:
            assert image.width == MAX_IMAGE_SIDE
            assert image.height == round(800 * MAX_IMAGE_SIDE / 3200)

    def test_encode_image_keeps_small_photos_at_native_size(self, tmp_path):
        path = write_image(tmp_path, size=(120, 80))

        with decoded(encode_image(str(path))) as image:
            assert (image.width, image.height) == (120, 80)

    def test_encode_image_applies_exif_orientation(self, tmp_path):
        # 手机竖拍的照片方向信息在 EXIF 里；不校正的话模型看到的是躺倒的画面。
        exif = Image.Exif()
        exif[Base.Orientation] = 6
        path = write_image(tmp_path, size=(60, 40), exif=exif)

        with decoded(encode_image(str(path))) as image:
            assert (image.width, image.height) == (40, 60)

    def test_encode_image_strips_private_metadata(self, tmp_path):
        # 送出去的照片不能带上拍摄时间、GPS 这些隐私信息。
        exif = Image.Exif()
        exif[Base.DateTimeOriginal] = '2026:10:01 08:30:00'
        path = write_image(tmp_path, exif=exif)

        with decoded(encode_image(str(path))) as image:
            assert not image.getexif()

    def test_encode_image_flattens_transparency_onto_white(self, tmp_path):
        # PNG 的透明区域转 JPEG 会变黑，必须先铺一层白底。
        path = write_image(tmp_path, name='clear.png', size=(20, 20), color=(0, 0, 0, 0),
                           mode='RGBA', fmt='PNG')

        with decoded(encode_image(str(path))) as image:
            assert image.mode == 'RGB'
            assert image.getpixel((10, 10)) == (255, 255, 255)

    def test_encode_image_converts_png_to_jpeg(self, tmp_path):
        path = write_image(tmp_path, name='shot.png', size=(30, 30), mode='RGB', fmt='PNG')

        with decoded(encode_image(str(path))) as image:
            assert image.format == 'JPEG'

    def test_encode_image_raises_for_an_unreadable_file(self, tmp_path):
        broken = tmp_path / 'broken.jpg'
        broken.write_bytes(b'definitely not an image')

        with pytest.raises(Exception):
            encode_image(str(broken))


class TestImageContent:
    """内容块打包：data URI 前缀不能错，读不了的图要变成不可重试错误。"""

    def test_image_content_wraps_the_jpeg_as_a_data_uri(self, tmp_path):
        content = _image_content(str(write_image(tmp_path)))

        assert content['type'] == 'image_url'
        assert content['image_url']['url'].startswith('data:image/jpeg;base64,')

    def test_image_content_reports_an_unreadable_photo_as_permanent(self, tmp_path):
        broken = tmp_path / 'broken.jpg'
        broken.write_bytes(b'definitely not an image')

        with pytest.raises(GenerationError) as error:
            _image_content(str(broken))

        # 照片本身坏了，重试多少次都一样，必须标成不可重试。
        assert (error.value.stage, error.value.retryable) == ('vision', False)
        assert error.value.message == '照片无法读取，请重新上传'


class TestRequestDescription:
    """视觉调用：异常一律翻译成可重试的安全错误。"""

    def test_request_description_returns_the_description(self, http_post):
        http_post.response.json.return_value = reply('  海面和一条船。 ')

        assert _request_description([{'type': 'text', 'text': '描述'}], 1000) == '海面和一条船。'

    def test_request_description_sends_model_and_token_budget(self, http_post):
        http_post.response.json.return_value = reply('描述')

        _request_description([{'type': 'text', 'text': '描述'}], 2000)

        payload = http_post.post.call_args.kwargs['json']
        assert payload['max_tokens'] == 2000
        assert payload['messages'][0]['role'] == 'user'
        assert http_post.post.call_args.kwargs['timeout'] == 60

    def test_request_description_times_out_as_retryable(self, http_post):
        http_post.post.side_effect = requests.Timeout('太慢了')

        with pytest.raises(GenerationError) as error:
            _request_description([], 1000)

        assert (error.value.message, error.value.retryable) == ('照片识别超时，请重试', True)

    def test_request_description_handles_transport_failure(self, http_post):
        http_post.post.side_effect = requests.ConnectionError('断网了')

        with pytest.raises(GenerationError) as error:
            _request_description([], 1000)

        assert error.value.message == '照片识别暂时失败，请重试'

    def test_request_description_handles_an_unusable_body(self, http_post):
        http_post.response.json.return_value = {'choices': []}

        with pytest.raises(GenerationError) as error:
            _request_description([], 1000)

        assert error.value.message == '照片识别结果异常，请重试'


class TestAnalyzeImage:
    """单张照片：空输入直接返回空串，不浪费一次调用。"""

    def test_analyze_image_returns_empty_for_a_blank_path(self, http_post):
        assert analyze_image('') == ''
        http_post.post.assert_not_called()

    def test_analyze_image_sends_the_photo_with_the_prompt_rules(self, http_post, tmp_path):
        http_post.response.json.return_value = reply('海面和一条船。')

        assert analyze_image(str(write_image(tmp_path))) == '海面和一条船。'

        content = http_post.post.call_args.kwargs['json']['messages'][0]['content']
        assert content[0]['type'] == 'image_url'
        assert VISION_RULES in content[1]['text']
        assert http_post.post.call_args.kwargs['json']['max_tokens'] == 1000


class TestAnalyzeImagesBatch:
    """多张照片：合并成一次请求，编号清晰，失败可整批重试。"""

    def test_analyze_images_batch_returns_empty_for_no_photos(self, http_post):
        assert analyze_images_batch([]) == ''
        http_post.post.assert_not_called()

    def test_analyze_images_batch_delegates_a_single_photo(self, http_post, tmp_path):
        http_post.response.json.return_value = reply('一张照片')

        assert analyze_images_batch([str(write_image(tmp_path))]) == '一张照片'

        # 单张走 ``analyze_image`` 的提示词，max_tokens 是 1000 而不是 2000。
        payload = http_post.post.call_args.kwargs['json']
        assert payload['max_tokens'] == 1000
        assert '请描述这张旅行照片' in payload['messages'][0]['content'][1]['text']

    def test_analyze_images_batch_sends_one_request_for_many_photos(self, http_post, tmp_path):
        http_post.response.json.return_value = reply('三张照片')
        paths = [str(write_image(tmp_path, name=f'photo-{index}.jpg')) for index in range(3)]

        analyze_images_batch(paths)

        # 关键性能与成本约束：N 张照片只发 1 次请求。
        assert http_post.post.call_count == 1
        assert http_post.post.call_args.kwargs['json']['max_tokens'] == 2000

    def test_analyze_images_batch_numbers_each_photo(self, http_post, tmp_path):
        http_post.response.json.return_value = reply('三张照片')
        paths = [str(write_image(tmp_path, name=f'photo-{index}.jpg')) for index in range(3)]

        analyze_images_batch(paths)

        content = http_post.post.call_args.kwargs['json']['messages'][0]['content']
        labels = [block['text'] for block in content if block['type'] == 'text']
        assert labels[:3] == ['照片1：', '照片2：', '照片3：']
        assert '以上是3张旅行照片' in labels[-1]
        assert VISION_RULES in labels[-1]
        # 3 个编号 + 3 张图 + 1 段总结（图片块在编号之后交替出现）。
        assert len(content) == 7

    def test_analyze_images_batch_propagates_a_broken_photo(self, http_post, tmp_path):
        broken = tmp_path / 'broken.jpg'
        broken.write_bytes(b'not an image')

        with pytest.raises(GenerationError):
            analyze_images_batch([str(write_image(tmp_path)), str(broken)])

        http_post.post.assert_not_called()

    def test_analyze_images_is_an_alias_for_the_batch_entry_point(self, http_post, tmp_path):
        http_post.response.json.return_value = reply('两张照片')
        paths = [str(write_image(tmp_path, name=f'photo-{index}.jpg')) for index in range(2)]

        assert analyze_images(paths) == analyze_images_batch(paths)
