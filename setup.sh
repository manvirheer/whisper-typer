#!/bin/bash
set -e

WHISPER_DIR="${WHISPER_CPP_DIR:-$HOME/.local/share/whisper.cpp}"
MODEL="${WHISPER_MODEL_NAME:-large-v3-turbo}"

echo "whisper.cpp → $WHISPER_DIR"
echo "model → $MODEL"

if [ ! -d "$WHISPER_DIR" ]; then
    git clone https://github.com/ggerganov/whisper.cpp.git "$WHISPER_DIR"
fi

cd "$WHISPER_DIR"

if [[ "$(uname)" == "Darwin" ]]; then
    echo "building with metal + coreml + flash attention..."
    cmake -B build \
        -DGGML_METAL=ON \
        -DGGML_METAL_EMBED_LIBRARY=ON \
        -DWHISPER_COREML=ON \
        -DGGML_FLASH_ATTN=ON
    cmake --build build --config Release -j$(sysctl -n hw.ncpu)
else
    echo "building with flash attention..."
    cmake -B build -DGGML_FLASH_ATTN=ON
    cmake --build build --config Release -j$(nproc)
fi

if [ ! -f "models/ggml-${MODEL}.bin" ]; then
    echo "downloading $MODEL..."
    ./models/download-ggml-model.sh "$MODEL"
fi

# coreml converts the encoder to run on apple's neural engine
# takes 10-60 min first time, but inference is faster after
if [[ "$(uname)" == "Darwin" ]] && [ ! -d "models/ggml-${MODEL}-encoder.mlmodelc" ]; then
    echo ""
    read -p "generate coreml model for neural engine? [Y/n] " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Nn]$ ]]; then
        pip3 install ane_transformers openai-whisper coremltools 'numpy<2' 2>/dev/null || \
        pip3 install --break-system-packages ane_transformers openai-whisper coremltools 'numpy<2'
        ./models/generate-coreml-model.sh "$MODEL"
    fi
fi

echo ""
echo "done. run: wv"
