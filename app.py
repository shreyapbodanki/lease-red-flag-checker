import os
import html
import json
import re

import pymupdf
import streamlit as st
from google import genai
from google.genai import types

# gemma 4 via gemini api
MODEL = "gemma-4-26b-a4b-it"
MAX_PAGES = 8

client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))

PROMPT = """You are a tenant-rights assistant for renters in Virginia, USA.
Read the lease provided (as page images and/or text). Find clauses that may be
unfair to the tenant or may conflict with the Virginia Residential Landlord and
Tenant Act (VRLTA). Examples of things worth flagging:
- security deposit above two months' rent, or no clear return timeline
- landlord entry without reasonable advance notice
- tenant waiving legal rights or the landlord's duty to make repairs
- tenant paying the landlord's attorney fees no matter who wins
- unusually high or vague fees (late fees, cleaning, "admin")
- automatic renewal or penalties that are easy to miss

Rules:
- Quote the exact clause text (short) so the user can find it.
- Use cautious language ("may", "could"). This is not legal advice.
- If nothing is concerning, return an empty flags list.

Return ONLY valid JSON in this exact shape:
{
  "summary": "2-3 sentence plain-English overview of the lease",
  "flags": [
    {
      "clause_quote": "exact short quote from the lease",
      "category": "deposit | entry | repairs | fees | waiver | renewal | other",
      "severity": "high | medium | low",
      "why": "plain-English explanation for a student renter",
      "question_for_landlord": "one polite question the tenant could ask"
    }
  ]
}"""


# turn pdf pages into png bytes
def pdf_to_images(data):
    doc = pymupdf.open(stream=data, filetype="pdf")
    pages = []
    for i, page in enumerate(doc):
        if i >= MAX_PAGES:
            break
        pages.append(page.get_pixmap(dpi=150).tobytes("png"))
    return pages


# pull plain text for the highlighted view
def pdf_to_text(data):
    doc = pymupdf.open(stream=data, filetype="pdf")
    return "\n".join(page.get_text() for i, page in enumerate(doc) if i < MAX_PAGES)


# pull json out even if model wraps it in text
def parse_json(text):
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        raise


def analyze(parts):
    resp = client.models.generate_content(
        model=MODEL,
        contents=parts + [PROMPT],
        config=types.GenerateContentConfig(
            temperature=0.2,
            response_mime_type="application/json",
        ),
    )
    return normalize(parse_json(resp.text))


# gemma sometimes returns a list instead of the object
def normalize(data):
    if isinstance(data, dict):
        data.setdefault("summary", "")
        data.setdefault("flags", [])
        return data
    if isinstance(data, list):
        # [ {summary, flags} ]
        if len(data) == 1 and isinstance(data[0], dict) and "flags" in data[0]:
            return normalize(data[0])
        # list of flags only
        flags = [d for d in data if isinstance(d, dict)]
        return {"summary": "", "flags": flags}
    return {"summary": str(data), "flags": []}


# stop streamlit reading $ as latex math
def md(text):
    return str(text).replace("$", "\\$")


def build_email(flags):
    lines = ["Hi,", "",
             "Thanks for sending over the lease. Before signing, I had a few questions:", ""]
    for i, f in enumerate(flags, 1):
        lines.append(f"{i}. {f.get('question_for_landlord', '')}")
    lines += ["", "Thanks so much!"]
    return "\n".join(lines)


# 100 = clean, each flag knocks points off
def safety_score(flags):
    cost = {"high": 18, "medium": 8, "low": 3}
    return max(5, 100 - sum(cost.get(f.get("severity", "low"), 3) for f in flags))


def score_label(score):
    if score >= 80:
        return "Looks pretty fair", "#16a34a"
    if score >= 50:
        return "A few things to ask about", "#d97706"
    return "Read carefully before signing", "#dc2626"


