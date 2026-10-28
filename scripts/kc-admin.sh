#!/usr/bin/env bash
# ADMIN kubectl: runs on the node over SSH with the cluster-admin kubeconfig there, which never leaves the node.
# Use it for platform work only; projects use their own namespace-scoped `deployer` account.
#   scripts/kc-admin.sh get nodes
# The SSH host alias defaults to `computa` (set it up in ~/.ssh/config); override with NODE_SSH_HOST.
set -euo pipefail
args=$(printf '%q ' "$@")
exec ssh "${NODE_SSH_HOST:-computa}" "KUBECONFIG=~/.kube/config kubectl $args"
