"""Generates the per-project parts of tailscale/policy.hujson from projects/projects.yaml, and checks the policy.

    python scripts/gen-tailscale-policy.py           # rewrite the "BEGIN projects" ... "END projects" blocks
    python scripts/gen-tailscale-policy.py --check   # exit 1 if they are out of date or a rule below is broken

Each project gets a CI tag `tag:ci-<project>` (owned by the admins), a grant from it to `tag:k3s` on the API port and
the project's own NodePorts, and a test that it reaches those and not SSH or any other NodePort in the registry
(docs/platform.md). The check also parses the whole file (HuJSON: JSON with comments and trailing commas) and fails
if a grant comes from "*" (it would match tagged devices too) or a tag is used without an owner.
Run by scripts/check.sh. Needs PyYAML (in the tools image).
"""
import json
import re
import sys

import yaml

POLICY = "tailscale/policy.hujson"
API_PORT = 6443
projects = yaml.safe_load(open("projects/projects.yaml", encoding="utf-8"))["projects"]

# Every NodePort in the registry, so a project's test can deny all the ones that are not its own.
registry = open("docs/platform.md", encoding="utf-8").read().split("### NodePorts", 1)[1].split("###", 1)[0]
all_nodeports = sorted({int(m) for m in re.findall(r"^\| (3\d{4}) \|", registry, re.M)})


def blocks():
    owners, grants, tests = [], [], []
    for p in projects:
        tag, own = f"tag:ci-{p['name']}", sorted(np["port"] for np in p.get("nodePorts") or [])
        owners.append(f'    "{tag}": ["autogroup:admin"],')
        ports = ", ".join(f'"tcp:{port}"' for port in [API_PORT] + own)
        grants.append(f'    {{"src": ["{tag}"], "dst": ["tag:k3s"], "ip": [{ports}]}},')
        accept = ", ".join(f'"tag:k3s:{port}"' for port in [API_PORT] + own)
        deny = ", ".join(f'"tag:k3s:{port}"' for port in [22] + [n for n in all_nodeports if n not in own])
        tests += ["    {", f'      "src": "{tag}",', f'      "accept": [{accept}],', f'      "deny": [{deny}],', "    },"]
    return owners, grants, tests


def render(text):
    parts = re.split(r"(^\s*// BEGIN projects.*\n)(?s:.*?)(^\s*// END projects.*\n)", text, flags=re.M)
    if len(parts) != 1 + 3 * 3:
        sys.exit(f"{POLICY}: expected three BEGIN/END projects blocks (tagOwners, grants, tests)")
    out, generated = [parts[0]], blocks()
    for i in range(3):
        begin, end, after = parts[1 + 3 * i], parts[2 + 3 * i], parts[3 + 3 * i]
        out += [begin, "".join(line + "\n" for line in generated[i]), end, after]
    return "".join(out)


def parse_hujson(text):
    """Strip // and /* */ comments outside strings, then trailing commas, and parse as JSON."""
    out, i, in_str = [], 0, False
    while i < len(text):
        c = text[i]
        if in_str:
            out.append(c)
            if c == "\\":
                out.append(text[i + 1])
                i += 1
            elif c == '"':
                in_str = False
        elif c == '"':
            in_str = True
            out.append(c)
        elif text.startswith("//", i):
            i = text.find("\n", i) - 1 if "\n" in text[i:] else len(text)
        elif text.startswith("/*", i):
            i = text.index("*/", i) + 1
        else:
            out.append(c)
        i += 1
    return json.loads(re.sub(r",(\s*[}\]])", r"\1", "".join(out)))


def check(policy):
    errors = []
    owners = policy.get("tagOwners", {})
    for g in policy.get("grants", []):
        if "*" in g.get("src", []):
            errors.append(f"a grant comes from \"*\", which also matches tagged devices: {g}")
        for tag in [t for t in g.get("src", []) + g.get("dst", []) if t.startswith("tag:")]:
            if tag not in owners:
                errors.append(f"{tag} is used in a grant but has no tagOwners entry")
        if any(t.startswith("tag:ci-") for t in g.get("src", [])) and "*" in g.get("dst", []):
            errors.append(f"a project's CI tag may not reach \"*\": {g}")
    tested = {t.get("src") for t in policy.get("tests", [])}
    for p in projects:
        if f"tag:ci-{p['name']}" not in tested:
            errors.append(f"no test for tag:ci-{p['name']}")
    return errors


current = open(POLICY, encoding="utf-8").read()
wanted = render(current)
if "--check" in sys.argv[1:]:
    problems = [] if current == wanted else [f"{POLICY} is out of date: run python scripts/gen-tailscale-policy.py"]
    try:
        problems += check(parse_hujson(current))
    except (ValueError, json.JSONDecodeError) as e:
        problems.append(f"{POLICY} does not parse: {e}")
    print("\n".join(problems) or f"{POLICY}: up to date, parses, {len(projects)} project tag(s) checked")
    sys.exit(1 if problems else 0)
with open(POLICY, "w", encoding="utf-8", newline="\n") as f:
    f.write(wanted)
print("wrote", POLICY)
