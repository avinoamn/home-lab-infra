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

**Helmfile and helm-diff were installed on the node by a script before the node was under Ansible.** Adopting the monitoring stack ([#3](../../../issues/3)) needed them before [#2](../../../issues/2) brought the node under code. A script (`scripts/install-node-tools.sh`) put them in the admin user's home without sudo, checksum-verified. The node's playbook took them over at the same paths, and the script was removed.

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

**cubicle owns the node's tailnet name on 443, and runs LiveKit on the host network** ([#25](../../../issues/25), 2026-10-29). cubicle's browser client needs camera and microphone, which browsers allow only on HTTPS pages, and its friends reach it over Tailscale. So its UI is served at `https://<node>.<tailnet>.ts.net` with a certificate from `tailscale cert`, instead of a plain-HTTP NodePort. The node has one such name, so its 443 goes to one project; a second project wanting HTTPS would need a path on it or another approach, decided then. LiveKit's WebRTC media must reach the node directly (7881/TCP, 7882/UDP), which needs the host network and therefore Pod Security `privileged` for the whole `cubicle` namespace, with its three host ports in the registry. Rejected alternatives: NodePorts for the media (WebRTC advertises one fixed address and port per candidate, and LiveKit's own docs require host networking), and a separate namespace for LiveKit alone (it shares its API key Secret with the cubicle server, and a second namespace and `deployer` for one pod is more to run than the narrower Pod Security is worth). The cubicle server's own pod still sets a restrictive security context.

**Offboarding refuses to run while the project is still listed, and needs `CONFIRM_DELETE=<project>`.** Deleting a namespace deletes its `local-path` volumes, and their data cannot be recovered. Requiring the list change (merged through a pull request) and an explicit confirmation makes it a deliberate, two-step act.

## uptime-kuma

**uptime-kuma was adopted unchanged.** Release `uptime-kuma` kept its name, namespace (`tools`), chart version (4.1.0, app 2.3.0) and its only values (the NodePort). `helmfile diff` against the live release was empty. The same diff with a changed NodePort showed the change, which proves the empty result is real.

**It watches the projects' UIs and the platform itself, and notifies Discord on its own.** Prometheus and Alertmanager cannot report their own outage, but uptime-kuma checks them from inside the cluster and sends its own notifications. That gives a second path that does not depend on the monitoring stack. When adopted it had no monitors at all. Six were added: the two tickertape UIs, Grafana, Prometheus, Alertmanager and the Kubernetes API.

**Its monitors are set up by hand and documented, not managed as code.** A tool that creates monitors from files (AutoKuma) would make them reviewable, but it adds a component, changes the adopted release, and needs an uptime-kuma login stored in the cluster. With a handful of monitors, a table in operations.md plus database backups is enough to rebuild them. Revisit if the list grows or changes often.

**Its database is backed up as a SQL dump to the laptop.** `sqlite3 -readonly .dump` inside the pod gives a consistent copy without stopping it or touching the volume, and the image already has `sqlite3`. The dump holds the webhook and the admin password hash, so it stays off the repository. It is on the list of data that is not code ([#9](../../../issues/9)).

## Cluster health

**The platform's alerts and dashboard are a separate Helm release, `cluster-health`, not part of `kps`.** Upgrading kube-prometheus-stack is heavy for the node. Rules and panels change more often than the stack, and as a small local chart they apply in seconds.

**The rules are a plain Prometheus rule file with unit tests.** `rules.yaml` is what `promtool` checks and tests (`rules_test.yaml` feeds made-up series and checks which alerts fire). The chart only wraps it in a PrometheusRule. This proves "a filling disk raises an alert" without filling a disk.

**The series were trimmed to what dashboards and alerts use, with a recorded budget.** Measured on 2026-10-28, about 6,800 live series grew Prometheus's storage by ~22 MB a day, which would reach the 5 GB cap after ~230 days instead of the intended 365. Most series were exporter internals nobody looked at:

- Prometheus Operator internals (~600)
- Prometheus's and Alertmanager's own HTTP histograms (~2,200)
- kube-state-metrics families no panel used (~2,200)
- per-pod network interfaces (~580), which also churn with every pod

Each exporter now keeps an explicit list, and `make check` fails if a rule or panel uses a metric that is not on it. The cost: ad-hoc exploration in Grafana sees fewer metrics, and a new need means adding to the list first.

**Volumes are covered by the root filesystem's alerts, not per volume.** `local-path` volumes are directories on the node's root filesystem. Their requested size is never enforced, and the kubelet's volume statistics report the whole disk for each of them. So keeping `kubelet_volume_stats_*` (as first planned) would only repeat the disk numbers. Measuring each directory (a `du` CronJob feeding node-exporter) was rejected as more moving parts than the risk warrants.

**A whole-node outage is not reported, for now.** Prometheus, Alertmanager and uptime-kuma all run on the node. An outside dead-man's switch (Alertmanager's Watchdog pinging a service such as healthchecks.io) would cover it, but it needs an external account, so it is left as a known gap. Prometheus or Alertmanager being down alone is reported by uptime-kuma.

**The API certificate is checked by a daily CronJob, not by uptime-kuma.** uptime-kuma sends expiry warnings only for certificates it verifies, and it can verify against a custom CA only in its mTLS mode, which demands a client certificate and key. The CronJob verifies the certificate against the public cluster CA, fails within 60 days of expiry, and an alert on the failed Job notifies. It needs no API token, and it uses metrics that are kept anyway.

## Guardrails between projects

Each guardrail was tried first on a throw-away k3s at the node's version (v1.36.2, in Docker), then dry-run against the live cluster.

**Each project gets a ResourceQuota on requests and memory limits, plus counts, and a LimitRange with defaults.** The quota caps CPU and memory requests, memory limits, pods, volumes and storage, and also the project's NodePort count (from the registry), with no LoadBalancers. CPU limits are not capped. A cap would force a CPU limit onto every container, and CPU limits throttle; only work that needs a hard cap (like tickertape's laya) sets one. The LimitRange gives containers without resources small defaults, because a quota refuses pods that do not state what they count against. Helm hook Jobs and `kubectl run` pods usually state nothing. On the throw-away cluster, a `Recreate` rollout fitted under a 96% full quota and a surging `RollingUpdate` did not, so the contract asks projects to leave room for their rollouts. tickertape's quota is sized from its measured use, with room for its Jobs.

**Projects are isolated by NetworkPolicy: ingress from their own namespace, the platform namespaces and outside clients only.** k3s enforces NetworkPolicies with its embedded controller (on by default). Port-specific rules per platform component were rejected for their upkeep; the platform can reach every project, and projects cannot reach each other. NodePort clients must be allowed by address. The throw-away cluster showed that the policy is checked before kube-proxy rewrites the client's address, so it sees the LAN or tailnet device itself. The policy therefore allows every source outside the pod and service networks (k3s's defaults 10.42.0.0/16 and 10.43.0.0/16), which outside clients can only use through NodePorts. A pod of another project stays blocked even through the node's NodePort, and the kubelet's probes pass.

