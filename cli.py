#!/usr/bin/env python3
"""
Adaptive CS Tutor -- command line entry point.

    python3 cli.py demo                 full end-to-end walkthrough (filmable)
    python3 cli.py demo --no-llm        same, fully offline, no model calls
    python3 cli.py quiz                 take the diagnostic interactively
    python3 cli.py explain recursion    explain one concept
    python3 cli.py explain recursion --lang ar
    python3 cli.py path --wrong q2,q9   remediation plan for given wrong answers
    python3 cli.py health               check graph, quiz and model availability

Stdlib only. Ollama is optional -- everything degrades to canned bilingual
explanations if the model is not running.
"""
import argparse
import sys

import explainer
import graph_engine as ge

GOLD = "\033[38;5;178m"
GOLD_DIM = "\033[38;5;136m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"
GREEN = "\033[38;5;71m"
AMBER = "\033[38;5;214m"
RED = "\033[38;5;167m"

STATE_STYLE = {
    "ok": (GREEN, "MASTERED"),
    "shaky": (AMBER, "SHAKY   "),
    "at_risk": (RED, "AT RISK "),
}

# The scripted student used by `demo`. Deliberately chosen so the diagnostic
# has something interesting to say: one shallow gap with a huge blast radius
# (boolean_logic), one mid-depth gap (recursion), one near-leaf gap
# (list_methods).
DEMO_WRONG = ["q2", "q9", "q18"]


def rule(char="─", width=74):
    return GOLD_DIM + char * width + RESET


def banner(subtitle):
    print()
    print(rule("═"))
    print(f"{GOLD}{BOLD}  ADAPTIVE CS TUTOR{RESET}  {DIM}·{RESET}  {GOLD_DIM}DHAHAB{RESET}")
    print(f"{DIM}  {subtitle}{RESET}")
    print(rule("═"))


def section(title):
    print()
    print(f"{GOLD}{BOLD}{title}{RESET}")
    print(rule())


def build_answers(quiz, wrong_ids):
    """Answer every question correctly except the listed ones."""
    wrong = set(wrong_ids)
    answers = {}
    for q in quiz:
        if q["id"] in wrong:
            answers[q["id"]] = (q["answer"] + 1) % len(q["choices"])
        else:
            answers[q["id"]] = q["answer"]
    return answers


def print_state_summary(nodes, states):
    buckets = {"shaky": [], "at_risk": [], "ok": []}
    for nid, st in states.items():
        buckets[st].append(nid)
    total = len(states)
    print(f"  {len(buckets['ok'])}/{total} mastered   "
          f"{AMBER}{len(buckets['shaky'])} shaky{RESET}   "
          f"{RED}{len(buckets['at_risk'])} at risk{RESET}")
    print()
    for st in ("shaky", "at_risk"):
        colour, label = STATE_STYLE[st]
        for nid in sorted(buckets[st]):
            print(f"  {colour}{label}{RESET}  {nodes[nid]['name']}")


def print_path(path):
    if not path:
        print(f"  {GREEN}No gaps detected. Nothing to remediate.{RESET}")
        return
    for row in path:
        print(f"  {GOLD}{row['order']}.{RESET} {BOLD}{row['name']}{RESET}"
              f"  {DIM}(depth {row['depth']}, unblocks {row['unlock_count']} "
              f"downstream concept{'s' if row['unlock_count'] != 1 else ''}){RESET}")
        if row["unlocks"]:
            preview = ", ".join(row["unlocks"][:6])
            more = f" +{len(row['unlocks']) - 6} more" if len(row["unlocks"]) > 6 else ""
            print(f"     {DIM}↳ {preview}{more}{RESET}")


