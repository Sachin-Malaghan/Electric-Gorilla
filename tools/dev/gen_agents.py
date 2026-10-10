"""Regenerates agents/**/*.yaml - the studio's org chart.

Run:  python tools/dev/gen_agents.py
The YAML files are what the studio loads; edit this script (not the YAML) when a whole
group of roles changes, so tools and permissions stay consistent across similar roles.
"""

from __future__ import annotations

import pathlib

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[2]


class NoAlias(yaml.SafeDumper):
    def ignore_aliases(self, data):
        return True


READ = ["read_file", "list_dir", "search_files", "find_symbol", "find_references", "inspect_dependencies", "analyze_impact", "analyze_call_graph", "knowledge_search"]
UE_READ = ["get_editor_state", "get_current_level", "find_actor", "inspect_actor", "inspect_asset"]
REVIEW = READ + ["git_diff", "git_status"]
DOC = REVIEW + ["create_doc", "patch_doc"]

P_READ = {"read_docs": "YES", "read_code": "YES", "knowledge_search": "YES", "git_read": "YES", "unreal_read": "YES"}
NO = {"write_code": "NO", "write_docs": "NO", "write_content": "NO", "git_commit": "NO", "merge": "NO", "deploy": "NO", "unreal_editor_modify": "NO"}
P_DOC = {**P_READ, **NO, "write_docs": "CONDITIONAL"}
P_CONTENT = {**P_READ, **NO, "write_content": "CONDITIONAL"}
P_CODE = {**P_READ, **NO, "write_code": "CONDITIONAL", "write_docs": "CONDITIONAL", "compile": "YES", "run_tests": "YES", "git_commit": "CONDITIONAL"}
P_QA_RUN = {**P_DOC, "run_tests": "YES", "unreal_runtime": "YES"}


def agent(id, name, role, resp, room, color, desk, *, cap=None, tools=None, perms=None, tier="standard", sup=None, prompts=None, **extra):
    d = dict(id=id, name=name, role=role, responsibilities=resp, enabled=cap is not None, supervisor=sup, model={"tier": tier},
             tools=tools if tools is not None else READ, permissions=perms if perms is not None else {**P_READ, **NO},
             avatar={"room": room, "color": color, "desk": desk})
    if cap:
        d["capability"] = cap
    if prompts:
        d["prompts"] = prompts
    d.update(extra)
    return d


def lead(id, name, role, resp, room, color, desk, cap, sup, **extra):
    """Department leads write briefs and review their department's work."""
    return agent(id, name, role, resp, room, color, desk, cap=cap, sup=sup, tools=DOC, perms=P_DOC, prompts=["doc_author", "lead_reviewer"],
                 write_globs=["Docs/*"], max_iterations=32, cost_budget=2.5, **extra)


def writer(id, name, role, resp, room, color, desk, cap, sup, tools_extra=(), perms=None, **extra):
    return agent(id, name, role, resp, room, color, desk, cap=cap, sup=sup, tools=DOC + list(tools_extra), perms=perms or P_DOC, prompts=["doc_author"],
                 write_globs=["Docs/*"], max_iterations=32, cost_budget=2.0, **extra)


def maker(id, name, role, resp, room, color, desk, cap, sup, queue_tools):
    """Content authors: typed content jobs, applied in the editor."""
    return agent(id, name, role, resp, room, color, desk, cap=cap, sup=sup, tools=READ + ["git_status", *queue_tools, "apply_content"], perms=P_CONTENT,
                 prompts=["content_author"], write_globs=["ContentJobs/*", "SourceArt/*"], max_iterations=48, max_runtime_s=2400, cost_budget=3.0)


PROG_TOOLS = READ + ["create_file", "patch_file", "compile_project", "run_automation_tests", "git_diff", "git_status"] + UE_READ
PROG = dict(write_globs=["Source/*", "Plugins/*/Source/*", "Docs/*"], max_iterations=80, max_tool_calls=240, max_runtime_s=7200, token_budget=6000000, cost_budget=8.0,
            escalation_policy={"escalate_to": "technical_director_01", "after_consecutive_failures": 3},
            validation_policy={"required_checks": ["compile", "tests", "review", "qa"]})


