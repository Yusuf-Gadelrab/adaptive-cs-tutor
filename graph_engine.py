"""
Concept-graph engine: loads graph.json and computes node states from quiz results.

Pure stdlib, no external deps, no Ollama dependency. This is the part that
must be provably correct on its own (see test_graph_engine.py).

States:
  "ok"       - no evidence of a problem
  "shaky"    - student answered a question mapped to this concept incorrectly
  "at_risk"  - not shaky itself, but depends (directly or transitively) on a
               shaky concept, so mastery here is questionable
"""
import json
import os

GRAPH_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "graph.json")


def load_graph(path=GRAPH_PATH):
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    nodes = {n["id"]: n for n in data["nodes"]}
    return nodes


def build_dependents(nodes):
    """Map concept_id -> list of concept_ids that list it as a prereq
    (i.e. the concepts that DEPEND ON it and would be at risk if it's shaky)."""
    dependents = {nid: [] for nid in nodes}
    for nid, node in nodes.items():
        for prereq in node.get("prereqs", []):
            if prereq not in dependents:
                raise ValueError(f"Unknown prereq '{prereq}' referenced by '{nid}'")
            dependents[prereq].append(nid)
    return dependents


def topo_levels(nodes):
    """Return dict concept_id -> depth (longest path from a root), used for
    layout. Assumes graph.json is acyclic; raises on cycles."""
    memo = {}

    def depth(nid, stack=None):
        if nid in memo:
            return memo[nid]
        stack = stack or set()
        if nid in stack:
            raise ValueError(f"Cycle detected in prerequisite graph at '{nid}'")
        stack = stack | {nid}
        prereqs = nodes[nid].get("prereqs", [])
        d = 0 if not prereqs else 1 + max(depth(p, stack) for p in prereqs)
        memo[nid] = d
        return d

    for nid in nodes:
        depth(nid)
    return memo


def compute_states(nodes, dependents, shaky_ids):
    """
    shaky_ids: set/list of concept ids the student got wrong.
    Returns dict concept_id -> "ok" | "shaky" | "at_risk".

    Propagation: BFS forward through the dependents graph starting from every
    shaky node. Anything reached that isn't itself shaky becomes "at_risk".
    """
    shaky_ids = set(shaky_ids)
    for sid in shaky_ids:
        if sid not in nodes:
            raise ValueError(f"Unknown concept id in shaky set: '{sid}'")

    states = {nid: "ok" for nid in nodes}
    for sid in shaky_ids:
        states[sid] = "shaky"

    at_risk = set()
    visited = set()
    frontier = list(shaky_ids)
    while frontier:
        cur = frontier.pop()
        if cur in visited:
            continue
        visited.add(cur)
        for dep in dependents.get(cur, []):
            if dep not in shaky_ids:
                at_risk.add(dep)
            if dep not in visited:
                frontier.append(dep)

    for nid in at_risk:
        states[nid] = "at_risk"

    return states


def prereq_chain(nodes, concept_id):
    """Full ancestor chain (all transitive prereqs) for a concept, ordered
    root-first, deduplicated. Used as RAG retrieval context."""
    if concept_id not in nodes:
        raise ValueError(f"Unknown concept id: '{concept_id}'")

    order = []
    seen = set()

    def visit(nid):
        for p in nodes[nid].get("prereqs", []):
            if p not in seen:
                visit(p)
                seen.add(p)
                order.append(p)

    visit(concept_id)
    return order


def score_quiz(quiz_questions, answers):
    """
    quiz_questions: list of question dicts (from quiz.json) each with
      id, concept, choices, answer (index of correct choice).
    answers: dict question_id -> chosen index.
    Returns (shaky_concept_ids, per_question_results).
    """
    shaky = set()
    results = []
    for q in quiz_questions:
        chosen = answers.get(q["id"])
        correct = chosen == q["answer"]
        if not correct:
            shaky.add(q["concept"])
        results.append({
            "id": q["id"],
            "concept": q["concept"],
            "correct": correct,
            "chosen": chosen,
        })
    return shaky, results
