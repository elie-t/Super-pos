from __future__ import annotations


BLOCKED_WORDS = {
    "rm",
    "sudo",
    "shutdown",
    "reboot",
    "mkfs",
    "dd",
    "killall",
}

APPROVAL_WORDS = {
    "git",
    "docker",
    "alembic",
    "drop",
    "truncate",
}


def check_command_policy(command: list[str]) -> tuple[bool, str]:
    if not command:
        return False, "Empty command"

    first = command[0].lower()

    if first in BLOCKED_WORDS:
        return False, f"Blocked command: {first}"

    if first in APPROVAL_WORDS:
        return False, f"Approval required for command: {first}"

    return True, "Allowed"