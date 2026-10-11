"""Experimental lineage-conditioned witness packing (LCWP).

Unlike lexical coverage, a requirement earns utility only when an entire witness
survives. Shared dependency failures are sampled jointly, never independently
per duplicate. Structured facts, witnesses and probabilities are trusted inputs,
not claims extracted or validated by this module. See docs/algorithm.md.
"""

import math
from dataclasses import dataclass
from itertools import combinations

Key = tuple[str, str]


@dataclass(frozen=True)
class Evidence:
    key: Key
    cost: int
    facts: frozenset[str]
    dependencies: frozenset[Key]


@dataclass(frozen=True)
class Requirement:
    name: str
    witnesses: tuple[frozenset[str], ...]
    weight: float = 1.0


@dataclass(frozen=True)
class Scenario:
    name: str
    probability: float
    revoked: frozenset[Key] = frozenset()


@dataclass(frozen=True)
class Selection:
    keys: tuple[Key, ...]
    cost: int
    expected_utility: float
    scenario_utilities: tuple[float, ...]
    objective_evaluations: int


class WitnessProblem:
    def __init__(self, evidence, requirements, scenarios, budget):
        self.evidence = tuple(sorted(evidence, key=lambda e: e.key))
        self.requirements = tuple(requirements)
        self.scenarios = tuple(scenarios)
        self.budget = budget
        if not isinstance(budget, int) or isinstance(budget, bool) or budget < 0:
            raise ValueError("budget must be a nonnegative integer")
        if len({e.key for e in self.evidence}) != len(self.evidence):
            raise ValueError("Duplicate evidence key")
        if any(
            not isinstance(e.cost, int) or isinstance(e.cost, bool) or e.cost <= 0
            for e in self.evidence
        ):
            raise ValueError("Evidence costs must be positive integers")
        if not self.scenarios or any(
            not math.isfinite(s.probability) or s.probability < 0 for s in self.scenarios
        ):
            raise ValueError("Scenarios require finite nonnegative probabilities")
        if not math.isclose(sum(s.probability for s in self.scenarios), 1.0, abs_tol=1e-9):
            raise ValueError("Scenario probabilities must sum to one")
        if any(
            not math.isfinite(r.weight)
            or r.weight < 0
            or not r.witnesses
            or any(not w for w in r.witnesses)
            for r in self.requirements
        ):
            raise ValueError("Requirements need nonempty witnesses and finite nonnegative weights")
        self._cache = {}

    def cost(self, chosen):
        return sum(self.evidence[i].cost for i in chosen)

    def utilities(self, chosen):
        key = frozenset(chosen)
        if key not in self._cache:
            utilities = []
            for scenario in self.scenarios:
                facts = set()
                for i in key:
                    evidence = self.evidence[i]
                    if (
                        evidence.key not in scenario.revoked
                        and not evidence.dependencies & scenario.revoked
                    ):
                        facts.update(evidence.facts)
                utilities.append(
                    sum(r.weight for r in self.requirements if any(w <= facts for w in r.witnesses))
                )
            self._cache[key] = tuple(utilities)
        return self._cache[key]

    def value(self, chosen):
        return sum(s.probability * u for s, u in zip(self.scenarios, self.utilities(chosen)))

    def result(self, chosen):
        return Selection(
            tuple(self.evidence[i].key for i in sorted(chosen)),
            self.cost(chosen),
            self.value(chosen),
            self.utilities(chosen),
            len(self._cache),
        )

    def completions(self, chosen):
        """Propose complete witnesses, including chains longer than max_bundle.

        For each survival scenario, greedily cover each remaining witness from
        each possible first item. This bounded set-cover heuristic supplies
        atomic additions; it is not an exact minimum-cost witness oracle.
        """
        proposals = set()
        for scenario in self.scenarios:
            active = {
                i
                for i, e in enumerate(self.evidence)
                if e.key not in scenario.revoked and not e.dependencies & scenario.revoked
            }
            present = set().union(*(self.evidence[i].facts for i in chosen & active))
            for requirement in self.requirements:
                for witness in requirement.witnesses:
                    missing = witness - present
                    if not missing:
                        continue
                    candidates = sorted(
                        i for i in active - chosen if self.evidence[i].facts & missing
                    )
                    for seed in [None, *candidates]:
                        addition = set() if seed is None else {seed}
                        uncovered = missing - set().union(
                            *(self.evidence[i].facts for i in addition)
                        )
                        while uncovered:
                            usable = [
                                i
                                for i in candidates
                                if i not in addition and self.evidence[i].facts & uncovered
                            ]
                            if not usable:
                                break
                            best = max(
                                usable,
                                key=lambda i: (
                                    len(self.evidence[i].facts & uncovered) / self.evidence[i].cost,
                                    -self.evidence[i].cost,
                                    -i,
                                ),
                            )
                            addition.add(best)
                            uncovered -= self.evidence[best].facts
                        if not uncovered and self.cost(chosen | addition) <= self.budget:
                            proposals.add(frozenset(addition))
        return proposals

    def solve(self, max_bundle=3, max_candidates=24, complete_witnesses=True):
        """Bounded bundle-density ascent plus best feasible bundle safeguard.

        No submodular approximation guarantee: AND witnesses are complementary.
        Explicitly reject oversized problems rather than silently prune bridges.
        """
        if not isinstance(max_bundle, int) or not 1 <= max_bundle <= 3:
            raise ValueError("max_bundle must be 1, 2, or 3")
        if len(self.evidence) > max_candidates or max_candidates > 24:
            raise ValueError("LCWP research solver supports at most 24 candidates")
        if len(self.scenarios) > 64 or sum(len(r.witnesses) for r in self.requirements) > 64:
            raise ValueError("LCWP supports at most 64 scenarios and 64 witnesses")
        chosen = frozenset()
        all_indices = frozenset(range(len(self.evidence)))
        best_bundle = frozenset()
        while True:
            current = self.value(chosen)
            proposals = []
            additions = self.completions(chosen) if complete_witnesses else set()
            remaining = sorted(all_indices - chosen)
            for size in range(1, min(max_bundle, len(remaining)) + 1):
                for indices in combinations(remaining, size):
                    additions.add(frozenset(indices))
            for addition in sorted(additions, key=lambda a: tuple(sorted(a))):
                if self.cost(chosen | addition) > self.budget:
                    continue
                standalone = self.value(addition)
                if (standalone, -self.cost(addition)) > (
                    self.value(best_bundle),
                    -self.cost(best_bundle),
                ):
                    best_bundle = addition
                gain = self.value(chosen | addition) - current
                if gain > 1e-12:
                    proposals.append(
                        (
                            gain / self.cost(addition),
                            gain,
                            -self.cost(addition),
                            tuple(sorted(addition)),
                        )
                    )
            if not proposals:
                break
            best = max(proposals, key=lambda p: (p[0], p[1], p[2], tuple(-i for i in p[3])))
            chosen |= frozenset(best[3])
        if (self.value(best_bundle), -self.cost(best_bundle)) > (
            self.value(chosen),
            -self.cost(chosen),
        ):
            chosen = best_bundle
        return self.result(chosen)

    def oracle(self):
        """Exhaustive reference, restricted to small experimental instances."""
        if len(self.evidence) > 18:
            raise ValueError("Oracle supports at most 18 candidates")
        best = frozenset()
        for size in range(1, len(self.evidence) + 1):
            for indices in combinations(range(len(self.evidence)), size):
                candidate = frozenset(indices)
                if self.cost(candidate) <= self.budget and (
                    self.value(candidate),
                    -self.cost(candidate),
                ) > (self.value(best), -self.cost(best)):
                    best = candidate
        return self.result(best)


