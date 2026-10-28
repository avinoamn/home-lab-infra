#!/usr/bin/env bash
# DELETES A PROJECT AND ALL ITS DATA (ask first). Deletes the project's namespace: every object in it, and every
# local-path volume with its data, which cannot be recovered. Use it only once the project's data is backed up off
# the node, or is disposable. See docs/onboarding.md, "Offboarding", for the steps before and after.
#   CONFIRM_DELETE=<project> scripts/offboard-project.sh <project>
# Without CONFIRM_DELETE it only lists what would be deleted. It refuses a project still in projects/projects.yaml
# (remove the entry first) and the namespaces that belong to k3s or the platform.
set -euo pipefail
cd "$(dirname "$0")/.."
project="${1:-}"
case "$project" in
  '' | default | kube-system | kube-public | kube-node-lease | monitoring | tools)
    echo "usage: scripts/offboard-project.sh <project> (not a k3s or platform namespace)" >&2; exit 2 ;;
  [a-z0-9]*) ;;
  *) echo "invalid project name: $project" >&2; exit 2 ;;
esac
if grep -Eq "^[[:space:]]*-[[:space:]]*name:[[:space:]]*${project}[[:space:]]*$" projects/projects.yaml; then
  echo "$project is still in projects/projects.yaml: remove its entry (and registry rows) first" >&2
  exit 1
fi

kca=scripts/kc-admin.sh
"$kca" get namespace "$project" >/dev/null
echo "Namespace $project holds:"
"$kca" get all,pvc,secrets,configmaps,ingresses -n "$project" --no-headers 2>/dev/null | sed 's/^/  /'
echo "Volumes whose data will be deleted:"
"$kca" get pvc -n "$project" -o custom-columns='  PVC:.metadata.name,SIZE:.spec.resources.requests.storage,VOLUME:.spec.volumeName' --no-headers

if [ "${CONFIRM_DELETE:-}" != "$project" ]; then
  echo "Nothing deleted. To delete all of the above: CONFIRM_DELETE=$project scripts/offboard-project.sh $project"
  exit 0
fi
"$kca" delete namespace "$project" --wait=true
echo "deleted namespace $project. Remove ~/.kube/$project and the project's GitHub Environment credentials too."
