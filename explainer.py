"""
Graph-augmented RAG explainer.

Retrieval is driven by the concept graph rather than by embedding similarity:
to explain concept C we walk C's prerequisite chain, take the nearest K
ancestors, and inject *their actual explanation passages* as context. The
model is therefore forced to build the new idea on top of material the student
has already been taught -- the "Adaptive Curriculum Maps" idea from
SIGCSE TS 2026, implemented literally.

Bilingual mode (SIGCSE TS 2026, "Exploring Bilingual Coding for Inclusive CS
Learning"): prose switches to Arabic, code identifiers and keywords stay in
English, because that is what the paper found actually helps learners.

OLLAMA NOTES (hard-won, do not regress):
  * Never shell out to `ollama run` and capture stdout. Always the HTTP API
    at localhost:11434. This module only ever speaks HTTP.
  * The local `qwen3-fast` Modelfile template opens a `<think>` block
    unconditionally. Consequences we measured, in order of discovery:
      1. `"think": false` is ignored -- reasoning arrives in the content
         field, terminated by a stray `</think>`.
      2. Qwen3's `/no_think` soft switch is ignored for the same reason.
      3. Worse: when reasoning ran past `num_predict`, the closing tag never
         arrived, so there was nothing to strip and raw chain-of-thought was
         served to the student as if it were the lesson.
    The fix is render_chatml() -- we build the ChatML prompt ourselves and
    send it with `raw: true`, pre-closing the block with an empty
    `<think></think>` pair so generation starts on the answer. strip_thinking()
    stays as defence in depth for any other model.
"""
import json
import os
import re
import time
import urllib.error
import urllib.request

import graph_engine as ge

HERE = os.path.dirname(os.path.abspath(__file__))
EXPLANATIONS_PATH = os.path.join(HERE, "explanations.json")
CACHE_DIR = os.path.join(HERE, ".cache")

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_URL = OLLAMA_HOST.rstrip("/") + "/api/generate"
OLLAMA_TAGS_URL = OLLAMA_HOST.rstrip("/") + "/api/tags"
OLLAMA_MODEL = os.environ.get("TUTOR_MODEL", "qwen3-fast")

# How many of the nearest prerequisite concepts to retrieve as context.
RETRIEVAL_K = 4
DEFAULT_TIMEOUT = 120

_explanations_cache = None

# Code tokens that must survive translation to Arabic (bilingual invariant).
CODE_TOKENS = [
    "def", "return", "for", "while", "if", "else", "elif", "in", "range",
    "print", "len", "class", "self", "import", "try", "except", "True",
    "False", "None", "and", "or", "not", "append", "list", "dict",
]


def load_explanations():
    global _explanations_cache
    if _explanations_cache is None:
        with open(EXPLANATIONS_PATH, "r", encoding="utf-8") as f:
            _explanations_cache = json.load(f)
    return _explanations_cache


def canned_explanation(concept_id, lang="en"):
    """Offline fallback. Never touches the network."""
    entry = load_explanations().get(concept_id)
    if not entry:
        return ("No explanation available for this concept yet." if lang == "en"
                else "لا يوجد شرح متاح لهذا المفهوم بعد.")
    return entry.get(lang, entry.get("en", ""))


def strip_thinking(text):
    """
    Remove chain-of-thought that local reasoning models leak into content.

    Handles three shapes seen in the wild:
      1. "<think> ... </think> answer"   (well-formed)
      2. "reasoning ... </think> answer" (opening tag consumed by the chat
                                          template -- what qwen3-fast does)
      3. "<think> ... "                  (truncated, no closing tag)
    """
    if not text:
        return ""
    # Shape 1 + 2: everything up to and including the LAST closing tag is
    # reasoning. Using the last one is safe because a real answer would not
    # contain a bare closing think tag.
    if "</think>" in text:
        text = text.rsplit("</think>", 1)[1]
    # Shape 3: unterminated reasoning block -- nothing usable follows.
    text = re.sub(r"<think>.*", "", text, flags=re.DOTALL)
    return text.strip()


