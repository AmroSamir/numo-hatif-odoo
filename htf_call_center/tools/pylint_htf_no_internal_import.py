"""Pylint plugin: enforce the htf_call_center module boundary.

Per API_CONTRACT.md, the bridge (`numo_crm_htf`) and any future consumer
MUST NOT import private internals from the vendor wrapper. They are allowed
to import:

    htf_call_center.constants
    htf_call_center.exceptions
    htf_call_center.signals          (the `htf_signals` singleton)

Everything else — especially `htf_call_center.services.*` and
`htf_call_center.models.*` — is off-limits. Use
``env['htf.config'].get_service('<name>')`` instead.

Usage:

    pylint --load-plugins=tools.pylint_htf_no_internal_import \
           extra-addons/custom/numo_crm_htf/

Run from the repo root so `tools` is importable. The checker walks every
Python file under any directory other than ``htf_call_center`` and flags any
``import`` / ``from ... import`` that crosses the boundary into an
internal module.
"""

from __future__ import annotations

import os

try:  # pragma: no cover — pylint always present in CI; optional locally
    from pylint.checkers import BaseChecker
    from pylint.interfaces import IAstroidChecker  # pylint < 3
except Exception:  # pylint missing — keep import-time clean for prod
    BaseChecker = object
    IAstroidChecker = None


_VENDOR_PKG = 'htf_call_center'
_PUBLIC_SUBMODULES = frozenset({
    'constants',
    'exceptions',
    'signals',
})


def _is_inside_vendor(file_path: str) -> bool:
    """True iff the source file lives under the htf_call_center package."""
    if not file_path:
        return False
    normalized = file_path.replace('\\', '/')
    return f'/{_VENDOR_PKG}/' in normalized or normalized.endswith(f'/{_VENDOR_PKG}')


def _violation_reason(module_name: str) -> str | None:
    """Return an explanation string if `module_name` crosses the boundary."""
    if not module_name:
        return None
    parts = module_name.split('.')
    if parts[0] != _VENDOR_PKG:
        return None
    if len(parts) == 1:
        return None  # `import htf_call_center` alone is fine
    head = parts[1]
    if head in _PUBLIC_SUBMODULES:
        return None
    return (
        f"Imports htf_call_center.{head!r} — internal API. "
        f"Use env['htf.config'].get_service('<name>') instead. "
        f"Public surface is {sorted(_PUBLIC_SUBMODULES)}."
    )


class HtfBoundaryChecker(BaseChecker):
    """Flag imports that cross the htf_call_center boundary."""

    if IAstroidChecker is not None:
        __implements__ = (IAstroidChecker,)

    name = 'htf-boundary'
    priority = -1
    msgs = {
        'C9001': (
            '%s',
            'htf-internal-import',
            'Bridge / external code must only import htf_call_center.{constants, '
            'exceptions, signals}. Everything else is internal.',
        ),
    }

    def visit_import(self, node):  # pragma: no cover — exercised in CI
        if _is_inside_vendor(getattr(node.root(), 'file', '')):
            return
        for name, _alias in node.names:
            reason = _violation_reason(name)
            if reason:
                self.add_message('htf-internal-import', node=node, args=(reason,))

    def visit_importfrom(self, node):  # pragma: no cover
        if _is_inside_vendor(getattr(node.root(), 'file', '')):
            return
        modname = node.modname or ''
        reason = _violation_reason(modname)
        if reason:
            self.add_message('htf-internal-import', node=node, args=(reason,))


def register(linter):  # pylint plugin entry point
    linter.register_checker(HtfBoundaryChecker(linter))


# ---------------------------------------------------------------------- #
# Lightweight CLI fallback for environments without pylint                #
# ---------------------------------------------------------------------- #

def _cli_scan(path: str) -> int:
    """Quick AST scan as a fallback. Returns number of violations."""
    import ast

    violations = 0
    for root, _dirs, files in os.walk(path):
        if f'/{_VENDOR_PKG}/' in root.replace('\\', '/') or root.endswith(_VENDOR_PKG):
            continue
        for fname in files:
            if not fname.endswith('.py'):
                continue
            full = os.path.join(root, fname)
            try:
                with open(full, encoding='utf-8') as fh:
                    tree = ast.parse(fh.read(), filename=full)
            except (OSError, SyntaxError):
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        reason = _violation_reason(alias.name)
                        if reason:
                            print(f'{full}:{node.lineno}: {reason}')
                            violations += 1
                elif isinstance(node, ast.ImportFrom):
                    reason = _violation_reason(node.module or '')
                    if reason:
                        print(f'{full}:{node.lineno}: {reason}')
                        violations += 1
    return violations


if __name__ == '__main__':  # pragma: no cover
    import sys
    target = sys.argv[1] if len(sys.argv) > 1 else '.'
    bad = _cli_scan(target)
    sys.exit(1 if bad else 0)
