#!/usr/bin/env python3
"""
Adaptive CS Tutor — single-page stdlib HTTP server.

Zero external dependencies. Ollama is optional: pass --no-llm to force the
canned bilingual fallback (also what happens automatically if the model is
unreachable), which is what makes the demo safe with the Wi-Fi off.

Run:
    python3 server.py               # tries Ollama, falls back automatically
    python3 server.py --no-llm      # force fallback only
    python3 server.py --port 8123
"""
import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import explainer
import graph_engine as ge

NODES = ge.load_graph()
DEPENDENTS = ge.build_dependents(NODES)
LEVELS = ge.topo_levels(NODES)
QUIZ = ge.load_quiz()

FORCE_NO_LLM = False


def layout_nodes():
    """Deterministic layout: x by topological depth, y by order within depth."""
    by_level = {}
    for nid, lvl in LEVELS.items():
        by_level.setdefault(lvl, []).append(nid)
    for lvl in by_level:
        by_level[lvl].sort(key=lambda nid: (NODES[nid]["cluster"], nid))

    positions = {}
    x_gap, y_gap, x0, y0 = 186, 74, 96, 46
    for lvl, ids in by_level.items():
        for i, nid in enumerate(ids):
            positions[nid] = {"x": x0 + lvl * x_gap, "y": y0 + i * y_gap}
    return positions


POSITIONS = layout_nodes()


def graph_payload():
    edges = [{"from": prereq, "to": nid}
             for nid, node in NODES.items() for prereq in node["prereqs"]]
    nodes_out = [{
        "id": nid, "name": node["name"], "cluster": node["cluster"],
        "x": POSITIONS[nid]["x"], "y": POSITIONS[nid]["y"],
    } for nid, node in NODES.items()]
    return {
        "nodes": nodes_out,
        "edges": edges,
        "width": max(p["x"] for p in POSITIONS.values()) + 190,
        "height": max(p["y"] for p in POSITIONS.values()) + 50,
    }


