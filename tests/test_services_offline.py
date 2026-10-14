"""Service regressions with local images and mocked provider requests only."""

import base64
import io
import json
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest
import requests
from PIL import Image, ImageDraw
from PIL.ExifTags import Base, GPS, IFD
from PIL.TiffImagePlugin import IFDRational

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services import text_service, vision_service
from services.errors import GenerationError
from utils import image_utils


@pytest.fixture(autouse=True)
def offline_providers(monkeypatch):
    def blocked(*args, **kwargs):
        raise AssertionError("External requests are forbidden in offline tests")

    monkeypatch.setattr(requests, "post", blocked)
    monkeypatch.setattr(requests, "get", blocked)
    for service, name in ((vision_service, "VISION_CONFIG"), (text_service, "TEXT_CONFIG")):
        monkeypatch.setattr(service, name, {
            "url": "https://example.invalid/private-endpoint",
            "model": "offline-model",
            "api_key": "offline-secret-token",
        })


@pytest.fixture
def photo(tmp_path):
    path = tmp_path / "photo.png"
    with Image.new("RGB", (120, 80), "orange") as image:
        image.save(path)
    return str(path)


def _response(content="一篇已确认事实的手账"):
    response = Mock()
    response.json.return_value = {"choices": [{"message": {"content": content}}]}
    return response


def _invoke(stage, photo):
    if stage == "vision":
        return vision_service.analyze_image(photo)
    return text_service.generate_journal("照片里可见一碗面", None, [], None)


def test_generation_error_has_public_fields():
    error = GenerationError("请重试", "vision", retryable=False)
    assert str(error) == error.message == "请重试"
    assert error.stage == "vision"
    assert error.retryable is False


def test_image_encoding_rotates_resizes_and_removes_exif(tmp_path):
    path = tmp_path / "large.jpg"
    exif = Image.Exif()
    exif[Base.Orientation] = 6
    exif[Base.DateTime] = "2020:01:02 03:04:05"
    with Image.new("RGB", (3200, 1600), "blue") as image:
        ImageDraw.Draw(image).rectangle((0, 0, 1599, 1599), fill="red")
        image.save(path, quality=98, exif=exif)

    raw = base64.b64decode(vision_service.encode_image(str(path)))
    with Image.open(io.BytesIO(raw)) as encoded:
        assert encoded.format == "JPEG"
        assert encoded.size == (800, 1600)
        assert not encoded.getexif()
        assert encoded.getpixel((400, 200))[0] > 220
        assert encoded.getpixel((400, 1400))[2] > 220
    assert len(raw) < path.stat().st_size


def test_transparent_png_is_jpeg_with_white_background(tmp_path):
    path = tmp_path / "transparent.png"
    with Image.new("RGBA", (30, 20), (0, 0, 0, 0)) as image:
        image.save(path)
    raw = base64.b64decode(vision_service.encode_image(str(path)))
    with Image.open(io.BytesIO(raw)) as encoded:
        assert encoded.format == "JPEG"
        assert encoded.getpixel((10, 10)) == (255, 255, 255)


def test_vision_uses_jpeg_mime_and_bounded_request(monkeypatch, photo):
    post = Mock(return_value=_response("  可见橙色画面  "))
    monkeypatch.setattr(requests, "post", post)
    assert vision_service.analyze_image(photo) == "可见橙色画面"
    kwargs = post.call_args.kwargs
    assert kwargs["timeout"] == 60
    content = kwargs["json"]["messages"][0]["content"]
    image_url = next(part["image_url"]["url"] for part in content if part["type"] == "image_url")
    assert image_url.startswith("data:image/jpeg;base64,")
    with Image.open(io.BytesIO(base64.b64decode(image_url.split(",", 1)[1]))) as uploaded:
        assert uploaded.format == "JPEG"
    assert "不要推断人物身份" in content[-1]["text"]


def test_batch_timeout_has_no_serial_fallback(monkeypatch, photo, caplog):
    post = Mock(side_effect=requests.Timeout("https://example.invalid/private-endpoint offline-secret-token"))
    monkeypatch.setattr(requests, "post", post)
    with pytest.raises(GenerationError, match="照片识别超时") as caught:
        vision_service.analyze_images_batch([photo, photo, photo])
    assert caught.value.stage == "vision"
    assert caught.value.retryable is True
    assert post.call_count == 1
    assert post.call_args.kwargs["timeout"] == 60
    assert "private-endpoint" not in caplog.text
    assert "offline-secret-token" not in caplog.text


