"""The Employee resource."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from nmbrs_rest.pagination import Page
from nmbrs_rest.resources._generated import EmployeeReads
from nmbrs_rest.resources.base import EmployeeScoped

if TYPE_CHECKING:
    from nmbrs_rest.transport import Transport

DETAIL = "/api/employees/{employeeId}"


class Employee(EmployeeScoped, EmployeeReads):
    """One employee, inside one company.

    Nmbrs offers no employee-to-company lookup, so an employee is always addressed
    through the company that owns it. Reads are methods rather than attributes
    because 33 of the 38 employee endpoints take a filter - ``year``, ``period``,
    ``created_from`` - and an attribute cannot express that::

        emp.contracts()                       # one request, then cached
        emp.contracts()                       # cached
        emp.fixed_hours(year=2026, period=3)  # different question, own cache entry

    The cheap identity fields come free from the company listing; anything else is
    fetched on demand.
    """

    __slots__ = ("_basic", "_company_id", "_id")

    def __init__(
        self,
        transport: Transport,
        company_id: str,
        employee_id: str,
        *,
        basic_info: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(transport)
        self._company_id = company_id
        self._id = employee_id
        self._basic = basic_info or {}

    # -- identity ----------------------------------------------------------- #

    @property
    def id(self) -> str:
        return self._id

    @property
    def company_id(self) -> str:
        return self._company_id

    @property
    def _employee_id(self) -> str:
        return self._id

    @property
    def raw(self) -> dict[str, Any]:
        """The basic-info row this object was built from, as the API sent it."""
        return dict(self._basic)

    def _path_values(self) -> dict[str, str]:
        return {"companyId": self._company_id, "employeeId": self._id}

    # -- free fields, from the company listing ------------------------------ #

    @property
    def employee_number(self) -> int | None:
        value = self._basic.get("employeeNumber")
        return value if isinstance(value, int) else None

    @property
    def first_name(self) -> str | None:
        return self._str("firstName")

    @property
    def last_name(self) -> str | None:
        return self._str("lastName")

    @property
    def prefix(self) -> str | None:
        return self._str("prefix")

    @property
    def initials(self) -> str | None:
        return self._str("initials")

    @property
    def employee_type(self) -> str | None:
        return self._str("employeeType")

    @property
    def full_name(self) -> str:
        parts = [self.first_name, self.prefix, self.last_name]
        return " ".join(p for p in parts if p) or self._id

    def _str(self, key: str) -> str | None:
        value = self._basic.get(key)
        return value if isinstance(value, str) else None

    # -- the composite record ----------------------------------------------- #

    def details(self) -> dict[str, Any]:
        """``GET /api/employees/{employeeId}``

        Returns ``personalInfo``, ``manager``, ``department``, ``function`` and
        ``address`` in one request. Cached like every other read.
        """
        key = self._cache_key(DETAIL, {})
        if key in self._cache:
            cached: dict[str, Any] = self._cache[key]
            return cached

        rows = list(
            Page(
                self._transport,
                DETAIL,
                path=DETAIL.format(employeeId=self._id),
                params={},
                factory=lambda row: row,
            )
        )
        record = rows[0] if rows else {}
        self._cache[key] = record
        return record

    def __repr__(self) -> str:
        return (
            f"Employee(id={self._id!r}, company_id={self._company_id!r}, name={self.full_name!r})"
        )
