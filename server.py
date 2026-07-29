#!/usr/bin/env python3
"""
Adaptive CS Tutor — single-page stdlib HTTP server.

Zero external deps (stdlib only). Ollama is optional: pass --no-llm to force
the canned-explanation fallback (also what happens automatically if Ollama
isn't reachable at localhost:11434).

Run:
    python3 server.py            # tries Ollama, falls back automatically
    python3 server.py --no-llm   # force fallback-only (demo-safe)
    python3 server.py --port 8123
"""
import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

import graph_engine as ge
import explainer

NODES = ge.load_graph()
DEPENDENTS = ge.build_dependents(NODES)
LEVELS = ge.topo_levels(NODES)

with open("quiz.json", "r", encoding="utf-8") as f:
    QUIZ = json.load(f)["questions"]

FORCE_NO_LLM = False


def layout_nodes():
    """Simple deterministic layout: x by topo depth, y by order within depth."""
    by_level = {}
    for nid, lvl in LEVELS.items():
        by_level.setdefault(lvl, []).append(nid)
    for lvl in by_level:
        by_level[lvl].sort(key=lambda nid: (NODES[nid]["cluster"], nid))

    positions = {}
    x_gap, y_gap, x0, y0 = 170, 85, 90, 60
    for lvl, ids in by_level.items():
        for i, nid in enumerate(ids):
            positions[nid] = {"x": x0 + lvl * x_gap, "y": y0 + i * y_gap}
    return positions


POSITIONS = layout_nodes()


def graph_payload():
    edges = []
    for nid, node in NODES.items():
        for prereq in node["prereqs"]:
            edges.append({"from": prereq, "to": nid})
    nodes_out = []
    for nid, node in NODES.items():
        p = POSITIONS[nid]
        nodes_out.append({
            "id": nid, "name": node["name"], "cluster": node["cluster"],
            "x": p["x"], "y": p["y"],
        })
    width = max(p["x"] for p in POSITIONS.values()) + 160
    height = max(p["y"] for p in POSITIONS.values()) + 60
    return {"nodes": nodes_out, "edges": edges, "width": width, "height": height}


def quiz_payload():
    # never leak the answer index to the client before scoring
    return [{"id": q["id"], "concept": q["concept"], "prompt": q["prompt"], "choices": q["choices"]}
            for q in QUIZ]


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass  # keep demo terminal output clean

    def _send_json(self, obj, status=200):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, html, status=200):
        body = html.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)

        if path == "/":
            self._send_html(INDEX_HTML)
        elif path == "/api/graph":
            self._send_json(graph_payload())
        elif path == "/api/quiz":
            self._send_json(quiz_payload())
        elif path == "/api/explain":
            concept = (qs.get("concept") or [""])[0]
            lang = (qs.get("lang") or ["en"])[0]
            no_llm = FORCE_NO_LLM or (qs.get("no_llm") or ["0"])[0] == "1"
            if concept not in NODES:
                self._send_json({"error": "unknown concept"}, status=404)
                return
            text, source = explainer.explain(NODES, concept, lang=lang, no_llm=no_llm)
            self._send_json({"concept": concept, "lang": lang, "text": text, "source": source})
        elif path == "/api/health":
            self._send_json({"ok": True, "nodes": len(NODES), "no_llm_forced": FORCE_NO_LLM})
        else:
            self._send_json({"error": "not found"}, status=404)

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path != "/api/submit":
            self._send_json({"error": "not found"}, status=404)
            return
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            self._send_json({"error": "bad json"}, status=400)
            return
        answers = body.get("answers", {})
        shaky, results = ge.score_quiz(QUIZ, answers)
        states = ge.compute_states(NODES, DEPENDENTS, shaky)
        self._send_json({
            "shaky": sorted(shaky),
            "results": results,
            "states": states,
        })


