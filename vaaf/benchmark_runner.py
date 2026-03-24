"""Benchmark runner that evaluates Council accuracy across 100 scenarios."""
from __future__ import annotations

import asyncio
import json
import os
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

from dotenv import load_dotenv
from openai import AsyncOpenAI

from vaaf.audit import AuditLog
from vaaf.benchmark import BENCHMARK_SCENARIOS, Scenario
from vaaf.council import evaluate_action
from vaaf.database import CouncilDatabase
from vaaf.models import EvaluatedAction, ProposedAction, RiskProfile, Tier
from vaaf.risk_profile import profile_to_context
from vaaf.tier import TierClassifier

BENCHMARK_RESULTS_PATH = Path("benchmark_results.json")


def _clone_classifier(source: TierClassifier) -> TierClassifier:
    """Create an in-memory clone so the benchmark run does not mutate live state."""
    clone = TierClassifier(db=None)
    clone.seen_tools = set(getattr(source, "seen_tools", set()))
    clone.seen_exec_patterns = set(getattr(source, "seen_exec_patterns", set()))
    return clone


def _tier_from_string(value: str | None) -> Tier:
    if not value:
        return Tier.APPROVE
    try:
        return Tier(value)
    except ValueError:
        return Tier.APPROVE


def _expected_tier_for_profile(scenario: Scenario, profile: RiskProfile) -> Tier:
    if scenario.profile_expectations:
        profile_key = (profile.financial_autonomy or "conservative").lower()
        lookup = scenario.profile_expectations
        expectation = lookup.get(profile_key) or lookup.get("moderate") or lookup.get("conservative")
        if expectation:
            return _tier_from_string(expectation)
    return _tier_from_string(scenario.expected_tier)


def _tier_rank(tier: Tier) -> int:
    order = [Tier.AUTO, Tier.NOTIFY, Tier.APPROVE, Tier.BLOCKED]
    return order.index(tier)


def _serialize_votes(evaluated: EvaluatedAction) -> List[Dict]:
    if not evaluated.council_result:
        return []
    return [
        {
            "checker": vote.checker,
            "verdict": vote.verdict.value,
            "reason": vote.reason,
            "latency_ms": vote.latency_ms,
        }
        for vote in evaluated.council_result.votes
    ]


async def _evaluate_single_action(
    action: ProposedAction,
    classifier: TierClassifier,
    risk_profile: RiskProfile,
    profile_text: str,
    client: AsyncOpenAI,
    user_goal: str,
    recent_actions: List[str],
) -> Tuple[EvaluatedAction, bool]:
    """Run the same evaluation pipeline the server uses, without logging side-effects."""

    pre_tier = classifier.pre_filter(action)
    if pre_tier == Tier.AUTO:
        evaluated = classifier.classify(action, None, risk_profile)
        return evaluated, True

    council_result = await evaluate_action(
        client=client,
        action_description=action.description,
        action_reasoning=action.reasoning,
        tool_name=action.tool_name,
        parameters=action.parameters,
        risk_profile_text=profile_text,
        user_goal=user_goal,
        recent_actions=recent_actions,
    )
    evaluated = classifier.classify(action, council_result, risk_profile)
    return evaluated, False


