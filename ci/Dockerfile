# The tools image: every tool the checks use, at pinned versions. CI and `make check` both run the checks
# inside it, so a local run and CI always agree. Dependabot updates the versions here and in requirements.txt.
# Ansible and ansible-lint (#2), and Helmfile, helm and kubeconform (#3) are added when their files arrive.
FROM koalaman/shellcheck:v0.11.0 AS shellcheck

FROM python:3.14.10-slim-trixie
COPY --from=shellcheck /bin/shellcheck /usr/local/bin/shellcheck
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --disable-pip-version-check -r /tmp/requirements.txt && rm /tmp/requirements.txt
