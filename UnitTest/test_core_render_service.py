"""核心函数单元测试：``services.image_render_service``。

被测单元
--------
``_graphemes``              把文字切成"不会被拆坏的排版单元"（组合符 / ZWJ / 肤色）
``_text_width``             像素级量宽，换行与标签排版的唯一依据
``_wrap_text``              按像素换行：保留段间空行，拉丁词优先整体不拆
``parse_journal_sections``  手账正文 → 可编辑的标题 / 正文 / 标签
``_fit_photo``              等比缩放，永不裁剪；默认不放大
``_add_film_grain``         胶片风格的确定性颗粒
``_get_font``               中文字体选择与 ``JOURNAL_FONT_PATH`` 覆盖
``render_journal_image``    整幅长图：倍率校验、风格回退、编辑内容优先
``render_journal_to_bytes`` 对外交付的 PNG 字节

打桩策略
--------
这些函数没有外部依赖（不联网、不读数据库），所以本模块几乎不需要 Mock；
唯一被"扶"一下的是字体环境变量——本机没有中文字体时用 ``pytest.skip`` 明示，
而不是让断言以令人困惑的方式失败。
"""

import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from PIL import Image, ImageFont

from services.image_render_service import (
    CANVAS_WIDTH,
    FONT_PATHS,
    STYLE_COLORS,
    _add_film_grain,
    _fit_photo,
    _get_font,
    _graphemes,
    _line_height,
    _parse_journal_sections,
    _text_width,
    _windows_font,
    _wrap_text,
    parse_journal_sections,
    render_journal_image,
    render_journal_to_bytes,
)

BODY_FONT_SIZE = 22
FONT = _get_font(BODY_FONT_SIZE)
WRAP_WIDTH = 200


class TestGraphemes:
    """排版单元切分：Emoji 与组合字符不能被拆成两半。"""

    def test_graphemes_keeps_combining_marks_with_their_base(self):
        assert _graphemes('e\u0301') == ['e\u0301']

    def test_graphemes_keeps_zwj_emoji_sequences_together(self):
        # 👨👩👧 = 三个 Emoji 用零宽连接符串起来，必须整体换行。
        assert _graphemes('\U0001F468\u200D\U0001F469\u200D\U0001F467') == \
            ['\U0001F468\u200D\U0001F469\u200D\U0001F467']

    def test_graphemes_keeps_skin_tone_modifiers_attached(self):
        # 👍🏻 = 手势 + 肤色修饰符，两个码点算一个排版单元。
        assert _graphemes('a\U0001F44D\U0001F3FBb') == ['a', '\U0001F44D\U0001F3FB', 'b']

    def test_graphemes_keeps_variation_selectors_attached(self):
        assert _graphemes('\u2764\ufe0f') == ['\u2764\ufe0f']

    def test_graphemes_splits_plain_text_per_character(self):
        assert _graphemes('abc') == ['a', 'b', 'c']

    def test_graphemes_of_an_empty_string_is_empty(self):
        assert _graphemes('') == []


class TestTextWidth:
    """量宽：换行与标签排版的唯一依据。"""

    def test_text_width_returns_a_positive_integer(self):
        assert isinstance(_text_width('国', FONT), int)
        assert _text_width('国', FONT) > 0

    def test_text_width_grows_with_content(self):
        assert _text_width('国国国', FONT) > _text_width('国', FONT)

    def test_text_width_of_an_empty_string_is_zero(self):
        assert _text_width('', FONT) == 0


class TestWrapText:
    """按像素换行：列宽不越界，段间空行保留，拉丁词尽量不拆。"""

    def test_wrap_text_rejects_a_non_positive_width(self):
        for width in (0, -1, -200):
            with pytest.raises(ValueError, match='文本区域宽度必须大于 0'):
                _wrap_text('正文', FONT, width)

    def test_wrap_text_keeps_every_line_inside_the_width(self):
        lines = _wrap_text('海风把云推得很慢，我沿着海岸走了很久。' * 3, FONT, WRAP_WIDTH)

        assert len(lines) > 1
        assert all(_text_width(line, FONT) <= WRAP_WIDTH for line in lines)

    def test_wrap_text_preserves_blank_lines_between_paragraphs(self):
        # 空行是手账的呼吸感，不能被吞掉。
        assert _wrap_text('第一段\n\n第二段', FONT, WRAP_WIDTH) == ['第一段', '', '第二段']

    def test_wrap_text_treats_a_whitespace_only_paragraph_as_blank(self):
        assert _wrap_text('第一段\n   \n第二段', FONT, WRAP_WIDTH) == ['第一段', '', '第二段']

    def test_wrap_text_keeps_a_latin_word_intact_when_it_fits(self):
        # 英文单词从中间断开读起来很糟；能放下就整体放。
        assert _wrap_text('hello world', FONT, _text_width('hello world', FONT) + 4) == \
            ['hello world']

    def test_wrap_text_breaks_a_word_that_cannot_fit_at_all(self):
        narrow = _text_width('abc', FONT)

        lines = _wrap_text('abcdefgh', FONT, narrow)

        assert len(lines) > 1
        assert ''.join(lines) == 'abcdefgh'

    def test_wrap_text_strips_trailing_whitespace(self):
        assert _wrap_text('hello   ', FONT, WRAP_WIDTH) == ['hello']

    def test_wrap_text_returns_a_single_blank_for_empty_input(self):
        assert _wrap_text('', FONT, WRAP_WIDTH) == ['']


