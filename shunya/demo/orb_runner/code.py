"""Source files and edits for each code task of the Orb Runner screenplay.

`files/<task>/...` holds new files exactly as the scripted programmer writes them;
PATCHES are the edits a task makes to files that already exist (applied with patch_file).
"""

from __future__ import annotations

from pathlib import Path

FILES_DIR = Path(__file__).parent / "files"
GAME_MODE_CPP = "Source/ShunyaGame/Private/Game/OrbGameMode.cpp"

# task key -> [(path, old_text, new_text)]
PATCHES: dict[str, list[tuple[str, str, str]]] = {
    "code_player": [
        (GAME_MODE_CPP, '#include "Kismet/GameplayStatics.h"\n', '#include "Kismet/GameplayStatics.h"\n#include "Player/OrbRunnerPawn.h"\n'),
        (GAME_MODE_CPP, "\tPrimaryActorTick.bCanEverTick = true;\n}", "\tPrimaryActorTick.bCanEverTick = true;\n\tDefaultPawnClass = AOrbRunnerPawn::StaticClass();\n}"),
    ],
    "code_ui": [
        (GAME_MODE_CPP, '#include "Sound/SoundBase.h"\n', '#include "Sound/SoundBase.h"\n#include "UI/OrbHUD.h"\n'),
        (GAME_MODE_CPP, "\tDefaultPawnClass = AOrbRunnerPawn::StaticClass();\n}", "\tDefaultPawnClass = AOrbRunnerPawn::StaticClass();\n\tHUDClass = AOrbHUD::StaticClass();\n}"),
    ],
}

CODE_TASK_ORDER = ["code_rules", "code_anim", "code_player", "code_ai", "code_ui", "code_tools"]


def task_files(task_key: str) -> dict[str, str]:
    """Workspace-relative path -> content for the files a task creates."""
    root = FILES_DIR / task_key
    if not root.is_dir():
        return {}
    return {p.relative_to(root).as_posix(): p.read_text(encoding="utf-8") for p in sorted(root.rglob("*")) if p.is_file()}


def apply_to(project_dir: Path, task_key: str) -> None:
    """Overlay one task onto a project directory (used to pre-verify the screenplay against the engine)."""
    for rel, content in task_files(task_key).items():
        target = project_dir / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8", newline="\n")
    for rel, old, new in PATCHES.get(task_key, []):
        target = project_dir / rel
        text = target.read_text(encoding="utf-8")
        if text.count(old) != 1:
            raise ValueError(f"{task_key}: patch anchor not found exactly once in {rel}: {old!r}")
        target.write_text(text.replace(old, new), encoding="utf-8", newline="\n")
