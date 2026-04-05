from __future__ import annotations

from pathlib import Path
from agent.orchestrator import Orchestrator


def main():
    project_path = str(Path.cwd())

    orchestrator = Orchestrator(project_path)

    orchestrator.run(
        "Understand the POS system and identify how barcode and stock logic works"
    )


if __name__ == "__main__":
    main()