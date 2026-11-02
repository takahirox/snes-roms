"""Generate the staged silhouettes of 夜鳴き鐘 with the Codex CLI's built-in image generation.

For every entry of assets/yonaki/stage.json (bg/character/position) that has no picture yet, runs `codex exec`
in a read-only sandbox with the background photo attached; the model edits the photo to hold the person in a
fitting pose, painted flat magenta.  The newest PNG it reports is copied to
assets/yonaki/src/stage/<bg>__<character>__<position>.png and the prompt is recorded in assets/yonaki/ART.json.
tools/yonaki/pictures.py (staged_silhouette) cuts the magenta out as the mask.

usage: python3 -I tools/yonaki/gen_stage.py [--jobs N] [--redo] [keys or key prefixes...]
"""
import sys, json, pathlib, subprocess, shutil, re, time, concurrent.futures as cf, threading

ROOT = pathlib.Path(__file__).resolve().parents[2]
STAGE = ROOT / 'assets/yonaki/stage.json'
ART = ROOT / 'assets/yonaki/ART.json'
SRC = ROOT / 'assets/yonaki/src'
GEN = pathlib.Path.home() / '.codex/generated_images'
LOCK = threading.Lock()


def stage_file(key):
    return SRC / 'stage' / (key.replace('/', '__') + '.png')


def prompts():
    s = json.loads(STAGE.read_text())
    for key, e in s['stage'].items():
        bg, who, pos = key.split('/')
        text = s['_common'].format(who=e.get('who', s['_who'][who]), pose=e['pose'],
                                   where=e.get('where', s['_where'][pos]))
        yield key, bg, text


def generate(key, bg, prompt, redo):
    out = stage_file(key)
    if out.exists() and not redo:
        return key, 'exists'
    src = SRC / 'bg' / f'{bg}.png'
    ask = ('Use your built-in image generation tool to edit the attached image and create exactly one image. '
           f'Do not run any shell commands. {prompt} Reply with the generated image file path only.')
    for attempt in range(3):
        try:
            r = subprocess.run(['codex', 'exec', '--skip-git-repo-check', '--sandbox', 'read-only',
                                f'--image={src}', ask],
                               capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=1800, cwd=str(SRC))
        except subprocess.TimeoutExpired:
            r = subprocess.CompletedProcess([], 1, '', 'timed out after 1800 s')
            continue
        paths = [pathlib.Path(m) for m in re.findall(r'(/\S+?\.png)', r.stdout + r.stderr)]
        paths = [q for q in paths if q.exists() and GEN in q.parents]
        if paths:
            out.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(paths[-1], out)
            with LOCK:
                art = json.loads(ART.read_text()) if ART.exists() else {}
                art[f'stage/{key}'] = dict(prompt=prompt, source=f'assets/yonaki/src/bg/{bg}.png',
                                           generated_path=str(paths[-1]).replace(str(pathlib.Path.home()), '~', 1),
                                           method='Codex CLI built-in image generation, editing the background '
                                                  '(codex exec --image)',
                                           target=str(out.relative_to(ROOT)), date=time.strftime('%Y-%m-%d'))
                ART.write_text(json.dumps(art, ensure_ascii=False, indent=1) + '\n')
            return key, 'ok'
        time.sleep(5)
    return key, 'FAILED: ' + (r.stdout + r.stderr)[-300:]


def main():
    args = sys.argv[1:]
    jobs, redo = 4, False
    while args[:1] and args[0].startswith('--'):
        if args[0] == '--jobs':
            jobs = int(args[1])
            args = args[2:]
        elif args[0] == '--redo':
            redo = True
            args = args[1:]
        else:
            sys.exit(__doc__)
    todo = [p for p in prompts() if not args or any(p[0] == a or p[0].startswith(a) for a in args)]
    with cf.ThreadPoolExecutor(jobs) as ex:
        for key, res in ex.map(lambda t: generate(*t, redo), todo):
            print(key, res, flush=True)


if __name__ == '__main__':
    main()
