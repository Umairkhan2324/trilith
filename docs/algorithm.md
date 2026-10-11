# Lineage-Conditioned Witness Packing (LCWP v2)

Research candidate, 7 September 2026. Implementation: `core/lineage.py`.
This is the proposed algorithmic direction for Trilith; the default Unicode
BM25/TPCC pipeline remains a baseline. **Novelty is not established.**

## 1. Proposed research contribution

Investigate budgeted agent-memory selection when useful evidence is conjunctive
and source failures are correlated through recorded derivation lineage. A compact
summary may contain all relevant facts but depend on several revocable sources;
several apparently separate memories may depend on the same source. Selecting
them as independent evidence overstates what will survive a shared invalidation.

The proposed contribution is the specific combination of a lineage-conditioned
complete-witness objective, atomic chain-completion proposals, and an experimental
protocol that separates conjunction, source dependence and probability error.
Each ingredient has related prior art. A new name or combination alone does not
establish scientific novelty; utility and a feature-level literature comparison
are required. The claims below are properties of the implementation's formal
model, not claims about LLM truth or comprehension.

## 2. Formal model

An authorized candidate i has:

- tenant-qualified identity, measured positive cost c_i;
- canonical fact identifiers E_i;
- transitive source dependencies D_i from the trusted storage lineage graph.

A requirement j has weight w_j >= 0 and one or more alternative witnesses
W_j1, W_j2, ... . A witness is an AND-set of facts; alternatives are OR-ed.
The task planner supplies these requirements without access to held-out answers.
LCWP does not extract facts, verify them, translate text or estimate probabilities.

A scenario omega has probability p_omega and revoked source set R_omega.
Candidate i is active iff neither its identity nor any dependency is revoked:

    active(i, omega) = 1[{i} union D_i is disjoint from R_omega]
    E(S, omega) = union of E_i for active i in S
    U(S, omega) = sum_j w_j 1[exists k: W_jk is a subset of E(S, omega)]
    F(S) = sum_omega p_omega U(S, omega)

Maximize F(S) subject to sum_i c_i <= B. Current authorization, expiry and source
closure are hard constraints before optimization; probability never grants
access. A scenario probability is a hypothesis about source validity/availability,
not permission to retain erased data or a calibrated probability of a true answer.

This objective is intended for planning context that remains useful across a
handoff or validity horizon. The current embedded function returns a snapshot at
assembly time. Every later use must revalidate authorization and dependencies.
It cannot retract knowledge already delivered to an LLM or an external agent.

## 3. Why singleton ranking and ordinary coverage are insufficient

**Complementarity counterexample.** There is one witness {a,b}. Candidate A carries
a; B carries b. In a no-failure scenario F(empty)=F({A})=F({B})=0, F({A,B})=1.
Every singleton gain is zero, so strictly positive singleton greedy cannot start.
The function violates diminishing returns and is not generally submodular.
Consequently ordinary submodular greedy guarantees do not apply to LCWP.

**Shared-source counterexample.** Two copies carry fact a and share a source that
survives with probability 0.5. Either copy and both together have expected coverage
0.5, not 0.75. Independent-item survival calculations double-count correlated
evidence. An alternative source that survives precisely when the first fails can
raise coverage to 1.0 at the same two-item budget. Marginal reliability alone
cannot identify that distinction. This illustrates known dependence issues rather
than constituting a claim to a new probability theorem.

## 4. Algorithm

At each iteration:

1. Enumerate feasible additions of up to k items (default k=3).
2. For every scenario and unfinished witness, propose full witness completions.
   Consider each covering item as a seed (and an empty seed), then greedily cover
   remaining facts by newly covered facts per cost. Proposals may be longer than
   k, so a four-hop witness can enter atomically.
3. Evaluate the **joint** scenario-weighted marginal gain of each proposal using
   actual source masks. Choose the largest positive gain per added cost, with
   deterministic cost/identity tie-breaking. Stop if none fits with positive gain.
4. Compare the resulting pack with the best standalone feasible proposal examined.

The proposal generator is heuristic set cover, not exact minimum-cost proof
search. Atomic chain completion avoids the zero-gain singleton trap; it does not
make the overall algorithm globally optimal. Local choices can miss useful
combinations, and a wrong scenario distribution can make the result much worse.

For fixed k, generic proposals number O(n^k) per iteration; there are at most n
iterations. With m scenarios and h witnesses, seeded greedy completions require
roughly O(m h n^3) candidate comparisons per iteration, in addition to set-operation
and objective-evaluation cost. The implementation rejects more than 24 candidates,
64 scenarios or 64 witness alternatives. It caches subset utilities. This is a
small-pool research solver, not a scalable ANN retrieval service. The exact oracle
enumerates 2^n subsets and is restricted to n <= 18.

## 5. Testable properties

**Budget feasibility.** Every accepted addition is checked against remaining cost;
the standalone safeguard is also feasible. Positive integer costs prevent free
unbounded admissions. Costs refer to content only unless the application accounts
for framing externally.

**Monotonic objective.** Adding an authorized item cannot remove facts in any
scenario, so cannot invalidate an already complete witness. Nonnegative weights
and probabilities preserve monotonicity. This does not imply submodularity.

