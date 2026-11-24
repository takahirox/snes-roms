"""Build separate read-only probes against the sources pinned by tools/bootstrap.py."""
import ctypes
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VENDOR = ROOT / 'tools/vendor'
DARWIN = sys.platform == 'darwin'
EXT = 'dylib' if DARWIN else 'so'
HEADER = Path(__file__).with_suffix('.h')


def insert(root, file, anchor, before='', after=''):
    path = root / file
    source = path.read_text()
    if source.count(anchor) != 1:
        raise RuntimeError(f'{file}: expected one probe anchor {anchor!r}')
    path.write_text(source.replace(anchor, before + anchor + after))


def snes9x(root):
    insert(root, 'dma.cpp', '#include "dma.h"\n', after='''
#include "transfer_probe.h"

static YonakiBeam yonaki_beam() {
    return {unsigned(CPU.V_Counter), unsigned(CPU.Cycles), unsigned(Timings.H_Max),
            unsigned(PPU.ScreenHeight + FIRST_VISIBLE_LINE), unsigned(Timings.HBlankStart),
            yonaki_frame, bool(Memory.FillRAM[0x2100] & 0x80)};
}
''')
    insert(root, 'dma.cpp', '\t// Check invalid DMA first\n', before='''
    bool yonaki_ppu = !d->ReverseTransfer && d->BAddress <= 0x3f;
    unsigned yonaki_bytes = d->TransferBytes ? d->TransferBytes : 0x10000;
    auto yonaki_start = yonaki_beam();

''')
    insert(root, 'dma.cpp', '\t// Release the memory used in SPC7110 DMA\n',
           before='    if (yonaki_ppu) yonaki_mdma(yonaki_start, yonaki_beam(), yonaki_bytes);\n\n')
    insert(root, 'dma.cpp', '\t\t\t\treturn (FALSE); \\\n\t\t\t}\n\n\t\twhile (1)',
           before='                if (yonaki_ppu) yonaki_violation("Interrupted PPU DMA", yonaki_start, yonaki_beam()); \\\n')
    insert(root, 'dma.cpp', '\t\t\tif (p->DoTransfer)\n\t\t\t{\n\t\t\t\t// XXX: Hack',
           before='            auto yonaki_start = yonaki_beam();\n')
    anchor = '\t\t\t}\n\t\t}\n\t}\n\n\tfor (mask = 1, p = &DMA[0], d = 0; mask; mask <<= 1, p++, d++)'
    insert(root, 'dma.cpp', anchor, before='''
                yonaki_hdma(yonaki_start, yonaki_beam(), d,
                            p->ReverseTransfer || p->TransferMode != 2 ? 0xff : p->BAddress,
                            HDMA_ModeByteCounts[p->TransferMode]);
''')
    # The frame boundary comes from the core even if retro_run returns in different places.
    insert(root, 'dma.cpp', 'static YonakiBeam yonaki_beam()', before='void yonaki_dma_vblank() { yonaki_vblank(); }\n\n')
    insert(root, 'cpuexec.cpp', '#include "dma.h"\n', after='\nvoid yonaki_dma_vblank();\n')
    insert(root, 'cpuexec.cpp', 'VBlank starts from V=225(240).\n\t\t\t{\n',
           after='                yonaki_dma_vblank();\n')
    return root / 'libretro', ['platform=' + ('osx' if DARWIN else 'unix'),
                              *(['OSX_GT_MOJAVE=YES'] if DARWIN else [])]


