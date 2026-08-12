# Adaptive CS Tutor

**Adaptive CS Tutor is an independent prototype concept-graph tutor for introductory computer science.**

It uses a short diagnostic to identify shaky CS1 concepts, propagates prerequisite risk through a hand-authored curriculum graph, and generates English or Arabic explanations that retrieve relevant prerequisites first. It is a research/software **prototype**: it has not been evaluated in a classroom or used to establish learning-outcome claims.

## What it does

- Scores a 22-question diagnostic against a 31-concept CS1 prerequisite graph.
- Marks concepts missed by the diagnostic as **shaky** and transitive dependents as **at risk**.
- Orders remediation foundations-first, then by downstream concepts unlocked.
- Retrieves up to four nearest prerequisite passages before asking an optional local LLM to explain a target concept.
- Provides bilingual English/Arabic explanations; code identifiers remain in English.
- Runs without network access or a model by serving included bilingual fallback passages.

The graph, questions, and explanation corpus are intentionally small and hand-authored. This repository does not claim student adoption, funding, awards, or learning-effectiveness results.

## Install

**Requirements:** Python 3.10 or newer. Runtime code uses the Python standard library only.

```bash
git clone https://github.com/Yusuf-Gadelrab/adaptive-cs-tutor.git
cd adaptive-cs-tutor
python3 --version
```

No package installation is required for the offline tutor. `pytest` (or `uv`) is only needed to run the test suite.

## Quickstart

Run the deterministic offline walkthrough—no model or network connection required:

```bash
python3 cli.py health
python3 cli.py demo --no-llm
```

Try individual workflows:

```bash
python3 cli.py quiz
python3 cli.py explain recursion --no-llm
python3 cli.py explain recursion --lang ar --no-llm
python3 cli.py path --wrong q2,q9
```

Start the local web interface at <http://localhost:8123>:

```bash
python3 server.py --no-llm
```

`demo.sh` runs the test suite plus a complete walkthrough. Use its offline mode when a local model is unavailable:

```bash
./demo.sh --offline
```

## Optional local LLM

The tutor can use Ollama at `http://localhost:11434` for generated explanations. The configured model name defaults to `qwen3-fast` and can be changed with the `TUTOR_MODEL` environment variable. If Ollama or the configured model is unavailable, explanations automatically fall back to the bundled bilingual passages.

```bash
# In a separate terminal, start Ollama after installing/configuring a compatible local model.
ollama serve

# Then run the tutor normally; it falls back safely if the model is unavailable.
python3 cli.py explain recursion
python3 server.py
```

## Tests

The test suite is offline and does not require Ollama. With `uv` installed:

```bash
uv run --with pytest pytest
```

Alternatively, install the development dependency `pytest` in your preferred environment and run:

```bash
python3 -m pytest
```

## Project layout

| Path | Purpose |
| --- | --- |
| `graph.json` | Hand-authored CS1 concepts and prerequisite edges |
| `quiz.json` | Diagnostic questions and answer keys |
| `explanations.json` | English and Arabic explanation passages, including offline fallback text |
| `graph_engine.py` | Scoring, graph propagation, and learning-path logic |
| `explainer.py` | Graph-based retrieval, prompt construction, Ollama transport, and fallback handling |
| `cli.py` | Command-line interface |
| `server.py` | Standard-library HTTP server and single-page web UI |
| `evaluate.py` | Reproducible evaluation harness for implementation-level checks |
| `tests/` | Offline automated tests |

## How the prototype works

```text
quiz.json ──> score diagnostic ──> shaky concepts
                                      |
                         graph.json ──> prerequisite propagation ──> at risk
                                      |
                                      +──> ordered remediation path
                                      |
                                      +──> retrieve nearest prerequisite passages
                                                     |
                                                     v
                                      optional local Ollama explanation
                                      or included bilingual fallback passage
```

A wrong answer identifies the concept tested by that item as shaky. The graph then marks concepts that depend on it as at risk; this is a structural signal to guide review, not evidence that a student cannot perform those downstream concepts. To explain a concept, the retriever walks its prerequisite chain and includes the nearest available prerequisite passages in the model context.

## Limitations

- The graph is a small, hand-authored CS1 curriculum map, not a comprehensive curriculum.
- A single wrong item can mark a concept shaky; this is a prototype diagnostic rather than a validated assessment.
- “At risk” is an inference from graph structure, not a student-performance measurement.
- The included Arabic material is not presented as instructor-reviewed pedagogical content.
- The implementation has not been trialed with students; do not infer learning outcomes from its automated tests or evaluation harness.

## SIGCSE 2026 contributions by Yusuf Gadelrab

- **Peer-reviewed poster:** *Exploring Bilingual Coding for Inclusive Computer Science Learning.* ACM SIGCSE Technical Symposium 2026, Proceedings V.2, pp. 1559–1560. DOI: [10.1145/3770761.3777339](https://doi.org/10.1145/3770761.3777339). Yusuf Gadelrab is listed seventh in the author order.
- **Accepted CER-track paper:** Ethel Tshukudu, Thien Khang Kieu, Leqaa Deeb, Harshitha Venkateswaran, and Yusuf Gadelrab. *Does Language Matter in Programming? Exploring Student Attitudes and Experiences in a Bilingual Coding Workshop.* SIGCSE Virtual 2026. Yusuf Gadelrab is fifth of five authors. [Official listing](https://sigcsevirtual2026.acm.org/details/sigcse-virtual-2026-papers/31/Does-Language-Matter-in-Programming-Exploring-Student-Attitudes-and-Experiences-in-a)

This repository is a separate software prototype and should not be represented as a classroom evaluation or as either SIGCSE contribution.

## Citation

If you use this software, please cite the repository version you used. Citation metadata is available in [`CITATION.cff`](CITATION.cff).

```text
Gadelrab, Yusuf. (2026). Adaptive CS Tutor (Version 1.0.0) [Computer software].
https://github.com/Yusuf-Gadelrab/adaptive-cs-tutor
```

When referring to Yusuf Gadelrab’s SIGCSE contributions, preserve their item types and author positions:

- *Exploring Bilingual Coding for Inclusive Computer Science Learning.* (2026). **Peer-reviewed poster**, SIGCSE Technical Symposium 2026, Proceedings V.2, pp. 1559–1560. DOI: https://doi.org/10.1145/3770761.3777339. Yusuf Gadelrab is listed seventh in the author order.
- Tshukudu, E., Kieu, T. K., Deeb, L., Venkateswaran, H., & Gadelrab, Y. (2026). *Does Language Matter in Programming? Exploring Student Attitudes and Experiences in a Bilingual Coding Workshop.* **Accepted CER-track paper**, SIGCSE Virtual 2026. Yusuf Gadelrab is fifth of five authors. https://sigcsevirtual2026.acm.org/details/sigcse-virtual-2026-papers/31/Does-Language-Matter-in-Programming-Exploring-Student-Attitudes-and-Experiences-in-a

## License

This project is released under the [MIT License](LICENSE). Copyright © 2026 Yusuf Gadelrab.
