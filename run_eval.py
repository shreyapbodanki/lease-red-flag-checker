"""measure how well gemma flags problem clauses in labeled test leases

usage:
  python eval/run_eval.py                 # text mode, every lease once
  python eval/run_eval.py --mode both     # text and pdf (page images + text, like the app)
  python eval/run_eval.py --runs 3        # repeat to check consistency
  python eval/run_eval.py --dry-run       # fake model, checks the pipeline without an api key

needs GEMINI_API_KEY unless --dry-run. writes eval/results.md and eval/results.json
"""
import argparse
import json
import random
import re
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pymupdf  # noqa: E402
from google.genai import types  # noqa: E402

import lease_core  # noqa: E402

HERE = Path(__file__).resolve().parent


def words(s):
    return re.findall(r"[a-z0-9$%]+", s.lower())


# which labeled clause does a flag point at
def match_clause(quote, clauses):
    q = set(words(quote))
    if not q:
        return None
    best, best_score = None, 0.0
    for i, cl in enumerate(clauses):
        c = set(words(cl["text"]))
        score = len(q & c) / len(q)
        if score > best_score:
            best, best_score = i, score
    return best if best_score >= 0.6 else None


# lease text to a real pdf so we can test the image path too
def to_pdf(text):
    doc = pymupdf.open()
    lines = text.split("\n")
    while lines:
        page = doc.new_page()
        rect = pymupdf.Rect(60, 60, 540, 780)
        chunk = []
        while lines:
            chunk.append(lines.pop(0))
            if len(chunk) > 45:
                break
        page.insert_textbox(rect, "\n".join(chunk), fontsize=11, fontname="tiro")
    return doc.tobytes()


def parts_for(lease, mode):
    if mode == "text":
        return [lease["text"]], lease["text"]
    data = to_pdf(lease["text"])
    page_text = lease_core.pdf_to_text(data)
    parts = [types.Part.from_bytes(data=img, mime_type="image/png") for img in lease_core.pdf_to_images(data)]
    parts.append(f"Extracted text of lease.pdf:\n{page_text}")
    return parts, page_text


