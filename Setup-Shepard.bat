@echo off
setlocal
cd /d "%~dp0"

where ollama >nul 2>nul
if errorlevel 1 (
  echo Ollama is not installed. Download it from https://ollama.com/download, then run this setup again.
  pause
  exit /b 1
)

where python >nul 2>nul
if errorlevel 1 (
  echo Python 3.11 or newer is required. Install Python, then run this setup again.
  pause
  exit /b 1
)

echo Preparing Shepard's local model...
ollama pull qwen3:8b
if errorlevel 1 exit /b 1
ollama create shepard -f "%~dp0Modelfile.shepard"
if errorlevel 1 exit /b 1

echo Preparing the Labyrinth...
python -m shepard init
if errorlevel 1 exit /b 1

echo Shepard is ready. Opening her home...
start "Shepard" http://127.0.0.1:8765/
python -m shepard web --no-open
