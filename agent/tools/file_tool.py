from __future__ import annotations

from pathlib import Path


IGNORED_DIRS = {
    ".git",
    "node_modules",
    "dist",
    "build",
    ".next",
    "venv",
    ".venv",
    "__pycache__",
    ".idea",
    ".pytest_cache",
}


def list_files(project_path: str, max_files: int = 200) -> list[str]:
    root = Path(project_path)
    results: list[str] = []

    for path in root.rglob("*"):
        if any(part in IGNORED_DIRS for part in path.parts):
            continue
        if path.is_file():
            results.append(str(path.relative_to(root)))
        if len(results) >= max_files:
            break

    return sorted(results)


def read_file(project_path: str, relative_path: str) -> str:
    root = Path(project_path).resolve()
    target = (root / relative_path).resolve()

    if root not in target.parents and target != root:
        raise ValueError("Invalid path: outside project directory")

    if not target.exists():
        raise FileNotFoundError(f"File not found: {relative_path}")

    return target.read_text(encoding="utf-8")


def read_file_slice(project_path: str, relative_path: str, start_line: int, end_line: int) -> str:
    root = Path(project_path).resolve()
    target = (root / relative_path).resolve()

    if root not in target.parents and target != root:
        raise ValueError("Invalid path: outside project directory")

    if not target.exists():
        raise FileNotFoundError(f"File not found: {relative_path}")

    lines = target.read_text(encoding="utf-8").splitlines()

    start_idx = max(0, start_line - 1)
    end_idx = min(len(lines), end_line)

    output = []
    for i in range(start_idx, end_idx):
        output.append(f"{i + 1}: {lines[i]}")

    return "\n".join(output)