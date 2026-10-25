"""unit tests for the non-ai parts of lease_core (no api key needed)"""
import json
import sys
from pathlib import Path

import pymupdf
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "eval"))

import lease_core  # noqa: E402
import run_eval  # noqa: E402


def make_pdf(text):
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_textbox(pymupdf.Rect(60, 60, 540, 780), text, fontsize=11, fontname="tiro")
    return doc.tobytes()


# json cleanup

def test_parse_json_plain():
    assert lease_core.parse_json('{"flags": []}') == {"flags": []}


def test_parse_json_wrapped_in_text():
    assert lease_core.parse_json('here you go:\n```json\n{"summary": "x", "flags": []}\n```') == {"summary": "x", "flags": []}


def test_parse_json_garbage_raises():
    with pytest.raises(json.JSONDecodeError):
        lease_core.parse_json("no json here")


def test_normalize_dict_fills_defaults():
    assert lease_core.normalize({}) == {"summary": "", "flags": []}


def test_normalize_wrapped_list():
    assert lease_core.normalize([{"summary": "s", "flags": [{"a": 1}]}]) == {"summary": "s", "flags": [{"a": 1}]}


def test_normalize_list_of_flags():
    out = lease_core.normalize([{"clause_quote": "x"}, "junk", {"clause_quote": "y"}])
    assert out == {"summary": "", "flags": [{"clause_quote": "x"}, {"clause_quote": "y"}]}


# finding quotes in text

def test_find_span_exact():
    text = "1. Landlord may enter the premises at any time without notice."
    s, e = lease_core.find_span(text, "Landlord may enter the premises at any time without notice")
    assert text[s:e].startswith("Landlord may enter")


def test_find_span_ignores_punctuation_and_case():
    text = "Tenant shall pay a SECURITY deposit of $4,500 before move-in."
    assert lease_core.find_span(text, "security deposit of 4 500") is not None


def test_find_span_falls_back_to_first_words():
    text = "Tenant waives all rights to request repairs and accepts the unit as-is."
    # model paraphrased the ending
    assert lease_core.find_span(text, "Tenant waives all rights to request repairs, taking the unit in its current state") is not None


def test_find_span_too_short_or_missing():
    assert lease_core.find_span("anything", "no") is None
    assert lease_core.find_span("rent is due on the first", "landlord may enter without notice") is None


# pdf highlighting

def test_highlight_pdf_finds_and_positions_boxes():
    data = make_pdf(lease_core.SAMPLE_LEASE)
    flags = [{"clause_quote": "security deposit of $4,500", "severity": "high"},
             {"clause_quote": "Landlord may enter the premises at any time without notice.", "severity": "high"},
             {"clause_quote": "this text is not in the lease at all", "severity": "low"}]
    pages, found = lease_core.highlight_pdf(data, flags)
    assert found == 2
    png, spots = pages[0]
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    assert {n for n, _, _ in spots} == {1, 2}
    for _, _, (x, y, w, h) in spots:
        assert 0 <= x <= 100 and 0 <= y <= 100 and 0 < w <= 100 and 0 < h <= 100


def test_pdf_text_and_images():
    data = make_pdf(lease_core.SAMPLE_LEASE)
    assert "SECURITY DEPOSIT" in lease_core.pdf_to_text(data)
    assert len(lease_core.pdf_to_images(data)) == 1


# scoring and email

def test_safety_score_bounds():
    assert lease_core.safety_score([]) == 100
    assert lease_core.safety_score([{"severity": "high"}] * 20) == 5
    assert lease_core.safety_score([{"severity": "medium"}]) == 92


def test_score_label_bands():
    assert lease_core.score_label(90)[0] == "Looks pretty fair"
    assert lease_core.score_label(60)[0] == "A few things to ask about"
    assert lease_core.score_label(10)[0] == "Read carefully before signing"


def test_build_email_numbers_questions():
    email = lease_core.build_email([{"question_for_landlord": "Can we lower the deposit?"}, {}])
    assert "1. Can we lower the deposit?" in email and "2. " in email


# retries and fallback (gemma is faked)

def test_analyze_retries_then_succeeds(monkeypatch):
    calls = []

    def fake(parts, json_mode=True):
        calls.append(parts)
        if len(calls) < 2:
            raise RuntimeError("503 UNAVAILABLE")
        return {"summary": "ok", "flags": []}

    monkeypatch.setattr(lease_core, "call_gemma", fake)
    monkeypatch.setattr(lease_core.time, "sleep", lambda s: None)
    assert lease_core.analyze(["lease"], "lease")["summary"] == "ok"
    assert len(calls) == 2


def test_analyze_falls_back_to_text(monkeypatch):
    def fake(parts, json_mode=True):
        if any(not isinstance(p, str) for p in parts):
            raise RuntimeError("500 INTERNAL")
        return {"summary": "from text", "flags": []}

    monkeypatch.setattr(lease_core, "call_gemma", fake)
    monkeypatch.setattr(lease_core.time, "sleep", lambda s: None)
    assert lease_core.analyze([object()], "lease text")["summary"] == "from text"


def test_analyze_does_not_retry_bad_key(monkeypatch):
    calls = []

    def fake(parts, json_mode=True):
        calls.append(1)
        raise RuntimeError("400 API key not valid")

    monkeypatch.setattr(lease_core, "call_gemma", fake)
    with pytest.raises(RuntimeError):
        lease_core.analyze(["lease"], "lease")
    assert len(calls) == 1


# test set and eval scoring

def test_test_set_is_well_formed():
    data = json.loads((ROOT / "eval" / "leases.json").read_text())
    ids = [l["id"] for l in data["leases"]]
    assert len(ids) == len(set(ids))
    for lease in data["leases"]:
        assert lease["title"] not in lease["text"]
        for cl in lease["clauses"]:
            assert cl["label"] in {"flag", "ok", "either"}
            assert cl["text"] in lease["text"]
            assert cl["why"]


def test_match_clause_and_scoring():
    lease = {"text": "1. Rent is $900.\n2. Landlord may enter at any time without notice.",
             "clauses": [{"text": "Rent is $900.", "label": "ok", "category": "other"},
                         {"text": "Landlord may enter at any time without notice.", "label": "flag", "category": "entry"}]}
    result = {"flags": [{"clause_quote": "Landlord may enter at any time", "category": "entry", "severity": "high"},
                        {"clause_quote": "something unrelated entirely", "category": "other", "severity": "low"}]}
    s = run_eval.score_lease(lease, result)
    summary = run_eval.summarize([s])
    assert summary["recall"] == 1 and summary["false_alarm_rate"] == 0
    assert summary["unmatched_flags"] == 1
