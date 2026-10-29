# tailscale/

[`policy.hujson`](policy.hujson) is the tailnet policy: who on the tailnet may reach what. It is the source of truth for what is in the Tailscale admin console (Access controls). It is applied by hand: change it here, then paste it into the console ([docs/operations.md](../docs/operations.md#tailscale-policy)).

- **Your own devices** (`autogroup:member`) reach everything. The rule is deliberately not `"*"`, which would also match tagged devices.
- **The node is `tag:k3s`.** The file refers to it by tag, never by address. Its key expiry is disabled too: a separate console step, because tagging in the console does not change it.
- **Each project has a CI tag, `tag:ci-<project>`,** for its GitHub Actions runners (ephemeral nodes that join through an OIDC trust credential). It reaches only the cluster API (6443) and the project's own NodePorts. These parts are generated from [`projects/projects.yaml`](../projects/projects.yaml) by `scripts/gen-tailscale-policy.py`.
- **Friends the node is shared with** (Tailscale node sharing; `autogroup:shared` in the policy) reach only the ports the projects list under `shared` in [`projects/projects.yaml`](../projects/projects.yaml): today cubicle's 443 (its page and LiveKit's signaling, through Traefik), 7881/TCP and 7882/UDP (LiveKit's media). Not SSH, the API, other host ports or any NodePort. A shared device can't start connections to the friend's devices either (Tailscale's quarantine). The grant is generated too.
- **There is no shared CI tag.** tickertape's workflow used a shared `tag:ci` until it switched to `tag:ci-tickertape` ([avinoamn/tickertape#54](https://github.com/avinoamn/tickertape/issues/54)), and the shared tag was removed.

The file's `tests` run in the console on every save, and a failing test refuses the save. `make check` checks:

- that the generated parts are up to date
- that the file parses
- that no grant comes from `"*"`
- that every tag used has an owner
- that every project's tag is tested
- that the only grant from `autogroup:shared` is the generated one, and that every `shared` port is the project's own (its host ports in the registry, or 443 for the project that owns the node's tailnet name)

The policy's own tests can't cover friends: a test's source must be a user, group, tag or host, not an autogroup, and friends' email addresses don't belong in a public file. So `make check` is the guard for that grant.
