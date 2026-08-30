#!/usr/bin/env python3
"""Dependency-free frontier provider; stdin/stdout implement flip-filter/1."""

import json
import sys
from pathlib import Path


request = json.load(sys.stdin)
if request.get("protocol") != "flip-filter/1" or request.get("hook") != "frontier.provide@1":
    raise SystemExit("unsupported protocol or hook")

path = Path("worklist.json")
if not path.is_file():
    print(json.dumps({
        "protocol": "flip-filter/1",
        "decline": True,
        "reason": "worklist.json is absent",
    }))
    raise SystemExit(0)

rows = json.loads(path.read_text(encoding="utf-8"))
items = []
for row in rows:
    items.append({
        "lane": "local-worklist",
        "notebook": str(row.get("notebook") or ""),
        "id": str(row["id"]),
        "text": str(row["text"]),
        "why": str(row.get("why") or "checked-in local worklist row"),
    })
print(json.dumps({"protocol": "flip-filter/1", "items": items}))
