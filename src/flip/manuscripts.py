"""Save numbered manuscripts without overwriting earlier reporting."""
import hashlib
import json
import os
import re
import tempfile
from pathlib import Path

from . import events, manifest, pages, revisions, util

VERSION = re.compile(r"v(?:0|[1-9]\d*)$")


def versions(root):
    result = []
    directory = root / "drafts"
    if not directory.is_dir():
        return result
    for child in directory.iterdir():
        if not VERSION.fullmatch(child.name) or not child.is_dir() or child.is_symlink():
            continue
        files = sorted(path for path in child.glob("*.md") if path.name != "changelog.md"
                       and path.is_file() and not path.is_symlink())
        if not files:
            continue
        path = next((path for path in files if path.name == "draft.md"), files[0])
        stat = path.stat()
        row = {"version": child.name, "path": path.relative_to(root).as_posix(),
               "fingerprint": f"{stat.st_mtime_ns}-{stat.st_size}"}
        receipt = child / "revision.json"
        if receipt.is_file() and not receipt.is_symlink():
            try:
                data = json.loads(receipt.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                data = {}
            if (child / "saved.txt").is_file() and not (child / "saved.txt").is_symlink():
                row["saved_path"] = (child / "saved.txt").relative_to(root).as_posix()
            if isinstance(data, dict):
                row.update({k: data[k] for k in ("sha256", "at", "by", "because", "evidence") if k in data})
        elif (child / "changelog.md").is_file() and not (child / "changelog.md").is_symlink():
            with (child / "changelog.md").open(encoding="utf-8") as stream:
                row["because"] = stream.read(2000).strip()
        result.append(row)
    return sorted(result, key=lambda v: int(v["version"][1:]))


def save(root: Path, text: str, because: str, expected: str | None = None, from_sha: str | None = None):
    root = util.require_notebook_root(root)
    if not text.strip() or not because.strip():
        raise SystemExit("supply the manuscript and a reason for this version")
    directory = root / "drafts"
    if directory.is_symlink():
        raise SystemExit("the drafts directory is a symlink; save inside the notebook")
    directory.mkdir(exist_ok=True)
    digest = hashlib.sha256(text.encode()).hexdigest()
    with pages._ids_lock(root, filename="draft-save.lock", operation="saving a draft version"):
        current = directory / "current"
        if os.path.lexists(current) and not current.is_symlink():
            raise SystemExit("drafts/current is not a symlink; its contents have been preserved")
        saved = versions(root)
        last = saved[-1] if saved else None
        base = last["version"] if last else "none"
        if last and last.get("sha256") == digest and (root / last["path"]).read_bytes() == text.encode():
            recorded_base = json.loads((directory / base / "revision.json").read_text()).get("base")
            if expected not in (None, base, recorded_base):
                raise SystemExit(f"draft history is at {base}; review it before saving from {expected}")
            # Recover a committed version after an interruption before pointer promotion.
            if not current.is_symlink() or os.readlink(current) == recorded_base:
                _activate(directory, base)
            return base
        if expected is not None and expected != base:
            raise SystemExit(f"draft history is at {base}; review it before saving from {expected}")
        if from_sha:
            active = next((v for v in saved if current.is_symlink() and
                           (directory / v["version"]).resolve() == current.resolve()), last)
            if active:
                previous_text = (root / active["path"]).read_bytes()
            else:
                flat = sorted(p for p in directory.glob("*.md") if p.name not in
                              ("question-plan.md", "changelog.md") and not p.is_symlink())
                previous_text = flat[-1].read_bytes() if flat else b""
            if hashlib.sha256(previous_text).hexdigest() != from_sha:
                raise SystemExit("the working manuscript changed; read it before saving")
        highest = max((int(p.name[1:]) for p in directory.iterdir() if VERSION.fullmatch(p.name)), default=0)
        version = f"v{highest + 1}"
        receipt = {"version": version, "base": base, "sha256": digest, "at": util.utc_now(),
                   "by": util.detect_actor(), "because": because.strip(),
                   "evidence": revisions.evidence_at_save(root, text)}
        with tempfile.TemporaryDirectory(dir=directory, prefix=".draft-") as scratch:
            stage = Path(scratch) / version
            stage.mkdir()
            (stage / "draft.md").write_bytes(text.encode())
            (stage / "saved.txt").write_bytes(text.encode())
            (stage / "revision.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            (stage / "changelog.md").write_text(because.strip() + "\n", encoding="utf-8")
            stage.rename(directory / version)
        _activate(directory, version)
        manifest.touch_updated(root)
        events.emit(root, "draft.save", version=version, sha256=digest, because=because.strip())
        return version


def _activate(directory, version):
    with tempfile.TemporaryDirectory(dir=directory, prefix=".current-") as scratch:
        link = Path(scratch) / "current"
        link.symlink_to(version, target_is_directory=True)
        os.replace(link, directory / "current")