**Duplicate saturation.** Adding an item with identical facts and identical
scenario survival to an already selected item has zero marginal utility. Different
independent sources may add value because their survival masks differ.

**Fact-label invariance.** Applying any bijection to fact identifiers in candidates
and witnesses preserves all subset relations, objective evaluations, proposals and
selected identities, when candidate IDs, costs and scenario masks are fixed.
The tests use Chinese and Urdu labels. This is a precise language-independent
symbolic selection property; it does not imply that automatic extraction from
different languages is equally accurate or that translated text costs are equal.

**Recorded-lineage authorization.** `assemble_witnesses` reads the current source
closure from SQLite and checks every recorded ancestor plus the candidate under
the same principal inside a transaction. Unknown/unrecorded external dependencies
remain outside this property. The standalone mathematical solver does not perform
authentication; use the runtime wrapper for stored memory.

## 6. Experiments and negative results

Run `python -m benchmarks.lineage`. The checked-in `lineage-results.json` contains
1,200 trials: 20 seeds, 10 instances per seed, six methods. We enumerate the test
distribution exactly and compare against an exhaustive optimum; no Monte Carlo
estimate of task success or answer-model judging is involved. Seeds vary item
costs in handcrafted structures, so they are not independent natural-language
tasks. All selectors receive the same candidate annotations.

Mean per-instance achieved utility divided by the exhaustive optimum:

| Regime | TPCC coverage | Singletons | Bounded bundles | No lineage | LCWP v2 |
| --- | ---: | ---: | ---: | ---: | ---: |
| Correlated source failure | 0.434 | 0.502 | 0.989 | 0.403 | **0.989** |
| Stable sources | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| Wrong failure model | **0.964** | 0.917 | 0.338 | 0.850 | 0.338 |
| Four-hop completion | **1.000** | 0.000 | 0.000 | **1.000** | **1.000** |

Correlated-regime LCWP minus TPCC mean **raw utility** is 0.586, with paired
seed-bootstrap interval [0.513, 0.653]. These are weighted witness-utility units,
not percentage points of answer accuracy. The result supports a mechanism claim
on this synthetic family only. The wrong-model loss is substantial and retained;
do not deploy the survival objective on uncalibrated failure estimates by default.

The no-lineage ablation replaces the scenario distribution with one no-failure
scenario. Bounded bundles remove chain completion. Singletons remove both bundle
and completion proposals. TPCC is the earlier additive-relevance/feature-coverage
selector. The oracle is privileged to the true test distribution and is an upper
bound, not a deployable fair competitor under misspecification.

Missing evidence for a paper: independently derived fact/witness annotations,
real multi-agent handoffs, actual source-change traces, probability calibration,
held-out downstream answer quality, stronger published selectors and larger-pool
latency/memory scaling. The synthetic optimum ratio is not a publishable overall
performance claim by itself.

## 7. Prior-art collision review

| Primary source | Established overlap | Needed distinction or comparison |
| --- | --- | --- |
| [PACMS](https://arxiv.org/abs/2606.20047) | Pooled context selection with submodular objectives | LCWP uses complete AND-witnesses and scenario-dependent lineage; compare released selector |
| [QUBO evidence selection](https://arxiv.org/abs/2607.12334) | Requirement coverage, complementarity and compactness in multi-hop RAG | Closest complementarity collision; compare formal objectives and solver outputs |
| [TEPA](https://arxiv.org/abs/2608.07429) | Explicit validity and revocation of agent memory | Revocation itself is not novel; LCWP studies budget allocation conditional on shared-source loss |
| [Selective Revocation and Replay](https://github.com/aliuyar1234/selective-revocation-replay) | Recovery of persisted agent state after compromise | Source-dependent recovery is prior art; distinguish selection from incident repair |
| [Robust sensor placement](https://las.inf.ethz.ch/files/krause08near-long.pdf) | Set selection robust to correlated failures | Scenario robustness and dependence are established optimization ideas |
| [Distributionally robust submodular maximization](https://proceedings.mlr.press/v89/staib19a.html) | Generalization under uncertain scenario distributions | LCWP is not a DRO algorithm and presently fails under distribution misspecification |
| [Bounded context packing](https://yesudeep.com/learn/search/the-result-list-is-a-context-window/) | Atomic bundles and structural repair before cost accounting | Bundling alone cannot be claimed as original |

Reviewed abstracts, source pages and selected technical material are insufficient
to establish an exhaustive absence claim. **Candidate novelty:** jointly evaluating
complete evidence witnesses under transitive, correlated lineage invalidation,
with bounded atomic completion and explicit failure-model ablations in an agent
memory governor. This must survive full-paper comparison and independent review.

## 8. Embedded usage

```python
from core.lineage import Requirement, Scenario, assemble_witnesses
from core.identity import Principal

context, receipt = assemble_witnesses(
    rt,
    Principal("acme", "alice", "session-1"),  # trusted application identity
    annotations={"step-a": {"dependency-found"}, "step-b": {"fix-verified"}},
    requirements=[Requirement("safe-handoff", (
        frozenset({"dependency-found", "fix-verified"}),
    ))],
    scenarios=[Scenario("current", 1.0)],
    budget=512,
)
```

The application must generate and validate annotations independently of benchmark
answer labels. This interface intentionally does not expose probability or
authorization controls to a model through REST/MCP tool arguments.
