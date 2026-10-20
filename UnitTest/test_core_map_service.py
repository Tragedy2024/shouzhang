"""核心函数单元测试：``services.map_service``。

被测单元
--------
``reverse_geocode``          坐标 → 文字地址（百度逆地理编码）
``search_nearby_attractions`` 坐标 → 附近景点列表（百度地点检索）

为什么要打桩而不是打 ``live`` 标记
----------------------------------
这两个函数的价值全在**失败路径**：地图服务限流、余额不足、返回体结构变动时，
流水线必须继续跑下去（返回 ``None`` / ``[]``），而不是把异常抛给用户。
这些分支离线完全可以验证，只要用 ``unittest.mock`` 替换 ``requests.get``。

模块顶部的 ``reactor`` 夹具会把 ``requests.get`` 换成一个 ``Mock``，
并把它和它返回的响应对象一起交出来，测试按需设置 ``return_value`` /
``side_effect``。
"""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import requests

import services.map_service as map_service

TEST_LAT, TEST_LNG = 39.9163, 116.3972


@pytest.fixture
def http_get(monkeypatch):
    """把 ``requests.get`` 换成可编程的 Mock，返回 (调用桩, 响应桩)。"""
    response = Mock()
    response.status_code = 200
    response.raise_for_status.return_value = None
    response.json.return_value = {}
    getter = Mock(return_value=response)
    monkeypatch.setattr(requests, 'get', getter)
    return SimpleNamespace(get=getter, response=response)


class TestReverseGeocode:
    """逆地理编码：成功取地址，失败一律 None。"""

    def test_reverse_geocode_returns_the_formatted_address(self, http_get):
        http_get.response.json.return_value = {
            'status': 0, 'result': {'formatted_address': '北京市东城区景山前街4号'}}

        assert map_service.reverse_geocode(TEST_LAT, TEST_LNG) == '北京市东城区景山前街4号'

    def test_reverse_geocode_sends_wgs84_coordinates(self, http_get):
        # 上传的照片是 WGS84（GPS 原始坐标），必须显式告诉百度按 wgs84ll 解析，
        # 否则会有几百米的偏移。
        http_get.response.json.return_value = {'status': 0, 'result': {'formatted_address': 'x'}}

        map_service.reverse_geocode(TEST_LAT, TEST_LNG)

        params = http_get.get.call_args.kwargs['params']
        assert params['coordtype'] == 'wgs84ll'
        assert params['location'] == f'{TEST_LAT},{TEST_LNG}'
        assert params['output'] == 'json'
        assert 'ak' in params

    def test_reverse_geocode_uses_a_timeout(self, http_get):
        http_get.response.json.return_value = {'status': 0, 'result': {'formatted_address': 'x'}}

        map_service.reverse_geocode(TEST_LAT, TEST_LNG)

        assert http_get.get.call_args.kwargs['timeout'] == 10

    @pytest.mark.parametrize('payload', [
        {'status': 1, 'message': '内部错误'},        # 服务端返回错误码
        {'status': 0, 'result': {}},                 # 少了 formatted_address
        {'status': 0},                               # 少了 result
        {},                                          # 空响应体
    ])
    def test_reverse_geocode_returns_none_for_unusable_bodies(self, http_get, payload):
        http_get.response.json.return_value = payload

        assert map_service.reverse_geocode(TEST_LAT, TEST_LNG) is None

    def test_reverse_geocode_returns_none_on_an_http_error(self, http_get):
        http_get.response.raise_for_status.side_effect = requests.HTTPError('403 Forbidden')

        assert map_service.reverse_geocode(TEST_LAT, TEST_LNG) is None

    @pytest.mark.parametrize('error', [
        requests.ConnectionError('断网了'),
        requests.Timeout('超时了'),
        ValueError('奇怪的响应'),
    ])
    def test_reverse_geocode_returns_none_on_transport_failures(self, http_get, error):
        http_get.get.side_effect = error

        assert map_service.reverse_geocode(TEST_LAT, TEST_LNG) is None

    def test_reverse_geocode_never_raises(self, http_get):
        # 流水线依赖这一点：定位失败只是少一条信息，不能让整个生成失败。
        http_get.get.side_effect = RuntimeError('意料之外')

        assert map_service.reverse_geocode(TEST_LAT, TEST_LNG) is None


class TestSearchNearbyAttractions:
    """附近景点检索：失败返回空列表，成功最多取前 5 条。"""

    def test_search_returns_name_and_address_pairs(self, http_get):
        http_get.response.json.return_value = {'status': 0, 'results': [
            {'name': '故宫博物院', 'address': '景山前街4号'},
            {'name': '景山公园', 'address': '景山西街44号'},
        ]}

        assert map_service.search_nearby_attractions(TEST_LAT, TEST_LNG) == [
            {'name': '故宫博物院', 'address': '景山前街4号'},
            {'name': '景山公园', 'address': '景山西街44号'},
        ]

    def test_search_truncates_to_the_top_five(self, http_get):
        http_get.response.json.return_value = {'status': 0, 'results': [
            {'name': f'景点{index}', 'address': f'地址{index}'} for index in range(9)]}

        assert len(map_service.search_nearby_attractions(TEST_LAT, TEST_LNG)) == 5

    def test_search_defaults_missing_fields_to_empty_text(self, http_get):
        # 百度有时不返回 address，不能因此让调用方拿到 None。
        http_get.response.json.return_value = {'status': 0, 'results': [{'name': '某景点'}]}

        assert map_service.search_nearby_attractions(TEST_LAT, TEST_LNG) == [
            {'name': '某景点', 'address': ''}]

    def test_search_returns_empty_for_a_non_zero_status(self, http_get):
        http_get.response.json.return_value = {'status': 2, 'message': '参数错误'}

        assert map_service.search_nearby_attractions(TEST_LAT, TEST_LNG) == []

    def test_search_returns_empty_when_no_places_matched(self, http_get):
        http_get.response.json.return_value = {'status': 0, 'results': []}

        assert map_service.search_nearby_attractions(TEST_LAT, TEST_LNG) == []

    def test_search_returns_empty_on_transport_failure(self, http_get):
        http_get.get.side_effect = requests.ConnectionError('断网了')

        assert map_service.search_nearby_attractions(TEST_LAT, TEST_LNG) == []

    def test_search_passes_the_requested_radius(self, http_get):
        http_get.response.json.return_value = {'status': 0, 'results': []}

        map_service.search_nearby_attractions(TEST_LAT, TEST_LNG, radius=1200)

        params = http_get.get.call_args.kwargs['params']
        assert params['radius'] == 1200
        assert params['query'] == '旅游景点'
        assert params['location'] == f'{TEST_LAT},{TEST_LNG}'