SAMPLE_LEASE = """RESIDENTIAL LEASE AGREEMENT
Premises: 123 Example St, Apt 4, Blacksburg, VA 24060

1. RENT. Tenant agrees to pay $1,200 per month, due on the 1st of each month.

2. SECURITY DEPOSIT. Tenant shall pay a security deposit of $4,500 before move-in.

3. ACCESS. Landlord may enter the premises at any time without notice.

4. MAINTENANCE. Tenant waives all rights to request repairs and accepts the unit as-is.

5. LEGAL FEES. Tenant shall pay all of Landlord's attorney fees in any dispute regardless of outcome.

6. LATE FEES. A $75 administrative fee applies to all late payments plus $25 per day.

7. RENEWAL. This lease automatically renews for 12 months unless tenant gives 120 days' written notice.

8. SNOW. Tenant is responsible for snow removal on the front walkway."""

SEV = {
    "high": ("High", "#dc2626", "#fef2f2", "#fecaca"),
    "medium": ("Medium", "#d97706", "#fff7ed", "#fed7aa"),
    "low": ("Low", "#a16207", "#fefce8", "#fef08a"),
}

CAT_ICON = {
    "deposit": "💰", "entry": "🚪", "repairs": "🔧", "fees": "🧾",
    "waiver": "⚖️", "renewal": "🔁", "other": "📌",
}

CSS = """
<style>
.block-container {max-width: 880px; padding-top: 2rem; padding-bottom: 4rem;}
#MainMenu, footer {visibility: hidden;}

.hero {background: linear-gradient(135deg, #065f46 0%, #059669 55%, #34d399 100%);
  border-radius: 22px; padding: 2rem 2rem 1.6rem; color: white; margin-bottom: 1.4rem;
  box-shadow: 0 12px 32px -12px rgba(5,150,105,.5);}
.hero h1 {color: white; font-size: 2.3rem; font-weight: 800; margin: 0 0 .3rem; padding: 0;}
.hero p {color: rgba(255,255,255,.9); font-size: 1.08rem; margin: 0 0 1rem;}
.chip {display: inline-block; background: rgba(255,255,255,.18); border: 1px solid rgba(255,255,255,.3);
  border-radius: 999px; padding: .25rem .75rem; font-size: .82rem; margin: 0 .35rem .35rem 0;}

.card {background: white; border: 1px solid #e5e7eb; border-radius: 18px; padding: 1.4rem 1.5rem;
  box-shadow: 0 4px 18px -10px rgba(17,24,39,.18); margin-bottom: 1rem;}
.overview {display: flex; gap: 1.6rem; align-items: center; flex-wrap: wrap;}
.overview .txt {flex: 1; min-width: 240px;}
.overview .lbl {font-size: 1.25rem; font-weight: 700; margin-bottom: .3rem;}
.overview .sum {color: #374151; line-height: 1.55; margin-bottom: .8rem;}
.pill {display: inline-block; border-radius: 999px; padding: .2rem .7rem; font-size: .82rem;
  font-weight: 600; margin-right: .4rem;}

.flag {border: 1px solid #e5e7eb; border-left: 6px solid; border-radius: 14px; padding: 1rem 1.2rem;
  margin-bottom: .8rem; background: white;}
.flag .top {display: flex; align-items: center; gap: .55rem; margin-bottom: .45rem;}
.flag .num {width: 1.6rem; height: 1.6rem; border-radius: 50%; color: white; font-weight: 700;
  font-size: .8rem; display: inline-flex; align-items: center; justify-content: center;}
.flag .sev {font-size: .74rem; font-weight: 700; letter-spacing: .05em; text-transform: uppercase;
  border-radius: 6px; padding: .1rem .45rem;}
.flag .cat {font-size: .8rem; color: #6b7280; text-transform: capitalize;}
.flag .quote {font-family: Georgia, serif; font-style: italic; color: #111827; background: #f9fafb;
  border-radius: 8px; padding: .55rem .75rem; margin: .4rem 0 .6rem;}
.flag .why {color: #374151; margin-bottom: .55rem; line-height: 1.5;}
.flag .ask {color: #064e3b; background: #ecfdf5; border-radius: 8px; padding: .5rem .75rem; font-size: .94rem;}

.paper {font-family: Georgia, serif; font-size: 1rem; line-height: 1.8; color: #1f2937; background: #fffdf8;
  border: 1px solid #ece7da; border-radius: 14px; padding: 1.6rem 1.8rem; max-height: 560px;
  overflow-y: auto;}
.paper mark {border-radius: 4px; padding: .05rem .15rem; color: inherit;}
.paper sup {font-family: sans-serif; font-size: .7rem; font-weight: 700; color: white; border-radius: 999px;
  padding: 0 .35rem; margin-left: .15rem;}

.empty {text-align: center; color: #6b7280; padding: 1.5rem 0 .5rem;}
.steps {display: flex; gap: .8rem; flex-wrap: wrap; margin-top: .4rem;}
.step {flex: 1; min-width: 180px; background: #f0fdf4; border-radius: 14px; padding: .9rem 1rem; font-size: .92rem; color: #374151;}
.step b {display: block; color: #111827; margin-bottom: .2rem;}
</style>
"""


