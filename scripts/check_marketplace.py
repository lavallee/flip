#!/usr/bin/env python3
"""Require the flip plugin in both Claude and Codex marketplace catalogs."""

from __future__ import annotations

import argparse
import json
import urllib.request
from pathlib import Path


CATALOGS = (
    ".claude-plugin/marketplace.json",
    ".agents/plugins/marketplace.json",
)


def load_catalog(source: str, relative: str) -> dict:
    if source.startswith(("http://", "https://")):
        url = f"{source.rstrip('/')}/{relative}"
        request = urllib.request.Request(url, headers={"User-Agent": "flip-release-check"})
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                return json.load(response)
        except Exception as exc:  # urllib exposes several unrelated failure types
            raise SystemExit(f"could not read {url}: {exc}") from exc
    path = Path(source).expanduser().resolve() / relative
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SystemExit(f"could not read {path}: {exc}") from exc


def check(source: str) -> None:
    failures = []
    for relative in CATALOGS:
        payload = load_catalog(source, relative)
        plugins = payload.get("plugins")
        if not isinstance(plugins, list):
            failures.append(f"{relative}: missing plugins list")
            continue
        matches = [row for row in plugins if isinstance(row, dict) and row.get("name") == "flip"]
        if len(matches) != 1:
            failures.append(f"{relative}: expected one flip entry, found {len(matches)}")
            continue
        if "lavallee/flip" not in json.dumps(matches[0]):
            failures.append(f"{relative}: flip entry does not point to lavallee/flip")
    if failures:
        raise SystemExit("marketplace check failed:\n" + "\n".join(failures))
    print(f"marketplace check passed: {source}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "source",
        nargs="?",
        default="https://raw.githubusercontent.com/lyra-forge/marketplace/main",
        help="marketplace checkout or raw-content base URL",
    )
    args = parser.parse_args()
    check(args.source)


if __name__ == "__main__":
    main()
