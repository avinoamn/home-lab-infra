"""Checks projects/projects.yaml against the registry in docs/platform.md.

Every project's NodePorts and hostnames must be in the registry under that project, every registry row for a
project must be in its entry, and no port or hostname may be taken twice. Run by scripts/check.sh.
"""
import re
import sys

import yaml

REGISTRY = "docs/platform.md"
PROJECTS = "projects/projects.yaml"

errors = []


def table_rows(text, heading):
    """The cells of each row of the first table after `heading`, without the header and separator rows."""
    section = text.split(heading, 1)[1]
    rows = []
    for line in section.splitlines()[1:]:
        if line.startswith("#"):
            break
        if line.startswith("|") and not line.startswith("|---"):
            rows.append([c.strip().strip("`") for c in line.strip().strip("|").split("|")])
    return rows[1:]  # drop the header row


text = open(REGISTRY, encoding="utf-8").read()
ports = table_rows(text, "### NodePorts")            # Port | Project | Namespace | Service | What
hosts = table_rows(text, "### Ingress hostnames")    # Hostname | Project | Namespace

for kind, column in (("NodePort", [r[0] for r in ports]), ("hostname", [r[0] for r in hosts])):
    for value in {v for v in column if column.count(v) > 1}:
        errors.append(f"{REGISTRY}: {kind} {value} is listed more than once")

projects = (yaml.safe_load(open(PROJECTS, encoding="utf-8")) or {}).get("projects") or []
names = [p.get("name") for p in projects]
for name in {n for n in names if names.count(n) > 1}:
    errors.append(f"{PROJECTS}: project {name} is listed more than once")

for p in projects:
    name = p.get("name", "?")
    if not isinstance(p.get("grafana"), bool):
        errors.append(f"{PROJECTS}: {name}: `grafana` must be true or false")
    want_ports = {(str(np["port"]), np["service"]) for np in p.get("nodePorts") or []}
    have_ports = {(r[0], r[3]) for r in ports if r[1] == name}
    for port, service in sorted(want_ports - have_ports):
        errors.append(f"{REGISTRY}: NodePort {port} ({service}) of {name} is missing from the registry")
    for port, service in sorted(have_ports - want_ports):
        errors.append(f"{PROJECTS}: {name}: the registry assigns NodePort {port} ({service}), the entry does not")
    for port, _ in want_ports:
        if not 30000 <= int(port) <= 32767:
            errors.append(f"{PROJECTS}: {name}: NodePort {port} is outside 30000-32767")
    want_hosts = set(p.get("hosts") or [])
    have_hosts = {r[0] for r in hosts if r[1] == name}
    for host in sorted(want_hosts - have_hosts):
        errors.append(f"{REGISTRY}: hostname {host} of {name} is missing from the registry")
    for host in sorted(have_hosts - want_hosts):
        errors.append(f"{PROJECTS}: {name}: the registry assigns hostname {host}, the entry does not")
    for host in want_hosts:
        if not re.fullmatch(r"[a-z0-9-]+\.local", host):
            errors.append(f"{PROJECTS}: {name}: hostname {host} is not of the form <name>.local")

# Registry rows that name a project which is not in the list (k3s and platform rows are fine).
for project in sorted({r[1] for r in ports + hosts} - set(names) - {"platform", "k3s"}):
    errors.append(f"{REGISTRY}: the registry names project {project}, which is not in {PROJECTS}")

for e in errors:
    print(e)
sys.exit(1 if errors else 0)
