#!/bin/sh
set -eu
for crew_script in skills/crew/scripts/*.sh tests/*.sh; do
  sh -n "$crew_script"
done
tests/run.sh
python3 -B -m unittest discover -s tests -p 'test_release.py' -v
python3 -B tools/release/check_version.py
