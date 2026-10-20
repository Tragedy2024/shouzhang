"""核心函数单元测试：``services.text_service``。

被测单元
--------
``_writing_http_message``  HTTP 失败 → 安全文案（不泄漏供应商原文与密钥）
``_request_text``          一次写作调用：载荷组装、异常翻译
``generate_journal``       写作素材 → 提示词（谁优先、谁只是参考）
``regenerate_journal``     改写：未知语气必须原样返回且不发请求

打桩策略
--------
全部用 ``unittest.mock`` 替换 ``requests.post``：本模块只关心"发了什么请求"
和"拿到什么响应之后怎么办"，真实模型调用既不必要也不允许。
``TEXT_CONFIG['api_key']`` 由 autouse 夹具钉成假值，保证测试结论不依赖本机环境。
"""

from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
import requests

from config import TEXT_CONFIG
from services.errors import GenerationError
from services.text_service import (
    FACTUALITY_RULES,
    REWRITE_RULES,
    STYLES,
    TONES,
    _request_text,
    _writing_http_message,
    generate_journal,
    regenerate_journal,
)


@pytest.fixture(autouse=True)
def fake_api_key(monkeypatch):
    """本机没有配置密钥时也要能跑；密钥存在与否由用例自己控制。"""
    monkeypatch.setitem(TEXT_CONFIG, 'api_key', 'unit-test-key')


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
    """构造一个合法的 chat-completion 响应体。"""
    return {'choices': [{'message': {'content': text}}]}


def http_error(status, body=None):
    """构造带响应对象的 ``requests.HTTPError``。"""
    response = Mock()
    response.status_code = status
    response.json.return_value = body if body is not None else {}
    return requests.HTTPError(response=response)


def sent_payload(http_post):
    """取出实际发送出去的 JSON 载荷。"""
    return http_post.post.call_args.kwargs['json']


class TestWritingHttpMessage:
    """HTTP 状态码 → 用户可操作的中文文案。"""

    @pytest.mark.parametrize('status,expected', [
        (400, '手账生成暂时失败，请重试'),
        (401, '文字生成服务认证失败，请检查服务配置后重试。'),
        (402, '文字生成服务余额不足，请充值后重试。'),
        (404, '文字生成模型或接口不可用，请更新服务配置后重试。'),
        (429, '文字生成请求过于频繁，请稍后重试。'),
        (500, '文字生成服务暂时不可用，请稍后重试。'),
        (503, '文字生成服务暂时不可用，请稍后重试。'),
        (418, '手账生成暂时失败，请重试'),
    ])
    def test_writing_http_message_maps_status_codes(self, status, expected):
        assert _writing_http_message(http_error(status)) == expected

    def test_writing_http_message_explains_an_unactivated_model(self):
        # ModelArts 用 403 + 业务错误码表示"模型没开通"，这是配置问题不是故障。
        error = http_error(403, {'error_code': 'ModelArts.81004'})

        assert _writing_http_message(error) == '文字生成服务尚未开通，请先开通当前模型后重试。'

    def test_writing_http_message_reads_nested_error_codes(self):
        # 有的网关把错误码藏在 error.code 里。
        error = http_error(403, {'error': {'code': 'ModelArts.81004'}})

        assert _writing_http_message(error) == '文字生成服务尚未开通，请先开通当前模型后重试。'

    @pytest.mark.parametrize('body', [
        {},
        {'error_code': 'SomethingElse'},
        {'error': '一个字符串而不是对象'},
        None,                       # json() 返回 None
    ])
    def test_writing_http_message_falls_back_to_a_generic_forbidden(self, body):
        assert _writing_http_message(http_error(403, body)) == \
            '文字生成服务拒绝了请求，请检查服务权限或账号状态后重试。'

    def test_writing_http_message_survives_an_unparseable_body(self):
        error = http_error(403)
        error.response.json.side_effect = ValueError('不是 JSON')

        assert _writing_http_message(error) == \
            '文字生成服务拒绝了请求，请检查服务权限或账号状态后重试。'

    def test_writing_http_message_handles_a_missing_response_object(self):
        # 极少数情况下 requests 抛出的 HTTPError 不带 response。
        assert _writing_http_message(requests.HTTPError('boom')) == '手账生成暂时失败，请重试'

    def test_writing_http_message_never_echoes_provider_details(self):
        secret = 'sk-provider-secret-key'
        error = http_error(403, {'error_code': secret, 'error': secret})

        message = _writing_http_message(error)

        assert secret not in message


