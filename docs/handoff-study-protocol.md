# Handoff study protocol — draft, not preregistered

Status: design only. No new independent-task results exist for this protocol.
Owner, dates, models, dataset size and resource budget remain to be set after the
applicant profile and development pilot. Freeze a version before held-out runs.

## Hypotheses

H1: At a fixed handoff-context budget, with correctly recorded dependencies and
estimated (not oracle) change probabilities, LCWP improves receiver task success
relative to the strongest prespecified simple baseline in a constrained-refetch
setting. This is currently untested.

H2: The gain is specifically attributable to complete-witness selection and
shared-source dependence, rather than privileged planner information or different
retrieval access. Test via ablations with identical inputs.

H3: Unrestricted inexpensive refetch reduces or eliminates the advantage. Report
this as an operational boundary, not an excluded regime.

## Unit and timeline

One independent unit is an underlying task/project with its source history, not a
seed, translation or method run. Each unit follows this timeline:

1. Producer receives source snapshot t0 and task; candidate generation is frozen.
2. Planner derives evidence annotations using only t0 information. Cost is logged.
3. Each selector packs context with the same measured tokenizer and budget.
4. A withheld event at t1 changes source validity or access. Receivers receive
   identical control events. Invalid descendants are removed by shared policy.
5. Receiver attempts the task under its declared retrieval-access condition.
6. An evaluator with hidden tests/answers scores correctness and policy behavior.

Candidate-generation failures count in end-to-end results. Separately report
selection-only diagnostics using a common pool, labelled as conditional results.

## Access conditions

| Condition | Additional source retrieval after t1 | Purpose |
| --- | --- | --- |
| Package-only | None; control events still delivered | Tests usefulness of proactive packing |
| Limited refetch | Fixed measured retrieval budget/latency | Tests practical tradeoff |
| Unrestricted refetch | Fresh retrieval allowed, actual cost reported | Tests whether proactive selection is necessary |

Do not describe unrestricted refetch as an equal-cost comparator unless all costs
really are matched. Do not conceal that a package-only environment was imposed by
the experiment. Motivate it with a concrete workflow before making practical claims.

## Prevent privileged information

Planner/selector inputs may include t0 task, permitted documents, recorded source
lineage and training-estimated event frequencies. They may not include hidden
answers/tests, the realized future event or evaluation-created gold witnesses.
Store evaluator labels separately from planner inputs and audit the boundary.

Oracle annotations and oracle future probabilities are diagnostic upper bounds.
They cannot support the main deployment claim. Use a frozen planner for the
non-oracle condition, and count its compute/tokens for every method using it.

## Endpoints and analysis

Primary: task success after the event, at the specified reader-context budget.
Specify the exact deterministic test or blinded rubric before testing. Record
timeouts, abstentions and invalid outputs without dropping hard cases.

Secondary: unsupported assertions, source-policy violations, surviving complete
evidence, total input/output tokens, selection and end-to-end latency, memory use,
and event-model calibration. Separate content-token budgets from UTF-8 proxies.

Report paired differences and confidence intervals clustered by independent task
family. Use pilot variance to choose sample size. Repeated decoding seeds measure
model stochasticity, not additional task diversity. Prespecify the primary model,
budget and baseline; label exploratory analyses and multiple secondary comparisons.

Keep stable, correlated-change and distribution-shift conditions. Preserve raw
outputs and evaluation decisions subject to dataset rights and privacy. Record
code/dependency/model versions, prompts, seeds, dataset hashes and access policy.

## Open decisions before freezing

- Concrete application and justification for the refetch constraint.
- Source datasets/workflows, licenses, grouping and independent held-out split.
- Task success evaluator and answerability/abstention rules.
- Annotation procedure, lineage verification and planner-error evaluation.
- Probability estimator, training period and observables available at t0.
- Reader/planner model, tokenizer, generation settings and cost ceiling.
- Comparator implementations, hyperparameter tuning and optimization limits.
- Independent task count and confidence-interval procedure from the pilot.
- External reviewer and reproduction procedure.

## Decision rule

Proceed with a positive method claim only if results survive non-oracle inputs and
fair operational baselines. If refetch dominates, narrow the claim to the verified
constrained setting or change the question. If realistic annotation/probability
error removes the gain, report that result and investigate the simpler baseline.
Do not equate a systems-security fix or a new benchmark with algorithmic novelty.
