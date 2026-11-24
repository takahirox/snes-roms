#!/bin/sh
set -eu
cd "$(dirname "$0")/.."

# If PATH selects a compiler without WASM, use the configured Rustup toolchain
# when it already has the target installed.
studio_target_libdir=$(rustc --print target-libdir --target wasm32-unknown-unknown)
if [ ! -d "$studio_target_libdir" ] && command -v rustup >/dev/null 2>&1; then
    studio_rustc=$(rustup which rustc)
    PATH="$(dirname "$studio_rustc"):$PATH"
    export PATH
fi

mkdir -p _site/pkg _site/demo
wasm-pack build web --target web --release --out-dir ../_site/pkg --no-pack -- --locked
cp web/static/* _site/
cp fixtures/demo/studio.json _site/demo/studio.json
touch _site/.nojekyll
