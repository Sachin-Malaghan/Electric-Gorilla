"""Model routing (spec 33): classify the work, then pick a tier.

Tiers map to configured models plus an effort level. By default every tier uses the
same capable model and varies effort - one model keeps one prompt-cache namespace and
lower effort on a strong model usually beats a weaker model. Point SHUNYA_MODEL_FAST /
SHUNYA_MODEL_STRONG at different models to route across models instead.
"""

from __future__ import annotations

import re

from shunya.config import Settings
from shunya.shared.schemas import ModelConfig, ModelTier

_TIER_EFFORT = {ModelTier.FAST: "low", ModelTier.STANDARD: "medium", ModelTier.STRONG: "high"}

_TRIVIAL = re.compile(r"\b(rename|typo|comment|format|docstring|spelling|log message)\b", re.I)
_HARD = re.compile(
    r"\b(architect|architecture|network(ing)?|replicat\w*|multiplayer|crash|deadlock|race condition|"
    r"refactor|optimi[sz]e|performance|memory leak|gameplay ability system|gas)\b",
    re.I,
)


def classify(text: str) -> ModelTier:
    if _HARD.search(text):
        return ModelTier.STRONG
    if _TRIVIAL.search(text) and len(text) < 240:
        return ModelTier.FAST
    return ModelTier.STANDARD


class ModelRouter:
    def __init__(self, settings: Settings):
        self.settings = settings

    def model_for(self, tier: ModelTier) -> str:
        return {
            ModelTier.FAST: self.settings.model_fast,
            ModelTier.STANDARD: self.settings.model_standard,
            ModelTier.STRONG: self.settings.model_strong,
        }[tier]

    def resolve(self, base: ModelConfig, work_description: str = "") -> ModelConfig:
        """Agent profile config + task classification -> concrete model config.

        Hard work is promoted to STRONG and trivial work demoted to FAST, except that an
        agent configured STRONG (e.g. the reviewer) is never demoted.
        """
        tier = base.tier
        if work_description and tier != ModelTier.STRONG:
            classified = classify(work_description)
            if classified != ModelTier.STANDARD:
                tier = classified
        return ModelConfig(
            tier=tier,
            model=base.model or self.model_for(tier),
            effort=base.effort or _TIER_EFFORT[tier],
            max_tokens=base.max_tokens,
        )
