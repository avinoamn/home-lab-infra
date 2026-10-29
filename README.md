# home-lab-infra

Infrastructure as code for a single-node k3s home lab: the node, shared platform services and project onboarding.

> **Status:** everything shared on the cluster is defined here. Each piece was first installed by hand or from the first project's repository ([tickertape](https://github.com/avinoamn/tickertape)), and was brought here without reinstalling anything. What's left is in the [issues](../../issues): mainly a disaster-recovery runbook and rehearsal ([#9](../../issues/9)).

## What this repository owns, and what it doesn't

The cluster is one small server (4 cores, 15 GiB RAM) running k3s. Several projects share it. Each project keeps its own Helm chart or manifests, and deploys only into its own namespace with a namespace-scoped `deployer` account. Everything that is shared, or that needs cluster-admin rights, lives here:

| This repository | Each project repository |
|---|---|
| The node: OS, Tailscale, k3s | Its workloads, in its own namespace |
| Platform services: the monitoring stack (Prometheus, Alertmanager, Grafana), uptime-kuma, overrides for k3s's bundled Traefik | Its dashboards, alert rules and datasources, which the platform picks up from its namespace |
| Project onboarding: namespace, `deployer` account, assigned ports and hostnames | Its own Secrets, deploys and backups |
| The Tailscale policy (who can reach which ports) | Its deploy workflow |
| The platform contract: what a project can rely on, and what it must not do | |

## What runs on the cluster

| Piece | Namespace | Defined in |
|---|---|---|
| The node (Ubuntu, Tailscale, k3s), the certificate timer for its tailnet name, its UDP buffer limits | | [`node/`](node/) (Ansible), [#2](../../issues/2) |
| Monitoring stack (Helm release `kps`, kube-prometheus-stack) | `monitoring` | [`platform/monitoring/`](platform/monitoring/), [#3](../../issues/3) |
| Node and platform alerts, the Node dashboard (release `cluster-health`) | `monitoring` | [`platform/cluster-health/`](platform/cluster-health/), [#7](../../issues/7) |
| PriorityClasses (release `priority-classes`) | cluster-wide | [`platform/priority-classes/`](platform/priority-classes/), [#8](../../issues/8) |
| uptime-kuma (Helm release `uptime-kuma`) | `tools` | [`platform/uptime-kuma/`](platform/uptime-kuma/) (its monitors: [docs/operations.md](docs/operations.md#uptime-kuma)), [#5](../../issues/5) |
| Each project's namespace, `deployer` account and guardrails | `tickertape`, `cubicle` | [`projects/`](projects/), [#4](../../issues/4), [#8](../../issues/8) |
| Tailscale policy | | [`tailscale/policy.hujson`](tailscale/policy.hujson), pasted into the console, [#6](../../issues/6) |
| Traefik, CoreDNS, local-path storage, metrics-server | `kube-system` | bundled with k3s, left to k3s |

Projects: [tickertape](https://github.com/avinoamn/tickertape) (RSS feeds, NER and Grafana dashboards) and [cubicle](https://github.com/avinoamn/cubicle) (a small multiplayer 3D hangout with voice and face video, for friends the node is shared with; onboarded in [#25](../../issues/25)).

## Layout

| Path | What | Tool |
|---|---|---|
| [`node/`](node/) | The server: OS, Tailscale, k3s | Ansible (in a container) |
| [`platform/`](platform/) | Shared services: monitoring, uptime-kuma, Traefik overrides | Helmfile (run on the node) |
| [`projects/`](projects/) | One entry per project: namespace, `deployer` account, ports, hostnames. How to onboard: [docs/onboarding.md](docs/onboarding.md) | a small Helm chart, rendered and applied with `kubectl` (on the node) |
| [`tailscale/`](tailscale/) | The Tailscale policy | |
| [`docs/platform.md`](docs/platform.md) | **The platform contract:** what a project gets, what it must not do, and the port and hostname registry | |
| [`docs/decisions.md`](docs/decisions.md) | Why things are the way they are | |
| [`docs/operations.md`](docs/operations.md) | How to apply changes and run each piece | |
| [`docs/onboarding.md`](docs/onboarding.md) | How to onboard or offboard a project | |

## Checks

`make check` runs everything CI runs:

- yamllint and shellcheck
- a scan for private values (private and Tailscale IP addresses, email addresses, `ts.net` names, keys and tokens)
- the projects list against the registry in the platform contract
- ansible-lint and a syntax check of the node playbook
- the Tailscale policy (generated parts up to date, it parses, its rules)
- the onboarding chart and every Helmfile release, rendered and schema-checked (kubeconform), and Helm's lint
- the alert rules (promtool, with unit tests), the generated dashboards, and that every metric they use is kept

It needs make, git and Docker (on Windows, run it from Git Bash). The tools run inside one image with pinned versions (`ci/Dockerfile`, `ci/requirements.txt`, `ci/ansible-collections.yml`), so local runs and CI agree, and Dependabot keeps the versions current.

The scan can only look for patterns, because the real values must not be in a public file. To also catch your own (an SSH user name, your tailnet name), list them in `.private-patterns` at the repository root, one regular expression per line. The file is git-ignored.

CI (`.github/workflows/ci.yml`) runs `make check` on every pull request and on `main`. A single summary job, `CI passed`, is the one check that branch protection requires.

## Plan

1. Done: set up this repository: layout, tooling, CI, and the platform contract ([#1](../../issues/1)).
2. Done: adopt what ran, each one a no-op against the live cluster: the monitoring stack ([#3](../../issues/3)), project onboarding ([#4](../../issues/4)), uptime-kuma ([#5](../../issues/5)), the Tailscale policy ([#6](../../issues/6)) and the node itself ([#2](../../issues/2)).
3. Done: improve it: cluster health alerts ([#7](../../issues/7)) and guardrails between projects ([#8](../../issues/8)).
4. Done: onboard the second project, [cubicle](https://github.com/avinoamn/cubicle), through the onboarding path ([#25](../../issues/25)).
5. Next: write down and rehearse disaster recovery ([#9](../../issues/9)), covering every project.
6. Later: HTTPS for web UIs other than cubicle's ([#30](../../issues/30)).

## Principles

- **Adopt, don't reinstall.** Everything here already runs and holds data (Prometheus history, uptime-kuma's monitors, project databases). Each piece is brought under code with the same names and versions, and the first apply must change nothing.
- **Changes are applied from a laptop, with admin access over SSH.** Ansible manages the node and Helmfile manages the cluster, and Helmfile runs on the node, so the admin kubeconfig never leaves it. No admin credential is stored in GitHub. CI only validates. The reasons are in [docs/decisions.md](docs/decisions.md), and how to apply a change is in [docs/operations.md](docs/operations.md).
- **Nothing is exposed to the internet.** Web UIs are reached over the LAN or Tailscale, on NodePorts assigned per project. The exception is cubicle, served over HTTPS on the node's Tailscale name. People outside the tailnet get in only through Tailscale node sharing, and reach only the ports a project lists for them.
- **Public, so nothing private.** No secrets, IP addresses, user names or tailnet names in this repository. Real values live in git-ignored files, cluster Secrets or GitHub Secrets.

## License

[Apache 2.0](LICENSE)
