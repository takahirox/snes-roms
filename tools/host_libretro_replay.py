"""Host audit: replay recorded controller masks on an unmodified libretro core.

No memory writes, save-state injection, or game simulation. Supports cores which do
not expose WRAM/VRAM through libretro, including the pinned bsnes build. Captures
retain raw callback dimensions; a separate integer-sampled image is provided when
the core duplicates the native 256x224 frame to 512x448.
"""
import argparse
import ctypes as C
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import time
import zlib


class Content(C.Structure):
    _fields_ = [('path', C.c_char_p), ('data', C.c_void_p), ('size', C.c_size_t), ('meta', C.c_char_p)]


class Variable(C.Structure):
    _fields_ = [('key', C.c_char_p), ('value', C.c_char_p)]


class Info(C.Structure):
    _fields_ = [('name', C.c_char_p), ('version', C.c_char_p), ('extensions', C.c_char_p),
                ('fullpath', C.c_bool), ('block_extract', C.c_bool)]


class Geometry(C.Structure):
    _fields_ = [('width', C.c_uint), ('height', C.c_uint), ('max_width', C.c_uint),
                ('max_height', C.c_uint), ('aspect', C.c_float)]


class Timing(C.Structure):
    _fields_ = [('fps', C.c_double), ('sample_rate', C.c_double)]


class AVInfo(C.Structure):
    _fields_ = [('geometry', Geometry), ('timing', Timing)]


def png(path, rows):
    height = len(rows); width = len(rows[0])
    raw = b''.join(b'\0' + bytes(v for p in row for v in p) for row in rows)
    def chunk(kind, payload):
        return struct.pack('>I', len(payload)) + kind + payload + struct.pack('>I', zlib.crc32(kind + payload))
    path.write_bytes(b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0))
                     + chunk(b'IDAT', zlib.compress(raw)) + chunk(b'IEND', b''))


