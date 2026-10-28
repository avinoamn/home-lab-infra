# Onboarding a project

How a new project gets onto the cluster, from "add an entry" to "its Deploy workflow passes a dry run", and how a project leaves again. What a project can rely on and must not do is in [platform.md](platform.md). Read that first.

A project gets:

- a namespace, named after the project
- a `deployer` ServiceAccount with a long-lived token, allowed to manage workloads in that namespace and nothing else (the permissions, each with its reason, are in [`projects/chart/templates/project.yaml`](../projects/chart/templates/project.yaml))
- the NodePorts and `*.local` hostnames assigned to it in the registry
- if it wants: Grafana loading dashboards and datasources from its namespace

Steps 1 to 4 need admin access to the node (see [operations.md](operations.md), "Admin access"). The steps after that happen in the project's own repository and in GitHub.

## 1. Add the project

On a branch of this repository:

1. Add an entry to [`projects/projects.yaml`](../projects/projects.yaml). The name becomes the namespace: lower case letters, digits and `-`. It can't be a namespace that belongs to k3s or the platform.

   ```yaml
   - name: myproject
     grafana: true                          # it ships dashboards or datasources
     nodePorts:
       - {port: 30005, service: myproject-ui}
     hosts: [myproject.local]
   ```

2. Add the same ports and hostnames to the registry in [platform.md](platform.md#registry). NodePorts take the next free number.
3. Run `make check`. It fails if the entry and the registry disagree, or if a port or hostname is taken twice.
4. Open a pull request with the output of the read-only diff (the new project shows up as objects to create):

   ```sh
   scripts/projects.sh diff myproject
   ```

## 2. Apply

After the pull request is merged, from an up-to-date `main` (each command changes the cluster):

```sh
scripts/projects.sh apply myproject     # namespace, deployer, token Secret, Role, RoleBinding
scripts/helmfile.sh apply               # only if grafana: true, to add the namespace to Grafana's list
```

The second command upgrades the monitoring stack, which is heavy for the node: run it when the projects are quiet.

## 3. A kubeconfig for the deploy account

```sh
scripts/write-kubeconfig.sh myproject   # writes ~/.kube/myproject
```

It holds the token, so never commit, print or share it. The project's repository then uses it through small wrappers, as tickertape does (`scripts/kc.sh`, `scripts/helm.sh`):

```sh
kubectl --kubeconfig ~/.kube/myproject get pods
helm --kubeconfig ~/.kube/myproject -n myproject list
```

Check what the account may do: `kubectl --kubeconfig ~/.kube/myproject auth can-i --list`.

## 4. Deploying from GitHub Actions (optional)

A project that deploys from GitHub needs a GitHub Environment with the cluster's address and the deploy token, and a way into the tailnet. tickertape's [`docs/releasing.md`](https://github.com/avinoamn/tickertape/blob/main/docs/releasing.md#deploying-from-github-actions) shows the whole setup and the workflow. In short:

1. **The Environment** (the project's repository, Settings, Environments): `production`, with you as required reviewer and deployments limited to `main`.
2. **The token**, piped straight from the cluster into GitHub so it never appears on screen:

   ```sh
   scripts/kc-admin.sh get secret deployer-token -n myproject -o jsonpath='{.data.token}' | base64 -d \
     | gh secret set KUBE_TOKEN --env production --repo <owner>/myproject
   ```

3. **The variables:**

   | Variable | Value |
   |---|---|
   | `KUBE_SERVER` | `https://<node-tailscale-ip>:6443` |
   | `KUBE_TLS_SERVER_NAME` | the node's name in the API certificate: the certificate has no IP address, so the IP is dialled with this name |
   | `KUBE_CA_DATA` | `scripts/kc-admin.sh get secret deployer-token -n myproject -o jsonpath='{.data.ca\.crt}'` |

4. **Tailscale:** the runner joins the tailnet as an ephemeral node with a tag, and the Tailscale policy lets that tag reach only the API and the project's NodePorts. Today all projects share the tag `tag:ci`. One tag per project comes with [#6](../../../issues/6).
5. **A dry run:** run the project's Deploy workflow with its dry-run option. It proves the chain (Tailscale, the policy, the token, the API) without changing anything.

## Rotating the token

The token never expires. Rotating it is a planned change, because it breaks the project's kubeconfig and its `KUBE_TOKEN` until both are updated:

1. `scripts/kc-admin.sh delete secret deployer-token -n myproject`
2. `scripts/projects.sh apply myproject` recreates the Secret, and Kubernetes fills in a new token.
3. `scripts/write-kubeconfig.sh myproject`, and set `KUBE_TOKEN` again (section 4, step 2).

To revoke a project's access without deleting it, do step 1 only.

## Offboarding

Removing a project deletes its namespace: every object in it, and **every `local-path` volume with its data**, which cannot be recovered. So:

1. Back up whatever the project needs to keep, **off the node**, and check that the backup restores.
2. Stop its deploys: delete its GitHub Environment's secrets, and its Tailscale tag or grant.
3. On a branch, remove its entry from `projects/projects.yaml` and its rows from the registry, and merge.
4. If it had `grafana: true`: `scripts/helmfile.sh apply` to take its namespace off Grafana's list.
5. See what will be deleted, then delete it (both change nothing until `CONFIRM_DELETE` is set):

   ```sh
   scripts/offboard-project.sh myproject                              # lists the objects and volumes
   CONFIRM_DELETE=myproject scripts/offboard-project.sh myproject     # deletes the namespace
   ```

   The script refuses a project that is still in `projects.yaml`, and the namespaces of k3s and the platform.
6. Delete `~/.kube/myproject`.
