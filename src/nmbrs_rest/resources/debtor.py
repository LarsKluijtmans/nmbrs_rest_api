"""The Debtor resource."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from nmbrs_rest.pagination import Page
from nmbrs_rest.resources._generated import DebtorReads
from nmbrs_rest.resources.base import Resource
from nmbrs_rest.resources.company import Company

if TYPE_CHECKING:
    from nmbrs_rest.transport import Transport

COMPANIES = "/api/debtors/{debtorId}/companies"


class Debtor(Resource, DebtorReads):
    """One debtor - the accounting entity a set of companies belongs to."""

    __slots__ = ("_data", "_id")

    def __init__(
        self,
        transport: Transport,
        debtor_id: str,
        *,
        data: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(transport)
        self._id = debtor_id
        self._data = data or {}

    @property
    def id(self) -> str:
        return self._id

    @property
    def name(self) -> str | None:
        value = self._data.get("name")
        return value if isinstance(value, str) else None

    @property
    def number(self) -> int | None:
        value = self._data.get("number")
        return value if isinstance(value, int) else None

    @property
    def raw(self) -> dict[str, Any]:
        """The listing row this object was built from, as the API sent it."""
        return dict(self._data)

    def _path_values(self) -> dict[str, str]:
        return {"debtorId": self._id}

    def companies(self) -> list[Company]:
        """``GET /api/debtors/{debtorId}/companies``, as Company objects."""
        key = self._cache_key(COMPANIES, {})
        if key in self._cache:
            cached: list[Company] = self._cache[key]
            return cached

        companies = [
            Company(self._transport, str(row.get("companyId", "")), data=row)
            for row in Page(
                self._transport,
                COMPANIES,
                path=COMPANIES.format(debtorId=self._id),
                params={},
                factory=lambda row: row,
            )
        ]
        self._cache[key] = companies
        return companies

    def __repr__(self) -> str:
        return f"Debtor(id={self._id!r}, name={self.name!r})"
