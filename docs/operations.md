# Operations

How to look at and change what this repository runs. Why it works this way is in [decisions.md](decisions.md); what projects can rely on is in [platform.md](platform.md).

## Admin access

All admin work runs on the node over SSH, with the admin kubeconfig that lives there. It never leaves the node: not to the laptop, and not to GitHub. You need an SSH host alias for the node (the scripts use `computa`, or set `NODE_SSH_HOST`) with key login.

| Script | What it does |
|---|---|
| `scripts/kc-admin.sh <kubectl args>` | `kubectl` as cluster admin, on the node |
| `scripts/projects.sh diff [project]`, `apply <project>` | The projects' namespaces and deploy accounts: renders `projects/chart` on the node and runs `kubectl diff` or `kubectl apply` ([onboarding.md](onboarding.md)) |
| `scripts/helmfile.sh <helmfile args>` | Helmfile on the node. It copies `helmfile.yaml.gotmpl`, `platform/` and `projects/` to a temporary directory there, runs, and removes it. Helm's repository list and cache stay in that directory, so the node's own Helm setup is not touched. |

Read-only commands (`get`, `describe`, `logs`, `helmfile diff`) are always safe. Anything that changes the cluster is a planned change.

### Tools on the node

`scripts/helmfile.sh` needs, in the admin user's home:

| Tool | Version | Where |
|---|---|---|
| Helm | v3.21.2 | `/usr/local/bin/helm` |
| Helmfile | 1.8.2 | `~/.local/bin/helmfile` |
| helm-diff plugin | 3.15.15 | `~/.local/share/helm/plugins/diff` |

The node's Ansible playbook installs them at the pinned versions (`node/group_vars/all.yml`), checksum-verified (see "The node" below). The tools image in CI (`ci/Dockerfile`) uses the same Helm and Helmfile versions; upgrade them together. Its `promtool` likewise matches the Prometheus version kube-prometheus-stack runs. Dependabot skips these three (`.github/dependabot.yml`), so they move only with the node or the monitoring stack. It keeps proposing the tools that stand alone (Python, shellcheck, kubeconform, yamllint).

## The node

The server is described as Ansible in `node/`: Ubuntu's packages and automatic security updates, Tailscale, k3s, the admin tools and the admin kubeconfig. Every version is pinned in `node/group_vars/all.yml`. The playbook runs from the tools image, over SSH with your `~/.ssh` (host alias `computa`), and asks for the admin user's sudo password at the start. Run it from your own terminal: it reads the password without showing it.

```sh
scripts/node.sh check    # read-only: what a run would change (--check --diff). Expect changed=0.
scripts/node.sh apply    # changes the node: run check first, and only after the change is merged
```

Each run is logged to `node-run.log` (git-ignored). The playbook captures the node as it was installed:

- **Not managed yet:** SSH runs with Ubuntu's defaults (password login allowed, root by key only). ufw is installed and stays off. Hardening either is a separate, reviewed change.
- **Install steps run only when needed:** k3s, Helm, Helmfile and helm-diff are installed only when missing or at another version. A run on an up-to-date node only checks them.

### Upgrading k3s

Upgrade one minor version at a time ([decisions.md](decisions.md), "The platform contract"), about once a quarter or when a fix is needed:

1. Read the release notes of the new version, and of every minor version in between, for removed APIs and changed defaults.
2. On a branch, set `k3s_version` in `node/group_vars/all.yml`, and `k3s_install_script_sha256` to the checksum of that tag's `install.sh`:

   ```sh
   curl -sL https://raw.githubusercontent.com/k3s-io/k3s/<version, with + as %2B>/install.sh | sha256sum
   ```

3. `scripts/node.sh check` should show only the two install steps.
4. After merge, when the projects are quiet: `scripts/node.sh apply`. The install script replaces the binary and restarts k3s. Running pods keep running during the restart, but the API is down for a minute.
5. Check the node is Ready, every pod is running, and the dashboards and uptime-kuma are green ("Checking that it works" below).

