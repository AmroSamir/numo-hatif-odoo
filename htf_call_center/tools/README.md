# Tools

Helper scripts kept out of the Odoo runtime path.

## `pylint_htf_no_internal_import.py`

Enforces the public API contract: only `htf_call_center.constants`,
`htf_call_center.exceptions`, and `htf_call_center.signals` may be imported
by code outside the `htf_call_center` package. Everything else — services,
models, controllers — is internal.

### Run inside CI

```bash
pylint \
    --load-plugins=tools.pylint_htf_no_internal_import \
    extra-addons/custom/numo_crm_htf/
```

Run from the repository root so the `tools` package is importable. Each
violation is emitted as `C9001 / htf-internal-import`.

### Quick local scan (no pylint required)

```bash
python tools/pylint_htf_no_internal_import.py extra-addons/custom/numo_crm_htf/
```

Returns exit code 1 if any violations are printed.
