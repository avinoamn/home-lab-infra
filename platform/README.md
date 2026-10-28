# platform/

The shared services, as Helmfile releases and their values:

| Piece | Release | Namespace | Moves here in |
|---|---|---|---|
| Monitoring stack (Prometheus, Alertmanager, Grafana) | `kps` (kube-prometheus-stack) | `monitoring` | [#3](../../../issues/3) |
| uptime-kuma | `uptime-kuma` | `tools` | [#5](../../../issues/5) |
| Overrides for k3s's bundled Traefik | a k3s `HelmChartConfig` | `kube-system` | when one is needed |

Each release keeps its live name, namespace and chart version, so adopting it changes nothing. Helmfile runs on the node over SSH (see [docs/decisions.md](../docs/decisions.md)). What projects can expect from these services is in [docs/platform.md](../docs/platform.md).
