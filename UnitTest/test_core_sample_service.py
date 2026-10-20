"""核心函数单元测试：``services.sample_service``。

被测单元
--------
``SAMPLE_TEXT``     内置的示例手帐文案（明确的虚构内容）
``sample_journal``   "先试后买"入口：第一次调用时现画一张示例插画并缓存，
                     之后直接复用，不同风格各缓存一份。

打桩策略
--------
``sample_journal`` 用 ``Path(__file__).parent.parent / 'instance'`` 定位插画，
所以本模块把 ``__file__`` 指到 ``tmp_path`` 里，既能让"插画不存在 → 现画"
这条只有在全新机器上才会走到的分支被覆盖，又保证测试不会污染项目真实的
``instance/`` 目录。
"""

from pathlib import Path
from unittest.mock import Mock

import pytest
from PIL import Image

import services.sample_service as sample_service
from services.image_render_service import CANVAS_WIDTH
from services.sample_service import SAMPLE_TEXT, sample_journal
from services.text_service import STYLES

PNG_MAGIC = b'\x89PNG\r\n\x1a\n'


@pytest.fixture(autouse=True)
def clear_sample_cache():
    """``sample_journal`` 带 ``lru_cache``，用例之间必须互不继承结果。"""
    sample_journal.cache_clear()
    yield
    sample_journal.cache_clear()


@pytest.fixture
def fresh_instance(tmp_path, monkeypatch):
    """把实例目录搬到临时目录，并返回插画应当落在的路径。"""
    monkeypatch.setattr(sample_service, '__file__',
                        str(tmp_path / 'services' / 'sample_service.py'))
    sample_journal.cache_clear()
    return tmp_path / 'instance' / 'sample-coast.jpg'


class TestSampleText:
    """示例文案本身：一眼就能看出是虚构的。"""

    def test_sample_text_carries_a_title_body_and_hashtags(self):
        lines = [line for line in SAMPLE_TEXT.splitlines() if line.strip()]

        assert lines[0] == '海边，慢一点也没关系'
        assert any(line.startswith('#') for line in lines)
        assert len(SAMPLE_TEXT) < 200


class TestSampleJournal:
    """示例长图：首次现画插画，之后复用并缓存。"""

    @pytest.mark.parametrize('style', sorted(STYLES))
    def test_sample_journal_returns_a_png_for_every_style(self, style):
        data = sample_journal(style)

        assert data[:8] == PNG_MAGIC

    def test_sample_journal_draws_the_illustration_on_first_use(self, fresh_instance):
        # 全新机器上 instance/sample-coast.jpg 并不存在，必须能自己画出来。
        assert not fresh_instance.exists()

        data = sample_journal('muji')

        assert fresh_instance.is_file()
        assert data[:8] == PNG_MAGIC

    def test_sample_journal_reuses_an_existing_illustration(self, fresh_instance):
        # 放一张"已经有插画"的占位图（内容与内置插画不同，方便辨认）。
        fresh_instance.parent.mkdir(parents=True)
        Image.new('RGB', (40, 30), '#ff0000').save(fresh_instance, 'JPEG')
        stamp = fresh_instance.stat().st_mtime_ns

        sample_journal('muji')

        # 插画已存在就不能重画（既没必要，也避免并发写同一个文件）。
        assert fresh_instance.stat().st_mtime_ns == stamp
        with Image.open(fresh_instance) as image:
            assert image.getpixel((20, 15))[0] > 200

    def test_sample_journal_renders_at_the_canvas_width(self, fresh_instance):
        import io

        with Image.open(io.BytesIO(sample_journal('film'))) as image:
            assert image.width == CANVAS_WIDTH

    def test_sample_journal_caches_per_style(self):
        # 同一个风格只渲染一次；示例图是每次打开页面都会请求的接口。
        assert sample_journal('muji') is sample_journal('muji')

    def test_sample_journal_caches_different_styles_separately(self):
        assert sample_journal('muji') != sample_journal('film')

    def test_sample_journal_never_uses_private_uploads(self, fresh_instance, monkeypatch):
        # 示例只读自己画的那张图，不碰 uploads/ 下的用户照片。
        renderer = Mock(return_value=PNG_MAGIC)
        monkeypatch.setattr(sample_service, 'render_journal_to_bytes', renderer)

        sample_journal('muji')

        rendered = [Path(path).name for path in renderer.call_args.args[1]]
        assert rendered == ['sample-coast.jpg']
