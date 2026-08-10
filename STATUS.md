# Status — Adaptive CS Tutor / SIGCSE SRC rescue

Written 2026-07-31 after re-verifying deadline, running the real test suite,
and reconciling four look-alike codebases. Every number below came from a
command I ran and can be reproduced; nothing is estimated.

---

## 1. Deadline — CORRECTED, this is the headline finding

**SIGCSE TS 2026 SRC's deadline already passed and the conference already
happened.** The prior agent's premise ("rescue this for SIGCSE TS 2026 SRC")
is stale:

| | Date |
|---|---|
| SIGCSE TS 2026 SRC submission deadline (Round Two, EasyChair) | **Monday, 6 October 2025, 23:59 AoE** |
| SRC author notification | Thursday, 10 November 2025 (tentative) |
| SIGCSE TS 2026 conference itself | **Feb 18–21, 2026, St. Louis, MO** — already held |

Today is 2026-07-31. That deadline was ~10 months ago and the conference was
~5 months ago. **There is no live TS2026 SRC to submit to.** This is also
consistent with Yusuf already being a co-author on the accepted TS2026
poster — that track already concluded.

**The real, still-open target is SIGCSE TS 2027 SRC:**

| | Date |
|---|---|
| SIGCSE TS 2027 SRC submission deadline (Round Two, EasyChair) | **Wednesday, 30 September 2026, 23:59 AoE** |
| Author notification | Monday, 9 November 2026 |
| Final submission | Sunday, 29 November 2026 |
| Conference | Feb 17–20, 2027, Sacramento, CA |

That's ~2 months from today — real, but not an emergency.

**Required artifacts for the SRC (from the live TS2026 track page, format
does not change year to year):**
- 2 pages total: 250-word abstract + Problem and Motivation + Background and
  Related Work + Approach and Uniqueness + Results and Contributions +
  References. ACM SIG Conference 2-column template, US letter.
