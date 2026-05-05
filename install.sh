#!/usr/bin/env bash
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$DIR/.venv"

echo "tinytalk installer"
echo

OS="$(uname -s)"
ARCH="$(uname -m)"

if [[ "$OS" == "Darwin" && "$ARCH" != "arm64" ]]; then
    echo "tinytalk requires Apple Silicon on macOS (MLX is arm64-only)."
    exit 1
fi

echo "creating venv..."
python3 -m venv "$VENV"
PIP="$VENV/bin/pip"
PYTHON="$VENV/bin/python"
"$PIP" install --upgrade pip -q
echo

if [[ "$OS" == "Darwin" ]]; then
    echo "macOS (Apple Silicon) — installing mlx-whisper"
    "$PIP" install mlx-whisper numpy sounddevice scipy -q
elif [[ "$OS" == "Linux" ]]; then
    echo "Linux — installing faster-whisper"
    if ! ldconfig -p 2>/dev/null | grep -q libportaudio; then
        echo "  note: if this fails, install PortAudio first:"
        echo "    sudo apt install portaudio19-dev   # Debian/Ubuntu"
        echo "    sudo dnf install portaudio-devel   # Fedora"
        echo
    fi
    "$PIP" install faster-whisper numpy sounddevice scipy -q
else
    echo "Unknown OS: $OS"
    exit 1
fi

echo
echo "installing tiny model (default)..."
if [[ "$OS" == "Darwin" ]]; then
    "$VENV/bin/hf" download mlx-community/whisper-tiny --quiet
else
    "$VENV/bin/hf" download Systran/faster-whisper-tiny --quiet
fi
echo "done."

echo
if [[ "$OS" == "Darwin" ]]; then
    echo "optional models (mlx-community):"
    echo "  base   ~290MB   hf download mlx-community/whisper-base"
    echo "  small  ~970MB   hf download mlx-community/whisper-small"
    echo "  medium ~3GB     hf download mlx-community/whisper-medium"
    echo "  turbo  ~1.6GB   hf download mlx-community/whisper-large-v3-turbo"
    echo
    echo "  browse all: https://huggingface.co/mlx-community"
else
    echo "optional models (faster-whisper):"
    echo "  base   ~290MB   hf download Systran/faster-whisper-base"
    echo "  small  ~970MB   hf download Systran/faster-whisper-small"
    echo "  medium ~3GB     hf download Systran/faster-whisper-medium"
    echo "  large  ~6GB     hf download Systran/faster-whisper-large-v3"
    echo
    echo "  browse all: https://huggingface.co/Systran"
fi
echo "  have a HuggingFace token? set it first for faster downloads:"
echo "    hf login"

echo
echo "run: $PYTHON tinytalk.py"
