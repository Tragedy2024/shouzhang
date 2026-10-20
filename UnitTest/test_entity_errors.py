"""实体类单元测试：异常实体。

被测单元
--------
``GenerationError``       生成流水线的"安全错误"——只携带可展示给用户的
                          ``message`` / ``stage`` / ``retryable``，不泄漏供应商细节。
                          （定义于 ``services/errors.py``）
``HallError``             公共大厅的 HTTP 语义错误——多携带一个 ``status``。
                          （定义于 ``services/hall_service.py``，与大厅路由同处一模块）
``read_generated_text``   把模型返回的 HTTP 响应校验成可用文本。

测试写法说明
------------
- 测试函数名统一为 ``test_<被测对象>_<场景>``，一个函数只断言一个行为，
  失败时从名字就能定位问题。
- 用 ``pytest.raises`` 断言异常类型，再读 ``error.value`` 断言属性。
- 外部依赖只有"一个 HTTP 响应对象"，用 ``unittest.mock.Mock`` 造替身，
  本模块因此不需要任何真实网络或文件。
"""

import pytest
import requests
from unittest.mock import Mock

from services.errors import GenerationError, read_generated_text
from services.hall_service import HallError


def fake_response(payload=None, status_code=200):
    """构造一个最小的 ``requests.Response`` 替身。

    ``Mock`` 的默认属性访问会返回子 Mock，容易写出"假通过"的断言，
    所以这里把用得到的三个成员显式钉死：``status_code`` / ``json`` /
    ``raise_for_status``。
    """
    response = Mock()
    response.status_code = status_code
    response.json.return_value = payload
    if status_code >= 400:
        response.raise_for_status.side_effect = requests.HTTPError(response=response)
    else:
        response.raise_for_status.return_value = None
    return response


def chat_payload(content):
    """包一层 OpenAI 兼容的 chat-completion 响应结构。"""
    return {'choices': [{'message': {'content': content}}]}


class TestGenerationError:
    """生成错误实体：三个字段的可读性与默认值。"""

    def test_generation_error_exposes_message_stage_and_retryable(self):
        error = GenerationError('照片分析未完成', 'vision', True)

        assert error.message == '照片分析未完成'
        assert error.stage == 'vision'
        assert error.retryable is True
        # 继承自 Exception，str() 应当就是给用户看的 message。
        assert str(error) == '照片分析未完成'

    def test_generation_error_defaults_to_retryable(self):
        # 绝大多数生成失败都是"再试一次就好"，因此默认值必须是 True。
        assert GenerationError('手账生成超时', 'writing').retryable is True

    def test_generation_error_can_mark_a_failure_as_permanent(self):
        # 照片本身读不出来时，重试没有意义，必须显式标成不可重试。
        assert GenerationError('照片无法读取', 'vision', False).retryable is False

    def test_generation_error_is_catchable_as_exception(self):
        with pytest.raises(GenerationError):
            raise GenerationError('失败', 'writing')


class TestHallError:
    """大厅错误实体：默认 status=400，可显式升级为 429/409 等。"""

    def test_hall_error_defaults_to_bad_request(self):
        error = HallError('请先确认将这篇手帐公开到大厅。')

        assert error.status == 400
        assert error.message == '请先确认将这篇手帐公开到大厅。'
        assert str(error) == error.message

    @pytest.mark.parametrize('status', [403, 404, 409, 429])
    def test_hall_error_keeps_an_explicit_status(self, status):
        assert HallError('拒绝', status).status == status

    def test_hall_error_is_a_distinct_type_from_generation_error(self):
        # 两者语义不同（HTTP 语义 vs 生成流水线），不能互相捕获。
        assert not issubclass(HallError, GenerationError)
        assert not issubclass(GenerationError, HallError)


class TestReadGeneratedText:
    """响应校验函数：把模型响应变成可信文本，或明确报错。"""

    def test_read_generated_text_returns_stripped_content(self):
        # 模型常在正文前后留空行，去掉后再使用，避免把空白当成"有内容"。
        assert read_generated_text(fake_response(chat_payload('  海边散步\n'))) == '海边散步'

    def test_read_generated_text_propagates_http_errors(self):
        response = fake_response(chat_payload('x'), status_code=500)

        with pytest.raises(requests.HTTPError):
            read_generated_text(response)

    @pytest.mark.parametrize('content', ['', '   ', None, 123, ['列表']])
    def test_read_generated_text_rejects_blank_or_non_text_content(self, content):
        with pytest.raises(ValueError, match='Missing generated text'):
            read_generated_text(fake_response(chat_payload(content)))

    def test_read_generated_text_rejects_a_malformed_payload(self):
        # 供应商换了响应结构时，宁可报错也不要把空内容写成手账。
        with pytest.raises((KeyError, IndexError, TypeError)):
            read_generated_text(fake_response({'choices': []}))
