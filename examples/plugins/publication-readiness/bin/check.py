#!/usr/bin/env python3
"""Example read-only domain check over a notebook root."""

import json
import sys
from pathlib import Path


request = json.load(sys.stdin)
root = Path(request["input"]["scope"]["root"])
findings = []
if not (root / "disclosure.md").is_file():
    findings.append({
        "level": "WARN",
        "code": "missing-disclosure",
        "message": "publication workflow expects disclosure.md",
        "path": "disclosure.md",
    })
print(json.dumps({"protocol": "flip-filter/1", "findings": findings}))
