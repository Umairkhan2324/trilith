import pytest
from core.proto.trilith_pb2 import ContextItem, Tier, Scope
from core.governor import Governor, TFIDFScorer

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
    
    assert gov.estimate_tokens(item1) == 1
    assert gov.estimate_tokens(item2) == 2
    assert gov.estimate_tokens(item3) == 0

def test_budget_never_exceeded():
    item1 = ContextItem(id="1", content="hello world!", tier=Tier.SEMANTIC)  # 12 chars -> 3 tokens
    item2 = ContextItem(id="2", content="this is a longer test content for unit testing", tier=Tier.SEMANTIC)  # 46 chars -> 11 tokens
    
    store = MockStore([item1, item2])
    gov = Governor(semantic_store=store)
    
    # Fit with budget of 5. Only item1 (3 tokens) should fit.
    assembled = gov.assemble(task="hello", budget=5)
    
    assert len(assembled.items) == 1
    assert assembled.items[0].id == "1"
    assert assembled.tokens_used == 3
    assert len(assembled.excluded_items) == 1
    assert assembled.excluded_items[0].item.id == "2"
    assert assembled.excluded_items[0].reason == "Exceeded token budget"

def test_higher_relevance_preferred():
    item_low = ContextItem(id="low", content="some random text about cats and dogs eating food", tier=Tier.SEMANTIC)  # 48 chars -> 12 tokens
    item_high = ContextItem(id="high", content="database partition strategy and indexing rules for Postgres", tier=Tier.SEMANTIC)  # 60 chars -> 15 tokens
    
    store = MockStore([item_low, item_high])
    gov = Governor(semantic_store=store)
    
    # Target budget fits either one, but not both.
    assembled = gov.assemble(task="database partition", budget=16)
    
    assert len(assembled.items) == 1
    assert assembled.items[0].id == "high"
    assert len(assembled.excluded_items) == 1
    assert assembled.excluded_items[0].item.id == "low"
    assert assembled.excluded_items[0].reason == "Exceeded token budget"

def test_distraction_penalty():
    # Query: "routing algorithm"
    # item_task: Specific to routing algorithm
    # item_distractor: Highly similar to other network docs in the corpus, but less specific to algorithm
    item_task = ContextItem(id="task_match", content="shortest path routing algorithm in graphs", tier=Tier.SEMANTIC)
    item_distractor = ContextItem(id="distractor", content="network routing protocol and packet routing data", tier=Tier.SEMANTIC)
    other1 = ContextItem(id="o1", content="network protocols for transmitting data packets", tier=Tier.SEMANTIC)
    other2 = ContextItem(id="o2", content="ip packet routing and routing tables in network", tier=Tier.SEMANTIC)
    
    store = MockStore([other1, other2, item_task, item_distractor])
    gov = Governor(semantic_store=store, distraction_coef=1.0)
    
    assembled = gov.assemble(task="routing algorithm", budget=100)
    
    ids = [item.id for item in assembled.items]
    # 'task_match' must be preferred over 'distractor' because 'distractor' is down-ranked due to distraction penalty
    assert ids[0] == "task_match"

