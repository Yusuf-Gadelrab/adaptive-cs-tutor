# Demo Video Script (target: 2 minutes, one take)

Setup before recording: `python3 server.py --no-llm` (offline fallback —
reliable regardless of whether Ollama happens to be running), browser open
to `http://localhost:8123`, maybe kill Wi-Fi right before hitting record to
make the "runs 100% offline" point undeniable.

---

**0:00–0:15 — Hook**
> "This is my SIGCSE research, running. Two papers I co-authored got
> accepted to SIGCSE TS 2026 — one on bilingual CS education, one on
> graph-augmented curriculum maps for adaptive learning. This weekend I
> turned both into a working tool."

**0:15–0:40 — Quiz**
> "It starts with a diagnostic quiz — twelve questions across variables,
> loops, functions, recursion, lists, dictionaries, sorting."
(Click through a few answers, deliberately get 2–3 wrong — e.g. variables
and functions — then hit Submit Quiz.)

**0:40–1:05 — Red nodes / graph propagation**
> "Here's the part from the curriculum-maps paper: this isn't just
> pass/fail. It's a concept graph — 31 nodes, real prerequisite edges. Get
> 'variables' wrong, and everything downstream — data types, lists,
> sorting, even recursion — lights up red as 'at risk,' because the graph
> knows what depends on what."
(Point at the yellow/red spread on the SVG graph.)

**1:05–1:35 — Adaptive explanation**
> "Click any node and it explains that concept using exactly what the
> student already knows — the prerequisite chain — instead of a generic
> canned answer. This is retrieval-augmented: the context is the graph
> itself."
(Click a red/yellow node, show the explanation panel populate.)

**1:35–1:50 — Arabic flip**
> "And here's the bilingual thesis from paper one — flip the whole UI,
> including this explanation, to Arabic. Code identifiers stay in English on
> purpose — that's literally what the paper found improves comprehension
> without teaching fake syntax."
(Click language toggle, show explanation panel + UI strings in Arabic.)

**1:50–2:00 — Close**
> "Zero API cost, zero cloud — stdlib Python server plus a local model,
> running on my laptop with Wi-Fi off. Both papers are cited in the
> write-up. Thanks for watching."

---

## DOIs to put in the Devpost write-up
- Paper 1 (bilingual CS ed): `10.1145/3770761.3777339`
- Paper 2 (curriculum maps, poster): cite as accepted SIGCSE TS 2026 poster (add DOI if assigned before submission)
