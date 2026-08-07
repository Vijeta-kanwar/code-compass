"""CodeCompass — Streamlit frontend.

Run with:  streamlit run app.py

- "Load demo" fills the app with a sample repo (chat + a graphical architecture
  map) so you can screenshot without a key or indexing.
- "Index" explores a real repo. The Architecture map works with no API key;
  add ANTHROPIC_API_KEY to .env for written answers in the Ask tab.
"""
from __future__ import annotations

import json

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from codecompass.engine.rag import RagEngine
from codecompass.pipeline import index_repo

st.set_page_config(page_title="CodeCompass", page_icon="🧭", layout="wide")

st.markdown(
    """
    <style>
      [data-testid="stToolbar"], [data-testid="stDecoration"],
      #MainMenu, header, footer {visibility: hidden; height: 0;}
      .block-container {padding-top: 2.2rem;}
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------- demo data
DEMO_STATS = {"Files": 34, "Chunks": 412, "Modules": 18}
DEMO_ANSWER = (
    "Authentication lives in `requests/auth.py`. Each scheme is a callable "
    "class attached to the request. `HTTPBasicAuth` sets the `Authorization` "
    "header from an encoded username and password *(requests/auth.py:61-72)*, "
    "while `HTTPDigestAuth` handles the challenge-response flow "
    "*(requests/auth.py:105-241)*."
)
DEMO_SOURCES = [
    ("requests/auth.py:61-72", "HTTPBasicAuth",
     "class HTTPBasicAuth(AuthBase):\n"
     '    """Attaches HTTP Basic Authentication to the given Request."""\n\n'
     "    def __call__(self, r):\n"
     "        r.headers['Authorization'] = _basic_auth_str(\n"
     "            self.username, self.password)\n"
     "        return r"),
    ("requests/auth.py:105-241", "HTTPDigestAuth",
     "class HTTPDigestAuth(AuthBase):\n"
     '    """Attaches HTTP Digest Authentication to the given Request."""\n\n'
     "    def build_digest_header(self, method, url):\n"
     "        ...  # computes the challenge-response digest"),
]
DEMO_EDGES = [
    ("api", "sessions"), ("sessions", "adapters"), ("sessions", "models"),
    ("sessions", "cookies"), ("sessions", "utils"), ("adapters", "models"),
    ("adapters", "utils"), ("models", "auth"), ("models", "cookies"),
    ("models", "structures"), ("auth", "utils"), ("utils", "structures"),
]
DEMO_TOP = [("utils", 4), ("models", 3), ("structures", 2),
            ("cookies", 2), ("adapters", 1), ("auth", 1)]
DEMO_SUMMARY = (
    "`requests` is organized around a **Session** that ties the pieces together. "
    "`api` exposes the top-level helpers (`get`, `post`) and delegates to `sessions`, "
    "which drives `adapters` for transport and builds `models` for requests and "
    "responses. The shared helpers in `utils` and `structures` are the most "
    "depended-on modules — a natural place for a new contributor to start reading."
)


def _demo_turns():
    return [
        {"role": "user", "content": "Where is authentication handled?"},
        {"role": "assistant", "payload": {"text": DEMO_ANSWER, "sources": DEMO_SOURCES}},
    ]


def short(module: str) -> str:
    return module.split(".")[-1]


def network_html(edges, top) -> str:
    """A styled, interactive module-dependency diagram (vis-network)."""
    deps = {short(m): d for m, d in top}
    top_names = set(deps)
    names = {short(a) for a, _ in edges} | {short(b) for _, b in edges}

    nodes = []
    for n in sorted(names):
        is_core = n in top_names
        size = 16 + deps.get(n, 0) * 6
        nodes.append({
            "id": n, "label": n, "value": size,
            "color": {
                "background": "#f0e6d3" if is_core else "#ffffff",
                "border": "#a9722a" if is_core else "#c9d3dc",
                "highlight": {"background": "#f6efe0", "border": "#a9722a"},
            },
            "font": {"color": "#16222f", "face": "Inter, sans-serif",
                     "size": 15 if is_core else 13},
            "borderWidth": 2 if is_core else 1,
        })
    links = [{"from": short(a), "to": short(b)} for a, b in edges]

    return f"""
<div id="net" style="height:460px;width:100%;"></div>
<script src="https://cdnjs.cloudflare.com/ajax/libs/vis-network/9.1.9/standalone/umd/vis-network.min.js"></script>
<script>
  const nodes = new vis.DataSet({json.dumps(nodes)});
  const edges = new vis.DataSet({json.dumps(links)});
  const net = new vis.Network(document.getElementById('net'), {{nodes, edges}}, {{
    nodes: {{ shape: 'box', shapeProperties: {{ borderRadius: 8 }},
              margin: 10, widthConstraint: {{ minimum: 54 }} }},
    edges: {{ arrows: {{ to: {{ enabled: true, scaleFactor: 0.6 }} }},
              color: {{ color: '#9fb0bd', highlight: '#a9722a' }},
              smooth: {{ type: 'cubicBezier', roundness: 0.5 }}, width: 1.4 }},
    layout: {{ improvedLayout: true }},
    physics: {{ solver: 'forceAtlas2Based',
                forceAtlas2Based: {{ gravitationalConstant: -55, springLength: 110 }},
                stabilization: {{ iterations: 220 }} }},
    interaction: {{ hover: true, dragNodes: true, zoomView: true }}
  }});
  net.once('stabilizationIterationsDone', () => net.setOptions({{ physics: false }}));
</script>
"""


def heuristic_summary(top, n_modules, n_edges) -> str:
    if not top:
        return f"This repo has {n_modules} modules and {n_edges} internal imports."
    names = ", ".join(f"`{short(m)}`" for m, _ in top[:3])
    return (
        f"This repo has {n_modules} modules connected by {n_edges} internal imports. "
        f"The most depended-on modules are {names} — usually the core the rest builds "
        f"on, and a good place to start reading."
    )


# ---------------------------------------------------------------- sidebar
with st.sidebar:
    st.markdown("### 🧭 CodeCompass")
    st.caption("Point new developers in the right direction.")
    source = st.text_input("GitHub URL or local path", placeholder="github.com/psf/requests")
    name = st.text_input("Name (optional)")

    if st.button("Index", type="primary", use_container_width=True) and source:
        with st.spinner("Cloning, parsing, indexing…"):
            result = index_repo(source, name or None)
        top = [(m, d) for m, d in sorted(result.graph.in_degree(),
               key=lambda kv: kv[1], reverse=True) if d > 0][:8]
        st.session_state.update(
            repo_name=result.repo_name,
            stats={"Files": result.file_count, "Chunks": result.chunk_count,
                   "Modules": result.graph.number_of_nodes()},
            edges=list(result.graph.edges()), top=top,
            summary=heuristic_summary(top, result.graph.number_of_nodes(),
                                      result.graph.number_of_edges()),
            history=[], demo=False,
        )

    if st.button("Load demo", use_container_width=True):
        st.session_state.update(
            repo_name="requests", stats=DEMO_STATS, edges=DEMO_EDGES, top=DEMO_TOP,
            summary=DEMO_SUMMARY, history=_demo_turns(), demo=True,
        )

    if stats := st.session_state.get("stats"):
        st.success("Indexed")
        for label, value in stats.items():
            st.markdown(f"**{label}:** {value}")

    if st.session_state.get("repo_name") and not st.session_state.get("demo"):
        if RagEngine(st.session_state["repo_name"]).has_key:
            st.caption("✅ API key found — written answers on.")
        else:
            st.caption("🔑 No API key — showing relevant code only.")

# ---------------------------------------------------------------- main
st.title("🧭 CodeCompass")

repo_name = st.session_state.get("repo_name")
if not repo_name:
    st.info("Index a repository from the sidebar to start — or click **Load demo**.")
    st.stop()

tab_ask, tab_arch = st.tabs(["💬  Ask", "🗺️  Architecture"])


def render_turn(turn) -> None:
    with st.chat_message(turn["role"]):
        if turn["role"] == "user":
            st.markdown(turn["content"])
            return
        p = turn["payload"]
        if p.get("note"):
            st.info(p["note"])
        if p.get("text"):
            st.markdown(p["text"])
        if p.get("sources"):
            with st.expander("Relevant code", expanded=not p.get("text")):
                for citation, symbol, code in p["sources"]:
                    st.markdown(f"**`{citation}`** — `{symbol}`")
                    st.code(code, language="python")


with tab_ask:
    st.subheader(f"Ask about `{repo_name}`")
    st.session_state.setdefault("history", [])
    for turn in st.session_state["history"]:
        render_turn(turn)

    if question := st.chat_input("Where is authentication handled?"):
        st.session_state["history"].append({"role": "user", "content": question})
        render_turn({"role": "user", "content": question})
        with st.spinner("Searching the codebase…"):
            answer = RagEngine(repo_name).ask(question)
        payload = {
            "text": answer.text if answer.used_llm else "",
            "note": answer.note,
            "sources": [(s.citation, s.symbol, s.text) for s in answer.sources],
        }
        st.session_state["history"].append({"role": "assistant", "payload": payload})
        render_turn({"role": "assistant", "payload": payload})

with tab_arch:
    st.subheader(f"Architecture of `{repo_name}`")
    if summary := st.session_state.get("summary"):
        st.markdown(summary)

    edges = st.session_state.get("edges", [])
    top = st.session_state.get("top", [])

    if edges:
        st.caption("Drag the modules around. Arrows point to what a module imports; highlighted nodes are the most depended-on.")
        components.html(network_html(edges, top), height=470)
    else:
        st.info("No internal dependencies detected in this repo.")

    if top:
        st.markdown("**Most depended-on modules**")
        df = pd.DataFrame(
            {"module": [short(m) for m, _ in top], "dependents": [d for _, d in top]}
        ).set_index("module")
        st.bar_chart(df, color="#a9722a", horizontal=True)