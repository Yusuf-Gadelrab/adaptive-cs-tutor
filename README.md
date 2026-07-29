# Adaptive CS Tutor

A diagnostic concept-graph tutor for intro CS, built from two of my published
SIGCSE TS 2026 papers:

- *Exploring Bilingual Coding for Inclusive CS Learning* — DOI: [10.1145/3770761.3777339](https://doi.org/10.1145/3770761.3777339)
- *Adaptive Curriculum Maps: Graph-Augmented Retrieval-Oriented LLMs for Education* (poster)

Take a 12-question diagnostic quiz → wrong answers mark concept nodes
**shaky** → graph propagation marks everything downstream that depends on a
shaky concept as **at risk** → click any node for an explanation that's
retrieval-grounded in that concept's actual prerequisite chain (RAG, not a
generic LLM answer) → flip the whole UI to Arabic, per Paper 1's bilingual
finding (code identifiers stay in English intentionally).

100% local, $0 stack: stdlib Python server, no npm, no cloud API. Ollama
(`qwen3-fast`) is optional — a `--no-llm` mode with canned bilingual
explanations is built in as a demo-safety net, and works standalone with
zero network calls.

## Run it

```bash
cd adaptive-cs-tutor
python3 server.py              # tries Ollama at localhost:11434, auto-falls back if it's not running
# or, to force the offline fallback (recommended for a reliable demo):
python3 server.py --no-llm
```

Then open **http://localhost:8123**.

- Take the quiz, hit **Submit Quiz** — watch nodes turn yellow (shaky) / red (at risk).
- Click any node to get an explanation grounded in its prerequisite chain.
- Click the language button (top right) to flip English ⇄ Arabic.

No `pip install` needed — everything is Python 3 stdlib (`http.server`,
`urllib`, `json`, `argparse`). Ollama, if running, is only ever called via
its HTTP API (`POST /api/generate` at `localhost:11434`) — never via
`ollama run` subprocess capture.

## Run the tests

The concept-graph propagation logic — the "adaptive" part — is pure Python
with zero dependency on Ollama or the server, and has its own test suite:

```bash
python3 test_graph_engine.py -v
```

19 tests covering graph loading/validation, cycle detection, forward
propagation from shaky → at-risk (single node, multi-node, unrelated
branches, leaf nodes), prerequisite-chain ordering, and quiz scoring.

## Architecture

| File | Role |
|---|---|
| `graph.json` | 31 intro-CS concepts with prerequisite edges (hand-authored DAG) |
| `quiz.json` | 12 diagnostic questions, 2–3 per concept cluster |
| `explanations.json` | Canned bilingual (en/ar) explanations — the offline fallback content |
| `graph_engine.py` | Pure-Python graph load/validate/propagate/prereq-chain logic |
| `test_graph_engine.py` | Standalone unit tests for the above |
| `explainer.py` | RAG layer: builds prereq-chain context, calls Ollama HTTP API or falls back |
| `server.py` | stdlib `http.server` — serves the single-page UI + JSON API |

## API

- `GET /api/graph` — nodes with layout coordinates + prerequisite edges
- `GET /api/quiz` — quiz questions (answer keys withheld until scoring)
- `POST /api/submit` — `{"answers": {"q1": 1, ...}}` → shaky concepts + propagated states
- `GET /api/explain?concept=recursion&lang=en[&no_llm=1]` — RAG explanation
- `GET /api/health` — sanity check

## Why this is a real entry, not a toy

Both papers involved a live IRB-approved study (60 participants, mixed
methods). This tool operationalizes the two core findings: (1) a
graph-augmented curriculum map that shows students exactly what's shaky vs.
what depends on it, and (2) bilingual delivery that keeps code syntax in
English while explanations flex to the student's language — because the
original paper found that mixing natural-language scaffolding with
English-only code identifiers improved comprehension without teaching
"fake" syntax.
