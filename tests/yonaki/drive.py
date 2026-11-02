"""High-level pad driver for 夜鳴き鐘 tests (pad bits only; WRAM is read, never written).

The driver reads ui_state and the choice / menu cursor from WRAM and presses the buttons a player would:
A through paragraphs, up / down until the wanted option is under the cursor, A.
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from emu import Game, ROOT, ST     # noqa: E402

MOVING = {'TYPE', 'WAIT', 'BUSY', 'CHAPTER', 'BOOT'}


class Stuck(Exception):
    pass


class Monitor:
    """Per frame: the worst NMI end line, overruns, glyph clipping (read from WRAM)."""

    def __init__(self):
        self.max_end = 0

    def __call__(self, g):
        if g.w('vblank_overrun_count'):
            raise AssertionError(f'V-blank overrun at frame {g.frame} (state {g.state()})')


class Driver(Game):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.mon = Monitor()
        self.observers.append(self.mon)
        self.texts_seen = []
        self.opt_by_addr = {}
        for cid, c in self.layout['choices'].items():
            for k, o in enumerate(c['options']):
                self.opt_by_addr[o['text_addr']] = (int(cid), k, o)

    def until(self, pred, limit=3000, what='condition'):
        for _ in range(limit):
            if pred():
                return
            self.run(1)
        raise Stuck(f'{what} not reached in {limit} frames (state {self.state()})')

    def press(self, button, want, limit=600):
        """Tap a button and wait for the state want (a menu, the wait after it closes...)."""
        self.tap(button, 2, 2)
        self.until(lambda: self.state() == want, limit, f'{button} -> {want}')
        self.run(2)

    def title(self, limit=1500):
        self.until(lambda: self.state() == 'TITLE' and self.w('bright') == 15, limit, 'title')
        self.run(4)

    def title_items(self):
        n = self.w('menu_count')
        return [self.w('menu_kind', 2 * i) for i in range(n)]

    def title_pick(self, kind):
        """kind: 0 はじめから, 1 しおりから, 2 結末の一覧, 3 おまけ"""
        items = self.title_items()
        if kind not in items:
            raise Stuck(f'title item {kind} not in {items}')
        self.menu_to(items.index(kind))
        self.tap('A', 2, 4)
        if kind == 0:
            self.names()

    def name_pick(self, row, col):
        """Name entry: move the cursor to (row, col) of the page (row NAME_ROWS: the commands) and press A."""
        for _ in range(40):
            if self.w('ne_row') == row:
                break
            self.tap('DOWN', 2, 3)
        for _ in range(40):
            if self.w('ne_col') == col:
                break
            self.tap('RIGHT', 2, 3)
        assert (self.w('ne_row'), self.w('ne_col')) == (row, col), 'name cursor'
        self.tap('A', 2, 6)

    def name_glyphs(self, field):
        n = self.w('names', field * 10)
        return [self.w('names', field * 10 + 2 + 2 * i) for i in range(n)]

    def names(self, limit=600):
        """The name entry after はじめから: keep the names shown (START on each name)."""
        for _ in range(2):
            self.until(lambda: self.state() == 'NAME', limit, 'name entry')
            self.tap('START', 2, 4)

    def menu_to(self, want):
        for _ in range(16):
            if self.w('menu_sel') == want:
                return
            self.tap('DOWN', 2, 3)
        raise Stuck(f'menu cursor never reached {want}')

    def advance(self, limit=20000, fast=True):
        """Through paragraphs (A) until a choice, an ending, the title or a menu.  Returns the state."""
        start = self.frame
        while self.frame - start < limit:
            st = self.state()
            if st == 'WAIT':
                t = self.w('cur_text')
                if not self.texts_seen or self.texts_seen[-1] != t:
                    self.texts_seen.append(t)
                self.tap('A', 1, 1)
            elif st == 'TYPE':
                if fast:
                    self.tap('A', 1, 1)
                else:
                    self.run(1)
            elif st in MOVING:
                self.run(1)
            else:
                self.run(2)
                if self.state() == st:
                    return st
        raise Stuck(f'advance: still {self.state()} after {limit} frames')

    def options(self):
        """The visible options of the choice on screen: [(choice id, option index, option dict)]."""
        n = self.w('opt_count')
        out = []
        for k in range(n):
            a = self.w('opt_text', 2 * k) | self.w('opt_tbank', 2 * k) << 16
            out.append(self.opt_by_addr[a])
        return out

    def choose(self, target=None, text=None, index=None):
        assert self.state() == 'CHOICE', self.state()
        opts = self.options()
        if index is None:
            for i, (_, _, o) in enumerate(opts):
                if (target and o['target'] == target) or (text and o['text'] == text):
                    index = i
                    break
            else:
                raise Stuck(f'option {target or text} not in {[o["text"] for _, _, o in opts]}')
        for _ in range(16):
            if self.w('opt_sel') == index:
                break
            self.tap('DOWN', 2, 3)
        assert self.w('opt_sel') == index
        self.tap('A', 2, 2)

    def new_game(self):
        self.title()
        self.title_pick(0)

    def play(self, path, final='ENDING'):
        """Follow a route (routes.plan path) to its end."""
        for cid, k, lab, text in path:
            st = self.advance()
            if st != 'CHOICE':
                raise Stuck(f'expected a choice before "{text}", state {st}')
            assert self.w('choice_id') == cid, (self.w('choice_id'), cid)
            self.choose(index=k)
        st = self.advance()
        assert st == final, (st, final)
        return st

    def ending_to_title(self):
        assert self.state() == 'ENDING'
        for _ in range(60):
            self.tap('A', 2, 8)
            if self.state() != 'ENDING':
                break
        self.title()
