# Evaluation results

_2026-10-24 18:43 · model `gemma-4-26b-a4b-it` · 15 leases · 87 labeled clauses · 3 run(s) per mode_

| metric | text | pdf |
|---|---|---|
| Recall on clauses that conflict with VA law | 97% (range 96%–100%) | 97% (range 96%–100%) |
| False alarms on fair clauses | 7% (range 6%–8%) | 4% (range 4%–4%) |
| Precision (flags that were real problems) | 86% (range 85%–88%) | 92% (range 92%–92%) |
| Flags with the right category | 81% (range 77%–86%) | 85% (range 82%–87%) |
| Real problems rated high severity | 85% (range 82%–91%) | 81% (range 77%–83%) |
| Flag quotes found in the lease (for highlighting) | 97% (range 94%–100%) | 98% (range 97%–100%) |

**text** (last run): caught 22 of 23 problem clauses, 4 false alarms out of 52 fair clauses, flagged 10 of 12 judgment-call clauses (not scored), 0 flags didn't match any clause.

**pdf** (last run): caught 22 of 23 problem clauses, 2 false alarms out of 52 fair clauses, flagged 11 of 12 judgment-call clauses (not scored), 0 flags didn't match any clause.

### Missed problems

- **L12**: If Tenant has a pet, Tenant shall also pay a refundable pet deposit of $500 in addition to the security deposit.

### False alarms

- **L10**: Subtenant will pay a deposit of $800, returned within 30 days after move-out.
- **L12**: Tenant shall pay a security deposit of $2,000.

Labels: `flag` = conflicts with the Virginia Residential Landlord and Tenant Act; `ok` = should not be flagged; `either` = legal but unfavorable or arguable (reported, not scored). See `eval/leases.json`. Not legal advice.