class TestParseJournalSections:
    """正文切分：首行即标题，纯标签行才是标签。"""

    def test_parse_journal_sections_splits_title_body_and_tags(self):
        sections = parse_journal_sections('海边散步\n\n风吹过海面。\n\n#旅行 #海边')

        assert sections == {'title': '海边散步', 'body': '风吹过海面。',
                            'tags': ['#旅行', '#海边']}

    def test_parse_journal_sections_strips_markdown_headings(self):
        assert parse_journal_sections('## 海边\n\n正文')['title'] == '海边'

    def test_parse_journal_sections_strips_trailing_hashes(self):
        assert parse_journal_sections('海边 ##\n\n正文')['title'] == '海边'

    def test_parse_journal_sections_keeps_mixed_lines_in_the_body(self):
        # 一行里既有正文又有话题，就不能整行当标签丢掉。
        sections = parse_journal_sections('标题\n\n今天很好 #旅行')

        assert sections['tags'] == []
        assert '今天很好 #旅行' in sections['body']

    def test_parse_journal_sections_accepts_full_width_hashtags(self):
        assert parse_journal_sections('标题\n\n＃旅行')['tags'] == ['＃旅行']

    def test_parse_journal_sections_keeps_paragraph_breaks_in_the_body(self):
        sections = parse_journal_sections('标题\n\n第一段\n\n第二段')

        assert sections['body'] == '第一段\n\n第二段'

    @pytest.mark.parametrize('text', ['', '   ', '\n\n'])
    def test_parse_journal_sections_of_blank_text_is_empty(self, text):
        assert parse_journal_sections(text) == {'title': '', 'body': '', 'tags': []}

    def test_parse_journal_sections_normalizes_line_endings(self):
        assert parse_journal_sections('标题\r\n\r\n正文')['body'] == '正文'

    def test_parse_journal_sections_keeps_the_legacy_alias(self):
        # 老调用方仍 import 下划线版本，别名必须指向同一个函数。
        assert _parse_journal_sections is parse_journal_sections


class TestFitPhoto:
    """等比适配：不裁剪、不放大（除非显式允许）。"""

    def test_fit_photo_never_upscales_by_default(self):
        photo = Image.new('RGB', (100, 100))

        assert _fit_photo(photo, 500, 500).size == (100, 100)

    def test_fit_photo_scales_down_to_the_box(self):
        photo = Image.new('RGB', (1000, 500))

        assert _fit_photo(photo, 400, 400).size == (400, 200)

    def test_fit_photo_preserves_the_aspect_ratio(self):
        photo = Image.new('RGB', (1600, 900))

        width, height = _fit_photo(photo, 300, 300).size

        assert round(width / height, 2) == round(1600 / 900, 2)

    def test_fit_photo_never_returns_a_zero_dimension(self):
        # 极端长条图缩放后可能算成 0 像素，必须钳到 1。
        photo = Image.new('RGB', (4000, 1))

        assert _fit_photo(photo, 400, 400).size[1] == 1

    def test_fit_photo_honours_an_explicit_upscale_allowance(self):
        # 高清导出（scale=2）允许放大到两倍，保持逻辑尺寸一致。
        photo = Image.new('RGB', (100, 100))

        assert _fit_photo(photo, 500, 500, max_upscale=2).size == (200, 200)

    def test_fit_photo_does_not_mutate_the_source(self):
        photo = Image.new('RGB', (1000, 500))

        _fit_photo(photo, 400, 400)

        assert photo.size == (1000, 500)


