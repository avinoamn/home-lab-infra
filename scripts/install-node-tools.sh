#!/usr/bin/env bash
# CHANGES THE NODE (ask first). Installs the tools scripts/helmfile.sh runs on the node, in the admin user's home
# (no sudo): helmfile to ~/.local/bin/helmfile, and the helm-diff plugin into Helm's plugin directory
# (~/.local/share/helm/plugins/diff). Both downloads
# are checked against the checksums their release publishes. Re-running replaces them with the pinned versions.
# Temporary until the node's Ansible (#2) installs them at the same paths.
#   scripts/install-node-tools.sh
set -euo pipefail
helmfile_version=1.8.2      # https://github.com/helmfile/helmfile/releases
helm_diff_version=3.15.15   # https://github.com/databus23/helm-diff/releases (needs Helm 3.18 or newer)

ssh "${NODE_SSH_HOST:-computa}" bash -s -- "$helmfile_version" "$helm_diff_version" <<'EOF'
set -euo pipefail
hf=$1 hd=$2
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
cd "$tmp"

base=https://github.com/helmfile/helmfile/releases/download/v$hf
curl -fsSLO "$base/helmfile_${hf}_linux_amd64.tar.gz"
curl -fsSLO "$base/helmfile_${hf}_checksums.txt"
grep " helmfile_${hf}_linux_amd64.tar.gz\$" "helmfile_${hf}_checksums.txt" | sha256sum -c -
tar -xzf "helmfile_${hf}_linux_amd64.tar.gz" helmfile
install -D -m 755 helmfile ~/.local/bin/helmfile

base=https://github.com/databus23/helm-diff/releases/download/v$hd
curl -fsSLO "$base/helm-diff-linux-amd64.tgz"
curl -fsSLO "$base/helm-diff_${hd}_checksums.txt"
grep " helm-diff-linux-amd64.tgz\$" "helm-diff_${hd}_checksums.txt" | sha256sum -c -
# The tarball holds diff/ with the binary in it. Unpack it straight into Helm's plugin directory: on Helm 3,
# `helm plugin install <dir>` would only link to the temporary directory.
plugins=$(helm env HELM_PLUGINS)
mkdir -p "$plugins"
rm -rf "${plugins:?}/diff"
tar -xzf helm-diff-linux-amd64.tgz -C "$plugins"

~/.local/bin/helmfile version --output short
helm plugin list
EOF
