#!/usr/bin/env python3
"""Create a new spoke host_vars file and update inventory/site identifiers."""

from __future__ import annotations

import argparse
from copy import deepcopy
from pathlib import Path
import re
import sys

try:
    import yaml
except ModuleNotFoundError:
    print("Error: PyYAML is required. Install with: pip install pyyaml", file=sys.stderr)
    sys.exit(1)


def load_yaml(path: Path):
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def dump_yaml(path: Path, data) -> None:
    with path.open("w", encoding="utf-8") as fh:
        yaml.safe_dump(data, fh, default_flow_style=False, sort_keys=False)


def insert_site_identifier(all_yml_path: Path, site_slug: str, site_id: int) -> None:
    lines = all_yml_path.read_text(encoding="utf-8").splitlines()
    start = None
    for idx, line in enumerate(lines):
        if re.match(r"^\s{2}site_identifiers:\s*$", line):
            start = idx
            break
    if start is None:
        raise RuntimeError("Could not find 'advpn.site_identifiers' block in group_vars/all.yml")

    item_indent = " " * 4
    end = start + 1
    while end < len(lines):
        line = lines[end]
        if line.strip() == "":
            end += 1
            continue
        leading = len(line) - len(line.lstrip(" "))
        if leading <= 2:
            break
        end += 1

    existing = {}
    item_re = re.compile(r"^\s{4}([a-zA-Z0-9_-]+):\s*(\d+)\s*$")
    for i in range(start + 1, end):
        m = item_re.match(lines[i])
        if m:
            existing[m.group(1)] = int(m.group(2))

    if site_slug in existing:
        raise RuntimeError(f"site_identifiers already contains '{site_slug}'")
    if site_id in existing.values():
        raise RuntimeError(f"site_identifiers already uses id '{site_id}'")

    new_line = f"{item_indent}{site_slug}: {site_id}"
    insert_at = end
    for i in range(start + 1, end):
        m = item_re.match(lines[i])
        if m and site_slug < m.group(1):
            insert_at = i
            break

    lines.insert(insert_at, new_line)
    all_yml_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Add a new spoke and update host_vars/inventory/site identifiers.")
    parser.add_argument("--name", required=True, help="Inventory hostname / site slug (example: miami)")
    parser.add_argument("--ansible-host", required=True, help="Management IP/FQDN to place in inventory.yml")
    parser.add_argument("--site-id", type=int, required=True, help="Unique site identifier for advpn.site_identifiers")
    parser.add_argument("--template", default="phoenix", help="Existing host_vars template name (default: phoenix)")
    parser.add_argument("--site-name", help="Friendly site name (default: '<name>')")
    parser.add_argument("--fgt-hostname", help="FortiGate hostname (default: next BranchNN)")
    parser.add_argument("--lo-bgp-ip", help="Loopback BGP IPv4 address (without mask), e.g. 10.250.0.31")
    parser.add_argument("--lo-hc-ip", help="Loopback health-check IPv4 address (without mask), e.g. 10.250.1.31")
    parser.add_argument("--force", action="store_true", help="Overwrite host_vars/<name>.yml if it exists")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    host_vars_dir = repo_root / "host_vars"
    inventory_path = repo_root / "inventory.yml"
    all_yml_path = repo_root / "group_vars" / "all.yml"

    site_slug = args.name.strip().lower()
    host_vars_path = host_vars_dir / f"{site_slug}.yml"
    if host_vars_path.exists() and not args.force:
        raise SystemExit(f"Error: {host_vars_path} already exists (use --force to overwrite)")

    template_path = host_vars_dir / f"{args.template}.yml"
    if not template_path.exists():
        raise SystemExit(f"Error: template not found: {template_path}")

    template_data = load_yaml(template_path)
    new_data = deepcopy(template_data)
    new_data["site_slug"] = site_slug
    new_data["site_name"] = args.site_name or site_slug
    new_data["fgt_hostname"] = args.fgt_hostname or site_slug

    if args.lo_bgp_ip:
        new_data.setdefault("lo_bgp", {})["ip"] = f"{args.lo_bgp_ip} 255.255.255.255"
    if args.lo_hc_ip:
        new_data.setdefault("lo_hc", {})["ip"] = f"{args.lo_hc_ip} 255.255.255.255"

    dump_yaml(host_vars_path, new_data)

    inventory_data = load_yaml(inventory_path)
    hosts = (
        inventory_data.setdefault("all", {})
        .setdefault("children", {})
        .setdefault("branch_devices", {})
        .setdefault("hosts", {})
    )
    if site_slug in hosts:
        raise SystemExit(f"Error: inventory already has branch host '{site_slug}'")
    hosts[site_slug] = {"ansible_host": args.ansible_host}
    dump_yaml(inventory_path, inventory_data)

    insert_site_identifier(all_yml_path, site_slug, args.site_id)

    print("Created/updated:")
    print(f"- {host_vars_path}")
    print(f"- {inventory_path}")
    print(f"- {all_yml_path} (advpn.site_identifiers)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
