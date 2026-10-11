from dataclasses import replace

import pytest

from core.identity import Principal
from core.lineage import Evidence, Requirement, Scenario, WitnessProblem, assemble_witnesses
from core.proto.trilith_pb2 import ContextItem, Scope
from core.runtime import build_runtime


def ev(name, facts, source="root", cost=1):
    return Evidence(("t", name), cost, frozenset(facts), frozenset({("t", source)}))


def req(*facts):
    return Requirement("goal", (frozenset(facts),))


def test_bundle_escapes_zero_singleton_gain():
    p = WitnessProblem([ev("a", ["x"]), ev("b", ["y"])], [req("x", "y")], [Scenario("ok", 1)], 2)
    assert p.solve(max_bundle=1, complete_witnesses=False).expected_utility == 0
    assert p.solve(max_bundle=2).expected_utility == 1
    assert p.solve().keys == p.oracle().keys


def test_shared_lineage_does_not_count_as_independent_survival():
    p = WitnessProblem(
        [ev("a", ["x"]), ev("b", ["x"])],
        [req("x")],
        [Scenario("ok", 0.5), Scenario("lost", 0.5, frozenset({("t", "root")}))],
        2,
    )
    assert p.value({0, 1}) == 0.5
    assert p.value({0}) == 0.5


def test_independent_alternative_can_be_worth_the_budget():
    p = WitnessProblem(
        [ev("a", ["x"], "root"), ev("b", ["x"], "other")],
        [req("x")],
        [
            Scenario("first", 0.5, frozenset({("t", "root")})),
            Scenario("second", 0.5, frozenset({("t", "other")})),
        ],
        2,
    )
    assert len(p.solve().keys) == 2
    assert p.solve().expected_utility == 1


def test_fact_label_bijection_invariance():
    evidence = [ev("a", ["x"]), ev("b", ["y"])]
    a = WitnessProblem(evidence, [req("x", "y")], [Scenario("ok", 1)], 2).solve()
    mapping = {"x": "数据库", "y": "یادداشت"}
    translated = [replace(e, facts=frozenset(mapping[f] for f in e.facts)) for e in evidence]
    b = WitnessProblem(translated, [req(*mapping.values())], [Scenario("ok", 1)], 2).solve()
    assert a.keys == b.keys and a.expected_utility == b.expected_utility


def test_chain_completion_repairs_bounded_bundle_failure():
    p = WitnessProblem(
        [ev(str(i), [str(i)]) for i in range(4)], [req("0", "1", "2", "3")], [Scenario("ok", 1)], 4
    )
    assert p.solve(max_bundle=3, complete_witnesses=False).expected_utility == 0
    assert p.solve().expected_utility == 1
    assert p.oracle().expected_utility == 1


def test_invalid_input_fails_closed():
    with pytest.raises(ValueError, match="sum to one"):
        WitnessProblem([], [], [Scenario("bad", 0.4)], 1)
    with pytest.raises(ValueError, match="positive"):
        WitnessProblem([ev("bad", [], cost=0)], [], [Scenario("ok", 1)], 1)
    p = WitnessProblem([ev(str(i), [str(i)]) for i in range(25)], [], [Scenario("ok", 1)], 4)
    with pytest.raises(ValueError, match="24"):
        p.solve()


def test_embedded_entry_point_checks_policy_and_derived_ancestors():
    rt = build_runtime(":memory:")
    for name, owner in (("mine", "alice"), ("private", "bob"), ("derived", "alice")):
        rt.semantic.write(
            ContextItem(id=name, content="fact", tenant_id="t", owner_id=owner, scope=Scope.USER)
        )
    with rt.backend.transaction():
        rt.backend.inner.conn.execute(
            "INSERT INTO derived_sources VALUES ('t','private','derived')"
        )
    result, selection = assemble_witnesses(
        rt,
        Principal("t", "alice"),
        {"mine": {"x"}, "private": {"y"}, "derived": {"y"}},
        [req("x")],
        [Scenario("ok", 1)],
        100,
    )
    assert [i.id for i in result.items] == ["mine"]
    assert selection.expected_utility == 1
