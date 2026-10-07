"""`shunya doctor`: checks that this machine can run the studio, before anything is started."""

from __future__ import annotations

import shutil
import subprocess
import sys
from dataclasses import dataclass

from shunya.config import Settings

OK, WARN, FAIL = "ok", "warn", "FAIL"


@dataclass
class Check:
    name: str
    status: str
    detail: str


def run_checks(settings: Settings) -> list[Check]:
    checks: list[Check] = []

    def add(name: str, status: str, detail: str) -> None:
        checks.append(Check(name, status, detail))

    add("Python", OK if sys.version_info >= (3, 12) else FAIL, sys.version.split()[0] + (" (3.12+ required)" if sys.version_info < (3, 12) else ""))

    git = shutil.which("git")
    if git:
        version = subprocess.run([git, "--version"], capture_output=True, text=True).stdout.strip()
        add("Git", OK, version)
    else:
        add("Git", FAIL, "git is not on PATH; task worktrees cannot be created")

    try:
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        probe = settings.data_dir / ".write_test"
        probe.write_text("x", encoding="utf-8")
        probe.unlink()
        add("Data directory", OK, str(settings.data_dir))
    except OSError as e:
        add("Data directory", FAIL, f"{settings.data_dir} is not writable: {e}")

    try:
        from shunya.core.persistence import Store

        store = Store(settings.db_url)
        store.events.last_seq()
        store.close()
        add("Database", OK, settings.db_url.split("@")[-1] if "@" in settings.db_url else settings.db_url)
    except Exception as e:  # noqa: BLE001 - report any driver / connection problem
        add("Database", FAIL, f"{type(e).__name__}: {e}")

    # Unreal build output nests ~150 characters below a worktree; Windows allows 260.
    worktree = settings.worktrees_dir / "GAME-9999"
    room = 260 - 150 - len(str(worktree))
    add("Workspace path length", OK if room >= 20 else (WARN if room >= 0 else FAIL),
        f"{worktree} leaves {room} characters of headroom" + ("" if room >= 20 else "; set SHUNYA_WORKSPACE_DIR to a shorter path"))

    if settings.unreal_available:
        engine = settings.engine_root / "Engine"  # type: ignore[operator]
        dotnet = next(iter(sorted((engine / "Binaries" / "ThirdParty" / "DotNet").glob("*/win-x64/dotnet.exe"))), None)
        editor = engine / "Binaries" / "Win64" / "UnrealEditor-Cmd.exe"
        uat = engine / "Build" / "BatchFiles" / "RunUAT.bat"
        missing = [n for n, p in (("bundled dotnet", dotnet), ("UnrealEditor-Cmd.exe", editor), ("RunUAT.bat", uat)) if p is None or not p.is_file()]
        add("Unreal Engine", FAIL if missing else OK, f"{settings.engine_root}" + (f" - missing: {', '.join(missing)}" if missing else ""))
    else:
        add("Unreal Engine", WARN, "not found - builds, tests, content and playtests will be reported as SKIPPED (set SHUNYA_ENGINE_ROOT)")

    add("Game template", OK if (settings.game_template / f"{settings.game_project_name}.uproject").is_file() else FAIL, str(settings.game_template))

    from shunya.core.secrets import SecretStore, hint

    secrets = SecretStore(settings.data_dir)
    key, source = secrets.anthropic_key()
    llm_key, llm_source = secrets.llm_key()
    base_url = settings.llm_base_url or secrets.get("llm_base_url")
    uses_endpoint = settings.model_provider == "openai" or (bool(llm_key and base_url) and not settings.provider_pinned)
    wants_real = uses_endpoint or settings.model_provider == "anthropic" or (bool(key) and not settings.provider_pinned)
    if uses_endpoint:
        if llm_key and base_url:
            add("Model provider", OK, f"OpenAI-compatible endpoint {base_url}, key {hint(llm_key)} from {llm_source}, model {settings.model_standard if settings.models_pinned else secrets.get('llm_model') or '(not chosen)'}")
        else:
            add("Model provider", FAIL, "OpenAI-compatible provider needs SHUNYA_LLM_BASE_URL and SHUNYA_LLM_API_KEY (or enter them under Model in the office)")
        cap = settings.max_spend_usd
        add("Spending cap", OK if cap > 0 else WARN, f"${cap:.2f} total (SHUNYA_MAX_SPEND_USD)" + ("" if settings.model_price_input or settings.model_price_output else " - model price unknown, spend is estimated at the highest known rate; set SHUNYA_MODEL_PRICE_INPUT / _OUTPUT"))
    elif wants_real:
        try:
            import anthropic  # noqa: F401

            if key:
                add("Model provider", OK, f"Claude, API key {hint(key)} from {source}")
            else:
                add("Model provider", FAIL, "SHUNYA_MODEL_PROVIDER=anthropic but no API key: set ANTHROPIC_API_KEY in .env or enter it under Model in the office")
        except ImportError:
            add("Model provider", FAIL, "anthropic SDK is not installed: pip install -e .[anthropic]")
        cap = settings.max_spend_usd
        add("Spending cap", OK if cap > 0 else WARN, f"${cap:.2f} total (SHUNYA_MAX_SPEND_USD)" if cap > 0 else "no cap - real agents can spend without limit")
    else:
        add("Model provider", WARN, "scripted - employees follow fixed scripts; only the two built-in requests work. Supply an API key to use real agents")

    loopback = settings.host in ("127.0.0.1", "localhost", "::1")
    if settings.api_token:
        add("API access", OK, f"token required; listening on {settings.host}:{settings.port}")
    elif loopback:
        add("API access", WARN, f"no SHUNYA_API_TOKEN set - anyone on this PC can use http://{settings.host}:{settings.port}")
    else:
        add("API access", FAIL, f"listening on {settings.host} without SHUNYA_API_TOKEN is refused")

    if settings.bridge_token == "shunya-dev-token":
        add("Editor bridge token", WARN, "default token in use; change Token in the game's Config/DefaultEngine.ini and SHUNYA_BRIDGE_TOKEN before opening the editor on a shared machine")
    else:
        add("Editor bridge token", OK, "custom token set")

    if settings.redis_url:
        try:
            import redis

            redis.from_url(settings.redis_url).ping()
            add("Redis", OK, settings.redis_url)
        except Exception as e:  # noqa: BLE001
            add("Redis", FAIL, f"{type(e).__name__}: {e}")
    return checks


def report(checks: list[Check]) -> int:
    width = max(len(c.name) for c in checks)
    for c in checks:
        print(f"[{c.status:4}] {c.name.ljust(width)}  {c.detail}")
    failed = sum(1 for c in checks if c.status == FAIL)
    warned = sum(1 for c in checks if c.status == WARN)
    print(f"\n{len(checks) - failed - warned} ok, {warned} warning(s), {failed} failure(s)")
    return 1 if failed else 0
