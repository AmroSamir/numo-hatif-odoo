"""contact_properties service — Hatif custom contact properties.

Thin CRUD wrapper around `/v1/contact-property-definitions`. Definitions
are managed admin-side in the Hatif portal; this service is mostly used
by tests + the bridge's enrichment helpers.
"""

from __future__ import annotations

import logging

_logger = logging.getLogger(__name__)


class ContactPropertyService:
    name = 'contact_properties'

    def __init__(self, env):
        self.env = env

    def list_definitions(self) -> list:
        http = self.env['htf.config'].get_service('http')
        out = http.get('/v1/contact-property-definitions') or []
        if isinstance(out, dict) and 'items' in out:
            return list(out['items'])
        return list(out) if isinstance(out, list) else []

    def create_definition(self, payload: dict) -> dict:
        http = self.env['htf.config'].get_service('http')
        return http.post('/v1/contact-property-definitions', json_body=payload)

    def update_definition(self, definition_id: str, payload: dict) -> dict:
        http = self.env['htf.config'].get_service('http')
        return http.put(
            f'/v1/contact-property-definitions/{definition_id}',
            json_body=payload,
        )

    def delete_definition(self, definition_id: str) -> None:
        http = self.env['htf.config'].get_service('http')
        http.delete(f'/v1/contact-property-definitions/{definition_id}')
