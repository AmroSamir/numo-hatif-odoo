# Tooling for the HTF Call Center module.
#
# Importable as a Python package so the pylint plugin can be loaded via
# `--load-plugins=tools.pylint_htf_no_internal_import` from a repo-rooted run.
#
# Standalone scripts in this package (run from the HOST, shell out to
# docker; do NOT import Odoo in-process):
#   * htf_p1_check.py / htf_p2_check.py / htf_p3_check.py / htf_p3_ui_check.py
#     / htf_p4_check.py / htf_e2e_check.py — phase-gate verification suites.
#   * replay_webhook.py / signal_smoke.py — local debugging utilities.
#   * disable_p7_discuss.py — P7 safe-revert, Tier 3 (flags off +
#     archive mirrored discuss.channels). Idempotent. Reversible.
#   * enable_p7_discuss.py — reverse of disable_p7_discuss.py.
#   * unbackfill_htf_discuss.py — P7 safe-revert, Tier 5 (DESTRUCTIVE
#     delete of mirrored mail.message rows). --dry-run by default;
#     requires explicit --commit to mutate.
#
# See htf_call_center/docs/P7_REVERT_RUNBOOK.md for the full P7
# rollback procedure and the L1..L5 escalation tiers.
