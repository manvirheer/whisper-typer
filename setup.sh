#!/bin/bash
set -e

# ── Preflight checks ────────────────────────────────────────────────────────

if [[ "$(uname)" != "Darwin" ]]; then
    echo "Error: whisper-typer requires macOS."
    exit 1
fi

if [[ "$(uname -m)" != "arm64" ]]; then
    echo "Error: whisper-typer requires Apple Silicon (M-series chip)."
    exit 1
fi

command -v git >/dev/null 2>&1 || {
    echo "Error: git not found. Install: xcode-select --install"
    exit 1
}

xcode-select -p >/dev/null 2>&1 || {
    echo "Error: Xcode Command Line Tools required. Install: xcode-select --install"
    exit 1
}

command -v cmake >/dev/null 2>&1 || {
    echo "Error: cmake not found. Install: brew install cmake (or https://cmake.org)"
    exit 1
}

command -v python3 >/dev/null 2>&1 || {
    echo "Error: python3 not found."
    exit 1
}

echo "Preflight checks passed."
echo ""

# ── Virtual environment ──────────────────────────────────────────────────────

CREATED_VENV=false

# Find best Python: prefer 3.12/3.13 for coremltools compatibility, fall back to python3
PYTHON=python3
for candidate in python3.12 python3.13; do
    if command -v "$candidate" >/dev/null 2>&1; then
        PYTHON="$candidate"
        break
    fi
done

if [ -z "$VIRTUAL_ENV" ]; then
    echo "Warning: not running in a virtual environment."
    echo "Using: $($PYTHON --version)"
    read -p "Create .venv in project directory? [Y/n] " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Nn]$ ]]; then
        $PYTHON -m venv .venv
        source .venv/bin/activate
        CREATED_VENV=true
        echo "Created and activated .venv"
    else
        echo "Proceeding without venv."
    fi
    echo ""
fi

# ── Install Python dependencies ──────────────────────────────────────────────

echo "Installing whisper-typer and macOS dependencies..."
python3 -m pip install -e ".[macos]"
echo ""

# ── Build whisper.cpp ────────────────────────────────────────────────────────

WHISPER_DIR="${WHISPER_CPP_DIR:-$HOME/.local/share/whisper.cpp}"

echo "whisper.cpp -> $WHISPER_DIR"

if [ ! -d "$WHISPER_DIR" ]; then
    git clone https://github.com/ggerganov/whisper.cpp.git "$WHISPER_DIR"
fi

cd "$WHISPER_DIR"

echo "Building with Metal + CoreML + Flash Attention..."
cmake -B build \
    -DGGML_METAL=ON \
    -DGGML_METAL_EMBED_LIBRARY=ON \
    -DWHISPER_COREML=ON \
    -DGGML_FLASH_ATTN=ON
cmake --build build --config Release -j$(sysctl -n hw.ncpu)
echo ""

# ── Model picker ─────────────────────────────────────────────────────────────

CHIP=$(sysctl -n machdep.cpu.brand_string 2>/dev/null || echo "Apple Silicon")
RAM_BYTES=$(sysctl -n hw.memsize 2>/dev/null || echo 0)
RAM_GB=$((RAM_BYTES / 1073741824))

# Recommendation based on RAM
if [ "$RAM_GB" -ge 24 ]; then
    RECOMMENDED=5
    REC_NAME="large-v3-turbo"
elif [ "$RAM_GB" -ge 16 ]; then
    RECOMMENDED=4
    REC_NAME="medium"
else
    RECOMMENDED=3
    REC_NAME="small"
fi

echo "Detected: $CHIP (${RAM_GB}GB RAM)"
echo ""
echo "Models:"
echo "  1) tiny            75MB   — fastest, lower accuracy"
echo "  2) base           142MB   — fast, decent accuracy"
echo "  3) small          466MB   — good balance"
echo "  4) medium         1.5GB   — high accuracy"
echo "  5) large-v3-turbo 1.5GB   — best accuracy"
echo ""
echo "  ★ Recommended for your device: $REC_NAME"
echo ""
read -p "Pick [1-5] (default: $RECOMMENDED): " MODEL_CHOICE

case "${MODEL_CHOICE:-$RECOMMENDED}" in
    1) MODEL="tiny" ;;
    2) MODEL="base" ;;
    3) MODEL="small" ;;
    4) MODEL="medium" ;;
    5) MODEL="large-v3-turbo" ;;
    *) echo "Invalid choice, using $REC_NAME"; MODEL="$REC_NAME" ;;
esac

if [ ! -f "models/ggml-${MODEL}.bin" ]; then
    echo ""
    echo "Downloading $MODEL model..."
    ./models/download-ggml-model.sh "$MODEL"
fi

# ── CoreML encoder (optional) ───────────────────────────────────────────────

if [ ! -d "models/ggml-${MODEL}-encoder.mlmodelc" ]; then
    echo ""
    echo "CoreML Neural Engine encoder speeds up inference ~2x."
    echo "Generating it takes 10-60 minutes (one-time cost)."
    echo "Requires Python <=3.13 and compatible coremltools."
    read -p "Generate CoreML model? [y/N] " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        if python3 -m pip install ane_transformers openai-whisper coremltools 'numpy<2' && \
           ./models/generate-coreml-model.sh "$MODEL"; then
            echo "CoreML encoder generated successfully."
        else
            echo ""
            echo "CoreML generation failed (likely Python/coremltools version mismatch)."
            echo "This is optional — Metal GPU acceleration is still active."
            echo "The app will work fine without it."
        fi
    fi
fi

# ── Download Silero VAD model ────────────────────────────────────────────────

echo ""
echo "Downloading Silero VAD model..."
python3 -c "from silero_vad import load_silero_vad; load_silero_vad(onnx=True)" 2>/dev/null || true

# ── Done ─────────────────────────────────────────────────────────────────────

cd - >/dev/null

echo ""
echo "════════════════════════════════════════"
echo "  Setup complete!"
echo ""
echo "  Model:  $MODEL (ggml-${MODEL}.bin)"
if [ "$CREATED_VENV" = true ]; then
    echo "  Venv:   .venv (activate with: source .venv/bin/activate)"
fi
echo ""
echo "  Run:    wv"
echo "════════════════════════════════════════"
