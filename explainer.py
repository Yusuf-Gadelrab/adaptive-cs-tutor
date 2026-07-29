"""
RAG explainer: builds context from a concept node + its prerequisite chain,
then either (a) asks local qwen3-fast via the Ollama HTTP API for an
explanation, or (b) falls back to a canned bilingual explanation.

IMPORTANT: never shell out to `ollama run` and capture stdout — always use
the HTTP API at localhost:11434. This module never invokes ollama as a
subprocess.
"""
import json
import os
import urllib.request
import urllib.error

import graph_engine as ge

OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "qwen3-fast"
EXPLANATIONS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "explanations.json")

_explanations_cache = None


def load_explanations():
    global _explanations_cache
    if _explanations_cache is None:
        with open(EXPLANATIONS_PATH, "r", encoding="utf-8") as f:
            _explanations_cache = json.load(f)
    return _explanations_cache


def canned_explanation(concept_id, lang="en"):
    """Demo-safety-net fallback. Never touches the network."""
    explanations = load_explanations()
    entry = explanations.get(concept_id)
    if not entry:
        return "No explanation available for this concept yet." if lang == "en" \
            else "لا يوجد شرح متاح لهذا المفهوم بعد."
    return entry.get(lang, entry.get("en", ""))


def build_context(nodes, concept_id):
    """Retrieval step: concept node + its full prerequisite chain, ordered
    root-first so the LLM sees foundational concepts before the target."""
    chain_ids = ge.prereq_chain(nodes, concept_id)
    node = nodes[concept_id]
    lines = []
    for cid in chain_ids:
        lines.append(f"- {nodes[cid]['name']} ({cid})")
    context = {
        "target": node["name"],
        "target_id": concept_id,
        "prereq_chain": chain_ids,
        "prereq_summary": "\n".join(lines) if lines else "(no prerequisites — this is a foundational concept)",
    }
    return context


def build_prompt(context, lang="en"):
    lang_instruction = (
        "Respond in clear, simple English."
        if lang == "en"
        else "أجب باللغة العربية الفصحى المبسطة. أبقِ أسماء المتغيرات وأسماء الدوال ومصطلحات الكود بالإنجليزية كما هي (مثل variables, for, def)."
    )
    prompt = f"""You are a patient CS tutor. The student is learning "{context['target']}".
They already know these prerequisite concepts (build your explanation on top of them, don't re-teach them from scratch):
{context['prereq_summary']}

Explain "{context['target']}" in 3-4 short sentences, referencing at least one prerequisite concept they already know to connect it. Include one tiny code-style example if relevant. {lang_instruction}
Keep code identifiers, keywords, and syntax in English regardless of the response language.
"""
    return prompt


def explain(nodes, concept_id, lang="en", no_llm=False, timeout=12):
    """
    Returns (text, source) where source is "llm" or "fallback".
    Always falls back to canned explanation on any Ollama error/timeout —
    this function must never raise due to Ollama being unavailable.
    """
    if no_llm:
        return canned_explanation(concept_id, lang), "fallback"

    context = build_context(nodes, concept_id)
    prompt = build_prompt(context, lang)
    payload = json.dumps({
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
    }).encode("utf-8")

    req = urllib.request.Request(
        OLLAMA_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            text = body.get("response", "").strip()
            if text:
                return text, "llm"
            return canned_explanation(concept_id, lang), "fallback"
    except (urllib.error.URLError, TimeoutError, ConnectionError, OSError, ValueError, json.JSONDecodeError):
        return canned_explanation(concept_id, lang), "fallback"
