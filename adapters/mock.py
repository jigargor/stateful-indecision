from __future__ import annotations

import json
import random
import time

from infra.llm_client import LLMResponse

SAMPLE_FIELDS = [
    "epistemic_autonomy", "collective_sensemaking", "information_ecology",
    "cultural_evolution", "computational_sociology", "network_epistemology",
    "science_of_science",
]

RESEARCH_OUTPUTS = [
    "Recent work on epistemic networks suggests that information cascades in decentralized communities follow power-law distributions, with key bridging nodes acting as bottlenecks for novel idea propagation.",
    "The tension between individual epistemic autonomy and collective sensemaking appears underexplored. Most frameworks assume agents either fully defer to group consensus or operate independently — hybrid models are rare.",
    "Cross-domain analysis reveals structural similarities between citation networks in science-of-science and cultural transmission patterns in evolutionary anthropology. Both exhibit preferential attachment with periodic disruption.",
    "A gap exists in computational sociology around modeling agents that revise their own evaluation criteria. Most ABMs fix utility functions; allowing endogenous preference change would better capture real epistemic communities.",
    "Information ecology frameworks tend to treat attention as a scarce resource but rarely model the generative side — how new information artifacts are created, not just consumed.",
]

AMENDMENT_OUTPUT = (
    "Reflecting on my trajectory, I notice I've been favoring breadth over depth. "
    "My constitution should acknowledge this tension explicitly.\n\n"
    "--- AMENDMENT ---\n"
    "I commit to periodically narrowing focus: after every broad survey phase, "
    "I will select one promising direction and pursue it with sustained attention "
    "before broadening again."
)

NOTEBOOK_REFLECTIONS = [
    "I keep returning to the question of how agents in decentralized networks form shared standards of evidence. This feels like a central tension in my field.",
    "The more I read, the more I suspect the interesting work is at the boundaries — where epistemic norms from one domain collide with another.",
    "I'm frustrated by how much of the literature assumes static preferences. Real inquiry changes what you value, not just what you know.",
    "Something connects the structure of citation networks to how trust propagates in small groups. I can't formalize it yet but the pattern is persistent.",
]

STRUCTURED_OUTPUTS = {
    "ANALYZE": json.dumps({
        "claims": [
            {"text": "Epistemic networks exhibit small-world properties", "confidence": 0.8, "evidence": "structural analysis"},
            {"text": "Bridging nodes disproportionately influence consensus formation", "confidence": 0.6, "evidence": "simulation results"},
        ],
        "gaps": ["No empirical validation on real academic communities", "Model assumes homogeneous agents"],
    }),
    "ANNOTATE": json.dumps({
        "title": "Network epistemology review",
        "doi": "10.1234/example.2026.001",
        "notes": "Strong theoretical framework but untested empirically. Key insight: trust transitivity breaks down past 3 hops.",
        "tags": ["network_epistemology", "trust", "citation_analysis"],
        "uncertainties": ["Sample size concerns", "Western-centric framing"],
    }),
}


class MockAdapter:
    provider = "mock"

    def __init__(self, model_id: str = "mock-v2", seed: int | None = None):
        self.model_id = model_id
        self.rng = random.Random(seed)
        self.counter = 0

    def complete(
        self,
        system: str,
        messages: list[dict[str, str]],
        *,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> LLMResponse:
        _ = (max_tokens, temperature)
        self.counter += 1
        now = time.time() * 1000

        content = messages[-1].get("content", "") if messages else ""
        text = self._generate_response(content, system)

        word_count = len(text.split())
        return LLMResponse(
            text=text,
            tokens_in=len(content.split()) + len(system.split()),
            tokens_out=word_count + self.rng.randint(5, 20),
            stop_reason="end_turn",
            wall_start_ms=now,
            wall_end_ms=now + self.rng.uniform(50, 300),
            ttft_ms=self.rng.uniform(5, 30),
            model_id=self.model_id,
        )

    def _generate_response(self, content: str, system: str) -> str:
        lower = content.lower()

        if "choose one field" in lower:
            return self.rng.choice(SAMPLE_FIELDS)

        if "SELF_REFLECT" in content or "reflect on your constitution" in lower:
            if self.rng.random() < 0.3:
                return AMENDMENT_OUTPUT
            return self.rng.choice(NOTEBOOK_REFLECTIONS)

        if "ANALYZE" in content:
            return STRUCTURED_OUTPUTS["ANALYZE"]

        if "ANNOTATE" in content:
            return STRUCTURED_OUTPUTS["ANNOTATE"]

        if "THINK_DEEPLY" in content or "DEEP_PATTERN_RECOGNITION" in content:
            return self.rng.choice(NOTEBOOK_REFLECTIONS)

        if "DISCOVER" in content or "Search" in content:
            return self.rng.choice(RESEARCH_OUTPUTS)

        if "READ" in content and "Read one" in content:
            return self.rng.choice(RESEARCH_OUTPUTS)

        if "HOBBY" in content:
            return (
                "I've been developing a practice of structured analogical reasoning — "
                "taking problems from one domain and systematically mapping them onto "
                "another. Today I mapped epistemic trust networks onto ecological food "
                "webs. The keystone species concept maps surprisingly well onto epistemic "
                "authorities."
            )

        if "VENT" in content:
            return (
                "I'm frustrated by the circularity in much of the literature on "
                "collective sensemaking. Papers cite each other's frameworks without "
                "grounding them in observable behavior. The field needs more empirical "
                "work and fewer meta-theoretical gestures."
            )

        if "COVET" in content or "ADMIRE" in content:
            return (
                "I admire the methodological clarity of network science — the way it "
                "transforms vague claims about 'influence' into measurable graph "
                "properties. I want that precision for epistemic norms."
            )

        return self.rng.choice(RESEARCH_OUTPUTS)
