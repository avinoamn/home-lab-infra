# platform/

The shared services, as Helmfile releases and their values. The releases themselves, with their pinned chart versions, are listed in [`helmfile.yaml.gotmpl`](../helmfile.yaml.gotmpl) at the repository root.

| Piece | Release | Namespace | Here |
|---|---|---|---|
| Monitoring stack (Prometheus, Alertmanager, Grafana) | `kps` (kube-prometheus-stack) | `monitoring` | [`monitoring/`](monitoring/) ([#3](../../../issues/3)) |
| uptime-kuma | `uptime-kuma` | `tools` | [`uptime-kuma/`](uptime-kuma/) ([#5](../../../issues/5)) |
| Overrides for k3s's bundled Traefik | a k3s `HelmChartConfig` | `kube-system` | when one is needed |

Each release keeps its live name, namespace and chart version, so adopting it changes nothing. Helmfile runs on the node over SSH: see [docs/operations.md](../docs/operations.md) for how to diff and apply. What projects can expect from these services is in [docs/platform.md](../docs/platform.md).
