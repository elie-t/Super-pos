from __future__ import annotations

import json
from agent.ollama_client import OllamaClient


def _clean_json_text(text: str) -> str:
    text = text.strip()

    if text.startswith("```"):
        lines = text.splitlines()

        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]

        text = "\n".join(lines).strip()

    if text.lower().startswith("json"):
        text = text[4:].strip()

    return text


class Planner:
    def __init__(self, model: str = "gemma3:4b"):
        self.client = OllamaClient(model=model)

    def create_plan(self, objective: str) -> list[str]:
        prompt = f"""
You are a coding agent planner.

Objective:
{objective}

Return exactly 5 short steps as a JSON array.

No markdown. No explanations.

Example:
["Inspect files", "Search barcode logic", "Read stock service", "Trace flow", "Summarize"]
"""
        result = self.client.chat(prompt, timeout=300)
        cleaned = _clean_json_text(result)

        try:
            data = json.loads(cleaned)
            if isinstance(data, list):
                return [str(x).strip() for x in data if str(x).strip()]
        except Exception:
            pass

        return [
            "Inspect project structure",
            "Search barcode-related code",
            "Read stock-related files",
            "Trace invoice flow",
            "Summarize findings",
        ]

    def decide_next_action(self, state_summary: str) -> dict:
        prompt = f"""
You are a coding agent deciding the next action.

State:
{state_summary}

Return ONLY JSON.

Actions:
list_files, search_text, read_file, run_command, done

Rules:
- Do not repeat list_files if already done
- Progress step by step
"""

        result = self.client.chat(prompt, timeout=300)
        cleaned = _clean_json_text(result)

        try:
            data = json.loads(cleaned)
            if isinstance(data, dict) and "action" in data:
                return data
        except Exception:
            pass

        # fallback logic (VERY IMPORTANT)
        if "Found " not in state_summary:
            return {"action": "list_files", "input": {}}

        if "Search results:" not in state_summary:
            return {"action": "search_text", "input": {"query": "barcode|stock|invoice|pos"}}

        if "Read file:" not in state_summary:
            return {"action": "read_file", "input": {"path": "main.py"}}

        if "Commands run:" not in state_summary:
            return {"action": "run_command", "input": {"command": ["python", "--version"]}}

        return {"action": "done", "input": {}}