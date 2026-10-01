"""Content the scripted art / environment / animation / audio agents author for Orb Runner.

Each entry is a list of (tool name, arguments) exactly as the agent calls them; the real
content tools turn them into source files and Unreal assets.
"""

from __future__ import annotations

from typing import Any

Call = tuple[str, dict[str, Any]]

# Palette from Docs/Art/StyleGuide.md
NAVY = [0.03, 0.05, 0.10]
GRID_CYAN = [0.10, 0.55, 0.75]
SLATE = [0.16, 0.19, 0.27]
VIOLET = [0.30, 0.22, 0.52]
ORB_CYAN = [0.20, 0.90, 1.00]
AMBER = [1.00, 0.60, 0.10]
DRONE_RED = [0.90, 0.10, 0.15]

MAP = "/Game/Shunya/Maps/L_Arena"

ENVIRONMENT_MATERIALS: list[Call] = [
    ("queue_texture", {"name": "T_FloorGrid", "folder": "Environment", "pattern": "grid", "color_a": NAVY, "color_b": GRID_CYAN, "size": 512, "cells": 4}),
    ("queue_material", {"name": "M_Floor", "folder": "Environment", "base_color": [1.0, 1.0, 1.0], "texture": "T_FloorGrid", "uv_tiling": 10.0, "roughness": 0.85}),
    ("queue_material", {"name": "M_Wall", "folder": "Environment", "base_color": SLATE, "roughness": 0.7, "metallic": 0.2}),
]

CHARACTER_MATERIALS: list[Call] = [
    ("queue_material", {"name": "M_Player", "folder": "Characters", "base_color": AMBER, "emissive_color": AMBER, "emissive_strength": 1.5, "metallic": 0.7, "roughness": 0.3}),
    ("queue_material", {"name": "M_Drone", "folder": "Characters", "base_color": DRONE_RED, "emissive_color": DRONE_RED, "emissive_strength": 6.0, "metallic": 0.4, "roughness": 0.4}),
]

PROP_MATERIALS: list[Call] = [
    ("queue_material", {"name": "M_Orb", "folder": "Props", "base_color": ORB_CYAN, "emissive_color": ORB_CYAN, "emissive_strength": 14.0, "roughness": 0.2}),
    ("queue_material", {"name": "M_Pillar", "folder": "Props", "base_color": VIOLET, "roughness": 0.5, "metallic": 0.3}),
]


def _n(freq: float, dur: float, wave: str = "sine", vol: float = 0.6, decay: float = 0.6, slide: float | None = None) -> dict[str, Any]:
    note: dict[str, Any] = {"frequency": freq, "duration": dur, "waveform": wave, "volume": vol, "decay": decay}
    if slide is not None:
        note["slide_to"] = slide
    return note


SFX: list[Call] = [
    ("queue_sound", {"name": "S_Pickup", "folder": "Audio", "notes": [_n(880, 0.07, "sine", 0.6, 0.3), _n(1320, 0.14, "sine", 0.6, 0.9)]}),
    ("queue_sound", {"name": "S_Hit", "folder": "Audio", "notes": [_n(180, 0.06, "noise", 0.8, 0.5), _n(140, 0.18, "square", 0.5, 1.0, slide=60)]}),
    ("queue_sound", {"name": "S_Win", "folder": "Audio", "notes": [_n(523, 0.12, "triangle"), _n(659, 0.12, "triangle"), _n(784, 0.12, "triangle"), _n(1047, 0.4, "triangle", 0.7, 0.9)]}),
    ("queue_sound", {"name": "S_Lose", "folder": "Audio", "notes": [_n(392, 0.18, "saw", 0.45), _n(330, 0.18, "saw", 0.45), _n(262, 0.5, "saw", 0.45, 1.0, slide=196)]}),
]

# Sixteen quarter-second steps in A minor: a 4 second loop.
_LOOP = [220, 330, 262, 330, 196, 294, 247, 294, 175, 262, 220, 262, 165, 247, 208, 247]
MUSIC: list[Call] = [
    ("queue_sound", {"name": "S_MusicLoop", "folder": "Audio", "looping": True, "notes": [_n(f, 0.25, "triangle", 0.22, 0.7) for f in _LOOP]}),
]

ORB_POSITIONS = [(1400, 0), (-1400, 0), (0, 1400), (0, -1400), (1300, 1300), (-1300, 1300), (1300, -1300), (-1300, -1300)]
PILLAR_POSITIONS = [(800, 800), (-800, 800), (800, -800), (-800, -800)]


def _mesh(label: str, shape: str, material: str, location: list[float], scale: list[float]) -> dict[str, Any]:
    return {"type": "static_mesh", "label": label, "shape": shape, "material": material, "location": location, "scale": scale}


