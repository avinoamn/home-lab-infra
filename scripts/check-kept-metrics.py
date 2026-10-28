"""Checks that every platform metric used by the cluster-health rules and dashboards is kept by the monitoring stack.

platform/monitoring/values.yaml keeps only listed series for each exporter (kube-state-metrics' allowlist, and
keep-regexes for node-exporter, cAdvisor, the kubelet, Prometheus, Alertmanager and the operator). A rule or panel
that uses a dropped metric would silently never fire or stay empty, so `make check` fails instead. Run by
scripts/check.sh. Projects' own metrics (from their ServiceMonitors) are not filtered and not checked here.
"""
import glob
import json
import re
import sys

import yaml

values = yaml.safe_load(open("platform/monitoring/values.yaml", encoding="utf-8"))


def keep_regexes(relabelings):
    return [r["regex"] for r in relabelings or [] if r.get("action") == "keep"]


kept = {  # metric prefix -> full-match regexes (with ";<label>" suffixes where the rule keys on a label too)
    "kube": [re.escape(m) for m in values["kube-state-metrics"]["metricAllowlist"]],
    "node": keep_regexes(values["prometheus-node-exporter"]["prometheus"]["monitor"]["metricRelabelings"]),
    "container": keep_regexes(values["kubelet"]["serviceMonitor"]["cAdvisorMetricRelabelings"]),
    "kubelet": keep_regexes(values["kubelet"]["serviceMonitor"]["metricRelabelings"]),
    "prometheus": keep_regexes(values["prometheus"]["serviceMonitor"]["metricRelabelings"])
    + keep_regexes(values["prometheusOperator"]["serviceMonitor"]["metricRelabelings"]),
    "alertmanager": keep_regexes(values["alertmanager"]["serviceMonitor"]["metricRelabelings"]),
}
METRIC = re.compile(r"\b(kube|node|container|kubelet|prometheus|alertmanager)_[a-zA-Z0-9_]+")


def is_kept(prefix, name):
    # A keep rule on [__name__, label] matches "name;value": accept the name if any value form matches.
    return any(re.fullmatch(rx, name) or re.fullmatch(rx, name + ";") or re.fullmatch(rx.split(";")[0], name)
               for rx in kept[prefix])


exprs = []
for group in yaml.safe_load(open("platform/cluster-health/rules.yaml", encoding="utf-8"))["groups"]:
    exprs += [("rules.yaml: " + r.get("alert", r.get("record", "?")), r["expr"]) for r in group["rules"]]
for path in sorted(glob.glob("platform/cluster-health/dashboards/*.json")):
    for panel in json.load(open(path, encoding="utf-8"))["panels"]:
        exprs += [(f"{path.split('/')[-1]}: {panel['title']}", t["expr"]) for t in panel.get("targets", [])]

errors = sorted({f"{where}: {m.group(0)} is not kept by platform/monitoring/values.yaml"
                 for where, expr in exprs for m in METRIC.finditer(expr) if not is_kept(m.group(1), m.group(0))})
print("\n".join(errors) or f"all metrics used by {len(exprs)} rules and panels are kept")
sys.exit(1 if errors else 0)
