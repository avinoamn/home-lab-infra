#!/usr/bin/env bash
# Backs up uptime-kuma's database (monitors, notifications, admin login, history) to this machine. Read-only on the
# cluster: `sqlite3 -readonly .dump` inside the pod gives a consistent SQL dump, streamed and gzipped locally.
# The dump holds the admin password hash and the notification webhooks: keep it private and out of git.
#   scripts/backup-uptime-kuma.sh                  # writes ~/home-lab-backups/uptime-kuma-<UTC time>.sql.gz
# BACKUP_DIR overrides the directory. Restoring: docs/operations.md, "uptime-kuma".
set -euo pipefail
kca="$(cd "$(dirname "$0")" && pwd)/kc-admin.sh"
dir="${BACKUP_DIR:-$HOME/home-lab-backups}"
out="$dir/uptime-kuma-$(date -u +%Y%m%dT%H%M%SZ).sql.gz"

pod=$("$kca" get pods -n tools -l app.kubernetes.io/instance=uptime-kuma -o jsonpath='{.items[0].metadata.name}')
mkdir -p "$dir"
umask 077
"$kca" exec -n tools "$pod" -- sqlite3 -readonly /app/data/kuma.db .dump | gzip > "$out.tmp"

# A complete dump ends with COMMIT; check it before keeping the file.
if ! gzip -dc "$out.tmp" | tail -n 1 | grep -qx 'COMMIT;'; then
  rm -f "$out.tmp"
  echo "the dump is incomplete; nothing kept" >&2
  exit 1
fi
mv "$out.tmp" "$out"
echo "wrote $out ($(gzip -dc "$out" | grep -c '^INSERT INTO "\?monitor"\? ') monitors)"
