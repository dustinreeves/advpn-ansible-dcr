#!/usr/bin/env python3
"""Local web UI for selecting ADVPN variables and rendering configs."""

from __future__ import annotations

import json
import subprocess
import tempfile
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import yaml

ROOT = Path(__file__).resolve().parents[1]
GROUP_VARS = ROOT / "group_vars"
HOST_VARS = ROOT / "host_vars"
TEMPLATES_DIR = ROOT / "templates"
WEBUI_DIR = ROOT / "webui"
INVENTORY = ROOT / "inventory.yml"
PLAYBOOK = ROOT / "playbook.yml"

TEMPLATE_ORDER = {
    "hub": [
        ("musthaves.j2", {}),
        ("interfaces.j2", {}),
        ("advpn.j2", {"advpn_render_section": "phase1"}),
        ("advpn.j2", {"advpn_render_section": "allowaccess"}),
        ("advpn.j2", {"advpn_render_section": "phase2"}),
        ("community_lists.j2", {}),
        ("route_maps_hub.j2", {}),
        ("sdwan_hub.j2", {}),
        ("bgp_hub.j2", {}),
        ("hub_interhub_ipsec.j2", {}),
        ("port_allowaccess_reenable.j2", {}),
    ],
    "branch": [
        ("musthaves.j2", {}),
        ("interfaces.j2", {}),
        ("advpn.j2", {"advpn_render_section": "phase1"}),
        ("advpn.j2", {"advpn_render_section": "allowaccess"}),
        ("advpn.j2", {"advpn_render_section": "phase2"}),
        ("route_maps_branch.j2", {}),
        ("sdwan_branch.j2", {}),
        ("bgp_branch.j2", {}),
        ("port_allowaccess_reenable.j2", {}),
    ],
}


def load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text())
    return data if isinstance(data, dict) else {}


def host_roles() -> dict[str, str]:
    inventory = load_yaml(INVENTORY)
    children = inventory.get("all", {}).get("children", {})
    hubs = children.get("hub_devices", {}).get("hosts", {})
    branches = children.get("branch_devices", {}).get("hosts", {})
    mapping = {name: "hub" for name in hubs.keys()}
    mapping.update({name: "branch" for name in branches.keys()})
    return mapping


def templates_payload() -> dict[str, list[dict[str, Any]]]:
    output: dict[str, list[dict[str, Any]]] = {"hub": [], "branch": []}
    for role, items in TEMPLATE_ORDER.items():
        for name, context in items:
            path = TEMPLATES_DIR / name
            if path.exists():
                output[role].append({"name": name, "content": path.read_text(), "context": context})
    return output


class Handler(BaseHTTPRequestHandler):
    def _send_json(self, payload: dict[str, Any], status: int = 200) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path: Path, content_type: str) -> None:
        if not path.exists():
            self.send_error(404)
            return
        data = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/":
            self._send_file(WEBUI_DIR / "index.html", "text/html; charset=utf-8")
            return

        if self.path == "/static/app.css":
            self._send_file(WEBUI_DIR / "app.css", "text/css; charset=utf-8")
            return

        if self.path == "/static/app.js":
            self._send_file(WEBUI_DIR / "app.js", "application/javascript; charset=utf-8")
            return

        if self.path == "/api/hosts":
            hosts = sorted(p.stem for p in HOST_VARS.glob("*.yml"))
            self._send_json({"hosts": hosts, "role_by_host": host_roles()})
            return

        if self.path == "/api/templates":
            self._send_json({"templates_by_role": templates_payload()})
            return

        if self.path.startswith("/api/vars"):
            parsed = urlparse(self.path)
            host = parse_qs(parsed.query).get("host", [""])[0].strip()
            if not host:
                self._send_json({"error": "host query parameter is required"}, status=400)
                return

            host_path = HOST_VARS / f"{host}.yml"
            if not host_path.exists():
                self._send_json({"error": f"host_vars/{host}.yml not found"}, status=404)
                return

            self._send_json(
                {
                    "global_vars": load_yaml(GROUP_VARS / "all.yml"),
                    "host_vars": load_yaml(host_path),
                    "device_role": host_roles().get(host),
                }
            )
            return

        self._send_json({"error": "not found"}, status=404)

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/api/render":
            self._send_json({"error": "not found"}, status=404)
            return

        content_length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(content_length) or "{}")

        host = str(payload.get("host", "")).strip()
        if not host:
            self._send_json({"error": "host is required"}, status=400)
            return

        global_vars = payload.get("global_vars", {})
        host_vars = payload.get("host_vars", {})
        if not isinstance(global_vars, dict) or not isinstance(host_vars, dict):
            self._send_json({"error": "global_vars and host_vars must be objects"}, status=400)
            return

        extra_vars: dict[str, Any] = {}
        extra_vars.update(global_vars)
        extra_vars.update(host_vars)

        with tempfile.TemporaryDirectory() as tmpdir:
            extra_path = Path(tmpdir) / "extra_vars.yml"
            extra_path.write_text(yaml.safe_dump(extra_vars, sort_keys=False))

            cmd = [
                "ansible-playbook",
                "-i",
                str(INVENTORY),
                str(PLAYBOOK),
                "--limit",
                host,
                "-e",
                f"@{extra_path}",
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT)
            if result.returncode != 0:
                self._send_json(
                    {"error": "ansible-playbook failed", "stdout": result.stdout, "stderr": result.stderr},
                    status=500,
                )
                return

        rendered_dir = ROOT / "rendered"
        matches = sorted(rendered_dir.glob(f"{host}-full-*.conf"), key=lambda p: p.stat().st_mtime)
        if not matches:
            self._send_json({"error": "No rendered full config was produced"}, status=500)
            return

        self._send_json({"rendered_config": matches[-1].read_text()})


def main() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 8080), Handler)
    print("Web UI running at http://127.0.0.1:8080")
    server.serve_forever()


if __name__ == "__main__":
    main()
