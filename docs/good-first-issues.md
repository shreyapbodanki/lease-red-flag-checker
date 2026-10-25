# Starter issues to open on GitHub

Create each one at **Issues → New issue**, then add the `good first issue` label (plus `hacktoberfest` if you like). Delete this file once they're posted, or keep it as a backlog.

---

### Add 3 more fair leases to the test set
More fair leases make the false-alarm rate more trustworthy. Add three leases to `eval/leases.json` where every clause is labeled `ok` (or `either` if arguable). Use realistic wording, like an apartment complex, a house share, or a sublease. Run `pytest -q` to validate the file.

### Add 3 leases with tricky wording to the test set
Write problem clauses in unusual or dense legal language (for example "Lessee hereby releases…" or "notwithstanding any provision of law…") so we can see whether the model still catches them. Cite the Virginia Code section in `why`.

### Spanish version of the explanations
Add a language toggle that asks Gemma to write the `why` and `question_for_landlord` fields in Spanish. Keep the clause quotes in the lease's original language so highlighting still works.

### Export results as a PDF
Add a "Download report" button that saves the score, flags, and landlord email as a PDF, so renters can bring it to a lease signing or a legal aid appointment.

### Keyboard access for hover cards
The hover cards on highlights only open on mouse hover. Make them open on keyboard focus too (`tabindex="0"` plus `:focus-within` CSS) so keyboard and screen-reader users can reach them.

### Add North Carolina landlord-tenant rules
Follow [Adding a state](../.github/CONTRIBUTING.md#adding-a-state): deposit cap, return deadline, late fee limits, entry notice, and prohibited lease terms, each with a code section and at least three test leases.

### Track eval results over time
Have `eval/run_eval.py` append a one-line summary (date, model, recall, false alarms) to `eval/history.csv`, so prompt changes can be compared.
