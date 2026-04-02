#!/usr/bin/env python3
"""Interactive wizard to create host_vars files from an existing template."""

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


def prompt(msg: str, default: str | None = None) -> str:
    suffix = f" [{default}]" if default not in (None, "") else ""
    value = input(f"{msg}{suffix}: ").strip()
    if value == "" and default is not None:
        return str(default)
    return value


def auto_cast(value: str, example):
    if isinstance(example, bool):
        lowered = value.lower()
        return lowered in {"1", "true", "yes", "y", "on", "enable"}
    if isinstance(example, int) and re.fullmatch(r"-?\d+", value):
        return int(value)
    if isinstance(example, float):
        try:
            return float(value)
        except ValueError:
            return value
    return value


def walk_and_prompt(node, path: str = ""):
    if isinstance(node, dict):
        updated = {}
        for key, value in node.items():
            key_path = f"{path}.{key}" if path else key
            updated[key] = walk_and_prompt(value, key_path)
        return updated

    if isinstance(node, list):
        updated = []
        for idx, value in enumerate(node):
            item_path = f"{path}[{idx}]"
            updated.append(walk_and_prompt(value, item_path))
        return updated

    new_value = prompt(path, str(node) if node is not None else "")
    return auto_cast(new_value, node)


def choose_template(host_vars_dir: Path, requested_template: str | None) -> Path:
    if requested_template:
        template_file = host_vars_dir / f"{requested_template}.yml"
        if not template_file.exists():
            print(f"Template file not found: {template_file}", file=sys.stderr)
            sys.exit(1)
        return template_file

    candidates = sorted(host_vars_dir.glob("*.yml"))
    if not candidates:
        print("No templates found in host_vars/.", file=sys.stderr)
        sys.exit(1)

    print("Available templates:")
    for idx, file_path in enumerate(candidates, start=1):
        print(f"  {idx}. {file_path.stem}")

    selection = prompt("Pick template number", "1")
    try:
        choice = int(selection)
        return candidates[choice - 1]
    except (ValueError, IndexError):
        print("Invalid selection.", file=sys.stderr)
        sys.exit(1)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Create a new host_vars YAML file by prompting for every variable "
            "from an existing host_vars template."
        )
    )
    parser.add_argument(
        "--template",
        help="Template host_vars name (without .yml), e.g. dallas or phoenix.",
    )
    parser.add_argument(
        "--output",
        help="Output host name (without .yml). If omitted, you'll be prompted.",
    )
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    host_vars_dir = repo_root / "host_vars"

    template_file = choose_template(host_vars_dir, args.template)

    with template_file.open("r", encoding="utf-8") as fh:
        template_data = yaml.safe_load(fh) or {}

    print(f"\nUsing template: {template_file.name}")
    print("Press Enter to accept a default shown in [brackets].\n")

    new_data = walk_and_prompt(deepcopy(template_data))

    output_name = args.output or prompt("Output host_vars filename (without .yml)")
    output_file = host_vars_dir / f"{output_name}.yml"

    with output_file.open("w", encoding="utf-8") as fh:
        yaml.safe_dump(new_data, fh, default_flow_style=False, sort_keys=False)

    print(f"\nWrote: {output_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