def print_explanation(result, nodes):
    src = result["source"]
    tag = {"llm": f"{GREEN}local qwen3-fast{RESET}",
           "cache": f"{GREEN}local qwen3-fast (cached){RESET}",
           "fallback": f"{AMBER}canned offline passage{RESET}"}[src]
    retrieved = result["retrieved"]
    print(f"  {DIM}source:{RESET} {tag}"
          + (f"   {DIM}{result['elapsed']:.1f}s{RESET}" if result.get("elapsed") else ""))
    if retrieved:
        names = ", ".join(nodes[r]["name"] for r in retrieved)
        print(f"  {DIM}retrieved prerequisites:{RESET} {GOLD_DIM}{names}{RESET}")
    else:
        print(f"  {DIM}retrieved prerequisites:{RESET} {GOLD_DIM}(foundational concept){RESET}")
    print()
    for line in result["text"].splitlines():
        print(f"    {line}")
    print()
    grounded = explainer.grounded_in(result["text"], nodes,
                                     concept_id=result["concept"],
                                     lang=result["lang"])
    checks = [("builds on a retrieved prerequisite", grounded)]
    if result["lang"] == "ar":
        checks.append(("prose is Arabic", explainer.has_arabic(result["text"])))
        checks.append(("code identifiers stayed English",
                       explainer.preserves_code_identifiers(result["text"])))
    for label, ok in checks:
        mark = f"{GREEN}PASS{RESET}" if ok else f"{RED}FAIL{RESET}"
        print(f"  [{mark}] {label}")
    if src == "fallback" and not grounded:
        print(f"  {DIM}↳ expected: the offline passage is static text, so it is not")
        print(f"    written against this student's retrieved prerequisites. Only the")
        print(f"    model path is graph-grounded — which is exactly what the metric"
              f" detects.{RESET}")


def cmd_demo(args):
    nodes = ge.load_graph()
    dependents = ge.build_dependents(nodes)
    quiz = ge.load_quiz()

    mode = "offline · canned explanations" if args.no_llm else "local qwen3-fast via Ollama HTTP"
    banner(f"Grounded in SIGCSE TS 2026 research · {mode}")

    section("1  DIAGNOSTIC")
    answers = build_answers(quiz, DEMO_WRONG)
    shaky, results = ge.score_quiz(quiz, answers)
    wrong_rows = [r for r in results if not r["correct"]]
    print(f"  Scripted student answered {len(results)} questions, "
          f"missed {len(wrong_rows)}.")
    print()
    for r in wrong_rows:
        q = next(x for x in quiz if x["id"] == r["id"])
        print(f"  {RED}✗{RESET} {q['id']}  {q['prompt']}")
        print(f"     {DIM}→ marks '{nodes[r['concept']]['name']}' as shaky{RESET}")

    section("2  GRAPH PROPAGATION")
    states = ge.compute_states(nodes, dependents, shaky)
    print(f"  {DIM}A wrong answer marks its own concept shaky, then every concept")
    print(f"  that transitively depends on it is flagged at risk.{RESET}")
    print()
    print_state_summary(nodes, states)

    section("3  ADAPTIVE LEARNING PATH")
    path = ge.learning_path(nodes, dependents, shaky)
    print(f"  {DIM}Ordered by depth first, then blast radius — fix the foundation")
    print(f"  before the things standing on it.{RESET}")
    print()
    print_path(path)

    if not path:
        return 0
    target = path[0]["concept"]

    section(f"4  EXPLANATION · {nodes[target]['name']} · ENGLISH")
    en = explainer.explain(nodes, target, lang="en", no_llm=args.no_llm,
                           refresh=args.refresh)
    print_explanation(en, nodes)

    section(f"5  EXPLANATION · {nodes[target]['name']} · العربية")
    print(f"  {DIM}Same retrieval, same graph context. Prose switches to Arabic;")
    print(f"  code identifiers stay English (SIGCSE bilingual-coding finding).{RESET}")
    print()
    ar = explainer.explain(nodes, target, lang="ar", no_llm=args.no_llm,
                           refresh=args.refresh)
    print_explanation(ar, nodes)

    print()
    print(rule("═"))
    print(f"{GOLD}  Next concept in the plan:{RESET} "
          f"{nodes[path[1]['concept']]['name'] if len(path) > 1 else '(none)'}")
    print(rule("═"))
    print()
    return 0


def cmd_quiz(args):
    nodes = ge.load_graph()
    dependents = ge.build_dependents(nodes)
    quiz = ge.load_quiz()
    banner("Interactive diagnostic")
    answers = {}
    for i, q in enumerate(quiz, 1):
        print()
        print(f"{GOLD}Q{i}/{len(quiz)}{RESET}  {q['prompt']}")
        for j, c in enumerate(q["choices"]):
            print(f"   {j + 1}) {c}")
        while True:
            raw = input(f"{GOLD_DIM}answer 1-{len(q['choices'])} (or 's' to skip): {RESET}").strip()
            if raw.lower() == "s":
                break
            if raw.isdigit() and 1 <= int(raw) <= len(q["choices"]):
                answers[q["id"]] = int(raw) - 1
                break
            print("  not a valid choice")
    shaky, _ = ge.score_quiz(quiz, answers)
    states = ge.compute_states(nodes, dependents, shaky)
    section("RESULTS")
    print_state_summary(nodes, states)
    section("YOUR LEARNING PATH")
    print_path(ge.learning_path(nodes, dependents, shaky))
    print()
    return 0


