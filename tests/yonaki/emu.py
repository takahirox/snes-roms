"""Snes9x 1.63 (unmodified libretro core, tests/harness.py) driver for 夜鳴き鐘: pad input only, WRAM read by label.

The game is driven only through the joypad bits handed to the core's input callback.  WRAM / VRAM / SRAM are
read through the core's memory API.  The battery SRAM is handled like a frontend's .srm file: read after a
session and handed to a fresh core before its first frame (a power cycle), or a prepared image (empty /
corrupt cases) is written before the first frame.  Nothing else is written into the emulated machine.
"""
import pathlib, sys, json, hashlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tests'))
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'tools/vendor/pylib'))
from harness import Emulator           # noqa: E402

IDS = {'B': 0, 'Y': 1, 'SELECT': 2, 'START': 3, 'UP': 4, 'DOWN': 5, 'LEFT': 6, 'RIGHT': 7, 'A': 8, 'X': 9, 'L': 10,
       'R': 11}
ST = dict(BOOT=0, TITLE=1, TYPE=2, WAIT=3, CHOICE=4, MENU=5, SLOTS=6, ENDLIST=7, ENDING=8, CHAPTER=9, BUSY=10,
          CONFIRM=11, NAME=12)
STN = {v: k for k, v in ST.items()}


def labels(path):
    out = {}
    for line in pathlib.Path(path).read_text().splitlines():
        p = line.split()
        if len(p) >= 3:
            out[p[2].lstrip('.')] = int(p[1], 16)
    return out


class Game:
    def __init__(self, build=ROOT / 'build/yonaki', sram=None):
        build = pathlib.Path(build)
        self.build = build
        rom = build / 'yonaki.sfc'
        self.e = Emulator(str(rom.relative_to(ROOT)) if rom.is_relative_to(ROOT) else str(rom))
        self.L = labels(build / 'labels.txt')
        self.layout = json.loads((build / 'layout.json').read_text())
        self.masks = []
        self.frame = 0
        self.observers = []
        assert self.e.sram is not None and len(self.e.sram) >= 8192, 'core exposes no 8 KiB battery RAM'
        if sram is not None:
            assert len(sram) == len(self.e.sram), 'battery image size'
            for i, b in enumerate(sram):
                self.e.sram[i] = b
        self.initial_sram = bytes(self.e.sram)
        self.captures = []

    # -- memory (read only)
    def addr(self, name):
        a = self.L[name]
        return a & 0x1FFFF if a >= 0x7E0000 else a & 0xFFFF

    def w(self, name, i=0):
        a = self.addr(name) + i
        return self.e.ram[a] | self.e.ram[a + 1] << 8

    def b(self, name, n, ofs=0):
        a = self.addr(name) + ofs
        return bytes(self.e.ram[a:a + n])

    def wram(self, a, n):
        return bytes(self.e.ram[a:a + n])

    def state(self):
        return STN.get(self.w('ui_state'), self.w('ui_state'))

    def sram_image(self):
        return bytes(self.e.sram[:8192])

    # -- input
    def run(self, n=1, buttons=()):
        mask = sum(1 << IDS[b] for b in buttons)
        for _ in range(n):
            self.e.mask = mask
            self.e.lib.retro_run()
            self.masks.append(mask)
            self.frame += 1
            for f in self.observers:
                f(self)

    def tap(self, b, hold=2, after=3):
        self.run(hold, (b,))
        self.run(after)

    def screen(self):
        """The current frame as a numpy (h, w, 3) uint8 array."""
        import numpy as np
        w, h, pitch, data = self.e.frame
        if self.e.pixel_format == 1:
            a = np.frombuffer(data, np.uint8).reshape(h, pitch // 4, 4)[:, :w, :3][..., ::-1]
        else:
            p = np.frombuffer(data, '<u2').reshape(h, pitch // 2)[:, :w].astype(np.uint32)
            if self.e.pixel_format == 2:
                r, g, b = (p >> 11 & 31) * 255 // 31, (p >> 5 & 63) * 255 // 63, (p & 31) * 255 // 31
            else:
                r, g, b = (p >> 10 & 31) * 255 // 31, (p >> 5 & 31) * 255 // 31, (p & 31) * 255 // 31
            a = np.stack([r, g, b], 2)
        return a.astype(np.uint8)

    def shot(self, path, scale=1):
        from PIL import Image
        im = Image.fromarray(self.screen())
        if im.height > 239:                       # hi-res / interlace frames: keep the 256x224 look
            im = im.resize((256, 224), Image.NEAREST)
        if scale != 1:
            im = im.resize((im.width * scale, im.height * scale), Image.NEAREST)
        path = pathlib.Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        im.save(path)
        self.captures.append(dict(frame=self.frame, path=str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path), scale=scale))
        return path

    def trace(self, path):
        """Pad masks, the battery before the first frame and after the last (.srm files next to the trace) and the
        screenshots taken (frame numbers): tests/yonaki/bsnes.py replays it on a second core."""
        path = pathlib.Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.with_suffix('.in.srm').write_bytes(self.initial_sram)
        path.with_suffix('.out.srm').write_bytes(self.sram_image())
        path.write_text(json.dumps(dict(
            rom=str(self.build.relative_to(ROOT) / 'yonaki.sfc'), rom_sha256=self.e.rom_sha256, masks=self.masks,
            captures=self.captures, input_sram_sha256=hashlib.sha256(self.initial_sram).hexdigest(),
            output_sram_sha256=hashlib.sha256(self.sram_image()).hexdigest()), indent=0) + '\n')

    def close(self):
        self.e.close()
