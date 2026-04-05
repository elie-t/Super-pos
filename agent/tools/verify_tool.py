from __future__ import annotations

from dataclasses import dataclass

from agent.tools.terminal_tool import run_command


@dataclass
class VerifyResult:
    ok: bool
    command: str
    stdout: str
    stderr: str
    exit_code: int


def verify_project(project_path: str) -> VerifyResult:
    commands_to_try = [
        ["python", "--version"],
    ]

    last_result = None

    for cmd in commands_to_try:
        result = run_command(cmd, cwd=project_path, timeout=30)
        last_result = result

        if result.exit_code == 0:
            return VerifyResult(
                ok=True,
                command=result.command,
                stdout=result.stdout,
                stderr=result.stderr,
                exit_code=result.exit_code,
            )

    return VerifyResult(
        ok=False,
        command=last_result.command if last_result else "",
        stdout=last_result.stdout if last_result else "",
        stderr=last_result.stderr if last_result else "",
        exit_code=last_result.exit_code if last_result else 1,
    )