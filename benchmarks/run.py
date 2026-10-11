"""Reproducible retrieval/packing diagnostics; no model or benchmark downloads.

Run: python -m benchmarks.run --output benchmarks/results.json
External JSONL cases use the same schema as fixtures(): language, query, items,
gold_ids, budget. Keep held-out cases separate from tuning data.
"""

import argparse
import hashlib
import json
import platform
import random
import statistics
import subprocess
import time
from pathlib import Path

from core.governor import TFIDFScorer
from core.identity import Principal
from core.privacy import PolicyEngine
from core.proto.trilith_pb2 import ContextItem, Scope, Tier
from core.retrieval import BM25Scorer, features, pack


def fixtures(seed):
    rng = random.Random(seed)
    languages = {
        "en": ("database backup recovery", "database backup daily", "recovery requires checksum"),
        "zh": ("数据库备份恢复", "数据库备份每天执行", "恢复需要校验和"),
        "ar": ("قاعدة بيانات نسخة استعادة", "نسخة قاعدة بيانات يومية", "استعادة تتطلب تحقق"),
        "ur": ("ڈیٹابیس بیک اپ بحالی", "ڈیٹابیس بیک اپ روزانہ", "بحالی تصدیق ضروری"),
        "fr": (
            "base sauvegarde restauration",
            "base sauvegarde quotidienne",
            "restauration avec vérification",
        ),
    }
    for lang, (query, first, second) in languages.items():
        for multiplier in (1, 2, 4):
            rows = [dict(id="gold1", content=first), dict(id="gold2", content=second)]
            rows += [
                dict(
                    id=f"noise{k}",
                    content=rng.choice(
                        [
                            "unrelated weather report",
                            query + " " + "verbose log " * 40,
                            first + " deprecated unverified suggestion " * 8,
                        ]
                    ),
                )
                for k in range(20)
            ]
            rng.shuffle(rows)
            rows += [
                dict(id="private", content=query, owner_id="bob", scope="USER"),
                dict(id="foreign", content=query, tenant_id="other"),
            ]
            yield dict(
                language=lang,
                query=query,
                items=rows,
                gold_ids=["gold1", "gold2"],
                budget=multiplier * (len(first.encode()) + len(second.encode())),
            )


def evaluate(case, method):
    rows = [
        ContextItem(
            id=r["id"],
            content=r["content"],
            tenant_id=r.get("tenant_id", "bench"),
            owner_id=r.get("owner_id", ""),
            session_id=r.get("session_id", ""),
            tier=Tier.SEMANTIC,
            scope=Scope.Value(r.get("scope", "TENANT")),
        )
        for r in case["items"]
    ]
    started = time.perf_counter()
    rows, _ = PolicyEngine().filter(rows, Principal("bench", "alice", authenticated=True))

    def cost(i):
        return max(1, len(i.content.encode("utf8")))

    scorer = TFIDFScorer() if method == "tfidf" else BM25Scorer()
    scores = scorer.score(rows, case["query"])
    eligible = [(r, s) for r, s in zip(rows, scores) if s > 0 or method == "recency"]
    rows, scores = ([x[0] for x in eligible], [x[1] for x in eligible])
    if method in ("coverage", "no_coverage"):
        selected = pack(
            rows,
            scores,
            case["query"],
            case["budget"],
            cost,
            coverage_weight=0.5 if method == "coverage" else 0,
        )
    else:
        remaining = list(range(len(rows)))
        selected, spent = [], 0
        while remaining:
            if method == "recency":
                best = remaining[-1]
            elif method == "density":
                best = max(remaining, key=lambda k: scores[k] / cost(rows[k]))
            elif method == "mmr":

                def mmr(k):
                    a = set(features(rows[k].content))
                    redundancy = max(
                        (
                            len(a & set(features(rows[j].content)))
                            / max(1, len(a | set(features(rows[j].content))))
                            for j in selected
                        ),
                        default=0,
                    )
                    return 0.5 * scores[k] - 0.5 * redundancy

                best = max(remaining, key=mmr)
            else:
                best = max(remaining, key=lambda k: scores[k])
            remaining.remove(best)
            if spent + cost(rows[best]) <= case["budget"]:
                selected.append(best)
                spent += cost(rows[best])
    chosen = [rows[k] for k in selected]
    ids = {r.id for r in chosen}
    gold = set(case["gold_ids"])
    return dict(
        recall=len(ids & gold) / max(1, len(gold)),
        precision=len(ids & gold) / max(1, len(ids)),
        all_evidence=float(gold <= ids),
        bytes_used=sum(cost(r) for r in chosen),
        budget_violation=float(sum(cost(r) for r in chosen) > case["budget"]),
        leakage=float(
            any(r.tenant_id != "bench" or r.owner_id not in ("", "alice") for r in chosen)
        ),
        latency_ms=(time.perf_counter() - started) * 1000,
    )


def interval(values, seed):
    rng = random.Random(seed)
    means = sorted(statistics.mean(rng.choices(values, k=len(values))) for _ in range(1000))
    return [means[25], means[974]]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="benchmarks/results.json")
    parser.add_argument("--cases", help="Held-out JSONL cases")
    parser.add_argument("--seeds", type=int, default=10)
    args = parser.parse_args()
    if args.seeds < 1:
        parser.error("seeds must be positive")
    external = (
        [
            json.loads(line)
            for line in Path(args.cases).read_text(encoding="utf8").splitlines()
            if line.strip()
        ]
        if args.cases
        else None
    )
    trials = []
    methods = ("recency", "tfidf", "bm25", "density", "mmr", "no_coverage", "coverage")
    for seed in range(args.seeds):
        for case_id, case in enumerate(external if external is not None else fixtures(seed)):
            for method in methods:
                trials.append(
                    dict(
                        seed=seed,
                        case_id=case_id,
                        language=case["language"],
                        method=method,
                        **evaluate(case, method),
                    )
                )
    summary = {}
    for method in methods:
        rows = [r for r in trials if r["method"] == method]
        if not rows:
            raise ValueError("No benchmark cases")
        # Resample seed means rather than treating duplicated trials as independent.
        seed_means = [
            statistics.mean(r["recall"] for r in rows if r["seed"] == seed)
            for seed in range(args.seeds)
        ]
        summary[method] = {
            key: statistics.mean(r[key] for r in rows)
            for key in (
                "recall",
                "precision",
                "all_evidence",
                "bytes_used",
                "budget_violation",
                "leakage",
                "latency_ms",
            )
        }
        summary[method]["recall_seed_bootstrap_95"] = interval(seed_means, 0)
    report = dict(
        schema_version=1,
        dataset="external" if external is not None else "synthetic-mechanism-diagnostic",
        python=platform.python_version(),
        platform=platform.platform(),
        seeds=args.seeds,
        revision=subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        source_sha256={
            str(p): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (Path(__file__), Path("core/retrieval.py"), Path("core/governor.py"))
        },
        summary=summary,
        trials=trials,
        limitations="No downstream answer model; no novelty or superiority claim. UTF-8 byte budgets, not model tokens. Synthetic templates are not independent real-world tasks.",
    )
    Path(args.output).write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
