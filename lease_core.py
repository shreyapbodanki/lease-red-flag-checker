"""core logic for lease red-flag checker

everything here works without streamlit so it can be tested and reused:
gemma calls, json cleanup, pdf helpers, quote matching, and scoring
"""
import os
import json
import re
import time

import pymupdf
from google import genai
from google.genai import types

# gemma 4 via gemini api
MODEL = "gemma-4-26b-a4b-it"
MAX_PAGES = 8

_client = None


# only connect when we actually call gemma, so tests run without a key
def get_client():
    global _client
    if _client is None:
        _client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))
    return _client

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

Virginia facts you can rely on:
- deposits (plus insurance premiums) may not exceed two months' rent; itemized return within 45 days (Va. Code 55.1-1226, 55.1-1208)
- late fees may not exceed the lesser of 10% of periodic rent or 10% of the remaining balance (55.1-1204)
- landlord must give notice before entry except emergencies; at least 72 hours for routine maintenance the tenant did not request (55.1-1229)
- a lease cannot make the tenant waive rights, pay the landlord's attorney fees (except as the law allows), or limit the landlord's liability (55.1-1208)
- landlord must keep the unit fit and habitable and generally cannot charge the tenant for repairs the tenant did not cause (55.1-1220, 55.1-1208)
- landlords generally must try to re-rent if a tenant leaves early (duty to mitigate)

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


# hex to 0-1 rgb for pymupdf
def rgb(hex_color):
    h = hex_color.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


# try the full quote then shorter pieces until something matches
def find_in_pdf(doc, quote):
    words = re.findall(r"[\w$%.,'’-]+", quote.strip(" \"'“”.;"))
    tries = [" ".join(words)]
    for take in (10, 7, 5):
        if len(words) > take:
            tries.append(" ".join(words[:take]))
    for t in tries:
        if len(t) < 10:
            continue
        for i, page in enumerate(doc):
            if i >= MAX_PAGES:
                break
            hits = page.search_for(t)
            if hits:
                return i, hits
    return None, []


# draw colored boxes and numbers on the real pdf pages
# also returns where each box sits so the page can show hover details
def highlight_pdf(data, flags):
    doc = pymupdf.open(stream=data, filetype="pdf")
    found = 0
    hits_by_page = {}
    for n, f in enumerate(flags, 1):
        pno, hits = find_in_pdf(doc, f.get("clause_quote", ""))
        if not hits:
            continue
        found += 1
        hits_by_page.setdefault(pno, []).append((n, f, hits))
        color = rgb(SEV.get(f.get("severity", "low"), SEV["low"])[1])
        page = doc[pno]
        for r in hits:
            page.draw_rect(r + (-1, -1, 1, 1), color=color, fill=color, fill_opacity=0.28, width=0.8)
        r = hits[0]
        # badge in the left margin so it never covers words
        c = pymupdf.Point(max(min(r.x0 - 10, 34), 9), (r.y0 + r.y1) / 2)
        page.draw_circle(c, 6.5, color=color, fill=color)
        page.insert_text(c + (-2.2 if n < 10 else -4.3, 2.7), str(n), fontsize=7.5, color=(1, 1, 1),
                         fontname="helv")
    pages = []
    for i, p in enumerate(doc):
        if i >= MAX_PAGES:
            break
        # trim empty margins so the text reads bigger
        boxes = [pymupdf.Rect(bl[:4]) for bl in p.get_text("blocks")]
        clip = p.rect
        if boxes:
            area = boxes[0]
            for bx in boxes[1:]:
                area |= bx
            clip = (area + (-40, -28, 28, 28)) & p.rect
        png = p.get_pixmap(dpi=160, clip=clip).tobytes("png")
        # box positions as % of the cropped page
        spots = []
        for n, f, hits in hits_by_page.get(i, []):
            for r in hits:
                spots.append((n, f, ((r.x0 - clip.x0) / clip.width * 100, (r.y0 - clip.y0) / clip.height * 100,
                                     r.width / clip.width * 100, r.height / clip.height * 100)))
        pages.append((png, spots))
    return pages, found


# pull json out even if model wraps it in text
def parse_json(text):
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        raise


def call_gemma(parts, json_mode=True):
    config = types.GenerateContentConfig(temperature=0.2)
    if json_mode:
        config.response_mime_type = "application/json"
    resp = get_client().models.generate_content(model=MODEL, contents=parts + [PROMPT], config=config)
    return normalize(parse_json(resp.text))


def is_busy(e):
    return any(k in str(e) for k in ("429", "500", "503", "INTERNAL", "UNAVAILABLE", "RESOURCE_EXHAUSTED"))


def analyze(parts, text=""):
    # retry a few times when the api is busy
    last = None
    for attempt in range(3):
        try:
            return call_gemma(parts)
        except Exception as e:
            last = e
            if not is_busy(e):
                raise
            time.sleep(2 * (attempt + 1))
    # images keep failing so fall back to plain text
    if text.strip():
        for json_mode in (True, False):
            try:
                return call_gemma([text], json_mode=json_mode)
            except Exception as e:
                last = e
    raise last


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
        lines.append(f"{i}. {f.get('question_for_landlord', '')}")
    lines += ["", "Thanks so much!"]
    return "\n".join(lines)


# 100 = clean, each flag knocks points off
def safety_score(flags):
    cost = {"high": 18, "medium": 8, "low": 3}
    return max(5, 100 - sum(cost.get(f.get("severity", "low"), 3) for f in flags))


def score_label(score):
    if score >= 80:
        return "Looks pretty fair", "#15803d"
    if score >= 50:
        return "A few things to ask about", "#ea580c"
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

# label, solid color, soft tint (works on light and dark)
SEV = {
    "high": ("High", "#dc2626", "rgba(220,38,38,.10)", "rgba(220,38,38,.18)"),
    "medium": ("Medium", "#ea580c", "rgba(234,88,12,.10)", "rgba(234,88,12,.18)"),
    "low": ("Low", "#71717a", "rgba(113,113,122,.12)", "rgba(113,113,122,.18)"),
}


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
