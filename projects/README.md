# projects/

The projects on the cluster. [`projects.yaml`](projects.yaml) lists them; each name is also the project's namespace. Today the list sets which namespaces Grafana loads dashboards and datasources from.

Onboarding ([#4](../../../issues/4)) adds the rest, rendered from one template per project: its namespace, its `deployer` ServiceAccount, Role and token. A project's ports and hostnames are registered in [docs/platform.md](../docs/platform.md). Until then, tickertape's namespace and account are still defined in the tickertape repository.

The project's own workloads are not here. They live in the project's repository, which deploys them into its namespace with its `deployer` account.