- All authors need ORCID iDs and active ACM Student Membership numbers.
- Faculty supervisor details + proof of current enrollment.
- Category: Undergraduate or Graduate (mutually exclusive with Posters track
  — can't submit the identical work to both).
- Submission via EasyChair (2026 link was
  `https://easychair.org/conferences/?conf=sigcsets2026`; the 2027 equivalent
  will post on `https://2027.sigcse-ts.acm.org/` closer to the deadline — not
  yet live as of this check).

Sources: live fetches of `sigcse2026.sigcse.org/track/sigcse-ts-2026-acm-student-research-competition`,
`sigcse2026.sigcse.org/`, and `2027.sigcse-ts.acm.org/`, all done today.

---

## 2. What's actually on disk — four codebases, not one

| Path | What it is | Repo |
|---|---|---|
| `~/adaptive-cs-tutor` | **This project.** SIGCSE-branded README/citations. Contains `demo.sh`, `evaluate.py`, `cli.py`, `server.py`, 91 passing tests. | `github.com/Yusuf-Gadelrab/adaptive-cs-tutor` |
| `~/Desktop/Money-Machine-Assets/competitions/adaptive-cs-tutor` | Same GitHub repo, stale local clone frozen at an early commit (missing `cli.py`, `evaluate.py`, tests/). No independent content — ignore it. | same origin as above |
| `~/Startups/prometheus-tutor` | A separate, more polished rebuild of the same engine, explicitly branded "Solo entry for the **Prometheus July AI Challenge**" (a Devpost hackathon — not SIGCSE). Own repo, own README, own SUBMISSION.md. | `github.com/Yusuf-Gadelrab/prometheus-tutor` |
| `~/Startups/ventures/adaptive-tutor` | A **business venture dossier** (`BUSINESS.md`) proposing to monetize this via grants/prizes/fellowships (all on the TD-visa green list), plus an MVP add-on (`mvp/`) layering cohorts, persistence, an instructor misconception heatmap, and an IRB-ready CSV export on top of the *same* `graph_engine.py`. Not a competition submission — a product-extension plan. | no separate GitHub repo checked |

**Important discovery:** `~/adaptive-cs-tutor`'s own commit history says explicitly
(commit `8bdc564`, made today by an agent, already pushed to origin):

> "Commits the working tree that was **built for the Prometheus challenge**
> but never pushed before the deadline."

So the `SUBMISSION.md` and `demo.sh`/`cli.py`/`evaluate.py` currently in this
repo are **Devpost hackathon materials** (tagline, "Inspiration", "Built
with" tags, 2-minute video script) that got merged into the SIGCSE-branded
repo — they are not, and were never meant to be, an ACM SRC extended
abstract. Confirmed by reading `SUBMISSION.md` directly: it is a
Devpost-field-by-field document, not a 2-page ACM paper.

**Repo state:** working tree is clean and pushed (`git status` → "nothing to
commit"; `git fetch` confirms local `HEAD` == `origin/master` at `8bdc564`).
That commit happened externally during this session (not made by me) — I
verified via `git log`/`reflog`/`git show`, I did not run `git commit` or
`git push` myself, consistent with the standing git-commit policy and the
"do not submit anything" hard rule for this task.

---

## 3. Test suite — real output

```
$ cd ~/adaptive-cs-tutor && uv run --with pytest pytest
........................................................................ [ 79%]
...................                                                      [100%]
91 passed in 3.13s
```

91/91 passing, 0 failures, 0 skips. Covers graph loading/DAG validation,
shaky→at-risk propagation, learning-path ordering, retrieval, prompt
construction, all four reasoning-strip failure modes, the offline fallback
contract, and every HTTP endpoint.

---

## 4. demo.sh and evaluate.py — both run, verified live

**`./demo.sh --offline`** — ran end-to-end, exit 0. Diagnostic → propagation
(12/31 concepts at-risk from the scripted 3-wrong-answer run) → learning path
→ bilingual canned explanations, zero network calls. Works exactly as
documented.

**`python3 cli.py health`** — all 6 checks PASS, including live Ollama
reachability once the model server was up.

**`server.py`** — smoke-tested on a throwaway port: `/api/health` returned
`{"ok": true, "nodes": 31, "questions": 22, ...}`, homepage returned HTTP 200.
Killed after the check.

**`evaluate.py`** — **Ollama was not running** when I started (`curl
localhost:11434` failed, no process). I started it
(`ollama serve`, background, HTTP-only, no `ollama run` capture — per your
standing rule) and confirmed `qwen3-fast` was already pulled. Then ran a real
reduced sample to prove the harness works without re-running the full
expensive 36-generation eval that was already done 2 days ago:

```
$ python3 evaluate.py --n 2 --lang en --skip-control
[ 1/2] OK   boolean_logic          llm         13.6s  grounded=True
[ 2/2] OK   conditionals           llm          1.7s  grounded=True
PREREQUISITE GROUNDING RATE ......... 1.0
reasoning leaked into output ........ 0
```

Confirmed functional, real LLM calls, real grounding check. The full
historical run already on disk (`EVALUATION.md`, dated 2026-07-29, from an
actual `evaluate.py --json` run, not re-run today to save time/tokens):

| Metric | English | Arabic | Control (no LLM) |
|---|---|---|---|
| Prerequisite grounding rate | 1.000 (12/12) | 0.833 (10/12) | 0.250 (3/12) |
| Code-identifier preservation | — | 1.000 (12/12) | — |
| Reasoning leaked | 0 | 0 | 0 |
| Latency mean/median | 36.0s / 28.4s | 38.1s / 39.1s | — |

No fabricated numbers used anywhere in this doc — every figure above is
either a command I ran this session or cited from the dated `EVALUATION.md`
that documents its own real run.

**Nothing was broken in the code.** The only real defect found was
environmental: Ollama wasn't running. Fixed for this session; note that it
does **not** auto-start on reboot unless the `com.ollama.ollama` launchd job
is actually enabled (it showed in `launchctl list` with no active PID before
I started it manually).

---

## 5. Is the SRC submission the poster, or something else?

**Distinct artifact, not the same work — three-way split:**

1. **The accepted poster** ("Adaptive Curriculum Maps: Graph-Augmented
   Retrieval-Oriented LLMs for Education") — already written, already
   accepted, already presented at TS2026 (Feb 2026). Done, closed.
2. **This software** (`adaptive-cs-tutor`) — a working implementation of the
   poster's idea (graph-driven retrieval instead of embeddings) plus a
   measurement harness. Real, tested, working. But its own submission
   document is a Devpost hackathon writeup for a *different* competition
   (Prometheus July AI Challenge), not an SRC abstract.
3. **An SRC extended abstract** — **does not exist yet, anywhere, in any of
   the four codebases checked.** Nothing on disk is in ACM 2-page format
   with the required section headers.

The legitimate framing for a TS2027 SRC entry would be: the poster
*proposed* graph-augmented retrieval; this repo is the *first empirical
implementation and evaluation* of it, with a measured grounding-rate result
(1.000 vs. 0.250 control) that didn't exist when the poster was written. That
is a defensible "distinct research contribution," but reusing an idea from an
already-presented poster for a new SRC entry has a novelty/research-integrity
angle only your advisor (Dr. Tshukudu) can actually clear — flag it to her
before writing, not after.

---

## 6. Remaining work to submit to SIGCSE TS 2027 SRC (deadline 30 Sep 2026)

| # | Task | Est. time | Notes |
|---|---|---|---|
| 1 | Confirm with Dr. Tshukudu that extending the already-presented poster into a new SRC entry is acceptable/advisable | 1 email + her turnaround | Do this first — gates everything else |
| 2 | Write the 2-page ACM-format extended abstract (250-word abstract, Problem/Motivation, Background/Related Work, Approach/Uniqueness, Results/Contributions, References) | 4–6 hrs | Content exists (README, EVALUATION.md, the two papers) — this is compression + reformatting + a related-work paragraph, not new research |
| 3 | Get/confirm ORCID iDs for all authors | ~15 min if none exist | Free, instant |
| 4 | Get/confirm active ACM Student Membership for all authors | ~20 min + ACM's small student fee | Needed for eligibility |
| 5 | Get faculty supervisor sign-off + enrollment verification | Depends on advisor availability | Bundle with item 1 |
| 6 | Watch `2027.sigcse-ts.acm.org` for the EasyChair link to open (not live yet as of today) | 0 (just check periodically) | — |
| 7 | Decide whether to keep `prometheus-tutor` and `adaptive-cs-tutor` as two separate public repos or consolidate — currently near-duplicate code under two repo names, which reads oddly if a reviewer looks you up | 30 min decision, more if merging | Not blocking, but worth doing before SRC review clicks through to GitHub |
| 8 | (Optional, strengthens the abstract) Re-run `evaluate.py` on the full sample right before submission so the numbers are maximally fresh | ~15–20 min (36 real LLM generations) | Current numbers are only 2 days old — not urgent |

**Total estimated hands-on time: roughly 6–8 hours of work + advisor
turnaround**, comfortably inside the ~2-month window to 30 Sept 2026.

---

## 7. Bottom line

- Code is solid: 91/91 tests pass, `demo.sh --offline` and `evaluate.py` both
  verified working live, `server.py` verified serving.
- The urgency in the original ask was based on a deadline that's already 10
  months gone. The real deadline (TS2027 SRC, Sept 30 2026) is not an
  emergency.
- The actual gap isn't code — it's a **from-scratch 2-page ACM abstract**
  that doesn't exist yet in any of the four related codebases, plus
  administrative items (ORCID, ACM membership, advisor sign-off) that only
  Yusuf and his advisor can close.
