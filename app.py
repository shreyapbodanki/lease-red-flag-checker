import base64
import html

import streamlit as st
from google.genai import types

from lease_core import (SAMPLE_LEASE, SEV, analyze, build_email, find_span, highlight_pdf,
                        pdf_to_images, pdf_to_text, safety_score, score_label)


# stop streamlit reading $ as latex math
def md(text):
    return str(text).replace("$", "\\$")


CAT_ICON = {
    "deposit": "💰", "entry": "🚪", "repairs": "🔧", "fees": "🧾",
    "waiver": "⚖️", "renewal": "🔁", "other": "📌",
}

# va code sections checked by hand on law.lis.virginia.gov
VA_CODE = "https://law.lis.virginia.gov/vacode/title55.1/chapter12/section{}/"
LAWS = {
    "deposit": ("55.1-1226", "Deposits max 2 months' rent, returned within 45 days"),
    "entry": ("55.1-1229", "Landlord must give notice before entering"),
    "repairs": ("55.1-1220", "Landlord must keep the unit fit and livable"),
    "fees": ("55.1-1204", "Late fees capped at 10% of rent"),
    "waiver": ("55.1-1208", "Lease terms that aren't allowed"),
}
HANDBOOK = "https://dhcd.virginia.gov/landlord-tenant-resources"

HELP = [
    ("🎓", "VT Student Legal Services", "Free lease reviews for Virginia Tech students", "https://legal.uss.vt.edu/"),
    ("🤝", "Virginia Legal Aid", "Free civil legal help if you qualify", "https://www.valegalaid.org/"),
    ("📘", "VA Landlord-Tenant Handbook", "Official guide to your rights from DHCD", HANDBOOK),
]

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
:root {
  --bg: #ffffff; --text: #0a0a0a; --body: #3f3f46; --muted: #71717a; --faint: #a1a1aa;
  --border: #e4e4e7; --soft: #fafafa; --card: #ffffff; --track: #f1f1f3;
  --yellow: #ffd60a; --yellow-soft: #fff6c2; --yellow-ink: #6b5900;
  --paper: #ffffff; --paper-border: #e4e4e7;
  --ask: #0a0a0a; --ask-bg: #fff9db; --link: #0a0a0a;
  --shadow: 0 1px 2px rgba(0,0,0,.04), 0 8px 24px -16px rgba(0,0,0,.18);
}

/* base */
.stApp {background: var(--bg) !important;}
.stApp, .stApp p, .stApp li, .stApp label, .stApp button, .stApp textarea, .stApp input,
.stApp h1, .stApp h2, .stApp h3, .stApp h4, .card, .flag, .step, .hero, .help, .tip {
  font-family: 'Inter', system-ui, -apple-system, 'Segoe UI', sans-serif;}
header[data-testid="stHeader"], [data-testid="stToolbar"], [data-testid="stDecoration"],
[data-testid="stStatusWidget"], #MainMenu, footer {display: none !important;}
[data-testid="stHeaderActionElements"], .stMarkdown h1 a, .stMarkdown h4 a {display: none !important;}
.block-container {max-width: 1160px !important; padding-top: 2.4rem !important; padding-bottom: 4rem;}
[data-testid="stElementContainer"]:has(.input-anchor), [data-testid="stElementContainer"]:has(.side-anchor),
[data-testid="stElementContainer"]:has(.lease-anchor) {display: none;}
a {color: var(--link);}

/* header */
.hero {margin: 0 0 2rem; animation: rise .4s ease-out;}
.hero .brand {display: inline-flex; align-items: center; gap: .5rem; font-weight: 700; font-size: .9rem;
  letter-spacing: .02em; color: var(--text); margin-bottom: .9rem;}
.hero .logo {width: 1.6rem; height: 1.6rem; border-radius: 6px; background: var(--text); color: var(--yellow);
  display: inline-flex; align-items: center; justify-content: center; font-size: .9rem;}
.hero h1 {font-size: 2.6rem; line-height: 1.1; font-weight: 800; letter-spacing: -.035em; color: var(--text);
  margin: 0 0 .6rem; padding: 0;}
.hero h1 mark {background: linear-gradient(transparent 58%, var(--yellow) 58%, var(--yellow) 92%, transparent 92%);
  color: inherit; padding: 0 .1em;}