def esc(text):
    return html.escape(str(text))


def score_ring(score, color):
    r, c = 52, 2 * 3.14159 * 52
    dash = c * score / 100
    return f"""<svg width="132" height="132" viewBox="0 0 132 132">
  <circle cx="66" cy="66" r="{r}" fill="none" stroke="#f1f5f9" stroke-width="12"/>
  <circle cx="66" cy="66" r="{r}" fill="none" stroke="{color}" stroke-width="12" stroke-linecap="round"
    stroke-dasharray="{dash:.1f} {c:.1f}" transform="rotate(-90 66 66)"/>
  <text x="66" y="66" text-anchor="middle" font-size="32" font-weight="800" fill="#111827" font-family="sans-serif">{score}</text>
  <text x="66" y="88" text-anchor="middle" font-size="12" fill="#6b7280" font-family="sans-serif">fairness score</text>
</svg>"""


def overview_card(flags, summary):
    score = safety_score(flags)
    label, color = score_label(score)
    pills = ""
    for k in ("high", "medium", "low"):
        n = sum(1 for f in flags if f.get("severity") == k)
        name, fg, bg, _ = SEV[k]
        pills += f'<span class="pill" style="color:{fg};background:{bg};">{n} {name}</span>'
    return f"""<div class="card overview">
  {score_ring(score, color)}
  <div class="txt">
    <div class="lbl" style="color:{color};">{label}</div>
    <div class="sum">{esc(summary) if summary else "Here is what stood out in your lease."}</div>
    {pills}
  </div>
</div>"""


def flag_card(n, f):
    name, fg, bg, _ = SEV.get(f.get("severity", "low"), SEV["low"])
    cat = f.get("category", "other")
    return f"""<div class="flag" style="border-left-color:{fg};">
  <div class="top">
    <span class="num" style="background:{fg};">{n}</span>
    <span class="sev" style="color:{fg};background:{bg};">{name}</span>
    <span class="cat">{CAT_ICON.get(cat, "📌")} {esc(cat)}</span>
  </div>
  <div class="quote">"{esc(f.get("clause_quote", ""))}"</div>
  <div class="why">{esc(f.get("why", ""))}</div>
  <div class="ask"><b>Ask your landlord:</b> {esc(f.get("question_for_landlord", ""))}</div>
</div>"""


# find a quote in the lease even if spacing or punctuation differs
def find_span(text, quote):
    words = re.findall(r"\w+", quote)
    for take in (len(words), 8, 5):
        if len(words) < 3 or take > len(words):
            continue
        pat = r"\W+".join(re.escape(w) for w in words[:take])
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            return m.start(), m.end()
    return None


def highlighted_lease(text, flags):
    spans = []
    for n, f in enumerate(flags, 1):
        hit = find_span(text, f.get("clause_quote", ""))
        if hit and all(hit[1] <= s or hit[0] >= e for s, e, _, _ in spans):
            spans.append((hit[0], hit[1], n, f.get("severity", "low")))
    spans.sort()
    out, pos = [], 0
    for s, e, n, sev in spans:
        _, fg, _, hl = SEV.get(sev, SEV["low"])
        out.append(esc(text[pos:s]))
        out.append(f'<mark style="background:{hl};">{esc(text[s:e])}</mark>'
                   f'<sup style="background:{fg};">{n}</sup>')
        pos = e
    out.append(esc(text[pos:]))
    # br instead of newlines so markdown leaves it alone
    body = "".join(out).replace("\n", "<br>")
    return f'<div class="paper">{body}</div>', len(spans)


