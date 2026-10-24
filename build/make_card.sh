#!/bin/sh
# make_card.sh — og.jpg (1200 x 630 link-preview card) from build/card.html, using Chrome with no window.
cd "$(dirname "$0")/.." || exit 1
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless=new --disable-gpu --hide-scrollbars --force-device-scale-factor=1 --window-size=1200,630 --virtual-time-budget=6000 --screenshot="$PWD/build/card.png" "file://$PWD/build/card.html" >/dev/null 2>&1
sips -s format jpeg -s formatOptions 86 build/card.png --out og.jpg >/dev/null && rm build/card.png && ls -la og.jpg
