"""Developer captures (not part of adv-test): intro pages, command screen, lists -> build/adv/dev/."""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from drive import Driver, ROOT

OUT = ROOT / 'build/adv/dev'


def stats(g):
    return {k: g.w(k) for k in ('mode', 'scene', 'text_clip', 'lag_count', 'vblank_overrun_count',
                                'dma_bytes_max', 'nmi_end_line_max', 'dma_deferred')}


def main():
    g = Driver()
    g.boot_menu()
    g.tap('A')
    n = 0
    for _ in range(80):
        g.run(20)
        if g.mode() == 2 and g.w('msg_state') != 0:
            g.quiet(); g.shot(OUT / f'intro{n:02d}.png')
            n += 1
            g.tap('A')
        if g.mode() not in (2, 3):
            break
    g.quiet(); g.shot(OUT / 'cmd0.png')
    print(stats(g))
    g.cmd('しらべる')
    g.quiet(); g.shot(OUT / 'look.png')
    print(g.list_names())
    for _ in range(9):
        g.tap('DOWN')
    g.quiet(); g.shot(OUT / 'look_scroll.png')
    g.pick('荷揚げ口')
    g.to_cmd()
    g.cmd('はなす')
    g.quiet(); g.shot(OUT / 'talk.png')
    g.pick('検視')
    g.quiet(); g.shot(OUT / 'talk_after.png')
    g.to_cmd()
    g.quiet(); g.shot(OUT / 'cmd_back.png')
    g.cmd('いどう')
    g.quiet(); g.shot(OUT / 'move.png')
    g.pick('汐見署')
    g.quiet(); g.shot(OUT / 'station.png')
    g.cmd('てちょう')
    g.quiet(); g.shot(OUT / 'note.png')
    g.pick('しょうこ')
    g.quiet(); g.shot(OUT / 'items.png')
    print(stats(g))
    g.close()


if __name__ == '__main__':
    main()