def assemble_witnesses(rt, principal, annotations, requirements, scenarios, budget, max_bundle=3):
    """Trusted embedded experimental entry point; exact item references only.

    annotations maps tenant-local item IDs to canonical fact IDs. The application
    supplies these mappings without reading evaluation labels. Source closure is
    read from storage, not accepted from model arguments. Policy is rechecked
    inside the read transaction for both selected items and all their ancestors.
    """
    from core.proto.trilith_pb2 import AssembledContext

    with rt.backend.transaction():
        candidates, approved = [], {}
        for item_id, facts in annotations.items():
            item = rt.backend.get(item_id, principal.tenant_id)
            if item is None:
                continue
            ancestors = rt.backend.lineage(item_id, principal.tenant_id)
            sources = [rt.backend.get(source_id, principal.tenant_id) for source_id in ancestors]
            if any(
                source is None or not rt.governor.policy_engine.explain(source, principal)[0]
                for source in sources
            ):
                continue
            visible, _ = rt.governor.policy_engine.filter([item], principal)
            if not visible:
                continue
            item = visible[0]
            key = (principal.tenant_id, item_id)
            candidates.append(
                Evidence(
                    key,
                    max(1, rt.governor.estimate_tokens(item)),
                    frozenset(facts),
                    frozenset((principal.tenant_id, source) for source in ancestors),
                )
            )
            approved[key] = item
        problem = WitnessProblem(candidates, requirements, scenarios, budget)
        selection = problem.solve(max_bundle=max_bundle)
        rt.audit.record(
            principal,
            "witness_assemble",
            "completed",
            algorithm="LCWP-v2",
            selected_count=len(selection.keys),
            cost=selection.cost,
            expected_utility=selection.expected_utility,
        )
        return (
            AssembledContext(
                items=[approved[key] for key in selection.keys], tokens_used=selection.cost
            ),
            selection,
        )
