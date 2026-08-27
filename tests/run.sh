#!/bin/sh

set -u

tests_dir=$(CDPATH= cd -- "$(dirname "$0")" && pwd) || exit 2

case "$#" in
  0)
    scripts_dir=$tests_dir/../skills/crew/scripts
    ;;
  1)
    scripts_dir=$1
    ;;
  *)
    printf '%s\n' 'usage: tests/run.sh [scripts-directory]' >&2
    exit 2
    ;;
esac

scripts_dir=$(CDPATH= cd -- "$scripts_dir" 2>/dev/null && pwd) || {
  printf 'invalid scripts directory: %s\n' "$scripts_dir" >&2
  exit 2
}

status=0
found=no
for case_file in "$tests_dir"/cases/*.json; do
  if [ ! -f "$case_file" ]; then
    continue
  fi
  found=yes
  if ! python3 "$tests_dir/case.py" "$scripts_dir" "$case_file"; then
    status=1
  fi
done

if [ "$found" != yes ]; then
  printf '%s\n' 'no test cases found' >&2
  exit 2
fi

exit "$status"
