#!/usr/bin/env python3
"""Generate platform/cluster-health/dashboards/*.json, the platform's Grafana dashboards. Plain stdlib.

    python platform/cluster-health/gen_dashboards.py           # rewrite the JSON
    python platform/cluster-health/gen_dashboards.py --check   # exit 1 if the JSON is not up to date (make check)

Edit the panels here, regenerate and commit the JSON: the cluster-health chart ships each file as a ConfigMap that
Grafana loads into the folder "platform". Every metric used here must be kept by platform/monitoring/values.yaml.
Same style as tickertape's grafana/gen_dashboards.py.
"""
import json
import os
import sys

PROM = {"type": "prometheus", "uid": "prometheus"}
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dashboards")
GREEN, YELLOW, RED = "green", "#EAB839", "red"

# cAdvisor also reports pod-level cgroups (container="") and the pause containers: leave them out of sums.
CONTAINERS = 'container!="", container!="POD"'
ROOT = 'mountpoint="/"'
NICS = 'device=~"en.*|wl.*|eth.*|tailscale.*"'


def prom(expr, legend="", ref="A", instant=False):
    t = {"refId": ref, "datasource": PROM, "expr": expr, "legendFormat": legend, "editorMode": "code"}
    t.update({"instant": True, "range": False, "format": "table"} if instant else {"range": True})
    return t


def thresholds(*steps):
    """steps: (value_or_None, color) pairs, the first one is the base."""
    return {"mode": "absolute", "steps": [{"value": v, "color": c} for v, c in steps]}


class Dash:
    def __init__(self, uid, title, tags, refresh="1m", time_from="now-24h"):
        self.uid, self.title, self.tags, self.refresh, self.time_from = uid, title, tags, refresh, time_from
        self.panels, self._x, self._y, self._rowh, self._id = [], 0, 0, 0, 0

    def _place(self, w, h):
        if self._x + w > 24:
            self._x, self._y, self._rowh = 0, self._y + self._rowh, 0
        pos = {"x": self._x, "y": self._y, "w": w, "h": h}
        self._x += w
        self._rowh = max(self._rowh, h)
        return pos

    def add(self, ptype, title, targets, w, h, desc="", options=None, defaults=None, overrides=None):
        self._id += 1
        self.panels.append({
            "id": self._id, "type": ptype, "title": title, "description": desc, "datasource": PROM,
            "targets": targets, "gridPos": self._place(w, h),
            "fieldConfig": {"defaults": defaults or {}, "overrides": overrides or []}, "options": options or {}})

    def stat(self, title, target, w=4, h=4, unit="short", th=None, desc="", decimals=None):
        d = {"unit": unit, "thresholds": th or thresholds((None, GREEN)), "color": {"mode": "thresholds"}}
        if decimals is not None:
            d["decimals"] = decimals
        self.add("stat", title, [target], w, h, desc, defaults=d, options={
            "reduceOptions": {"values": False, "calcs": ["lastNotNull"], "fields": ""},
            "colorMode": "value", "graphMode": "area", "textMode": "auto", "justifyMode": "center"})

    def series(self, title, targets, w=12, h=8, unit="short", stack=False, desc="", minimum=None, maximum=None):
        d = {"unit": unit, "custom": {"drawStyle": "line", "lineWidth": 1, "fillOpacity": 30 if stack else 10,
                                      "showPoints": "never", "spanNulls": False,
                                      "stacking": {"mode": "normal" if stack else "none"}}}
        if minimum is not None:
            d["min"] = minimum
        if maximum is not None:
            d["max"] = maximum
        self.add("timeseries", title, targets, w, h, desc, defaults=d, options={
            "legend": {"displayMode": "list", "placement": "bottom", "showLegend": True},
            "tooltip": {"mode": "multi", "sort": "desc"}})

    def table(self, title, target, w=12, h=8, desc="", hide=(), rename=None, unit_by_col=None):
        overrides = [{"matcher": {"id": "byName", "options": col}, "properties": [{"id": "unit", "value": unit}]}
                     for col, unit in (unit_by_col or {}).items()]
        self.add("table", title, [target], w, h, desc, options={"showHeader": True, "cellHeight": "sm"},
                 defaults={"custom": {"align": "auto", "filterable": True}}, overrides=overrides)
        self.panels[-1]["transformations"] = [{"id": "organize", "options": {
            "excludeByName": {c: True for c in ("Time",) + tuple(hide)}, "renameByName": rename or {}}}]

    def doc(self):
        return {
            "uid": self.uid, "title": self.title, "tags": ["platform"] + self.tags, "timezone": "browser",
            "schemaVersion": 39, "version": 1, "editable": True, "graphTooltip": 1, "refresh": self.refresh,
            "time": {"from": self.time_from, "to": "now"}, "templating": {"list": []},
            "annotations": {"list": []}, "links": [], "panels": self.panels,
        }


