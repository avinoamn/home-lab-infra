# tailscale/

[`policy.hujson`](policy.hujson) is the tailnet policy: who on the tailnet may reach what. It is the source of truth for what is in the Tailscale admin console (Access controls). It is applied by hand: change it here, then paste it into the console ([docs/operations.md](../docs/operations.md#tailscale-policy)).

- **Your own devices** (`autogroup:member`) reach everything. The rule is deliberately not `"*"`, which would also match tagged devices.
- **The node is `tag:k3s`.** The file refers to it by tag, never by address. Its key expiry is disabled too: a separate console step, because tagging in the console does not change it.
- **Each project has a CI tag, `tag:ci-<project>`,** for its GitHub Actions runners (ephemeral nodes that join through an OIDC trust credential). It reaches only the cluster API (6443) and the project's own NodePorts. These parts are generated from [`projects/projects.yaml`](../projects/projects.yaml) by `scripts/gen-tailscale-policy.py`.
- **The shared `tag:ci`** stays until tickertape's workflow uses its own tag ([avinoamn/tickertape#54](https://github.com/avinoamn/tickertape/issues/54)), then it is removed.

The file's `tests` run in the console on every save, and a failing test refuses the save. `make check` checks:

- that the generated parts are up to date
- that the file parses
- that no grant comes from `"*"`
- that every tag used has an owner
- that every project's tag is tested
