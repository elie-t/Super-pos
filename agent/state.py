from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


@dataclass
class PlanStep:
    id: int
    description: str
    status: str = "pending"


@dataclass
class AgentState:
    objective: str
    project_path: str
    steps: List[PlanStep] = field(default_factory=list)
    current_step_id: int | None = None
    files_touched: List[str] = field(default_factory=list)
    command_history: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)

    def add_step(self, description: str) -> None:
        step_id = len(self.steps) + 1
        self.steps.append(PlanStep(id=step_id, description=description))

    def set_current_step(self, step_id: int) -> None:
        self.current_step_id = step_id
        for step in self.steps:
            if step.id == step_id and step.status == "pending":
                step.status = "in_progress"

    def mark_step_done(self, step_id: int) -> None:
        for step in self.steps:
            if step.id == step_id:
                step.status = "done"
                break

    def mark_step_failed(self, step_id: int) -> None:
        for step in self.steps:
            if step.id == step_id:
                step.status = "failed"
                break

    def add_touched_file(self, path: str) -> None:
        if path not in self.files_touched:
            self.files_touched.append(path)

    def add_command(self, command: str) -> None:
        self.command_history.append(command)

    def add_note(self, note: str) -> None:
        self.notes.append(note)

    def summary(self) -> str:
        lines = [
            f"Objective: {self.objective}",
            f"Project path: {self.project_path}",
            "",
            "Plan:",
        ]

        for step in self.steps:
            marker = f"[{step.status}]"
            lines.append(f"{marker} Step {step.id}: {step.description}")

        if self.files_touched:
            lines.append("")
            lines.append("Files touched:")
            for path in self.files_touched:
                lines.append(f"- {path}")

        if self.command_history:
            lines.append("")
            lines.append("Commands run:")
            for cmd in self.command_history:
                lines.append(f"- {cmd}")

        if self.notes:
            lines.append("")
            lines.append("Notes:")
            for note in self.notes:
                lines.append(f"- {note}")

        return "\n".join(lines)