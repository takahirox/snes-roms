#!/bin/sh
set -eu
cd "$(dirname "$0")"
cargo fmt --all --check
cargo clippy --locked --workspace --all-targets -- -D warnings
cargo test --locked --workspace
cargo build --locked -p sfc-studio
./web/build.sh
studio_target=${CARGO_TARGET_DIR:-target}
node web/tests/parity.mjs "$studio_target/debug/sfc-studio"