def node():
    d = Dash("platform-node", "Node", ["node"])
    pct = thresholds((None, GREEN), (70, YELLOW), (90, RED))

    # ---- at a glance
    d.stat("CPU busy", prom('100 * (1 - avg(rate(node_cpu_seconds_total{mode="idle"}[5m])))'), unit="percent",
           th=pct, decimals=0, desc="Share of the node's 4 cores in use (5-minute average).")
    d.stat("Memory available", prom("node_memory_MemAvailable_bytes"), unit="bytes",
           th=thresholds((None, RED), (1.6e9, YELLOW), (3.2e9, GREEN)),
           desc="Memory the kernel can hand out without swapping. Alert NodeMemoryLow below 10%.")
    d.stat("Root disk used", prom(f"100 * (1 - node_filesystem_avail_bytes{{{ROOT}}} / node_filesystem_size_bytes{{{ROOT}}})"),
           unit="percent", th=pct, decimals=1,
           desc="The root filesystem holds every local-path volume (Prometheus, the projects' databases).")
    d.stat("Root disk full in", prom(
        f"clamp_max(node_filesystem_avail_bytes{{{ROOT}}} / clamp_min(-deriv(node_filesystem_avail_bytes{{{ROOT}}}[6h]), 1e-3), 3.15e8)"),
        unit="s", th=thresholds((None, RED), (86400, YELLOW), (30 * 86400, GREEN)),
        desc="At the rate of the last 6 hours. Shows 10 years when the disk is not filling.")
    d.stat("Prometheus storage", prom(
        "100 * (prometheus_tsdb_storage_blocks_bytes + prometheus_tsdb_wal_storage_size_bytes) / prometheus_tsdb_retention_limit_bytes"),
        unit="percent", th=pct, decimals=0,
        desc="Of its size cap (retentionSize). At the cap the oldest data is deleted; before a year, that fires PrometheusRetentionShortened.")
    d.stat("Up for", prom("time() - node_boot_time_seconds"), unit="s", desc="Since the node last booted.")

    # ---- who uses the node
    d.series("CPU per namespace", [prom(
        f"sum by (namespace) (rate(container_cpu_usage_seconds_total{{{CONTAINERS}}}[5m]))", "{{namespace}}")],
        unit="short", stack=True, minimum=0, desc="Cores used, stacked. The node has 4.")
    d.series("Memory per namespace", [prom(
        f"sum by (namespace) (container_memory_working_set_bytes{{{CONTAINERS}}})", "{{namespace}}")],
        unit="bytes", stack=True, minimum=0, desc="Working set, stacked. The node has about 15 GiB.")

    # ---- the node itself
    d.series("CPU and load", [
        prom('100 * (1 - avg(rate(node_cpu_seconds_total{mode="idle"}[5m])))', "busy %"),
        prom('100 * node_load5 / scalar(count(node_cpu_seconds_total{mode="idle"}))', "load5 per core %", "B")],
        unit="percent", minimum=0, w=8)
    d.series("Memory", [
        prom("node_memory_MemTotal_bytes - node_memory_MemAvailable_bytes", "used"),
        prom("node_memory_MemAvailable_bytes", "available", "B"),
        prom("node_memory_SwapTotal_bytes - node_memory_SwapFree_bytes", "swap used", "C")],
        unit="bytes", minimum=0, w=8)
    d.series("Pressure (time stalled)", [
        prom('rate(node_pressure_cpu_waiting_seconds_total[5m])', "cpu"),
        prom('rate(node_pressure_memory_waiting_seconds_total[5m])', "memory", "B"),
        prom('rate(node_pressure_io_waiting_seconds_total[5m])', "io", "C")],
        unit="percentunit", minimum=0, w=8,
        desc="Share of time some task waited for the resource (Linux PSI). Sustained memory or io stall means the node is overloaded.")
    d.series("Filesystems used", [prom(
        '100 * (1 - node_filesystem_avail_bytes{fstype=~"ext4|xfs|btrfs|vfat"} / node_filesystem_size_bytes{fstype=~"ext4|xfs|btrfs|vfat"})',
        "{{mountpoint}}")], unit="percent", minimum=0, maximum=100, w=8)
    d.series("Disk I/O", [
        prom("sum(rate(node_disk_read_bytes_total[5m]))", "read"),
        prom("sum(rate(node_disk_written_bytes_total[5m]))", "written", "B")], unit="Bps", minimum=0, w=8)
    d.series("Network", [
        prom(f"rate(node_network_receive_bytes_total{{{NICS}}}[5m])", "{{device}} in"),
        prom(f"rate(node_network_transmit_bytes_total{{{NICS}}}[5m])", "{{device}} out", "B")],
        unit="Bps", minimum=0, w=8)

    # ---- capacity and health
    d.stat("CPU requested", prom(
        'sum(kube_pod_container_resource_requests{resource="cpu"}) / sum(kube_node_status_allocatable{resource="cpu"}) * 100'),
        unit="percent", th=pct, decimals=0,
        desc="Sum of the containers' CPU requests against what the node offers. Over 100%, new pods cannot be scheduled.")
    d.stat("Memory requested", prom(
        'sum(kube_pod_container_resource_requests{resource="memory"}) / sum(kube_node_status_allocatable{resource="memory"}) * 100'),
        unit="percent", th=pct, decimals=0, desc="Sum of the containers' memory requests against what the node offers.")
    d.stat("Memory limits", prom(
        'sum(kube_pod_container_resource_limits{resource="memory"}) / sum(kube_node_status_allocatable{resource="memory"}) * 100'),
        unit="percent", th=thresholds((None, GREEN), (100, YELLOW), (150, RED)), decimals=0,
        desc="Sum of the memory limits. Over 100% is overcommitted: if every container used its limit, something would be killed.")
    d.series("Temperature", [prom("node_hwmon_temp_celsius", "{{chip}} {{sensor}}")], unit="celsius", w=12, h=4)

    d.table("Container restarts (24h)", prom(
        "sort_desc(increase(kube_pod_container_status_restarts_total[24h]) > 0)", instant=True), w=8,
        hide=("__name__", "job", "instance", "endpoint", "service", "uid"),
        rename={"Value": "restarts"}, desc="Containers that restarted in the last day.")
    d.table("OOMKilled containers", prom(
        'kube_pod_container_status_last_terminated_reason{reason="OOMKilled"} == 1', instant=True), w=8,
        hide=("__name__", "job", "instance", "endpoint", "service", "uid", "Value", "reason"),
        desc="Containers whose last exit was an out-of-memory kill. Raise the limit or find the leak.")
    d.table("Volumes (requested size)", prom(
        "kube_persistentvolumeclaim_resource_requests_storage_bytes", instant=True), w=8,
        hide=("__name__", "job", "instance", "endpoint", "service", "pod", "container"),
        rename={"Value": "requested"}, unit_by_col={"requested": "bytes"},
        desc="local-path volumes are directories on the root disk: the requested size is not enforced and cannot be changed. Their real usage counts against the root disk above.")

    d.series("Prometheus storage", [
        prom("prometheus_tsdb_storage_blocks_bytes + prometheus_tsdb_wal_storage_size_bytes", "stored"),
        prom("prometheus_tsdb_retention_limit_bytes", "cap", "B")], unit="bytes", minimum=0, w=12, h=6)
    d.series("Prometheus series", [prom("prometheus_tsdb_head_series", "series in the head block")],
             minimum=0, w=12, h=6,
             desc="The series budget is in platform/monitoring/values.yaml. Pod churn makes this higher than the live count.")
    return d


def main():
    check = "--check" in sys.argv[1:]
    stale = []
    for dash in (node(),):
        path = os.path.join(OUT, dash.uid.replace("platform-", "") + ".json")
        text = json.dumps(dash.doc(), indent=2) + "\n"
        if check:
            current = open(path, encoding="utf-8").read() if os.path.exists(path) else ""
            if current != text:
                stale.append(path)
            continue
        os.makedirs(OUT, exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        print("wrote", path, len(dash.panels), "panels")
    if stale:
        print("out of date (run python platform/cluster-health/gen_dashboards.py):", *stale)
        sys.exit(1)


if __name__ == "__main__":
    main()