class Frontend:
    def __init__(self, core, rom, out, record=False, global_symbols=False):
        self.lib = C.CDLL(str(core.resolve()), mode=C.RTLD_GLOBAL if global_symbols else C.RTLD_LOCAL)
        self.output = out; out.mkdir(parents=True, exist_ok=True)
        self.mask = 0; self.format = 0; self.frame = None; self.frames = 0
        self.audio_samples = 0; self.audio_peak = 0
        self.record = record; self.encoder = None; self.record_size = None
        self.audio_file = (out / 'recording.pcm').open('wb') if record else None
        self.directory = str(out.resolve()).encode()
        self.options = {k.encode(): v.encode() for k, v in {
            'bsnes_ppu_fast': 'OFF', 'bsnes_cpu_overclock': '100',
            'bsnes_cpu_fastmath': 'OFF', 'bsnes_ppu_no_sprite_limit': 'OFF',
            'bsnes_ppu_no_vram_blocking': 'OFF', 'bsnes_blur_emulation': 'OFF',
            'bsnes_hotfixes': 'OFF', 'bsnes_ppu_show_overscan': 'OFF',
            'bsnes_mode7_scale': '1x', 'bsnes_dsp_fast': 'OFF',
            'bsnes_dsp_cubic': 'OFF', 'bsnes_dsp_echo_shadow': 'OFF',
            'bsnes_entropy': 'None',
        }.items()}
        self.options_read = {}
        ENV = C.CFUNCTYPE(C.c_bool, C.c_uint, C.c_void_p)
        VIDEO = C.CFUNCTYPE(None, C.c_void_p, C.c_uint, C.c_uint, C.c_size_t)
        AUDIO = C.CFUNCTYPE(None, C.c_int16, C.c_int16)
        BATCH = C.CFUNCTYPE(C.c_size_t, C.POINTER(C.c_int16), C.c_size_t)
        POLL = C.CFUNCTYPE(None)
        INPUT = C.CFUNCTYPE(C.c_int16, C.c_uint, C.c_uint, C.c_uint, C.c_uint)

        def env(cmd, data):
            if cmd in (9, 31):
                C.cast(data, C.POINTER(C.c_char_p))[0] = self.directory
                return True
            if cmd == 10:
                fmt = C.cast(data, C.POINTER(C.c_int))[0]
                if fmt not in (0, 1, 2): return False
                self.format = fmt
                return True
            if cmd == 15:
                var = C.cast(data, C.POINTER(Variable)).contents
                if var.key not in self.options: return False
                var.value = self.options[var.key]
                self.options_read[var.key.decode()] = self.options[var.key].decode()
                return True
            if cmd == 17:
                C.cast(data, C.POINTER(C.c_bool))[0] = False
                return True
            if cmd in (16, 18, 35, 37): return True
            return False

        def video(data, width, height, pitch):
            if data: self.frame = (width, height, pitch, C.string_at(data, pitch * height))

        def batch(data, n):
            self.audio_samples += n * 2
            if n: self.audio_peak = max(self.audio_peak, max(abs(data[i]) for i in range(n * 2)))
            if self.audio_file: self.audio_file.write(C.string_at(data, n * 4))
            return n

        self.callbacks = [ENV(env), VIDEO(video), AUDIO(lambda l, r: None), BATCH(batch), POLL(lambda: None),
                          INPUT(lambda port, device, index, key: bool(self.mask & (1 << key)) if port == 0 and key < 16 else 0)]
        for name, callback in zip(('environment', 'video_refresh', 'audio_sample', 'audio_sample_batch', 'input_poll', 'input_state'), self.callbacks):
            getattr(self.lib, 'retro_set_' + name)(callback)
        info = Info()
        self.lib.retro_get_system_info(C.byref(info))
        self.info = dict(name=info.name.decode(), version=info.version.decode(), needs_full_path=bool(info.fullpath))
        self.lib.retro_init()
        blob = rom.read_bytes()
        self.rom_sha = hashlib.sha256(blob).hexdigest()
        self.content = C.create_string_buffer(blob)
        self.rom_path = str(rom.resolve()).encode()
        self.lib.retro_load_game.argtypes = [C.POINTER(Content)]
        self.lib.retro_load_game.restype = C.c_bool
        assert self.lib.retro_load_game(C.byref(Content(self.rom_path, C.cast(self.content, C.c_void_p), len(blob), None)))
        self.lib.retro_set_controller_port_device(0, 1)
        av = AVInfo()
        self.lib.retro_get_system_av_info(C.byref(av))
        self.av = dict(fps=av.timing.fps, sample_rate=av.timing.sample_rate,
                       base_size=[av.geometry.width, av.geometry.height])

    def step(self, mask):
        self.mask = mask
        self.lib.retro_run()
        self.frames += 1
        if self.record:
            assert self.frame, 'no video frame to record'
            w, h, pitch, data = self.frame
            if self.encoder is None:
                self.record_size = [w, h]
                fmt = {0: 'rgb555le', 1: 'bgra', 2: 'rgb565le'}[self.format]
                self.encoder = subprocess.Popen([
                    'ffmpeg', '-hide_banner', '-loglevel', 'error', '-y',
                    '-f', 'rawvideo', '-pixel_format', fmt, '-video_size', f'{w}x{h}',
                    '-framerate', str(self.av['fps']), '-i', 'pipe:0',
                    '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '14',
                    '-pix_fmt', 'yuv420p', str(self.output / 'recording.silent.mp4')], stdin=subprocess.PIPE)
            assert self.record_size == [w, h], 'video geometry changed; do not silently rescale'
            bpp = 4 if self.format == 1 else 2
            self.encoder.stdin.write(b''.join(data[y * pitch:y * pitch + w * bpp] for y in range(h)))

    def capture(self, name):
        assert self.frame, 'core supplied no frame'
        w, h, pitch, data = self.frame
        rows = []
        for y in range(h):
            row = []
            for x in range(w):
                if self.format == 1:
                    b, g, r, _ = data[y * pitch + x * 4:y * pitch + x * 4 + 4]
                else:
                    p = struct.unpack_from('<H', data, y * pitch + x * 2)[0]
                    r = ((p >> (11 if self.format == 2 else 10)) & 31) * 255 // 31
                    g = ((p >> 5) & (63 if self.format == 2 else 31)) * 255 // (63 if self.format == 2 else 31)
                    b = (p & 31) * 255 // 31
                row.append((r, g, b))
            rows.append(row)
        name = Path(name).stem
        png(self.output / (name + '-raw.png'), rows)
        scale = None
        if w % 256 == 0 and h % 224 == 0:
            sx, sy = w // 256, h // 224
            rows = [[rows[y * sy][x * sx] for x in range(256)] for y in range(224)]
            png(self.output / (name + '.png'), rows)
            scale = [sx, sy]
        nonblack = sum(max(p) > 16 for row in rows for p in row)
        return dict(name=name, frame=self.frames, callback_size=[w, h], integer_sample_step=scale, nonblack_pixels=nonblack)

    def close(self):
        self.lib.retro_unload_game()
        self.lib.retro_deinit()
        if self.audio_file: self.audio_file.close()
        if self.encoder:
            self.encoder.stdin.close()
            assert self.encoder.wait() == 0, 'video encoding failed'
            subprocess.run([
                'ffmpeg', '-hide_banner', '-loglevel', 'error', '-y',
                '-i', str(self.output / 'recording.silent.mp4'),
                '-f', 's16le', '-ar', str(self.av['sample_rate']), '-ac', '2',
                '-i', str(self.output / 'recording.pcm'), '-c:v', 'copy',
                '-c:a', 'aac', '-b:a', '128k', '-movflags', '+faststart',
                str(self.output / 'recording.mp4')], check=True)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--core', type=Path, required=True)
    p.add_argument('--rom', type=Path, required=True)
    p.add_argument('--trace', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--record', action='store_true', help='record raw core video and audio as recording.mp4')
    args = p.parse_args()
    trace = json.loads(args.trace.read_text())
    assert trace['rom_sha256'] == hashlib.sha256(args.rom.read_bytes()).hexdigest(), 'trace/ROM mismatch'
    e = Frontend(args.core, args.rom, args.out, args.record)
    captures = {}
    for point in trace['captures']: captures.setdefault(point['frame'], []).append(point['name'])
    start = time.time(); images = []
    try:
        for mask in trace['masks']:
            e.step(mask)
            for name in captures.get(e.frames, []): images.append(e.capture(name))
        result = dict(core=e.info, av=e.av, core_sha256=hashlib.sha256(args.core.read_bytes()).hexdigest(), rom_sha256=e.rom_sha,
                      frames=e.frames, elapsed_seconds=round(time.time() - start, 2),
                      core_options_read=e.options_read, captures=images,
                      audio_samples=e.audio_samples, audio_peak=e.audio_peak,
                      recording='recording.mp4' if args.record else None,
                      method='Exact recorded libretro controller masks; no WRAM/SRAM writes, no core patches, raw video callback capture.',
                      scope='Only the scenes in this trace; not a full-game or physical-hardware verification.')
    finally:
        e.close()
    if args.record:
        recording = args.out / 'recording.mp4'
        probe = json.loads(subprocess.check_output([
            'ffprobe', '-v', 'error', '-show_entries',
            'stream=codec_type,width,height,nb_frames,duration,sample_rate',
            '-of', 'json', str(recording)]))
        video = next(s for s in probe['streams'] if s['codec_type'] == 'video')
        assert int(video['nb_frames']) == e.frames, 'recording omitted frames'
        result['recording_sha256'] = hashlib.sha256(recording.read_bytes()).hexdigest()
        result['recording_probe'] = probe
    (args.out / 'replay.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__': main()
