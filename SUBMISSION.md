# Adaptive CS Tutor — Devpost Submission

**Repo:** https://github.com/Yusuf-Gadelrab/adaptive-cs-tutor
**Built by:** Yusuf Gadelrab (solo) — SJSU Computer Science
**Cost to run:** $0. No API keys, no accounts, no cloud.

---

## Title

**Adaptive CS Tutor**

## Tagline

*It doesn't answer the question you asked. It finds the one you should have asked.*

> Alternates, if a shorter field is needed:
> - A concept-graph tutor that finds the gap under the gap — offline, bilingual, $0.
> - Published SIGCSE research, turned into a tutor that runs on your laptop with the Wi-Fi off.

---

## Inspiration

I co-authored two papers accepted to **SIGCSE TS 2026**, the ACM computer
science education conference:

- *Exploring Bilingual Coding for Inclusive CS Learning* — [10.1145/3770761.3777339](https://doi.org/10.1145/3770761.3777339)
- *Adaptive Curriculum Maps: Graph-Augmented Retrieval-Oriented LLMs for Education* (poster)

Both went through an IRB-approved study in Dr. Ethel Tshukudu's CSEd Research
Lab at SJSU. And then they did what papers do: they became PDFs.

Meanwhile I tutor CS1 students at SJSU, and I kept watching the same thing
happen. A student says "I don't get recursion." You explain recursion. It
doesn't land. Because they don't actually have a recursion problem — they have
a conditionals problem, three concepts upstream, and neither of you knows it.

Every AI tutor I've used makes this worse, not better. Ask about recursion, get
a great paragraph about recursion, stay exactly as stuck. The model answers the
question you asked, which is precisely the thing a good tutor refuses to do.

So I built the thing the papers describe.

## What it does

You take a 22-question diagnostic. Then four things happen that a chatbot
doesn't do:

**1. It diagnoses.** Every question maps to a node in a 31-concept prerequisite
graph. Miss one, and that concept is marked *shaky*.

**2. It propagates.** Everything transitively downstream of a shaky concept is
flagged *at risk*. Miss the boolean logic question and 19 other concepts light
up — not because you got them wrong, but because they're standing on something
that just broke. That's the diagnosis you can't get by asking a chatbot, because
you don't know to ask.

**3. It sequences the repair.** Weak topics come back as an *ordered plan*, not
a pile: foundations first, then widest blast radius. Fix Boolean Logic first —
it's the shallowest gap, and it alone is what's putting those 19 concepts at
risk. Fixing recursion first would be wasted effort.

**4. It teaches, grounded in the graph.** Click any concept and retrieval walks
its prerequisite chain, pulls the passages for the four nearest ancestors the
student has already been taught, and puts them in the prompt. So the explanation
of recursion is *built out of* functions and conditionals — by construction, not
by luck. The UI shows you exactly which prerequisites were retrieved.

Then you hit the toggle and the entire thing — interface, learning path, and the
model's prose — becomes Arabic, while every keyword, identifier and code example
stays English. That's the bilingual paper's design, implemented literally.

The whole thing runs on a local model. Turn off your Wi-Fi and it still works.

## How I built it

**Stack:** Python 3 standard library. That's the whole runtime — no Flask, no
React, no npm, no vector database, no dependencies at all. `uv` for the test
suite. Ollama serving `qwen3-fast` (Qwen3-30B-A3B, 4-bit) over HTTP on
localhost.

**The graph** is 31 hand-authored CS1 concepts across 6 clusters with
prerequisite edges. Small and correct beats large and wrong. The engine
validates it's a DAG, computes topological depth, and does forward BFS from
shaky nodes to find at-risk ones.

**Retrieval is the interesting part.** There are no embeddings and no vector
store. The prerequisite graph *is* the retriever: to explain concept C, walk C's
ancestor chain root-first and take the nearest four — the material most recently
taught — then inject those concepts' actual explanation passages as context.
It's RAG where the index is a curriculum, which is the whole idea of the
Adaptive Curriculum Maps paper.

**Sequencing** sorts shaky concepts by depth ascending, then blast radius
descending, then id for determinism.

**Everything is measured, not asserted.** `evaluate.py` runs the real pipeline
over 12 concepts in both languages with caching disabled and reports
prerequisite-grounding rate, code-identifier preservation in Arabic, latency,
and reasoning-leakage count. It also runs a no-LLM control so the grounding
metric visibly discriminates instead of being trivially always-true. Every
number in this submission comes from that harness.

## Challenges I ran into

**Getting a reasoning model to stop reasoning.** This ate most of a day and
failed in three escalating stages:

1. `"think": false`, the documented Ollama switch, was **silently ignored** —
   the chain-of-thought came back inside the normal content field, terminated by
   a stray `</think>` with no opening tag.
2. Qwen3's `/no_think` soft switch was **also ignored**.
3. Then the genuinely dangerous one: when reasoning ran past the token budget,
   the closing tag never arrived. My strip logic had nothing to match, so raw
   chain-of-thought — *"We are asked to explain Boolean Logic. We should
   probably mention..."* — was served to the student as if it were the lesson.

`/api/show` finally explained it: this model's chat template opens a `<think>`
block unconditionally, so no request-level flag could ever close it. The fix was
to stop using the template — build the ChatML prompt by hand, send it with
`raw: true`, and pre-close the block with an empty `<think></think>` pair so
generation starts directly on the answer. Clean output, and it got faster
because the model stopped writing hundreds of reasoning tokens per explanation.

The lasting lesson: a response that is *only* reasoning must be discarded, never
displayed. There's now a test for exactly that.

**Making the grounding metric honest.** My first version marked an explanation
"grounded" if it mentioned any prerequisite — which the canned fallback passages
also did sometimes, by coincidence. A metric that everything passes measures
nothing. Adding the no-LLM control run was what made it real: it shows the gap
between graph-grounded generation and static text, and that gap is the actual
result.

**Deciding what not to build.** No login, no database, no deployment, no vector
store. Every one of those was tempting and none of them would have made the
diagnosis better.

## Accomplishments I'm proud of

- **Peer-reviewed research that actually runs.** Two SIGCSE TS 2026 papers,
  implemented as working software, cited by DOI, in a repo you can clone.
- **Zero dependencies and zero cost.** Whole runtime is Python stdlib. Whole
  inference bill is $0, forever, for anyone — which matters, because the
  students this is for are exactly the ones who can't expense an API key.
- **It works with the Wi-Fi off.** Not a fallback bolted on at the end: every
  concept has a bilingual passage, `explain()` cannot raise because of the
  model, and provenance is labelled in the UI so you always know what you're
  reading.
- **91 tests, and they test the hard parts** — propagation, path ordering,
  retrieval, the reasoning-strip failure modes, and every HTTP endpoint. The
  full suite runs offline in about 4 seconds.
- **Arabic that keeps its code English.** Prose flips, `def` and `return` don't
  — programmatically verified, not eyeballed.

## What's next

- **Multiple items per concept** so one wrong answer is a signal, not a verdict —
  the honest fix for the biggest current weakness.
- **Item-response theory** instead of binary shaky/at-risk, giving confidence
  levels rather than flags.
- **Instructor view:** point it at a class's results and surface the concept
  that's quietly breaking the most students at once.
- **More languages.** The bilingual layer is two JSON keys and a prompt rule —
  Spanish, Mandarin and Hindi are additive, not architectural.
- **A real classroom trial.** The research was studied with students; this
  implementation hasn't been. That's the next honest step, and the lab is the
  right place to do it.

## Built with

`python` · `python-stdlib` · `ollama` · `qwen3` · `local-llm` · `rag` ·
`knowledge-graph` · `graph-augmented-retrieval` · `http.server` · `uv` ·
`pytest` · `svg` · `computer-science-education` · `sigcse` · `bilingual` ·
`arabic` · `offline-first` · `zero-dependency`

## Try it out

```bash
git clone https://github.com/Yusuf-Gadelrab/adaptive-cs-tutor
cd adaptive-cs-tutor
./demo.sh --offline     # full walkthrough, no model, no network needed
```

With Ollama running, `./demo.sh --serve` adds the live local model and opens the
web UI at http://localhost:8123.

---

# 2-Minute Demo Video Script

**Total: 2:00.** Screen recording with voiceover. Two terminal windows and a
browser, all on a dark background. Speak at a normal pace — the lines below are
timed for roughly 150 words per minute.

**Before recording:**

```bash
cd ~/adaptive-cs-tutor
ollama serve                                    # separate terminal
python3 cli.py explain boolean_logic --lang en  # warm the model + cache
python3 cli.py explain boolean_logic --lang ar
./demo.sh --fast                                # confirm it's clean
```

Then clear the terminal and open http://localhost:8123 in a second window.
Pre-warming matters: the first generation loads 18GB of weights and takes ~30s.

---

### 0:00 – 0:12 · Hook

**SHOT:** Full-screen terminal, `cli.py demo` mid-run, the red AT RISK list
scrolling.

> "A student tells you they don't understand recursion. So you explain
> recursion. And it doesn't work — because they don't have a recursion problem.
> They have a conditionals problem, three concepts upstream. Nobody in the room
> knows that."

---

### 0:12 – 0:26 · What it is

**SHOT:** Cut to the browser. Concept graph, all nodes green. Slow scroll so the
whole DAG reads.

> "This is Adaptive CS Tutor. It's built from two papers I co-authored that were
> accepted to SIGCSE 2026 — the ACM computer science education conference. Every
> concept in intro CS, wired to its prerequisites."

---

### 0:26 – 0:44 · The diagnostic

**SHOT:** Answer three or four quiz questions on camera, deliberately missing
the boolean logic one. Click **Submit Diagnostic**.

> "You take a twenty-two question diagnostic. Miss one, and that concept goes
> amber. But watch what happens to everything standing on top of it."

**BEAT — let the graph recolour in silence for a full second.**

---

### 0:44 – 1:00 · Propagation

**SHOT:** Graph now amber and red. Cursor traces the edges from Boolean Logic
outward to Conditionals, Loops, Functions, Recursion.

> "One wrong answer. Nineteen concepts now at risk — not because I got them
> wrong, but because they're built on something that just broke. That's the
> diagnosis you can't get by asking a chatbot, because you don't know to ask."

---

### 1:00 – 1:16 · The learning path

**SHOT:** Scroll to the Your Learning Path panel. Numbered plan visible.

> "And it doesn't hand back a pile of weak topics. It hands back an order.
> Boolean Logic first — it's the shallowest gap, and it's the one putting all
> nineteen of those at risk. Fixing recursion first would be wasted effort."

---

### 1:16 – 1:36 · Grounded explanation

**SHOT:** Click the Boolean Logic node. Explanation streams in. Cursor
highlights the "Built on: Variables · Operators" provenance line and the green
check underneath.

> "Click it and a local model teaches it — but retrieval walks the prerequisite
> chain first and feeds it what I already know. So the explanation is built out
> of variables and operators, by construction. It shows you exactly what it
> retrieved."

---

### 1:36 – 1:50 · The Arabic flip

**SHOT:** Click العربية. Whole interface mirrors to RTL. Re-click the node.
Arabic explanation appears with an English Python block inside it. **Zoom in on
the code block.**

> "One toggle. The interface, the plan, the teaching — all Arabic. But the code
> stays English. That's the finding from the bilingual paper: switch the
> language you think in, never the language you code in."

---

### 1:50 – 2:00 · The close

**SHOT:** Cut to the menu bar. **Turn Wi-Fi off on camera.** Click another node.
It still answers.

> "And all of it runs on my laptop. No API key, no account, nothing to pay —
> forever. Which matters, because the students this is for are exactly the ones
> who can't expense an API key."

**END CARD (hold 3s, black background, gold text):**

```
ADAPTIVE CS TUTOR
github.com/Yusuf-Gadelrab/adaptive-cs-tutor

SIGCSE TS 2026 · 10.1145/3770761.3777339
100% local inference · $0
```

---

### Delivery notes

- The Wi-Fi-off moment at 1:50 is the single most memorable second in the video.
  Make sure the menu bar is visible and don't rush it.
- Let the graph recolour at 0:44 with **no narration**. The silence sells it.
- If a live generation is slow on the day, `./demo.sh --offline` produces the
  identical diagnostic and path — only the prose changes. Nothing on screen
  breaks.
- Don't voice any accuracy number. The measured results are in `EVALUATION.md`
  and the repo; the video is for the idea.
