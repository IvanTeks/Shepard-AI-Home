#!/bin/zsh
set -e

PROJECT_DIR="${0:A:h}"
cd "$PROJECT_DIR"

if ! command -v ollama >/dev/null 2>&1; then
  echo "Ollama is not installed. Download it from https://ollama.com/download, then run this setup again."
  read "?Press Return to close."
  exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3.11 or newer is required. Install Python, then run this setup again."
  read "?Press Return to close."
  exit 1
fi

echo "Preparing Shepard's local model…"
ollama pull qwen3:8b
ollama create shepard -f "$PROJECT_DIR/Modelfile.shepard"

echo "Preparing the Labyrinth…"
python3 -m shepard init

echo "Shepard is ready. Opening her home…"
exec "$PROJECT_DIR/Start Shepard.command"
