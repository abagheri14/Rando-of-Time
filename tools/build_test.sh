#!/bin/sh
# Generates a test seed, builds its patch, applies and checks the cosmetics, then reads the patch back.
# Usage: sh tools/build_test.sh OUT_DIR SEED SETTINGS [ROMFS]. Pass "" as SETTINGS for the default settings.
set -u
OUT=$1; SEED=$2; SETTINGS=$3; ROMFS=${4:-E:/LongshotLauncher-data/builds/rc/romfs}
export PYTHONHASHSEED=0 PYTHONIOENCODING=utf-8
mkdir -p "$OUT"
if [ -n "$SETTINGS" ]; then set -- --settings "$SETTINGS"; else set --; fi
python tools/rando/generate.py "$OUT" --seed "$SEED" "$@" > "$OUT/generate.log" 2>&1; echo "generate $?"
python tools/make_patch.py "$ROMFS" "$OUT/patch" "$OUT/plan.json" > "$OUT/patch.log" 2>&1; echo "make_patch $?"
python tools/rando/parity/_cosmetics_apply.py "$ROMFS" "$OUT/patch" "$OUT/plan.json" > "$OUT/cosmetics.log" 2>&1; echo "cosmetics $?"
python tools/rando/parity/_cosmetics_apply.py "$ROMFS" "$OUT/patch" "$OUT/plan.json" --check > "$OUT/cosmetics_check.log" 2>&1; echo "cosmetics check $?"
python tools/rando/in_game_check.py "$OUT" "$ROMFS" > "$OUT/check.log" 2>&1; echo "check $?"
tail -1 "$OUT/check.log"
