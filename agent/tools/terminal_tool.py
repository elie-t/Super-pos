from __future__ import annotations

import subprocess
from dataclasses import dataclass


@dataclass
class CommandResult:
    command: str
    exit_code: int
    stdout: str
    stderr: str


def run_command(
    command: list[str],
    cwd: str,
    timeout: int = 60,
) -> CommandResult:
    result = subprocess.run(
        command,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=timeout,
    )

    return CommandResult(
        command=" ".join(command),
        exit_code=result.returncode,
        stdout=result.stdout,
        stderr=result.stderr,
    )