# pretend model for --dry-run, flags most real problems and a few wrong ones
def fake_analyze(lease, rng):
    flags = []
    for cl in lease["clauses"]:
        hit = {"flag": 0.85, "either": 0.5, "ok": 0.08}[cl["label"]]
        if rng.random() < hit:
            sev = "high" if cl["label"] == "flag" else rng.choice(["medium", "low"])
            flags.append({"clause_quote": cl["text"][: max(30, len(cl["text"]) // 2)], "category": cl["category"],
                          "severity": sev, "why": "dry run", "question_for_landlord": "dry run?"})
    return {"summary": "dry run", "flags": flags}


def score_lease(lease, result):
    clauses = lease["clauses"]
    flagged = {}
    unmatched, located = [], 0
    for f in result.get("flags", []):
        quote = f.get("clause_quote", "")
        if lease_core.find_span(lease["text"], quote):
            located += 1
        idx = match_clause(quote, clauses)
        if idx is None:
            unmatched.append(quote)
        else:
            flagged.setdefault(idx, f)
    rows = []
    for i, cl in enumerate(clauses):
        f = flagged.get(i)
        rows.append({"clause": cl["text"], "label": cl["label"], "category": cl["category"],
                     "flagged": f is not None,
                     "pred_category": (f or {}).get("category"), "pred_severity": (f or {}).get("severity")})
    return {"rows": rows, "n_flags": len(result.get("flags", [])), "unmatched": unmatched, "located": located}


def summarize(scored):
    rows = [r for s in scored for r in s["rows"]]
    must = [r for r in rows if r["label"] == "flag"]
    ok = [r for r in rows if r["label"] == "ok"]
    either = [r for r in rows if r["label"] == "either"]
    tp = sum(r["flagged"] for r in must)
    fp = sum(r["flagged"] for r in ok)
    n_flags = sum(s["n_flags"] for s in scored)
    hit_rows = [r for r in must if r["flagged"]]
    return {
        "recall": tp / len(must) if must else 0,
        "false_alarm_rate": fp / len(ok) if ok else 0,
        "precision": tp / (tp + fp) if (tp + fp) else 0,
        "tp": tp, "must": len(must), "fp": fp, "ok": len(ok),
        "either_flagged": sum(r["flagged"] for r in either), "either": len(either),
        "category_match": (sum(r["pred_category"] == r["category"] for r in hit_rows) / len(hit_rows)) if hit_rows else 0,
        "high_severity_on_hits": (sum(r["pred_severity"] == "high" for r in hit_rows) / len(hit_rows)) if hit_rows else 0,
        "quotes_located": (sum(s["located"] for s in scored) / n_flags) if n_flags else 0,
        "unmatched_flags": sum(len(s["unmatched"]) for s in scored),
        "n_flags": n_flags,
    }


def pct(x):
    return f"{x * 100:.0f}%"


def spread(vals):
    if len(vals) == 1:
        return pct(vals[0])
    return f"{pct(statistics.mean(vals))} (range {pct(min(vals))}–{pct(max(vals))})"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["text", "pdf", "both"], default="text")
    ap.add_argument("--runs", type=int, default=1)
    ap.add_argument("--leases", nargs="*", help="only these ids, e.g. L01 L11")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--sleep", type=float, default=2.0, help="seconds between calls (free tier rate limits)")
    args = ap.parse_args()

    data = json.loads((HERE / "leases.json").read_text())
    leases = [l for l in data["leases"] if not args.leases or l["id"] in args.leases]
    modes = ["text", "pdf"] if args.mode == "both" else [args.mode]
    rng = random.Random(7)

    raw, by_mode = [], {m: [] for m in modes}
    for mode in modes:
        for run in range(args.runs):
            scored = []
            for lease in leases:
                t0 = time.time()
                if args.dry_run:
                    result = fake_analyze(lease, rng)
                else:
                    parts, text = parts_for(lease, mode)
                    try:
                        result = lease_core.analyze(parts, text)
                    except Exception as e:
                        print(f"  {lease['id']} {mode} run {run + 1}: error {e}")
                        result = {"summary": "", "flags": [], "error": str(e)}
                    time.sleep(args.sleep)
                s = score_lease(lease, result)
                s["id"], s["mode"], s["run"] = lease["id"], mode, run + 1
                s["seconds"] = round(time.time() - t0, 1)
                scored.append(s)
                raw.append({"id": lease["id"], "mode": mode, "run": run + 1, "result": result, "score": s})
                caught = sum(r["flagged"] for r in s["rows"] if r["label"] == "flag")
                must = sum(r["label"] == "flag" for r in s["rows"])
                false = sum(r["flagged"] for r in s["rows"] if r["label"] == "ok")
                print(f"  {lease['id']} {mode} run {run + 1}: caught {caught}/{must}, false alarms {false}, "
                      f"{s['n_flags']} flags, {s['seconds']}s")
            by_mode[mode].append(summarize(scored))

    # write report
    total = sum(len(l["clauses"]) for l in leases)
    lines = ["# Evaluation results", "",
             f"_{datetime.now():%Y-%m-%d %H:%M} · model `{lease_core.MODEL}` · {len(leases)} leases · {total} labeled clauses · "
             f"{args.runs} run(s) per mode{' · DRY RUN (fake model)' if args.dry_run else ''}_", "",
             "| metric | " + " | ".join(modes) + " |", "|---|" + "---|" * len(modes)]
    metrics = [("Recall on clauses that conflict with VA law", "recall"),
               ("False alarms on fair clauses", "false_alarm_rate"),
               ("Precision (flags that were real problems)", "precision"),
               ("Flags with the right category", "category_match"),
               ("Real problems rated high severity", "high_severity_on_hits"),
               ("Flag quotes found in the lease (for highlighting)", "quotes_located")]
    for label, key in metrics:
        lines.append(f"| {label} | " + " | ".join(spread([s[key] for s in by_mode[m]]) for m in modes) + " |")
    for m in modes:
        s = by_mode[m][-1]
        lines.append("")
        lines.append(f"**{m}** (last run): caught {s['tp']} of {s['must']} problem clauses, "
                     f"{s['fp']} false alarms out of {s['ok']} fair clauses, flagged {s['either_flagged']} of "
                     f"{s['either']} judgment-call clauses (not scored), {s['unmatched_flags']} flags didn't match any clause.")
    misses = [(r["id"], row["clause"]) for r in raw if r["mode"] == modes[-1] and r["run"] == args.runs
              for row in r["score"]["rows"] if row["label"] == "flag" and not row["flagged"]]
    falses = [(r["id"], row["clause"]) for r in raw if r["mode"] == modes[-1] and r["run"] == args.runs
              for row in r["score"]["rows"] if row["label"] == "ok" and row["flagged"]]
    if misses:
        lines += ["", "### Missed problems", ""] + [f"- **{i}**: {c}" for i, c in misses]
    if falses:
        lines += ["", "### False alarms", ""] + [f"- **{i}**: {c}" for i, c in falses]
    lines += ["", "Labels: `flag` = conflicts with the Virginia Residential Landlord and Tenant Act; "
              "`ok` = should not be flagged; `either` = legal but unfavorable or arguable (reported, not scored). "
              "See `eval/leases.json`. Not legal advice."]
    out = "\n".join(lines) + "\n"
    # dry runs never overwrite real results
    stem = "results-dryrun" if args.dry_run else "results"
    (HERE / f"{stem}.md").write_text(out)
    (HERE / f"{stem}.json").write_text(json.dumps({"summary": by_mode, "raw": raw}, indent=1))
    print("\n" + out)


if __name__ == "__main__":
    main()