# ui
st.set_page_config(page_title="Lease Red-Flag Checker", page_icon="🏠", layout="centered")
st.markdown(CSS, unsafe_allow_html=True)
st.markdown("""<div class="hero">
  <h1>🏠 Lease Red-Flag Checker</h1>
  <p>Drop in your lease. See the clauses worth a second look, explained in plain English.</p>
  <span class="chip">✨ Powered by Gemma 4</span>
  <span class="chip">📄 PDF · photos · text</span>
  <span class="chip">⚖️ Virginia tenant law</span>
  <span class="chip">🔒 Nothing is stored</span>
</div>""", unsafe_allow_html=True)

with st.container(border=True):
    tab_up, tab_paste = st.tabs(["📄 Upload lease", "✍️ Paste text"])
    with tab_up:
        uploads = st.file_uploader("PDF or photos of your lease", type=["pdf", "png", "jpg", "jpeg"],
                                   accept_multiple_files=True, label_visibility="collapsed")
    with tab_paste:
        if st.button("✨ Try a sample lease", type="tertiary"):
            st.session_state.pasted = SAMPLE_LEASE
        pasted = st.text_area("Lease text", height=200, key="pasted", label_visibility="collapsed",
                              placeholder="Paste your lease text here...")

    ready = bool(uploads or pasted.strip())
    go = st.button("Check my lease →", type="primary", disabled=not ready, use_container_width=True)

if go:
    parts, text = [], []
    with st.status("Checking your lease...", expanded=True) as status:
        st.write("📄 Reading pages")
        for f in uploads or []:
            data = f.read()
            if f.type == "application/pdf":
                text.append(pdf_to_text(data))
                for img in pdf_to_images(data):
                    parts.append(types.Part.from_bytes(data=img, mime_type="image/png"))
            else:
                parts.append(types.Part.from_bytes(data=data, mime_type=f.type))
        if pasted.strip():
            parts.append(pasted)
            text.append(pasted)
        st.write("🧠 Gemma 4 is reviewing each clause")
        try:
            st.session_state.result = analyze(parts)
            st.session_state.lease_text = "\n\n".join(t for t in text if t.strip())
            status.update(label="Done!", state="complete", expanded=False)
        except Exception as e:
            status.update(label="Something went wrong", state="error")
            st.error(f"{e}")

result = st.session_state.get("result")
if not result:
    st.markdown("""<div class="steps">
  <div class="step"><b>1. Add your lease</b>Upload a PDF, snap photos, or paste the text.</div>
  <div class="step"><b>2. Gemma 4 reviews it</b>Each clause is checked against common tenant red flags.</div>
  <div class="step"><b>3. Know what to ask</b>Get plain-English flags and a ready-to-send email.</div>
</div>""", unsafe_allow_html=True)
else:
    flags = result.get("flags", [])
    order = {"high": 0, "medium": 1, "low": 2}
    flags.sort(key=lambda f: order.get(f.get("severity", "low"), 3))

    st.markdown(overview_card(flags, result.get("summary", "")), unsafe_allow_html=True)

    t_flags, t_lease, t_email = st.tabs([f"🚩 Flags ({len(flags)})", "📄 Highlighted lease", "✉️ Landlord email"])

    with t_flags:
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
            for n, f in shown:
                st.markdown(flag_card(n, f), unsafe_allow_html=True)

    with t_lease:
        lease_text = st.session_state.get("lease_text", "")
        if not lease_text:
            st.info("The highlighted view works with PDFs and pasted text. For photos, see the Flags tab.")
        else:
            page, found = highlighted_lease(lease_text, flags)
            st.caption(f"{found} of {len(flags)} flagged clauses highlighted. Numbers match the Flags tab.")
            st.markdown(page, unsafe_allow_html=True)

    with t_email:
        if not flags:
            st.caption("No questions needed.")
        else:
            email = build_email(flags)
            st.caption("Hover the box and click the copy icon, or download it.")
            st.code(email, language=None, wrap_lines=True)
            st.download_button("⬇️ Download as .txt", email, file_name="questions-for-landlord.txt")

st.markdown("<br>", unsafe_allow_html=True)
st.caption("Not legal advice. Built with Gemma 4 at GDG Build with AI × Hacktoberfest 2026 · Virginia Tech")
