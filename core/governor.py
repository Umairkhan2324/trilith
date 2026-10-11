import math
import re
from abc import ABC, abstractmethod
from collections import Counter
from typing import List, Optional, Tuple, Union

from core.identity import Principal
from core.proto.trilith_pb2 import AssembledContext, ContextItem, ExcludedItem
from core.retrieval import BM25Scorer, pack

# Why an item did not reach the prompt. Gateways group exclusions by these, so
# they are constants rather than literals spelled out at each raise site.
BUDGET_EXCEEDED = "Exceeded token budget"
RELEVANCE_FLOOR = "Below relevance floor"


class Scorer(ABC):
    @abstractmethod
    def score(self, candidates: List[ContextItem], task: str) -> List[float]:
        """Compute relevance scores of candidates with respect to the task.

        Returns:
            A list of float scores, one per candidate.
        """
        pass


class TFIDFScorer(Scorer):
    def score(self, candidates: List[ContextItem], task: str) -> List[float]:
        if not candidates:
            return []

        def tokenize(text: str) -> List[str]:
            return re.findall(r"\w+", text.lower())

        task_tokens = tokenize(task)
        if not task_tokens:
            return [0.0] * len(candidates)

        docs = [tokenize(c.content) for c in candidates]
        num_docs = len(docs)

        # Build vocabulary from candidates and query
        vocab = set(task_tokens)
        for doc in docs:
            vocab.update(doc)

        # Calculate document frequency
        df = Counter()
        for doc in docs:
            for term in set(doc):
                df[term] += 1

        # Smooth IDF
        idf = {}
        for term in vocab:
            count = df[term]
            idf[term] = math.log((num_docs + 1) / (count + 1)) + 1.0

        # Query vector
        task_counter = Counter(task_tokens)
        task_vec = {}
        task_norm_sq = 0.0
        for term, freq in task_counter.items():
            val = freq * idf.get(term, 1.0)
            task_vec[term] = val
            task_norm_sq += val * val
        task_norm = math.sqrt(task_norm_sq)

        scores = []
        for doc in docs:
            doc_counter = Counter(doc)
            doc_vec = {}
            doc_norm_sq = 0.0
            for term, freq in doc_counter.items():
                val = freq * idf.get(term, 1.0)
                doc_vec[term] = val
                doc_norm_sq += val * val
            doc_norm = math.sqrt(doc_norm_sq)

            if task_norm == 0.0 or doc_norm == 0.0:
                scores.append(0.0)
                continue

            # Iterate the query's *distinct* terms. `task_tokens` is a list, so
            # summing over it counted a repeated word once per occurrence and
            # pushed the result above 1.0 - not a similarity at all. `task_vec`
            # is already keyed by distinct term, with the tf weight folded in.
            dot_product = 0.0
            for term, task_weight in task_vec.items():
                dot_product += task_weight * doc_vec.get(term, 0.0)

            scores.append(dot_product / (task_norm * doc_norm))

        return scores

    def compute_pairwise_similarities(self, candidates: List[ContextItem]) -> List[List[float]]:
        """Compute cosine similarity matrix between all pair of candidates."""
        if not candidates:
            return []

        def tokenize(text: str) -> List[str]:
            return re.findall(r"\w+", text.lower())

        docs = [tokenize(c.content) for c in candidates]
        num_docs = len(docs)

        vocab = set()
        for doc in docs:
            vocab.update(doc)

        df = Counter()
        for doc in docs:
            for term in set(doc):
                df[term] += 1

        idf = {}
        for term in vocab:
            count = df[term]
            idf[term] = math.log((num_docs + 1) / (count + 1)) + 1.0

        doc_vectors = []
        doc_norms = []
        for doc in docs:
            doc_counter = Counter(doc)
            vec = {}
            norm_sq = 0.0
            for term, freq in doc_counter.items():
                val = freq * idf.get(term, 1.0)
                vec[term] = val
                norm_sq += val * val
            doc_vectors.append(vec)
            doc_norms.append(math.sqrt(norm_sq))

        matrix = [[0.0] * num_docs for _ in range(num_docs)]
        for i in range(num_docs):
            matrix[i][i] = 1.0
            for j in range(i + 1, num_docs):
                norm_i = doc_norms[i]
                norm_j = doc_norms[j]
                if norm_i == 0.0 or norm_j == 0.0:
                    sim = 0.0
                else:
                    dot_product = 0.0
                    vec_i = doc_vectors[i]
                    vec_j = doc_vectors[j]
                    # Dot product over keys in intersection
                    for term in set(vec_i.keys()) & set(vec_j.keys()):
                        dot_product += vec_i[term] * vec_j[term]
                    sim = dot_product / (norm_i * norm_j)
                matrix[i][j] = sim
                matrix[j][i] = sim

        return matrix


