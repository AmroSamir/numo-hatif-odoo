"""Service layer for the HTF Call Center wrapper.

Services are NOT imported directly by the bridge. Instead, consumers call
`env['htf.config'].get_service('<name>')`. This module wires the registry.
"""

from . import hmac_verify
from . import auth
from . import http_client

from ..constants import SERVICE_AUTH, SERVICE_HTTP
from ..models.htf_config import register_service

register_service(SERVICE_AUTH, auth.AuthService)
register_service(SERVICE_HTTP, http_client.HtfHttpClient)