class TestRequestText:
    """一次写作调用：先校验凭据，再发请求，最后把异常翻译成安全错误。"""

    def test_request_text_refuses_to_call_without_an_api_key(self, http_post, monkeypatch):
        monkeypatch.setitem(TEXT_CONFIG, 'api_key', '')

        with pytest.raises(GenerationError) as error:
            _request_text([{'role': 'user', 'content': '你好'}])

        assert error.value.stage == 'writing'
        # 没有密钥就不该浪费一次往返。
        http_post.post.assert_not_called()

    def test_request_text_returns_the_generated_text(self, http_post):
        http_post.response.json.return_value = reply('  海边散步  ')

        assert _request_text([{'role': 'user', 'content': '你好'}]) == '海边散步'

    def test_request_text_sends_model_messages_and_thinking_flag(self, http_post):
        http_post.response.json.return_value = reply('正文')

        _request_text([{'role': 'system', 'content': '系统提示'}], temperature=0.3)

        payload = sent_payload(http_post)
        assert payload['model'] == TEXT_CONFIG['model']
        assert payload['messages'] == [{'role': 'system', 'content': '系统提示'}]
        assert payload['temperature'] == 0.3
        assert payload['max_tokens'] == 1500
        assert payload['thinking'] == TEXT_CONFIG['thinking']
        assert http_post.post.call_args.args[0] == TEXT_CONFIG['url']

    def test_request_text_sends_a_bearer_token(self, http_post):
        http_post.response.json.return_value = reply('正文')

        _request_text([{'role': 'user', 'content': '你好'}])

        headers = http_post.post.call_args.kwargs['headers']
        assert headers['Authorization'] == f"Bearer {TEXT_CONFIG['api_key']}"
        assert headers['Content-Type'] == 'application/json'

    def test_request_text_times_out_as_a_retryable_error(self, http_post):
        http_post.post.side_effect = requests.Timeout('太慢了')

        with pytest.raises(GenerationError) as error:
            _request_text([{'role': 'user', 'content': '你好'}])

        assert (error.value.message, error.value.stage, error.value.retryable) == \
            ('手账生成超时，请重试', 'writing', True)

    def test_request_text_turns_http_errors_into_safe_messages(self, http_post):
        http_post.response.raise_for_status.side_effect = http_error(429)

        with pytest.raises(GenerationError) as error:
            _request_text([{'role': 'user', 'content': '你好'}])

        assert error.value.message == '文字生成请求过于频繁，请稍后重试。'
        assert error.value.retryable is True

    def test_request_text_handles_transport_failures(self, http_post):
        http_post.post.side_effect = requests.ConnectionError('断网了')

        with pytest.raises(GenerationError) as error:
            _request_text([{'role': 'user', 'content': '你好'}])

        assert error.value.message == '手账生成暂时失败，请重试'

    def test_request_text_handles_unparseable_json(self, http_post):
        http_post.response.json.side_effect = requests.exceptions.JSONDecodeError('bad', '', 0)

        with pytest.raises(GenerationError) as error:
            _request_text([{'role': 'user', 'content': '你好'}])

        assert error.value.message == '手账生成结果异常，请重试'

    @pytest.mark.parametrize('body', [
        {'choices': []},                                  # 结构缺项
        {'choices': [{'message': {'content': ''}}]},       # 空正文
        {'choices': [{'message': {'content': None}}]},     # 非文本
    ])
    def test_request_text_rejects_an_unusable_body(self, http_post, body):
        http_post.response.json.return_value = body

        with pytest.raises(GenerationError) as error:
            _request_text([{'role': 'user', 'content': '你好'}])

        assert error.value.message == '手账生成结果异常，请重试'

    def test_request_text_marks_every_failure_as_retryable(self, http_post):
        http_post.post.side_effect = RuntimeError('意料之外')

        with pytest.raises(GenerationError) as error:
            _request_text([{'role': 'user', 'content': '你好'}])

        assert error.value.retryable is True


def generate(http_post, **kwargs):
    """调用 ``generate_journal`` 并返回它发给模型的用户消息（上下文）。"""
    http_post.response.json.return_value = reply('生成的手账')
    arguments = {'image_description': '海面和一条船', 'address': None, 'attractions': [],
                 'datetime_str': None}
    arguments.update(kwargs)
    generate_journal(**arguments)
    payload = sent_payload(http_post)
    return payload['messages'][0]['content'], payload['messages'][1]['content']


