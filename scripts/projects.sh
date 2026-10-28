#!/usr/bin/env bash
# Renders the projects' onboarding objects (projects/chart, from projects/projects.yaml) on the node and diffs or
# applies them there with the admin kubeconfig, using `kubectl apply` as when they were first created.
#   scripts/projects.sh diff                # read-only: what would change, for every project
#   scripts/projects.sh diff <project>      # read-only, one project
#   scripts/projects.sh apply <project>     # CHANGES THE CLUSTER (ask first): creates or updates that project's objects
# It never deletes anything: removing a project from the list leaves its objects in place (offboarding is
# scripts/offboard-project.sh, docs/onboarding.md).
# PROJECTS_FILE overrides the project list, e.g. for a throw-away test project. NODE_SSH_HOST as in helmfile.sh.
set -euo pipefail
cd "$(dirname "$0")/.."
host="${NODE_SSH_HOST:-computa}"
file="${PROJECTS_FILE:-projects/projects.yaml}"
action="${1:-}" only="${2:-}"
case "$action" in
  diff) ;;
  apply) [ -n "$only" ] || { echo "apply needs a project name: scripts/projects.sh apply <project>" >&2; exit 2; } ;;
  *) echo "usage: scripts/projects.sh diff [project] | apply <project>" >&2; exit 2 ;;
esac
[ -f "$file" ] || { echo "no project list at $file" >&2; exit 2; }
case "$only" in
  '' | [a-z0-9]*) ;;
  *) echo "invalid project name: $only" >&2; exit 2 ;;
esac

# The chart and the list go to a temporary directory on the node, as in scripts/helmfile.sh.
dir=$(tar -cf - projects/chart -C "$(dirname "$file")" "$(basename "$file")" \
  | ssh "$host" 'd=$(mktemp -d) && tar -xf - -C "$d" && echo "$d"')
case "$dir" in
  /tmp/tmp.*) ;;
  *) echo "unexpected temporary directory on the node: '$dir'" >&2; exit 1 ;;
esac
trap 'ssh "$host" "rm -rf $dir"' EXIT

# ssh joins its arguments into one command line, so quote them (an empty project name must survive).
# shellcheck disable=SC2029
ssh "$host" "bash -s -- $(printf '%q ' "$dir" "$action" "$only" "$(basename "$file")")" <<'EOF'
set -euo pipefail
dir=$1 action=$2 only=$3 list=$4
cd "$dir"
export KUBECONFIG=~/.kube/config
render() { helm template onboarding projects/chart -f "$list" --set-string only="$1"; }

if [ "$action" = apply ]; then
  render "$only" | kubectl apply -f -
  exit
fi

# Diff one project at a time: `kubectl diff` fails for objects in a namespace that does not exist yet, so for a
# project that is not onboarded yet, list what `apply` would create instead.
for ns in $(render "$only" | awk '/^kind: Namespace$/ {f=1} f && /^  name:/ {print $2; f=0}'); do
  echo "== $ns"
  if ! kubectl get namespace "$ns" >/dev/null 2>&1; then
    echo "not onboarded yet; apply would create:"
    render "$ns" | kubectl apply --dry-run=client -f - | sed 's/^/  /'
    continue
  fi
  rc=0
  render "$ns" | kubectl diff -f - || rc=$?
  case $rc in
    0) echo "no changes" ;;
    1) echo "(differences above)" ;;      # kubectl diff exits 1 when something would change
    *) exit "$rc" ;;
  esac
done
EOF
