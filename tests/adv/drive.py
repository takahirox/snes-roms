"""High-level pad driver for 潮鳴りの密室 tests (pad bits only; WRAM is read, never written).

Navigation reads the current list (list_label text ids) from WRAM and moves the cursor with the
d-pad until the wanted entry is under it, then presses A -- the same thing a player does by looking.
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from emu import Game, ROOT

M_CMD, M_LIST, M_MSG, M_FADE, M_END, M_OPEN = range(6)
OP_TITLE = 2                     # op_state of the title screen (src/adv/opening.inc)
CMDS = ['はなす', 'しらべる', 'みせる', 'いどう', 'てちょう']


def fw(s):
    return ''.join(chr(ord(c) + 0xFEE0) if 0x21 <= ord(c) <= 0x7E else c for c in s)


class Stuck(Exception):
    pass


class Driver(Game):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.text_ids = {}
        for i, t in enumerate(self.layout['texts']):
            if t['kind'] == 'label':
                self.text_ids.setdefault(t['text'], i)
        self.pages_seen = 0
        self.log = []

    def mode(self):
        return self.w('mode')

    def settle(self, limit=6000, fast=True):
        """Run until the game waits for a command / list choice / ending; page through messages with A."""
        start = self.frame
        while self.frame - start < limit:
            m = self.mode()
            if m == M_MSG:
                st = self.w('msg_state')
                if st == 0:
                    if fast and self.w('msg_fast') == 0:
                        self.tap('A', 1, 1)
                    else:
                        self.run(1)
                else:
                    self.pages_seen += 1
                    self.tap('A', 2, 2)
            elif m == M_FADE:
                self.run(1)
            else:
                self.run(2)
                if self.mode() == m and self.w('mode') not in (M_MSG, M_FADE):
                    return m
        raise Stuck(f'no stable state after {limit} frames (mode {self.mode()})')

    def quiet(self, limit=120):
        """Run until every text row and picture tile is uploaded (dirty_rows 0, no stream, no fade)."""
        for _ in range(limit):
            self.run(1)
            if (self.w('dirty_rows') == 0 and self.w('img_left') == 0 and self.w('por_rows') == 0
                    and self.w('fade_state') == 0 and self.w('pal_dirty') == 0):
                self.run(2)
                return
        raise Stuck('uploads did not settle')

    def list_texts(self):
        n = self.w('list_count')
        return [self.w('list_label', i * 2) for i in range(n)]

    def list_names(self):
        names = {v: k for k, v in self.text_ids.items()}
        return [names.get(t, f'#{t}') for t in self.list_texts()]

    def title_screen(self, skip=True, limit=4000):
        """From power-on (or the ending): to the title screen with PUSH START BUTTON shown.  skip: START
        during the prologue (as a player would); otherwise the opening plays to the end."""
        start = self.frame
        while self.frame - start < limit:
            if self.mode() == M_OPEN and self.w('op_state') == OP_TITLE and self.w('op_ui_level') == 16 \
                    and self.w('fade_level') == 16 and self.w('op_pic_state') == 0:
                return
            if skip and self.mode() == M_OPEN and self.w('op_state') == 0 and self.frame - start >= 2:
                self.tap('START', 2, 2)
            else:
                self.run(1)
        raise Stuck('the title did not come')

    def title_menu(self, skip=True):
        """From power-on: the title menu (はじめから / つづきから)."""
        self.title_screen(skip)
        self.tap('START', 2, 4)
        assert self.mode() == M_LIST and self.w('list_kind') == 9, ('no title menu', self.mode(), self.w('list_kind'))
        self.quiet()

    def boot_menu(self):
        """Power-on to the title menu: this ROM through its opening (skipped with START), an earlier
        candidate ROM (no opening: its title menu comes by itself) after 40 frames."""
        if self.mode() == M_LIST and self.w('list_kind') == 9:
            return
        if 'op_state' in self.L:
            self.title_menu()
        else:
            self.run(40)

    def ending_to_title(self):
        """On the ending: A, and the title screen comes back (PUSH START BUTTON)."""
        assert self.mode() == M_END, self.mode()
        self.tap('A')
        self.title_screen(skip=False)
        assert self.mode() == M_OPEN and self.w('op_state') == OP_TITLE

    def to_cmd(self):
        for _ in range(4):
            if self.mode() == M_CMD:
                return
            self.tap('B')
            self.settle()
        raise Stuck('cannot get back to the command menu')

    def cmd(self, name):
        if self.mode() != M_CMD:
            self.to_cmd()
        want = CMDS.index(name)
        for _ in range(8):
            cur = self.w('cmd_sel')
            if cur == want:
                break
            self.tap('DOWN' if (want - cur) % 5 <= 2 else 'UP')
        assert self.w('cmd_sel') == want
        self.tap('A')
        self.settle()

    def pick(self, label):
        label = fw(label)
        tid = self.text_ids.get(label)
        if tid is None:
            raise KeyError(f'no label text {label}')
        items = self.list_texts()
        if tid not in items:
            raise Stuck(f'"{label}" is not in the list {self.list_names()}')
        want = items.index(tid)
        for _ in range(64):
            cur = self.w('list_sel')
            if cur == want:
                break
            self.tap('DOWN' if want > cur else 'UP')
        assert self.w('list_sel') == want
        self.log.append(label)
        self.tap('A')
        return self.settle()

    def look(self, *labels):
        self.cmd('しらべる')
        for l in labels:
            self.pick(l)
        self.to_cmd()

    def talk(self, *labels):
        self.cmd('はなす')
        for l in labels:
            self.pick(l)
        self.to_cmd()

    def show(self, *clues):
        self.cmd('みせる')
        for c in clues:
            self.pick(self.layout['clue_names'][c])
        self.to_cmd()

    def move(self, scene_name):
        self.cmd('いどう')
        self.pick(scene_name)
        assert self.mode() == M_CMD

    def note(self, label):
        self.cmd('てちょう')
        return self.pick(label)
