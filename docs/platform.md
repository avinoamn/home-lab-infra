# The platform contract

What a project running on the cluster can rely on, what it must not do, and which ports and hostnames are taken. It is written for someone bringing a new project to the cluster. Changing it is a pull request to this repository, with the reason recorded in [decisions.md](decisions.md).

The cluster is one small server (4 cores, 15 GiB of RAM) running k3s. In this document `<node>` stands for its name on the LAN or the tailnet.

## What a project gets

### A namespace and a deploy account

Each project gets one namespace, named after the project, and a `deployer` ServiceAccount in it. Onboarding is described in [#4](../../../issues/4). The account comes with a long-lived token, which the project uses in its local kubeconfig and in its GitHub deploy Environment. The account can manage, in its own namespace only:

- Pods, Services, ConfigMaps, Secrets and PersistentVolumeClaims
- Deployments and StatefulSets, Jobs and CronJobs
- Ingresses
- ServiceMonitors and PrometheusRules

It can also read logs and events, and use `exec` and `port-forward`. It cannot touch other namespaces or anything cluster-scoped. Helm keeps its release state in Secrets in the namespace, so a project can deploy with `helm upgrade --install` without extra permissions.

### Kubernetes

- **k3s on a single node.** Every pod runs on the same machine, so there is no high availability: a node reboot stops every project for a few minutes.
- **Version policy.** The k3s version is pinned in this repository (`node/`, [#2](../../../issues/2)). Upgrades are planned changes, made one minor version at a time, and announced in a pull request here. Projects should use only stable (GA) Kubernetes APIs.

### Storage

- **StorageClass `local-path`** (k3s's default): a directory on the node's disk, `ReadWriteOnce` only.
- **A volume cannot be resized.** Growing one means a new volume and copying the data, so size it with room to spare.
- **The data is lost with the node.** Backups are the project's own job (see "What a project must do").

### Network

- **A NodePort for each web UI**, assigned in the [registry](#registry) below. It opens as `http://<node>:<port>` from any device on the LAN or the tailnet, with nothing to set up on the device.
- **Traefik** (bundled with k3s) serves Ingresses on port 80 for `*.local` hostnames from the registry. See [how `*.local` names resolve](#how-local-names-resolve).
- **Tailscale.** The node is on the tailnet. Who can reach which ports is set by the Tailscale policy in `tailscale/` ([#6](../../../issues/6)).

### Monitoring and alerts

The monitoring stack (Helm release `kps`, kube-prometheus-stack, in namespace `monitoring`) picks up what a project ships from its own namespace:

- **ServiceMonitors, PodMonitors and PrometheusRules from any namespace.** No `release:` label is needed.
- **Grafana dashboards:** ConfigMaps labelled `grafana_dashboard: "1"`, annotated `grafana_folder: <project>`. Each project gets its own folder. A dashboard `uid` must be unique across every project: if two share one, Grafana shows only one and stops loading dashboard changes. Prefix uids with the project name.
- **Grafana datasources:** Secrets labelled `grafana_datasource: "1"`. Secrets, because datasources carry passwords. Datasource uids must be unique too.
- Grafana loads dashboards and datasources only from the namespaces on its list. A namespace is added to the list at onboarding.
- **Alerts** from a project's PrometheusRules go to one shared Discord channel, grouped by alert name and namespace. Use the `severity` values `critical`, `warning` and `info`.
- **Grafana** is at NodePort 30004: anonymous viewing, plus an admin login for changes.
- **Prometheus** is internal (no NodePort). It keeps 365 days of history on a small volume that is sized for a trimmed set of series. Keep metric labels low-cardinality: no IDs, URLs or user names as label values.
- **uptime-kuma** (NodePort 30001) checks that the UIs answer. Its monitors are configured in its own UI.

## What a project must not do

- **Nothing cluster-scoped:** no Namespaces, ClusterRoles, CRDs, PersistentVolumes, StorageClasses, webhooks or PriorityClasses. If a project needs one, it is added here, for every project.
- **Nothing outside its own namespace.** `kube-system` belongs to k3s, and `monitoring` and `tools` belong to this repository.
- **No NodePorts other than the ones assigned to it** in the registry.
- **No Services of type `LoadBalancer`.** k3s's ServiceLB would claim the port on every address of the node; ports 80 and 443 already belong to Traefik.
- **No `hostNetwork`, `hostPort`, `hostPath` or privileged containers,** unless the registry assigns that project those host ports and records why.
- **Nothing exposed to the internet:** no router port forwarding, no Tailscale Funnel, no tunnels (Cloudflare Tunnel, ngrok and the like). Most UIs have no login, and they rely on staying on the private network.
- **No admin credentials.** A project deploys with its own `deployer` account and never needs more.

Not all of these are enforced yet. The `deployer` account already blocks cluster-scoped objects and other namespaces. Limits on NodePorts, host access and resources come with [#8](../../../issues/8). Until then, this document is the rule.

## What a project must do

- **Set resource requests and limits on every container.** All projects share 4 cores and 15 GiB. A container without a CPU limit once took 3.5 cores and starved everything else.
- **Pin images to exact versions,** never `latest` or another tag that moves. With a moving tag, what runs depends on what the node happened to cache.
- **Keep its Secrets out of git.** Create them in the namespace, from a script or the deploy workflow.
- **Back up its own data,** off the node, and test the restore. `local-path` volumes die with the disk.
- **Register ports and hostnames here before using them,** in the same pull request that onboards the project or changes its entry.

## Registry

Every NodePort, Ingress hostname and host port in use. The NodePort range is k3s's default, 30000–32767. New NodePorts take the next free number.

### NodePorts

| Port | Project | Namespace | Service | What |
|---|---|---|---|---|
| 30001 | platform | `tools` | `uptime-kuma` | uptime-kuma |
| 30002 | tickertape | `tickertape` | `ner-ui` | ner UI |
| 30003 | tickertape | `tickertape` | `laya-ui` | laya UI |
| 30004 | platform | `monitoring` | `kps-grafana` | Grafana |
| 30393 | k3s | `kube-system` | `traefik` | Traefik's 443, assigned by Kubernetes (LoadBalancer Services get NodePorts too) |
| 31963 | k3s | `kube-system` | `traefik` | Traefik's 80, assigned by Kubernetes |

### Ingress hostnames (Traefik, port 80)

| Hostname | Project | Namespace |
|---|---|---|
| `grafana.local` | platform | `monitoring` |
| `ner.local` | tickertape | `tickertape` |
| `laya.local` | tickertape | `tickertape` |

### Host ports

None assigned. A project that needs `hostNetwork` or `hostPort` lists each port, its protocol and the reason here.

### How `*.local` names resolve

There is no DNS for them. A device that wants the names needs a hosts-file entry pointing them at the node's LAN or Tailscale address. Traefik answers on both:

```text
<node-address>  grafana.local ner.local laya.local
```

Phones and tablets can't edit their hosts file, which is why every UI also has a NodePort. The NodePort is the main way in, and the hostname is an extra.