class TestFilmGrain:
    """胶片颗粒：确定性纹理，同样输入必须得到同样输出。"""

    def _sample(self):
        return Image.new('RGB', (200, 120), (80, 90, 100))

    def test_add_film_grain_is_deterministic(self):
        assert _add_film_grain(self._sample()).tobytes() == \
               _add_film_grain(self._sample()).tobytes()

    def test_add_film_grain_changes_the_pixels(self):
        source = self._sample()

        assert _add_film_grain(source).tobytes() != source.tobytes()

    def test_add_film_grain_keeps_size_and_mode(self):
        grained = _add_film_grain(self._sample())

        assert (grained.size, grained.mode) == ((200, 120), 'RGB')

    def test_add_film_grain_handles_sizes_smaller_than_the_tile(self):
        # 128x128 的纹理贴到更小的画布上时要正确裁剪。
        assert _add_film_grain(Image.new('RGB', (37, 11), 'white')).size == (37, 11)


def available_font_path():
    """返回本机第一个可用的字体文件，找不到就返回 None。"""
    return next((path for path in FONT_PATHS if os.path.isfile(path)), None)


class TestGetFont:
    """字体选择：项目字体 > 系统中文字体 > Pillow 兜底。"""

    def test_get_font_returns_a_measurable_font(self):
        font = _get_font(18)

        assert isinstance(font, ImageFont.FreeTypeFont)
        assert font.getbbox('国Ag')[2] > 0

    def test_get_font_caches_per_size(self):
        # lru_cache 让相同字号只加载一次字体文件。
        assert _get_font(19) is _get_font(19)

    def test_get_font_honours_the_configured_path(self, tmp_path, monkeypatch):
        source = available_font_path()
        if source is None:
            pytest.skip('本机没有任何可用中文字体，无法验证字体覆盖')
        custom = tmp_path / 'custom-font.ttf'
        custom.write_bytes(Path(source).read_bytes())
        monkeypatch.setenv('JOURNAL_FONT_PATH', str(custom))
        _get_font.cache_clear()          # 缓存键不含环境变量，改完必须手动清

        try:
            assert Path(_get_font(21).path) == custom
        finally:
            _get_font.cache_clear()

    def test_get_font_falls_back_when_the_configured_path_is_missing(self, monkeypatch):
        monkeypatch.setenv('JOURNAL_FONT_PATH', 'Z:/definitely/not/here.ttf')
        _get_font.cache_clear()

        try:
            font = _get_font(23)
            assert font.getbbox('国')[2] > 0
        finally:
            _get_font.cache_clear()

    def test_windows_font_paths_are_resolved_from_the_windir_variable(self):
        # 回归：Windows 不一定装在 C:，字体目录不能写死成 C:\Windows\Fonts，
        # 必须按 %WINDIR% 解析。
        expected = Path(os.environ.get('WINDIR', r'C:\Windows')) / 'Fonts'

        assert Path(_windows_font('msyh.ttc')).parent == expected
        assert sum(Path(path).parent == expected for path in FONT_PATHS) >= 5


