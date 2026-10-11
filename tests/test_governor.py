import pytest

from core.governor import BUDGET_EXCEEDED, RELEVANCE_FLOOR, Governor, TFIDFScorer
from core.proto.trilith_pb2 import ContextItem, Tier


class MockStore:
    def __init__(self, items):
        self.items = items

    def query(self, filter="", budget_tokens=0, scope=""):
        return self.items


def test_token_estimation():
    gov = Governor()
    item1 = ContextItem(content="abcd")  # 4 chars -> 1 token
    item2 = ContextItem(content="abcdefgh")  # 8 chars -> 2 tokens
    item3 = ContextItem(content="")  # 0 chars -> 0 tokens

    assert gov.estimate_tokens(item1) == 4
    assert gov.estimate_tokens(item2) == 8
    assert gov.estimate_tokens(item3) == 0


def test_budget_never_exceeded():
    item1 = ContextItem(id="1", content="hello world!", tier=Tier.SEMANTIC)  # 12 chars -> 3 tokens
    item2 = ContextItem(
        id="2", content="hello world, a longer test content for unit testing", tier=Tier.SEMANTIC
    )  # 51 chars -> 12 tokens

    store = MockStore([item1, item2])
    gov = Governor(semantic_store=store)

    # Fit with budget of 5. Only item1 (3 tokens) should fit.
    assembled = gov.assemble(task="hello", budget=20)

    assert len(assembled.items) == 1
    assert assembled.items[0].id == "1"
    assert assembled.tokens_used == 12
    assert len(assembled.excluded_items) == 1
    assert assembled.excluded_items[0].item.id == "2"
    assert assembled.excluded_items[0].reason == BUDGET_EXCEEDED


def test_higher_relevance_preferred():
    item_low = ContextItem(
        id="low", content="database sharding notes kept for the archive", tier=Tier.SEMANTIC
    )  # 44 chars -> 11 tokens
    item_high = ContextItem(
        id="high",
        content="database partition strategy and indexing rules for Postgres",
        tier=Tier.SEMANTIC,
    )  # 60 chars -> 15 tokens

    store = MockStore([item_low, item_high])
    gov = Governor(semantic_store=store)

    # Target budget fits either one, but not both.
    assembled = gov.assemble(task="database partition", budget=64)

    assert len(assembled.items) == 1
    assert assembled.items[0].id == "high"
    assert len(assembled.excluded_items) == 1
    assert assembled.excluded_items[0].item.id == "low"
    assert assembled.excluded_items[0].reason == BUDGET_EXCEEDED


def test_distraction_penalty():
    # Query: "routing algorithm"
    # item_task: Specific to routing algorithm
    # item_distractor: Highly similar to other network docs in the corpus, but less specific to algorithm
    item_task = ContextItem(
        id="task_match", content="shortest path routing algorithm in graphs", tier=Tier.SEMANTIC
    )
    item_distractor = ContextItem(
        id="distractor",
        content="network routing protocol and packet routing data",
        tier=Tier.SEMANTIC,
    )
    other1 = ContextItem(
        id="o1", content="network protocols for transmitting data packets", tier=Tier.SEMANTIC
    )
    other2 = ContextItem(
        id="o2", content="ip packet routing and routing tables in network", tier=Tier.SEMANTIC
    )

    store = MockStore([other1, other2, item_task, item_distractor])
    gov = Governor(semantic_store=store, distraction_coef=1.0)

    assembled = gov.assemble(task="routing algorithm", budget=100)

    ids = [item.id for item in assembled.items]
    # 'task_match' must be preferred over 'distractor' because 'distractor' is down-ranked due to distraction penalty
    assert ids[0] == "task_match"


# --- The cosine numerator summed over a list of query tokens ---------------


def test_similarity_is_unchanged_when_a_query_term_repeats():
    """A repeated word says nothing new; it used to multiply the score.

    Summing over `task_tokens` counted a term once per occurrence, so
    "python python" scored twice "python" - and produced values above 1.0,
    which no cosine can take.
    """
    scorer = TFIDFScorer()
    candidates = [
        ContextItem(id="a", content="python duckdb data", tier=Tier.SEMANTIC),
        ContextItem(id="b", content="sailing boats harbour", tier=Tier.SEMANTIC),
    ]

    once = scorer.score(candidates, "python")
    twice = scorer.score(candidates, "python python")
    thrice = scorer.score(candidates, "python python python")

    assert once == twice == thrice
    assert all(0.0 <= value <= 1.0 for value in once)


