#!/usr/bin/env bash
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FORCE=0

for arg in "$@"; do
    [[ "$arg" == "--force" ]] && FORCE=1
done

echo "tinytalk installer"
echo

if [[ "$(uname -s)" != "Darwin" || "$(uname -m)" != "arm64" ]]; then
    echo "This installer is for macOS on Apple Silicon."
    echo "Elsewhere: pipx install '$DIR'  (you'll get the faster-whisper backend)"
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

# turbo is what tinytalk selects by default, so it's the one worth having on
# disk before the first run. otherwise the app downloads it mid-recording
echo
read -r -p "download the default model now? turbo, ~1.6GB [Y/n] " grab
if [[ ! "$grab" =~ ^[Nn]$ ]]; then
    hf download mlx-community/whisper-large-v3-turbo --quiet
    echo "done."
else
    echo "skipped - tinytalk will fetch it the first time you record."
fi

echo
echo "other models:"
echo "  tiny    ~75MB   hf download mlx-community/whisper-tiny"
echo "  base   ~145MB   hf download mlx-community/whisper-base-mlx"
echo "  medium  ~1.5GB  hf download mlx-community/whisper-medium-mlx"
echo
echo "  browse all: https://huggingface.co/mlx-community"
echo
echo "run: tinytalk          read them back later: tinytalk log"
