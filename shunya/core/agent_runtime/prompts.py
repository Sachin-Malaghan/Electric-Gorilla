"""Prompt composition (spec 34): layered policies, never one giant prompt.

system = base policy + company policy + department policy + role policy + project context.
The task and retrieved knowledge go in the first user message, so the system prompt stays
byte-stable per agent (prompt-cache friendly).
"""

from __future__ import annotations

from pathlib import Path

from shunya.shared.schemas import AgentProfile


class PromptComposer:
    def __init__(self, prompts_dir: Path, project: str = "shunya_game"):
        self.dir = prompts_dir
        self.project = project

    def _read(self, rel: str) -> str:
        path = self.dir / rel
        return path.read_text(encoding="utf-8").strip() if path.is_file() else ""

    def compose(self, agent: AgentProfile) -> str:
        role_key = agent.capability or agent.id
        layers = [
            self._read("base.md"),
            self._read("company.md"),
            self._read(f"departments/{agent.department}.md"),
            *[self._read(f"roles/{name}.md") for name in agent.prompts if name != role_key],
            self._read(f"roles/{role_key}.md"),
            self._read(f"projects/{self.project}.md"),
        ]
        identity = (
            f"# You\n"
            f"You are {agent.name}, {agent.role} in the {agent.department} department (agent id `{agent.id}`).\n"
            f"Responsibilities: {', '.join(agent.responsibilities) or 'as assigned'}.\n"
            f"Your supervisor is `{agent.supervisor or 'the user'}`.\n"
            f"[capability:{agent.capability or 'general'}]"
        )
        return "\n\n".join([x for x in layers if x] + [identity])
