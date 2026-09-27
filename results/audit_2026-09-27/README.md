# Audit of 2026-09-27 (before any training)

Codex council round 4 (progress auditor, training-plan reviewer, reward-specification audit) and a
113-agent adversarial review workflow (30 findings confirmed by >=2 of 3 verifiers, 5 rejected).

Consequence: the P selection (results/p_selection_choice.json), the headline/headroom gate
(results/gate_headline.json) and the partial variance gate were produced with harness v3 defects
(contract-loading race, fault targets validated only for seed 0, contract-blind fabricated-input
check, wrong P-selection eligibility, variance-gate grouping) and are **superseded diagnostics**.
data/validity/v3.jsonl and data/contracts_v3.jsonl are kept as the v3 record (595/609 tasks).
Harness v4 and amendment A5 address the findings; every gate is re-run under v4.
