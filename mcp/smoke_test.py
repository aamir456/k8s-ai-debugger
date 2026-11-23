"""Smoke test for kubernetes-mcp-server running in Docker (stdio transport).

Starts the server exactly as Claude Code does (see .mcp.json), performs the MCP
handshake, lists tools and calls a few of them.

Run:  python mcp\\smoke_test.py
"""
import json
import os
import subprocess
import sys

HOME = os.path.expanduser("~")
HERE = os.path.dirname(os.path.abspath(__file__))
IMAGE = ("quay.io/containers/kubernetes_mcp_server@sha256:"
         "200c1aba3b47b9ab572f61d64f689f63f5abccab3e5e95b4aee34c7411658ad3")

CMD = [
    "docker", "run", "-i", "--rm", "--network", "kind",
    "-v", f"{HOME}\\.kube\\mcp-viewer.docker.kubeconfig:/etc/kubernetes-mcp-server/kubeconfig:ro",
    "-v", f"{HERE}\\config.toml:/etc/kubernetes-mcp-server/config.toml:ro",
    IMAGE, "--config", "/etc/kubernetes-mcp-server/config.toml",
]

proc = subprocess.Popen(CMD, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE, text=True, encoding="utf-8")
_next_id = 0


def rpc(method, params=None, notify=False):
    global _next_id
    msg = {"jsonrpc": "2.0", "method": method, "params": params or {}}
    if not notify:
        _next_id += 1
        msg["id"] = _next_id
    proc.stdin.write(json.dumps(msg) + "\n")
    proc.stdin.flush()
    if notify:
        return None
    while True:
        line = proc.stdout.readline()
        if not line:
            sys.exit("server exited:\n" + proc.stderr.read())
        resp = json.loads(line)
        if resp.get("id") == msg["id"]:
            return resp


def call(tool, **args):
    resp = rpc("tools/call", {"name": tool, "arguments": args})
    if "error" in resp:
        return True, resp["error"].get("message", "")
    res = resp["result"]
    text = "\n".join(c.get("text", "") for c in res.get("content", []))
    return res.get("isError", False), text


init = rpc("initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                          "clientInfo": {"name": "smoke-test", "version": "1"}})
info = init["result"]["serverInfo"]
print(f"Connected: {info['name']} {info.get('version', '')}")
rpc("notifications/initialized", notify=True)

tools = sorted(t["name"] for t in rpc("tools/list")["result"]["tools"])
print(f"\n{len(tools)} tools registered:\n  " + "\n  ".join(tools))

checks = [
    ("pods_list_in_namespace", {"namespace": "demo-app"}),
    ("pods_top", {"namespace": "demo-app"}),
    ("nodes_top", {}),
    ("events_list", {"namespace": "demo-app", "limit": 5}),
    ("resources_get", {"apiVersion": "apps/v1", "kind": "Deployment",
                       "name": "notes-app", "namespace": "demo-app"}),
    ("resources_list", {"apiVersion": "v1", "kind": "Secret", "namespace": "demo-app"}),
    # observability/metrics toolset (Prometheus + Alertmanager, Step 6)
    ("list_metrics", {"name_regex": "http_request.*"}),
    ("execute_instant_query", {"query": 'sum by (pod) (rate(http_requests_total{namespace="demo-app"}[5m]))'}),
    ("execute_instant_query", {"query": 'sum by (pod) (kube_pod_container_status_restarts_total{namespace="demo-app"})'}),
    ("get_alerts", {"active": True}),
]
for tool, args in checks:
    is_err, text = call(tool, **args)
    head = "\n    ".join(text.strip().splitlines()[:6])
    print(f"\n[{'ERROR' if is_err else 'OK'}] {tool} {args}\n    {head}")

proc.stdin.close()
proc.terminate()
