# The tools image: every tool the checks use, at pinned versions. CI and `make check` both run the checks
# inside it, so a local run and CI always agree. Dependabot updates the versions here and in requirements.txt.
FROM koalaman/shellcheck:v0.11.0 AS shellcheck
# Keep helm at the node's version (docs/operations.md, "Tools on the node"): upgrade both together.
FROM alpine/helm:3.21.2 AS helm
FROM ghcr.io/helmfile/helmfile:v1.8.2 AS helmfile
FROM ghcr.io/yannh/kubeconform:v0.8.0 AS kubeconform
# promtool checks and unit-tests the alert rules. Keep it at the Prometheus version kube-prometheus-stack runs.
FROM prom/prometheus:v3.15.0 AS prometheus

FROM python:3.15.0-slim-trixie
COPY --from=shellcheck /bin/shellcheck /usr/local/bin/shellcheck
COPY --from=helm /usr/bin/helm /usr/local/bin/helm
COPY --from=helmfile /usr/local/bin/helmfile /usr/local/bin/helmfile
COPY --from=kubeconform /kubeconform /usr/local/bin/kubeconform
COPY --from=prometheus /bin/promtool /usr/local/bin/promtool
# Ansible needs an SSH client to reach the node (scripts/node.sh).
RUN apt-get update && apt-get install -y --no-install-recommends openssh-client && rm -rf /var/lib/apt/lists/*
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --disable-pip-version-check -r /tmp/requirements.txt && rm /tmp/requirements.txt
COPY ansible-collections.yml /tmp/ansible-collections.yml
RUN ansible-galaxy collection install --collections-path /usr/share/ansible/collections -r /tmp/ansible-collections.yml \
  && rm /tmp/ansible-collections.yml
