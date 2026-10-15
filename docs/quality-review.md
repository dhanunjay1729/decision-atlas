# Quality review — 2026-10-15

This is a developer-reviewed smoke suite, not a held-out benchmark or evidence that debate beats a strong single-agent system. Inputs and expected labels are tracked under `evaluation/`. Generated reports and third-party web excerpts remain in ignored `work/`.

## Observed issues and changes

- Outcome claims about communication skills, learning, accessibility and workload were sometimes labeled as values by both verifiers. A separate kind-classification call now ignores the draft labels. Prompts distinguish pure preferences from measurable effects and mixed statements. Empirical claims cannot receive an accepted value label during source verification. This remains model-assisted classification and may over-abstain or err.
- A source-free report recommended a hybrid assignment design despite the no-recommendation instruction. A separate report review and bounded rewrite were added.
- The first cheap report reviewer missed advice that untested contexts warranted monitored adoption. The review now uses Haiku and a narrow phrase guard covers that observed conclusion. This is a regression safeguard, not an exhaustive semantic filter.
- A reviewed rewrite could fix neutrality but fall below 300 words. Section-based correction now also applies after the review rewrite, without rerunning debate arguments. Tests cover this exact recovery and rejection after persistent audit failure.
- Web results can include vendor commentary. Search instructions now prefer primary research and official institutional sources; inclusion and label agreement do not certify source quality.

## Recorded comparisons

`initial-review-summary.json` records three completed pipelines: knowledge (2 participants / 4 arguments / 317 report words / $0.002234), documents (5 / 10 / 310 / $0.005826), web (3 / 6 / 401 / $0.011604, including one shared search). Manual review found recommendation leakage in the web report despite completion. These counts must not be presented as three quality passes.

For each input, one Haiku baseline call received the same selected evidence and all requested perspectives, with the same report length and neutrality instructions. Baseline costs were $0.000556, $0.000712 and $0.006216 respectively, including an equal search-cost allocation for web. Reports were 264, 270 and 281 words: all below the requested range, but their summaries were generally balanced and much faster (about 7–14 seconds versus 29–104 seconds). The debate pipeline had additional validation/corrections that the one-call baseline did not. This is not a cost-matched comparison or the strongest possible single-agent baseline.

On the initial developer-authored 12-claim fixture, kind classification, the single Haiku verifier and the cross-checked labels each matched all expected labels. On the repeated stricter run, kind classification again matched 12/12; the single verifier matched 11/12 and the combined result matched 11/12 with one explicit review/abstention and no wrong non-abstained label. Repetition demonstrates variability, not an accuracy guarantee.

`strict-review-summary.json` records the follow-up failures honestly: knowledge and document runs stopped because reviewed rewrites missed the word range; the web run stopped on invalid structured output during report review. No completed reports were claimed for these failures. The subsequent section-recovery change has a regression test; live checks must distinguish later successes from these failures.

Known ledger-accounted cost of these two review suites: $0.023158 + $0.029748 = **$0.052906**, within the existing research allowance. Retained reservations may exceed actual provider charges. The earlier model-screening allowance and separate live app checks also count when considering the overall research ceiling.

## Reproduce deliberately

Offline:

```bash
PYTHONPATH=backend .venv/bin/python -m pytest backend/tests -q
npm run build
```

Paid opt-in, using the configured server-only gateway key:

```bash
PYTHONPATH=backend .venv/bin/python scripts/evaluate.py --live --max-usd .06 --name YOUR_NEW_RUN_NAME
```

The runner refuses an existing output directory, uses a separate persistent budget ledger, pins the approved cheap model pool and saves failures alongside successes. It does not consume or reset public per-IP counters. Each invocation must fit the remaining user-authorized research budget. Web sources can change; these are repeated smoke tests rather than identical deterministic benchmarks.

The defensible benefit demonstrated so far is inspectable perspectives, specific challenge references, uncertainty labels and visible verifier disagreement. Greater factual accuracy than a single-agent baseline has **not** been established.
