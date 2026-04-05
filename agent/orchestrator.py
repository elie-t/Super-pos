from __future__ import annotations

import json
import os
from agent.tools.search_tool import search_text, search_exact_symbol
from agent.ollama_client import OllamaClient
from agent.planner import Planner
from agent.state import AgentState
from agent.tools.edit_tool import replace_in_file, write_file
from agent.tools.file_tool import list_files, read_file
from agent.tools.search_tool import search_text
from agent.tools.terminal_tool import run_command
from agent.tools.file_tool import list_files, read_file, read_file_slice
from agent.tools.search_tool import search_text, search_exact_symbol, search_regex

class Orchestrator:
    def __init__(self, project_path: str):
        self.project_path = project_path
        self.planner = Planner()
        self.report_client = OllamaClient(model="gemma3:4b")

    def _rel(self, path: str) -> str:
        if path.startswith(self.project_path):
            return os.path.relpath(path, self.project_path)
        return path

    def _extract_candidate_files(self, search_output: str, limit: int = 4) -> list[str]:
        found: list[str] = []
        seen: set[str] = set()

        for line in search_output.splitlines():
            if not line.strip():
                continue

            parts = line.split(":", 2)
            if len(parts) < 2:
                continue

            path = parts[0].strip()
            rel_path = self._rel(path)

            if rel_path.startswith("agent/"):
                continue

            if not path.endswith((".py", ".js", ".ts", ".tsx", ".jsx")):
                continue

            if path not in seen:
                seen.add(path)
                found.append(path)

            if len(found) >= limit:
                break

        return found



    def _extract_symbol_locations(self, search_output: str, limit: int = 6) -> list[tuple[str, int]]:
        found: list[tuple[str, int]] = []
        seen: set[tuple[str, int]] = set()

        for line in search_output.splitlines():
            if not line.strip():
                continue
            if line.startswith("Symbol:"):
                continue

            parts = line.split(":", 2)
            if len(parts) < 3:
                continue

            path = parts[0].strip()
            rel_path = self._rel(path)

            if rel_path.startswith("agent/") or rel_path.startswith("agent_output/"):
                continue
            if not rel_path.endswith(".py"):
                continue

            try:
                lineno = int(parts[1])
            except ValueError:
                continue

            key = (path, lineno)
            if key not in seen:
                seen.add(key)
                found.append(key)

            if len(found) >= limit:
                break

        return found







    def _generate_report(self, state: AgentState) -> str:
        prompt = f"""
You are a careful coding agent summarizer.

Write a markdown inspection report using ONLY the evidence in the state below.

Strict rules:
- Do not claim anything unless supported by the state
- If something is a guess, put it under Inferences
- If something was not observed, put it under Unknowns
- Do not repeat sections
- Use each heading exactly once
- Mention only files actually read or clearly present in search results

Required structure exactly:

# Inspection Report

## Project Type
## Files Actually Inspected
## Observed Findings
## Inferences
## Unknowns
## Next Inspection Steps

State:
{state.summary()}
"""
        return self.report_client.chat(prompt, timeout=120)

    def _generate_patch(self, state: AgentState) -> dict:
        prompt = f"""
You are a coding agent.

Based ONLY on the inspected evidence below, suggest one very small safe improvement.

Strict rules:
- Return ONLY valid JSON
- No markdown
- No explanations
- Modify only one file
- The original_snippet MUST be copied exactly from an observed file preview in the state
- Keep the patch tiny
- If you are not confident, return {{}}

Format:
{{
  "path": "services/pos_service.py",
  "original_snippet": "exact text copied from file preview",
  "replacement_snippet": "new code"
}}

State:
{state.summary()}
"""
        result = self.report_client.chat(prompt, timeout=120).strip()

        if result.startswith("```"):
            lines = result.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            result = "\n".join(lines).strip()

        try:
            data = json.loads(result)
            if isinstance(data, dict):
                return data
        except Exception:
            pass

        return {}

    def run(self, objective: str) -> None:
        state = AgentState(objective=objective, project_path=self.project_path)

        steps = self.planner.create_plan(objective)
        for step in steps:
            state.add_step(step)

        print("\n=== PLAN ===")
        for step in state.steps:
            print("-", step.description)

        files_listed = False
        search_done = False
        files_read_done = False
        command_run = False

        last_search_results = ""
        candidate_files: list[str] = []
        symbol_locations: list[tuple[str, int]] = []

        for _ in range(10):
            summary = state.summary()
            decision = self.planner.decide_next_action(summary)

            action = decision.get("action")
            input_data = decision.get("input", {})

            if not files_listed:
                action = "list_files"
                input_data = {}
            elif not search_done:
                action = "search_text"
                input_data = {
                    "query": "barcode|ItemBarcode|save_sale|save.*sale|stockmovement|itemstock|pos_service"
                }
            elif not files_read_done:
                action = "read_file"

                if symbol_locations:
                    input_data = {}
                else:
                    if not candidate_files:
                        candidate_files = self._extract_candidate_files(
                            last_search_results,
                            limit=4,
                        )

                    if candidate_files:
                        input_data = {"path": candidate_files.pop(0)}
                    else:
                        input_data = {"path": "main.py"}
            elif not command_run:
                action = "run_command"
                input_data = {"command": ["python", "--version"]}
            else:
                action = "done"
                input_data = {}

            print(f"\n>>> ACTION: {action}")

            if action == "list_files":
                files = list_files(self.project_path, 100)
                preview = "\n".join(files[:30])

                state.add_note(f"Found {len(files)} files")
                state.add_note(f"File sample:\n{preview}")
                files_listed = True

                if state.steps and state.steps[0].status == "pending":
                    state.mark_step_done(1)

            elif action == "search_text":
                query = input_data.get(
                    "query",
                    "barcode|ItemBarcode|save_sale|save.*sale|stockmovement|itemstock|pos_service",
                )

                symbol_queries = [
                    ("class PosService", r"^\s*class PosService:"),
                    ("def save_sale", r"^\s*def save_sale\("),
                    ("def _reverse_stock", r"^\s*def _reverse_stock\("),
                    ("class ItemService", r"^\s*class ItemService:"),
                    ("def search_items", r"^\s*def search_items\("),
                ]

                symbol_hits = []
                for label, pattern in symbol_queries:
                    hit = search_regex(self.project_path, pattern, 10)
                    if hit:
                        symbol_hits.append(f"Symbol: {label}\n{hit}")

                last_search_results = "\n\n".join(symbol_hits)

                if not last_search_results:
                    result = search_text(self.project_path, query, 50)
                    last_search_results = result or ""

                candidate_files = self._extract_candidate_files(
                    last_search_results,
                    limit=4,
                )
                symbol_locations = self._extract_symbol_locations(
                    last_search_results,
                    limit=6,
                )

                state.add_note(f"Search query: {query}")
                state.add_note(
                    "Search results:\n"
                    f"{last_search_results[:2500] if last_search_results else 'No matches'}"
                )
                state.add_note(f"Candidate files: {candidate_files}")
                state.add_note(f"Symbol locations: {symbol_locations}")
                search_done = True

                if len(state.steps) >= 2 and state.steps[1].status == "pending":
                    state.mark_step_done(2)

            elif action == "read_file":
                if symbol_locations:
                    path, lineno = symbol_locations.pop(0)
                    try:
                        snippet = read_file_slice(
                            self.project_path,
                            self._rel(path),
                            max(1, lineno - 20),
                            lineno + 40,
                        )
                        state.add_note(
                            f"Read symbol slice: {self._rel(path)} around line {lineno}"
                        )
                        state.add_note(f"Slice preview:\n{snippet[:2500]}")
                        state.add_touched_file(self._rel(path))
                        candidate_files = []
                    except Exception as e:
                        state.add_note(f"Failed to read slice {path}:{lineno}: {e}")
                else:
                    path = input_data.get("path")
                    if path:
                        try:
                            content = read_file(self.project_path, path)
                            state.add_note(f"Read file: {path}")
                            state.add_note(f"File preview:\n{content[:1800]}")
                            state.add_touched_file(self._rel(path))
                        except Exception as e:
                            state.add_note(f"Failed to read file {path}: {e}")

                if not symbol_locations:
                    files_read_done = True
                    if len(state.steps) >= 3 and state.steps[2].status == "pending":
                        state.mark_step_done(3)

            elif action == "run_command":
                cmd = input_data.get("command", ["python", "--version"])
                result = run_command(cmd, self.project_path)

                state.add_command(result.command)
                state.add_note(f"Command stdout:\n{result.stdout[:500]}")
                if result.stderr.strip():
                    state.add_note(f"Command stderr:\n{result.stderr[:500]}")

                command_run = True
                if len(state.steps) >= 4 and state.steps[3].status == "pending":
                    state.mark_step_done(4)

            elif action == "done":
                if len(state.steps) >= 5 and state.steps[4].status == "pending":
                    state.mark_step_done(5)
                print("\n=== AGENT FINISHED ===")
                break

        print("\n>>> SKIPPING PATCH STAGE FOR NOW...")
        patch = {}
        state.add_note("Patch stage skipped temporarily until exact-target patching is added.")

        if patch:
            path = patch.get("path")
            original_snippet = patch.get("original_snippet")
            replacement_snippet = patch.get("replacement_snippet")

            if path and original_snippet and replacement_snippet:
                try:
                    success = replace_in_file(
                        self.project_path,
                        path,
                        original_snippet,
                        replacement_snippet,
                    )

                    if success:
                        state.add_note(f"Patched file: {path}")
                        state.add_touched_file(self._rel(path))
                    else:
                        state.add_note(f"Patch failed: snippet not found in {path}")
                except Exception as e:
                    state.add_note(f"Patch error: {e}")
        else:
            state.add_note("No patch suggestion was generated.")

        print("\n>>> VERIFYING PROJECT...")
        from agent.tools.verify_tool import verify_project

        verify_result = verify_project(self.project_path)
        print(f">>> VERIFY RESULT: ok={verify_result.ok}, command={verify_result.command}")

        state.add_note(
            f"Verification command: {verify_result.command} | ok={verify_result.ok} | exit_code={verify_result.exit_code}"
        )
        if verify_result.stdout.strip():
            state.add_note(f"Verification stdout:\n{verify_result.stdout[:500]}")
        if verify_result.stderr.strip():
            state.add_note(f"Verification stderr:\n{verify_result.stderr[:500]}")

        print("\n>>> GENERATING REPORT...")
        report = self._generate_report(state)
        print(">>> REPORT GENERATED")

        report_path = "agent_output/inspection_report.md"
        write_file(self.project_path, report_path, report)
        state.add_touched_file(report_path)
        state.add_note(f"Wrote report: {report_path}")

        print("\n=== FINAL STATE ===\n")
        print(state.summary())
        print(f"\nReport written to: {report_path}")