#!/bin/bash
# Startup script for Ollama - loads required models on startup

MODEL_NAME="${CUSTOM_MODEL_NAME:-qwen2.5:1.5b}"

echo "Starting Ollama service..."

# Pull the model if it doesn't exist
echo "Checking if $MODEL_NAME exists..."
if ! ollama list -q | grep -q "^${MODEL_NAME}$"; then
    echo "Pulling $MODEL_NAME..."
    ollama pull "$MODEL_NAME"
fi

# Verify the model is loaded
echo "Verifying model readiness..."
ollama show $MODEL_NAME > /dev/null 2>&1

if [ $? -eq 0 ]; then
    echo "✓ Ollama service ready with model: $MODEL_NAME"
    # Keep Ollama running in the background
    while true; do
        sleep 3600
    done
else
    echo "✗ Failed to load model. Please check Ollama logs."
    exit 1
fi
