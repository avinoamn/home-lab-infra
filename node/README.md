# node/

The server as Ansible: Ubuntu's packages and automatic security updates, Tailscale, k3s, the admin tools that `scripts/helmfile.sh` runs on the node (Helm, Helmfile, helm-diff), and the admin kubeconfig.

| File | What |
|---|---|
| [`site.yml`](site.yml) | The playbook: one play, five roles |
| [`group_vars/all.yml`](group_vars/all.yml) | Every pinned version and checksum |
| [`roles/`](roles/) | `base`, `tailscale`, `k3s`, `node_tools`, `admin_kubeconfig` |
| [`inventory.yml`](inventory.yml) | The node by its SSH alias `computa`. The real address, user and key are in `~/.ssh/config`. |

Run it with `scripts/node.sh check` (read-only) or `apply`, from your own terminal; it asks for the sudo password. It runs in the tools image, the same one CI uses to lint it. How to upgrade k3s and how to install a node from scratch are in [docs/operations.md](../docs/operations.md#the-node).
