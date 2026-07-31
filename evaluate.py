#!/usr/bin/env python3
"""
Evaluation harness.

Every number quoted about this project comes from here. Run it yourself:

    python3 evaluate.py                 # default sample, English + Arabic
    python3 evaluate.py --n 12          # bigger sample
    python3 evaluate.py --lang en       # one language only
    python3 evaluate.py --json out.json # machine readable

Three things are measured, each one testing a specific claim:

  1. PREREQUISITE GROUNDING RATE
     Claim: graph-augmented retrieval makes explanations build on what the
     student already knows. Measured as the share of generated explanations
     that name at least one of the prerequisite concepts the retriever
     actually injected. Concepts with no prerequisites are excluded, since
     there is nothing to ground in.

  2. CODE-IDENTIFIER PRESERVATION (Arabic only)
     Claim: Arabic prose, English code -- the SIGCSE bilingual-coding
     finding. Measured as the share of Arabic explanations that contain
     Arabic script AND still contain recognisable English code tokens.

  3. LATENCY
     Wall-clock seconds per explanation against the local model, reported as
     mean / median / min / max. No cache, every call is a real generation.

A no-LLM control run is included so the grounding metric is visibly
discriminating rather than trivially always-true.
"""
import argparse
import json
import statistics
import sys
import time

import explainer
import graph_engine as ge

# Concepts sampled by default: a spread across depth and cluster, all of them
# with at least one prerequisite so grounding is meaningful.
DEFAULT_SAMPLE = [
    "boolean_logic", "conditionals", "loops_for", "functions",
    "recursion", "lists", "dicts", "complexity",
    "classes", "inheritance", "sorting", "file_io",
]


def evaluate(nodes, concepts, lang, no_llm=False, timeout=180, verbose=True):
    rows = []
    for i, cid in enumerate(concepts, 1):
        ctx = explainer.retrieve(nodes, cid, lang=lang)
        t0 = time.time()
        res = explainer.explain(nodes, cid, lang=lang, no_llm=no_llm,
                                use_cache=False, timeout=timeout)
        elapsed = res.get("elapsed") or (time.time() - t0)

        grounded = explainer.grounded_in(res["text"], ctx)
        row = {
            "concept": cid,
            "lang": lang,
            "source": res["source"],
            "retrieved": res["retrieved"],
            "n_retrieved": len(res["retrieved"]),
            "grounded": grounded,
            "has_arabic": explainer.has_arabic(res["text"]),
            "keeps_code_english": explainer.preserves_code_identifiers(res["text"]),
            "leaked_reasoning": "<think>" in res["text"] or "</think>" in res["text"],
            "chars": len(res["text"]),
            "elapsed": round(elapsed, 2),
        }
        rows.append(row)
        if verbose:
            mark = "OK  " if grounded else "MISS"
            print(f"  [{i:>2}/{len(concepts)}] {mark} {cid:<22} "
                  f"{row['source']:<9} {row['elapsed']:>6.1f}s  "
                  f"grounded={grounded}"
                  + (f" ar={row['has_arabic']} code_en={row['keeps_code_english']}"
                     if lang == "ar" else ""))
    return rows


def summarise(rows, lang):
    scored = [r for r in rows if r["n_retrieved"] > 0]
    grounded = [r for r in scored if r["grounded"]]
    times = [r["elapsed"] for r in rows if r["elapsed"] > 0]
    out = {
        "lang": lang,
        "n": len(rows),
        "n_scored_for_grounding": len(scored),
        "grounding_rate": round(len(grounded) / len(scored), 3) if scored else None,
        "leaked_reasoning_count": sum(1 for r in rows if r["leaked_reasoning"]),
        "sources": {},
    }
    for r in rows:
        out["sources"][r["source"]] = out["sources"].get(r["source"], 0) + 1
    if times:
        out["latency_s"] = {
            "mean": round(statistics.mean(times), 2),
            "median": round(statistics.median(times), 2),
            "min": round(min(times), 2),
            "max": round(max(times), 2),
        }
    if lang == "ar":
        ar_rows = [r for r in rows if r["has_arabic"]]
        out["arabic_output_rate"] = round(len(ar_rows) / len(rows), 3) if rows else None
        keep = [r for r in ar_rows if r["keeps_code_english"]]
        out["code_identifier_preservation"] = (
            round(len(keep) / len(ar_rows), 3) if ar_rows else None
        )
    return out


def print_summary(s):
    print()
    print(f"  language ............................ {s['lang']}")
    print(f"  explanations generated .............. {s['n']}")
    print(f"  sources ............................. {s['sources']}")
    print(f"  scored for grounding ................ {s['n_scored_for_grounding']}")
    print(f"  PREREQUISITE GROUNDING RATE ......... {s['grounding_rate']}")
    if "arabic_output_rate" in s:
        print(f"  arabic output rate .................. {s['arabic_output_rate']}")
        print(f"  CODE-IDENTIFIER PRESERVATION ........ {s['code_identifier_preservation']}")
    if "latency_s" in s:
        l = s["latency_s"]
        print(f"  latency seconds ..................... mean {l['mean']}  "
              f"median {l['median']}  min {l['min']}  max {l['max']}")
    print(f"  reasoning leaked into output ........ {s['leaked_reasoning_count']}")


def main(argv=None):
    p = argparse.ArgumentParser(description="Adaptive CS Tutor evaluation harness")
    p.add_argument("--n", type=int, default=len(DEFAULT_SAMPLE),
                   help="how many concepts to sample")
    p.add_argument("--lang", choices=["en", "ar", "both"], default="both")
    p.add_argument("--timeout", type=int, default=180)
    p.add_argument("--json", dest="json_out", help="write full results to this path")
    p.add_argument("--skip-control", action="store_true",
                   help="skip the no-LLM control run")
    args = p.parse_args(argv)

    nodes = ge.load_graph()
    concepts = DEFAULT_SAMPLE[:args.n]
    langs = ["en", "ar"] if args.lang == "both" else [args.lang]

    if not explainer.ollama_available():
        print(f"Ollama not reachable at {explainer.OLLAMA_HOST} with model "
              f"'{explainer.OLLAMA_MODEL}'.", file=sys.stderr)
        print("Start it, or run `python3 cli.py demo --no-llm` for the offline path.",
              file=sys.stderr)
        return 1

    print("=" * 74)
    print(f"  ADAPTIVE CS TUTOR — EVALUATION")
    print(f"  model {explainer.OLLAMA_MODEL} via {explainer.OLLAMA_HOST}  "
          f"· {len(concepts)} concepts · cache disabled")
    print("=" * 74)

    report = {
        "model": explainer.OLLAMA_MODEL,
        "host": explainer.OLLAMA_HOST,
        "concepts": concepts,
        "runs": [],
    }

    for lang in langs:
        print()
        print(f"--- LLM run · {lang} " + "-" * (74 - 14 - len(lang)))
        rows = evaluate(nodes, concepts, lang, no_llm=False, timeout=args.timeout)
        s = summarise(rows, lang)
        print_summary(s)
        report["runs"].append({"kind": "llm", "summary": s, "rows": rows})

    if not args.skip_control:
        print()
        print("--- CONTROL · canned fallback, no LLM " + "-" * 36)
        print("  (shows the grounding metric is discriminating, not always-true)")
        rows = evaluate(nodes, concepts, "en", no_llm=True, verbose=False)
        s = summarise(rows, "en")
        print_summary(s)
        report["runs"].append({"kind": "control_no_llm", "summary": s, "rows": rows})

    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print()
        print(f"  full results written to {args.json_out}")

    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
