"""Service layer for the HTF Call Center wrapper.

Services are NOT imported directly by the bridge. Instead, consumers call
`env['htf.config'].get_service('<name>')`. This module wires the registry.
"""

from . import hmac_verify
from . import auth
from . import http_client
from . import channels
from . import tags
from . import workspace
from . import contacts
from . import contact_properties
from . import dnc_listener
from . import chatter
from . import whatsapp_inbound

from ..constants import SERVICE_AUTH, SERVICE_HTTP
from ..models.htf_config import register_service

register_service(SERVICE_AUTH, auth.AuthService)
register_service(SERVICE_HTTP, http_client.HtfHttpClient)
register_service('channels', channels.ChannelService)
register_service('tags', tags.TagService)
register_service('workspace', workspace.WorkspaceService)
register_service('contacts', contacts.ContactService)
register_service('contact_properties', contact_properties.ContactPropertyService)