INDEX_HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Adaptive CS Tutor</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  :root { color-scheme: dark; }
  * { box-sizing: border-box; }
  body {
    margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    background: #0f1117; color: #e6e6e6;
  }
  header {
    padding: 16px 24px; border-bottom: 1px solid #262a36;
    display: flex; justify-content: space-between; align-items: center;
  }
  header h1 { font-size: 18px; margin: 0; }
  header .sub { color: #9aa0ac; font-size: 12.5px; margin-top: 2px; }
  #langToggle {
    background: #1b1f2a; border: 1px solid #333a4a; color: #e6e6e6;
    padding: 8px 14px; border-radius: 8px; cursor: pointer; font-size: 13px;
  }
  #langToggle:hover { background: #232838; }
  main { display: grid; grid-template-columns: 1.4fr 1fr; gap: 18px; padding: 18px 24px; }
  .panel { background: #161a24; border: 1px solid #262a36; border-radius: 12px; padding: 16px; }
  .panel h2 { font-size: 14px; text-transform: uppercase; letter-spacing: .04em; color: #9aa0ac; margin: 0 0 12px; }
  #graphWrap { overflow: auto; max-height: 640px; }
  svg { display: block; }
  .node-circle { stroke: #0f1117; stroke-width: 2; cursor: pointer; }
  .node-label { font-size: 10px; fill: #cfd3dc; pointer-events: none; }
  .edge { stroke: #3a4152; stroke-width: 1.4; }
  .state-ok { fill: #2f9e44; }
  .state-shaky { fill: #f08c00; }
  .state-at_risk { fill: #e03131; }
  #quizPanel .q { margin-bottom: 14px; padding-bottom: 14px; border-bottom: 1px solid #232838; }
  #quizPanel .q:last-child { border-bottom: none; }
  .q-prompt { font-size: 13.5px; margin-bottom: 8px; }
  .choice { display: block; width: 100%; text-align: left; background: #1b1f2a; border: 1px solid #2c3242;
    color: #e6e6e6; padding: 8px 10px; margin-bottom: 6px; border-radius: 7px; cursor: pointer; font-size: 12.5px; }
  .choice:hover { background: #232a3c; }
  .choice.selected { border-color: #5c7cfa; background: #232a44; }
  #submitBtn, #explainHint {
    background: #5c7cfa; color: white; border: none; padding: 10px 16px;
    border-radius: 8px; cursor: pointer; font-size: 13.5px; margin-top: 8px;
  }
  #submitBtn:hover { background: #4c6ef5; }
  #explainBox { font-size: 13.5px; line-height: 1.55; white-space: pre-wrap; }
  .badge { display: inline-block; font-size: 11px; padding: 2px 8px; border-radius: 999px; margin-left: 6px; }
  .badge-llm { background: #1b3d2e; color: #63e6be; }
  .badge-fallback { background: #2b2410; color: #ffd43b; }
  .legend { display: flex; gap: 14px; font-size: 12px; color: #9aa0ac; margin-bottom: 10px; }
  .legend span { display: inline-flex; align-items: center; gap: 5px; }
  .dot { width: 10px; height: 10px; border-radius: 50%; display: inline-block; }
  [dir="rtl"] .choice { text-align: right; }
</style>
</head>
<body>
<header>
  <div>
    <h1 id="title">Adaptive CS Tutor</h1>
    <div class="sub" id="subtitle">Concept-graph diagnostic, built from published SIGCSE TS 2026 research</div>
  </div>
  <button id="langToggle" onclick="toggleLang()">العربية</button>
</header>
<main>
  <div class="panel">
    <h2 id="graphHeading">Concept Graph</h2>
    <div class="legend">
      <span><i class="dot" style="background:#2f9e44"></i><span id="legendOk">Mastered</span></span>
      <span><i class="dot" style="background:#f08c00"></i><span id="legendShaky">Shaky</span></span>
      <span><i class="dot" style="background:#e03131"></i><span id="legendRisk">At risk</span></span>
    </div>
    <div id="graphWrap"></div>
  </div>
  <div>
    <div class="panel" id="quizPanelWrap">
      <h2 id="quizHeading">Diagnostic Quiz</h2>
      <div id="quizPanel"></div>
      <button id="submitBtn" onclick="submitQuiz()">Submit Quiz</button>
    </div>
    <div class="panel" style="margin-top:16px;">
      <h2 id="explainHeading">Explanation</h2>
      <div id="explainMeta" style="margin-bottom:8px;"></div>
      <div id="explainBox">Click any node in the graph to get an explanation.</div>
    </div>
  </div>
</main>
<script>
let lang = "en";
let graphData = null;
let quizData = null;
let states = {};
let answers = {};

const STR = {
  en: { title: "Adaptive CS Tutor", subtitle: "Concept-graph diagnostic, built from published SIGCSE TS 2026 research",
        graphHeading: "Concept Graph", legendOk: "Mastered", legendShaky: "Shaky", legendRisk: "At risk",
        quizHeading: "Diagnostic Quiz", submitBtn: "Submit Quiz", explainHeading: "Explanation",
        clickHint: "Click any node in the graph to get an explanation.", toggleLabel: "العربية" },
  ar: { title: "المدرّس التكيّفي لعلوم الحاسب", subtitle: "تشخيص قائم على خريطة المفاهيم، مبني على أبحاث SIGCSE TS 2026 المنشورة",
        graphHeading: "خريطة المفاهيم", legendOk: "متقن", legendShaky: "غير مستقر", legendRisk: "معرّض للخطر",
        quizHeading: "اختبار تشخيصي", submitBtn: "إرسال الاختبار", explainHeading: "الشرح",
        clickHint: "اضغط على أي عقدة في الخريطة للحصول على شرح.", toggleLabel: "English" }
};

function applyLangStrings() {
  const s = STR[lang];
  document.getElementById('title').textContent = s.title;
  document.getElementById('subtitle').textContent = s.subtitle;
  document.getElementById('graphHeading').textContent = s.graphHeading;
  document.getElementById('legendOk').textContent = s.legendOk;
  document.getElementById('legendShaky').textContent = s.legendShaky;
  document.getElementById('legendRisk').textContent = s.legendRisk;
  document.getElementById('quizHeading').textContent = s.quizHeading;
  document.getElementById('submitBtn').textContent = s.submitBtn;
  document.getElementById('explainHeading').textContent = s.explainHeading;
  document.getElementById('langToggle').textContent = s.toggleLabel;
  document.body.dir = (lang === 'ar') ? 'rtl' : 'ltr';
}

function toggleLang() {
  lang = (lang === 'en') ? 'ar' : 'en';
  applyLangStrings();
}

async function loadAll() {
  const [g, q] = await Promise.all([
    fetch('/api/graph').then(r => r.json()),
    fetch('/api/quiz').then(r => r.json())
  ]);
  graphData = g;
  quizData = q;
  graphData.nodes.forEach(n => states[n.id] = 'ok');
  renderGraph();
  renderQuiz();
  applyLangStrings();
}

function renderGraph() {
  const wrap = document.getElementById('graphWrap');
  const w = graphData.width, h = graphData.height;
  let svg = `<svg width="${w}" height="${h}" viewBox="0 0 ${w} ${h}">`;
  const pos = {};
  graphData.nodes.forEach(n => pos[n.id] = n);
  graphData.edges.forEach(e => {
    const a = pos[e.from], b = pos[e.to];
    svg += `<line class="edge" x1="${a.x}" y1="${a.y}" x2="${b.x}" y2="${b.y}" />`;
  });
  graphData.nodes.forEach(n => {
    const st = states[n.id] || 'ok';
    svg += `<circle class="node-circle state-${st}" cx="${n.x}" cy="${n.y}" r="9" onclick="explainNode('${n.id}')" />`;
    svg += `<text class="node-label" x="${n.x + 12}" y="${n.y + 4}">${n.name}</text>`;
  });
  svg += `</svg>`;
  wrap.innerHTML = svg;
}

function renderQuiz() {
  const panel = document.getElementById('quizPanel');
  panel.innerHTML = quizData.map(q => `
    <div class="q" data-qid="${q.id}">
      <div class="q-prompt">${q.prompt}</div>
      ${q.choices.map((c, i) => `<button class="choice" onclick="selectChoice('${q.id}', ${i}, this)">${c}</button>`).join('')}
    </div>
  `).join('');
}

function selectChoice(qid, idx, el) {
  answers[qid] = idx;
  el.parentElement.querySelectorAll('.choice').forEach(b => b.classList.remove('selected'));
  el.classList.add('selected');
}

async function submitQuiz() {
  const res = await fetch('/api/submit', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({answers})
  });
  const data = await res.json();
  states = data.states;
  renderGraph();
}

async function explainNode(id) {
  const box = document.getElementById('explainBox');
  const meta = document.getElementById('explainMeta');
  box.textContent = (lang === 'ar') ? 'جارٍ التحميل...' : 'Loading...';
  meta.innerHTML = '';
  const res = await fetch(`/api/explain?concept=${id}&lang=${lang}`);
  const data = await res.json();
  box.textContent = data.text;
  const badgeClass = data.source === 'llm' ? 'badge-llm' : 'badge-fallback';
  const badgeText = data.source === 'llm' ? 'qwen3-fast (local)' : (lang === 'ar' ? 'شرح جاهز (بدون نموذج)' : 'canned (no-LLM)');
  meta.innerHTML = `<strong>${id}</strong><span class="badge ${badgeClass}">${badgeText}</span>`;
}

loadAll();
</script>
</body>
</html>
"""


def main():
    global FORCE_NO_LLM
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8123)
    parser.add_argument("--no-llm", action="store_true", help="Force canned explanations, never call Ollama")
    args = parser.parse_args()
    FORCE_NO_LLM = args.no_llm

    server = ThreadingHTTPServer(("0.0.0.0", args.port), Handler)
    mode = "NO-LLM (fallback only)" if FORCE_NO_LLM else "LLM-with-fallback"
    print(f"Adaptive CS Tutor running on http://localhost:{args.port}  [{mode}]")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
