# Operations

How to look at and change what this repository runs. Why it works this way is in [decisions.md](decisions.md); what projects can rely on is in [platform.md](platform.md).

## Admin access

All admin work runs on the node over SSH, with the admin kubeconfig that lives there. It never leaves the node: not to the laptop, and not to GitHub. You need an SSH host alias for the node (the scripts use `computa`, or set `NODE_SSH_HOST`) with key login.

| Script | What it does |
|---|---|
| `scripts/kc-admin.sh <kubectl args>` | `kubectl` as cluster admin, on the node |
| `scripts/helmfile.sh <helmfile args>` | Helmfile on the node. It copies `helmfile.yaml.gotmpl`, `platform/` and `projects/` to a temporary directory there, runs, and removes it. Helm's repository list and cache stay in that directory, so the node's own Helm setup is not touched. |

Read-only commands (`get`, `describe`, `logs`, `helmfile diff`) are always safe. Anything that changes the cluster is a planned change.

### Tools on the node

`scripts/helmfile.sh` needs, in the admin user's home:

| Tool | Version | Where |
|---|---|---|
| Helm | v3.21.2 | `/usr/local/bin/helm` (installed with the node) |
| Helmfile | 1.8.2 | `~/.local/bin/helmfile` |
| helm-diff plugin | 3.15.15 | `~/.local/share/helm/plugins/diff` |

`scripts/install-node-tools.sh` installs Helmfile and helm-diff at the pinned versions, checksum-verified and without sudo. Re-running it is safe. When the node is managed by Ansible ([#2](../../../issues/2)), Ansible installs them instead, at the same paths. The tools image in CI (`ci/Dockerfile`) uses the same Helm and Helmfile versions; upgrade them together.

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