def test_analyze_images_uses_one_labeled_batch(monkeypatch, photo):
    post = Mock(return_value=_response("照片1：橙色。照片2：橙色。"))
    monkeypatch.setattr(requests, "post", post)
    assert "照片1" in vision_service.analyze_images([photo, photo])
    assert post.call_count == 1
    content = post.call_args.kwargs["json"]["messages"][0]["content"]
    assert sum(part["type"] == "image_url" for part in content) == 2
    assert "不假定在同一天或同一地点" in content[-1]["text"]


def test_empty_image_sets_do_not_call_provider():
    assert vision_service.analyze_image("") == ""
    assert vision_service.analyze_images([]) == ""
    assert vision_service.analyze_images_batch([]) == ""


def test_unreadable_photo_is_an_error_before_provider(tmp_path):
    path = tmp_path / "invalid.jpg"
    path.write_bytes(b"not an image")
    with pytest.raises(GenerationError, match="照片无法读取") as caught:
        vision_service.analyze_image(str(path))
    assert caught.value.stage == "vision"
    assert caught.value.retryable is False


@pytest.mark.parametrize("stage", ["vision", "writing"])
@pytest.mark.parametrize("content", [None, "", " \n ", [], {"text": "bad shape"}])
def test_empty_or_malformed_content_is_not_success(monkeypatch, photo, stage, content):
    monkeypatch.setattr(requests, "post", Mock(return_value=_response(content)))
    with pytest.raises(GenerationError) as caught:
        _invoke(stage, photo)
    assert caught.value.stage == stage
    assert caught.value.retryable is True
    assert "请重试" in caught.value.message


@pytest.mark.parametrize("stage", ["vision", "writing"])
@pytest.mark.parametrize("body", [{}, {"choices": []}, {"choices": [{}]}, []])
def test_invalid_response_schema_is_an_error(monkeypatch, photo, stage, body):
    response = _response()
    response.json.return_value = body
    monkeypatch.setattr(requests, "post", Mock(return_value=response))
    with pytest.raises(GenerationError) as caught:
        _invoke(stage, photo)
    assert caught.value.stage == stage


@pytest.mark.parametrize("stage", ["vision", "writing"])
def test_invalid_json_is_an_error(monkeypatch, photo, stage):
    response = _response()
    response.json.side_effect = ValueError("private provider response")
    monkeypatch.setattr(requests, "post", Mock(return_value=response))
    with pytest.raises(GenerationError) as caught:
        _invoke(stage, photo)
    assert caught.value.stage == stage
    assert "private" not in str(caught.value)


@pytest.mark.parametrize("stage", ["vision", "writing"])
def test_http_failure_does_not_leak_provider_details(monkeypatch, photo, stage, caplog):
    response = _response()
    response.raise_for_status.side_effect = requests.HTTPError(
        "https://example.invalid/private-endpoint offline-secret-token"
    )
    monkeypatch.setattr(requests, "post", Mock(return_value=response))
    with pytest.raises(GenerationError) as caught:
        _invoke(stage, photo)
    assert caught.value.stage == stage
    assert "private-endpoint" not in str(caught.value) + caplog.text
    assert "offline-secret-token" not in str(caught.value) + caplog.text
    response.json.assert_not_called()


def test_writing_timeout_raises_instead_of_error_text(monkeypatch):
    post = Mock(side_effect=requests.Timeout("private endpoint"))
    monkeypatch.setattr(requests, "post", post)
    with pytest.raises(GenerationError, match="手账生成超时") as caught:
        text_service.generate_journal("照片中可见建筑", None, [], None)
    assert caught.value.stage == "writing"
    assert caught.value.retryable is True
    assert post.call_args.kwargs["timeout"] == 60


def _invoke_writing(operation):
    if operation == "generate":
        return text_service.generate_journal("离线测试中的照片描述", None, [], None)
    return text_service.regenerate_journal("离线原稿\n\n一段已经记录的经历。", "healing")


def _http_response(status, provider_code=None):
    """Use Requests' actual HTTPError, including its bound response and URL."""
    response = requests.Response()
    response.status_code = status
    response.url = "https://example.invalid/private-endpoint?token=offline-secret-token"
    response.reason = "Offline provider failure"
    response.headers["Content-Type"] = "application/json"
    response._content = json.dumps({"error": {
        "code": provider_code,
        "message": "private-provider-body-do-not-expose offline-secret-token",
    }}).encode("utf-8")
    response.request = requests.Request("POST", response.url, headers={
        "Authorization": "Bearer offline-secret-token",
    }).prepare()
    return response


