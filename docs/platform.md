# The platform contract

What a project running on the cluster can rely on, what it must not do, and which ports and hostnames are taken. It is written for someone bringing a new project to the cluster. Changing it is a pull request to this repository, with the reason recorded in [decisions.md](decisions.md).

The cluster is one small server (4 cores, 15 GiB of RAM) running k3s. In this document `<node>` stands for its name on the LAN or the tailnet.

## What a project gets

### A namespace and a deploy account

Each project gets one namespace, named after the project, with the guardrails described below, and a `deployer` ServiceAccount in it. The steps are in [onboarding.md](onboarding.md). The account comes with a long-lived token, which the project uses in its local kubeconfig and in its GitHub deploy Environment. The account can manage, in its own namespace only:

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
- **HTTPS on the node's tailnet name.** The node's MagicDNS name, `<node>.<tailnet>.ts.net`, can have a real certificate from Tailscale (`tailscale cert`, Let's Encrypt). Traefik serves it on 443 with an Ingress for that host, using a TLS Secret in the project's namespace. The node writes that Secret and renews it daily ([operations.md](operations.md#the-tailnet-names-certificate)); the project names it in its Ingress and never changes or deletes it. There is one such name per node and only one project can own it; the registry says which. A UI that needs a secure page (browsers allow camera and microphone only on HTTPS) uses it. The name ends up in the public certificate logs.
- **Tailscale.** The node is on the tailnet as `tag:k3s`. Your own devices reach everything. A project's GitHub runners join as `tag:ci-<project>` and reach only the API and that project's NodePorts (`tailscale/policy.hujson`). People outside the tailnet can get the node shared with them (Tailscale node sharing); they reach only the ports the projects list under `shared` (443 on the tailnet name, a project's own host ports), never SSH, the API or a NodePort.

### Monitoring and alerts

The monitoring stack (Helm release `kps`, kube-prometheus-stack, in namespace `monitoring`) picks up what a project ships from its own namespace:

- **ServiceMonitors, PodMonitors and PrometheusRules from any namespace.** No `release:` label is needed.
- **Grafana dashboards:** ConfigMaps labelled `grafana_dashboard: "1"`, annotated `grafana_folder: <project>`. Each project gets its own folder. A dashboard `uid` must be unique across every project: if two share one, Grafana shows only one and stops loading dashboard changes. Prefix uids with the project name.
- **Grafana datasources:** Secrets labelled `grafana_datasource: "1"`. Secrets, because datasources carry passwords. Datasource uids must be unique too.
- Grafana loads dashboards and datasources only from `monitoring` and the namespaces in `projects/projects.yaml`. Onboarding adds the project's namespace there.
- **Alerts** from a project's PrometheusRules go to one shared Discord channel, grouped by alert name and namespace. Use the `severity` values `critical`, `warning` and `info`.
- **Grafana** is at NodePort 30004: anonymous viewing, plus an admin login for changes.
- **Prometheus** is internal (no NodePort). It keeps 365 days of history on a small volume that is sized for a trimmed set of series. Keep metric labels low-cardinality: no IDs, URLs or user names as label values.
- **Platform metrics are a fixed list.** Everything a project's own ServiceMonitors scrape is kept. Of the platform's exporters, only what a dashboard or alert uses is stored (`platform/monitoring/values.yaml`):
  - from kube-state-metrics: CronJob created / suspended / last success, `kube_job_status_failed`, container restarts / last termination reason / requests / limits, node conditions and capacity, PVC requested size
  - from cAdvisor: container CPU and memory working set
  - the node's CPU, memory, filesystems, disks, network, pressure and temperature

  A project that needs another one asks for it, and it is added with what uses it.
- **The platform alerts on the node itself** (disk, memory, CPU, exporters, Prometheus storage, the API certificate) to the same Discord channel ([operations.md](operations.md#cluster-health-the-platforms-own-alerts-and-the-node-dashboard)), and the Node dashboard in Grafana's "platform" folder shows CPU and memory per namespace.
- **uptime-kuma** (NodePort 30001) checks from inside the cluster that the UIs and the platform answer, and notifies the same Discord channel on its own, even when the monitoring stack is down. To have a UI watched, ask at onboarding: its monitor is added by hand and listed in [operations.md](operations.md#uptime-kuma).

## What a project must not do

- **Nothing cluster-scoped:** no Namespaces, ClusterRoles, CRDs, PersistentVolumes, StorageClasses, webhooks or PriorityClasses. If a project needs one, it is added here, for every project.
- **Nothing outside its own namespace.** `kube-system` belongs to k3s, and `monitoring` and `tools` belong to this repository.
- **No NodePorts other than the ones assigned to it** in the registry.
- **No Services of type `LoadBalancer`.** k3s's ServiceLB would claim the port on every address of the node; ports 80 and 443 already belong to Traefik.
- **No `hostNetwork`, `hostPort`, `hostPath` or privileged containers,** unless the registry assigns that project those host ports and records why.
- **Nothing exposed to the internet:** no router port forwarding, no Tailscale Funnel, no tunnels (Cloudflare Tunnel, ngrok and the like). Most UIs have no login, and they rely on staying on the private network.
- **No admin credentials.** A project deploys with its own `deployer` account and never needs more.

Most of these are enforced, not just agreed (see "Guardrails" below):

- The `deployer` account blocks cluster-scoped objects and other namespaces.
- The quota caps the NodePort count and refuses LoadBalancers.
- Pod Security `baseline` refuses host network, host ports, `hostPath` and privileged containers.

Which port numbers a project uses, and not exposing anything to the internet, stay rules that the registry and reviews keep.

## Guardrails

Every project namespace gets these from its entry in `projects/projects.yaml` (`projects/chart/templates/`). The `deployer` account cannot change any of them.

**A ResourceQuota (`project-quota`)** caps the namespace's totals:

- `requests.cpu`, `requests.memory`, `limits.memory`
- the number of pods and volumes, and their total requested storage
- its NodePorts (as many as the registry assigns it)
- no LoadBalancer Services

A pod that would go over is refused when it is created, so the error shows up in the Deployment's or Job's events, not in the pod. There is no quota on CPU limits: that would force a CPU limit onto every container.

- **Leave room for a rollout.** A `RollingUpdate` with surge runs the old and the new pod together and needs both in the quota. `Recreate` (stop, then start) needs only one, as do Jobs that run one at a time. Size the quota from what the project really uses (the Node dashboard's "per namespace" panels), plus its Jobs and its rollouts.

**A LimitRange (`project-defaults`)** fills in resources for containers that set none: requests of 50m CPU and 64Mi memory, and a 256Mi memory limit. Helm hook Jobs and `kubectl run` pods usually set none, and without defaults the quota would refuse them. Set your own on every long-running container anyway (see "What a project must do").

**NetworkPolicies (`default-deny-ingress`, `allow-own-and-platform`)** let into the namespace only:

- the project's own pods
- the platform's pods: Traefik in `kube-system`, Prometheus and Grafana in `monitoring`, uptime-kuma in `tools`
- clients outside the cluster, who can only arrive through a NodePort (LAN and tailnet devices; the policy sees their own address)

Other projects' pods cannot connect, not even through the node's NodePorts. The kubelet's health probes always pass. Outgoing traffic is not restricted. A project that must accept traffic from another project asks for it here. Pods on the host network are not covered by NetworkPolicies, which is one more reason they are the exception.

A new pod is let in only a moment after it has started: k3s's policy controller adds its address to the allowed sources when it sees the pod running. Until then, its connections into a namespace with these policies are refused, its own namespace included. Long-running services don't notice, but a Job or init container that connects as soon as it starts does. tickertape's backup `pg_dump` connected within a second and failed with "Connection refused" every night until it waited first (tickertape#67).

**Pod Security** (the namespace label `pod-security.kubernetes.io/enforce`) is `baseline` by default: no host network, host ports, `hostPath`, privileged containers or added capabilities. A project whose registered host ports need the host network gets `privileged`, with the reason in the registry. `restricted` is available for a project that wants the stricter level.

**PriorityClasses** decide which pods the scheduler places first and which the kubelet evicts last when the node runs short of memory:

| Class | Value | For |
|---|---|---|
| `platform` | 1,000,000 | the platform's own pods (monitoring, uptime-kuma) |
| `project-data` | 100,000 | a project's stateful data, such as its database |
| *(none)* | 0 | everything else: the default |
| `project-batch` | -1,000 | batch, ML and other work that can wait or restart; evicted first, never pushes another pod aside |

A project references them by name (`priorityClassName`).

## What a project must do

- **Set resource requests and limits on every container.** All projects share 4 cores and 15 GiB. A container without a CPU limit once took 3.5 cores and starved everything else. The LimitRange's defaults are a floor for stray Jobs, not a size for real work.
- **Fit the quota, rollouts included** (see "Guardrails"), and give the database `project-data` and work that can wait `project-batch`.
- **Pin images to exact versions,** never `latest` or another tag that moves. With a moving tag, what runs depends on what the node happened to cache.
- **Keep its Secrets out of git.** Create them in the namespace, from a script or the deploy workflow.
- **Wait before connecting from a short-lived pod.** A Job or init container that connects to something in the namespace must retry or wait for it first (for example `until pg_isready; do sleep 2; done`, with a limit), because a new pod's first connections are refused (see "Guardrails").
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

### Ingress hostnames (Traefik)

`*.local` names on port 80, and the node's tailnet name on 443 with its Tailscale certificate.

| Hostname | Project | Namespace |
|---|---|---|
| `grafana.local` | platform | `monitoring` |
| `ner.local` | tickertape | `tickertape` |
| `laya.local` | tickertape | `tickertape` |
| `<node>.<tailnet>.ts.net` | cubicle | `cubicle` |

### Host ports

A project that needs `hostNetwork` or `hostPort` lists each port here, and gets `podSecurity: privileged` in its entry. `make check` refuses `privileged` without a row here, and a row here without `privileged`. A pod on the host network takes its ports on every address of the node (LAN and tailnet), and NetworkPolicies don't cover it.

| Port | Protocol | Project | Reason |
|---|---|---|---|
| 7880 | TCP | cubicle | LiveKit's signaling (WebSocket). LiveKit runs on the host network for its media ports, so this one is on the host too; browsers reach it through Traefik on the node's tailnet name, path `/rtc` |
| 7881 | TCP | cubicle | LiveKit's WebRTC media over TCP, when UDP is blocked. Browsers connect to it directly on the node's Tailscale address |
| 7882 | UDP | cubicle | LiveKit's WebRTC media (voice and face video), all on one UDP port. Browsers connect to it directly on the node's Tailscale address |

### How `*.local` names resolve

There is no DNS for them. A device that wants the names needs a hosts-file entry pointing them at the node's LAN or Tailscale address. Traefik answers on both:

```text
<node-address>  grafana.local ner.local laya.local
```

Phones and tablets can't edit their hosts file, which is why every UI also has a NodePort. The NodePort is the main way in, and the hostname is an extra.
