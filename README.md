<div align="center">

# Adaptive CS Tutor

**A concept-graph diagnostic for introductory computer science.**
Twenty-two questions find the gap. The graph finds everything the gap is breaking.
A local model teaches it back, in English or Arabic, at zero cost.

`31 concepts` · `22 diagnostic questions` · `91 tests` · `0 paid APIs` · `runs with the Wi-Fi off`

</div>

---

## Why this exists

Most tutoring tools answer the question a student asks. That is usually the
wrong question — a student stuck on recursion is often really stuck on
conditionals, three concepts upstream, and neither of you knows it.

This project comes out of two papers accepted to **SIGCSE TS 2026**:

| Paper | Idea this repo implements |
|---|---|
| *Adaptive Curriculum Maps: Graph-Augmented Retrieval-Oriented LLMs for Education* (poster) | Retrieval driven by a prerequisite graph rather than embedding similarity: to teach concept C, retrieve C's prerequisite chain. |
| *Exploring Bilingual Coding for Inclusive Computer Science Learning* — [10.1145/3770761.3777339](https://doi.org/10.1145/3770761.3777339) | Explanatory prose switches language; code identifiers and keywords stay English. |

So the tutor does three things a chatbot does not:

1. **Diagnoses instead of answering.** A wrong answer marks its concept *shaky*,
   then every concept transitively depending on it is flagged *at risk*.
2. **Sequences the repair.** It returns an ordered plan — foundations first,
   then widest blast radius — rather than a pile of weak topics.
3. **Grounds every explanation in the graph.** The prompt carries the actual
   passages for the prerequisites the student has already been taught, so new
   ideas are built on old ones by construction.

---

## Run it

Requires Python 3.10+. The runtime has **zero dependencies** — stdlib only.
[`uv`](https://docs.astral.sh/uv/) is used for the test suite.

```bash
git clone https://github.com/Yusuf-Gadelrab/adaptive-cs-tutor
cd adaptive-cs-tutor
./demo.sh --offline          # complete walkthrough, no model, no network
```

That is the whole install. To use the local model as well:

```bash
ollama serve                 # in another terminal
./demo.sh                    # offline path, then the live local model
./demo.sh --serve            # ...and finish by opening the web UI
```

### The web UI

```bash
python3 server.py            # http://localhost:8123
python3 server.py --no-llm   # force the offline path
```

Click a node to be taught it. Take the diagnostic and the graph recolours, the
learning path appears, and the toggle in the corner flips the whole interface —
and the model's prose — to Arabic.

### Command line

```bash
python3 cli.py demo                    # scripted student, end to end
python3 cli.py demo --no-llm           # same, fully offline
python3 cli.py quiz                    # take the diagnostic yourself
python3 cli.py explain recursion       # teach one concept
python3 cli.py explain recursion --lang ar
python3 cli.py path --wrong q2,q9      # remediation plan for given mistakes
python3 cli.py health                  # graph, quiz and model status
```

### Tests

```bash
uv run --with pytest pytest            # 91 tests, no network required
```

---

## How it works

```
quiz.json ──▶ score_quiz ──▶ shaky concepts
                                  │
                    graph.json ──▶ compute_states ──▶ ok / shaky / at_risk
                                  │
                                  ├──▶ learning_path ──▶ ordered repair plan
                                  │
                                  └──▶ retrieve ──▶ prerequisite passages
                                                        │
                                                        ▼
                                          render_chatml ──▶ Ollama HTTP
                                                        │
                                            (unreachable? canned passage)
```

| File | Role |
|---|---|
| `graph.json` | 31 intro-CS concepts, hand-authored prerequisite edges, 6 clusters |
| `quiz.json` | 22 diagnostic questions, every cluster covered |
| `explanations.json` | Bilingual passage per concept — the retrieval corpus *and* the offline fallback |
| `graph_engine.py` | Scoring, propagation, topological depth, learning path. No model, no network |
| `explainer.py` | Graph-augmented retrieval, prompt construction, Ollama transport, metrics |
| `server.py` | Stdlib HTTP server + single-page UI |
| `cli.py` | Terminal client |
| `evaluate.py` | Measurement harness — the source of every number quoted |

### Retrieval

To explain concept `C`, `retrieve()` walks `C`'s full prerequisite chain
root-first and takes the **nearest 4 ancestors** — the material most recently
taught — pulling each one's explanation passage into the prompt. Explaining
`recursion` retrieves `operators → boolean_logic → conditionals → functions`.
The model is then told, by name, which of those it must connect to.

### Sequencing

`learning_path()` sorts shaky concepts by:

1. **Depth ascending** — you cannot repair a misconception while the thing it
   rests on is still broken.
2. **Blast radius descending** — among equals, fix the one that unblocks the
   most downstream material.
3. **Id** — so the output is deterministic and testable.

A student who misses boolean logic, recursion and list methods is told to fix
**Boolean Logic** first: depth 2, and it alone is what puts 19 other concepts
at risk.

### HTTP API

| Endpoint | Returns |
|---|---|
| `GET /api/graph` | nodes with layout coordinates + prerequisite edges |
| `GET /api/quiz` | questions with the answer key withheld |
| `POST /api/submit` | `{"answers":{"q1":1,…}}` → states, ordered path, summary |
| `GET /api/explain?concept=recursion&lang=ar` | explanation + retrieval provenance + checks |
| `GET /api/health` | inventory and model availability |

---

## The local model, and one hard-won lesson

Inference is **100% local** through the Ollama HTTP API at `localhost:11434`
(`qwen3-fast`, Qwen3-30B-A3B). No API keys, no accounts, no per-token cost.
The model is never invoked as a subprocess — only over HTTP.

Getting a reasoning model to stop reasoning turned out to be the hardest part
of the build, and it failed in three escalating ways:

1. `"think": false` — the documented switch — **was ignored.** Reasoning came
   back inside the normal content field, terminated by a stray `</think>`.
2. Qwen3's `/no_think` soft switch was **also ignored.**
3. Worst of all: when reasoning ran past `num_predict`, the closing tag never
   arrived. Nothing matched, nothing was stripped, and raw chain-of-thought was
   served to the student as though it were the lesson.

`/api/show` explained it — this model's chat template opens a `<think>` block
unconditionally, so no request-level flag can ever close it.

The fix is to stop using the template. `render_chatml()` builds the ChatML
prompt by hand and sends it with `raw: true`, **pre-closing the block with an
empty `<think></think>` pair** so generation begins on the answer:

```
<|im_start|>assistant
<think>

</think>

```

Generation now starts clean. `strip_thinking()` remains as defence in depth for
other models, and a response that is *only* reasoning is discarded rather than
displayed — there is a test for exactly that.

### It degrades, it does not break

If Ollama is down, slow, returns junk, or returns nothing but reasoning, the
tutor serves the canned bilingual passage for that concept instead. `explain()`
cannot raise because of the model. Every explanation is labelled with its
provenance, so you always know whether you are reading the model or the
fallback.

---

## Measured results

Every number quoted about this project comes from `evaluate.py` — 12 concepts,
both languages, cache disabled so each call is a real generation. Reproduce:

```bash
python3 evaluate.py --json eval-results.json
```

Full run and raw output: **[EVALUATION.md](EVALUATION.md)**.

| Metric | What it tests |
|---|---|
| **Prerequisite grounding rate** | Does the explanation actually name a prerequisite the retriever injected? |
| **Code-identifier preservation** | Does Arabic output keep English keywords, per the bilingual paper? |
| **Latency** | Wall-clock seconds per generation, on an M1 Max |
| **Reasoning leakage** | Did any chain-of-thought reach the student? Must be 0 |

The harness includes a **no-LLM control run** so the grounding metric is
visibly discriminating rather than trivially always-true: the static fallback
passages score far lower than graph-grounded model output. That gap is the
result.

---

## Limitations

- The concept graph is hand-authored for CS1. It is small and correct, not
  comprehensive — no compilers, no concurrency, no data structures past dicts.
- A single wrong answer marks a concept shaky. A real diagnostic needs several
  items per concept to separate a misconception from a slip.
- *At risk* is a structural inference, not evidence. It means "this rests on
  something broken", not "the student cannot do this".
- Explanation quality is bounded by a 30B model quantised to 4 bits.
- Arabic output is checked programmatically for script and code-token
  preservation. It has not been reviewed for pedagogical quality by an
  Arabic-speaking CS instructor.
- The tutor itself has not been trialled with students. The research it derives
  from was; this implementation has not.

---

## About the author

Built by **Yusuf Gadelrab** — computer science student at San José State
University (BS Computer Science, expected May 2028) and co-author of two
peer-reviewed SIGCSE Technical Symposium 2026 papers on computer science
education, written in Dr. Ethel Tshukudu's CSEd Research Lab at SJSU.

- Portfolio: <https://yusuf-gadelrab.github.io/>
- About / FAQ: <https://yusuf-gadelrab.github.io/about.html>
- Guides: <https://yusuf-gadelrab.github.io/guides.html>
- Contact: yusuf.gadelrab06@gmail.com

Runtime: Python stdlib. Model: Qwen3-30B-A3B via Ollama. Cost: $0.
MIT licensed.
