#!/usr/bin/env bash
# The drift check (docs/operations.md, "The drift check"). A daily timer on the node compares the cluster with the
# files last applied from here, and those files with main on GitHub, and reports to an uptime-kuma push monitor.
#   scripts/drift.sh run            # read-only: run the check on the node now and print its report (sends the result)
#   scripts/drift.sh record         # record this checkout's files as what the cluster runs; changes nothing on the
#                                   # cluster. scripts/helmfile.sh apply and scripts/projects.sh apply do it themselves.
#   scripts/drift.sh set-push-url   # store the push monitor's URL on the node; asks for it without echo
# NODE_SSH_HOST as in helmfile.sh.
set -euo pipefail
cd "$(dirname "$0")/.."
host="${NODE_SSH_HOST:-computa}"

case "${1:-}" in
  run)
    # The script exits 1 when it found something; its report says what.
    ssh "$host" /usr/local/bin/home-lab-drift-check
    ;;

  record)
    # The files the apply scripts read, as git sees them: tracked and new files, not ignored ones. They replace the
    # previous record in one step, so a check running at the same time sees the old or the new files, never a mix.
    source_line="$(git rev-parse --short HEAD) on $(git branch --show-current || true)"
    git diff --quiet HEAD -- helmfile.yaml.gotmpl platform projects || source_line="$source_line, with local changes"
    source_line="$source_line, $(date -u +%Y-%m-%dT%H:%MZ)"
    # shellcheck disable=SC2029 # the quoted source line expands here on purpose
    git ls-files -z --cached --others --exclude-standard -- helmfile.yaml.gotmpl platform projects \
      | tar --null -T - -cf - \
      | ssh "$host" "set -e
          s=~/.local/state/home-lab-infra
          mkdir -p \$s && rm -rf \$s/applied.new \$s/applied.old && mkdir \$s/applied.new
          tar -xf - -C \$s/applied.new
          if [ -d \$s/applied ]; then mv \$s/applied \$s/applied.old; fi
          mv \$s/applied.new \$s/applied && rm -rf \$s/applied.old
          printf '%s\n' $(printf '%q' "$source_line") > \$s/applied-source"
    echo "recorded as applied: $source_line"
    ;;

  set-push-url)
    IFS= read -rsp "uptime-kuma push URL (from the push monitor's page): " url
    echo
    case "$url" in
      http://*/api/push/* | https://*/api/push/*) ;;
      *) echo "that doesn't look like a push URL (http://<host>:<port>/api/push/<token>)" >&2; exit 2 ;;
    esac
    # On stdin, so the token is never on a command line; only the admin user can read the file.
    printf '%s\n' "$url" | ssh "$host" 'umask 077 && mkdir -p ~/.config/home-lab-infra && cat > ~/.config/home-lab-infra/drift-push-url'
    echo "stored on the node. Check it with: scripts/drift.sh run"
    ;;

  *)
    echo "usage: scripts/drift.sh run | record | set-push-url" >&2
    exit 2
    ;;
esac