def quiz_payload():
    """Never leak the answer key to the client before scoring."""
    return [{"id": q["id"], "concept": q["concept"], "prompt": q["prompt"],
             "choices": q["choices"]} for q in QUIZ]


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass  # keep the demo terminal clean

    def _send_json(self, obj, status=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
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
        path, qs = parsed.path, parse_qs(parsed.query)

        if path == "/":
            self._send_html(INDEX_HTML)
        elif path == "/api/graph":
            self._send_json(graph_payload())
        elif path == "/api/quiz":
            self._send_json(quiz_payload())
        elif path == "/api/explain":
            concept = (qs.get("concept") or [""])[0]
            lang = (qs.get("lang") or ["en"])[0]
            if concept not in NODES:
                self._send_json({"error": "unknown concept"}, status=404)
                return
            if lang not in ("en", "ar"):
                lang = "en"
            no_llm = FORCE_NO_LLM or (qs.get("no_llm") or ["0"])[0] == "1"
            result = explainer.explain(NODES, concept, lang=lang, no_llm=no_llm)
            result["retrieved_names"] = [NODES[r]["name"] for r in result["retrieved"]]
            result["grounded"] = explainer.grounded_in(
                result["text"], NODES, concept_id=concept, lang=lang)
            if lang == "ar":
                result["keeps_code_english"] = \
                    explainer.preserves_code_identifiers(result["text"])
            self._send_json(result)
        elif path == "/api/health":
            self._send_json({
                "ok": True,
                "nodes": len(NODES),
                "questions": len(QUIZ),
                "no_llm_forced": FORCE_NO_LLM,
                "model": explainer.OLLAMA_MODEL,
                "ollama_available": False if FORCE_NO_LLM else explainer.ollama_available(),
            })
        else:
            self._send_json({"error": "not found"}, status=404)

    def do_POST(self):
        if urlparse(self.path).path != "/api/submit":
            self._send_json({"error": "not found"}, status=404)
            return
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            self._send_json({"error": "bad json"}, status=400)
            return

        answers = body.get("answers") or {}
        if not isinstance(answers, dict):
            self._send_json({"error": "answers must be an object"}, status=400)
            return

        shaky, results = ge.score_quiz(QUIZ, answers)
        states = ge.compute_states(NODES, DEPENDENTS, shaky)
        path = ge.learning_path(NODES, DEPENDENTS, shaky)
        for row in path:
            row["unlock_names"] = [NODES[u]["name"] for u in row["unlocks"]]
        self._send_json({
            "shaky": sorted(shaky),
            "results": results,
            "states": states,
            "path": path,
            "summary": {
                "answered": len([r for r in results if r["chosen"] is not None]),
                "correct": sum(1 for r in results if r["correct"]),
                "total": len(results),
                "mastered": sum(1 for s in states.values() if s == "ok"),
                "shaky": sum(1 for s in states.values() if s == "shaky"),
                "at_risk": sum(1 for s in states.values() if s == "at_risk"),
            },
        })


INDEX_HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Adaptive CS Tutor</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  :root{
    color-scheme: dark;
    --bg:#0a0a0a; --panel:#111010; --line:#26221a;
    --gold:#d4af37; --gold-dim:#8a7327; --gold-soft:#e8d38a;
    --ink:#ece7dc; --muted:#8d857a;
    --ok:#4f7d52; --shaky:#d4af37; --risk:#a33a34;
    --serif: "Iowan Old Style", "Palatino Linotype", Palatino, Georgia, "Times New Roman", serif;
    --sans: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
    --mono: "SF Mono", ui-monospace, Menlo, Consolas, monospace;
  }
  *{box-sizing:border-box}
  body{margin:0;background:var(--bg);color:var(--ink);font-family:var(--sans);
       font-size:14px;line-height:1.6;-webkit-font-smoothing:antialiased}
  header{padding:26px 34px 22px;border-bottom:1px solid var(--line);
         display:flex;justify-content:space-between;align-items:flex-end;gap:20px;flex-wrap:wrap}
  .brand{display:flex;align-items:baseline;gap:14px}
  h1{font-family:var(--serif);font-size:27px;font-weight:500;margin:0;
     letter-spacing:.015em;color:var(--gold-soft)}
  .house{font-size:10px;letter-spacing:.32em;text-transform:uppercase;color:var(--gold-dim)}
  .sub{color:var(--muted);font-size:12.5px;margin-top:5px;max-width:62ch}
  .sub a{color:var(--gold-dim);text-decoration:none;border-bottom:1px solid var(--line)}
  .sub a:hover{color:var(--gold)}
  button{font-family:inherit}
  #langToggle{background:transparent;border:1px solid var(--gold-dim);color:var(--gold);
    padding:9px 20px;border-radius:2px;cursor:pointer;font-size:12px;
    letter-spacing:.14em;text-transform:uppercase;transition:.18s}
  #langToggle:hover{background:var(--gold);color:#0a0a0a}
  main{display:grid;grid-template-columns:minmax(0,1.5fr) minmax(0,1fr);
       gap:22px;padding:22px 34px 44px;align-items:start}
  main > *{min-width:0}
  @media(max-width:1080px){main{grid-template-columns:minmax(0,1fr)}}
  .panel{background:var(--panel);border:1px solid var(--line);border-radius:3px;padding:20px 22px}
  .panel + .panel{margin-top:20px}
  h2{font-family:var(--serif);font-size:12px;font-weight:400;text-transform:uppercase;
     letter-spacing:.26em;color:var(--gold-dim);margin:0 0 16px;
     padding-bottom:11px;border-bottom:1px solid var(--line)}
  /* The graph is a diagram of English concept names: keep it LTR even when the
     rest of the page mirrors, or SVG labels reverse and overlap their nodes. */
  #graphWrap{overflow:auto;max-height:600px;direction:ltr}
  svg{display:block}
  .node-label{direction:ltr;unicode-bidi:isolate}
  .node-circle{stroke:var(--bg);stroke-width:2.5;cursor:pointer;transition:r .15s}
  .node-circle:hover{stroke:var(--gold);r:9}
  .node-label{font-size:10.5px;fill:#b7afa1;pointer-events:none;font-family:var(--sans)}
  .edge{stroke:#443b2b;stroke-width:1.1;opacity:.85}
  #quizPanel{max-height:520px;overflow-y:auto;padding-right:8px}
  #quizPanel::-webkit-scrollbar{width:7px}
  #quizPanel::-webkit-scrollbar-thumb{background:var(--line);border-radius:4px}
  #graphWrap::-webkit-scrollbar{height:7px;width:7px}
  #graphWrap::-webkit-scrollbar-thumb{background:var(--line);border-radius:4px}
  .state-ok{fill:var(--ok)} .state-shaky{fill:var(--shaky)} .state-at_risk{fill:var(--risk)}
  .legend{display:flex;gap:20px;font-size:11px;color:var(--muted);margin-bottom:14px;
    letter-spacing:.1em;text-transform:uppercase;flex-wrap:wrap}
  .legend span{display:inline-flex;align-items:center;gap:7px}
  .dot{width:8px;height:8px;border-radius:50%;display:inline-block}
  .q{margin-bottom:16px;padding-bottom:16px;border-bottom:1px solid var(--line)}
  .q:last-child{border-bottom:none;margin-bottom:0}
  .q-prompt{font-size:13px;margin-bottom:9px;color:var(--ink)}
  .q-prompt code,.q-prompt tt{font-family:var(--mono);color:var(--gold-soft);font-size:12px}
  .choice{display:block;width:100%;text-align:left;background:transparent;
    border:1px solid var(--line);color:#cdc5b8;padding:8px 12px;margin-bottom:6px;
    border-radius:2px;cursor:pointer;font-size:12.5px;transition:.14s}
  .choice:hover{border-color:var(--gold-dim);color:var(--ink)}
  .choice.selected{border-color:var(--gold);color:var(--gold-soft);background:#161208}
  .gold-btn{background:var(--gold);color:#0a0a0a;border:none;padding:12px 26px;
    border-radius:2px;cursor:pointer;font-size:12px;font-weight:600;
    letter-spacing:.16em;text-transform:uppercase;margin-top:14px;transition:.18s}
  .gold-btn:hover{background:var(--gold-soft)}
  .gold-btn:disabled{opacity:.45;cursor:default}
  #explainBox{font-size:13.5px;line-height:1.72;white-space:pre-wrap;color:#ded7ca}
  #explainBox code{font-family:var(--mono);font-size:12.5px;color:var(--gold-soft)}
  .badge{display:inline-block;font-size:9.5px;padding:3px 10px;border-radius:2px;
    margin-left:8px;letter-spacing:.14em;text-transform:uppercase;vertical-align:middle}
  .badge-llm{border:1px solid var(--ok);color:#7ba97e}
  .badge-fallback{border:1px solid var(--gold-dim);color:var(--gold)}
  .prov{font-size:11px;color:var(--muted);margin-top:6px;letter-spacing:.02em}
  .prov b{color:var(--gold-dim);font-weight:500}
  .checks{margin-top:14px;padding-top:12px;border-top:1px solid var(--line);
    font-size:11px;color:var(--muted);letter-spacing:.04em}
  .pass{color:#7ba97e} .fail{color:#b9564f}
  .stats{display:flex;gap:26px;margin-bottom:16px;flex-wrap:wrap}
  .stat .n{font-family:var(--serif);font-size:26px;color:var(--gold-soft);line-height:1}
  .stat .l{font-size:9.5px;letter-spacing:.2em;text-transform:uppercase;color:var(--muted);margin-top:5px}
  ol.path{list-style:none;counter-reset:step;padding:0;margin:0}
  ol.path li{counter-increment:step;padding:12px 0 12px 42px;position:relative;
    border-bottom:1px solid var(--line)}
  ol.path li:last-child{border-bottom:none}
  ol.path li::before{content:counter(step);position:absolute;left:0;top:11px;
    width:26px;height:26px;border:1px solid var(--gold-dim);border-radius:50%;
    display:flex;align-items:center;justify-content:center;
    font-family:var(--serif);font-size:12px;color:var(--gold)}
  .path-name{color:var(--gold-soft);font-size:13.5px}
  .path-meta{font-size:11px;color:var(--muted);margin-top:3px}
  .empty{color:var(--muted);font-size:12.5px;font-style:italic}
  [dir="rtl"] .choice{text-align:right}
  [dir="rtl"] ol.path li{padding:12px 42px 12px 0}
  [dir="rtl"] ol.path li::before{left:auto;right:0}
  footer{padding:22px 34px 40px;border-top:1px solid var(--line);color:var(--muted);font-size:11px}
  footer a{color:var(--gold-dim);text-decoration:none}
  footer a:hover{color:var(--gold)}
</style>
</head>
<body>
<header>
  <div>
    <div class="brand">
      <h1 id="title">Adaptive CS Tutor</h1>
      <span class="house">Dhahab</span>
    </div>
    <div class="sub" id="subtitle">A concept-graph diagnostic for introductory computer science, built from published SIGCSE TS 2026 research. Runs entirely offline on a local model.</div>
  </div>
  <button id="langToggle" onclick="toggleLang()">العربية</button>
</header>
<main>
  <div>
    <div class="panel">
      <h2 id="graphHeading">Concept Graph</h2>
      <div class="legend">
        <span><i class="dot" style="background:var(--ok)"></i><span id="legendOk">Mastered</span></span>
        <span><i class="dot" style="background:var(--shaky)"></i><span id="legendShaky">Shaky</span></span>
        <span><i class="dot" style="background:var(--risk)"></i><span id="legendRisk">At risk</span></span>
        <span id="legendHint" style="color:var(--gold-dim)">Click any node to be taught it</span>
      </div>
      <div id="graphWrap"></div>
    </div>
    <div class="panel">
      <h2 id="pathHeading">Your Learning Path</h2>
      <div class="stats" id="statsRow"></div>
      <div id="pathBox"><div class="empty" id="pathEmpty">Take the diagnostic to generate an ordered remediation plan.</div></div>
    </div>
  </div>
  <div>
    <div class="panel">
      <h2 id="explainHeading">Explanation</h2>
      <div id="explainMeta"></div>
      <div id="explainBox" class="empty">Click any node in the graph to get an explanation built from its prerequisites.</div>
      <div class="checks" id="explainChecks"></div>
    </div>
    <div class="panel">
      <h2 id="quizHeading">Diagnostic Quiz</h2>
      <div id="quizPanel"></div>
      <button id="submitBtn" class="gold-btn" onclick="submitQuiz()">Submit Diagnostic</button>
    </div>
  </div>
</main>
<footer>
  <span id="footNote">Grounded in two SIGCSE TS 2026 papers</span> ·
  <a href="https://doi.org/10.1145/3770761.3777339" target="_blank" rel="noopener">10.1145/3770761.3777339</a> ·
  <span id="footStack">100% local inference · zero API cost</span>
</footer>
<script>
let lang = "en", graphData = null, quizData = null, states = {}, answers = {}, lastConcept = null;

const STR = {
  en: {
    title:"Adaptive CS Tutor",
    subtitle:"A concept-graph diagnostic for introductory computer science, built from published SIGCSE TS 2026 research. Runs entirely offline on a local model.",
    graphHeading:"Concept Graph", legendOk:"Mastered", legendShaky:"Shaky", legendRisk:"At risk",
    legendHint:"Click any node to be taught it",
    pathHeading:"Your Learning Path",
    pathEmpty:"Take the diagnostic to generate an ordered remediation plan.",
    quizHeading:"Diagnostic Quiz", submitBtn:"Submit Diagnostic", explainHeading:"Explanation",
    clickHint:"Click any node in the graph to get an explanation built from its prerequisites.",
    toggleLabel:"العربية", loading:"Consulting the local model…",
    mastered:"Mastered", shaky:"Shaky", atRisk:"At risk",
    builtOn:"Built on", unblocks:"unblocks", depth:"depth", downstream:"downstream concepts",
    srcLlm:"local qwen3-fast", srcCache:"local qwen3-fast · cached", srcFallback:"offline passage",
    chkGrounded:"builds on a retrieved prerequisite", chkCode:"code identifiers stayed English",
    footNote:"Grounded in two SIGCSE TS 2026 papers", footStack:"100% local inference · zero API cost"
  },
  ar: {
    title:"المدرّس التكيّفي لعلوم الحاسب",
    subtitle:"تشخيص قائم على خريطة المفاهيم لمقررات علوم الحاسب التمهيدية، مبني على أبحاث منشورة في SIGCSE TS 2026. يعمل بالكامل دون اتصال بالإنترنت على نموذج محلي.",
    graphHeading:"خريطة المفاهيم", legendOk:"متقن", legendShaky:"غير مستقر", legendRisk:"معرّض للخطر",
    legendHint:"اضغط على أي عقدة ليتم شرحها",
    pathHeading:"مسار التعلّم الخاص بك",
    pathEmpty:"أكمل الاختبار التشخيصي لإنشاء خطة علاجية مرتبة.",
    quizHeading:"اختبار تشخيصي", submitBtn:"إرسال الاختبار", explainHeading:"الشرح",
    clickHint:"اضغط على أي عقدة في الخريطة للحصول على شرح مبني على متطلباتها السابقة.",
    toggleLabel:"English", loading:"جارٍ استشارة النموذج المحلي…",
    mastered:"متقن", shaky:"غير مستقر", atRisk:"معرّض للخطر",
    builtOn:"مبني على", unblocks:"يفتح", depth:"العمق", downstream:"مفاهيم لاحقة",
    srcLlm:"qwen3-fast محلي", srcCache:"qwen3-fast محلي · مخزّن", srcFallback:"شرح جاهز دون اتصال",
    chkGrounded:"مبني على متطلب سابق تم استرجاعه", chkCode:"أسماء الكود بقيت بالإنجليزية",
    footNote:"مبني على ورقتين بحثيتين في SIGCSE TS 2026", footStack:"استدلال محلي بالكامل · بدون أي تكلفة"
  }
};

function esc(s){return String(s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));}
function code(s){return esc(s).replace(/`([^`]+)`/g,'<code>$1</code>');}

function applyLangStrings(){
  const s = STR[lang];
  ["title","subtitle","graphHeading","legendOk","legendShaky","legendRisk","legendHint",
   "pathHeading","quizHeading","explainHeading","footNote","footStack"].forEach(id=>{
    const el=document.getElementById(id); if(el) el.textContent=s[id];
  });
  document.getElementById('submitBtn').textContent = s.submitBtn;
  document.getElementById('langToggle').textContent = s.toggleLabel;
  const pe=document.getElementById('pathEmpty'); if(pe) pe.textContent=s.pathEmpty;
  document.body.dir = (lang==='ar') ? 'rtl' : 'ltr';
}

function toggleLang(){
  lang = (lang==='en') ? 'ar' : 'en';
  applyLangStrings();
  if(lastState) renderPath(lastState);
  if(lastConcept) explainNode(lastConcept);
}

let lastState = null;

async function loadAll(){
  const [g,q] = await Promise.all([
    fetch('/api/graph').then(r=>r.json()),
    fetch('/api/quiz').then(r=>r.json())
  ]);
  graphData=g; quizData=q;
  graphData.nodes.forEach(n=>states[n.id]='ok');
  renderGraph(); renderQuiz(); applyLangStrings();
}

function renderGraph(){
  const w=graphData.width, h=graphData.height, pos={};
  graphData.nodes.forEach(n=>pos[n.id]=n);
  let svg=`<svg width="${w}" height="${h}" viewBox="0 0 ${w} ${h}">`;
  graphData.edges.forEach(e=>{
    const a=pos[e.from], b=pos[e.to];
    svg+=`<line class="edge" x1="${a.x}" y1="${a.y}" x2="${b.x}" y2="${b.y}"/>`;
  });
  graphData.nodes.forEach(n=>{
    const st=states[n.id]||'ok';
    svg+=`<circle class="node-circle state-${st}" cx="${n.x}" cy="${n.y}" r="7" `
      +`onclick="explainNode('${n.id}')"><title>${esc(n.name)}</title></circle>`;
    svg+=`<text class="node-label" x="${n.x+13}" y="${n.y+4}">${esc(n.name)}</text>`;
  });
  document.getElementById('graphWrap').innerHTML = svg+`</svg>`;
}

function renderQuiz(){
  document.getElementById('quizPanel').innerHTML = quizData.map((q,i)=>`
    <div class="q" data-qid="${q.id}">
      <div class="q-prompt">${i+1}. ${code(q.prompt)}</div>
      ${q.choices.map((c,j)=>`<button class="choice" onclick="selectChoice('${q.id}',${j},this)">${code(c)}</button>`).join('')}
    </div>`).join('');
}

function selectChoice(qid,idx,el){
  answers[qid]=idx;
  el.parentElement.querySelectorAll('.choice').forEach(b=>b.classList.remove('selected'));
  el.classList.add('selected');
}

async function submitQuiz(){
  const btn=document.getElementById('submitBtn'); btn.disabled=true;
  const res=await fetch('/api/submit',{method:'POST',
    headers:{'Content-Type':'application/json'},body:JSON.stringify({answers})});
  const data=await res.json();
  states=data.states; lastState=data;
  renderGraph(); renderPath(data);
  btn.disabled=false;
}

function renderPath(data){
  const s=STR[lang], sm=data.summary;
  document.getElementById('statsRow').innerHTML = `
    <div class="stat"><div class="n">${sm.correct}/${sm.total}</div><div class="l">${lang==='ar'?'إجابات صحيحة':'Correct'}</div></div>
    <div class="stat"><div class="n">${sm.mastered}</div><div class="l">${s.mastered}</div></div>
    <div class="stat"><div class="n">${sm.shaky}</div><div class="l">${s.shaky}</div></div>
    <div class="stat"><div class="n">${sm.at_risk}</div><div class="l">${s.atRisk}</div></div>`;
  const box=document.getElementById('pathBox');
  if(!data.path.length){
    box.innerHTML=`<div class="empty">${lang==='ar'?'لا توجد فجوات. عمل ممتاز.':'No gaps detected. Excellent work.'}</div>`;
    return;
  }
  box.innerHTML = '<ol class="path">'+data.path.map(r=>`
    <li>
      <div class="path-name">${esc(r.name)}</div>
      <div class="path-meta">${s.depth} ${r.depth} · ${s.unblocks} ${r.unlock_count} ${s.downstream}</div>
    </li>`).join('')+'</ol>';
}

async function explainNode(id){
  lastConcept=id;
  const box=document.getElementById('explainBox');
  const meta=document.getElementById('explainMeta');
  const checks=document.getElementById('explainChecks');
  box.classList.add('empty'); box.textContent=STR[lang].loading;
  meta.innerHTML=''; checks.innerHTML='';
  const res=await fetch(`/api/explain?concept=${encodeURIComponent(id)}&lang=${lang}`);
  const d=await res.json();
  const s=STR[lang];
  box.classList.remove('empty');
  box.innerHTML = code(d.text);
  const badge = d.source==='fallback'
    ? `<span class="badge badge-fallback">${s.srcFallback}</span>`
    : `<span class="badge badge-llm">${d.source==='cache'?s.srcCache:s.srcLlm}</span>`;
  const prov = d.retrieved_names && d.retrieved_names.length
    ? `<div class="prov">${s.builtOn}: <b>${d.retrieved_names.map(esc).join(' · ')}</b></div>` : '';
  meta.innerHTML = `<div style="margin-bottom:10px"><span style="font-family:var(--mono);font-size:11.5px;color:var(--muted)">${esc(d.concept)}</span>${badge}</div>${prov}`;
  const rows=[[s.chkGrounded,d.grounded]];
  if(d.lang==='ar') rows.push([s.chkCode,d.keeps_code_english]);
  checks.innerHTML = rows.map(([l,ok])=>
    `<div><span class="${ok?'pass':'fail'}">${ok?'✓':'✗'}</span> ${l}</div>`).join('');
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
    parser.add_argument("--no-llm", action="store_true",
                        help="force canned explanations, never call Ollama")
    args = parser.parse_args()
    FORCE_NO_LLM = args.no_llm

    mode = "NO-LLM (offline passages only)" if FORCE_NO_LLM else "local qwen3-fast with offline fallback"
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"Adaptive CS Tutor  ·  http://localhost:{args.port}  [{mode}]")
    print(f"{len(NODES)} concepts · {len(QUIZ)} diagnostic questions · Ctrl-C to stop")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print()


if __name__ == "__main__":
    main()
