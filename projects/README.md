# projects/

The projects on the cluster, and what each one gets from the platform.

| File | What |
|---|---|
| [`projects.yaml`](projects.yaml) | One entry per project: name (also its namespace), whether Grafana loads its dashboards, its NodePorts and hostnames |
| [`chart/`](chart/) | Renders each entry into its namespace (with its Pod Security level) and its `deployer` account (ServiceAccount, token Secret, Role with every permission explained, RoleBinding), and the guardrails: ResourceQuota, LimitRange, NetworkPolicies |

`scripts/projects.sh` renders the chart on the node and runs `kubectl diff` or `kubectl apply` there. It is never installed as a Helm release ([docs/decisions.md](../docs/decisions.md), "Projects"). Helmfile also reads `projects.yaml`, for Grafana's list of namespaces.

How to onboard or offboard a project, step by step: [docs/onboarding.md](../docs/onboarding.md). The ports and hostnames must also be in the registry in [docs/platform.md](../docs/platform.md); `make check` checks that they match.

The project's own workloads are not here. They live in the project's repository, which deploys them into its namespace with its `deployer` account.
