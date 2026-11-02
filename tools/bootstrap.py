"""Fetch the hash-pinned build and test tools into tools/vendor/, never into system directories.

  python3 tools/bootstrap.py                  cc65 (assembler, linker) and Pillow / numpy (夜鳴き鐘's picture tools)
  python3 tools/bootstrap.py --with-emulator  also the Snes9x 1.63 and bsnes 115 libretro cores for make *-test
"""
import argparse,hashlib,json,os,pathlib,platform,shutil,subprocess,sys,tarfile,tempfile,urllib.request
ROOT=pathlib.Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--with-emulator',action='store_true');args=p.parse_args()
deps=json.loads((ROOT/'tools/dependencies.json').read_text());vendor=ROOT/'tools/vendor';vendor.mkdir(parents=True,exist_ok=True)
jobs=str(min(4,os.cpu_count() or 1));darwin=platform.system()=='Darwin'

def fetch(d):
    target=vendor/d['directory']
    if target.exists():return target
    print('Downloading',d['url'],flush=True)
    with urllib.request.urlopen(d['url'],timeout=120) as response:content=response.read()
    assert hashlib.sha256(content).hexdigest()==d['sha256'],'Dependency SHA-256 mismatch'
    with tempfile.NamedTemporaryFile(suffix='.tar.gz') as f, tempfile.TemporaryDirectory(dir=vendor) as tmp:
        f.write(content);f.flush()
        with tarfile.open(f.name) as archive:
            # Reject path traversal, links and device files before extracting.
            for entry in archive.getmembers():
                dest=(pathlib.Path(tmp)/entry.name).resolve()
                assert dest.is_relative_to(pathlib.Path(tmp).resolve()) and not entry.issym() and not entry.islnk() and (entry.isdir() or entry.isfile())
            archive.extractall(tmp)
        shutil.move(str(pathlib.Path(tmp)/d.get('strip',d['directory'])),target)
    return target

target=fetch(deps['cc65'])
if not (target/'bin/ld65').exists():subprocess.run(['make','-C',str(target),'-j'+jobs,'ca65','ld65'],check=True)

pylib=vendor/deps['pylib']['directory']
if not pylib.exists():
    subprocess.run([sys.executable,'-m','pip','install','--disable-pip-version-check','--target',str(pylib)]+deps['pylib']['packages'],check=True)

if args.with_emulator:
    ext='dylib' if darwin else 'so'
    target=fetch(deps['snes9x'])
    if not (target/f'libretro/snes9x_libretro.{ext}').exists():
        # Avoid the upstream historical macOS 10.1 deployment flag on Apple Silicon.
        cmd=['make','-C',str(target/'libretro'),'-j'+jobs,'platform='+('osx' if darwin else 'unix')]
        if darwin:cmd+=['OSX_GT_MOJAVE=YES']
        subprocess.run(cmd,check=True)
    target=fetch(deps['bsnes'])
    if not (target/f'bsnes_libretro.{ext}').exists():
        # Unmodified source; newer Clang rejects old nall int128 trait specializations, so those diagnostics are
        # silenced on the command line only.
        cmd=['make','-C',str(target),'-j'+jobs,'GIT_VERSION=',
             'NEW_GCC_WARNING_FLAGS=-Wno-invalid-specialization -Wno-unqualified-std-cast-call']
        if darwin:cmd+=['platform=osx','arch='+platform.machine(),'CC=clang','CXX=clang++','fpic=-fPIC -mmacosx-version-min=11.0']
        subprocess.run(cmd,check=True)
print('Ready. Run make, or make test after --with-emulator.')
