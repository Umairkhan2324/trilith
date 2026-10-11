# Trilith: research and PhD application roadmap

Prepared 7 September 2026. This is a working plan, not a prediction of admission,
publication or funding. Timeline assumes roughly 12–15 focused hours/week and
must be adjusted to the applicant's background, resources and entry year.

## Target outcome

Produce evidence that the applicant can formulate a consequential question,
understand prior work, design a defensible experiment, implement and debug a
method, interpret failures and communicate conclusions. The target package is:

- A focused technical report or submission with an accurate status label.
- Reproducible code, experiment configurations and results from independent tasks.
- A short research talk and a clear account of the applicant's own contributions.
- Feedback from a researcher who has observed the work over time and, when
  appropriate, can write a specific recommendation.
- An application statement connecting this work to future questions and faculty.

An accepted paper is a possible outcome, not a prerequisite imposed by this plan.
Avoid adding product features solely to make the repository look substantial.

## Current evidence and missing evidence

| Claim | Current evidence | Missing evidence |
| --- | --- | --- |
| The implementation enforces specified boundaries | Regression tests and explicit policies | Independent review; concurrency and deployment testing |
| LCWP solves small annotated selection problems reasonably well | Synthetic exact-oracle comparisons | Diverse unseen structures and stronger optimization baselines |
| Lineage improves actual agent outcomes | Not established | Executable or answer-level evaluation with a frozen reader |
| It works with realistic metadata | Not established | Non-oracle fact/witness extraction and estimated failure scenarios |
| Proactive packing is operationally necessary | Not established | Comparison with retrieving again after a change |
| It is language agnostic | Symbolic fact-label invariance; multilingual lexical smoke tests | Natural-language extraction and tokenizer performance per language |
| The contribution is original | Candidate distinction recorded in algorithm.md | Full-paper comparison and external technical feedback |

The 98.9% result is a ratio to the optimum of a supplied synthetic objective.
It is not answer accuracy, a probability of agent success, or an admissions signal
by itself. Repeated seeds vary costs within handcrafted structures; they do not
constitute hundreds of independently authored tasks.

## Research question to test first

**Under what handoff and retrieval constraints does selecting complete evidence
chains using shared-source lineage improve downstream task success at fixed
context cost?**

Proposed setting: a producing agent prepares a bounded context package at t0.
At t1, a receiving agent learns which sources have expired or been invalidated.
It must remove unusable descendants before acting. In one regime it cannot fetch
new content; in another, it can retrieve again with measured latency/token cost.

Keep semantic correction, permission revocation and temporary source availability
as separate event types. A revoked source is never usable, irrespective of its
predicted utility. Define whether the receiver has received the relevant control
events; do not equate unknown changes with known revocations.

The no-refetch regime is a hypothesis about a useful deployment constraint, not
an excuse to handicap competitors. Find a concrete motivating workflow and report
the unrestricted-refetch comparison. If the benefit disappears whenever cheap
refetch is possible, that boundary belongs prominently in the paper.

## Milestones and decision gates

| Stage | Estimated work | Deliverable | Gate to proceed |
| --- | --- | --- | --- |
| 1. Understand and challenge | Weeks 1–2 | Two-page proposal, hand-worked examples, full-paper comparison of closest methods | Explain LCWP, its inputs and a failure without relying on generated prose |
| 2. Reproduce and falsify | Weeks 3–4 | Fresh reproduction plus reactive-refetch and strong small-instance baselines | Show a plausible setting where the problem is not eliminated by a simpler method |
| 3. Build an independent pilot | Weeks 5–6 | 20–30 development tasks from separate underlying source families; blinded metadata extraction | Demonstrate that task labels cannot enter selector inputs |
| 4. Freeze the evaluation | Weeks 7–8 | Versioned protocol, frozen models/prompts, group-based train/dev/test split, cost estimate | Choose sample size using pilot variance and available resources before test access |
| 5. Run and diagnose | Weeks 9–11 | Held-out runs, paired intervals, cost breakdown, ablations, failure taxonomy | Results are reproducible and conclusions survive realistic inputs |
| 6. Write and get feedback | Weeks 12–14 | Technical report, clean artifact, ten-minute talk and external review | Another researcher can reproduce a main result and identify exactly what is claimed |

These stages may overlap with application preparation. If applying for Fall 2027,
check actual 2026 deadlines now; do not make a paper acceptance a dependency of
submitting applications. A later entry year may allow a fuller research cycle.

## Evaluation design

Use one primary endpoint: downstream task correctness at a fixed measured reader
context budget. For executable tasks, score against hidden tests; for question
answering, use an appropriate answer/citation rubric with blinded evaluation.
Failure to retrieve or abstention on an answerable task remains in the denominator.

Keep source-policy violations, unsupported claims, complete-witness survival,
latency, extraction tokens, retrieval tokens and packing cost as separate metrics.
Do not report low leakage as selector superiority when all selectors use the same
policy filter. Do not combine unrelated metrics into an unexplained headline score.

Minimum comparator set:

