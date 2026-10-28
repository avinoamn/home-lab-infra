#!/usr/bin/env bash
# Runs every check CI runs: yamllint, shellcheck, and the scan for private values.
# Reads the files to check from stdin as a NUL-separated list (from `git ls-files`), so git-ignored
# files such as CLAUDE.local.md are never read. Run it with `make check`, which uses the pinned tools image.
set -euo pipefail
cd "$(dirname "$0")/.."

files=() yaml=() shell=()
while IFS= read -r -d '' f; do
  [ -f "$f" ] || continue           # listed by git but deleted in the working tree
  files+=("$f")
  case "$f" in
    *.yml | *.yaml) yaml+=("$f") ;;
    *.sh) shell+=("$f") ;;
  esac
done

status=0
run() {
  echo "==> $1"
  shift
  "$@" || status=1
}

[ ${#yaml[@]} -eq 0 ] || run "yamllint (${#yaml[@]} files)" yamllint --strict "${yaml[@]}"
[ ${#shell[@]} -eq 0 ] || run "shellcheck (${#shell[@]} files)" shellcheck "${shell[@]}"
run "private values (${#files[@]} files)" bash scripts/check-private.sh "${files[@]}"

if [ -f helmfile.yaml.gotmpl ]; then
  # Downloads the pinned charts, so it needs network access. CRDs are left out of the render (--include-crds is off);
  # objects of CRD kinds (ServiceMonitor, Prometheus...) have no schema in kubeconform and are skipped.
  run "helmfile lint" helmfile lint --quiet
  run "helmfile template | kubeconform" bash -c \
    'set -o pipefail; helmfile template --quiet | kubeconform -strict -ignore-missing-schemas -summary'
fi

[ "$status" -eq 0 ] && echo "all checks passed" || echo "some checks failed"
exit "$status"
