#!/usr/bin/env bash
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FORCE=0

for arg in "$@"; do
    [[ "$arg" == "--force" ]] && FORCE=1
done

echo "tinytalk installer"
echo

ARCH="$(uname -m)"
if [[ "$(uname -s)" != "Darwin" || "$ARCH" != "arm64" ]]; then
    echo "tinytalk requires macOS on Apple Silicon."
    exit 1
fi

if ! command -v pipx &>/dev/null; then
    echo "pipx not found. Install it first:"
    echo "  brew install pipx && pipx ensurepath"
    exit 1
fi

if [[ $FORCE -eq 1 ]]; then
    pipx install --force "$DIR"
else
    pipx install "$DIR" 2>/dev/null || {
        read -r -p "tinytalk already installed. reinstall? [y/N] " answer
        [[ "$answer" =~ ^[Yy]$ ]] && pipx install --force "$DIR" || { echo "aborted."; exit 0; }
    }
fi

echo
echo "installing tiny model (default)..."
hf download mlx-community/whisper-tiny --quiet
echo "done."

echo
echo "optional models:"
echo "  base   ~137MB   hf download mlx-community/whisper-base-mlx"
echo "  medium ~1.5GB   hf download mlx-community/whisper-medium-mlx"
echo "  turbo  ~1.5GB   hf download mlx-community/whisper-large-v3-turbo"
echo
echo "  browse all: https://huggingface.co/mlx-community"
echo "  for faster downloads, please log in first: hf auth login"
echo
echo "run: tinytalk"