def retrieve(nodes, concept_id, lang="en", k=RETRIEVAL_K):
    """
    Graph-augmented retrieval: return the K prerequisite concepts nearest to
    the target (deepest ancestors first, i.e. the ones most recently taught),
    each with its explanation passage.
    """
    chain = ge.prereq_chain(nodes, concept_id)  # root-first order
    nearest = chain[-k:] if k else chain
    passages = []
    for cid in nearest:
        passages.append({
            "id": cid,
            "name": nodes[cid]["name"],
            "text": canned_explanation(cid, lang),
        })
    return {
        "target_id": concept_id,
        "target": nodes[concept_id]["name"],
        "full_chain": chain,
        "retrieved": passages,
    }


def build_messages(context, lang="en"):
    """Turn retrieved context into an Ollama /api/chat message list."""
    if context["retrieved"]:
        known = "\n\n".join(
            f"[{p['id']}] {p['name']}: {p['text']}" for p in context["retrieved"]
        )
        known_names = ", ".join(p["name"] for p in context["retrieved"])
        grounding = (
            f"The student has ALREADY been taught these prerequisite concepts. "
            f"Use them as the foundation and explicitly connect to at least one "
            f"of them by name:\n\n{known}"
        )
        connect = f"You must reference at least one of these by name: {known_names}."
    else:
        grounding = ("This is a foundational concept with no prerequisites. "
                     "Assume the student is a complete beginner.")
        connect = "Assume no prior programming knowledge."

    if lang == "ar":
        lang_rule = (
            "اكتب الشرح بالعربية الفصحى المبسطة. "
            "أبقِ جميع الكلمات المفتاحية وأسماء الدوال والمتغيرات ورموز الكود "
            "بالإنجليزية كما هي (مثل def، return، for، if)."
        )
    else:
        lang_rule = "Write the explanation in clear, simple English."

    system = (
        "You are a patient introductory computer science tutor. "
        "Reply with the explanation only. No preamble, no meta-commentary, "
        "no restating the instructions."
    )
    user = (
        f"Teach the concept: {context['target']}.\n\n"
        f"{grounding}\n\n"
        f"Rules:\n"
        f"- 3 to 4 short sentences.\n"
        f"- {connect}\n"
        f"- Include one tiny Python example in a ```python code block.\n"
        f"- Keep all code identifiers, keywords and syntax in English.\n"
        f"- {lang_rule}"
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def ollama_available(timeout=2):
    """Cheap liveness probe against /api/tags."""
    try:
        with urllib.request.urlopen(OLLAMA_TAGS_URL, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return any(m.get("name", "").split(":")[0] == OLLAMA_MODEL.split(":")[0]
                   for m in data.get("models", []))
    except Exception:
        return False


def _cache_path(concept_id, lang):
    return os.path.join(CACHE_DIR, f"{concept_id}.{lang}.json")


def _cache_read(concept_id, lang):
    try:
        with open(_cache_path(concept_id, lang), "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _cache_write(concept_id, lang, payload):
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
        with open(_cache_path(concept_id, lang), "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
    except OSError:
        pass


def render_chatml(messages):
    """
    Render messages into Qwen3's ChatML prompt, then PRE-CLOSE the reasoning
    block with an empty `<think></think>` pair.

    This is the only reliable way to stop qwen3-fast reasoning. Its Modelfile
    template opens `<think>` unconditionally, so:
      * `"think": false` is ignored, and
      * the `/no_think` soft switch is also ignored,
    which left reasoning in the content field -- and worse, when the reasoning
    ran past num_predict the closing tag never arrived, so there was nothing
    to strip and raw chain-of-thought reached the student.

    Supplying the prompt ourselves with raw=true lets us close the block
    before the model writes a single token. Generation then starts directly on
    the answer.
    """
    parts = []
    for m in messages:
        parts.append(f"<|im_start|>{m['role']}\n{m['content']}<|im_end|>\n")
    parts.append("<|im_start|>assistant\n<think>\n\n</think>\n\n")
    return "".join(parts)


def call_ollama(messages, timeout=DEFAULT_TIMEOUT, num_predict=400):
    """
    POST to /api/generate in raw mode. Returns (raw_text, elapsed_seconds).
    Raises on any transport failure -- callers decide about fallback.
    """
    payload = json.dumps({
        "model": OLLAMA_MODEL,
        "prompt": render_chatml(messages),
        "raw": True,
        "stream": False,
        # Correct for well-behaved reasoning models; harmless here.
        "think": False,
        "keep_alive": "10m",
        "options": {
            "temperature": 0.2,
            "top_p": 0.9,
            "num_predict": num_predict,
            "stop": ["<|im_end|>", "<|im_start|>"],
        },
    }).encode("utf-8")

    req = urllib.request.Request(
        OLLAMA_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    elapsed = time.time() - t0
    return body.get("response", ""), elapsed


def explain(nodes, concept_id, lang="en", no_llm=False, timeout=DEFAULT_TIMEOUT,
            use_cache=True, refresh=False):
    """
    Return a dict:
      {concept, lang, text, source, retrieved:[ids], chain_len, elapsed}

    source is one of:
      "llm"      generated just now by the local model
      "cache"    generated earlier by the local model, replayed from disk
      "fallback" canned bilingual passage (offline / model unavailable / error)

    This function never raises because of Ollama. Falling back is always
    allowed -- that is what makes the demo safe on a flaky network.
    """
    context = retrieve(nodes, concept_id, lang=lang)
    base = {
        "concept": concept_id,
        "lang": lang,
        "retrieved": [p["id"] for p in context["retrieved"]],
        "chain_len": len(context["full_chain"]),
    }

    if no_llm:
        return {**base, "text": canned_explanation(concept_id, lang),
                "source": "fallback", "elapsed": 0.0}

    if use_cache and not refresh:
        hit = _cache_read(concept_id, lang)
        if hit and hit.get("text"):
            return {**base, "text": hit["text"], "source": "cache",
                    "elapsed": 0.0}

    try:
        raw, elapsed = call_ollama(build_messages(context, lang), timeout=timeout)
        text = strip_thinking(raw)
        if text:
            if use_cache:
                _cache_write(concept_id, lang,
                             {"text": text, "model": OLLAMA_MODEL,
                              "retrieved": base["retrieved"]})
            return {**base, "text": text, "source": "llm", "elapsed": elapsed}
    except (urllib.error.URLError, TimeoutError, ConnectionError, OSError,
            ValueError, json.JSONDecodeError):
        pass

    return {**base, "text": canned_explanation(concept_id, lang),
            "source": "fallback", "elapsed": 0.0}


def grounded_in(text, context_or_nodes, concept_id=None, lang="en"):
    """
    Did the explanation actually build on a retrieved prerequisite?

    True when the text mentions the name (or id) of at least one retrieved
    prerequisite concept. Foundational concepts (no prereqs) count as grounded
    by definition -- there is nothing to build on.
    """
    if concept_id is not None:
        context = retrieve(context_or_nodes, concept_id, lang=lang)
    else:
        context = context_or_nodes
    if not context["retrieved"]:
        return True
    low = text.lower()
    for p in context["retrieved"]:
        if p["name"].lower() in low:
            return True
        if p["id"].replace("_", " ") in low or p["id"] in low:
            return True
        # match the head word of multi-word names, e.g. "Loops" from "For Loops"
        for word in re.findall(r"[a-z]{4,}", p["name"].lower()):
            if word in low:
                return True
    return False


def preserves_code_identifiers(text):
    """
    Bilingual invariant from the SIGCSE bilingual-coding paper: prose may be
    Arabic, but code must stay English. True when the text still contains a
    recognisable English code token or an ASCII-only code fence.
    """
    if not text:
        return False
    fences = re.findall(r"```[a-z]*\n(.*?)```", text, flags=re.DOTALL)
    for block in fences:
        if re.search(r"[A-Za-z_][A-Za-z0-9_]*\s*[=(:]", block):
            return True
    for tok in CODE_TOKENS:
        if re.search(rf"(?<![A-Za-z0-9_]){re.escape(tok)}(?![A-Za-z0-9_])", text):
            return True
    return False


def has_arabic(text):
    return bool(re.search(r"[؀-ۿ]", text or ""))
