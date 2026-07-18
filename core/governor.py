import math
import re
from collections import Counter
from typing import List, Tuple, Optional
from abc import ABC, abstractmethod

from core.proto.trilith_pb2 import ContextItem, AssembledContext, ExcludedItem

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
            return re.findall(r'\w+', text.lower())

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

            dot_product = 0.0
            for term in task_tokens:
                dot_product += task_vec.get(term, 0.0) * doc_vec.get(term, 0.0)

            scores.append(dot_product / (task_norm * doc_norm))

        return scores

    def compute_pairwise_similarities(self, candidates: List[ContextItem]) -> List[List[float]]:
        """Compute cosine similarity matrix between all pair of candidates."""
        if not candidates:
            return []

        def tokenize(text: str) -> List[str]:
            return re.findall(r'\w+', text.lower())

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
    def __init__(
        self,
        semantic_store=None,
        procedural_store=None,
        episodic_store=None,
        policy_engine=None,
        scorer: Optional[Scorer] = None,
        distraction_coef: float = 0.5
    ):
        self.semantic_store = semantic_store
        self.procedural_store = procedural_store
        self.episodic_store = episodic_store
        self.policy_engine = policy_engine
        self.scorer = scorer or TFIDFScorer()
        self.distraction_coef = distraction_coef

    def estimate_tokens(self, item: ContextItem) -> int:
        """Estimate token consumption of a given context item.

        Rule of thumb: ~4 characters per token. Content is the primary driver.
        """
        if not item.content:
            return 0
        return max(1, len(item.content) // 4)

    def rank(
        self,
        candidates: List[ContextItem],
        task: str,
        budget: int
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

        if n > 1 and isinstance(self.scorer, TFIDFScorer):
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

    def assemble(
        self,
        task: str,
        budget: int,
        requester_scope: str = ""
    ) -> AssembledContext:
        """Query stores, filter by policy, rank, fill token budget, audit exclusions."""
        candidates = []

        # 1. Retrieve candidates from tiers
        if self.semantic_store:
            # Query all semantic items
            candidates.extend(self.semantic_store.query(filter=task, budget_tokens=budget, scope=requester_scope))
        if self.procedural_store:
            candidates.extend(self.procedural_store.query(filter=task, budget_tokens=budget, scope=requester_scope))
        if self.episodic_store:
            candidates.extend(self.episodic_store.query(filter=task, budget_tokens=budget, scope=requester_scope))

        excluded_items = []

        # 2. Run Privacy/Policy Engine before ranking
        allowed_candidates = []
        if self.policy_engine:
            allowed, denied_list = self.policy_engine.filter(candidates, requester_scope)
            allowed_candidates = allowed
            for item, reason in denied_list:
                excluded_items.append(ExcludedItem(item=item, reason=reason))
        else:
            allowed_candidates = candidates

        # 3. Score and rank allowed candidates
        ranked_candidates = self.rank(allowed_candidates, task, budget)

        # 4. Fill budget
        assembled_items = []
        tokens_used = 0

        for item, score in ranked_candidates:
            item_tokens = self.estimate_tokens(item)
            if tokens_used + item_tokens <= budget:
                assembled_items.append(item)
                tokens_used += item_tokens
            else:
                excluded_items.append(ExcludedItem(item=item, reason="Exceeded token budget"))

        return AssembledContext(
            items=assembled_items,
            tokens_used=tokens_used,
            excluded_items=excluded_items
        )