class EmbeddingScorer(Scorer):
    def __init__(self, embedder=None):
        self.embedder = embedder

    def score(self, candidates: List[ContextItem], task: str) -> List[float]:
        if not candidates:
            return []
        if not self.embedder:
            return [0.0] * len(candidates)

        query_emb = self.embedder(task)
        scores = []
        for c in candidates:
            if not c.embedding:
                scores.append(0.0)
                continue
            dot_product = sum(q * v for q, v in zip(query_emb, c.embedding))
            q_norm = math.sqrt(sum(q * q for q in query_emb))
            v_norm = math.sqrt(sum(v * v for v in c.embedding))
            if q_norm == 0.0 or v_norm == 0.0:
                scores.append(0.0)
            else:
                scores.append(dot_product / (q_norm * v_norm))
        return scores


class Governor:
    """Policy-first full-corpus retrieval and budgeted evidence coverage.

    Defaults to Unicode BM25 and marginal coverage per cost. max_candidates
    bounds the packing pool, not the exact first-stage corpus scan. A custom
    TFIDFScorer retains the optional pairwise distraction penalty. Costs use a
    supplied tokenizer or UTF-8 content bytes; callers reserve prompt overhead.
    Policy denials are recorded durably without returning private item metadata.
    See docs/research.md for the objective, complexity and experimental limits.
    """

    def __init__(
        self,
        semantic_store=None,
        procedural_store=None,
        episodic_store=None,
        policy_engine=None,
        scorer: Optional[Scorer] = None,
        distraction_coef: float = 0.5,
        max_candidates: int = 500,
        max_pairwise: int = 400,
        min_score: float = 0.0,
        token_counter=None,
        selection: str = "coverage",
    ):
        self.semantic_store = semantic_store
        self.procedural_store = procedural_store
        self.episodic_store = episodic_store
        self.policy_engine = policy_engine
        self.scorer = scorer or BM25Scorer()
        self.token_counter = token_counter
        self.selection = selection
        self.audit = None
        if selection not in ("coverage", "rank"):
            raise ValueError("selection must be coverage or rank")
        self.distraction_coef = distraction_coef
        if not isinstance(max_candidates, int) or max_candidates < 1:
            raise ValueError("max_candidates must be positive")
        if math.isnan(min_score) or min_score == float("inf"):
            raise ValueError("min_score must be finite or negative infinity")
        self.max_candidates = max_candidates
        self.max_pairwise = max_pairwise
        self.min_score = min_score

    def estimate_tokens(self, item: ContextItem) -> int:
        """Estimate token consumption of a given context item.

        Uses the configured content tokenizer, or UTF-8 bytes as a proxy.
        The application must reserve framing, tools and generation overhead.
        """
        if not item.content:
            return 0
        if self.token_counter is not None:
            value = self.token_counter(item.content)
            if not isinstance(value, int) or value < 1:
                raise ValueError("token counter must return a positive integer")
            return value
        # UTF-8 bytes are a conservative content-only proxy, not a model tokenizer.
        return max(1, len(item.content.encode("utf-8")))

    def rank(
        self, candidates: List[ContextItem], task: str, budget: int
    ) -> List[Tuple[ContextItem, float]]:
        """Rank candidates according to task query and distraction penalty."""
        if not candidates:
            return []

        # Get query similarities
        task_similarities = self.scorer.score(candidates, task)

        # Distraction penalty: high similarity to other candidates, low to tasks
        # Compute corpus similarity (mean similarity to other candidates)
        n = len(candidates)
        corpus_similarities = [0.0] * n

        if n > self.max_pairwise:
            # The pairwise matrix is O(n²); past this size the penalty costs
            # more than it is worth. Rank on task similarity alone.
            pass
        elif n > 1 and isinstance(self.scorer, TFIDFScorer):
            # Compute using TF-IDF pairwise similarity
            matrix = self.scorer.compute_pairwise_similarities(candidates)
            for i in range(n):
                total_sim = sum(matrix[i][j] for j in range(n) if j != i)
                corpus_similarities[i] = total_sim / (n - 1)
        elif n > 1:
            # Fallback embedding cosine similarity Matrix
            for i in range(n):
                total_sim = 0.0
                c_i = candidates[i]
                for j in range(n):
                    if i == j:
                        continue
                    c_j = candidates[j]
                    if c_i.embedding and c_j.embedding:
                        dot = sum(x * y for x, y in zip(c_i.embedding, c_j.embedding))
                        norm_i = math.sqrt(sum(x * x for x in c_i.embedding))
                        norm_j = math.sqrt(sum(x * x for x in c_j.embedding))
                        sim = dot / (norm_i * norm_j) if norm_i > 0 and norm_j > 0 else 0.0
                        total_sim += sim
                corpus_similarities[i] = total_sim / (n - 1)

        ranked = []
        for i in range(n):
            c_task = task_similarities[i]
            c_corp = corpus_similarities[i]
            # Distraction exists if item is highly similar to the corpus metadata/other items, but not the task
            distraction = max(0.0, c_corp - c_task)
            final_score = c_task - (self.distraction_coef * distraction)
            ranked.append((candidates[i], final_score))

        # Sort descending by final score
        ranked.sort(key=lambda x: x[1], reverse=True)
        return ranked

    def _collect(
        self,
        store,
        task: str,
        budget: int,
        principal: Principal,
    ) -> Tuple[List[ContextItem], int]:
        """Pull one tier's candidates. Returns (items, truncated_count).

        Stores that implement `query_for` are read tenant-scoped and capped.
        Anything else (a custom or mock store) keeps the v0.1 call shape.
        """
        if store is None:
            return [], 0

        if not hasattr(store, "query_for"):
            legacy = store.query(
                filter=task,
                budget_tokens=budget,
                scope=principal.legacy_scope,
            )
            return list(legacy), 0

        # Search the full tenant corpus before applying the candidate cap.
        items = store.query_for(principal)
        if self.policy_engine:
            items, denied = self.policy_engine.filter(items, principal)
            if self.audit:
                for _, reason in denied:
                    self.audit.record(principal, "policy", "denied", reason=reason.split(":")[0])
        scores = self.scorer.score(items, task)
        items = [
            item for item, _ in sorted(zip(items, scores), key=lambda pair: pair[1], reverse=True)
        ]
        total = len(items)
        items = items[: self.max_candidates]

        truncated = 0
        truncated = max(0, total - len(items))
        return items, truncated

    def assemble(
        self,
        task: str,
        budget: int,
        requester_scope: str = "",
        principal: Optional[Union[Principal, str]] = None,
    ) -> AssembledContext:
        """Query stores, filter by policy, rank, fill token budget, audit exclusions.

        `principal` carries tenant/owner/session identity and is the preferred
        input. `requester_scope` remains accepted for v0.1 callers and is
        interpreted as a legacy scope name.

        Raises:
            ValueError: if `budget` is not a number. Failing here names the
                problem; the comparison inside the fill loop did not.
        """
        if not isinstance(budget, int) or isinstance(budget, bool) or budget < 0:
            raise ValueError("assemble() requires a nonnegative integer token budget")

        if principal is None:
            principal = Principal(legacy_scope=requester_scope)
        elif isinstance(principal, str):
            principal = Principal(legacy_scope=principal)

        # 1. Retrieve candidates from tiers.
        #    Every tier is read through the principal, so an episodic read is
        #    bounded by tenant instead of refusing to run without a scope
        #    string — assembly no longer fails for GLOBAL or empty scopes.
        candidates: List[ContextItem] = []
        candidates_truncated = 0
        for store in (self.semantic_store, self.procedural_store, self.episodic_store):
            items, truncated = self._collect(store, task, budget, principal)
            candidates.extend(items)
            candidates_truncated += truncated

        excluded_items = []

        # 2. Run Privacy/Policy Engine before ranking
        if self.policy_engine:
            allowed_candidates, denied_list = self.policy_engine.filter(candidates, principal)
            for item, reason in denied_list:
                excluded_items.append(ExcludedItem(reason="Policy denied"))
        else:
            allowed_candidates = candidates

        # 3. Score and rank allowed candidates
        ranked_candidates = self.rank(allowed_candidates, task, budget)

        # 4. Fill budget
        assembled_items = []
        tokens_used = 0

        eligible = [(i, s) for i, s in ranked_candidates if math.isfinite(s) and s > self.min_score]
        selected_keys = None
        if self.selection == "coverage" and self.min_score != float("-inf"):
            selected = pack(
                [i for i, _ in eligible],
                [s for _, s in eligible],
                task,
                budget,
                self.estimate_tokens,
            )
            selected_keys = {(eligible[k][0].tenant_id, eligible[k][0].id) for k in selected}

        for item, score in ranked_candidates:
            # Relevance first. An item nobody asked for is not a budget
            # problem, and saying so would misreport why it was dropped.
            if not math.isfinite(score) or score <= self.min_score:
                excluded_items.append(
                    ExcludedItem(
                        item=item,
                        reason=(
                            f"{RELEVANCE_FLOOR}: scored {score:.4f}, at or below {self.min_score}"
                        ),
                    )
                )
                continue

            item_tokens = self.estimate_tokens(item)
            if tokens_used + item_tokens <= budget and (
                selected_keys is None or (item.tenant_id, item.id) in selected_keys
            ):
                assembled_items.append(item)
                tokens_used += item_tokens
            else:
                excluded_items.append(ExcludedItem(item=item, reason=BUDGET_EXCEEDED))

        return AssembledContext(
            items=assembled_items,
            tokens_used=tokens_used,
            excluded_items=excluded_items,
            candidates_truncated=candidates_truncated,
        )
