#!/bin/bash
set -eu
site=$(cd "$(dirname "$0")/.." && pwd)
py=/runtime/TacHarness/.venv/bin/python
while test -e /proc/695240/exe; do sleep 5; done
for spec in 'stove-origin --bowl-x 0 --target-y 0 --yaw 0' 'stove-east --bowl-x 3 --target-y -3 --yaw 15' 'stove-west --bowl-x -3 --target-y 3 --yaw -15' 'drawer-east --task drawer --bowl-x 3 --target-y 0 --yaw 15'; do
  "$py" "$site/review/tabero.py" $spec || echo "failed: $spec"
done