@pytest.mark.parametrize("operation", ["generate", "regenerate"])
@pytest.mark.parametrize("status,provider_code,expected", [
    (404, "ModelArts.81009", "文字生成模型或接口不可用，请更新服务配置后重试。"),
    (404, None, "文字生成模型或接口不可用，请更新服务配置后重试。"),
    (403, "ModelArts.81004", "文字生成服务尚未开通，请先开通当前模型后重试。"),
    (403, "ModelArts.81005", "文字生成服务拒绝了请求，请检查服务权限或账号状态后重试。"),
    (401, None, "文字生成服务认证失败，请检查服务配置后重试。"),
    (402, None, "文字生成服务余额不足，请充值后重试。"),
    (429, None, "文字生成请求过于频繁，请稍后重试。"),
    (500, None, "文字生成服务暂时不可用，请稍后重试。"),
    (503, None, "文字生成服务暂时不可用，请稍后重试。"),
    (400, None, "手账生成暂时失败，请重试"),
])
def test_writing_http_errors_are_actionable_safe_and_keep_retry(monkeypatch, caplog,
                                                               operation, status, provider_code, expected):
    post = Mock(return_value=_http_response(status, provider_code))
    monkeypatch.setattr(requests, "post", post)
    with pytest.raises(GenerationError) as caught:
        _invoke_writing(operation)
    assert caught.value.stage == "writing"
    assert caught.value.message == expected
    # Fixing configuration must let an existing job retry only the writing step.
    assert caught.value.retryable is True
    assert post.call_count == 1
    exposed = str(caught.value) + caplog.text
    for sensitive in ("https://example.invalid", "private-endpoint", "offline-secret-token",
                      "private-provider-body-do-not-expose"):
        assert sensitive not in exposed


@pytest.mark.parametrize("operation", ["generate", "regenerate"])
@pytest.mark.parametrize("error_type", [requests.ConnectionError, requests.exceptions.ProxyError,
                                        requests.exceptions.SSLError])
def test_writing_connection_failures_are_safe_and_do_not_retry_internally(monkeypatch, caplog,
                                                                        operation, error_type):
    post = Mock(side_effect=error_type(
        "https://example.invalid/private-endpoint offline-secret-token private-network-details"
    ))
    monkeypatch.setattr(requests, "post", post)
    with pytest.raises(GenerationError) as caught:
        _invoke_writing(operation)
    assert caught.value.message == "手账生成暂时失败，请重试"
    assert caught.value.stage == "writing"
    assert caught.value.retryable is True
    assert post.call_count == 1
    exposed = str(caught.value) + caplog.text
    for sensitive in ("https://example.invalid", "private-endpoint", "offline-secret-token",
                      "private-network-details"):
        assert sensitive not in exposed


@pytest.mark.parametrize("operation", ["generate", "regenerate"])
def test_requests_json_decode_error_is_a_response_error_not_a_connection_error(monkeypatch, caplog,
                                                                               operation):
    response = requests.Response()
    response.status_code = 200
    response.url = "https://example.invalid/private-endpoint"
    response.headers["Content-Type"] = "text/html"
    response._content = b"<html>private-provider-body-do-not-expose offline-secret-token</html>"
    post = Mock(return_value=response)
    monkeypatch.setattr(requests, "post", post)
    with pytest.raises(GenerationError) as caught:
        _invoke_writing(operation)
    assert caught.value.message == "手账生成结果异常，请重试"
    assert caught.value.stage == "writing"
    assert caught.value.retryable is True
    assert post.call_count == 1
    exposed = str(caught.value) + caplog.text
    for sensitive in ("https://example.invalid", "private-endpoint", "offline-secret-token",
                      "private-provider-body-do-not-expose"):
        assert sensitive not in exposed


@pytest.mark.parametrize("operation", ["generate", "regenerate"])
def test_writing_sends_configured_thinking_disabled_without_changing_prompts(monkeypatch, operation):
    monkeypatch.setitem(text_service.TEXT_CONFIG, "thinking", {"type": "disabled"})
    post = Mock(return_value=_response("已完成的离线测试正文"))
    monkeypatch.setattr(requests, "post", post)
    assert _invoke_writing(operation) == "已完成的离线测试正文"
    assert post.call_count == 1
    payload = post.call_args.kwargs["json"]
    assert payload["thinking"] == {"type": "disabled"}
    assert payload["messages"][0]["role"] == "system"
    assert "真实性规则" in payload["messages"][0]["content"]
    if operation == "regenerate":
        assert "不增加新事实" in payload["messages"][0]["content"]


@pytest.mark.parametrize("operation", ["generate", "regenerate"])
def test_writing_missing_authentication_fails_before_request(monkeypatch, caplog, operation):
    monkeypatch.setitem(text_service.TEXT_CONFIG, "api_key", "")
    post = Mock()
    monkeypatch.setattr(requests, "post", post)
    with pytest.raises(GenerationError) as caught:
        _invoke_writing(operation)
    assert caught.value.message == "文字生成服务认证失败，请检查服务配置后重试。"
    assert caught.value.stage == "writing"
    assert caught.value.retryable is True
    post.assert_not_called()
    exposed = str(caught.value) + caplog.text
    assert "private-endpoint" not in exposed
    assert "offline-secret-token" not in exposed


