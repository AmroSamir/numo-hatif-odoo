# numo_crm_htf — Bridge Module

This module is part of the htf integration project. **All planning and architecture documents live alongside the vendor wrapper:**

➡ `extra-addons/custom/htf_call_center/docs/planning/`

## Quick links
- [00_OVERVIEW.md](../../htf_call_center/docs/planning/00_OVERVIEW.md)
- [P7_CRM_ENRICHMENT.md](../../htf_call_center/docs/planning/P7_CRM_ENRICHMENT.md) — this module's primary scope
- [P5_IVR.md](../../htf_call_center/docs/planning/P5_IVR.md) — bridge wires action mapping
- [API_CONTRACT.md](../../htf_call_center/docs/planning/API_CONTRACT.md) — what this module is allowed to call
- [SIGNAL_BUS.md](../../htf_call_center/docs/planning/SIGNAL_BUS.md) — events this module subscribes to
- [STATUS.md](../../htf_call_center/docs/planning/STATUS.md)

## Dependencies
- `htf_call_center` (vendor wrapper)
- `numo_crm` (Numo CRM extension — UNTOUCHED)
- `crm` (Odoo standard)

## Hard rule
This module MUST NOT import anything under `htf_call_center.services.*`. Use `env['htf.config'].get_service('<name>')` instead. CI enforces this via pylint custom rule.