LEVEL_ACTORS: list[dict[str, Any]] = [
    _mesh("Floor", "Plane", "M_Floor", [0, 0, 0], [40, 40, 1]),
    _mesh("Wall North", "Cube", "M_Wall", [2000, 0, 150], [1, 41, 3]),
    _mesh("Wall South", "Cube", "M_Wall", [-2000, 0, 150], [1, 41, 3]),
    _mesh("Wall East", "Cube", "M_Wall", [0, 2000, 150], [41, 1, 3]),
    _mesh("Wall West", "Cube", "M_Wall", [0, -2000, 150], [41, 1, 3]),
    *[_mesh(f"Pillar {i + 1}", "Cylinder", "M_Pillar", [x, y, 200], [2, 2, 4]) for i, (x, y) in enumerate(PILLAR_POSITIONS)],
    {"type": "player_start", "label": "Player Start", "location": [0, 0, 60]},
    *[{"type": "actor_class", "label": f"Orb {i + 1}", "class_path": "/Script/ShunyaGame.OrbCollectible", "location": [x, y, 80]} for i, (x, y) in enumerate(ORB_POSITIONS)],
    {"type": "actor_class", "label": "Chaser Drone", "class_path": "/Script/ShunyaGame.ChaserDrone", "location": [-1700, 1700, 90]},
]

LEVEL: list[Call] = [
    ("queue_level", {"name": "L_Arena", "folder": "Maps", "game_mode": "/Script/ShunyaGame.OrbGameMode", "actors": LEVEL_ACTORS}),
]

LIGHTING: list[Call] = [
    ("queue_level_additions", {"level": "L_Arena", "actors": [
        {"type": "directional_light", "label": "Key Light", "rotation": [-48, 35, 0], "intensity": 3.5, "color": [0.80, 0.86, 1.0]},
        {"type": "sky_light", "label": "Sky Fill", "intensity": 0.7},
        {"type": "sky_atmosphere", "label": "Sky Atmosphere"},
        {"type": "post_process", "label": "Exposure", "exposure_brightness": 1.0},
        *[{"type": "point_light", "label": f"Corner Glow {i + 1}", "location": [x, y, 320], "intensity": 600.0, "color": [0.45, 0.3, 0.9], "radius": 1100.0}
          for i, (x, y) in enumerate([(1700, 1700), (-1700, 1700), (1700, -1700), (-1700, -1700)])],
    ]}),
]

CINEMATIC: list[Call] = [
    ("queue_sequence", {"name": "SEQ_Intro", "folder": "Cinematics", "duration_seconds": 6.0, "fps": 30, "camera_keys": [
        {"time": 0.0, "location": [-3200, -3200, 2600], "rotation": [-33, 45, 0]},
        {"time": 3.0, "location": [-2600, 0, 2000], "rotation": [-36, 0, 0]},
        {"time": 6.0, "location": [-1500, 0, 1700], "rotation": [-50, 0, 0]},
    ]}),
]

CONCEPT_BOARD: Call = ("generate_image", {
    "path": "Docs/Art/ConceptBoard.png", "width": 960, "height": 540, "background": [0.04, 0.05, 0.08],
    "shapes": [
        # top-down sketch of the arena
        {"shape": "rect", "color": SLATE, "x": 60, "y": 50, "w": 440, "h": 440},
        {"shape": "rect", "color": NAVY, "x": 76, "y": 66, "w": 408, "h": 408},
        *[{"shape": "rect", "color": GRID_CYAN, "x": 76 + i * 51, "y": 66, "w": 1, "h": 408} for i in range(1, 8)],
        *[{"shape": "rect", "color": GRID_CYAN, "x": 76, "y": 66 + i * 51, "w": 408, "h": 1} for i in range(1, 8)],
        *[{"shape": "circle", "color": VIOLET, "x": 280 + int(x * 0.1), "y": 270 - int(y * 0.1), "r": 16} for x, y in PILLAR_POSITIONS],
        *[{"shape": "circle", "color": ORB_CYAN, "x": 280 + int(x * 0.1), "y": 270 - int(y * 0.1), "r": 7} for x, y in ORB_POSITIONS],
        {"shape": "circle", "color": AMBER, "x": 280, "y": 270, "r": 10},
        {"shape": "circle", "color": DRONE_RED, "x": 110, "y": 100, "r": 11},
        # palette swatches
        *[{"shape": "rect", "color": c, "x": 560 + (i % 4) * 92, "y": 60 + (i // 4) * 92, "w": 76, "h": 76}
          for i, c in enumerate([NAVY, GRID_CYAN, SLATE, VIOLET, ORB_CYAN, AMBER, DRONE_RED])],
        # value strip: dark world, bright interactive things
        *[{"shape": "rect", "color": [0.1 + 0.11 * i] * 3, "x": 560 + i * 46, "y": 300, "w": 46, "h": 40} for i in range(8)],
    ],
})
