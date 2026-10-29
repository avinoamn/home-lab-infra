"""Checks projects/projects.yaml against the registry in docs/platform.md.

Every project's NodePorts and hostnames must be in the registry under that project, every registry row for a
project must be in its entry, and no port or hostname may be taken twice. Run by scripts/check.sh.
"""
import re
import sys

import yaml

REGISTRY = "docs/platform.md"
PROJECTS = "projects/projects.yaml"

TAILNET_NAME = "<node>.<tailnet>.ts.net"   # the node's MagicDNS name, served by Traefik on 443
QUOTA_KEYS ={"requests.cpu", "requests.memory", "limits.memory", "pods", "persistentvolumeclaims", "requests.storage"}

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
host_ports = [r for r in table_rows(text, "### Host ports") if len(r) >= 3]   # Port | Protocol | Project | Reason

host_port_keys = [f"{r[0]}/{r[1]}" for r in host_ports]
for kind, column in (("NodePort", [r[0] for r in ports]), ("hostname", [r[0] for r in hosts]),
                     ("host port", host_port_keys)):
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
    level = p.get("podSecurity")
    if level not in ("baseline", "restricted", "privileged"):
        errors.append(f"{PROJECTS}: {name}: podSecurity must be baseline, restricted or privileged")
    if level == "privileged" and not any(r[2] == name for r in host_ports):
        errors.append(f"{PROJECTS}: {name}: podSecurity privileged needs its host ports in the registry ({REGISTRY})")
    if level != "privileged" and any(r[2] == name for r in host_ports):
        errors.append(f"{PROJECTS}: {name}: the registry assigns it host ports, which need podSecurity privileged")
    quota = p.get("quota") or {}
    for key in sorted(QUOTA_KEYS - set(quota)):
        errors.append(f"{PROJECTS}: {name}: quota needs {key}")
    for key in sorted(set(quota) - QUOTA_KEYS):
        errors.append(f"{PROJECTS}: {name}: quota key {key} is not one the platform sets (NodePorts come from nodePorts)")
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
    # What friends the node is shared with may reach: the tailnet name's 443, or the project's own host ports.
    for entry in p.get("shared") or []:
        m = re.fullmatch(r"(tcp|udp):(\d+)", str(entry))
        if not m:
            errors.append(f"{PROJECTS}: {name}: shared entry {entry} is not tcp:<port> or udp:<port>")
        elif entry == "tcp:443":
            if TAILNET_NAME not in want_hosts:
                errors.append(f"{PROJECTS}: {name}: shared tcp:443 needs the node's tailnet name in its hosts")
        elif not any(r[0] == m[2] and r[1].lower() == m[1] and r[2] == name for r in host_ports):
            errors.append(f"{PROJECTS}: {name}: shared {entry} is not a host port the registry assigns it")
    for host in want_hosts:
        # The node's own tailnet name is written as this placeholder: the real one is private.
        if not (re.fullmatch(r"[a-z0-9-]+\.local", host) or host == TAILNET_NAME):
            errors.append(f"{PROJECTS}: {name}: hostname {host} is not of the form <name>.local or {TAILNET_NAME}")

# Registry rows that name a project which is not in the list (k3s and platform rows are fine).
for project in sorted(({r[1] for r in ports + hosts} | {r[2] for r in host_ports}) - set(names) - {"platform", "k3s"}):
    errors.append(f"{REGISTRY}: the registry names project {project}, which is not in {PROJECTS}")

for e in errors:
    print(e)
sys.exit(1 if errors else 0)
