"""LCWP mechanism experiment with exact small-instance oracle and ablations.

These are fully specified synthetic optimization instances, not LLM task scores.
Includes stable inputs, correlated failures, a misspecified failure distribution,
and a four-hop witness requiring explicit completion beyond bounded bundles.
"""

import argparse
import hashlib
import json
import platform
import random
import statistics
import time
from dataclasses import asdict
from pathlib import Path

from core.lineage import Evidence, Requirement, Scenario, WitnessProblem
from core.proto.trilith_pb2 import ContextItem
from core.retrieval import pack


def cases(seed):
    rng = random.Random(seed)
    evidence = []
    for i in range(4):
        evidence.append(
            Evidence(
                ("t", f"raw{i}"),
                rng.randint(2, 4),
                frozenset({f"fact{i}"}),
                frozenset({("t", f"source{i // 2}")}),
            )
        )
    for i in range(4):
        evidence.append(
            Evidence(
                ("t", f"alt{i}"),
                rng.randint(3, 5),
                frozenset({f"fact{i}"}),
                frozenset({("t", f"alt_source{i}")}),
            )
        )
    evidence.append(
        Evidence(
            ("t", "summary"),
            rng.randint(3, 6),
            frozenset({"fact0", "fact1", "fact2"}),
            frozenset({("t", "source0"), ("t", "source1")}),
        )
    )
    requirements = [
        Requirement("chain0", (frozenset({"fact0", "fact1"}),), 1.0),
        Requirement("chain1", (frozenset({"fact2", "fact3"}),), 0.8),
    ]
    risky = [
        Scenario("none", 0.2),
        Scenario("source0", 0.4, frozenset({("t", "source0")})),
        Scenario("source1", 0.2, frozenset({("t", "source1")})),
        Scenario("both", 0.2, frozenset({("t", "source0"), ("t", "source1")})),
    ]
    stable = [Scenario("none", 1.0)]
    wrong = [
        Scenario("none", 0.2),
        Scenario("alternatives", 0.8, frozenset(("t", f"alt_source{i}") for i in range(4))),
    ]
    for budget in (6, 10, 14):
        yield "stable", evidence, requirements, stable, stable, budget
        yield "correlated", evidence, requirements, risky, risky, budget
        yield "misspecified", evidence, requirements, risky, wrong, budget
    # An intentional hard boundary; retain it even though it makes LCWP lose.
    chain = [Evidence(("t", str(i)), 1, frozenset({str(i)}), frozenset()) for i in range(4)]
    yield (
        "long_chain",
        chain,
        [Requirement("all", (frozenset(map(str, range(4))),))],
        stable,
        stable,
        4,
    )


def choose(evidence, requirements, scenarios, budget, method):
    problem = WitnessProblem(evidence, requirements, scenarios, budget)
    if method == "oracle":
        return problem.oracle()
    if method == "lcwp":
        return problem.solve()
    if method == "singletons":
        return problem.solve(max_bundle=1, complete_witnesses=False)
    if method == "bounded_bundles":
        return problem.solve(complete_witnesses=False)
    if method == "no_lineage":
        return WitnessProblem(evidence, requirements, [Scenario("none", 1.0)], budget).solve()
    if method == "tpcc":
        evidence = problem.evidence
        query = set().union(*(w for r in requirements for w in r.witnesses))
        items = [
            ContextItem(id=e.key[1], tenant_id=e.key[0], content=" ".join(sorted(e.facts)))
            for e in evidence
        ]
        scores = [len(e.facts & query) / max(1, len(query)) for e in evidence]
        costs = {e.key: e.cost for e in evidence}
        chosen = pack(
            items, scores, " ".join(sorted(query)), budget, lambda i: costs[(i.tenant_id, i.id)]
        )
        return problem.result(chosen)
    raise ValueError(method)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--seeds", type=int, default=20)
    parser.add_argument("--output", default="benchmarks/lineage-results.json")
    args = parser.parse_args()
    if args.seeds < 1:
        parser.error("seeds must be positive")
    trials = []
    for seed in range(args.seeds):
        for case_id, (regime, evidence, requirements, train, test, budget) in enumerate(
            cases(seed)
        ):
            actual = WitnessProblem(evidence, requirements, test, budget)
            oracle = actual.oracle()
            for method in ("tpcc", "singletons", "bounded_bundles", "no_lineage", "lcwp", "oracle"):
                started = time.perf_counter()
                result = choose(
                    evidence, requirements, test if method == "oracle" else train, budget, method
                )
                elapsed = (time.perf_counter() - started) * 1000
                indices = {i for i, e in enumerate(actual.evidence) if e.key in result.keys}
                value = actual.value(indices)
                trials.append(
                    dict(
                        seed=seed,
                        case_id=case_id,
                        regime=regime,
                        method=method,
                        budget=budget,
                        cost=result.cost,
                        actual_utility=value,
                        oracle_utility=oracle.expected_utility,
                        regret=oracle.expected_utility - value,
                        normalized_utility=(
                            value / oracle.expected_utility if oracle.expected_utility else 1.0
                        ),
                        latency_ms=elapsed,
                        selection=asdict(result),
                    )
                )
    summary = {}
    paired = {}
    for regime in sorted({r["regime"] for r in trials}):
        summary[regime] = {}
        for method in ("tpcc", "singletons", "bounded_bundles", "no_lineage", "lcwp", "oracle"):
            rows = [r for r in trials if r["regime"] == regime and r["method"] == method]
            summary[regime][method] = {
                key: statistics.mean(r[key] for r in rows)
                for key in ("actual_utility", "regret", "normalized_utility", "cost", "latency_ms")
            }
        for baseline in ("tpcc", "singletons", "bounded_bundles", "no_lineage"):
            differences = []
            for seed in range(args.seeds):
                rows = [r for r in trials if r["regime"] == regime and r["seed"] == seed]
                differences.append(
                    statistics.mean(r["actual_utility"] for r in rows if r["method"] == "lcwp")
                    - statistics.mean(r["actual_utility"] for r in rows if r["method"] == baseline)
                )
            rng = random.Random(0)
            means = sorted(
                statistics.mean(rng.choices(differences, k=len(differences))) for _ in range(1000)
            )
            paired[f"{regime}:{baseline}"] = dict(
                mean_difference=statistics.mean(differences),
                seed_bootstrap_95=[means[25], means[974]],
            )
    report = dict(
        schema_version=1,
        algorithm="LCWP-v2",
        dataset="synthetic-witness-lineage",
        seeds=args.seeds,
        python=platform.python_version(),
        source_sha256={
            str(p): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (Path(__file__), Path("core/lineage.py"), Path("core/retrieval.py"))
        },
        summary=summary,
        paired_comparisons=paired,
        trials=trials,
        limitations="Oracle fact/witness annotations; synthetic failure scenarios; no natural-language extraction or downstream model. Misspecification and bounded-bundle failure cases retained.",
    )
    Path(args.output).write_text(json.dumps(report, indent=2), encoding="utf8")
    print(json.dumps(dict(summary=summary, paired_comparisons=paired), indent=2))


if __name__ == "__main__":
    main()