def test_similarity_stays_within_bounds_for_a_repetitive_query():
    scorer = TFIDFScorer()
    candidates = [ContextItem(id="a", content="the cat sat on the mat", tier=Tier.SEMANTIC)]

    assert all(0.0 <= value <= 1.0 for value in scorer.score(candidates, "the the the cat"))


# --- The relevance floor ---------------------------------------------------


def _noise_store():
    return MockStore(
        [
            ContextItem(
                id="relevant",
                content="Alice prefers Python and duckdb for data work",
                tier=Tier.SEMANTIC,
            ),
            ContextItem(
                id="noise", content="The fire drill is scheduled for Tuesday", tier=Tier.SEMANTIC
            ),
        ]
    )


def test_irrelevant_items_are_dropped_even_when_they_fit():
    """The budget used to be the only gate, so slack was filled with noise."""
    gov = Governor(semantic_store=_noise_store())

    assembled = gov.assemble(task="What does Alice prefer?", budget=10_000)

    assert [item.id for item in assembled.items] == ["relevant"]
    dropped = assembled.excluded_items[0]
    assert dropped.item.id == "noise"
    assert dropped.reason.startswith(RELEVANCE_FLOOR)


def test_the_floor_says_it_was_the_floor_and_not_the_budget():
    """An item nobody asked for is not a budget problem."""
    gov = Governor(semantic_store=_noise_store())

    assembled = gov.assemble(task="What does Alice prefer?", budget=1)

    reasons = {ex.item.id: ex.reason for ex in assembled.excluded_items}
    assert reasons["noise"].startswith(RELEVANCE_FLOOR)
    assert reasons["relevant"] == BUDGET_EXCEEDED


def test_the_floor_can_be_opened_all_the_way():
    """Pre-0.2 behaviour stays available: admit anything that fits."""
    gov = Governor(semantic_store=_noise_store(), min_score=float("-inf"))

    assembled = gov.assemble(task="What does Alice prefer?", budget=10_000)

    assert {item.id for item in assembled.items} == {"relevant", "noise"}
    assert list(assembled.excluded_items) == []


def test_a_task_with_no_terms_admits_nothing():
    """No task means no evidence of relevance for anything - and it says so."""
    gov = Governor(semantic_store=_noise_store())

    assembled = gov.assemble(task="", budget=10_000)

    assert list(assembled.items) == []
    assert len(assembled.excluded_items) == 2
    assert all(ex.reason.startswith(RELEVANCE_FLOOR) for ex in assembled.excluded_items)


def test_every_candidate_is_still_accounted_for():
    """Adding a gate must not lose items from the audit."""
    gov = Governor(semantic_store=_noise_store())

    assembled = gov.assemble(task="Alice", budget=3)

    seen = [i.id for i in assembled.items] + [ex.item.id for ex in assembled.excluded_items]
    assert sorted(seen) == ["noise", "relevant"]


# --- A missing budget ------------------------------------------------------


def test_assemble_names_a_missing_budget():
    """It used to fail inside the fill loop with a TypeError about NoneType."""
    gov = Governor(semantic_store=_noise_store())

    with pytest.raises(ValueError, match="budget"):
        gov.assemble(task="Alice", budget=None)


# --- Reaching the floor from a deployment ----------------------------------


def test_the_floor_is_configurable_from_the_environment(monkeypatch):
    """The escape hatch has to be reachable by whoever runs the server.

    `trilith serve` builds the Governor itself, so a floor that could only be
    set by constructing one in Python would not be an escape hatch at all.
    """
    from core.runtime import DEFAULT_MIN_SCORE, build_runtime, resolve_min_score

    monkeypatch.delenv("TRILITH_MIN_SCORE", raising=False)
    assert resolve_min_score() == DEFAULT_MIN_SCORE
    assert build_runtime(":memory:").governor.min_score == DEFAULT_MIN_SCORE

    monkeypatch.setenv("TRILITH_MIN_SCORE", "-inf")
    assert resolve_min_score() == float("-inf")
    assert build_runtime(":memory:").governor.min_score == float("-inf")

    monkeypatch.setenv("TRILITH_MIN_SCORE", "0.05")
    assert resolve_min_score() == 0.05

    # An explicit argument beats the environment.
    assert resolve_min_score(0.5) == 0.5
    assert build_runtime(":memory:", min_score=0.5).governor.min_score == 0.5


def test_an_unparseable_floor_is_rejected_loudly(monkeypatch):
    from core.runtime import resolve_min_score

    monkeypatch.setenv("TRILITH_MIN_SCORE", "very relevant please")
    with pytest.raises(ValueError, match="TRILITH_MIN_SCORE"):
        resolve_min_score()
