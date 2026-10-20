"""核心函数单元测试：``utils.image_utils``。

被测单元
--------
``_convert_to_degrees``  EXIF 度分秒有理数 → 十进制度的换算与合法性校验
``_reference``           半球参考字符（``b'N'`` → ``'N'``）的解码
``extract_gps``          从图片 EXIF 读出可用的 WGS84 坐标
``extract_datetime``     从图片 EXIF 读出拍摄时间

测试写法说明
------------
前两个是纯函数，直接喂参数断言返回值与异常即可。
后两个要做真实 I/O，所以用 ``IFDRational`` 现造一张带 GPS EXIF 的 JPEG——
这样验证的是"PIL 写进去、我们的代码读出来"的完整往返，而不是 mock 出来的
假 EXIF 字典。所有失败路径都必须返回 ``None``，绝不能把异常抛到流水线上。
"""

import datetime
import io

import pytest
from PIL import Image
from PIL.ExifTags import Base, GPS, IFD
from PIL.TiffImagePlugin import IFDRational

from utils.image_utils import _convert_to_degrees, _reference, extract_datetime, extract_gps


def rational(value):
    """EXIF 的度分秒是"分子/分母"有理数，不能直接塞 int。"""
    return IFDRational(value, 1)


def build_jpeg(size=(40, 30), gps=None, timestamp=None, extra_exif=None):
    """造一张带指定 EXIF 的 JPEG，返回 ``BytesIO``（可直接喂给被测函数）。"""
    exif = Image.Exif()
    if gps is not None:
        latitude, longitude, lat_ref, lng_ref = gps
        exif[IFD.GPSInfo] = {
            GPS.GPSLatitudeRef: lat_ref,
            GPS.GPSLatitude: tuple(rational(part) for part in latitude),
            GPS.GPSLongitudeRef: lng_ref,
            GPS.GPSLongitude: tuple(rational(part) for part in longitude),
        }
    if timestamp is not None:
        exif[Base.DateTimeOriginal] = timestamp
    for tag, value in (extra_exif or {}).items():
        exif[tag] = value
    buffer = io.BytesIO()
    Image.new('RGB', size, 'red').save(buffer, 'JPEG', exif=exif)
    return buffer


class TestConvertToDegrees:
    """度分秒 → 十进制：只接受合法的非负分量。"""

    @pytest.mark.parametrize('parts,expected', [
        ((30, 30, 0), 30.5),
        ((120, 15, 0), 120.25),
        ((0, 0, 0), 0.0),
        ((39, 54, 55), 39 + 54 / 60 + 55 / 3600),
        ((30.5, 0, 0), 30.5),          # 已经是十进制的度
        ((40, 30, 30.5), 40 + 30 / 60 + 30.5 / 3600),   # 小数秒
    ])
    def test_convert_to_degrees_decodes_valid_rationals(self, parts, expected):
        assert _convert_to_degrees(parts) == pytest.approx(expected)

    def test_convert_to_degrees_accepts_exif_rationals(self):
        # 真实 EXIF 里是 IFDRational，不是 float，两种都要能处理。
        assert _convert_to_degrees([rational(30), rational(30), rational(0)]) == pytest.approx(30.5)

    @pytest.mark.parametrize('parts', [
        (30, 60, 0),        # 分不能等于 60
        (30, 0, 60),        # 秒不能等于 60
        (30, 75, 0),
        (30, -1, 0),
        (-30, 0, 0),        # 度必须非负（正负号由 ref 决定）
        (float('nan'), 0, 0),
        (float('inf'), 0, 0),
        (30, 0, float('-inf')),
    ])
    def test_convert_to_degrees_rejects_invalid_components(self, parts):
        with pytest.raises(ValueError, match='Invalid GPS coordinates'):
            _convert_to_degrees(parts)

    def test_convert_to_degrees_rejects_a_malformed_triple(self):
        # 少于 3 个分量时解包就失败了，调用方靠 except 兜住。
        with pytest.raises((ValueError, TypeError)):
            _convert_to_degrees((30, 30))


class TestReference:
    """半球参考字符解码：EXIF 里既可能是 bytes 也可能是 str。"""

    def test_reference_decodes_bytes(self):
        assert _reference(b'N') == 'N'

    def test_reference_passes_through_text(self):
        assert _reference('E') == 'E'


