"""Generate the source pictures of 夜鳴き鐘 with the Codex CLI's built-in image generation.

For every entry of assets/yonaki/prompts.json that has no picture yet, runs `codex exec` in a read-only sandbox
(the model only calls its image tool), takes the newest PNG it reports, copies it to assets/yonaki/src/<kind>/<id>.png
and records the prompt and the generated path in assets/yonaki/ART.json.

usage: python3 -I tools/yonaki/gen_art.py [--jobs N] [ids...]
"""
import sys, json, pathlib, subprocess, shutil, re, time, concurrent.futures as cf, threading

ROOT = pathlib.Path(__file__).resolve().parents[2]
PROMPTS = ROOT / 'assets/yonaki/prompts.json'
ART = ROOT / 'assets/yonaki/ART.json'
SRC = ROOT / 'assets/yonaki/src'
GEN = pathlib.Path.home() / '.codex/generated_images'
LOCK = threading.Lock()


def items():
    p = json.loads(PROMPTS.read_text())
    for kind, common in (('bg', p['_common_bg']), ('sil', p['_common_sil'])):
        for k, v in p[kind].items():
            yield kind, k, f'{v} {common}'


def generate(kind, key, prompt):
    out = SRC / kind / f'{key}.png'
    if out.exists():
        return key, 'exists'
    ask = ('Use your built-in image generation tool to create exactly one image. Do not run any shell commands. '
           f'Image description: {prompt} Reply with the generated image file path only.')
    for attempt in range(3):
        try:
            r = subprocess.run(['codex', 'exec', '--skip-git-repo-check', '--sandbox', 'read-only', ask],
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
                art[f'{kind}/{key}'] = dict(prompt=prompt, generated_path=str(paths[-1]).replace(str(pathlib.Path.home()), '~', 1),
                                            method='Codex CLI built-in image generation (codex exec)',
                                            target=str(out.relative_to(ROOT)), date=time.strftime('%Y-%m-%d'))
                ART.write_text(json.dumps(art, ensure_ascii=False, indent=1) + '\n')
            return key, 'ok'
        time.sleep(5)
    return key, 'FAILED: ' + (r.stdout + r.stderr)[-300:]


def main():
    args = sys.argv[1:]
    jobs = 3
    if args[:1] == ['--jobs']:
        jobs = int(args[1])
        args = args[2:]
    todo = [i for i in items() if not args or i[1] in args]
    SRC.mkdir(parents=True, exist_ok=True)
    with cf.ThreadPoolExecutor(jobs) as ex:
        for key, res in ex.map(lambda t: generate(*t), todo):
            print(key, res, flush=True)


if __name__ == '__main__':
    main()