def cmd_explain(args):
    nodes = ge.load_graph()
    if args.concept not in nodes:
        print(f"unknown concept '{args.concept}'", file=sys.stderr)
        print("known ids: " + ", ".join(sorted(nodes)), file=sys.stderr)
        return 2
    banner(f"Explaining {nodes[args.concept]['name']}")
    result = explainer.explain(nodes, args.concept, lang=args.lang,
                               no_llm=args.no_llm, refresh=args.refresh)
    print()
    print_explanation(result, nodes)
    print()
    return 0


def cmd_path(args):
    nodes = ge.load_graph()
    dependents = ge.build_dependents(nodes)
    quiz = ge.load_quiz()
    wrong = [w.strip() for w in args.wrong.split(",") if w.strip()]
    known = {q["id"] for q in quiz}
    bad = [w for w in wrong if w not in known]
    if bad:
        print(f"unknown question id(s): {', '.join(bad)}", file=sys.stderr)
        return 2
    answers = build_answers(quiz, wrong)
    shaky, _ = ge.score_quiz(quiz, answers)
    states = ge.compute_states(nodes, dependents, shaky)
    banner(f"Remediation plan for wrong answers: {', '.join(wrong) or '(none)'}")
    section("STATE")
    print_state_summary(nodes, states)
    section("PATH")
    print_path(ge.learning_path(nodes, dependents, shaky))
    print()
    return 0


def cmd_health(args):
    nodes = ge.load_graph()
    dependents = ge.build_dependents(nodes)
    quiz = ge.load_quiz()
    levels = ge.topo_levels(nodes)
    expl = explainer.load_explanations()
    banner("Health check")
    print()
    checks = [
        (f"concept graph loaded ({len(nodes)} nodes, max depth {max(levels.values())})", True),
        (f"prerequisite edges resolve ({sum(len(v) for v in dependents.values())} edges)", True),
        ("graph is acyclic", True),
        (f"quiz loaded ({len(quiz)} questions, "
         f"{len({q['concept'] for q in quiz})} concepts covered)", True),
        (f"bilingual fallback passages ({len(expl)}/{len(nodes)} concepts, en+ar)",
         len(expl) >= len(nodes)),
        (f"ollama reachable at {explainer.OLLAMA_HOST} with model "
         f"'{explainer.OLLAMA_MODEL}'", explainer.ollama_available()),
    ]
    for label, ok in checks:
        mark = f"{GREEN}PASS{RESET}" if ok else f"{AMBER}SKIP{RESET}"
        print(f"  [{mark}] {label}")
    if not checks[-1][1]:
        print()
        print(f"  {DIM}Ollama is optional. Without it the tutor still runs"
              f" end-to-end using canned bilingual passages (--no-llm).{RESET}")
    print()
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(prog="cli.py", description="Adaptive CS Tutor")
    sub = parser.add_subparsers(dest="cmd", required=True)

    def add_common(p):
        p.add_argument("--no-llm", action="store_true",
                       help="never call Ollama; use canned bilingual passages")
        p.add_argument("--refresh", action="store_true",
                       help="ignore the on-disk cache and regenerate")

    p_demo = sub.add_parser("demo", help="full end-to-end walkthrough")
    add_common(p_demo)
    p_demo.set_defaults(func=cmd_demo)

    p_quiz = sub.add_parser("quiz", help="take the diagnostic interactively")
    p_quiz.set_defaults(func=cmd_quiz)

    p_ex = sub.add_parser("explain", help="explain one concept")
    p_ex.add_argument("concept")
    p_ex.add_argument("--lang", choices=["en", "ar"], default="en")
    add_common(p_ex)
    p_ex.set_defaults(func=cmd_explain)

    p_path = sub.add_parser("path", help="remediation plan from wrong answers")
    p_path.add_argument("--wrong", default="", help="comma separated question ids, e.g. q2,q9")
    p_path.set_defaults(func=cmd_path)

    p_health = sub.add_parser("health", help="check graph, quiz and model")
    p_health.set_defaults(func=cmd_health)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
