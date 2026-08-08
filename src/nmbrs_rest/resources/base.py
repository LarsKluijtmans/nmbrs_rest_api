"""Shared machinery behind the generated read methods.

One place decides how a spec path plus a handful of keyword filters becomes an
actual request: path substitution, filter normalisation, paging, per-object caching
and unwrapping the response into the value the caller asked for.
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, Any

from nmbrs_rest.pagination import Page
from nmbrs_rest.resources._generated import READS

if TYPE_CHECKING:
    from nmbrs_rest.transport import Transport

CacheKey = tuple[str, tuple[tuple[str, str], ...]]


def normalise(params: dict[str, Any]) -> dict[str, Any]:
    """Drop unset filters and render dates the way the API expects them.

    Callers pass ``date``/``datetime`` objects because that is what they have;
    the API wants ISO-8601 strings. Passing a ``date`` straight through would be
    silently serialised by httpx as ``2026-08-08`` anyway, but ``datetime`` would
    render with a space instead of ``T``, which the API rejects.
    """
    clean: dict[str, Any] = {}
    for key, value in params.items():
        if value is None:
            continue
        if isinstance(value, date):
            # datetime is a date subclass, so this covers both. date -> 2026-08-08,
            # datetime -> 2026-08-08T09:30:00; the API accepts either.
            clean[key] = value.isoformat()
        else:
            clean[key] = value
    return clean


class Resource:
    """Base for Debtor, Company and Employee.

    Caching is per object and keyed on the filter arguments, not just the endpoint:
    ``emp.salaries()`` and ``emp.salaries(created_from=...)`` are different questions
    and must not share an answer. Two identical calls make one request.
    """

    __slots__ = ("_cache", "_transport")

    def __init__(self, transport: Transport) -> None:
        self._transport = transport
        self._cache: dict[CacheKey, Any] = {}

    # -- subclass hooks ----------------------------------------------------- #

    def _path_values(self) -> dict[str, str]:
        """Values for the ``{placeholders}`` in a spec path."""
        return {}

    def _extra_params(self, template: str) -> dict[str, Any]:
        """Query parameters the resource itself contributes."""
        return {}

    def _extract(self, template: str, rows: list[dict[str, Any]]) -> Any:
        """Turn the raw row list into the value the caller wants."""
        return rows

    # -- request path ------------------------------------------------------- #

    def _cache_key(self, template: str, params: dict[str, Any]) -> CacheKey:
        return (template, tuple(sorted((k, repr(v)) for k, v in params.items())))

    def _rows(self, template: str, params: dict[str, Any]) -> Any:
        query = {**normalise(params), **self._extra_params(template)}
        key = self._cache_key(template, query)
        if key in self._cache:
            return self._cache[key]

        path = template.format(**self._path_values())
        rows = list(
            Page(
                self._transport,
                template,
                path=path,
                params=query,
                factory=lambda row: row,
            )
        )
        value = self._extract(template, rows)
        self._cache[key] = value
        return value

    # -- what the generated methods call ------------------------------------ #

    def _read_list(self, template: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        value = self._rows(template, params)
        if value is None:
            return []
        if isinstance(value, list):
            return [row for row in value if isinstance(row, dict)]
        return [value] if isinstance(value, dict) else []

    def _read_object(self, template: str, params: dict[str, Any]) -> dict[str, Any] | None:
        value = self._rows(template, params)
        if isinstance(value, list):
            value = value[0] if value else None
        return value if isinstance(value, dict) else None

    def _read_scalar(self, template: str, params: dict[str, Any]) -> Any:
        value = self._rows(template, params)
        if isinstance(value, list):
            return value[0] if value else None
        return value

    # -- cache control ------------------------------------------------------ #

    def refresh(self) -> None:
        """Forget everything cached on this object, so the next read refetches."""
        self._cache.clear()

    @property
    def cached(self) -> int:
        """How many distinct reads this object is currently holding."""
        return len(self._cache)


class EmployeeScoped(Resource):
    """A resource whose rows arrive wrapped one-per-employee.

    Employee data reached through a company comes back as
    ``{"employeeId": ..., "<payloadKey>": ...}``, one row per employee. Most of
    those endpoints accept ``?employeeId=`` so the server does the filtering;
    ``privateInfos``, ``extraFields`` and ``useraccounts`` do not, so the whole
    company is fetched and filtered here instead. Either way the caller gets their
    own employee's payload rather than a wrapper.
    """

    __slots__ = ()

    @property
    def _employee_id(self) -> str:
        raise NotImplementedError

    def _extra_params(self, template: str) -> dict[str, Any]:
        spec = READS.get(template)
        if spec is not None and spec.employee_filter:
            return {"employeeId": self._employee_id}
        return {}

    def _extract(self, template: str, rows: list[dict[str, Any]]) -> Any:
        spec = READS.get(template)
        if spec is None or spec.payload_key is None:
            return rows

        mine = [row for row in rows if row.get("employeeId") == self._employee_id]
        if not mine:
            return None
        return mine[0].get(spec.payload_key)
