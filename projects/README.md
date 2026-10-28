# projects/

One entry per project on the cluster, rendered from one template: its namespace, its `deployer` ServiceAccount, Role and token, and the namespace's place in Grafana's list. A project's ports and hostnames are registered in [docs/platform.md](../docs/platform.md).

The project's own workloads are not here. They live in the project's repository, which deploys them into its namespace with its `deployer` account.

Filled in by [#4](../../../issues/4). Today tickertape's namespace and account are still defined in the tickertape repository.