class TestExtractGps:
    """GPS 读取：合法坐标转成十进制度，任何异常都降级为 None。"""

    def test_extract_gps_returns_decimal_degrees(self):
        image = build_jpeg(gps=((30, 30, 0), (120, 15, 0), 'N', 'E'))

        assert extract_gps(image) == pytest.approx((30.5, 120.25))

    def test_extract_gps_negates_southern_and_western_hemispheres(self):
        image = build_jpeg(gps=((30, 30, 0), (120, 15, 0), 'S', 'W'))

        assert extract_gps(image) == pytest.approx((-30.5, -120.25))

    def test_extract_gps_returns_none_without_gps_exif(self):
        assert extract_gps(build_jpeg()) is None

    def test_extract_gps_returns_none_for_an_unknown_hemisphere(self):
        # 半球不是 N/S 就无从判断正负号，宁可放弃也不要猜。
        assert extract_gps(build_jpeg(gps=((30, 30, 0), (120, 15, 0), 'X', 'E'))) is None
        assert extract_gps(build_jpeg(gps=((30, 30, 0), (120, 15, 0), 'N', 'X'))) is None

    def test_extract_gps_returns_none_for_out_of_range_values(self):
        assert extract_gps(build_jpeg(gps=((200, 0, 0), (120, 0, 0), 'N', 'E'))) is None
        assert extract_gps(build_jpeg(gps=((30, 0, 0), (200, 0, 0), 'N', 'E'))) is None

    def test_extract_gps_returns_none_for_a_missing_file(self, tmp_path):
        assert extract_gps(str(tmp_path / 'missing.jpg')) is None

    def test_extract_gps_returns_none_for_a_corrupt_file(self, tmp_path):
        broken = tmp_path / 'broken.jpg'
        broken.write_bytes(b'definitely not a jpeg')

        assert extract_gps(str(broken)) is None

    def test_extract_gps_returns_none_for_a_non_image_path(self, tmp_path):
        assert extract_gps(str(tmp_path)) is None


class TestExtractDatetime:
    """拍摄时间读取：优先 DateTimeOriginal，其次 DateTime，统一输出格式。"""

    def test_extract_datetime_normalizes_the_exif_format(self):
        image = build_jpeg(timestamp='2026:10:01 08:30:00')

        assert extract_datetime(image) == '2026-10-01 08:30:00'

    def test_extract_datetime_prefers_datetime_original(self):
        # 两个标签同时存在时，DateTimeOriginal 才是真正的拍摄时间。
        image = build_jpeg(timestamp='2026:10:01 08:30:00',
                           extra_exif={Base.DateTime: '2020:01:01 00:00:00'})

        assert extract_datetime(image) == '2026-10-01 08:30:00'

    def test_extract_datetime_falls_back_to_datetime(self):
        image = build_jpeg(extra_exif={Base.DateTime: '2020:05:06 07:08:09'})

        assert extract_datetime(image) == '2020-05-06 07:08:09'

    @pytest.mark.parametrize('value', ['not a date', '2026-10-01 08:30:00', '2026:13:45 99:99:99'])
    def test_extract_datetime_skips_unparseable_values(self, value):
        assert extract_datetime(build_jpeg(timestamp=value)) is None

    def test_extract_datetime_returns_none_without_exif(self):
        assert extract_datetime(build_jpeg()) is None

    def test_extract_datetime_returns_none_for_a_missing_file(self, tmp_path):
        assert extract_datetime(str(tmp_path / 'missing.jpg')) is None

    def test_extract_datetime_returns_none_for_a_corrupt_file(self, tmp_path):
        broken = tmp_path / 'broken.jpg'
        broken.write_bytes(b'definitely not a jpeg')

        assert extract_datetime(str(broken)) is None

    def test_extract_datetime_round_trips_a_real_timestamp(self):
        # 端到端确认：写进去的时间能原样（格式归一后）读回来。
        now = datetime.datetime(2026, 10, 14, 21, 5, 0)

        image = build_jpeg(timestamp=now.strftime('%Y:%m:%d %H:%M:%S'))

        assert extract_datetime(image) == now.strftime('%Y-%m-%d %H:%M:%S')

    def test_extract_datetime_decodes_a_byte_string_timestamp(self):
        # 有些相机/工具把 ASCII 标签写成 raw bytes 而不是 str，两种都要认。
        assert extract_datetime(build_jpeg(timestamp=b'2026:10:01 08:30:00')) == \
            '2026-10-01 08:30:00'
