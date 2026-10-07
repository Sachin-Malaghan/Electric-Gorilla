"""Runtime configuration, read from environment variables (and an optional .env file)."""

from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel, Field

REPO_ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv(path: Path) -> None:
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"'))


class Settings(BaseModel):
    repo_root: Path = REPO_ROOT
    data_dir: Path = REPO_ROOT / "data"
    workspace_dir: Path = REPO_ROOT / "workspace"

    database_url: str = ""
    redis_url: str = ""

    # "anthropic" for real agents, "scripted" for the deterministic demo/test provider.
    model_provider: str = "scripted"
    model_standard: str = "claude-opus-5-5"
    model_strong: str = "claude-opus-5-5"
    model_fast: str = "claude-opus-5-5"
    model_fallbacks: bool = True
    # OpenAI-compatible endpoint (a router, gateway or local server), used when model_provider == "openai"
    llm_base_url: str = ""
    # USD per million tokens for models the built-in price table does not know (0 = estimate at the most expensive known rate)
    model_price_input: float = 0.0
    model_price_output: float = 0.0
    models_pinned: bool = False  # True when SHUNYA_MODEL_* were set explicitly

    # Unreal
    engine_root: Path | None = None
    game_template: Path = REPO_ROOT / "unreal" / "ShunyaGame"
    # Finished games are committed into <publish_repo>/games/<slug>/ (only that folder is ever committed).
    publish_games: bool = True
    publish_repo: Path | None = REPO_ROOT
    publish_push: bool = False
    game_project_name: str = "ShunyaGame"
    bridge_url: str = "http://127.0.0.1:30777"
    bridge_token: str = "shunya-dev-token"
    build_timeout_s: int = 1800
    test_timeout_s: int = 1200

    # Orchestration limits
    max_concurrent_tasks: int = 4
    # "" = every merge needs a human; "LOW" = merges whose computed risk is LOW are approved by policy
    auto_approve_max_risk: str = ""
    max_build_attempts: int = 3
    max_review_rounds: int = 2
    max_qa_rounds: int = 2

    agents_dir: Path = REPO_ROOT / "agents"
    prompts_dir: Path = REPO_ROOT / "prompts"
    ui_dir: Path = REPO_ROOT / "apps" / "studio-ui"

    host: str = "127.0.0.1"
    port: int = 8400
    # When set, every API call and the WebSocket must present it. Required to listen on anything but loopback.
    api_token: str = ""
    # New feature requests are refused (HTTP 429) while this many are still in flight.
    max_active_features: int = 3
    log_level: str = "INFO"
    # Hard cap on total model spend (USD) across the whole studio. 0 = no cap. Applies to real providers.
    max_spend_usd: float = 25.0
    # True when SHUNYA_MODEL_PROVIDER was set explicitly; otherwise the provider follows whether a key is available.
    provider_pinned: bool = False
    package_timeout_s: int = 5400

    demo_step_delay: float = Field(default=0.0, description="Scripted provider only: seconds of 'thinking' per step, so the office is watchable.")
    demo_inject_compile_error: bool = Field(
        default=True,
        description="Scripted provider only: the programmer's first attempt has a compile error, "
        "so the demo exercises the parse -> diagnose -> fix loop.",
    )

    @property
    def db_url(self) -> str:
        return self.database_url or f"sqlite:///{(self.data_dir / 'shunya.db').as_posix()}"

    @property
    def artifacts_dir(self) -> Path:
        return self.data_dir / "artifacts"

    @property
    def worktrees_dir(self) -> Path:
        # short on purpose: Unreal build output nests ~150 characters below this (Windows 260-char limit)
        return self.workspace_dir / "wt"

    @property
    def games_dir(self) -> Path:
        """One folder (and git repository) per game."""
        return self.workspace_dir / "games"

    @property
    def builds_dir(self) -> Path:
        """Packaged game builds (not committed anywhere)."""
        return self.workspace_dir / "builds"

    @property
    def logs_dir(self) -> Path:
        return self.data_dir / "logs"

    @property
    def unreal_available(self) -> bool:
        return self.engine_root is not None and (
            self.engine_root / "Engine" / "Build" / "BatchFiles" / "Build.bat"
        ).is_file()


