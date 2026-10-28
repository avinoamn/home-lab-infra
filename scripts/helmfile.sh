#!/usr/bin/env bash
# Runs Helmfile on the node over SSH, with the admin kubeconfig there (the admin credential never leaves the node,
# docs/decisions.md). Copies the files Helmfile reads into a temporary directory on the node, runs Helmfile in it and
# removes it afterwards. Helm's repository list and cache also live in that directory, so the node's own Helm setup
# is left as it is.
#   scripts/helmfile.sh diff               # read-only: what would change
#   scripts/helmfile.sh -l name=kps diff   # one release
#   scripts/helmfile.sh apply              # CHANGES THE CLUSTER: applies the releases whose diff is not empty
# Needs helmfile and the helm-diff plugin on the node (docs/operations.md, "Tools on the node").
# The SSH host alias defaults to `computa`; override with NODE_SSH_HOST.
set -euo pipefail
cd "$(dirname "$0")/.."
host="${NODE_SSH_HOST:-computa}"
args=$(printf '%q ' "$@")

dir=$(tar -cf - helmfile.yaml.gotmpl platform projects | ssh "$host" 'd=$(mktemp -d) && tar -xf - -C "$d" && echo "$d"')
case "$dir" in
  /tmp/tmp.*) ;;
  *) echo "unexpected temporary directory on the node: '$dir'" >&2; exit 1 ;;
esac
trap 'ssh "$host" "rm -rf $dir"' EXIT

# $dir and $args expand here on purpose: $dir is the path on the node (checked above), $args is quoted with %q.
# shellcheck disable=SC2029
ssh "$host" "cd $dir && KUBECONFIG=~/.kube/config HELM_REPOSITORY_CONFIG=$dir/.helm/repositories.yaml \
  HELM_REPOSITORY_CACHE=$dir/.helm/cache ~/.local/bin/helmfile $args"
