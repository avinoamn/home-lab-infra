#!/usr/bin/env bash
# Runs the node playbook (node/) from the tools image, over SSH with your ~/.ssh (host alias `computa`).
#   scripts/node.sh check   # read-only: --check --diff, what a run would change. Asks for the sudo password.
#   scripts/node.sh apply   # CHANGES THE NODE (ask first). Asks for the sudo password.
#   scripts/node.sh tasks   # lists the tasks without connecting (a quick test of the setup)
#   scripts/node.sh lint    # ansible-lint and a syntax check; no node needed (make check runs the same)
# The sudo password is read here, without echo, and handed to the container on stdin: it is never on a command
# line, in the environment or in a file outside the container. Each run is logged to node-run.log (git-ignored).
set -euo pipefail
cd "$(dirname "$0")/.."
action="${1:-}"
case "$action" in
  check) cmd="ansible-playbook site.yml --check --diff" ;;
  apply) cmd="ansible-playbook site.yml --diff" ;;
  tasks) cmd="ansible-playbook site.yml --list-tasks" ;;
  lint) cmd="ansible-lint --offline && ansible-playbook site.yml --syntax-check" ;;
  *) echo "usage: scripts/node.sh check | apply | tasks | lint" >&2; exit 2 ;;
esac

password=""
if [ "$action" = check ] || [ "$action" = apply ]; then
  IFS= read -rsp "sudo password for the admin user on the node: " password
  echo
  cmd="$cmd --extra-vars @/tmp/become.json"
fi

docker build -q -t home-lab-infra-tools ci >/dev/null

# Docker on Windows wants Windows paths for the mounts, and Git Bash must not rewrite the container's paths.
repo=$(pwd -W 2>/dev/null || pwd)
ssh_dir=$(cygpath -m "$HOME/.ssh" 2>/dev/null || echo "$HOME/.ssh")
color=0
[ -t 1 ] && color=1

# Inside: the SSH files get the permissions ssh insists on (a Windows mount shows them as world-readable), the
# password from stdin goes into /tmp/become.json (gone with the container), and ANSIBLE_CONFIG is set because
# Ansible ignores an ansible.cfg in a world-writable directory, which a mount is.
# shellcheck disable=SC2016 # the single-quoted parts expand inside the container
printf '%s' "$password" | MSYS_NO_PATHCONV=1 docker run --rm -i \
  -v "$repo:/work" -v "$ssh_dir:/ssh-src:ro" -w /work/node \
  -e ANSIBLE_CONFIG=/work/node/ansible.cfg -e ANSIBLE_LOG_PATH=/work/node-run.log -e ANSIBLE_FORCE_COLOR="$color" \
  home-lab-infra-tools bash -c '
    mkdir -p /root/.ssh && cp /ssh-src/* /root/.ssh/ && chmod 700 /root/.ssh && chmod 600 /root/.ssh/*
    python3 -c "import json, sys; json.dump({\"ansible_become_password\": sys.stdin.read()}, open(\"/tmp/become.json\", \"w\"))"
    chmod 600 /tmp/become.json
    '"$cmd"
