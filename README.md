# 🏠 Lease Red-Flag Checker

Upload a lease (PDF, photos, or pasted text) and get plain-English flags on clauses that may be unfair to tenants or may conflict with Virginia renter law, plus a ready-to-send email asking your landlord about each one.

Built at **GDG Build with AI × Hacktoberfest 2026** at Virginia Tech (AI for Good: Housing).

> Not legal advice. This tool points out clauses worth a second look; it doesn't replace a lawyer or your local tenant resources.

## Why

Most student renters sign leases without reading every clause, and the ones that matter (huge deposits, entry without notice, waived repairs, one-sided fees) are easy to miss. This tool makes a lease readable in under a minute.

## What it does

- Reads leases as **PDFs, phone photos, or pasted text** (multimodal: PDF pages are sent as images)
- Flags risky clauses with the **exact quote**, a **severity** (high / medium / low), and a **plain-English explanation**
- Suggests a **polite question** to ask the landlord for each flag
- Drafts a **landlord email** you can copy and edit

## Built with

- **Gemma 4** (`gemma-4-26b-a4b-it`), an open-weight model, via the Gemini API
- **Streamlit** for the UI
- **PyMuPDF** to turn PDF pages into images

## Run it locally

```bash
pip install -r requirements.txt
```

Get a free API key from [Google AI Studio](https://aistudio.google.com) and set it:

```bash
# mac / linux
export GEMINI_API_KEY="your-key"

# windows powershell
$env:GEMINI_API_KEY="your-key"
```

Then:

```bash
streamlit run app.py
```

## How it works

1. Uploaded PDFs are rendered to images (up to 8 pages); photos and pasted text are passed as-is.
2. Gemma 4 gets the lease plus a prompt describing common tenant red flags under the Virginia Residential Landlord and Tenant Act (VRLTA).
3. The model returns structured JSON (summary + flags), which the app sorts by severity and displays.

Leases are only sent to the model for analysis. The app does not store them.

## Roadmap

- Highlight flagged clauses directly on the lease pages
- Support for other states' landlord-tenant laws
- Links to local tenant resources

## License

MIT
