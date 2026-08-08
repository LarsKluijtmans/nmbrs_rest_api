"""Python SDK for the Nmbrs public REST API.

The public surface is documented in ``DESIGN.md``. The client and resource layers
are still being built; the authentication, error, transport and pagination layers
below are usable now.

Note the distribution is ``nmbrs-rest-api`` but the import name is ``nmbrs_rest``.
That is deliberate: the ``nmbrs`` import name belongs to the separate SOAP SDK,
and the two are designed to be installable side by side.
"""

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _installed_version

try:
    __version__ = _installed_version("nmbrs-rest-api")
except PackageNotFoundError:  # pragma: no cover - running from a source tree
    __version__ = "0.0.0"

from nmbrs_rest.auth import AuthorizationRequest, OAuth
from nmbrs_rest.errors import (
    APIError,
    AuthenticationError,
    DataAccessError,
    EmployeeResolutionError,
    IdentityServerError,
    InsufficientScopeError,
    InvalidGrantError,
    NmbrsConfigError,
    NmbrsError,
    NotFoundError,
    PermissionError,
    QuotaExceededError,
    RateLimitError,
    ReauthorizationRequired,
    ServerError,
    TokenStoreError,
    TransportError,
    ValidationError,
)
from nmbrs_rest.pagination import Page, unwrap_one
from nmbrs_rest.tokens import (
    CallbackTokenStore,
    FileTokenStore,
    KeyringTokenStore,
    MemoryTokenStore,
    Token,
    TokenStore,
)
from nmbrs_rest.transport import Transport

__all__ = [
    "APIError",
    "AuthenticationError",
    "AuthorizationRequest",
    "CallbackTokenStore",
    "DataAccessError",
    "EmployeeResolutionError",
    "FileTokenStore",
    "IdentityServerError",
    "InsufficientScopeError",
    "InvalidGrantError",
    "KeyringTokenStore",
    "MemoryTokenStore",
    "NmbrsConfigError",
    "NmbrsError",
    "NotFoundError",
    "OAuth",
    "Page",
    "PermissionError",
    "QuotaExceededError",
    "RateLimitError",
    "ReauthorizationRequired",
    "ServerError",
    "Token",
    "TokenStore",
    "TokenStoreError",
    "Transport",
    "TransportError",
    "ValidationError",
    "__version__",
    "unwrap_one",
]
