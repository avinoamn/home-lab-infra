#!/usr/bin/env python3
"""Runs every Prometheus query of the platform's dashboards (platform/cluster-health/dashboards/*.json) against the
live Prometheus, through Grafana's anonymous datasource proxy, and reports errors and empty results. Read-only.

    GRAFANA_URL=http://<node>:30004 python scripts/verify-dashboards.py [dashboard.json ...]

Exit code 1 if a query fails or returns nothing. Run it after changing a dashboard or the series kept by
platform/monitoring/values.yaml: a dropped metric shows up here as an empty panel. Stdlib only.
"""
import glob
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

URL = os.environ.get("GRAFANA_URL", "").rstrip("/")
if not URL:
    sys.exit("set GRAFANA_URL, e.g. http://<node>:30004")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Panels that are empty when all is well (nothing restarted, nothing was killed).
MAY_BE_EMPTY = {"Container restarts (24h)", "OOMKilled containers"}
files = sys.argv[1:] or sorted(glob.glob(os.path.join(ROOT, "platform", "cluster-health", "dashboards", "*.json")))


def query(expr):
    url = URL + "/api/datasources/proxy/uid/prometheus/api/v1/query?" + urllib.parse.urlencode({"query": expr})
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            body = json.load(r)
    except urllib.error.HTTPError as e:
        try:
            body = json.load(e)
        except ValueError:
            return "error", "HTTP %s" % e.code
    if body.get("status") != "success":
        return "error", body.get("error", "unknown error")
    return "ok", len(body["data"]["result"])


bad = 0
for path in files:
    dash = json.load(open(path, encoding="utf-8"))
    print("==", dash["title"])
    for panel in dash["panels"]:
        for t in panel.get("targets", []):
            # Range-vector placeholders that Grafana would fill in.
            expr = t["expr"].replace("$__rate_interval", "5m").replace("$__range", "24h")
            status, detail = query(expr)
            if status == "error":
                bad += 1
                print("  ERROR    %-32s %s" % (panel["title"], detail))
            elif detail == 0 and panel["title"] in MAY_BE_EMPTY:
                print("  empty    %s (fine: empty when all is well)" % panel["title"])
            elif detail == 0:
                bad += 1
                print("  NO DATA  %-32s %s" % (panel["title"], expr))
            else:
                print("  ok %4d  %s" % (detail, panel["title"]))
sys.exit(1 if bad else 0)
