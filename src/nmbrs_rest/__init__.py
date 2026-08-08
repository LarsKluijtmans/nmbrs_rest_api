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
from nmbrs_rest.client import ALL_READ_SCOPES, DEFAULT_SCOPES, Nmbrs
from nmbrs_rest.errors import (
    APIError,
    AuthenticationError,
    DataAccessError,
    IdentityServerError,
    InsufficientScopeError,
    InvalidGrantError,
    NmbrsConfigError,
    NmbrsError,
    NotAuthenticatedError,
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
from nmbrs_rest.resources import Company, Debtor, Employee
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
    "ALL_READ_SCOPES",
    "DEFAULT_SCOPES",
    "APIError",
    "AuthenticationError",
    "AuthorizationRequest",
    "CallbackTokenStore",
    "Company",
    "DataAccessError",
    "Debtor",
    "Employee",
    "FileTokenStore",
    "IdentityServerError",
    "InsufficientScopeError",
    "InvalidGrantError",
    "KeyringTokenStore",
    "MemoryTokenStore",
    "Nmbrs",
    "NmbrsConfigError",
    "NmbrsError",
    "NotAuthenticatedError",
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
