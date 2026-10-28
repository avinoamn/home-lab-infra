# Decisions

Why this repository is set up the way it is. Each entry states the decision in bold, then the reason and the alternatives that were rejected. When a decision changes, its entry is rewritten and says what it replaced.

## Repository

**The repository is public.** Like [tickertape](https://github.com/avinoamn/tickertape), it doubles as a showcase. So tracked files hold nothing private: no secrets, tokens, real IP addresses, SSH user names, personal emails, Tailscale tailnet names or `ts.net` hostnames. Tracked files use placeholders (`<node>`, `<tailnet>`, `100.x.y.z`), and the real values live in git-ignored files, cluster Secrets or GitHub Secrets. CI checks every pull request for values that look private.

## Tooling

**Ansible manages the node: OS packages, Tailscale, and the k3s version and flags.** Re-running it is safe, and `--check --diff` shows what would change before anything does. That is how bringing the hand-installed node under code is shown to change nothing. Plain shell scripts were rejected: they have no dry run, and re-running them is not guaranteed to be safe. Documenting the steps without automating them was rejected too, because rebuilding the node after a failure would become a manual checklist.

**Ansible runs in a pinned Docker container, the same image CI uses.** Ansible does not run on Windows, and the development machine is Windows. A container gives local runs and CI the same tool versions, and a newcomer needs only Docker. WSL was rejected because its versions drift from CI and every machine needs its own setup. Running Ansible on the node itself was rejected because it needs extra Python packages there and cannot build a node from nothing.

**Helmfile manages the platform releases:** monitoring, uptime-kuma and the Traefik override. (Per-project onboarding was planned here too; see "Projects" below for why it is not.) One file pins every release and chart version, and `helmfile diff` (through the helm-diff plugin) shows each change before it is applied. Releases keep their existing names, so adopting them changes nothing. Rejected alternatives:

- **A plain `helm` script per release** (tickertape's way): no single view of what is installed, and diffs need extra steps.
- **OpenTofu** with the helm and kubernetes providers: its state file would hold Secret values and would need protected storage.

## Applying changes

**Changes are applied from a laptop over SSH, and the tools run on the node with the node's admin kubeconfig.** A script copies the repository's files to the node and runs Helmfile there, as tickertape's `install-monitoring.sh` already does with `helm`. The admin kubeconfig never leaves the node: it is not on the laptop and not in GitHub. This needs pinned versions of Helmfile and the helm-diff plugin on the node, installed by the node's Ansible. Rejected alternatives:

- **Running Helmfile on the laptop through an SSH tunnel to the API:** this puts the admin credential on the laptop's disk.
- **Applying from GitHub Actions:** an admin token stored in GitHub could do far more damage than a project's namespace-scoped deploy token. Infrastructure changes are rare, so automating them saves little.

**Helmfile runs in a temporary directory on the node, with its own Helm repository list.** `scripts/helmfile.sh` copies only the files Helmfile reads, and removes them afterwards. The node's own `helm repo` list is left alone, so nothing on the node depends on what the last run added. The charts are downloaded again on every run, which takes seconds.

**Helmfile and helm-diff were installed on the node by a script before the node was under Ansible.** Adopting the monitoring stack ([#3](../../../issues/3)) needed them before [#2](../../../issues/2) brought the node under code. `scripts/install-node-tools.sh` puts them in the admin user's home without sudo, checks their checksums, and uses the paths Ansible will take over.

**CI only validates.** On every pull request it lints, renders and schema-checks the files and looks for private values. It never connects to the cluster.

**No pull-based controller (Flux, Argo CD).** tickertape rejected one for its attack surface: a controller with cluster-admin rights that follows a git repository. Several projects sharing the cluster do not change that. On a 4-core node with 15 GiB of RAM, the controller would also compete with the projects for memory and CPU. Each project deploys itself with its own namespace-scoped account.

## The platform contract

The rules themselves are in [platform.md](platform.md). These entries say why they are what they are.

**NodePorts are assigned one at a time, using the next free number, not in blocks per project.** The ports in use were assigned as each UI appeared (30001 platform, 30002 and 30003 tickertape, 30004 platform), so they are already interleaved, and blocks would leave most of the range unused. The registry in platform.md is the list of what each project may use. Ports that Kubernetes assigns on its own, such as the NodePorts behind Traefik's LoadBalancer Service, are listed too, so nobody picks them.

**k3s is upgraded one minor version at a time, as a planned change announced in a pull request.** Kubernetes removes deprecated APIs at minor releases, and every project shares the one node. Small, announced steps give each project time to move off a removed API, and keep a failed upgrade easy to roll back.

**Every project must set CPU and memory requests and limits, pin its images, keep Secrets out of git, back up its own data and register its ports and hostnames.** All projects share 4 cores and 15 GiB. Without a CPU limit, one tickertape service once took 3.5 of the 4 cores. Moving image tags make a rollout depend on what the node cached. The platform cannot back up a project's data, because only the project knows how to restore it consistently. Some of these rules are enforced only from [#8](../../../issues/8) on. Until then they are rules a project agrees to.

**`hostNetwork` and `hostPort` are allowed only for host ports assigned in the registry.** They are banned by default, because a pod on the host network bypasses the cluster's networking and can take ports that other projects or the node need. They are not banned outright, because some workloads need them. A WebRTC media server, for example, must receive UDP directly on the node's address. Each port is registered with its protocol and the reason.

## Monitoring

**The monitoring stack was adopted, not reinstalled.** Release `kps` kept its name, namespace (`monitoring`), chart version (kube-prometheus-stack 91.9.0) and values. Before the first apply from this repository, the values Helmfile produces were compared with the live release's (identical), and `helmfile diff` against the live release was empty. A reinstall would have taken the whole stack down and put Prometheus's year of history at risk, for no gain.

**One Discord channel for every project's alerts.** Alerts are grouped by alert name and namespace, so each message names the project, and nothing in the live configuration had to change. Per-project routes (projects bringing `AlertmanagerConfig` objects in their namespace) were left for when a project needs a different receiver. They need `alertmanagerConfigSelector` settings in the stack and a wider `deployer` Role.

**Grafana's list of namespaces comes from the project list.** The dashboard and datasource sidecars watch `monitoring` plus every namespace in `projects/projects.yaml`, never all namespaces. Onboarding a project is then one entry in that file, and a namespace that was never onboarded cannot add dashboards or datasources.

## Projects

**A project's namespace and deploy account are rendered from a small Helm chart and applied with `kubectl apply`, not installed as a Helm release.** `projects/chart` turns each entry of `projects/projects.yaml` into a Namespace, the `deployer` ServiceAccount, its token Secret, a Role and a RoleBinding. `scripts/projects.sh` renders them on the node and runs `kubectl diff` or `kubectl apply`, the same way tickertape first created them. Adopting tickertape was therefore an exact no-op (`kubectl diff` empty, every object `unchanged` in a server-side dry run). A Helm release per project was rejected for three reasons:

- Adopting the live objects would have added Helm's labels and annotations to them.
- Helm would own each Namespace, so a careless `helm uninstall` could delete a project's volumes and their data.
- The release records would sit in the project's own namespace, where its `deployer` can edit them.

The cost: removing an entry does not delete anything, and offboarding is a separate script.

**Every project gets the same Role,** tickertape's, with a comment on each permission. A project that needs more asks for it here, and the change applies to every project. Per-project exceptions would make the contract harder to reason about.

**The token is a long-lived Secret, rotated only as a planned change.** Kubernetes no longer creates one by itself, and a short-lived token would need a refresh path from GitHub Actions into the cluster. The token works only inside the tailnet and only in one namespace. Recreating the Secret changes the token and breaks the project's kubeconfig and its `KUBE_TOKEN` until both are updated, so `scripts/projects.sh` never deletes it.

**The project list and the registry must agree, and `make check` enforces it.** Each project's NodePorts and hostnames are in `projects/projects.yaml` and in the registry in platform.md, and the check fails on any difference or duplicate. Blocking them inside the cluster (an admission policy) is part of [#8](../../../issues/8).

**Offboarding refuses to run while the project is still listed, and needs `CONFIRM_DELETE=<project>`.** Deleting a namespace deletes its `local-path` volumes, and their data cannot be recovered. Requiring the list change (merged through a pull request) and an explicit confirmation makes it a deliberate, two-step act.
