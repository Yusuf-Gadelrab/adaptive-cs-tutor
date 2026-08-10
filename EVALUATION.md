# Evaluation

Every number quoted about this project comes from `evaluate.py`. Nothing here
is estimated.

## Reproduce

```bash
ollama serve
python3 evaluate.py --json eval-results.json
```

Full per-item results, including the raw text of all 36 generations, are in
[`eval-results.json`](eval-results.json).

## Setup

| | |
|---|---|
| Model | `qwen3-fast` (Qwen3-30B-A3B MoE, Q4_K_M) via Ollama HTTP |
| Hardware | Apple M1 Max, local inference only |
| Sample | 12 concepts spanning depth 2–6 and all 6 clusters |
| Languages | English and Arabic — 24 model generations |
| Cache | **Disabled.** Every call is a real generation |
| Control | 12 further explanations with the model switched off |
| Date | 2026-07-29 |
| Cost | $0.00 |

Sampled concepts: `boolean_logic`, `conditionals`, `loops_for`, `functions`,
`recursion`, `lists`, `dicts`, `complexity`, `classes`, `inheritance`,
`sorting`, `file_io`. All have at least one prerequisite, so grounding is
meaningful for every item.

## Results

| Metric | English | Arabic | Control (no LLM) |
|---|---|---|---|
| Explanations generated | 12 | 12 | 12 |
| **Prerequisite grounding rate** | **1.000** (12/12) | **0.833** (10/12) | **0.250** (3/12) |
| Arabic output rate | — | 1.000 (12/12) | — |
| **Code-identifier preservation** | — | **1.000** (12/12) | — |
| **Reasoning leaked to student** | **0** | **0** | **0** |
| Latency mean | 36.01 s | 38.12 s | — |
| Latency median | 28.42 s | 39.09 s | — |
| Latency min / max | 5.10 s / 61.29 s | 18.74 s / 54.69 s | — |

Combined across both languages: **22 of 24 generations (0.917)** named a
prerequisite the retriever had injected.

### What each metric means

**Prerequisite grounding rate** — the share of explanations that name at least
one of the prerequisite concepts the retriever actually put in the prompt. This
is the core design goal of this project's own graph-augmented retrieval
engine: that graph-driven retrieval makes explanations build on prior
knowledge rather than floating free.

The control run is the important column. The canned fallback passages are good
CS1 explanations, but they are static text written without any knowledge of a
particular student's retrieved prerequisites — and they score **0.250**.
Graph-grounded generation scores **1.000** in English. The metric discriminates;
it is not a formality that everything passes.

**Code-identifier preservation** — the share of Arabic explanations that contain
Arabic script *and* still carry recognisable English code tokens or an
ASCII code block. This is the bilingual paper's design rule: switch the prose,
never the code. **12 of 12**, with no failures.

**Reasoning leakage** — how many generations contained `<think>` or `</think>`
after processing. This started as a real defect (see below) and is the reason
the check exists. **0 of 36.**

### The two Arabic misses

`loops_for` and `functions` produced correct, useful Arabic explanations that
simply did not name a retrieved prerequisite in a form the checker recognises.
The checker matches English concept names and ids; Arabic prose that refers to a
prerequisite using an Arabic gloss instead of the English term is scored as a
miss. So **0.833 is a floor, not a ceiling** — the true rate is at least that
and probably higher. Fixing it means adding Arabic aliases per concept, which is
a data change, not an architecture change.

Being precise about this matters more than the number looking better.

### Latency

Latency is high and worth stating plainly: a mean of **36 seconds** for a
30-billion-parameter model quantised to 4 bits, generating on a laptop. The
spread (5.1 s to 61.3 s) tracks output length — the slowest runs hit the
400-token generation cap.

Two mitigations exist in the product, neither of which is used in these numbers:

- **Disk cache.** A repeated explanation is served instantly. The eval disables
  it so that every measurement is a genuine generation.
- **Offline passages.** `--no-llm` answers immediately for every concept.

The diagnostic, the propagation and the learning path are all **instant** — that
work is pure Python and never touches the model. Only prose generation is slow.

## The reasoning-leakage defect

This check exists because the failure was real, and it was the worst kind: the
system produced confident output that was not an explanation.

`qwen3-fast`'s chat template opens a `<think>` block unconditionally, so:

1. `"think": false` was ignored — reasoning arrived in the content field, ended
   by a stray `</think>` with no opening tag.
2. Qwen3's `/no_think` soft switch was also ignored.
3. When reasoning ran past `num_predict`, the closing tag never arrived. The
   strip logic had nothing to match, and raw chain-of-thought was served as the
   lesson.

The fix (`render_chatml()`) builds the ChatML prompt by hand and sends it with
`raw: true`, pre-closing the block with an empty `<think></think>` pair so
generation starts on the answer. `strip_thinking()` stays as defence in depth,
and a response that is *only* reasoning is discarded rather than displayed.

Measured outcome: **0 leaks in 36 generations.** Regression coverage lives in
`tests/test_explainer.py::TestStripThinking` and
`TestFallbackContract::test_reasoning_only_generation_falls_back`.

## Test suite

```bash
$ uv run --with pytest pytest
91 passed in 3.86s
```

91 tests, no network required, covering:

- graph loading, DAG validation, cycle detection, topological depth
- shaky → at-risk propagation, including multi-source and unrelated branches
- learning-path ordering, tie-breaking determinism, and unlock sets
- quiz well-formedness: unique ids, valid concepts, in-range answer keys, no
  constant-index answer key, full cluster coverage
- retrieval: nearest-K selection, ancestor validity, passage completeness
- prompt construction and the pre-closed ChatML think block
- all four reasoning-strip failure shapes
- the fallback contract: `explain()` cannot raise because of the model
- every HTTP endpoint, including answer-key leakage and malformed input

## What has not been measured

- **Learning outcomes.** No claim is made that this improves student
  performance. The research it derives from was studied with participants; this
  implementation has not been trialled in a classroom.
- **Pedagogical quality of the Arabic.** Verified programmatically for script
  and code-token preservation, not reviewed by an Arabic-speaking CS instructor.
- **Explanation correctness.** Grounding measures whether an explanation builds
  on prerequisites, not whether it is factually right. Spot-checked by hand
  across the sample; not systematically graded.
- **Graph validity as a curriculum.** The prerequisite edges are hand-authored
  and reflect one person's reading of CS1 structure.
