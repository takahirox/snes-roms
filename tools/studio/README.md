# SFC Studio

SFC Studio is a static browser workbench and native CLI for Super Famicom asset authoring. Both use `studio-core` for the project model, edits, diagnostics, rendering and binary formats. A game can consume Studio assets from its own build tools and choose its own map schema, ROM layout, graphics allocation, compression and sound driver.

## GitHub Pages

GitHub Pages is configured to publish Studio at [https://takahirox.github.io/snes-roms/](https://takahirox.github.io/snes-roms/). The browser workbench and its original Chromatic Lab demo become available after the first successful deployment from `main`.

The [Pages workflow](../../.github/workflows/studio-pages.yml) runs on changes to Studio or the workflow on `main`. It uses pinned Rust, wasm-pack and Binaryen releases and the Cargo lockfile. It runs `check.sh`, which builds the site with `web/build.sh` and verifies native/WASM parity. The upload contains the browser files from `_site/` and the bundled demo. Asset URLs are relative to the repository's Pages path.

Under **Settings → Pages**, the publishing source is **GitHub Actions**. To redeploy, select **Deploy SFC Studio to GitHub Pages** under **Actions**, then choose **Run workflow** on `main`. The CLI can dispatch the same workflow.

```sh
gh workflow run studio-pages.yml --repo takahirox/snes-roms --ref main
```

The workflow publishes the deployment URL to the `github-pages` environment. In each run, the `smoke` job fetches the deployed files over HTTPS, verifies their MIME types and SHA-256 checksums, and runs headless Chromium to load Chromatic Lab, paint a pixel and check the exported JSON. [View workflow runs](https://github.com/takahirox/snes-roms/actions/workflows/studio-pages.yml).

### Initial verification

On 2026-11-25, GitHub's Pages API reported the configured URL and HTTPS enforcement. The public endpoint returned HTTP 404 before the first deployment. The Studio checks, browser/CLI regressions and Pages smoke test passed locally. The smoke test used the exact upload allowlist and verified the artifact under a local `/snes-roms/` URL. The first workflow run on `main` will record the public deployment and HTTPS smoke results.

To run the smoke test against an already served site, install the locked browser test dependencies and pass its URL. For a local server, substitute the loopback URL from the next section.

```sh
cd tools/studio/web/tests
npm ci --ignore-scripts
npx --no-install playwright install --only-shell chromium
node pages-smoke.mjs https://takahirox.github.io/snes-roms/
```

## Run locally

From `tools/studio`, build the CLI with a recent stable Rust toolchain.

```sh
cargo build --locked -p sfc-studio
target/debug/sfc-studio --help
target/debug/sfc-studio validate fixtures/demo
```

For the workbench, install the Rust `wasm32-unknown-unknown` target and [wasm-pack](https://drager.github.io/wasm-pack/installer/). Build and serve the static output over HTTP.

```sh
rustup target add wasm32-unknown-unknown
./web/build.sh
python3 -m http.server 8000 --bind 127.0.0.1 --directory _site
```

Open [the local Studio](http://127.0.0.1:8000). Publish the contents of `_site/` to any static host that serves WebAssembly, including GitHub Pages under a repository subpath. The build emits relative URLs and a `.nojekyll` marker. All opened assets stay in the browser. The host serves the application and bundled demo.

Open a project by choosing `studio.json` or a ZIP. Browsers with File System Access on HTTPS or localhost can open and save a folder directly. The Save / export dialog offers a new folder, JSON download and ZIP download. See [format v1](FORMAT.md) for supported files and limits.

## Edit and inspect

| Asset | Browser workflow | CLI output |
| --- | --- | --- |
| Subpalette | Add BGR555 entries, edit RGB values, mark a transparent index and look up the nearest indexed color | RGBA PNG, little-endian BGR555 |
| Tile | Paint an 8×8 tile with a subpalette and inspect 2, 4 and 8bpp index limits | RGBA PNG, indexed PNG, planar CHR |
| Metatile and tileset | Compose a grid of tiles with palette overrides and flips. Organize member IDs and CHR order in a tileset | RGBA PNG, tileset CHR |
| Map | Paint, erase or flood-fill on the active layer. Select a rectangle and copy or paste it. Edit JSON metadata on a map, layer or brush | RGBA PNG, selection JSON |
| Sprite and animation | Compose OBJs for a hardware size mode, set OAM order and frame timing, and play the animation | RGBA PNG per frame, OAM, OBJ CHR and OBJ CGRAM |
| Bitmap font | Map Unicode characters to tile artwork, draw glyphs in the tile editor and preview text or the atlas | RGBA PNG |
| Sample | Open WAV or BRR, view a waveform, trim, set a sample rate or loop start and audition the result | RGBA PNG, WAV, BRR |
| Music and sound effects | Edit tempo, track voices and timed notes. Audition square, triangle and pitched sample voices | RGBA waveform PNG, mono WAV |
| VRAM layout | Place and inspect named byte ranges across 64 KiB of VRAM | RGBA PNG and validation diagnostics |

The Tools menu also imports indexed or true-color PNGs as tiles, inspects ROM headers read-only, and applies or reverses Studio RLE. The pixel, metatile and map canvases accept mouse or touch input. Arrow keys move the cursor, Enter applies the brush, and Shift+arrow extends a map selection in Select mode. Undo and redo cover the last 32 edit transactions.

## Hand off the same project

Run these commands from `tools/studio`. An automated editor can test a proposed change and write a separate handoff artifact.

```sh
target/debug/sfc-studio edit fixtures/demo fixtures/paint.json --dry-run
target/debug/sfc-studio edit fixtures/demo fixtures/paint.json --output /tmp/studio-handoff.zip
target/debug/sfc-studio render /tmp/studio-handoff.zip chromatic-lab /tmp/studio-before.png
```

A human opens `studio-handoff.zip` in Studio, selects `chromatic-lab` and paints on the `signals` layer. They download a project ZIP through Save / export. Substitute the downloaded path below to review, validate and render the result.

```sh
target/debug/sfc-studio diff /tmp/studio-handoff.zip /path/to/studio-project.zip
target/debug/sfc-studio validate /path/to/studio-project.zip
target/debug/sfc-studio render /path/to/studio-project.zip chromatic-lab /tmp/studio-after.png
```

For a shared project folder, the CLI prints the input SHA-256 as `revision` in `validate`. An in-place edit requires that exact fingerprint through `edit --expect SHA256`. A browser folder save uses the fingerprint from when the project was opened or last saved. Both writers hold a temporary `studio.json.save-*.lock` marker while verifying the fingerprint and committing. An overlapping writer that finds a marker reports a conflict. Review the current manifest or export a separate copy before retrying. If an interrupted save leaves a marker behind, remove it after confirming that the writer has stopped. Use updated Studio clients for this protection. Other editors can still change the manifest concurrently. Output paths in the CLI fail if they already exist.

CLI reports are JSON. Successful write commands for binary files are quiet. `validate` writes diagnostics to stdout for a parsed project, including validation failures. Other failures use stderr. Exit codes are `0` for success, `2` for usage, parse, conversion or validation errors, `3` for I/O errors, and `4` for conflicts. Warnings permit preview and save.

```sh
target/debug/sfc-studio export fixtures/demo compass indexed-png /tmp/compass.png --bpp 4
target/debug/sfc-studio export fixtures/demo signal-light oam /tmp/signal.oam --frame flare
target/debug/sfc-studio export fixtures/demo lab-chime wav /tmp/lab-chime.wav
target/debug/sfc-studio copy fixtures/demo chromatic-lab signals 4 4 2 2
target/debug/sfc-studio rom-header /path/to/image.sfc lo-rom
```

## Development

`core/` exposes the Rust operations. `cli/` handles arguments, file I/O and exit codes. `web/` binds those same operations through `wasm-bindgen`. Its DOM shell handles controls, pointer input, file access and audio playback. The original [Chromatic Lab fixture](fixtures/README.md) exercises each asset type.

Run `./check.sh` with Cargo, Clippy, rustfmt, wasm-pack and Node.js available. It runs native tests, builds the static workbench, and compares its WASM exports, diagnostics, project edits and imports against the production CLI. The test checks byte equality across targets and exercises conflicts between CLI saves and between browser and CLI saves.

An optional MCP adapter could expose the validated operations and JSON diagnostics to clients that require tool discovery. The CLI already supports deterministic editing, review and conflict handling, so an adapter adds another permission and distribution surface without adding authoring capability to this workflow. Studio uses no model API, AI backend or MCP dependency.

See [the v1 format reference](FORMAT.md) and [hardware and workflow research](RESEARCH.md).
