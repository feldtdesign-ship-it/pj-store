#!/bin/sh
# build.sh — full rebuild of the preview: refresh data (optional), render pages, make the link card.
# Needs python-liquid:  python3 -m venv .venv && .venv/bin/pip install python-liquid   (one time, anywhere)
cd "$(dirname "$0")" || exit 1
PY="${PY:-python3}"
[ "$1" = "--fresh" ] && ./fetch_data.sh
"$PY" render.py --mockup && ./make_card.sh
