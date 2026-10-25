# Contributing

Thanks for helping renters read their leases! Contributions of every size are welcome, from fixing a typo to adding a whole new state. This project takes part in **Hacktoberfest**.

## Ways to help

- **Report a wrong flag.** Did the checker miss a problem clause, or flag something that's fine? Open a [wrong flag issue](https://github.com/shreyapbodanki/lease-red-flag-checker/issues/new?template=wrong_flag.md). Every report can become a new test case.
- **Add test leases.** The test set in [`eval/leases.json`](../eval/leases.json) is how we measure accuracy. More realistic leases make the numbers more trustworthy.
- **Add another state.** The legal facts and code links are Virginia-only right now. See [Adding a state](#adding-a-state).
- **Improve the UI or accessibility.** The app is a single Streamlit file, [`app.py`](../app.py).
- Look for issues labeled [`good first issue`](https://github.com/shreyapbodanki/lease-red-flag-checker/issues?q=is%3Aissue+is%3Aopen+label%3A%22good+first+issue%22).

## Setup

```bash
git clone https://github.com/shreyapbodanki/lease-red-flag-checker.git
cd lease-red-flag-checker
pip install -r requirements-dev.txt
```

Run the tests (no API key needed):

```bash
pytest -q
```

Run the app (needs a free key from [Google AI Studio](https://aistudio.google.com)):

```bash
export GEMINI_API_KEY="your-key"        # windows powershell: $env:GEMINI_API_KEY="your-key"
streamlit run app.py
```

Never commit your API key or a real person's lease.

## Project layout

| Path | What it is |
|---|---|
| `lease_core.py` | Everything that isn't UI: the Gemma prompt and call, retries, JSON cleanup, PDF rendering, quote matching, scoring. |
| `app.py` | The Streamlit UI: layout, styling, hover cards. |
| `eval/leases.json` | Labeled test leases. |
| `eval/run_eval.py` | Runs the model on the test leases and reports accuracy. |
| `tests/` | Unit tests for `lease_core.py` and the eval scoring. |

## Adding or fixing test cases

Each lease in `eval/leases.json` has a list of clauses. Label every clause:

- `flag`: conflicts with the Virginia Residential Landlord and Tenant Act. Put the code section in `why`, for example `"over 2 months' rent (55.1-1226)"`.
- `ok`: an ordinary clause that should **not** be flagged.
- `either`: legal but unfavorable, or arguable. These are reported but not scored, so we don't grade the model on opinions.

The `text` field is the full lease the model sees. It must contain every clause word for word, and it must **not** contain the title. Run `pytest -q` afterwards, which checks both.

Then measure the change:

```bash
python eval/run_eval.py --mode both          # needs GEMINI_API_KEY
python eval/run_eval.py --dry-run            # no key, just checks the pipeline
```

Please only cite code sections you've checked on [law.lis.virginia.gov](https://law.lis.virginia.gov/vacode/title55.1/chapter12/).

## Adding a state

1. Add the state's facts to the prompt in `lease_core.py` (deposit cap, return deadline, late fee limits, entry notice, prohibited lease terms), each with its code section.
2. Add code links in `LAWS` in `app.py`.
3. Add at least three labeled test leases for the state to `eval/leases.json`.
4. Open a PR with your eval results.

## Pull requests

- Keep PRs focused on one change.
- Make sure `pytest -q` passes. CI runs it on every PR.
- If you changed the prompt or model, include before and after numbers from `eval/run_eval.py`.
- Code comments are short and lowercase, for example `# retry when the api is busy`.

## Code of conduct

Be kind. See [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).

## Not legal advice

This tool points out clauses worth a second look. It isn't a lawyer, and contributions shouldn't present it as one.