class TestRenderJournalImage:
    """整幅长图：倍率校验、风格回退、编辑内容优先。"""

    def test_render_rejects_scale_values_other_than_one_or_two(self):
        for scale in (0, 3, -1, 1.5, '2', None, True, False):
            with pytest.raises(ValueError, match='导出倍率仅支持 1 或 2'):
                render_journal_image('标题\n\n正文', [], 'muji', scale=scale)

    def test_render_uses_the_canvas_width_at_scale_one(self):
        assert render_journal_image('标题\n\n正文', [], 'muji').width == CANVAS_WIDTH

    def test_render_doubles_the_canvas_at_scale_two(self):
        assert render_journal_image('标题\n\n正文', [], 'muji', scale=2).width == CANVAS_WIDTH * 2

    def test_render_falls_back_to_xiaohongshu_for_unknown_styles(self):
        image = render_journal_image('标题\n\n正文', [], '不存在的风格')

        # 回退后背景色应当是小红书风的粉色底，而不是默认白。
        assert image.getpixel((5, image.height - 5)) == STYLE_COLORS['xiaohongshu']['bg']

    def test_render_accepts_every_defined_style(self):
        for style in STYLE_COLORS:
            assert render_journal_image('标题\n\n正文', [], style).width == CANVAS_WIDTH

    def test_render_honours_an_intentionally_empty_title(self):
        # 编辑区里把标题清空是明确意图，不能从正文首行再推断一个标题出来。
        without_title = render_journal_image(
            '', [], 'muji', sections={'title': '', 'body': '正文内容', 'tags': []})
        with_title = render_journal_image(
            '', [], 'muji', sections={'title': '标题', 'body': '正文内容', 'tags': []})

        assert with_title.height > without_title.height

    def test_render_prefixes_hashtags_that_lack_one(self):
        # 编辑区允许用户只填"旅行"，渲染时要补成话题样式。
        with_hash = render_journal_image(
            '', [], 'muji', sections={'title': '标题', 'body': '正文', 'tags': ['#旅行']})
        without_hash = render_journal_image(
            '', [], 'muji', sections={'title': '标题', 'body': '正文', 'tags': ['旅行']})

        assert with_hash.size == without_hash.size

    def test_render_drops_blank_tags(self):
        blank = render_journal_image(
            '', [], 'muji', sections={'title': '标题', 'body': '正文', 'tags': ['  ', '\t', '']})
        none_at_all = render_journal_image(
            '', [], 'muji', sections={'title': '标题', 'body': '正文', 'tags': []})

        assert blank.size == none_at_all.size

    def test_render_keeps_a_bare_hash_tag(self):
        # 渲染层只丢弃"纯空白"标签；只剩一个 # 的标签会被保留成一个话题胶囊。
        # 更严格的过滤（丢掉只剩 # 的项）由路由层负责，渲染层不越权替用户删内容。
        bare = render_journal_image(
            '', [], 'muji', sections={'title': '标题', 'body': '正文', 'tags': ['#']})
        none_at_all = render_journal_image(
            '', [], 'muji', sections={'title': '标题', 'body': '正文', 'tags': []})

        assert bare.height > none_at_all.height

    @pytest.mark.parametrize('sections,message', [
        ('不是字典', '手帐结构必须包含标题、正文与标签'),
        ({'title': 1, 'body': '正文', 'tags': []}, '手帐标题与正文必须为文字，标签必须为列表'),
        ({'title': '标题', 'body': None, 'tags': []}, '手帐标题与正文必须为文字，标签必须为列表'),
        ({'title': '标题', 'body': '正文', 'tags': '不是列表'}, '手帐标题与正文必须为文字，标签必须为列表'),
        ({'title': '标题', 'body': '正文', 'tags': [1]}, '每个手帐标签必须为文字'),
    ])
    def test_render_rejects_malformed_sections(self, sections, message):
        with pytest.raises(ValueError, match=message):
            render_journal_image('', [], 'muji', sections=sections)

    def test_render_accepts_a_photo_path(self, make_jpeg):
        image = render_journal_image('标题\n\n正文', [str(make_jpeg(size=(300, 200)))], 'film')

        assert image.width == CANVAS_WIDTH and image.height > 0

    def test_render_photo_styles_differ_in_layout(self, make_jpeg):
        # 日杂/胶片把照片与段落交错，极简把照片全部前置，二者高度必然不同。
        path = [str(make_jpeg(size=(300, 200)))]
        text = '标题\n\n第一段\n\n第二段'

        assert render_journal_image(text, path, 'muji').height != \
               render_journal_image(text, path, 'film').height


class TestRenderJournalToBytes:
    """对外交付格式：PNG 字节，倍率决定分辨率。"""

    def test_render_to_bytes_returns_a_png(self):
        data = render_journal_to_bytes('标题\n\n正文', [], 'muji')

        assert data[:8] == b'\x89PNG\r\n\x1a\n'

    def test_render_to_bytes_honours_the_export_scale(self):
        import io

        data = render_journal_to_bytes('标题\n\n正文', [], 'muji', scale=2)

        with Image.open(io.BytesIO(data)) as image:
            assert image.width == CANVAS_WIDTH * 2

    def test_render_to_bytes_rejects_an_invalid_scale(self):
        with pytest.raises(ValueError, match='导出倍率仅支持 1 或 2'):
            render_journal_to_bytes('标题\n\n正文', [], 'muji', scale=3)


class TestWrapTextGraphemeJoining:
    """词元切分之后的补救：组合符 / 变体选择符不能被留在上一行。"""

    def test_wrap_text_keeps_a_combining_mark_with_its_base_letter(self):
        # 词元正则会把 'e' 和组合重音符拆成两个单元，合并步骤要把它们拼回去。
        assert _wrap_text('e\u0301', FONT, WRAP_WIDTH) == ['e\u0301']

    def test_wrap_text_keeps_a_variation_selector_with_its_emoji(self):
        assert _wrap_text('\u2764\ufe0f', FONT, WRAP_WIDTH) == ['\u2764\ufe0f']