1. No memory and a full allowed-context reference where feasible.
2. BM25, a pinned embedding retriever if affordable, MMR and TPCC.
3. LCWP without lineage, without completions, and with singleton additions only.
4. A strong exact or optimization reference on tractable instances.
5. Reactive retrieval after the event, with the same information access and a
   separately reported unconstrained version.
6. The closest published selector that can be faithfully reproduced. A local
   approximation must be labelled as such, not named as the published method.

Run two metadata conditions: oracle annotations for diagnosis, and independently
produced annotations for the main practical claim. The planner sees only the
permitted query/corpus; it never sees gold answers, hidden tests, future events or
evaluation witnesses. Give all methods equivalent access to planner output and
include the cost of generating it. Validate source lineage independently of a
model's assertions.

Estimate failure scenarios from training history or observable TTL information.
Separate these from oracle future scenarios. Test calibration and distribution
shift. Preserve the current wrong-model loss as motivation for this evaluation;
do not silently replace it with a favorable distribution.

Split by underlying project, document family or event trace before generating
variants. A translation, paraphrase or changed random seed of a training case is
not an independent test case. Bootstrap independent task groups and use paired
comparisons on identical cases. Report all prespecified regimes and model seeds.
Set budget/sample size after a cheap development pilot; no paid model runs are
needed to begin the methodological work.

## First seven days: concrete work

1. Write a one-page explanation in your own words: what fails, who experiences
   it, why existing retrieval may not suffice, and what would falsify the claim.
2. Work through a two-hop case, a shared-source duplicate case, and the incorrect
   probability case by hand. Reproduce them in the existing solver.
3. Read the full PACMS and QUBO selector papers first. Record the closest matching
   equation, information available to each method and important assumptions.
   Continue with TEPA and robustness literature linked in algorithm.md.
4. Reproduce the checked-in experiments in a clean environment. Record the exact
   code version, dependency versions and any discrepancy; do not overwrite the
   existing frozen results during exploratory work.
5. Specify one realistic producer/receiver workflow and the refetch comparator.
   Use the draft in handoff-study-protocol.md; resolve its open decisions.
6. Prepare three sample tasks without giving their answers to the planner. Check
   that a stronger baseline is capable of winning and that unsupported outputs
   are scored as failures.
7. Discuss the proposal and one failed case with a faculty mentor or researcher.
   Ask for criticism of the question and evaluation, not endorsement of novelty.

## Your research ownership

Maintain a dated notebook: question, prediction before the experiment, code/data
version, outcome, explanation and next decision. Distinguish experiments you ran,
algorithms or proofs you independently checked, and assistance you received.
Because this project includes AI-assisted implementation and writing, keep a
contribution record and ensure you can defend the method and evidence yourself.

Useful preparation is targeted: sets/probability, conditional dependence, basic
discrete optimization, experimental design, confidence intervals, retrieval and
evaluation leakage. Learn these through the examples and baselines, rather than
postponing all research until a broad curriculum is complete.

For an interview, be able to answer: Why is the objective not submodular? Where
do witnesses come from? How are probabilities estimated? Why not retrieve again?
Which experiment made you change your mind? Where does LCWP lose? What did you
personally contribute? What is the next unanswered question?

## Application preparation in parallel

Build a faculty-fit table using current primary sources: recent relevant papers,
the connection to your research question, current application process, funding
terms, deadlines and potential recommenders. Do not choose programs solely by
ranking or assume that every relevant faculty member is accepting students.

Ask potential recommenders early enough that they can observe sustained work.
A specific account of your decisions and independence is more informative than
an endorsement based only on a repository link. A mentor need not promise
coauthorship or admission for their feedback to be valuable.

Prepare an accurate CV entry, a two-page research summary and a ten-minute talk.
Distinguish an internal report, public preprint, submitted manuscript and accepted
paper. Describe substantive open-source issues, tests and reproducibility work
separately from experimental claims. Select a venue after understanding the final
contribution and checking its current scope; acceptance cannot be scheduled.

Current official guidance supports emphasizing the research problem, prior work,
technical approach and validation: [CMU faculty statement advice](https://www.cs.cmu.edu/~aldrich/essay-advice.html).
Stanford's application checklist asks for preparation/research interests and three
recommendation letters: [Stanford checklist](https://www.cs.stanford.edu/admissions/graduate-application-checklists).
These examples are not a recommended university shortlist.

Funding must be checked program by program. For example, CMU CSD currently states
that admitted PhD students receive comprehensive support while in good standing,
with the same basic funding for domestic and international students:
[CMU doctoral admissions](https://csd.cs.cmu.edu/academics/doctoral/admissions).
This is a program policy, not a prediction of admission or a universal US policy.

## If the algorithm does not win

An honest outcome may be that cheap refetch dominates proactive selection, or
that noisy witnesses eliminate gains. Possible contributions then include a
carefully validated boundary result, a benchmark revealing unrealistic metadata
assumptions, or a simpler reliable method. Discuss the evidence with a mentor
before choosing that direction. Do not keep changing the test distribution until
a favorable result appears. A failed hypothesis can still demonstrate research
ability when the investigation is rigorous and clearly explained.
