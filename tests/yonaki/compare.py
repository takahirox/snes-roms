"""Compare the packed Yonaki ROM with the pre-packing revision. Run after run.py --real."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import ctypes as C
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
from emu import ROOT, labels
from host_libretro_replay import Frontend
from transfer_probe import Transfers, build as build_probe
from upgrade import prepare_bookmarks, resume_state

BASELINE = 'ff5fe48380161e4235ceb41856662f5afc47018e'
OUT = ROOT / 'build/yonaki-comparison'
TRACES = ROOT / 'build/yonaki-test/traces'
CORES = ('snes9x', 'bsnes')
TRACES_TO_COMPARE = ('effects', 'ending_G02', 'real_E06', 'real_E13')
# Frame numbers are 1-based frontend callbacks in the existing effects and ending traces.
# Each entry gives the start of the probe window, settled reference frame, and
# expected first response and settle frames. The bus follows a timed chapter card.
SCENES = {
    'effects': {'bus_fade': (550, 599, 570, 598), 'genkan_white': (808, 879, 810, 874),
                'lobby_mosaic': (954, 1042, 956, 1039)},
    'ending_G02': {'old_bath_cut': (1083, 1098, 1086, 1098)},
}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def baseline_build(source):
    archive = subprocess.check_output(['git', 'archive', BASELINE, 'assets', 'data', 'src', 'tools', 'tests'], cwd=ROOT)
    subprocess.run(['tar', '-xf', '-', '-C', str(source)], input=archive, check=True)
    (source / 'tools/vendor').symlink_to(ROOT / 'tools/vendor', target_is_directory=True)
    subprocess.run([sys.executable, '-I', '-c',
                    'from pathlib import Path; import sys; '
                    'sys.path.insert(0, str(Path("tests/yonaki").resolve())); import buildrom; '
                    'buildrom.build_fixture(); buildrom.build(buildrom.ROOT / "build/yonaki")'],
                   cwd=source, check=True)


def memory(lib, kind, size):
    lib.retro_get_memory_data.argtypes = [C.c_uint]
    lib.retro_get_memory_data.restype = C.c_void_p
    lib.retro_get_memory_size.argtypes = [C.c_uint]
    lib.retro_get_memory_size.restype = C.c_size_t
    address = lib.retro_get_memory_data(kind)
    assert address and lib.retro_get_memory_size(kind) == size, (kind, size)
    return (C.c_ubyte * size).from_address(address)


class Replay(Frontend):
    def __init__(self, core_name, core, rom, out, initial_sram):
        out.mkdir(parents=True, exist_ok=True)
        self.battery = out / 'yonaki.srm'
        self.core_name = core_name
        # bsnes restores and exports its battery on load/unload, using the ROM basename.
        if core_name == 'bsnes':
            self.battery.write_bytes(initial_sram)
        super().__init__(core, rom, out)
        self.addresses = labels(rom.with_name('labels.txt'))
        if core_name == 'snes9x':
            self.sram = memory(self.lib, 0, 8192)
            self.sram[:] = initial_sram
            self.ram = memory(self.lib, 2, 128 * 1024)
        else:
            self.lib.yonaki_probe_wram.restype = C.POINTER(C.c_ubyte * (128 * 1024))
            self.ram = self.lib.yonaki_probe_wram().contents

    def b(self, field, size, offset=0):
        address = self.addresses[field] & 0x1ffff
        return bytes(self.ram[address + offset:address + offset + size])

    def w(self, field, offset=0):
        return int.from_bytes(self.b(field, 2, offset), 'little')

    def close(self):
        # Read Snes9x's battery before unloading its memory.
        final = bytes(self.sram) if self.core_name == 'snes9x' else None
        super().close()
        return final if final is not None else self.battery.read_bytes()


class PCM:
    """Hash native stereo PCM without resampling or buffering the entire trace."""
    def __init__(self):
        self.digest = hashlib.sha256()
        self.bytes = 0

    def write(self, data):
        self.digest.update(data)
        self.bytes += len(data)

    def close(self):
        pass


def pixels(frontend, margins=False):
    w, h, pitch, data = frontend.frame
    bpp = 4 if frontend.format == 1 else 2
    if margins:
        assert w % 256 == h % 224 == 0, (w, h)
        # Restrict the timing measurement to the photo margins outside the text.
        sx, sy = w // 256, h // 224
        return b''.join(data[y * sy * pitch + x * sx * bpp:y * sy * pitch + (x + 14) * sx * bpp]
                        for y in range(24, 200) for x in (4, 238))
    return b''.join(data[y * pitch:y * pitch + w * bpp] for y in range(h))


def scene_frames(frames, scenes):
    results = {}
    for scene, (action, reference, first_expected, settled_expected) in scenes.items():
        before = frames[action - 1]
        settled = frames[reference]
        assert before != settled, f'{scene} has no photo change'
        response = next(i for i in range(action, reference + 1) if frames[i] != before)
        final = 1 + max(i for i in range(action - 1, reference) if frames[i] != settled)
        assert (response, final) == (first_expected, settled_expected), (scene, response, final)
        results[scene] = dict(first_response=response, settled_photo=final,
                              response_frames=response - action, settle_frames=final - action)
    return results


def replay(core_name, core, rom, trace_file, out):
    trace = json.loads(trace_file.read_text())
    initial = trace_file.with_suffix('.in.srm').read_bytes()
    assert len(initial) == 8192 and sha(initial) == trace['input_sram_sha256'], trace_file
    frontend = Replay(core_name, core, rom, out, initial)
    pcm = PCM()
    frontend.audio_file = pcm
    frames, captures, states = {}, {}, {}
    scenes = SCENES.get(trace_file.stem, {})
    sample_frames = {frame for start, end, _, _ in scenes.values() for frame in range(start - 1, end + 1)}
    capture_frames = {c['frame'] for c in trace['captures']}
    checkpoints = trace.get('checkpoints', {})
    try:
        for i, mask in enumerate(trace['masks'], 1):
            frontend.step(mask)
            if i in sample_frames:
                frames[i] = sha(pixels(frontend, margins=True))
            if i in capture_frames:
                captures[i] = sha(pixels(frontend))
            if str(i) in checkpoints:
                point, expected = checkpoints[str(i)]
                state = resume_state(frontend, point)
                assert state == expected, (point, i, state, expected)
                states[point] = dict(frame=i, state=state)
        counters = {name: frontend.w(name) for name in ('vblank_overrun_count', 'dma_deferred')}
        transfers = Transfers.read(frontend.lib)
        rate = frontend.av['sample_rate']
    finally:
        final = frontend.close()
    assert len(final) == 8192 and sha(final) == trace['output_sram_sha256'], (trace_file.stem, 'final battery')
    assert counters == dict(vblank_overrun_count=0, dma_deferred=0), counters
    assert transfers['violations'] == 0, transfers
    assert 0 < transfers['visible_dma_peak'] <= 3072, transfers
    assert transfers['forced_dma_max_transfer'] == 65536, transfers  # boot VRAM clear
    assert pcm.bytes and frontend.audio_peak and pcm.bytes == 2 * frontend.audio_samples, 'missing PCM'
    return dict(rom_sha256=frontend.rom_sha, frames=frontend.frames, initial_sram_sha256=sha(initial),
                final_sram_sha256=sha(final), captures=captures, checkpoints=states,
                scene_frames=scene_frames(frames, scenes),
                scene_pixels_sha256=sha(''.join(frames.values()).encode()), **counters, transfers=transfers,
                pcm=dict(sha256=pcm.digest.hexdigest(), sample_frames=pcm.bytes // 4, rate_hz=rate,
                         peak=frontend.audio_peak))


def compare(core_name, core, baseline, name, trace_file, candidate, out):
    results = {}
    for version, rom in (('baseline', baseline), ('packed', candidate)):
        path = out / core_name / name / version
        # Core globals and audio buffers start fresh on each replay.
        subprocess.run([sys.executable, '-I', __file__, '--replay', core_name, str(core), str(rom),
                        str(trace_file), str(path)], check=True)
        results[version] = json.loads((path / 'result.json').read_text())
    old, new = results.values()
    assert old['rom_sha256'] != new['rom_sha256'], (name, 'expected distinct ROMs')
    for field in ('captures', 'checkpoints', 'scene_frames', 'scene_pixels_sha256', 'pcm'):
        assert old[field] == new[field], (core_name, name, field, old[field], new[field])
    for field in ('visible_dma_bytes', 'visible_dma_peak', 'forced_dma_bytes', 'hdma_bytes', 'hdma_peak'):
        assert old['transfers'][field] == new['transfers'][field], (core_name, name, field, old, new)
    print(f'PASS {core_name} {name}', flush=True)
    return results


def compare_core(name, core, source, bookmarks):
    results = {}
    for trace_name in TRACES_TO_COMPARE:
        trace_file = TRACES / f'{trace_name}.json'
        trace = json.loads(trace_file.read_text())
        candidate = ROOT / trace['rom']
        assert sha(candidate.read_bytes()) == trace['rom_sha256'], f'{trace_name}: trace / ROM mismatch'
        results[trace_name] = compare(name, core, source / trace['rom'], trace_name, trace_file, candidate, OUT)
    assert results['effects']['packed']['transfers']['hdma_peak'] == 450, 'ripple peak was not exercised'
    assert results['real_E06']['packed']['transfers']['visible_dma_peak'] == 3072, 'DMA queue limit was not exercised'
    for path in bookmarks:
        results[path.stem] = compare(name, core, source / 'build/yonaki/yonaki.sfc',
                                     path.stem, path, ROOT / 'build/yonaki/yonaki.sfc', OUT)
    return results


def check_bookmark_upgrade(name, core, bookmarks):
    rom = ROOT / 'build/yonaki/yonaki.sfc'
    results = {}
    for trace in bookmarks:
        path = OUT / name / trace.stem / 'current'
        subprocess.run([sys.executable, '-I', __file__, '--replay', name, str(core), str(rom),
                        str(trace), str(path)], check=True)
        results[trace.stem] = json.loads((path / 'result.json').read_text())
        print(f'PASS {name} {trace.stem}', flush=True)
    return results


def main(upgrade_only=False):
    OUT.mkdir(parents=True, exist_ok=True)
    report = OUT / ('UPGRADE.json' if upgrade_only else 'RESULTS.json')
    report.unlink(missing_ok=True)
    with tempfile.TemporaryDirectory(dir=OUT, prefix='baseline-') as directory, ThreadPoolExecutor() as pool:
        source = Path(directory)
        build = pool.submit(baseline_build, source)
        probes = {name: pool.submit(build_probe, name, OUT / 'cores') for name in CORES}
        build.result()
        traces = None if upgrade_only else TRACES
        bookmarks = prepare_bookmarks(source / 'build/yonaki', traces, OUT / 'upgrade')
        if upgrade_only:
            runs = {name: pool.submit(check_bookmark_upgrade, name, probes[name].result(), bookmarks) for name in CORES}
        else:
            runs = {name: pool.submit(compare_core, name, probes[name].result(), source, bookmarks) for name in CORES}
        results = {name: run.result() for name, run in runs.items()}
    report.write_text(json.dumps(dict(baseline_revision=BASELINE, cores=results), indent=2) + '\n')
    print(f'Yonaki verification passed. {report.relative_to(ROOT)}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--upgrade-only', action='store_true',
                        help='verify bookmark upgrades independently of intentional presentation changes')
    parser.add_argument('--replay', nargs=5, metavar=('CORE_NAME', 'CORE', 'ROM', 'TRACE', 'OUT'))
    options = parser.parse_args()
    if options.replay:
        name, core, rom, trace, out = options.replay
        result = replay(name, Path(core), Path(rom), Path(trace), Path(out))
        (Path(out) / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    else:
        main(options.upgrade_only)
