"""UnitTest 套件的共用夹具。

三条铁律，贯穿全部单元测试：

1. **离线**——沿用项目 ``tests/conftest.py`` 的做法，在 ``requests`` 唯一的
   出口 ``Session.request`` 上打桩。任何没有被显式 mock 的真实 HTTP 调用都会
   立刻抛 ``AssertionError``，而不是静默联网（既不花钱，也让"漏 mock"变成
   一个显式的失败而不是一个隐藏的副作用）。
2. **隔离**——所有落盘路径都指向 pytest 的 ``tmp_path``，绝不触碰项目真实的
   ``instance/``、``uploads/`` 目录。
3. **可移植**——字体缺失、symlink 权限不足等环境差异都有兜底，同一套测试在
   Windows / macOS / Linux 上结论一致。
"""

import io
import sys
from pathlib import Path

import pytest
import requests
from PIL import Image

# 让 ``import app`` / ``import services.*`` 在任何运行方式下都能解析。
# 显式插入而不是依赖 pytest 的 rootdir 推断，便于单独执行某个测试文件。
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture(autouse=True)
def block_unplanned_network(request, monkeypatch):
    """在没有 ``@pytest.mark.live`` 的测试里，禁止任何真实网络请求。

    这是本套件的安全网：单元测试必须用 ``unittest.mock.patch`` 显式打桩
    ``requests.get`` / ``requests.post``，否则直接失败。
    """
    if request.node.get_closest_marker('live'):
        return

    def blocked(*args, **kwargs):
        raise AssertionError('单元测试必须用 unittest.mock 打桩外部请求，不得真实联网')

    monkeypatch.setattr(requests.sessions.Session, 'request', blocked)


@pytest.fixture(autouse=True)
def clear_font_cache():
    """``_get_font`` 带 ``lru_cache``；改动字体环境变量前后都要清缓存。

    否则前一个测试缓存的字体对象会污染后一个测试，导致断言随机失败。
    """
    from services.image_render_service import _get_font

    _get_font.cache_clear()
    yield
    _get_font.cache_clear()


@pytest.fixture
def store(tmp_path):
    """一个落在临时目录里的真实 ``JournalStore``。

    刻意**不做 mock**：它自己就是要被测的实体，mock 掉 sqlite 就测不出 SQL
    约束、WAL 与文件句柄这些真正的风险点。
    """
    from services.storage_service import JournalStore

    return JournalStore(tmp_path / 'journal.sqlite3', tmp_path / 'private-photos')


@pytest.fixture
def hall(tmp_path):
    """一个落在临时目录里的真实 ``HallService``，媒体目录与 store 相互独立。"""
    from services.hall_service import HallService
    from services.storage_service import JournalStore

    store = JournalStore(tmp_path / 'hall.sqlite3', tmp_path / 'private-photos')
    return HallService(store, tmp_path / 'public-media')


@pytest.fixture
def make_jpeg(tmp_path):
    """生成一张真实可读的 JPEG，返回其路径。

    ``exif`` 传入 ``PIL.Image.Exif`` 对象即可带上元信息；文件名要唯一时用
    ``name=`` 指定。
    """
    counter = {'n': 0}

    def build(name=None, size=(120, 80), color='#7799aa', exif=None):
        counter['n'] += 1
        path = tmp_path / (name or f'photo-{counter["n"]}.jpg')
        # 只在真的要写 EXIF 时才传 exif 参数：显式传 None 会让 Pillow 把它
        # 当成"用户指定了空的 EXIF 块"，保存时对 None 取长度而报 TypeError。
        options = {} if exif is None else {'exif': exif}
        Image.new('RGB', size, color).save(path, 'JPEG', **options)
        return path

    return build


@pytest.fixture
def png_bytes():
    """生成服务端渲染长图用的 PNG 字节，默认 750x500（与 CANVAS_WIDTH 一致）。"""

    def build(size=(750, 500), color='#7aaabb'):
        buffer = io.BytesIO()
        Image.new('RGB', size, color).save(buffer, 'PNG')
        return buffer.getvalue()

    return build