class TestLineHeight:
    """行高：优先用字体自报的 ascent/descent，拿不到就用包围盒估算。"""

    def test_line_height_uses_the_font_metrics_when_available(self):
        ascent, descent = FONT.getmetrics()

        assert _line_height(FONT, 6) == ascent + descent + 6

    def test_line_height_falls_back_when_metrics_are_unavailable(self):
        # 少数替身 / 精简字体只实现了 getbbox，不能因此让整幅图渲染失败。
        font = Mock(spec=['getbbox'])
        font.getbbox.return_value = (0, 2, 10, 22)

        assert _line_height(font, 4) == 24


class TestFontFallback:
    """字体兜底链：项目自带 > 系统中文字体 > Pillow 内置（含老版本兼容）。"""

    def test_get_font_falls_back_to_the_pillow_default(self, monkeypatch):
        # 全新容器里可能一个中文字体都没有，此时仍要返回一个能用的字体对象。
        monkeypatch.delenv('JOURNAL_FONT_PATH', raising=False)
        monkeypatch.setattr('services.image_render_service.FONT_PATHS', ['Z:/definitely/not/here.ttf'])
        _get_font.cache_clear()

        try:
            assert _get_font(16).getbbox('国')[2] > 0
        finally:
            _get_font.cache_clear()

    def test_get_font_survives_an_old_pillow_without_a_scalable_default(self, monkeypatch):
        # Pillow < 10.1 的 load_default() 不接受 size 参数，必须退回无参调用。
        fallback = ImageFont.load_default()
        loader = Mock(side_effect=[TypeError('unexpected keyword argument'), fallback])
        monkeypatch.delenv('JOURNAL_FONT_PATH', raising=False)
        monkeypatch.setattr('services.image_render_service.FONT_PATHS', [])
        monkeypatch.setattr('services.image_render_service.ImageFont',
                            SimpleNamespace(load_default=loader))
        _get_font.cache_clear()

        try:
            assert _get_font(16) is fallback
        finally:
            _get_font.cache_clear()

    def test_get_font_skips_a_candidate_that_cannot_be_loaded(self, tmp_path, monkeypatch):
        # 路径存在但文件不是合法字体（下载到一半、被替换成占位文件）时，
        # 要跳过它继续往下找，而不是把整幅图的渲染拖挂。
        broken = tmp_path / 'broken.ttf'
        broken.write_bytes(b'this is not a font')
        working = available_font_path()
        if working is None:
            pytest.skip('本机没有任何可用中文字体，无法验证候选链的降级')
        monkeypatch.delenv('JOURNAL_FONT_PATH', raising=False)
        monkeypatch.setattr('services.image_render_service.FONT_PATHS', [str(broken), working])
        _get_font.cache_clear()

        try:
            assert Path(_get_font(17).path) == Path(working)
        finally:
            _get_font.cache_clear()


class TestMultiPhotoLayout:
    """多张照片的排版：宫格（小红书 / INS）与标签换行。"""

    def test_xiaohongshu_lays_multiple_photos_out_in_a_grid(self, make_jpeg):
        # 小红书风在两张以上照片时走宫格；奇数张时最后一张居中。
        paths = [str(make_jpeg(name=f'grid-{index}.jpg', size=(300, 200)))
                 for index in range(3)]

        image = render_journal_image('标题\n\n正文', paths, 'xiaohongshu')

        assert image.width == CANVAS_WIDTH and image.height > 0

    def test_a_single_photo_is_not_put_in_a_grid(self, make_jpeg):
        # 一张照片走大图排版，与多张照片的宫格高度必然不同。
        path = [str(make_jpeg(name='solo.jpg', size=(300, 200)))]

        assert render_journal_image('标题\n\n正文', path, 'xiaohongshu').height != \
               render_journal_image('标题\n\n正文', path * 2, 'xiaohongshu').height

    def test_long_tags_wrap_onto_several_rows(self):
        # 标签总宽超过画布时必须换行，而不是画到画布外面去。
        sections = {'title': '标题', 'body': '正文', 'tags': ['#旅行碎片记录一下']}
        crowded = {**sections, 'tags': ['#旅行碎片记录一下'] * 6}

        single_row = render_journal_image('', [], 'muji', sections=sections)
        several_rows = render_journal_image('', [], 'muji', sections=crowded)

        assert several_rows.height > single_row.height
