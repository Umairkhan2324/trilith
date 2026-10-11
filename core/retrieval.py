"""Unicode lexical retrieval and coverage-per-cost packing.

No translation model is implied: scripts are supported, cross-language meaning
requires an embedding provider. These are lexical evidence proxies, not a
measurement of factual truth or downstream information survival.
"""

import math
import re
import unicodedata
from collections import Counter


def features(text):
    text = unicodedata.normalize("NFKC", text).casefold()
    words = re.findall(r"\w+", text)
    result = ["w:" + w for w in words]
    # Character bigrams handle unsegmented scripts without language detection
    # or an English stopword list. Prefixes keep channels disjoint.
    for word in words:
        if any("\u3400" <= char <= "\u9fff" or "\u3040" <= char <= "\u30ff" for char in word):
            result.extend("c:" + word[i : i + 2] for i in range(len(word) - 1))
    return result


class BM25Scorer:
    def score(self, candidates, task):
        docs = [Counter(features(c.content)) for c in candidates]
        query = set(features(task))
        if not docs or not query:
            return [0.0] * len(docs)
        df = Counter(t for doc in docs for t in doc)
        lengths = [sum(d.values()) for d in docs]
        avg = sum(lengths) / len(docs) or 1
        scores = []
        for doc, length in zip(docs, lengths):
            score = 0.0
            for term in query & doc.keys():
                idf = math.log(1 + (len(docs) - df[term] + 0.5) / (df[term] + 0.5))
                tf = doc[term]
                score += idf * tf * 2.2 / (tf + 1.2 * (0.25 + 0.75 * length / avg))
            scores.append(score / (1 + score))
        return scores


class HybridScorer:
    """Lexical + exact vector retrieval with a caller-provided embedding model.

    The provider must use the same model/version for queries and stored vectors.
    This performs exact cosine search, not approximate vector indexing.
    """

    def __init__(self, embedder, lexical_weight=0.5):
        if not 0 <= lexical_weight <= 1:
            raise ValueError("lexical_weight must be in [0, 1]")
        self.embedder = embedder
        self.lexical_weight = lexical_weight

    def score(self, candidates, task):
        lexical = BM25Scorer().score(candidates, task)
        if not candidates:
            return []
        query = list(self.embedder(task))
        if not query or any(not math.isfinite(x) for x in query):
            raise ValueError("Query embedding must be nonempty and finite")
        query_norm = math.sqrt(sum(x * x for x in query))
        result = []
        for item, score in zip(candidates, lexical):
            vector = list(item.embedding)
            if not vector:
                result.append(score)
                continue
            if len(vector) != len(query) or any(not math.isfinite(x) for x in vector):
                raise ValueError("Stored embedding dimension/model mismatch or nonfinite value")
            norm = math.sqrt(sum(x * x for x in vector))
            cosine = (
                sum(a * b for a, b in zip(query, vector)) / (query_norm * norm)
                if query_norm * norm
                else 0
            )
            result.append(
                self.lexical_weight * score + (1 - self.lexical_weight) * max(0, min(1, cosine))
            )
        return result


def pack(candidates, scores, task, budget, cost, coverage_weight=0.5):
    """Greedy marginal utility/token with a best-singleton safeguard.

    F(S) = (1-a) sum relevance(i) + a |union evidence(i)| / |query|.
    This nonnegative monotone submodular objective is a research heuristic.
    We do not claim the 1-1/e guarantee for this simple knapsack heuristic.
    """
    query = set(features(task))
    evidence = [set(features(i.content)) & query for i in candidates]
    costs = [max(1, cost(i)) for i in candidates]
    covered, chosen = set(), []
    remaining = set(range(len(candidates)))
    spent = 0

    def gain(i, seen):
        return (1 - coverage_weight) * max(0, scores[i]) + coverage_weight * len(
            evidence[i] - seen
        ) / max(1, len(query))

    while remaining:
        feasible = [i for i in remaining if costs[i] + spent <= budget]
        if not feasible:
            break
        best = max(
            feasible,
            key=lambda i: (
                gain(i, covered) / costs[i],
                gain(i, covered),
                candidates[i].tenant_id,
                candidates[i].id,
            ),
        )
        if gain(best, covered) <= 0:
            break
        chosen.append(best)
        covered.update(evidence[best])
        spent += costs[best]
        remaining.remove(best)
    singletons = [i for i in range(len(candidates)) if costs[i] <= budget]
    if singletons:
        best = max(singletons, key=lambda i: gain(i, set()))
        utility = (1 - coverage_weight) * sum(
            max(0, scores[i]) for i in chosen
        ) + coverage_weight * len(covered) / max(1, len(query))
        if gain(best, set()) > utility:
            return [best]
    return chosen
