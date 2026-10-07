"""Model credentials and the studio-wide spending cap.

The API key is supplied by the studio owner (environment / .env, or the office's Model
settings). It is kept in a file inside the data directory, never returned by any API,
never logged, and never shown to agents. The spend meter is the last line of defence for
a hosted studio using a real key: once the cap is reached no further model call is made.
"""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path

from shunya.core.persistence import Store

KEY_NAME = "anthropic_api_key"
LLM_KEY_NAME = "llm_api_key"
LLM_URL_NAME = "llm_base_url"
LLM_MODEL_NAME = "llm_model"


class SecretStore:
    def __init__(self, data_dir: Path):
        self.path = data_dir / "secrets.json"

    def _load(self) -> dict[str, str]:
        if not self.path.is_file():
            return {}
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

    def get(self, name: str) -> str:
        return self._load().get(name, "")

    def set(self, name: str, value: str) -> None:
        data = self._load()
        if value:
            data[name] = value
        else:
            data.pop(name, None)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data), encoding="utf-8")
        try:
            os.chmod(self.path, stat.S_IRUSR | stat.S_IWUSR)  # owner-only where the OS supports it
        except OSError:
            pass

    def anthropic_key(self) -> tuple[str, str]:
        """(key, source). The environment wins over the stored key so an operator can override it."""
        env = os.environ.get("ANTHROPIC_API_KEY", "")
        if env:
            return env, "environment"
        stored = self.get(KEY_NAME)
        return (stored, "office settings") if stored else ("", "")


    def llm_key(self) -> tuple[str, str]:
        """Key for an OpenAI-compatible endpoint: environment first, then what the owner entered in the office."""
        for name in ("SHUNYA_LLM_API_KEY", "OPENAI_API_KEY"):
            if os.environ.get(name):
                return os.environ[name], "environment"
        stored = self.get(LLM_KEY_NAME)
        return (stored, "office settings") if stored else ("", "")

    def key_for(self, provider: str) -> tuple[str, str]:
        return self.llm_key() if provider == "openai" else self.anthropic_key() if provider == "anthropic" else ("", "")


def hint(key: str) -> str:
    """Enough to recognise which key is configured, never enough to use it."""
    return f"...{key[-4:]}" if len(key) >= 12 else ("set" if key else "")


class SpendMeter:
    """Running total of model spend against the owner's cap. 0 means no cap."""

    def __init__(self, store: Store, limit_usd: float):
        self.limit_usd = limit_usd
        self.spent_usd = round(sum(r.cost_usd for r in store.cost_records.list(limit=1_000_000)), 6)

    def add(self, cost_usd: float) -> None:
        self.spent_usd = round(self.spent_usd + cost_usd, 6)

    @property
    def exhausted(self) -> bool:
        return self.limit_usd > 0 and self.spent_usd >= self.limit_usd

    @property
    def remaining_usd(self) -> float | None:
        return None if self.limit_usd <= 0 else max(0.0, round(self.limit_usd - self.spent_usd, 4))
