"""Developer tool: run the standard route and report where text_clip increases (screens in build/adv/dev/clip)."""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from drive import Driver, ROOT
import routes

OUT = ROOT / 'build/adv/dev/clip'
seen = [0]


def obs(g):
    c = g.w('text_clip')
    if c != seen[0]:
        seen[0] = c
        print('text_clip', c, 'frame', g.frame, 'mode', g.w('mode'), 'list_kind', g.w('list_kind'),
              'msg_x', g.w('msg_x'), 'msg_y', g.w('msg_y'), 'g_x', g.w('g_x'), 'g_y', g.w('g_y'),
              'g_glyph', g.w('g_glyph'), 'clip_right', g.w('clip_right'), 'last', g.log[-1:] if g.log else None)
        g.shot(OUT / f'clip{c:03d}.png')


g = Driver()
g.observers.append(obs)
g.boot_menu()
g.tap('A')
g.settle()
routes.standard(g)
routes.deduce(g)
g.close()