def test_user_place_and_date_replace_conflicting_automatic_metadata(monkeypatch):
    post = Mock(return_value=_response())
    monkeypatch.setattr(requests, "post", post)
    text_service.generate_journal(
        "一张旅行照片", "自动识别错误地点", [{"name": "错误地点的附近景点"}],
        "2000-01-01 09:00:00", location="用户确认地点", date="2026-10-10", weather="小雨",
    )
    messages = post.call_args.kwargs["json"]["messages"]
    context = messages[1]["content"]
    assert "用户确认地点" in context
    assert "2026-10-10" in context
    assert "小雨" in context
    assert "自动识别错误地点" not in context
    assert "2000-01-01" not in context
    assert "错误地点的附近景点" not in context
    assert "不编造具体拍摄时间" in messages[0]["content"]


def test_nearby_places_are_explicitly_unconfirmed(monkeypatch):
    post = Mock(return_value=_response())
    monkeypatch.setattr(requests, "post", post)
    text_service.generate_journal("蓝天与建筑", "自动地点", [{"name": "附近公园"}], None)
    messages = post.call_args.kwargs["json"]["messages"]
    assert "未证明用户到访，默认不加入正文" in messages[1]["content"]
    assert "不得写成去过、打卡、看过或吃过" in messages[0]["content"]


def test_rewriting_cannot_add_new_facts(monkeypatch):
    post = Mock(return_value=_response("改写正文"))
    monkeypatch.setattr(requests, "post", post)
    original = "2026-10-10，我在杭州记录了一场小雨。"
    assert text_service.regenerate_journal(original, "magazine") == "改写正文"
    messages = post.call_args.kwargs["json"]["messages"]
    assert original in messages[1]["content"]
    assert "不增加新事实" in messages[0]["content"]
    assert "不要加入原稿没有的文化历史" in messages[1]["content"]


def _metadata_photo(tmp_path, lat_ref="S", lng_ref="W", latitude=(33, 52, 0)):
    path = tmp_path / "metadata.jpg"
    exif = Image.Exif()
    exif[IFD.GPSInfo] = {
        GPS.GPSLatitudeRef: lat_ref,
        GPS.GPSLatitude: tuple(IFDRational(value) for value in latitude),
        GPS.GPSLongitudeRef: lng_ref,
        GPS.GPSLongitude: tuple(IFDRational(value) for value in (151, 12, 0)),
    }
    exif[IFD.Exif] = {Base.DateTimeOriginal: "2026:10:09 08:07:06"}
    exif[Base.DateTime] = "2020:01:01 00:00:00"
    with Image.new("RGB", (30, 20), "green") as image:
        image.save(path, exif=exif)
    return str(path)


def test_modern_exif_reads_nested_gps_and_original_time_and_closes_files(monkeypatch, tmp_path):
    path = _metadata_photo(tmp_path)
    real_open = Image.open
    opened = []

    def tracked_open(*args, **kwargs):
        image = real_open(*args, **kwargs)
        opened.append(image)
        return image

    monkeypatch.setattr(Image, "open", tracked_open)
    assert image_utils.extract_gps(path) == pytest.approx((-33.8666667, -151.2))
    assert image_utils.extract_datetime(path) == "2026-10-09 08:07:06"
    assert opened and all(image.fp is None for image in opened)


def test_invalid_gps_reference_and_range_are_ignored(tmp_path):
    assert image_utils.extract_gps(_metadata_photo(tmp_path, lat_ref="X")) is None
    assert image_utils.extract_gps(_metadata_photo(tmp_path, latitude=(100, 0, 0))) is None


def test_invalid_original_time_falls_back_to_file_time(tmp_path):
    path = tmp_path / "fallback.jpg"
    exif = Image.Exif()
    exif[IFD.Exif] = {Base.DateTimeOriginal: "not a date"}
    exif[Base.DateTime] = "2026:10:10 11:12:13"
    with Image.new("RGB", (20, 20)) as image:
        image.save(path, exif=exif)
    assert image_utils.extract_datetime(str(path)) == "2026-10-10 11:12:13"


def test_optional_exif_handles_missing_files_and_plain_photos(photo, tmp_path):
    assert image_utils.extract_gps(photo) is None
    assert image_utils.extract_datetime(photo) is None
    missing = str(tmp_path / "missing.jpg")
    assert image_utils.extract_gps(missing) is None
    assert image_utils.extract_datetime(missing) is None
