"""The Company resource."""

from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING, Any

from nmbrs_rest.errors import ResourceNotFoundError
from nmbrs_rest.pagination import Page
from nmbrs_rest.resources._generated import CompanyReads
from nmbrs_rest.resources.base import Resource, normalise
from nmbrs_rest.resources.employee import Employee

if TYPE_CHECKING:
    from nmbrs_rest.transport import Transport

EMPLOYEES = "/api/companies/{companyId}/employees"


class Company(Resource, CompanyReads):
    """One company, and the way in to its employees.

    Company-level reads are methods for the same reason employee reads are - many
    of them take ``year``/``period`` - and are cached per argument set::

        company.period()                      # current payroll period
        company.wage_taxes(year=2026)
        for employee in company.employees():  # every page, eagerly
            ...
    """

    __slots__ = ("_data", "_id")

    def __init__(
        self,
        transport: Transport,
        company_id: str,
        *,
        data: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(transport)
        self._id = company_id
        self._data = data or {}

    # -- identity ----------------------------------------------------------- #

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
    def debtor_id(self) -> str | None:
        value = self._data.get("debtorId")
        return value if isinstance(value, str) else None

    @property
    def raw(self) -> dict[str, Any]:
        """The listing row this object was built from, as the API sent it."""
        return dict(self._data)

    def _path_values(self) -> dict[str, str]:
        return {"companyId": self._id}

    # -- employees ---------------------------------------------------------- #

    def employees(
        self,
        *,
        created_from: date | datetime | str | None = None,
        employee_type: str | None = None,
    ) -> list[Employee]:
        """``GET /api/companies/{companyId}/employees``

        Every page is fetched before this returns. The identity fields on each
        ``Employee`` come from this call, so reading names costs nothing extra.
        """
        return [
            Employee(
                self._transport,
                self._id,
                str(row.get("employeeId", "")),
                basic_info=row.get("employeeBasicInfo") or {},
            )
            for row in self._employee_rows(
                {"createdFrom": created_from, "employeeType": employee_type}
            )
        ]

    def employee(self, employee_id: str) -> Employee:
        """One employee by id, in a single request.

        The listing endpoint accepts ``?employeeId=``, so this does not page through
        the company. Raises ``ResourceNotFoundError`` if the employee is not in this
        company - which is also how you find out an id belongs somewhere else.
        """
        rows = self._employee_rows({"employeeId": employee_id})
        for row in rows:
            if row.get("employeeId") == employee_id:
                return Employee(
                    self._transport,
                    self._id,
                    employee_id,
                    basic_info=row.get("employeeBasicInfo") or {},
                )
        raise ResourceNotFoundError(
            http_status=404,
            detail=(
                f"employee {employee_id!r} is not in company {self._id!r}. "
                "Employee ids are only meaningful inside their owning company"
            ),
        )

    def _employee_rows(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        query = normalise(params)
        key = self._cache_key(EMPLOYEES, query)
        if key in self._cache:
            cached: list[dict[str, Any]] = self._cache[key]
            return cached

        rows = list(
            Page(
                self._transport,
                EMPLOYEES,
                path=EMPLOYEES.format(companyId=self._id),
                params=query,
                factory=lambda row: row,
            )
        )
        self._cache[key] = rows
        return rows

    def __repr__(self) -> str:
        return f"Company(id={self._id!r}, name={self.name!r})"
