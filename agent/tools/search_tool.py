from __future__ import annotations

import subprocess

def search_regex(project_path: str, pattern: str, max_results: int = 20) -> str:
    cmd = [
        "rg",
        "-n",
        "--hidden",
        "--glob",
        "!.git",
        "--glob",
        "!node_modules",
        "--glob",
        "!dist",
        "--glob",
        "!build",
        "--glob",
        "!.venv",
        "--glob",
        "!venv",
        pattern,
        project_path,
    ]

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=20,
    )

    if result.returncode not in (0, 1):
        raise RuntimeError(result.stderr.strip() or "regex search failed")

    lines = result.stdout.splitlines()
    return "\n".join(lines[:max_results])
def search_text(project_path: str, query: str, max_results: int = 50) -> str:
    cmd = [
        "rg",
        "-n",
        "--hidden",
        "--glob",
        "!.git",
        "--glob",
        "!node_modules",
        "--glob",
        "!dist",
        "--glob",
        "!build",
        "--glob",
        "!.venv",
        "--glob",
        "!venv",
        query,
        project_path,
    ]

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=20,
    )

    if result.returncode not in (0, 1):
        raise RuntimeError(result.stderr.strip() or "search failed")

    lines = result.stdout.splitlines()
    return "\n".join(lines[:max_results])

def search_exact_symbol(project_path: str, symbol: str, max_results: int = 20) -> str:
    cmd = [
        "rg",
        "-n",
        "--hidden",
        "--glob",
        "!.git",
        "--glob",
        "!node_modules",
        "--glob",
        "!dist",
        "--glob",
        "!build",
        "--glob",
        "!.venv",
        "--glob",
        "!venv",
        "-F",
        symbol,
        project_path,
    ]

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=20,
    )

    if result.returncode not in (0, 1):
        raise RuntimeError(result.stderr.strip() or "exact symbol search failed")

    lines = result.stdout.splitlines()
    return "\n".join(lines[:max_results])