def programmer(id, name, role, resp, color, desk, cap, room="engineering", sup="technical_director_01"):
    return agent(id, name, role, resp, room, color, desk, cap=cap, sup=sup, tools=PROG_TOOLS, perms=P_CODE, prompts=["programmer"], **PROG)


FILES = {
    "management/management.yaml": [
        agent("studio_director_01", "Meera", "Studio Director", ["interpret game objectives", "scope features", "flag product risk", "review direction-setting documents"], "executive", "#c9a227", 0,
              cap="director", tools=REVIEW, prompts=["lead_reviewer"], max_iterations=20, cost_budget=1.5),
        agent("producer_01", "Kabir", "Producer", ["create epics and typed tasks", "acceptance criteria", "task graph and dependencies", "review plans, sign-offs and release documents"], "executive", "#d4783a", 1,
              cap="producer", sup="studio_director_01", tools=REVIEW, prompts=["lead_reviewer"], max_iterations=24, cost_budget=2.0),
    ],
    "design/design.yaml": [
        lead("lead_designer_01", "Maya", "Lead Designer", ["game design document", "design pillars", "review design documents"], "design", "#e6589c", 0, "lead_designer", "producer_01"),
        writer("gameplay_designer_01", "Rahul", "Gameplay Designer", ["controls", "game feel", "player verbs"], "design", "#ee6fae", 1, "gameplay_designer", "lead_designer_01"),
        writer("combat_designer_01", "Aarav", "Combat Designer", ["enemy behaviour", "threat specifications", "damage rules"], "design", "#f085bb", 2, "combat_designer", "lead_designer_01"),
        writer("level_designer_01", "Nisha", "Level Designer", ["level layouts with coordinates", "pickup and obstacle placement", "pacing"], "design", "#dd4d90", 3, "level_designer", "lead_designer_01"),
        writer("economy_designer_01", "Kunal", "Economy Designer", ["scoring", "tuning tables", "timers and rewards"], "design", "#d1407f", 4, "economy_designer", "lead_designer_01"),
        writer("narrative_designer_01", "Ira", "Narrative Designer", ["premise", "UI and banner text", "naming"], "design", "#f29ac8", 5, "narrative_designer", "lead_designer_01"),
    ],
    "engineering/engineering.yaml": [
        agent("technical_director_01", "Vikram", "Technical Director / Code Reviewer", ["independent code review", "architecture decisions", "engineering standards"], "engineering", "#7a5cff", 0,
              cap="reviewer", tier="strong", sup="producer_01", tools=REVIEW, max_iterations=32, cost_budget=3.0),
        programmer("gameplay_programmer_01", "Arjun", "Senior Unreal Gameplay Programmer", ["gameplay systems", "Unreal C++", "components", "game rules", "replication"], "#4f8cff", 1, "programmer"),
        programmer("unreal_programmer_01", "Diya", "Unreal Engine Programmer", ["pawns and actors", "engine integration", "subsystems", "automation tests"], "#3fb6c9", 2, "programmer"),
        writer("software_architect_01", "Ishaan", "Software Architect", ["technical design", "module and class layout", "ADRs"], "engineering", "#6d7cff", 3, "software_architect", "technical_director_01"),
        programmer("ai_programmer_01", "Tara", "AI Programmer", ["enemy AI", "pursuit and steering", "navigation", "perception"], "#4fa3ff", 4, "ai_programmer"),
        agent("graphics_programmer_01", "Neel", "Graphics Programmer", ["shaders", "rendering features"], "engineering", "#5b8def", 5, sup="technical_director_01"),
        programmer("ui_programmer_01", "Sana", "UI Programmer", ["HUD", "UMG / Slate / canvas", "menus"], "#5aa0e6", 6, "ui_programmer"),
        agent("networking_programmer_01", "Dev", "Networking Programmer", ["replication", "RPCs", "prediction", "sessions"], "engineering", "#4a7fe0", 7, sup="technical_director_01"),
        programmer("tools_programmer_01", "Riya", "Tools Programmer", ["QA tooling", "automation bots", "telemetry", "pipelines"], "#6fa8ff", 8, "tools_programmer"),
    ],
    "art/art.yaml": [
        lead("art_director_01", "Leela", "Art Director", ["style guide and palette", "review art content against the style guide"], "art", "#f2a33a", 0, "art_director", "producer_01"),
        writer("concept_agent_01", "Veer", "Concept Agent", ["concept boards", "layout sketches", "palette studies"], "art", "#f5b458", 1, "concept_artist", "art_director_01", tools_extra=["generate_image"]),
        maker("character_agent_01", "Anika", "Character Agent", ["player and enemy look", "character materials"], "art", "#eb9722", 2, "character_artist", "art_director_01", ["queue_texture", "queue_material"]),
        maker("prop_agent_01", "Jay", "Prop Agent", ["pickups and obstacles look", "prop materials"], "art", "#f7c070", 3, "prop_artist", "art_director_01", ["queue_texture", "queue_material"]),
        maker("material_agent_01", "Pari", "Material Agent", ["environment materials", "tiling textures"], "art", "#e08a12", 4, "material_artist", "art_director_01", ["queue_texture", "queue_material"]),
        agent("vfx_agent_01", "Reyansh", "VFX Agent", ["Niagara effects"], "art", "#fbd08c", 5, sup="art_director_01"),
    ],
    "environment/environment.yaml": [
        lead("environment_director_01", "Gauri", "Environment Director", ["environment brief", "review levels and lighting"], "environment", "#8bbf3f", 0, "environment_director", "producer_01"),
        maker("world_builder_01", "Samar", "World Builder", ["level blockout and build", "actor placement from the level layout"], "environment", "#9bcc55", 1, "world_builder", "environment_director_01", ["queue_level", "queue_level_additions"]),
        agent("landscape_agent_01", "Tanvi", "Landscape Agent", ["terrain", "landscape materials"], "environment", "#7fb22f", 2, sup="environment_director_01"),
        agent("foliage_agent_01", "Advait", "Foliage Agent", ["foliage", "PCG scattering"], "environment", "#a8d66b", 3, sup="environment_director_01"),
        maker("lighting_agent_01", "Mira", "Lighting Agent", ["lighting passes", "sky and exposure"], "environment", "#74a624", 4, "lighting_artist", "environment_director_01", ["queue_level_additions"]),
        agent("optimization_agent_01", "Kabya", "Optimization Agent", ["HLOD", "culling", "streaming budgets"], "environment", "#b6e081", 5, sup="environment_director_01"),
    ],
    "animation/animation.yaml": [
        lead("animation_lead_01", "Ruhi", "Animation Lead", ["animation brief", "review motion and cinematics"], "animation", "#b86be0", 0, "animation_lead", "producer_01"),
        agent("rigging_agent_01", "Arnav", "Rigging Agent", ["skeletons", "control rigs"], "animation", "#c684e8", 1, sup="animation_lead_01"),
        programmer("gameplay_animation_agent_01", "Saanvi", "Gameplay Animation Agent", ["procedural motion in C++", "idle and pickup animation", "anim maths with tests"], "#aa55d6", 2, "gameplay_animator", room="animation", sup="animation_lead_01"),
        maker("cinematic_agent_01", "Kabeer", "Cinematic Agent", ["level sequences", "camera moves"], "animation", "#d49df0", 3, "cinematic_artist", "animation_lead_01", ["queue_sequence"]),
    ],
    "audio/audio.yaml": [
        lead("audio_director_01", "Esha", "Audio Director", ["audio brief", "review sound effects and music"], "audio", "#3fc2b0", 0, "audio_director", "producer_01"),
        maker("sfx_agent_01", "Vihaan", "SFX Agent", ["sound effects"], "audio", "#58d0bf", 1, "sfx_designer", "audio_director_01", ["queue_sound"]),
        maker("music_agent_01", "Alia", "Music Agent", ["music loops"], "audio", "#2bb09e", 2, "composer", "audio_director_01", ["queue_sound"]),
    ],
    "qa/qa.yaml": [
        lead("qa_lead_01", "Farah", "QA Lead", ["sign-off report", "review playtest, performance and regression reports"], "qa", "#2fae6b", 0, "qa_lead", "producer_01"),
        agent("qa_functional_01", "Ananya", "Functional QA Engineer", ["independent validation of code and content", "acceptance-criteria evidence", "defect reports"], "qa", "#39c27d", 1, cap="qa", sup="qa_lead_01",
              tools=REVIEW + ["run_automation_tests", "validate_content"] + UE_READ + ["get_runtime_telemetry"], perms={**P_READ, **NO, "run_tests": "YES", "unreal_runtime": "YES"},
              max_iterations=32, max_runtime_s=2400, cost_budget=3.0),
        writer("qa_gameplay_01", "Om", "Gameplay QA", ["playtests", "playtest reports with evidence"], "qa", "#49cc8a", 2, "qa_gameplay", "qa_lead_01", tools_extra=["run_playtest"], perms=P_QA_RUN, max_runtime_s=2400),
        writer("qa_regression_01", "Lila", "Regression QA", ["full test-suite runs", "regression reports"], "qa", "#28a362", 3, "qa_regression", "qa_lead_01", tools_extra=["run_automation_tests"], perms=P_QA_RUN, max_runtime_s=2400),
        writer("qa_performance_01", "Yash", "Performance QA", ["frame-rate budgets", "performance reports from playtests"], "qa", "#1f9958", 4, "qa_performance", "qa_lead_01", tools_extra=["run_playtest"], perms=P_QA_RUN, max_runtime_s=2400),
        agent("crash_investigator_01", "Zoya", "Crash Investigator", ["crash dumps", "callstack triage", "repro steps"], "qa", "#57d695", 5, sup="qa_lead_01"),
    ],
    "devops/devops.yaml": [
        agent("build_engineer_01", "Rohan", "Build Engineer", ["official builds", "build health", "compiler diagnostics"], "devops", "#e0574f", 0, cap="build", sup="producer_01", tools=[], perms={"compile": "YES", "read_code": "YES"}),
        agent("ci_agent_01", "Kiran", "CI Agent", ["pipelines", "automated checks"], "devops", "#e87a5f", 1, sup="build_engineer_01"),
        writer("release_agent_01", "Aditi", "Release Agent", ["release notes", "packaged builds", "version summaries"], "devops", "#d94c6a", 2, "release_manager", "build_engineer_01",
               tools_extra=["package_game"], perms={**P_DOC, "package": "YES", "deploy": "APPROVAL"}, max_runtime_s=7200),
    ],
    "documentation/documentation.yaml": [
        writer("technical_writer_01", "Nikhil", "Technical Writer", ["player manual", "class reference"], "documentation", "#9aa3b2", 0, "technical_writer", "producer_01"),
        writer("knowledge_curator_01", "Sara", "Knowledge Curator", ["knowledge index", "ADR upkeep"], "documentation", "#aab3c2", 1, "knowledge_curator", "producer_01"),
    ],
}


def main() -> None:
    total = active = 0
    for rel, agents in FILES.items():
        path = ROOT / "agents" / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        header = f"# {path.parent.name.title()} department. Generated by tools/dev/gen_agents.py.\n# enabled: false = defined in the org chart, no work for this role yet (shown as an empty desk).\n"
        path.write_text(header + yaml.dump(agents, Dumper=NoAlias, sort_keys=False, width=140), encoding="utf-8", newline="\n")
        total += len(agents)
        active += sum(1 for a in agents if a["enabled"])
    print(f"{total} agents, {active} active")


if __name__ == "__main__":
    main()
