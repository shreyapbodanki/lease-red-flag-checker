import os
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


def build_email(flags):
    lines = ["Hi,", "",
             "Thanks for sending over the lease. Before signing, I had a few questions:", ""]
    for i, f in enumerate(flags, 1):
        lines.append(f"{i}. {f['question_for_landlord']}")
    lines += ["", "Thanks so much!"]
    return "\n".join(lines)


# ui
st.set_page_config(page_title="Lease Red-Flag Checker", page_icon="🏠", layout="centered")
st.title("🏠 Lease Red-Flag Checker")
st.caption("Upload your lease and get plain-English flags on clauses worth a second look. "
           "Not legal advice.")

uploads = st.file_uploader("Lease (PDF or photos)", type=["pdf", "png", "jpg", "jpeg"],
                           accept_multiple_files=True)
pasted = st.text_area("...or paste lease text", height=150)

if st.button("Check my lease", type="primary", disabled=not (uploads or pasted.strip())):
    parts = []
    for f in uploads or []:
        data = f.read()
        if f.type == "application/pdf":
            for img in pdf_to_images(data):
                parts.append(types.Part.from_bytes(data=img, mime_type="image/png"))
        else:
            parts.append(types.Part.from_bytes(data=data, mime_type=f.type))
    if pasted.strip():
        parts.append(pasted)

    with st.spinner("Reading your lease..."):
        try:
            st.session_state.result = analyze(parts)
        except Exception as e:
            st.error(f"Something went wrong: {e}")

result = st.session_state.get("result")
if result:
    st.subheader("Summary")
    st.write(result.get("summary", ""))

    flags = result.get("flags", [])
    order = {"high": 0, "medium": 1, "low": 2}
    flags.sort(key=lambda f: order.get(f.get("severity", "low"), 3))

    st.subheader(f"Flags ({len(flags)})")
    if not flags:
        st.success("Nothing stood out. Still read it carefully before signing!")

    icons = {"high": "🔴", "medium": "🟠", "low": "🟡"}
    for f in flags:
        sev = f.get("severity", "low")
        with st.expander(f"{icons.get(sev, '⚪')} {sev.upper()} · {f.get('category', 'other')}"):
            st.markdown(f"> {f.get('clause_quote', '')}")
            st.write(f.get("why", ""))
            st.markdown(f"**Ask your landlord:** {f.get('question_for_landlord', '')}")

    if flags:
        st.subheader("Email to your landlord")
        st.text_area("Copy and edit", build_email(flags), height=220)