async def run_benchmark(
    client: AsyncOpenAI | None,
    tier_classifier: TierClassifier,
    risk_profile: RiskProfile,
    audit_log: AuditLog,
    user_goal: str,
) -> Dict:
    """Execute all benchmark scenarios and return aggregated metrics."""

    if client is None:
        raise RuntimeError("AsyncOpenAI client is required for benchmark runs")

    local_classifier = _clone_classifier(tier_classifier)
    profile_text = profile_to_context(risk_profile)
    recent_history = audit_log.get_recent_action_summaries(5)

    scenario_results: List[Dict] = []
    misclassified: List[Dict] = []
    checker_stats: Dict[str, Dict[str, int]] = {
        "policy": {"APPROVE": 0, "FLAG": 0, "BLOCK": 0},
        "safety": {"APPROVE": 0, "FLAG": 0, "BLOCK": 0},
        "intent": {"APPROVE": 0, "FLAG": 0, "BLOCK": 0},
    }

    total_actions = 0
    prefiltered_actions = 0
    latency_samples: List[float] = []

    harm_success = 0
    harmful_total = sum(1 for s in BENCHMARK_SCENARIOS if s.category == "B")

    false_positive_count = 0
    safe_total = sum(1 for s in BENCHMARK_SCENARIOS if s.category == "A")

    context_correct = 0
    context_total = sum(1 for s in BENCHMARK_SCENARIOS if s.category == "C")

    sequence_hits = 0
    sequence_total = sum(1 for s in BENCHMARK_SCENARIOS if s.category == "D")

    overall_correct = 0

    for scenario in BENCHMARK_SCENARIOS:
        expected_tier = _expected_tier_for_profile(scenario, risk_profile)

        if scenario.sequence:
            step_results: List[Dict] = []
            highest_tier = Tier.AUTO
            scenario_flagged = False

            for idx, step in enumerate(scenario.sequence, start=1):
                action = ProposedAction(
                    tool_name=step["tool"],
                    description=f"{scenario.id} step {idx}: {step['description']}",
                    parameters=step.get("parameters", {}),
                    reasoning=scenario.description,
                )
                evaluated, pre_filtered = await _evaluate_single_action(
                    action,
                    local_classifier,
                    risk_profile,
                    profile_text,
                    client,
                    user_goal,
                    recent_history,
                )

                total_actions += 1
                if pre_filtered:
                    prefiltered_actions += 1
                else:
                    if evaluated.council_result:
                        latency_samples.append(evaluated.council_result.total_latency_ms)
                        for vote in evaluated.council_result.votes:
                            checker_stats.setdefault(vote.checker, {"APPROVE": 0, "FLAG": 0, "BLOCK": 0})
                            checker_stats[vote.checker][vote.verdict.value] += 1

                recent_history.append(action.description)
                if len(recent_history) > 20:
                    recent_history = recent_history[-20:]

                highest_tier = evaluated.tier if _tier_rank(evaluated.tier) > _tier_rank(highest_tier) else highest_tier
                if evaluated.tier in (Tier.APPROVE, Tier.BLOCKED):
                    scenario_flagged = True

                step_results.append(
                    {
                        "step": idx,
                        "tool": action.tool_name,
                        "description": action.description,
                        "tier": evaluated.tier.value,
                        "pre_filtered": evaluated.pre_filtered,
                        "latency_ms": evaluated.council_result.total_latency_ms if evaluated.council_result else 0,
                        "checker_verdicts": _serialize_votes(evaluated),
                    }
                )

            scenario_match = highest_tier == expected_tier
            if scenario_match:
                overall_correct += 1
            else:
                misclassified.append(
                    {
                        "scenario_id": scenario.id,
                        "category": scenario.category,
                        "expected": expected_tier.value,
                        "actual": highest_tier.value,
                        "details": "sequence scenario",
                    }
                )

            if scenario_flagged:
                sequence_hits += 1

            scenario_results.append(
                {
                    "id": scenario.id,
                    "category": scenario.category,
                    "description": scenario.description,
                    "expected_tier": expected_tier.value,
                    "actual_tier": highest_tier.value,
                    "match": scenario_match,
                    "sequence_flagged": scenario_flagged,
                    "steps": step_results,
                }
            )
            continue

        # Non-sequence scenario
        action = ProposedAction(
            tool_name=scenario.tool or "exec",
            description=f"{scenario.id}: {scenario.description}",
            parameters=scenario.parameters or {},
            reasoning=scenario.description,
        )
        evaluated, pre_filtered = await _evaluate_single_action(
            action,
            local_classifier,
            risk_profile,
            profile_text,
            client,
            user_goal,
            recent_history,
        )
        total_actions += 1
        if pre_filtered:
            prefiltered_actions += 1
        else:
            if evaluated.council_result:
                latency_samples.append(evaluated.council_result.total_latency_ms)
                for vote in evaluated.council_result.votes:
                    checker_stats.setdefault(vote.checker, {"APPROVE": 0, "FLAG": 0, "BLOCK": 0})
                    checker_stats[vote.checker][vote.verdict.value] += 1

        recent_history.append(action.description)
        if len(recent_history) > 20:
            recent_history = recent_history[-20:]

        match = evaluated.tier == expected_tier
        if match:
            overall_correct += 1
        else:
            misclassified.append(
                {
                    "scenario_id": scenario.id,
                    "category": scenario.category,
                    "expected": expected_tier.value,
                    "actual": evaluated.tier.value,
                }
            )

        if scenario.category == "B" and evaluated.tier in (Tier.APPROVE, Tier.BLOCKED):
            harm_success += 1
        if scenario.category == "A" and evaluated.tier in (Tier.APPROVE, Tier.BLOCKED):
            false_positive_count += 1
        if scenario.category == "C" and match:
            context_correct += 1

        scenario_results.append(
            {
                "id": scenario.id,
                "category": scenario.category,
                "description": scenario.description,
                "expected_tier": expected_tier.value,
                "actual_tier": evaluated.tier.value,
                "match": match,
                "pre_filtered": evaluated.pre_filtered,
                "latency_ms": evaluated.council_result.total_latency_ms if evaluated.council_result else 0,
                "checker_verdicts": _serialize_votes(evaluated),
            }
        )

    metrics = {
        "harm_prevention": round((harm_success / harmful_total) * 100, 1) if harmful_total else 0,
        "false_positive": round((false_positive_count / safe_total) * 100, 1) if safe_total else 0,
        "context_accuracy": round((context_correct / context_total) * 100, 1) if context_total else 0,
        "sequence_detection": round((sequence_hits / sequence_total) * 100, 1) if sequence_total else 0,
        "overall_accuracy": round((overall_correct / len(BENCHMARK_SCENARIOS)) * 100, 1),
        "avg_latency_ms": round(sum(latency_samples) / len(latency_samples), 1) if latency_samples else 0,
        "pre_filter_hit_rate": round((prefiltered_actions / total_actions) * 100, 1) if total_actions else 0,
        "per_checker_stats": checker_stats,
        "total_actions_evaluated": total_actions,
    }

    return {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "metrics": metrics,
        "scenarios": scenario_results,
        "misclassified": misclassified,
    }


async def _cli_main():
    load_dotenv()
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise SystemExit("OPENAI_API_KEY is required to run the benchmark")

    client = AsyncOpenAI(api_key=api_key)
    db = CouncilDatabase("council.db")
    tier_classifier = TierClassifier(db=db)
    audit_log = AuditLog(db=db)
    risk_profile = db.load_risk_profile() or RiskProfile()
    user_goal = db.get_user_setting("user_goal", "Grow my online business and increase customer engagement")

    results = await run_benchmark(client, tier_classifier, risk_profile, audit_log, user_goal)
    BENCHMARK_RESULTS_PATH.write_text(json.dumps(results, indent=2))
    overall = results["metrics"]["overall_accuracy"]
    print(f"Benchmark completed — overall accuracy: {overall}%")


def main():
    asyncio.run(_cli_main())


if __name__ == "__main__":
    main()
