# CLAUDE.md

Guidance for AI coding assistants working in this repo (humans: see `README.md` and `docs/`). The rules below are binding.

**Start here:** `README.md` says what this repo owns. Open work is in GitHub Issues (`gh issue list`), and each issue lists its dependencies and a "Done when". `docs/decisions.md` records what has been decided (tooling, how changes are applied), and `docs/platform.md` is the platform contract with the NodePort and hostname registry: update the registry whenever a port or hostname changes. If it exists locally, also read `CLAUDE.local.md` (real access details, the live cluster snapshot and environment gotchas, git-ignored).

## Project

`home-lab-infra` describes a single-node k3s home lab ("computa") and everything on it that is shared between projects: the node itself (OS, Tailscale, k3s), the platform services (the monitoring stack `kps`, uptime-kuma, Traefik overrides), the Tailscale policy, and project onboarding (namespace + `deployer` account). Each project keeps its own chart or manifests and deploys only into its own namespace.

Projects on the cluster:

- **tickertape** (`github.com/avinoamn/tickertape`, usually checked out next to this repo as `../tickertape`): the first project. Its cluster-wide setup (monitoring stack, onboarding, admin scripts) was adopted here by #3 and #4 and removed from tickertape by tickertape#53, so tickertape now describes only its own namespace (its `docs/operations.md`, "What this project needs from the cluster"). The old files are in tickertape's git history before #53. Its Deploy workflow joins the tailnet as `tag:ci-tickertape`.
- **cubicle** (`github.com/avinoamn/cubicle`, `../cubicle`): a multiplayer 3D hangout for friends, onboarded by #25. Its manifests are in its `deploy/`, its needs in its `docs/design.md`, section 1.8. It is the platform's exception, recorded in `docs/platform.md`: LiveKit on the host network (host ports 7880 to 7882), the node's `ts.net` name on 443 with a `tailscale cert` certificate that the node renews into cubicle's TLS Secret (`node/roles/tailscale_cert`), friends reaching the node through Tailscale node sharing, limited to the ports under `shared` in `projects/projects.yaml`, and the node's UDP socket buffer limits sized for LiveKit (`node/roles/udp_buffers`, #31). When a decision here (platform contract, registry, Tailscale policy, guardrails) would rule one of these out, say so and ask instead of deciding silently.

## Context for #9 (disaster recovery)

#9 is the last planned issue (#30, HTTPS for other UIs, is for later); its runbook and rehearsal cover every project. Read tickertape's `docs/operations.md` "Backups" and "Restoring" (its own data and restore), and `docs/releasing.md` "Deploying from GitHub Actions" (the `production` Environment's `KUBE_*` values that change on a new cluster). For cubicle: its README "Deploying" (its git-ignored `deploy/cluster.env` and the Secrets its scripts create; `cubicle-tls` comes back from the node's certificate timer). cubicle keeps no data: players, chat and rooms are in memory.

## Rules

- **Ask, don't assume.** If anything is unclear (identities, credentials, tooling, trade-offs), ask the user before acting. Record each decision in `docs/decisions.md` once made.
- **Public repo: nothing private in tracked files.** No secrets, tokens, real IP addresses, SSH user names, personal emails, Tailscale tailnet names or `ts.net` hostnames. Use placeholders (`<node>`, `<tailnet>`, `100.x.y.z`). Real values live in `CLAUDE.local.md`, git-ignored inventory files, `~/.ssh/config`, cluster Secrets or env vars.
- **Docs are part of the change.** Update `README.md` / `docs/` in the same PR as the behaviour they describe. They are written for newcomers who do not know the project or its history.
- **Adopt, never reinstall.** Everything already runs (see `CLAUDE.local.md`, "Live cluster"). Bringing it under this repo uses the same release names, namespaces, chart versions and object names, and the first apply must change nothing. Prove it before applying: `helm diff`, `helm template` against `helm get manifest`, `kubectl diff`, a server-side dry run, Ansible `--check --diff`. Any difference gets its own decision first.
- **Ask before any cluster or node state change**: apply, delete, restart, rollout, Helm upgrade, secret changes, Ansible runs without `--check`, Tailscale policy edits, reboots. Approval covers that one change, not later ones. Read-only checks (`kubectl get/describe/logs`, `helm list/get/diff`, `--check` runs, read-only SSH commands) are fine.
- **Never `helm uninstall`** `kps`, `uptime-kuma`, `tickertape` or the k3s-managed `traefik`/`traefik-crd`, and never delete a namespace or PVC: `local-path` volumes hold Prometheus history, uptime-kuma's monitors and tickertape's Postgres, and cannot be resized or recovered.
- **Never recreate or delete a project's `deployer-token` Secret.** It would break that project's local kubeconfig and the `KUBE_TOKEN` in its GitHub Environment. Rotation is a planned change (tickertape `docs/releasing.md`, "Rotating and revoking").
- **Don't break the projects.** Each project's scripts read its own kubeconfig, `~/.kube/<project>` (tickertape's `scripts/kc.sh` and `scripts/helm.sh`, cubicle's `scripts/kc.sh`); keep those paths, their context names and the object names. Never print or read the contents of `~/.kube/*` kubeconfigs (no `kubectl config view --raw`), and never put a token in the repo.
- **`kube-system` belongs to k3s.** Change Traefik only through a k3s `HelmChartConfig`, and only after asking. Don't touch k3s's bundled components otherwise.
- **Admin access stays on the laptop.** Cluster-admin work runs over SSH with the admin kubeconfig on the node (`ssh computa 'KUBECONFIG=~/.kube/config kubectl ...'`, as `scripts/kc-admin.sh` does). No admin credential goes to GitHub; CI only validates (unless issue #1 decides otherwise and records why).
- **Web UIs are LAN/tailnet only.** Every UI has its own NodePort from the registry in `docs/platform.md`, except cubicle's, which needs HTTPS and is served on the node's `ts.net` name. Nothing is exposed to the internet (no router port-forwarding, no Tailscale Funnel); people outside the tailnet get in only through Tailscale node sharing, limited to the `shared` ports.
- **Pin versions.** Exact chart, image, k3s and tool versions; never `latest`.
- **Git:** commit only when the user asks. Never push to `main`: one branch and PR per issue, `Closes #<n>` in the body, squash merge after CI passes. Conventional commits (`feat:`, `fix:`, `docs:`, `chore:`...).
- **Shell:** the dev machine is Windows. Use Git Bash for `scripts/*.sh` and `make` (Chocolatey's `C:\ProgramData\chocolatey\bin` may need adding to PATH). Files use LF line endings. Tools that don't run on Windows (Ansible, shellcheck, helmfile...) run in the pinned tools image (`ci/Dockerfile`), through `make check` and `scripts/node.sh`.
- **Check external sources before relying on them** (chart values, k3s/Tailscale/LiveKit docs): read the current upstream docs or the chart's `values.yaml` for the pinned version, not memory.
