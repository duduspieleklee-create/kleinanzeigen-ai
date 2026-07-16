#!/bin/bash
# Startup script for Ollama — starts server, loads model, stays running.

MODEL_NAME="${CUSTOM_MODEL_NAME:-qwen2.5:1.5b}"

echo "Starting Ollama server..."
ollama serve &
sleep 3  # let the server bind port 11434

echo "Checking if $MODEL_NAME exists..."
if ! ollama list | grep -q "$MODEL_NAME"; then
    echo "Pulling $MODEL_NAME..."
    ollama pull "$MODEL_NAME"
fi

echo "Verifying model..."
ollama show "$MODEL_NAME" > /dev/null 2>&1 || {
    echo "✗ Failed to load model"
    exit 1
}

echo "✓ Ollama ready with model: $MODEL_NAME"
wait  # keep container alive (wait for ollama serve)
