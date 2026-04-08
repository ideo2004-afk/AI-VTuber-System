#!/bin/bash

# Get the directory where the script is located
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$DIR"

echo "=== AI-VTuber System Launcher ==="

# Fix Python 3.14 subprocess hash seed validation (prevents config_init_hash_seed errors)
export PYTHONHASHSEED=random

# Suppress duplicate dylib warnings from cv2 vs Homebrew ffmpeg
export OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES

# Check if venv exists
if [ -d "venv" ]; then
    echo "Using virtual environment: ./venv"
    ./venv/bin/python3 AIVT_Core.py
else
    echo "Virtual environment not found. Falling back to system python3..."
    python3 AIVT_Core.py
fi