**Pod Security `baseline` is enforced per project, with `privileged` only for registered host ports.** The contract already forbade the host network, host ports, `hostPath` and privileged containers, and the namespace label makes Kubernetes refuse them. tickertape passed a server-side dry run of `baseline` with no warnings (`restricted` would refuse most of its pods). The level is per project because a project with real host-port needs (cubicle's media server) must run on the host network. That is allowed only with its ports in the registry, which `make check` enforces.

**Three PriorityClasses, and the platform's own pods use the highest.** `platform` for monitoring and uptime-kuma: if they are evicted, nobody hears about the trouble that caused it. `project-data` for databases, `project-batch` (negative, never preempts) for work that can wait or restart, and 0 for everything else. Assigning them to a project's pods is that project's change.

**Grafana reads ConfigMaps and Secrets only in `monitoring` and the projects with `grafana: true`.** The Grafana chart's `rbac.namespaced` replaces its cluster-wide ClusterRole with a Role per listed namespace, and its sidecar watches each namespace separately (tested on the throw-away cluster: it loaded a dashboard from a listed namespace, ignored an unlisted one, and was refused Secrets there). Kubernetes RBAC cannot narrow access by label, so Grafana can still read every Secret in a project that ships dashboards or datasources. That is recorded in `projects/projects.yaml` next to the `grafana` flag.

## Tailscale

**The tailnet policy is a file in this repository, applied by pasting it into the console.** The console runs the file's tests on every save and refuses a failing policy, so a broken file cannot go live. The GitOps action (`tailscale/gitops-acl-action`) was rejected: it needs a policy-write credential stored in GitHub, against "CI only validates". CI checks the file instead: it parses, has no grant from `"*"`, every tag has an owner, and every project is tested.

**The node is tagged `tag:k3s`, and the file has no addresses.** Grants and tests name the node by tag. Its key expiry is disabled as well; with it on, the node would have dropped off the tailnet on 2027-01-03. Tagging in the console does not change expiry (only a re-authentication with tags does), so that is a separate console step. A tagged device belongs to the tag, not to a user. A tagged machine can still be shared with another tailnet (its menu still offers "Share"), which cubicle needs.

**One CI tag per project, generated from the project list.** `tag:ci-<project>` reaches the cluster API and that project's own NodePorts only, so a project's GitHub workflow cannot reach another project's UIs. The tag, its grant and a test (it reaches its ports and not SSH or any other NodePort in the registry) are generated from `projects/projects.yaml`, so onboarding a project adds them. tickertape's tag does not reach Grafana (30004): its Deploy workflow uses only the API and its own UIs. The shared `tag:ci` that tickertape's workflow used first (it also reached Grafana) was removed once that workflow switched to its own tag and passed a dry run (avinoamn/tickertape#54).

**Your own devices keep reaching everything, through `autogroup:member` rather than `"*"`.** `"*"` also matches tagged devices, so it would hand every CI runner the whole tailnet.

## The node

**The node is captured as it was installed, and hardened later.** The playbook reproduces what runs: Ubuntu's packages, automatic security updates, Tailscale, k3s with no flags, the admin tools and the admin kubeconfig. Its first check run against the live node reported no changes. The inventory found SSH with Ubuntu's defaults (password login allowed) and ufw installed but off. Changing either is a separate, reviewed change, so adopting the node could not lock anyone out or block a port by accident.

**Ansible asks for the sudo password on every run.** It runs as the admin user and needs root for most tasks, even in check mode. A passwordless sudo rule was rejected: anyone with the laptop's SSH key would get root without a second secret. `scripts/node.sh` reads the password without echo in your terminal and passes it to the container on stdin, so it is never on a command line, in the environment or on the laptop's disk. An earlier version used Ansible's own prompt through `winpty`, which broke on Git Bash's path rewriting.

**k3s is installed with its own install script, from the pinned release's tag, only when the version differs.** That is how the node was installed, so the systemd unit and the bundled components stay exactly as k3s writes them; templating the unit would drift from upstream. The script's checksum is pinned, and the script verifies the k3s binary itself. The same "install only when missing or another version" rule covers Helm, Helmfile and helm-diff, so a check run on an up-to-date node changes nothing.

**Tailscale's signing key is pinned by checksum.** Without a checksum, `get_url` would re-download the key whenever the server's copy is newer than the node's, so the first check run reported a change even though the key was identical. With the checksum, a rotated key fails the run instead of being trusted silently.

**The tailnet name's certificate is renewed by a daily timer on the node, with `--min-validity`, not a monthly one** (#25). Without `--min-validity`, `tailscale cert` returns the cached certificate and only starts a background renewal once two-thirds of its life is gone (checked in Tailscale 1.102.4's source), so the run that triggers a renewal still loads the old certificate. With monthly runs, a 90-day certificate could expire before the next run picked up the new one. A daily run with `--min-validity 336h` renews synchronously once less than two weeks are left, gives two weeks of retries, and costs nothing on the other days (the cached certificate, an unchanged Secret). The value has to stay well under the certificate's lifetime, or every run would get a new certificate and hit Let's Encrypt's rate limits. The timer runs as root with k3s's own kubeconfig, so the admin credential stays on the node, and it reads the name from `tailscale status`, so the name is never in the repository. A CronJob was rejected: it would need the node's Tailscale socket mounted into a pod.

**The k3s `tls-san` change is left for later.** Adding the node's Tailscale address and names to the API certificate (a `/etc/rancher/k3s/config.yaml`) would remove the need for `tls-server-name` when dialling the Tailscale address. It changes the certificate and needs a k3s restart, so it is its own decision.
