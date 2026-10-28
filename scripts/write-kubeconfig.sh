#!/usr/bin/env bash
# Writes ~/.kube/<project>: a kubeconfig for the project's namespace-scoped `deployer` account. It holds the token:
# never commit, print or share it. The token is read with admin access over SSH and goes straight into the file.
# Re-running rewrites the file with the same token (the token changes only when deployer-token is recreated).
#   scripts/write-kubeconfig.sh <project>
# The names stay as tickertape's bootstrap script wrote them, so projects' kc.sh/helm.sh wrappers keep working:
# cluster `computa`, user `<project>-deployer`, context `<project>`, default namespace `<project>`.
# API_SERVER overrides the API address (default https://computa:6443: the name must be in the API certificate).
set -euo pipefail
project="${1:-}"
case "$project" in
  [a-z0-9]*) ;;
  *) echo "usage: scripts/write-kubeconfig.sh <project>" >&2; exit 2 ;;
esac
kca="$(cd "$(dirname "$0")" && pwd)/kc-admin.sh"
cfg="${KUBECONFIG_OUT:-$HOME/.kube/$project}"
server="${API_SERVER:-https://computa:6443}"

# The token controller fills a new token Secret within a second or two.
token=
for _ in $(seq 1 20); do
  token=$("$kca" get secret deployer-token -n "$project" -o jsonpath='{.data.token}')
  [ -n "$token" ] && break
  sleep 1
done
[ -n "$token" ] || { echo "Secret deployer-token in $project has no token (is the project onboarded?)" >&2; exit 1; }
ca=$("$kca" get secret deployer-token -n "$project" -o jsonpath='{.data.ca\.crt}')

mkdir -p "$(dirname "$cfg")"
umask 077
tmp="$cfg.tmp.$$"
cat > "$tmp" <<KCFG
apiVersion: v1
kind: Config
clusters:
  - name: computa
    cluster: {server: $server, certificate-authority-data: $ca}
users:
  - name: $project-deployer
    user: {token: $(printf '%s' "$token" | base64 -d)}
contexts:
  - name: $project
    context: {cluster: computa, user: $project-deployer, namespace: $project}
current-context: $project
KCFG
mv -f "$tmp" "$cfg"
echo "wrote $cfg"
kubectl --kubeconfig "$cfg" auth can-i --list -n "$project" >/dev/null && echo "the deploy account can log in"
