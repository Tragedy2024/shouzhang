"""Built-in, clearly fictional samples using the same renderer as exports."""
from functools import lru_cache
from pathlib import Path
import threading

from PIL import Image, ImageDraw
from services.image_render_service import render_journal_to_bytes

_lock = threading.Lock()
SAMPLE_TEXT = """海边，慢一点也没关系

沿着海岸走了一小段路，蓝色从远处一直铺到脚边。停下来，看船经过，也看云慢慢换了形状。

把这段安静留在手帐里。以后翻到这一页，还能想起风吹过的那个下午。

#旅行碎片 #海边 #慢慢记录"""


@lru_cache(maxsize=5)
def sample_journal(style):
    folder = Path(__file__).resolve().parent.parent / 'instance'
    folder.mkdir(exist_ok=True)
    path = folder / 'sample-coast.jpg'
    # This illustrated sample is built into the app; no private uploads are used.
    with _lock:
        if not path.exists():
            image = Image.new('RGB', (1200, 820), '#d8e8ed')
            draw = ImageDraw.Draw(image)
            draw.rectangle((0, 340, 1200, 820), fill='#75a3ad')
            draw.ellipse((920, 65, 1060, 205), fill='#faf2d8')
            draw.polygon([(0, 320), (190, 220), (390, 350), (570, 265), (760, 340), (1200, 290), (1200, 420), (0, 420)], fill='#82958b')
            draw.polygon([(0, 820), (0, 645), (210, 565), (370, 630), (530, 735), (930, 820)], fill='#e5d7be')
            for y in range(460, 750, 65):
                draw.line((600, y, 1090, y - 9), fill='#a8c3c5', width=3)
            draw.polygon([(760, 530), (900, 530), (865, 560), (795, 560)], fill='#faf6ee')
            draw.line((824, 400, 824, 530), fill='#405965', width=5)
            draw.polygon([(814, 420), (814, 510), (755, 510)], fill='#e8e5db')
            image.save(path, 'JPEG', quality=92)
    return render_journal_to_bytes(SAMPLE_TEXT, [str(path)], style=style,
                                   date='2026-10-01', address='海边散步 · 示例旅行', weather='晴天', scale=1)
