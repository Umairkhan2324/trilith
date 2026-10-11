# Experimental harness

Run from the repository root with Trilith dependencies installed:

```bash
python -m benchmarks.run --seeds 10 --output benchmarks/results.json
python -m benchmarks.run --cases heldout.jsonl --seeds 1 --output heldout-results.json
```

The checked-in `results.json` is a **synthetic mechanism diagnostic**, not LoCoMo,
LongMemEval, an answer-model evaluation or evidence of state-of-the-art results.
It contains 1,050 method trials (150 cases, seven selectors), every metric,
configuration, environment, source hashes and revision. Input templates are
visible in `run.py`. Five languages are exercised; this is not cross-language
translation evaluation. Budgets are UTF-8 bytes, not model tokens.

Initial run:

| Method | Gold-item recall | Complete evidence |
| --- | ---: | ---: |
| Recency | 0.5833 | 0.4067 |
| TF-IDF | 0.8000 | 0.8000 |
| BM25 score order | 1.0000 | 1.0000 |
| Density | 1.0000 | 1.0000 |
| MMR | 1.0000 | 1.0000 |
| Coverage disabled | 1.0000 | 1.0000 |
| TPCC coverage | 1.0000 | 1.0000 |

All methods recorded zero policy leakage and zero budget violations because they
share the same policy filter and budget enforcement. These results **do not show
an improvement from coverage selection**. The fixtures saturate for BM25; more
independent, difficult evidence-combination tasks are needed. Do not tune on these
fixtures and then present their scores as held-out validation.

Report raw runs and paired task-level intervals on independent datasets. The
current synthetic interval resamples seed means; repeated translations and
templates do not provide independent research observations. Exact local latency
is in the JSON and is not a hardware-independent performance claim.

External JSONL schema and the proposed paper's Section 7 protocol are in
[docs/research.md](../docs/research.md). Gold IDs are used only in evaluation;
the selectors receive the query and policy-approved candidate content.

## Lineage and complete-witness experiment

`python -m benchmarks.lineage` runs 1,200 trials over 20 seeds with exhaustive
small-instance optima, TPCC, singletons, bounded bundles, no-lineage and LCWP v2.
See [algorithm specification and results](../docs/algorithm.md) and
[lineage-results.json](lineage-results.json). These experiments assume supplied
fact/witness annotations and known synthetic source-failure scenarios; they
measure an optimization objective, not LLM accuracy. Wrong failure probabilities
produce a substantial loss, which is retained in the results.
