from __future__ import annotations

from pathlib import Path


def _resolve_target(project_path: str, relative_path: str) -> Path:
    root = Path(project_path).resolve()
    target = (root / relative_path).resolve()

    if root not in target.parents and target != root:
        raise ValueError("Invalid path: outside project directory")

    return target


def write_file(project_path: str, relative_path: str, content: str) -> None:
    target = _resolve_target(project_path, relative_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


def replace_in_file(
    project_path: str,
    relative_path: str,
    old_text: str,
    new_text: str,
    count: int = 1,
) -> bool:
    target = _resolve_target(project_path, relative_path)

    if not target.exists():
        raise FileNotFoundError(f"File not found: {relative_path}")

    content = target.read_text(encoding="utf-8")

    if old_text not in content:
        return False

    updated = content.replace(old_text, new_text, count)
    target.write_text(updated, encoding="utf-8")
    return True


def append_to_file(project_path: str, relative_path: str, text: str) -> None:
    target = _resolve_target(project_path, relative_path)
    target.parent.mkdir(parents=True, exist_ok=True)

    existing = ""
    if target.exists():
        existing = target.read_text(encoding="utf-8")

    target.write_text(existing + text, encoding="utf-8")