class TestGenerateJournal:
    """写作素材 → 提示词：用户记录优先，自动识别只作参考。"""

    def test_generate_journal_sends_style_prompt_with_factuality_rules(self, http_post):
        system, _ = generate(http_post, style='film')

        assert STYLES['film']['prompt'] in system
        assert FACTUALITY_RULES in system

    def test_generate_journal_falls_back_to_xiaohongshu_for_unknown_styles(self, http_post):
        system, _ = generate(http_post, style='不存在的风格')

        assert STYLES['xiaohongshu']['prompt'] in system

    def test_generate_journal_always_includes_the_photo_description(self, http_post):
        _, user = generate(http_post, image_description='海面和一条船')

        assert '海面和一条船' in user

    def test_generate_journal_prefers_the_user_location(self, http_post):
        # 用户填的地点优先于自动定位；冲突时不混用，自动定位整条不出现。
        _, user = generate(http_post, address='自动识别出的地址', location='用户说的地点')

        assert '用户说的地点' in user
        assert '自动识别出的地址' not in user

    def test_generate_journal_labels_automatic_address_as_reference(self, http_post):
        _, user = generate(http_post, address='自动识别出的地址')

        assert '自动识别出的地址' in user
        assert '参考信息' in user

    def test_generate_journal_labels_attractions_as_unverified(self, http_post):
        # 附近景点只是地图检索结果，不能被写成"去过"。
        _, user = generate(http_post, attractions=[{'name': '故宫'}, {'name': '景山'}])

        assert '故宫、景山' in user
        assert '未证明用户到访' in user

    def test_generate_journal_drops_attractions_when_the_user_gave_a_location(self, http_post):
        _, user = generate(http_post, attractions=[{'name': '故宫'}], location='用户说的地点')

        assert '故宫' not in user

    def test_generate_journal_skips_attractions_without_names(self, http_post):
        _, user = generate(http_post, attractions=[{'name': ''}, {'name': '西湖'}])

        assert '西湖' in user

    def test_generate_journal_omits_an_all_blank_attraction_list(self, http_post):
        _, user = generate(http_post, attractions=[{'name': ''}, {}])

        assert '附近景点' not in user

    def test_generate_journal_prefers_the_user_date(self, http_post):
        _, user = generate(http_post, date='2026-10-01', datetime_str='2020:01:01 00:00:00')

        assert '2026-10-01' in user
        assert '2020:01:01 00:00:00' not in user

    def test_generate_journal_labels_camera_time_as_reference(self, http_post):
        _, user = generate(http_post, datetime_str='2020-01-01 00:00:00')

        assert '照片拍摄时间' in user and '参考信息' in user

    def test_generate_journal_folds_in_mood_feelings_and_weather(self, http_post):
        _, user = generate(http_post, mood='放松', feelings='海风很舒服', weather='晴')

        assert '放松' in user and '海风很舒服' in user and '晴' in user

    def test_generate_journal_does_not_invent_omitted_context(self, http_post):
        _, user = generate(http_post)

        for absent in ('地点', '日期', '天气', '心情', '感受', '附近景点'):
            assert absent not in user


class TestRegenerateJournal:
    """改写：只调语气，不增事实。"""

    def test_regenerate_journal_returns_the_original_for_an_unknown_tone(self, http_post):
        # 未知语气是"无事发生"，不该报错，更不该发一次请求。
        assert regenerate_journal('原标题\n\n正文', '不存在的语气') == '原标题\n\n正文'
        http_post.post.assert_not_called()

    def test_regenerate_journal_sends_original_text_and_tone_prompt(self, http_post):
        http_post.response.json.return_value = reply('改写后的手账')

        assert regenerate_journal('原标题\n\n正文', 'literary', 'film') == '改写后的手账'

        payload = sent_payload(http_post)
        assert '原标题\n\n正文' in payload['messages'][1]['content']
        assert TONES['literary']['prompt'] in payload['messages'][1]['content']

    def test_regenerate_journal_carries_the_rewrite_rules(self, http_post):
        http_post.response.json.return_value = reply('改写后的手账')

        regenerate_journal('原标题\n\n正文', 'healing', 'film')

        system = sent_payload(http_post)['messages'][0]['content']
        assert REWRITE_RULES in system and FACTUALITY_RULES in system
        assert STYLES['film']['prompt'] in system

    def test_regenerate_journal_uses_a_lower_temperature(self, http_post):
        http_post.response.json.return_value = reply('改写后的手账')

        regenerate_journal('原标题\n\n正文', 'girly')

        # 改写要保持原稿事实，温度比首次生成低。
        assert sent_payload(http_post)['temperature'] == 0.6

    @pytest.mark.parametrize('tone', sorted(TONES))
    def test_regenerate_journal_accepts_every_defined_tone(self, http_post, tone):
        http_post.response.json.return_value = reply('改写后的手账')

        assert regenerate_journal('原标题\n\n正文', tone) == '改写后的手账'

    def test_regenerate_journal_propagates_writing_failures(self, http_post):
        http_post.post.side_effect = requests.Timeout('太慢了')

        with pytest.raises(GenerationError) as error:
            regenerate_journal('原标题\n\n正文', 'literary')

        assert error.value.stage == 'writing'
