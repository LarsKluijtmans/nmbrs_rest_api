"""Token model and durable token storage.

Nmbrs refresh tokens are single-use and rotating: every refresh returns a new one
and kills the old one. Everything here exists to make sure a rotated token is
durably persisted *before* it is used, and that two workers never refresh at once.

See ``docs/authentication.md`` for the full contract.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager, suppress
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, field_serializer

from nmbrs_rest.errors import TokenStoreError

__all__ = [
    "CallbackTokenStore",
    "FileTokenStore",
    "KeyringTokenStore",
    "MemoryTokenStore",
    "Token",
    "TokenStore",
]

#: Refresh this long before the access token actually expires, to cover a slow
#: request plus mild clock drift.
REFRESH_SKEW = timedelta(seconds=60)


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


class Token(BaseModel):
    """An OAuth token set, as persisted.

    ``expires_at`` is stored as an absolute UTC instant rather than the relative
    ``expires_in`` from the wire: recomputing a relative lifetime on load would
    silently extend it by however long the process was down.
    """

    model_config = ConfigDict(frozen=True, extra="allow")

    access_token: str
    refresh_token: str | None = None
    expires_at: datetime
    scopes: tuple[str, ...] = ()
    token_type: str = "Bearer"
    obtained_at: datetime = Field(default_factory=_utcnow)

    @field_serializer("expires_at", "obtained_at")
    def _serialize_dt(self, value: datetime) -> str:
        return value.astimezone(timezone.utc).isoformat()

    @classmethod
    def from_response(cls, payload: dict[str, Any], *, now: datetime | None = None) -> Token:
        """Build from a ``/connect/token`` response body."""
        now = now or _utcnow()
        expires_in = payload.get("expires_in", 3600)
        try:
            seconds = int(expires_in)
        except (TypeError, ValueError):
            seconds = 3600
        raw_scope = payload.get("scope") or ""
        return cls(
            access_token=str(payload["access_token"]),
            refresh_token=payload.get("refresh_token"),
            expires_at=now + timedelta(seconds=seconds),
            # The GRANTED scope, which may be narrower than what was requested.
            scopes=tuple(raw_scope.split()) if raw_scope else (),
            token_type=str(payload.get("token_type", "Bearer")),
            obtained_at=now,
        )

    @property
    def granted_scopes(self) -> frozenset[str]:
        return frozenset(self.scopes)

    def is_expired(self, *, skew: timedelta = REFRESH_SKEW, now: datetime | None = None) -> bool:
        return self.expires_at - skew <= (now or _utcnow())

    def __repr__(self) -> str:
        # Never render the secrets, not even truncated.
        return (
            f"Token(expires_at={self.expires_at.isoformat()}, "
            f"scopes={list(self.scopes)!r}, "
            f"has_refresh_token={self.refresh_token is not None})"
        )

    __str__ = __repr__


@runtime_checkable
class TokenStore(Protocol):
    """Durable storage for tokens, keyed per consented profile.

    ``save`` MUST NOT return until the write is durable. The SDK persists a rotated
    refresh token *before* using it and relies on that ordering; a store that
    buffers writes turns a crash into a permanent lockout.
    """

    def load(self, key: str) -> Token | None: ...

    def save(self, key: str, token: Token) -> None: ...

    def delete(self, key: str) -> None: ...


class MemoryTokenStore:
    """Non-durable, process-local. For tests and short-lived scripts only."""

    def __init__(self) -> None:
        self._tokens: dict[str, Token] = {}
        self._lock = threading.Lock()

    def load(self, key: str) -> Token | None:
        with self._lock:
            return self._tokens.get(key)

    def save(self, key: str, token: Token) -> None:
        with self._lock:
            self._tokens[key] = token

    def delete(self, key: str) -> None:
        with self._lock:
            self._tokens.pop(key, None)


class FileTokenStore:
    """JSON on disk. Atomic, cross-process safe, unencrypted.

    The recommended default for a single host. Writes go to a temp file in the same
    directory and are ``os.replace``d into position, so a crash mid-write leaves the
    previous good token intact rather than a truncated file.

    Does **not** encrypt. ``0600`` keeps other users on the box out; it does nothing
    against a stolen disk, a backup, or a compromised host. See ``SECURITY.md``.
    """

    def __init__(self, path: str | os.PathLike[str]) -> None:
        self.path = Path(path).expanduser()
        self._lock = threading.Lock()

    # -- locking ---------------------------------------------------------- #

    @contextmanager
    def _file_lock(self) -> Iterator[None]:
        """Advisory cross-process lock around a read-modify-write cycle.

        A threading.Lock is useless across processes, and a worker pool sharing one
        token file is the common deployment. Best-effort: if the platform call is
        unavailable we degrade to the in-process lock rather than failing.
        """
        self.path.parent.mkdir(parents=True, exist_ok=True)
        lock_path = self.path.with_suffix(self.path.suffix + ".lock")
        handle = None
        try:
            handle = open(lock_path, "a+b")  # noqa: SIM115 - released in finally
            if sys.platform == "win32":
                import msvcrt

                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            yield
        except (OSError, ImportError):
            # Degrade rather than break; the thread lock still applies.
            yield
        finally:
            if handle is not None:
                with suppress(OSError, ValueError):
                    if sys.platform == "win32":
                        import msvcrt

                        handle.seek(0)
                        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                    else:
                        import fcntl

                        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
                handle.close()

    # -- io --------------------------------------------------------------- #

    def _read_all(self) -> dict[str, Any]:
        if not self.path.exists():
            return {}
        try:
            raw = self.path.read_text(encoding="utf-8")
        except OSError as exc:
            raise TokenStoreError(f"could not read token store at {self.path}: {exc}") from exc
        if not raw.strip():
            return {}
        try:
            parsed = json.loads(raw)
        except ValueError as exc:
            raise TokenStoreError(
                f"token store at {self.path} is not valid JSON: {exc}. "
                f"If it is corrupted the refresh token is unrecoverable and the "
                f"integration must be authorized again."
            ) from exc
        return parsed if isinstance(parsed, dict) else {}

    def _write_all(self, payload: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2)
                handle.flush()
                os.fsync(handle.fileno())  # durable BEFORE the rename
            if os.name == "posix":
                os.chmod(tmp, 0o600)
            os.replace(tmp, self.path)  # atomic on POSIX and Windows
        except OSError as exc:
            with suppress(OSError):
                Path(tmp).unlink(missing_ok=True)
            raise TokenStoreError(f"could not write token store at {self.path}: {exc}") from exc

    # -- protocol --------------------------------------------------------- #

    def load(self, key: str) -> Token | None:
        with self._lock, self._file_lock():
            entry = self._read_all().get(key)
            return Token.model_validate(entry) if entry else None

    def save(self, key: str, token: Token) -> None:
        with self._lock, self._file_lock():
            data = self._read_all()
            data[key] = token.model_dump(mode="json")
            self._write_all(data)

    def delete(self, key: str) -> None:
        with self._lock, self._file_lock():
            data = self._read_all()
            if data.pop(key, None) is not None:
                self._write_all(data)


class KeyringTokenStore:
    """OS keychain storage. Encrypted at rest by the platform.

    Requires the ``keyring`` extra::

        pip install "nmbrs-rest-api[keyring]"

    Good for desktop and developer machines. Headless servers usually have no
    usable backend - use :class:`FileTokenStore` or :class:`CallbackTokenStore`.
    """

    def __init__(self, service: str = "nmbrs-rest-api") -> None:
        try:
            import keyring
        except ImportError as exc:  # pragma: no cover - depends on the extra
            raise TokenStoreError(
                "KeyringTokenStore requires the 'keyring' extra: "
                'pip install "nmbrs-rest-api[keyring]"'
            ) from exc
        self._keyring = keyring
        self.service = service

    def load(self, key: str) -> Token | None:
        raw = self._keyring.get_password(self.service, key)
        return Token.model_validate_json(raw) if raw else None

    def save(self, key: str, token: Token) -> None:
        self._keyring.set_password(self.service, key, token.model_dump_json())

    def delete(self, key: str) -> None:
        with suppress(Exception):
            self._keyring.delete_password(self.service, key)


class CallbackTokenStore:
    """Adapter for bringing your own storage - a database, Vault, Secrets Manager.

    ``save`` must be durable before it returns::

        store = CallbackTokenStore(
            load=lambda k: db.get_token(k),
            save=lambda k, t: db.put_token(k, t),
            delete=lambda k: db.drop_token(k),
        )
    """

    def __init__(
        self,
        *,
        load: Callable[[str], Token | None],
        save: Callable[[str, Token], None],
        delete: Callable[[str], None] | None = None,
    ) -> None:
        self._load = load
        self._save = save
        self._delete = delete

    def load(self, key: str) -> Token | None:
        return self._load(key)

    def save(self, key: str, token: Token) -> None:
        self._save(key, token)

    def delete(self, key: str) -> None:
        if self._delete is not None:
            self._delete(key)
