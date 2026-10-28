# node/

The server itself, as Ansible: OS packages and settings, Tailscale, and k3s (pinned version and flags). Also the tools that changes to the cluster run with on the node (Helmfile and the helm-diff plugin).

Ansible runs in a pinned Docker container, the same one CI uses (see [docs/decisions.md](../docs/decisions.md)). The real inventory (addresses, SSH user) is git-ignored. Only an example with placeholders is tracked.

Filled in by [#2](../../../issues/2). Today the node is still as it was installed by hand.
