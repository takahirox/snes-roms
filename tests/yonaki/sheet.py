"""Contact sheet of screenshots: python3 -I tests/yonaki/sheet.py OUT.png COLUMNS SCALE IMG...  (review aid)"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / 'tools/vendor/pylib'))
from PIL import Image, ImageDraw

out, cols, scale, files = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), sys.argv[4:]
ims = [Image.open(f).convert('RGB') for f in files]
w, h = max(i.width for i in ims) * scale, max(i.height for i in ims) * scale
rows = (len(ims) + cols - 1) // cols
sheet = Image.new('RGB', (cols * (w + 4), rows * (h + 16)), (40, 40, 40))
d = ImageDraw.Draw(sheet)
for k, (f, im) in enumerate(zip(files, ims)):
    x, y = k % cols * (w + 4), k // cols * (h + 16)
    sheet.paste(im.resize((im.width * scale, im.height * scale), Image.NEAREST), (x, y + 14))
    d.text((x + 2, y + 1), pathlib.Path(f).parent.name + '/' + pathlib.Path(f).stem, fill=(220, 220, 220))
sheet.save(out)
