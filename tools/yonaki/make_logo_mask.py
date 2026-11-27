"""One-off: render the logo glyphs 夜鳴き鐘 from Noto Serif CJK JP Regular (SIL Open Font License 1.1) into a
high-resolution coverage mask, assets/yonaki/logo/yonakigane_mask.png (one 256x256 cell per character,
stacked vertically), and 終 of the ending screen (owari_mask.png).  With --cards, the cards of the opening
instead, from Noto Serif CJK JP Light: the maker's mark (card_logo.png) and the credit (card_credit.png), each the
whole 256x192 screen at four times the size.  Only these renderings (images, not the font) are kept in the
repository; tools/yonaki/logo.py styles them.  The OFL permits using the font to make images; see
assets/yonaki/logo/README.

usage: python3 -I tools/yonaki/make_logo_mask.py PATH/TO/NotoSerifCJK-Regular.ttc
       python3 -I tools/yonaki/make_logo_mask.py --cards PATH/TO/NotoSerifCJKjp-Light.otf
"""
import sys, pathlib
ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/vendor/pylib'))
from PIL import Image, ImageDraw, ImageFont

OUT = ROOT / 'assets/yonaki/logo'
TEXT = '夜鳴き鐘'
CELL = 256
MAKER = 'takahirox'                  # the maker's mark and the credit (作)
S = 4                                # the cards: 4x the 256x192 screen


def tracked(d, y, text, font, track):
    """text centred on the card at y (the middle of the line), track px between the letters"""
    ws = [d.textlength(c, font=font) for c in text]
    x = (256 * S - sum(ws) - track * (len(text) - 1)) / 2
    for c, w in zip(text, ws):
        d.text((x, y), c, fill=255, font=font, anchor='lm')
        x += w + track


def cards(path):
    big = ImageFont.truetype(path, 25 * S)
    small = ImageFont.truetype(path, 15 * S)
    im = Image.new('L', (256 * S, 192 * S), 0)
    d = ImageDraw.Draw(im)
    tracked(d, 94 * S, MAKER, big, 5 * S)
    im.save(OUT / 'card_logo.png')
    im = Image.new('L', (256 * S, 192 * S), 0)
    d = ImageDraw.Draw(im)
    tracked(d, 78 * S, "作", small, 0)
    tracked(d, 104 * S, MAKER, ImageFont.truetype(path, 19 * S), 3 * S)
    im.save(OUT / 'card_credit.png')


def title(path):
    font = ImageFont.truetype(path, 224, index=0)          # face 0 = Noto Serif CJK JP
    assert font.getname()[0] == 'Noto Serif CJK JP', font.getname()
    out = Image.new('L', (CELL, CELL * len(TEXT)), 0)
    d = ImageDraw.Draw(out)
    for i, ch in enumerate(TEXT):
        d.text((CELL // 2, CELL * i + CELL // 2), ch, fill=255, font=font, anchor='mm')
    out.save(OUT / 'yonakigane_mask.png')
    # 終 of the ending screen
    end = Image.new('L', (CELL, CELL), 0)
    ImageDraw.Draw(end).text((CELL // 2, CELL // 2), '終', fill=255, font=font, anchor='mm')
    end.save(OUT / 'owari_mask.png')


if __name__ == '__main__':
    if sys.argv[1] == '--cards':
        cards(sys.argv[2])
    else:
        title(sys.argv[1])