def _default_engine_root() -> Path | None:
    for candidate in (
        os.environ.get("SHUNYA_ENGINE_ROOT"),
        r"C:\Program Files\Epic Games\UE_5.8",
        r"C:\Program Files\Epic Games\UE_5.7",
        r"C:\Program Files\Epic Games\UE_5.6",
        r"C:\Program Files\Epic Games\UE_5.5",
        r"C:\Program Files\Epic Games\UE_5.4",
    ):
        if candidate and (Path(candidate) / "Engine" / "Build" / "BatchFiles" / "Build.bat").is_file():
            return Path(candidate)
    return None


def load_settings(**overrides) -> Settings:
    if not os.environ.get("SHUNYA_NO_DOTENV"):  # the test suite sets this so a developer's real key is never used by tests
        _load_dotenv(REPO_ROOT / ".env")
    env = os.environ
    values: dict = {}
    mapping = {
        "SHUNYA_DATA_DIR": "data_dir",
        "SHUNYA_WORKSPACE_DIR": "workspace_dir",
        "DATABASE_URL": "database_url",
        "REDIS_URL": "redis_url",
        "SHUNYA_MODEL_PROVIDER": "model_provider",
        "SHUNYA_MODEL_STANDARD": "model_standard",
        "SHUNYA_MODEL_STRONG": "model_strong",
        "SHUNYA_MODEL_FAST": "model_fast",
        "SHUNYA_BRIDGE_URL": "bridge_url",
        "SHUNYA_BRIDGE_TOKEN": "bridge_token",
        "SHUNYA_HOST": "host",
        "SHUNYA_PORT": "port",
        "SHUNYA_MAX_CONCURRENT_TASKS": "max_concurrent_tasks",
        "SHUNYA_AUTO_APPROVE_MAX_RISK": "auto_approve_max_risk",
        "SHUNYA_API_TOKEN": "api_token",
        "SHUNYA_MAX_ACTIVE_FEATURES": "max_active_features",
        "SHUNYA_LOG_LEVEL": "log_level",
        "SHUNYA_MAX_SPEND_USD": "max_spend_usd",
        "SHUNYA_LLM_BASE_URL": "llm_base_url",
        "SHUNYA_MODEL_PRICE_INPUT": "model_price_input",
        "SHUNYA_MODEL_PRICE_OUTPUT": "model_price_output",
    }
    for key, field in mapping.items():
        if env.get(key):
            values[field] = env[key]
    if env.get("SHUNYA_DEMO_INJECT_ERROR"):
        values["demo_inject_compile_error"] = env["SHUNYA_DEMO_INJECT_ERROR"].lower() in ("1", "true", "yes")
    for key, field in (("SHUNYA_PUBLISH_GAMES", "publish_games"), ("SHUNYA_PUBLISH_PUSH", "publish_push")):
        if env.get(key):
            values[field] = env[key].lower() in ("1", "true", "yes")
    if env.get("SHUNYA_DEMO_STEP_DELAY"):
        values["demo_step_delay"] = float(env["SHUNYA_DEMO_STEP_DELAY"])
    if env.get("SHUNYA_MODEL_FALLBACKS"):
        values["model_fallbacks"] = env["SHUNYA_MODEL_FALLBACKS"].lower() in ("1", "true", "yes")
    if env.get("SHUNYA_DISABLE_UNREAL", "").lower() in ("1", "true", "yes"):
        values["engine_root"] = None
    else:
        values["engine_root"] = _default_engine_root()
    values["models_pinned"] = any(env.get(k) for k in ("SHUNYA_MODEL_STANDARD", "SHUNYA_MODEL_STRONG", "SHUNYA_MODEL_FAST"))
    values["provider_pinned"] = bool(env.get("SHUNYA_MODEL_PROVIDER")) or "model_provider" in overrides
    values.update(overrides)
    settings = Settings(**values)
    return settings