.hero p {font-size: 1.08rem; color: var(--body); margin: 0 0 1rem; max-width: 640px;}
.meta {display: flex; flex-wrap: wrap; gap: .4rem 1.1rem; font-size: .84rem; color: var(--muted);}
.meta span::before {content: ""; display: inline-block; width: 6px; height: 6px; border-radius: 50%;
  background: var(--yellow); margin-right: .45rem; vertical-align: middle; box-shadow: 0 0 0 1px #e6c200;}

/* input panel */
[data-testid="stVerticalBlockBorderWrapper"]:has(.input-anchor) {border: 1px solid var(--border) !important;
  border-radius: 14px !important; background: var(--card); box-shadow: var(--shadow);}
.stTabs [role="tablist"] {gap: .2rem; background: var(--soft); padding: .25rem; border-radius: 10px;
  border: 1px solid var(--border) !important; width: fit-content;}
.stTabs [role="tablist"]::after, .stTabs [role="tablist"]::before, .stTabs .react-aria-SelectionIndicator {display: none;}
.stTabs [data-testid="stTab"] {border-radius: 7px; padding: .35rem .9rem; height: auto; border: 0 !important;}
.stTabs [data-testid="stTab"] p {color: var(--muted) !important; font-weight: 500;}
.stTabs [data-testid="stTab"][aria-selected="true"] {background: #fff; box-shadow: 0 1px 2px rgba(0,0,0,.08);}
.stTabs [data-testid="stTab"][aria-selected="true"] p {color: var(--text) !important; font-weight: 600;}
[data-testid="stFileUploaderDropzone"] {border: 1.5px dashed #d4d4d8 !important; border-radius: 12px !important;
  background: var(--soft) !important; padding: 1.4rem 1.1rem !important;}
[data-testid="stFileUploaderDropzone"]:hover {border-color: var(--text) !important;}
[data-testid="stBaseButton-primary"] {background: var(--yellow) !important; color: var(--text) !important;
  border: 1px solid #e6c200 !important; border-radius: 10px !important; padding: .7rem 1rem !important;
  box-shadow: none !important; transition: background .12s, transform .12s;}
[data-testid="stBaseButton-primary"] p {color: var(--text) !important; font-weight: 700 !important;}
[data-testid="stBaseButton-primary"]:hover:not(:disabled) {background: #ffcc00 !important; transform: translateY(-1px);}
[data-testid="stBaseButton-primary"]:disabled {background: var(--track) !important; border-color: var(--border) !important;}
[data-testid="stBaseButton-primary"]:disabled p {color: var(--faint) !important;}
[data-testid="stBaseButton-tertiary"] p {color: var(--text) !important; text-decoration: underline;
  text-decoration-color: var(--yellow); text-decoration-thickness: 3px; text-underline-offset: 3px;}

/* score */
.card {background: var(--card); border: 1px solid var(--border); border-radius: 14px; padding: 1.3rem 1.4rem;
  box-shadow: var(--shadow); margin-bottom: 1rem; animation: rise .35s ease-out;}
.overview {display: flex; gap: 1.4rem; align-items: center; flex-wrap: wrap;}
.overview .txt {flex: 1; min-width: 220px;}
.overview .lbl {font-size: 1.15rem; font-weight: 700; margin-bottom: .3rem; letter-spacing: -.01em;}
.overview .sum {color: var(--body); line-height: 1.55; margin-bottom: .8rem; font-size: .93rem;}
.overview.compact {flex-direction: column; text-align: center; gap: .3rem;}
.overview.compact .txt {min-width: 0;}
.pill {display: inline-block; border-radius: 999px; padding: .15rem .65rem; font-size: .8rem; font-weight: 600;
  margin: 0 .25rem .25rem 0;}

/* section headings */
.panel-h {display: flex; justify-content: space-between; align-items: baseline; margin: .1rem 0 .7rem;}
.panel-h b {font-size: 1rem; font-weight: 700; color: var(--text);}
.panel-h span {font-size: .8rem; color: var(--muted);}
h4.sec {margin: 2rem 0 .7rem; font-size: 1.05rem; font-weight: 700; color: var(--text);}

/* flag cards */
.fgrid {display: grid; grid-template-columns: 1fr 1fr; gap: .8rem;}
.flag {background: var(--card); border: 1px solid var(--border); border-radius: 12px; padding: 1rem 1.1rem;
  position: relative; animation: rise .35s ease-out both; transition: border-color .15s, box-shadow .15s;}
.flag::before {content: ""; position: absolute; left: -1px; top: 14px; bottom: 14px; width: 3px; border-radius: 3px;
  background: var(--sevc, var(--border));}
.flag:hover {border-color: #d4d4d8; box-shadow: var(--shadow);}
.flag .top {display: flex; align-items: center; gap: .5rem; margin-bottom: .5rem; flex-wrap: wrap;}
.flag .num {width: 1.45rem; height: 1.45rem; border-radius: 50%; color: #fff; font-weight: 700; font-size: .74rem;
  display: inline-flex; align-items: center; justify-content: center;}
.flag .sev {font-size: .7rem; font-weight: 700; letter-spacing: .05em; text-transform: uppercase;
  border-radius: 5px; padding: .1rem .4rem;}
.flag .cat {font-size: .8rem; color: var(--muted); text-transform: capitalize;}
.flag .quote {font-family: Georgia, 'Times New Roman', serif; color: var(--text); font-size: .98rem;
  border-left: 2px solid var(--border); padding: .1rem 0 .1rem .75rem; margin: .3rem 0 .6rem;}
.flag .why {color: var(--body); font-size: .92rem; line-height: 1.5; margin-bottom: .6rem;}
.flag .ask {color: var(--ask); background: var(--ask-bg); border-radius: 8px; padding: .5rem .7rem; font-size: .9rem;}
.flag .law {margin-top: .6rem; font-size: .8rem; color: var(--muted);}
.flag .law a, .tip .law a, .help a b {color: var(--text); font-weight: 600; text-decoration: underline;
  text-decoration-color: var(--yellow); text-decoration-thickness: 2px; text-underline-offset: 2px;}

/* lease view */
.pg {position: relative; border: 1px solid var(--paper-border); border-radius: 12px; background: #fff;
  margin-bottom: 1rem; box-shadow: var(--shadow);}
.pg img {width: 100%; display: block; border-radius: 12px;}
.pg .pgno {position: absolute; bottom: .5rem; right: .8rem; font-size: .72rem; color: var(--faint);}
.paper {font-family: Georgia, 'Times New Roman', serif; font-size: 1rem; line-height: 1.85; color: var(--text);
  background: var(--paper); border: 1px solid var(--paper-border); border-radius: 12px; padding: 1.8rem 2rem;
  box-shadow: var(--shadow);}
.paper sup {font-family: Inter, sans-serif; font-size: .66rem; font-weight: 700; color: #fff; border-radius: 999px;
  padding: 0 .32rem; margin-left: .15rem;}
.spot {position: absolute; cursor: help; border-radius: 3px;}
.spot:hover {outline: 2px solid currentColor; outline-offset: 1px;}
.hl {position: relative; cursor: help; border-radius: 3px; padding: .05rem .1rem;}
.hl:hover {outline: 2px solid var(--hlc); outline-offset: 1px;}

/* hover card */
.tip {visibility: hidden; opacity: 0; position: absolute; z-index: 50; top: 100%; left: 0; width: 310px;
  padding-top: 8px; transition: opacity .12s; font-style: normal; line-height: 1.45; text-align: left; white-space: normal;}
.tip.r {left: auto; right: 0;}
.tip.up {top: auto; bottom: 100%; padding-top: 0; padding-bottom: 8px;}
.spot:hover .tip, .hl:hover .tip {visibility: visible; opacity: 1;}
.tip .in {background: #fff; color: var(--text); border: 1px solid var(--border); border-top: 3px solid;
  border-radius: 10px; padding: .75rem .85rem; font-size: .85rem;
  box-shadow: 0 2px 4px rgba(0,0,0,.04), 0 18px 40px -12px rgba(0,0,0,.25);}
.tip .row {display: flex; gap: .45rem; align-items: center; margin-bottom: .35rem;}
.tip .why {color: var(--body); margin-bottom: .45rem;}
.tip .ask {color: var(--ask); background: var(--ask-bg); border-radius: 7px; padding: .4rem .55rem; margin-bottom: .35rem;}
.tip .law {font-size: .76rem; color: var(--muted);}
.tip .pill-s {font-size: .66rem; font-weight: 700; text-transform: uppercase; letter-spacing: .04em;
  border-radius: 5px; padding: .05rem .38rem;}
.tip .num-s {width: 1.25rem; height: 1.25rem; border-radius: 50%; color: #fff; font-size: .7rem; font-weight: 700;
  display: inline-flex; align-items: center; justify-content: center;}

/* empty state */
.placeholder {border: 1.5px dashed #d4d4d8; border-radius: 14px; padding: 3.4rem 2rem; text-align: center;
  color: var(--muted); background: var(--soft);}
.placeholder .big {font-size: 2.2rem; filter: grayscale(1);}
.placeholder b {display: block; color: var(--text); font-size: 1.1rem; margin: .4rem 0 .3rem;}
.steps {display: grid; grid-template-columns: repeat(3, 1fr); gap: .8rem; margin-top: .8rem;}
.step {background: var(--card); border: 1px solid var(--border); border-radius: 12px; padding: .9rem 1rem;
  font-size: .88rem; color: var(--body);}
.step b {display: block; color: var(--text); margin-bottom: .2rem;}
.step i {font-style: normal; display: inline-flex; width: 1.4rem; height: 1.4rem; border-radius: 50%;
  background: var(--yellow); color: var(--text); font-weight: 700; font-size: .75rem; align-items: center;
  justify-content: center; margin-bottom: .45rem;}
.empty {text-align: center; color: var(--muted); padding: 1.5rem 0 .5rem;}

/* help links */
.help {display: grid; grid-template-columns: repeat(3, 1fr); gap: .8rem;}
.help a.item {display: block; background: var(--card); border: 1px solid var(--border); border-radius: 12px;
  padding: .9rem 1rem; color: var(--text); text-decoration: none; transition: border-color .15s, transform .15s;}
.help a.item:hover {border-color: var(--text); transform: translateY(-1px);}
.help .ic {font-size: 1.1rem; filter: grayscale(1);}
.help b {display: block; margin: .3rem 0 .15rem; font-size: .95rem;}
.help span {font-size: .84rem; color: var(--muted);}

/* misc widgets */
[data-testid="stSegmentedControl"] button {border-color: var(--border) !important;}
[data-testid="stSegmentedControl"] button[aria-checked="true"], [data-testid="stSegmentedControl"] button[kind*="Active"] {
  background: var(--text) !important; border-color: var(--text) !important;}
[data-testid="stSegmentedControl"] button[aria-checked="true"] p, [data-testid="stSegmentedControl"] button[kind*="Active"] p {color: #fff !important;}
[data-testid="stColumn"]:has(.side-anchor) {position: sticky; top: 1rem;}
[data-testid="stHorizontalBlock"]:has(.side-anchor) {align-items: flex-start;}
code, pre {background: var(--soft) !important;}

@keyframes rise {from {opacity: 0; transform: translateY(4px);} to {opacity: 1; transform: none;}}

@media (max-width: 640px) {
  .block-container {padding-left: 1rem !important; padding-right: 1rem !important; padding-top: 1.2rem !important;}
  .hero h1 {font-size: 1.9rem;}
  .fgrid, .help, .steps {grid-template-columns: 1fr;}
  [data-testid="stHorizontalBlock"]:has(.side-anchor) {flex-direction: column-reverse;}
  [data-testid="stColumn"]:has(.side-anchor) {position: static;}
  .paper {padding: 1.1rem 1.2rem; font-size: .95rem;}
  .tip {width: 250px;}
}
</style>
"""


def esc(text):
    return html.escape(str(text))


def score_ring(score, color):
    r, c = 52, 2 * 3.14159 * 52
    dash = c * score / 100
    return f"""<svg width="132" height="132" viewBox="0 0 132 132" style="flex-shrink:0">
  <circle cx="66" cy="66" r="{r}" fill="none" style="stroke:var(--track)" stroke-width="12"/>
  <circle cx="66" cy="66" r="{r}" fill="none" stroke="{color}" stroke-width="12" stroke-linecap="round"
    stroke-dasharray="{dash:.1f} {c:.1f}" transform="rotate(-90 66 66)"/>
  <text x="66" y="66" text-anchor="middle" font-size="32" font-weight="800" style="fill:var(--text)" font-family="sans-serif">{score}</text>
  <text x="66" y="88" text-anchor="middle" font-size="12" style="fill:var(--muted)" font-family="sans-serif">fairness score</text>
</svg>"""


def overview_card(flags, summary, compact=False):
    score = safety_score(flags)
    label, color = score_label(score)
    pills = ""
    for k in ("high", "medium", "low"):
        n = sum(1 for f in flags if f.get("severity") == k)
        name, fg, bg, _ = SEV[k]
        pills += f'<span class="pill" style="color:{fg};background:{bg};">{n} {name}</span>'
    cls = "card overview compact" if compact else "card overview"
    return f"""<div class="{cls}">
  {score_ring(score, color)}
  <div class="txt">
    <div class="lbl" style="color:{color};">{label}</div>
    <div class="sum">{esc(summary) if summary else "Here is what stood out in your lease."}</div>
    {pills}
  </div>
</div>"""


def law_line(cat):
    if cat in LAWS:
        sec, blurb = LAWS[cat]
        return (f'<div class="law">Know your rights: <a href="{VA_CODE.format(sec)}" target="_blank">'
                f'Va. Code § {sec}</a> · {esc(blurb)}</div>')
    return (f'<div class="law">Know your rights: <a href="{HANDBOOK}" target="_blank">'
            f'Virginia Landlord-Tenant Handbook</a></div>')


def flag_card(n, f):
    name, fg, bg, _ = SEV.get(f.get("severity", "low"), SEV["low"])
    cat = str(f.get("category", "other")).lower()
    return f"""<div class="flag" style="--sevc:{fg};">
  <div class="top">
    <span class="num" style="background:{fg};">{n}</span>
    <span class="sev" style="color:{fg};background:{bg};">{name}</span>
    <span class="cat">{esc(cat)}</span>
  </div>
  <div class="quote">"{esc(f.get("clause_quote", ""))}"</div>
  <div class="why">{esc(f.get("why", ""))}</div>
  <div class="ask"><b>Ask your landlord:</b> {esc(f.get("question_for_landlord", ""))}</div>
  {law_line(cat)}
</div>"""


def help_cards():
    items = "".join(f'<a class="item" href="{url}" target="_blank">'
                    f'<b>{esc(t)}</b><span>{esc(d)}</span></a>' for ic, t, d, url in HELP)
    return f'<h4 class="sec">Need a second opinion?</h4><div class="help">{items}</div>'


def tip_html(n, f, cls=""):
    name, fg, bg, _ = SEV.get(f.get("severity", "low"), SEV["low"])
    cat = str(f.get("category", "other")).lower()
    return f"""<span class="tip {cls}"><span class="in" style="border-top-color:{fg};display:block;">
<span class="row"><span class="num-s" style="background:{fg};">{n}</span>
<span class="pill-s" style="color:{fg};background:{bg};">{name}</span>
<span style="color:var(--muted);font-size:.8rem;">{esc(cat)}</span></span>
<span class="why" style="display:block;">{esc(f.get("why", ""))}</span>
<span class="ask" style="display:block;"><b>Ask:</b> {esc(f.get("question_for_landlord", ""))}</span>
{law_line(cat).replace("<div", "<span style='display:block'").replace("</div>", "</span>")}
</span></span>""".replace("\n", "")


def highlighted_lease(text, flags):
    spans = []
    for n, f in enumerate(flags, 1):
        hit = find_span(text, f.get("clause_quote", ""))
        if hit and all(hit[1] <= s or hit[0] >= e for s, e, _, _ in spans):
            spans.append((hit[0], hit[1], n, f))
    spans.sort(key=lambda x: x[0])
    out, pos = [], 0
    for s, e, n, f in spans:
        _, fg, _, hl = SEV.get(f.get("severity", "low"), SEV["low"])
        out.append(esc(text[pos:s]))
        out.append(f'<span class="hl" style="background:{hl};--hlc:{fg};">{esc(text[s:e])}'
                   f'<sup style="background:{fg};">{n}</sup>{tip_html(n, f)}</span>')
        pos = e
    out.append(esc(text[pos:]))
    # br instead of newlines so markdown leaves it alone
    body = "".join(out).replace("\n", "<br>")
    return f'<div class="paper">{body}</div>', len(spans)


def page_html(png, spots, label):
    img = base64.b64encode(png).decode()
    marks = []
    for n, f, (x, y, w, h) in spots:
        fg = SEV.get(f.get("severity", "low"), SEV["low"])[1]
        side = "r" if x + w / 2 > 55 else ""
        side += " up" if y > 70 else ""
        marks.append(f'<span class="spot" style="left:{x:.2f}%;top:{y:.2f}%;width:{w:.2f}%;height:{h:.2f}%;'
                     f'color:{fg};">{tip_html(n, f, side)}</span>')
    return (f'<div class="pg"><img src="data:image/png;base64,{img}" alt="{esc(label)}">'
            f'{"".join(marks)}<span class="pgno">{esc(label)}</span></div>')


# ui
st.set_page_config(page_title="Lease Red-Flag Checker", page_icon="🏠", layout="wide")
st.markdown(CSS, unsafe_allow_html=True)
st.markdown("""<div class="hero">
  <div class="brand"><span class="logo">⚑</span>Lease Red-Flag Checker</div>
  <h1>Know what you're <mark>signing</mark>.</h1>
  <p>Drop in your lease. We highlight the clauses worth a second look and explain them in plain English.</p>
  <div class="meta"><span>Powered by Gemma 4</span><span>PDF, photos or text</span><span>Virginia tenant law</span><span>Nothing is stored</span></div>
</div>""", unsafe_allow_html=True)

main, side = st.columns([7, 4], gap="large")

# right side: upload + score
with side:
    st.markdown('<span class="side-anchor"></span>', unsafe_allow_html=True)
    with st.container(border=True):
        st.markdown('<span class="input-anchor"></span>', unsafe_allow_html=True)
        tab_up, tab_paste = st.tabs(["Upload", "Paste text"])
        with tab_up:
            uploads = st.file_uploader("PDF or photos of your lease", type=["pdf", "png", "jpg", "jpeg"],
                                       accept_multiple_files=True, label_visibility="collapsed")
        with tab_paste:
            if st.button("Try a sample lease", type="tertiary"):
                st.session_state.pasted = SAMPLE_LEASE
            pasted = st.text_area("Lease text", height=180, key="pasted", label_visibility="collapsed",
                                  placeholder="Paste your lease text here...")
        ready = bool(uploads or pasted.strip())
        go = st.button("Check my lease →", type="primary", disabled=not ready, use_container_width=True)
    score_slot = st.container()

if go:
    parts, text, pdfs = [], [], []
    with side:
        box = st.empty()
    with box.status("Checking your lease...", expanded=True) as status:
        st.write("📄 Reading pages")
        for f in uploads or []:
            data = f.read()
            if f.type == "application/pdf":
                pdfs.append((f.name, data))
                page_text = pdf_to_text(data)
                text.append(page_text)
                for img in pdf_to_images(data):
                    parts.append(types.Part.from_bytes(data=img, mime_type="image/png"))
                # text alongside images so quotes match exactly
                if page_text.strip():
                    parts.append(f"Extracted text of {f.name}:\n{page_text}")
            else:
                parts.append(types.Part.from_bytes(data=data, mime_type=f.type))
        if pasted.strip():
            parts.append(pasted)
            text.append(pasted)
        st.write("🧠 Gemma 4 is reviewing each clause")
        try:
            lease_text = "\n\n".join(t for t in text if t.strip())
            st.session_state.result = analyze(parts, lease_text)
            st.session_state.lease_text = lease_text
            st.session_state.pdfs = pdfs
            st.session_state.pop("error", None)
            ok = True
        except Exception as e:
            ok = False
            # drop old results so they don't look like this run
            st.session_state.pop("result", None)
            st.session_state.error = str(e)
    box.empty()
    if ok:
        st.toast("Lease checked", icon="✅")
    st.rerun()

result = st.session_state.get("result")
flags = []
if result:
    flags = result.get("flags", [])
    order = {"high": 0, "medium": 1, "low": 2}
    flags.sort(key=lambda f: order.get(f.get("severity", "low"), 3))
    with score_slot:
        st.markdown(overview_card(flags, result.get("summary", ""), compact=True), unsafe_allow_html=True)

with side:
    if st.session_state.get("error") and not result:
        err = st.session_state.error
        if "API key" in err or "API_KEY" in err or "PERMISSION_DENIED" in err:
            st.error("The API key isn't working. Check GEMINI_API_KEY on the server.")
        elif "429" in err or "RESOURCE_EXHAUSTED" in err:
            st.error("Gemma is getting a lot of requests right now. Wait a few seconds and try again.")
        else:
            st.error("Something went wrong while reading the lease. Try again in a moment.")
        with st.expander("Error details"):
            st.code(err, language=None, wrap_lines=True)

# left side: highlighted lease, then the flags under it
with main:
    if not result:
        st.markdown("""<div class="placeholder"><div class="big">📄</div>
<b>Your lease will show up here</b>
Upload a PDF or paste the text on the right. Flagged clauses get highlighted,<br>and you can hover any highlight to see why it matters.</div>""",
                    unsafe_allow_html=True)
        st.markdown("""<div class="steps">
  <div class="step"><i>1</i><b>Add your lease</b>Upload a PDF, snap photos, or paste the text.</div>
  <div class="step"><i>2</i><b>Gemma 4 reviews it</b>Each clause is checked against Virginia tenant law.</div>
  <div class="step"><i>3</i><b>Know what to ask</b>Get plain-English flags and a ready-to-send email.</div>
</div>""", unsafe_allow_html=True)
    else:
        pdfs = st.session_state.get("pdfs", [])
        lease_text = st.session_state.get("lease_text", "")
        if pdfs:
            name, data = pdfs[0]
            pages, found = highlight_pdf(data, flags)
            st.markdown(f'<div class="panel-h"><b>{esc(name)}</b><span>{found} of {len(flags)} marked · '
                        f'hover a highlight for details</span></div>', unsafe_allow_html=True)
            for i, (png, spots) in enumerate(pages, 1):
                st.markdown(page_html(png, spots, f"page {i}"), unsafe_allow_html=True)
        elif lease_text:
            page, found = highlighted_lease(lease_text, flags)
            st.markdown(f'<div class="panel-h"><b>Your lease</b><span>{found} of {len(flags)} highlighted · '
                        f'hover a highlight for details</span></div>', unsafe_allow_html=True)
            st.markdown(page, unsafe_allow_html=True)
        else:
            st.info("The highlighted view works with PDFs and pasted text. Photos are still checked; see the flags below.")

        st.markdown(f'<div class="panel-h" style="margin-top:1.4rem;"><b>All flags</b><span>{len(flags)} found</span></div>',
                    unsafe_allow_html=True)
        if not flags:
            st.markdown('<div class="empty">🎉 Nothing stood out. Still read it carefully before signing!</div>',
                        unsafe_allow_html=True)
        else:
            pick = st.segmented_control("Show", ["All", "High", "Medium", "Low"], default="All",
                                        label_visibility="collapsed")
            shown = [(n, f) for n, f in enumerate(flags, 1)
                     if pick in (None, "All") or f.get("severity", "").lower() == pick.lower()]
            if not shown:
                st.caption(f"No {pick.lower()} flags.")
            else:
                st.markdown('<div class="fgrid">' + "".join(flag_card(n, f) for n, f in shown) + "</div>",
                            unsafe_allow_html=True)

# bottom: email + links
if result and flags:
    st.markdown('<h4 class="sec">Email your landlord</h4>', unsafe_allow_html=True)
    email = build_email(flags)
    with st.container(border=True):
        st.caption("Hover the box and click the copy icon, or download it.")
        st.code(email, language=None, wrap_lines=True)
        st.download_button("⬇️ Download as .txt", email, file_name="questions-for-landlord.txt")

st.markdown(help_cards(), unsafe_allow_html=True)
st.markdown("<br>", unsafe_allow_html=True)
st.caption("Not legal advice. Built with Gemma 4 at GDG Build with AI × Hacktoberfest 2026 · Virginia Tech")
