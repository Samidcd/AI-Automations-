#!/bin/bash
DIR="$(cd "$(dirname "$0")" && pwd)"
"$DIR/venv/bin/streamlit" run "$DIR/app.py" --server.port 8502
