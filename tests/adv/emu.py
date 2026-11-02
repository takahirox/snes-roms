"""Snes9x 1.63 (unmodified libretro core) driver for 潮鳴りの密室: pad input only, WRAM read by label.

The game is driven only through the joypad bits given to the core's input callback.  WRAM/VRAM/CGRAM
are read through the core's memory API for checks.  The battery SRAM is handled like a frontend's .srm
file: read after a session and handed to a fresh core before its first frame (power cycle), or
written with a prepared image before the first frame for the empty/corrupt cases.  Nothing else is
written into the emulated machine.
"""
import pathlib, sys, json, hashlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tests'))
sys.path.insert(0, str(ROOT / 'tools'))
from harness import Emulator
import png_codec

ROM = 'build/adv/shionari.sfc'
IDS = {'B': 0, 'Y': 1, 'SELECT': 2, 'START': 3, 'UP': 4, 'DOWN': 5, 'LEFT': 6, 'RIGHT': 7, 'A': 8, 'X': 9, 'L': 10, 'R': 11}


def labels(path=None):
    out = {}
    for line in pathlib.Path(path or ROOT / 'build/adv/labels.txt').read_text().splitlines():
        p = line.split()
        if len(p) >= 3:
            out[p[2].lstrip('.')] = int(p[1], 16)
    return out


def layout():
    return json.loads((ROOT / 'build/adv/layout.json').read_text())


class Game:
    def __init__(self, rom=ROM, sram=None, label_file=None):
        self.e = Emulator(rom)
        self.L = labels(label_file)
        self.layout = layout()
        self.masks = []
        self.captures = []
        self.frame = 0
        self.observers = []
        assert self.e.sram is not None and len(self.e.sram) >= 8192, 'core exposes no 8 KiB battery RAM'
        if sram is not None:                 # battery image, before the first frame (like loading a .srm)
            assert len(sram) == len(self.e.sram), 'battery image size'
            for i, b in enumerate(sram):
                self.e.sram[i] = b
        self.initial_sram = bytes(self.e.sram)   # what the first retro_run sees
        self.sram_files = {}

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

    def flag(self, name):
        f = self.layout['flags'][name]
        return bool(self.e.ram[self.addr('flags') + (f >> 3)] >> (f & 7) & 1)

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

    def shot(self, path):
        w, h, pitch, data = self.e.frame
        rows = []
        for y in range(h):
            row = []
            for x in range(w):
                if self.e.pixel_format == 1:
                    bb, g, r, _ = data[y * pitch + x * 4:y * pitch + x * 4 + 4]
                else:
                    p = data[y * pitch + x * 2] | data[y * pitch + x * 2 + 1] << 8
                    if self.e.pixel_format == 2:
                        r, g, bb = (p >> 11 & 31) * 255 // 31, (p >> 5 & 63) * 255 // 63, (p & 31) * 255 // 31
                    else:
                        r, g, bb = (p >> 10 & 31) * 255 // 31, (p >> 5 & 31) * 255 // 31, (p & 31) * 255 // 31
                row.append((r, g, bb))
            rows.append(row)
        path = pathlib.Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        png_codec.write(path, rows)
        self.captures.append(dict(frame=self.frame, name=path.stem))
        return rows

    def save_battery(self, folder):
        """initial.srm (before the first frame) and final.srm (now) of this session."""
        folder = pathlib.Path(folder)
        folder.mkdir(parents=True, exist_ok=True)
        final = bytes(self.e.sram)
        for name, data in (('initial.srm', self.initial_sram), ('final.srm', final)):
            (folder / name).write_bytes(data)
            self.sram_files[name] = dict(path=str((folder / name).relative_to(ROOT)),
                                         sha256=hashlib.sha256(data).hexdigest(), bytes=len(data))
        return final

    def trace(self, path):
        pathlib.Path(path).parent.mkdir(parents=True, exist_ok=True)
        pathlib.Path(path).write_text(json.dumps(dict(
            rom_sha256=self.e.rom_sha256, masks=self.masks, captures=self.captures,
            input_sram=self.sram_files.get('initial.srm'), output_sram=self.sram_files.get('final.srm'),
            battery='input_sram is the 8 KiB battery RAM before the first retro_run; output_sram after the last frame'),
            indent=0) + '\n')

    def close(self):
        self.e.close()
