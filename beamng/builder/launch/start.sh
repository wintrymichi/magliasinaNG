#!/usr/bin/env bash
# Switzerland Builder for Linux and macOS: on the first start it sets up its own Python with micromamba (conda-forge)
# in beamng/builder/.runtime, then runs the app and opens it in the browser. Nothing has to be installed beforehand.
#
#   start.sh                      the app (http://127.0.0.1:8765)
#   start.sh --no-browser         the app without opening the browser
#   start.sh cli <command> ...    the command line (python -m app.cli: check, build, resume)
#   SWISSBUILDER_RUNTIME=<dir>    keeps micromamba, the Python environment and the settings there
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILDER="$(dirname "$HERE")"
RUNTIME="${SWISSBUILDER_RUNTIME:-$BUILDER/.runtime}"
case "$RUNTIME" in
  *[![:print:]]*|*" "*) RUNTIME="$HOME/.swissbuilder/runtime" ;;      # conda packages break on spaces in paths
esac
export SWISSBUILDER_RUNTIME="$RUNTIME"
export MAMBA_ROOT_PREFIX="$RUNTIME/mamba"
export PIP_ROOT_USER_ACTION=ignore PIP_DISABLE_PIP_VERSION_CHECK=1
MM="$RUNTIME/bin/micromamba"
ENVP="$RUNTIME/env"
YML="$BUILDER/environment.yml"
MM_PINNED="2.10.0-0"                       # the conda-forge build of micromamba taken when the two first sources fail
mkdir -p "$RUNTIME/bin"

say() { printf '\n  %s\n' "$*"; }
fail() { printf '\n  ERROR: %s\n\n' "$*" >&2; exit 1; }

fetch() {   # url destination
  if command -v curl >/dev/null 2>&1; then
    curl -fsSL --retry 4 --retry-delay 3 --connect-timeout 20 -o "$2" "$1"
  elif command -v wget >/dev/null 2>&1; then
    wget -q -t 4 -O "$2" "$1"
  else
    fail "neither curl nor wget is installed: install one of them and start again."
  fi
}

platform() {
  local os arch
  case "$(uname -s)" in
    Linux) os=linux ;;
    Darwin) os=osx ;;
    *) fail "this launcher is for Linux and macOS (on Windows start 'Start Switzerland Builder.bat')." ;;
  esac
  case "$(uname -m)" in
    x86_64|amd64) arch=64 ;;
    aarch64|arm64) if [ "$os" = osx ]; then arch=arm64; else arch=aarch64; fi ;;
    *) fail "unsupported processor $(uname -m)." ;;
  esac
  echo "$os-$arch"
}

if [ ! -x "$MM" ]; then
  P="$(platform)"
  say "Downloading micromamba ($P), the installer of the app's Python..."
  rm -f "$MM.part"
  if ! fetch "https://github.com/mamba-org/micromamba-releases/releases/latest/download/micromamba-$P" "$MM.part"; then
    T="$RUNTIME/mm_unpack"
    rm -rf "$T" && mkdir -p "$T"
    if fetch "https://micro.mamba.pm/api/micromamba/$P/latest" "$T/mm.tar.bz2" ||
       fetch "https://conda.anaconda.org/conda-forge/$P/micromamba-$MM_PINNED.tar.bz2" "$T/mm.tar.bz2"; then
      tar -xjf "$T/mm.tar.bz2" -C "$T" bin/micromamba && mv "$T/bin/micromamba" "$MM.part"
    fi
    rm -rf "$T"
  fi
  [ -s "$MM.part" ] || fail "micromamba could not be downloaded: check the internet connection and start again."
  chmod +x "$MM.part" && mv "$MM.part" "$MM"
fi

HASH="$( (sha256sum "$YML" 2>/dev/null || shasum -a 256 "$YML") | cut -d' ' -f1)"
if [ ! -f "$ENVP/.swissbuilder-env" ] || [ "$(cat "$ENVP/.swissbuilder-env")" != "$HASH" ]; then
  say "Setting up Python and the map libraries (first start only: 5-10 minutes, about 2 GB)..."
  rm -rf "$ENVP"
  "$MM" create -y -q -p "$ENVP" -f "$YML" || fail "the Python environment could not be made (see the messages above). Start again: it goes on where it stopped."
  echo "$HASH" > "$ENVP/.swissbuilder-env"
  "$MM" clean -y -q --tarballs >/dev/null 2>&1 || true
fi

cd "$BUILDER"
if [ "${1:-}" = "cli" ]; then
  shift
  exec "$MM" run -p "$ENVP" python -m app.cli "$@"
fi
exec "$MM" run -p "$ENVP" python -m app.server "$@"
