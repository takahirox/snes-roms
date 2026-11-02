"""One-off: render the logo glyphs 夜鳴き鐘 from Noto Serif CJK JP Regular (SIL Open Font License 1.1) into a
high-resolution coverage mask, assets/yonaki/logo/yonakigane_mask.png (one 256x256 cell per character,
stacked vertically), and 終 of the ending screen (owari_mask.png).  Only this rendering (an image, not the font) is kept in the repository; tools/yonaki/logo.py
styles it.  The OFL permits using the font to make images; see assets/yonaki/logo/README.

usage: python3 -I tools/yonaki/make_logo_mask.py PATH/TO/NotoSerifCJK-Regular.ttc
"""
import sys, pathlib
ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/vendor/pylib'))
from PIL import Image, ImageDraw, ImageFont

TEXT = '夜鳴き鐘'
CELL = 256
font = ImageFont.truetype(sys.argv[1], 224, index=0)          # face 0 = Noto Serif CJK JP
assert font.getname()[0] == 'Noto Serif CJK JP', font.getname()
out = Image.new('L', (CELL, CELL * len(TEXT)), 0)
d = ImageDraw.Draw(out)
for i, ch in enumerate(TEXT):
    d.text((CELL // 2, CELL * i + CELL // 2), ch, fill=255, font=font, anchor='mm')
p = ROOT / 'assets/yonaki/logo/yonakigane_mask.png'
out.save(p)
print(p, out.size)
# 終 of the ending screen
end = Image.new('L', (CELL, CELL), 0)
ImageDraw.Draw(end).text((CELL // 2, CELL // 2), '終', fill=255, font=font, anchor='mm')
end.save(ROOT / 'assets/yonaki/logo/owari_mask.png')