def bsnes(root):
    cpu = 'bsnes/sfc/cpu/'
    insert(root, 'bsnes/sfc/ppu/ppu.hpp', '  //ppu.cpp\n  PPU();',
           before='  auto yonakiForcedBlank() const -> bool { return bool(io.displayDisable); }\n\n')
    insert(root, cpu + 'cpu.cpp', '#include <sfc/sfc.hpp>\n', after='''
#include "../../../transfer_probe.h"

extern "C" __attribute__((visibility("default")))
const uint8_t* yonaki_probe_wram() { return SuperFamicom::cpu.wram; }

static YonakiBeam yonaki_beam() {
    using namespace SuperFamicom;
    // HBlank boundary from the CPU's $4212 read in io.cpp.
    return {cpu.vcounter(), cpu.hcounter(), cpu.hperiod(), ppu.vdisp(),
            1096, yonaki_frame, ppu.yonakiForcedBlank()};
}
''')
    insert(root, cpu + 'dma.cpp', 'auto CPU::Channel::dmaRun() -> void {\n  if(!dmaEnable) return;\n',
           after='''
  bool yonaki_ppu = direction == 0 && targetAddress <= 0x3f;
  unsigned yonaki_bytes = transferSize ? unsigned(transferSize) : 0x10000;
  auto yonaki_start = yonaki_beam();
''')
    insert(root, cpu + 'dma.cpp', '  } while(dmaEnable && --transferSize);\n',
           after='''
  if (yonaki_ppu) {
    if (dmaEnable) yonaki_mdma(yonaki_start, yonaki_beam(), yonaki_bytes);
    else yonaki_violation("Interrupted PPU DMA", yonaki_start, yonaki_beam());
  }
''')
    insert(root, cpu + 'dma.cpp', '  static const uint lengths[8]', before='  auto yonaki_start = yonaki_beam();\n')
    insert(root, cpu + 'dma.cpp', '}\n\nauto CPU::Channel::hdmaAdvance()',
           before='''
  yonaki_hdma(yonaki_start, yonaki_beam(), this - cpu.channels,
              direction || transferMode != 2 ? 0xff : unsigned(targetAddress), lengths[transferMode]);
''')
    insert(root, cpu + 'timing.cpp', '  if(vcounter() == ppu.vdisp()) {\n', after='    yonaki_vblank();\n')
    flags = ['GIT_VERSION=', 'NEW_GCC_WARNING_FLAGS=-Wno-invalid-specialization -Wno-unqualified-std-cast-call']
    if DARWIN:
        flags += ['platform=osx', 'arch=' + platform.machine(), 'CC=clang', 'CXX=clang++',
                  'fpic=-fPIC -mmacosx-version-min=11.0']
    return root, flags


def build(name, out):
    dep = json.loads((ROOT / 'tools/dependencies.json').read_text())[name]
    source = VENDOR / dep['directory']
    # Cache only complete builds, and key the copy by the pinned source and the probe code.
    key = hashlib.sha256(HEADER.read_bytes() + Path(__file__).read_bytes() + dep['sha256'].encode()).hexdigest()
    work = out / f'{name}-{key[:12]}'
    library_dir = work / 'libretro' if name == 'snes9x' else work
    core = library_dir / f'{name}_libretro.{EXT}'
    stamp = work / 'probe-built'
    if not stamp.exists() or not core.is_file():
        if work.exists():
            shutil.rmtree(work)
        shutil.copytree(source, work, ignore=shutil.ignore_patterns('*.o', '*.d', '*.dylib', '*.so'))
        shutil.copyfile(HEADER, work / HEADER.name)
        cwd, flags = (snes9x if name == 'snes9x' else bsnes)(work)
        log = out / f'{name}-build.log'
        print(f'Building {name} transfer probe ({log.relative_to(ROOT)})', flush=True)
        with log.open('w') as output:
            result = subprocess.run(['make', f'-j{min(4, os.cpu_count() or 1)}', *flags], cwd=cwd,
                                    stdout=output, stderr=subprocess.STDOUT)
        if result.returncode or not core.is_file():
            raise RuntimeError(f'{name} transfer probe build failed. See {log}')
        stamp.touch()
    return core


class Transfers(ctypes.Structure):
    _fields_ = [(field, ctypes.c_uint32) for field in (
        'forced_dma_bytes', 'forced_dma_max_transfer', 'visible_dma_bytes', 'visible_dma_peak',
        'visible_dma_peak_end', 'visible_dma_latest', 'hdma_bytes', 'hdma_peak', 'hdma_first',
        'hdma_last', 'violations')]

    @classmethod
    def read(cls, lib):
        lib.yonaki_transfer_probe.restype = ctypes.POINTER(cls)
        probe = lib.yonaki_transfer_probe().contents
        report = {field: getattr(probe, field) for field, _ in cls._fields_}
        for field in ('visible_dma_peak_end', 'visible_dma_latest'):
            report[field] = list(divmod(report[field], 0x10000))
        return report