k3s's certificates are valid for a year and are renewed only when k3s starts within 120 days of their expiry. An upgrade restarts k3s, so upgrading regularly also renews them. "The API certificate" below covers the alert if that doesn't happen.

### Installing a node from scratch

For a new or rebuilt server (disaster recovery is [#9](../../../issues/9)):

1. **Install Ubuntu 24.04 LTS Server** (x86_64). Create the admin user with sudo, and add your SSH public key to its `~/.ssh/authorized_keys`.
2. **On your laptop,** point the `Host computa` entry in `~/.ssh/config` at the new address (HostName, User, IdentityFile), and check that `ssh computa true` works.
3. **`scripts/node.sh check`, then `scripts/node.sh apply`.** It installs the packages, Tailscale, k3s (with the cluster's bundled Traefik, local-path storage, CoreDNS and metrics-server), the admin tools and the admin kubeconfig. Run `check` again afterwards: it should show `changed=0`.
4. **Join the tailnet by hand:** `sudo tailscale up` on the node and log in. Then, in the admin console: tag the machine `tag:k3s`, disable its key expiry, and remove the old machine. The Tailscale policy then applies to it ("Tailscale policy" below).
5. **Put the cluster back** with this repository:
   - `scripts/create-monitoring-secrets.sh`
   - `scripts/helmfile.sh apply`
   - `scripts/projects.sh apply <project>` for each project
6. Projects deploy themselves again. Their data comes back from backups ([#9](../../../issues/9)).

## Applying a change

1. Change the files on a branch, run `make check`, and open a pull request.
2. See what it would change on the cluster (read-only):

   ```sh
   scripts/helmfile.sh diff                  # every release
   scripts/helmfile.sh -l name=kps diff      # one release
   ```

   Put the diff in the pull request if it is not obvious from the change.
3. After the pull request is merged, apply from an up-to-date `main`, so the cluster always matches `main`:

   ```sh
   git switch main && git pull
   scripts/helmfile.sh apply
   ```

   `apply` diffs first and upgrades only the releases that changed. A release with an empty diff is not touched (no new Helm revision).
4. Check the result (for the monitoring stack, see "Checking that it works" below).

To undo an applied change, revert the pull request and apply again. `helm rollback` also works in an emergency (`ssh <node> 'KUBECONFIG=~/.kube/config helm rollback kps <revision> -n monitoring'`), but then the cluster no longer matches `main` until the files are fixed.

## The monitoring stack

Helm release `kps` (kube-prometheus-stack) in namespace `monitoring`: Prometheus, Alertmanager, Grafana, the Prometheus Operator, kube-state-metrics and node-exporter. The chart version is pinned in `helmfile.yaml.gotmpl`, and the values are in `platform/monitoring/`:

- `values.yaml`: everything except the namespace lists. Its comments explain the sizing, the trimmed scrape set and the access model.
- `values-projects.yaml.gotmpl`: the namespaces Grafana loads dashboards and datasources from, made from `projects/projects.yaml`.

**A `kps` upgrade is heavy for the node** (4 cores). Apply it when the projects are quiet, for example once tickertape's laya backlog is drained (its Pipeline dashboard).

### Secrets

The stack needs two Secrets in `monitoring`. They are not part of the release and never in git:

| Secret | Keys | Holds |
|---|---|---|
| `grafana-admin` | `admin-user`, `admin-password` | Grafana's admin login (viewing needs no login) |
| `alertmanager-discord` | `webhook-url` | the Discord webhook alerts are sent to, mounted into Alertmanager as a file |

`scripts/create-monitoring-secrets.sh` creates both, and only when they are missing (`DISCORD_WEBHOOK_URL` must be set for the webhook). On a new cluster, run it before the first `apply`. To replace one, for example a new webhook: delete the Secret, run the script again, then restart Alertmanager (`scripts/kc-admin.sh rollout restart statefulset/alertmanager-kps-kube-prometheus-stack-alertmanager -n monitoring`). Both steps change the cluster.

To read the Grafana admin password:

```sh
scripts/kc-admin.sh get secret grafana-admin -n monitoring -o jsonpath='{.data.admin-password}' | base64 -d
```

### Alerts

Projects ship PrometheusRules in their own namespace. Prometheus picks them up from any namespace, and Alertmanager sends every alert to one Discord channel shared by all projects. Alerts are grouped by alert name and namespace, so each message names the project. A message goes out when an alert starts and when it resolves, and a still-firing alert is repeated every 12 hours.

### Cluster health: the platform's own alerts and the Node dashboard

The Helm release `cluster-health` (chart `platform/cluster-health/`, namespace `monitoring`) adds what concerns every project. It is separate from `kps`, so changing an alert or a panel does not upgrade the whole stack.

| Alert | Fires when | Severity |
|---|---|---|
| `NodeFilesystemFillingUp` | a filesystem will be full within 24 hours at the rate of the last 6 hours (and is over 60% used), for 1 hour | warning |
| `NodeFilesystemFillingUpFast` | ... within 4 hours at the rate of the last hour (and over 80% used), for 15 minutes | critical |
| `NodeFilesystemAlmostFull` | under 5% free, for 10 minutes | critical |
| `NodeMemoryLow` | under 10% of memory available, for 15 minutes | warning |
| `NodeOOMKill` | the kernel killed a process for lack of memory | warning |
| `NodeCPUSaturated` | the CPU over 90% busy for an hour | warning |
| `KubeNodeNotReady`, `KubeNodePressure` | the node is not Ready, or reports memory, disk or PID pressure, for 5 minutes | critical, warning |
| `ExporterDown`, `ExporterMissing` | node-exporter or kube-state-metrics cannot be scraped (the alerts above go blind) | critical |
| `PrometheusRetentionShortened` | Prometheus deletes data for size before it is a year old | warning |
| `PrometheusStorageWillReachCap` | its storage will reach the cap within 30 days, before holding a year | warning |
| `PrometheusRuleFailures`, `MonitoringConfigReloadFailed` | rules fail to evaluate, or Prometheus or Alertmanager runs on an old configuration | warning |
| `KubeAPICertificateExpiring` | the daily `api-cert-check` Job failed: the API certificate expires within 60 days | warning |
| `KubeAPICertificateCheckNotRunning` | that check has not passed for 3 days | warning |

**Volumes.** `local-path` volumes are directories on the root filesystem. Their requested size is not enforced, and the kubelet reports the whole disk for each of them. So the filesystem alerts cover every volume, and there is no per-volume alert.

**What is not covered.** If the whole node goes down, Prometheus, Alertmanager and uptime-kuma go with it, and nothing notifies. You notice when the UIs stop answering. Prometheus or Alertmanager being down alone is reported by uptime-kuma.

The rules are in `platform/cluster-health/rules.yaml`, with unit tests in `rules_test.yaml` (`make check` runs `promtool check rules` and `promtool test rules`). To change one, edit both, then diff and apply as usual.

**The Node dashboard** (Grafana, folder "platform") shows:

- CPU, memory, disk and Prometheus storage at a glance, including how long until the root disk is full
- CPU and memory per namespace
- pressure, disk and network I/O, temperature
- requests and limits against the node's capacity
- container restarts and OOM kills
- the volumes' requested sizes

It is generated by `platform/cluster-health/gen_dashboards.py`: edit the panels there, run it, and commit the JSON (`make check` fails if they differ). To run every panel's query against the live Prometheus (read-only):

```sh
GRAFANA_URL=http://<node>:30004 python scripts/verify-dashboards.py
```

**The series budget.** To keep a year of history within Prometheus's 5 GB cap, the monitoring stack stores only the series a dashboard or an alert uses (the lists in `platform/monitoring/values.yaml`, about 1,500 series in all). `make check` fails if a rule or panel here uses a metric that is not kept. A project that needs another platform metric asks for it, and it is added to the list with what uses it. Watch the "Prometheus storage" and "Prometheus series" panels after any change.

### The API certificate

k3s's certificates are valid for a year. k3s renews them every time it starts within 120 days of expiry, and leaves them alone otherwise. The current API certificate expires on 2027-07-12, so a k3s restart after mid-March 2027 renews it. The `api-cert-check` CronJob (in `cluster-health`) verifies the certificate daily against the cluster's CA and fails within 60 days of expiry, which fires `KubeAPICertificateExpiring`. When it fires, restart k3s (a planned change: every pod restarts) and check the Job again:

```sh
scripts/kc-admin.sh create job --from=cronjob/api-cert-check cert-check-manual -n monitoring   # run the check now
scripts/kc-admin.sh logs -n monitoring job/cert-check-manual
```

### Looking at Prometheus and Alertmanager

Neither has a NodePort. For quick queries, Grafana's anonymous datasource proxy works from any device on the network:

```sh
curl -s 'http://<node>:30004/api/datasources/proxy/uid/prometheus/api/v1/query?query=up'
```

For the full UIs, forward a port over SSH. `kubectl port-forward` listens on the node's localhost, and `ssh -L` brings that port to the laptop:

```sh
ssh -L 9090:localhost:9090 computa 'KUBECONFIG=~/.kube/config kubectl port-forward -n monitoring svc/kps-kube-prometheus-stack-prometheus 9090'
ssh -L 9093:localhost:9093 computa 'KUBECONFIG=~/.kube/config kubectl port-forward -n monitoring svc/kps-kube-prometheus-stack-alertmanager 9093'
```

Then open `http://localhost:9090` (Prometheus, see Status → Targets) or `http://localhost:9093` (Alertmanager).

### Checking that it works

After an apply, or when something looks wrong:

1. Grafana opens at `http://<node>:30004`, and the projects' dashboards are in their folders.
2. Every Prometheus target is up: Status → Targets, or `count by (job) (up == 0)` returns nothing.
3. A test alert reaches Discord. With the Alertmanager port-forward above running:

   ```sh
   curl -XPOST localhost:9093/api/v2/alerts -H 'Content-Type: application/json' \
     -d '[{"labels":{"alertname":"TestAlert","severity":"info","namespace":"monitoring"}}]'
   ```

   It arrives within a minute (`group_wait` is 30 seconds), and resolves on its own after about five minutes.

## Tailscale policy

The tailnet policy is `tailscale/policy.hujson` ([its README](../tailscale/README.md)). The console holds the live copy, and the file is the source of truth. To change it:

1. Edit the file on a branch. For a project's tag and grant, change `projects/projects.yaml` and run `python scripts/gen-tailscale-policy.py`. Run `make check`, and merge.
2. In the admin console, open Access controls and paste the whole file over the editor's content. "Preview rules" shows who may reach what.
3. Save. The console runs the file's `tests` and refuses to save if one fails, so a bad policy never goes live.
4. Paste it unchanged every time, so the live policy stays identical to the file.

**The node is tagged `tag:k3s`** (Machines, the node's menu, Edit tags). A tagged device belongs to the tag instead of a user. Tagging in the console keeps the device's key expiry, so it was turned off separately (the node's menu, Disable key expiry); the console shows "Expiry disabled". To make it user-owned again, re-authenticate it without tags on the node (`sudo tailscale up --advertise-tags= --force-reauth`, then log in as the user).

## Projects' guardrails

Each project namespace has a ResourceQuota, a LimitRange, two NetworkPolicies and a Pod Security level, all from its entry in `projects/projects.yaml` ([platform.md](platform.md#guardrails)). They change like any onboarding object: edit the entry, then `scripts/projects.sh diff <project>` and `apply <project>`.

- **How full the quota is:** `scripts/kc-admin.sh describe resourcequota project-quota -n <project>`. A pod refused by the quota shows up as `FailedCreate` in its Deployment's, ReplicaSet's or Job's events (`scripts/kc-admin.sh get events -n <project>`), not as a pod.
- **A rollout stuck on the quota:** raise the quota in the entry, or switch the workload to `Recreate`.
- **Something can't connect after a policy change:** NetworkPolicies take effect at once. To lift them while investigating (this changes the cluster), delete the allow-list and default-deny for that project, then re-apply with `projects.sh` when fixed. `projects.sh` never deletes anything, so they stay away until then:

  ```sh
  scripts/kc-admin.sh delete networkpolicy default-deny-ingress allow-own-and-platform -n <project>
  ```

## uptime-kuma

Helm release `uptime-kuma` in namespace `tools`, at `http://<node>:30001`. It checks from inside the cluster that the projects' UIs and the platform answer, and notifies Discord **on its own**, without Prometheus or Alertmanager. So it still reports when the monitoring stack itself is down. The chart version is pinned in `helmfile.yaml.gotmpl`, and the values are in `platform/uptime-kuma/values.yaml`.

### Monitors

Monitors are set up by hand in uptime-kuma's UI and stored in its database, not in this repository (see [decisions.md](decisions.md), "uptime-kuma"). This table is the reference, so they can be rebuilt from it. Keep it in step with the UI.

Every monitor is of type HTTP(s): checked every 60 seconds, marked down after 2 failed retries (60 seconds apart), and sent to the notification "Discord (home-lab alerts)".

| Name | URL | Accepted codes | Notes |
|---|---|---|---|
| tickertape: ner UI | `http://ner-ui.tickertape.svc.cluster.local:7860/` | 200-299 | |
| tickertape: laya UI | `http://laya-ui.tickertape.svc.cluster.local:7860/` | 200-299 | |
| platform: Grafana | `http://kps-grafana.monitoring.svc.cluster.local/api/health` | 200-299 | |
| platform: Prometheus | `http://kps-kube-prometheus-stack-prometheus.monitoring.svc.cluster.local:9090/-/healthy` | 200-299 | |
| platform: Alertmanager | `http://kps-kube-prometheus-stack-alertmanager.monitoring.svc.cluster.local:9093/-/healthy` | 200-299 | |
| platform: Kubernetes API | `https://kubernetes.default.svc.cluster.local/readyz` | 200-299, 401 | "Ignore TLS/SSL errors" on. k3s turns off anonymous access, so `/readyz` answers 401 without a login, which still proves the API server answers. The cluster's CA is not in uptime-kuma's trust store. |

The checks use the in-cluster Service names, so they test the application, not the NodePort path from outside. A project that wants its UI watched adds a row here and the monitor in the UI when it is onboarded.

**The notification** "Discord (home-lab alerts)" (type Discord, "Default enabled" on, so new monitors get it) posts to the same channel as Alertmanager. Its webhook URL is in uptime-kuma's database only.

### Backing up and restoring

The database (`/app/data/kuma.db`, SQLite, on the volume `uptime-kuma-pvc`) holds the monitors, the notification with its webhook, the admin login and the history. Back it up before anything risky (an upgrade, a node change) and after changing monitors:

```sh
scripts/backup-uptime-kuma.sh     # read-only: ~/home-lab-backups/uptime-kuma-<UTC time>.sql.gz
```

It is a consistent SQL dump (`sqlite3 -readonly .dump` inside the pod), checked for completeness before it is kept. It contains the admin password hash and the webhook, so keep it private.

To restore (this changes the cluster: plan it, and back up the current state first):

```sh
pod=$(scripts/kc-admin.sh get pods -n tools -l app.kubernetes.io/instance=uptime-kuma -o jsonpath='{.items[0].metadata.name}')
gzip -dc ~/home-lab-backups/uptime-kuma-<time>.sql.gz \
  | scripts/kc-admin.sh exec -i -n tools "$pod" -- sqlite3 /app/data/kuma.db.restore
scripts/kc-admin.sh exec -n tools "$pod" -- sh -c \
  'cd /app/data && sqlite3 kuma.db.restore "pragma integrity_check" && mv kuma.db.restore kuma.db && rm -f kuma.db-wal kuma.db-shm'
scripts/kc-admin.sh rollout restart deployment/uptime-kuma -n tools
```

The dump has been test-loaded into a fresh database (integrity check passes). The full restore on the cluster is rehearsed with disaster recovery ([#9](../../../issues/9)).
