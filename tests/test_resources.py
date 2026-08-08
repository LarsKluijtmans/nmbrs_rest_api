"""Resource reads: unwrapping, filtering, caching."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

import httpx
import pytest

from nmbrs_rest.resources import Company, Debtor, Employee
from nmbrs_rest.resources._generated import (
    READS,
    CompanyReads,
    DebtorReads,
    EmployeeReads,
)
from nmbrs_rest.tokens import Token
from nmbrs_rest.transport import Transport
from tests.helpers import SUBSCRIPTION_KEY, make_token


class Server:
    """Records every request and replies with whatever the test queued."""

    def __init__(self, rows: list[dict[str, Any]] | None = None) -> None:
        self.rows = rows if rows is not None else []
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return httpx.Response(200, json={"data": self.rows})

    @property
    def paths(self) -> list[str]:
        return [r.url.path for r in self.requests]

    @property
    def params(self) -> list[dict[str, str]]:
        return [dict(r.url.params) for r in self.requests]

    def __len__(self) -> int:
        return len(self.requests)


def transport_for(server: Server, token: Token | None = None) -> Transport:
    return Transport(
        subscription_key=SUBSCRIPTION_KEY,
        token=token or make_token(),
        http_client=httpx.Client(transport=httpx.MockTransport(server)),
    )


def employee(server: Server, **kwargs: Any) -> Employee:
    return Employee(transport_for(server), "c-1", "e-1", **kwargs)


# --------------------------------------------------------------------------- #
# Unwrapping the per-employee wrapper
# --------------------------------------------------------------------------- #


def test_a_list_payload_is_unwrapped_from_the_employee_row() -> None:
    """The caller asked for contracts, not for {employeeId, contracts}."""
    server = Server([{"employeeId": "e-1", "contracts": [{"contractId": "k-1"}]}])
    assert employee(server).contracts() == [{"contractId": "k-1"}]


def test_the_employee_id_filter_is_sent_when_the_endpoint_supports_it() -> None:
    server = Server([{"employeeId": "e-1", "contracts": []}])
    employee(server).contracts()

    assert server.paths == ["/api/companies/c-1/employees/contracts"]
    assert server.params[0]["employeeId"] == "e-1"


def test_other_employees_rows_are_never_returned() -> None:
    """privateInfos has no employeeId filter, so the whole company comes back."""
    assert READS["/api/companies/{companyId}/employees/privateInfos"].employee_filter is False

    server = Server(
        [
            {"employeeId": "e-0", "privateInfos": [{"phone": "not-yours"}]},
            {"employeeId": "e-1", "privateInfos": [{"phone": "yours"}]},
            {"employeeId": "e-2", "privateInfos": [{"phone": "also-not-yours"}]},
        ]
    )
    assert employee(server).private_info() == [{"phone": "yours"}]
    assert "employeeId" not in server.params[0]


def test_an_employee_with_no_row_reads_as_empty_not_as_someone_else() -> None:
    server = Server([{"employeeId": "e-99", "privateInfos": [{"phone": "theirs"}]}])
    assert employee(server).private_info() == []


def test_an_object_payload_comes_back_as_one_object() -> None:
    server = Server([{"employeeId": "e-1", "userAccount": {"email": "ada@example.com"}}])
    assert employee(server).user_account() == {"email": "ada@example.com"}


def test_a_scalar_payload_comes_back_as_a_scalar() -> None:
    server = Server([{"employeeId": "e-1", "costPerHour": "42.50"}])
    assert employee(server).cost_per_hour(year=2026, period=3) == "42.50"


def test_employee_keyed_endpoints_return_rows_directly() -> None:
    """/api/employees/{id}/... is not wrapped, so nothing should be unwrapped."""
    server = Server([{"hourComponentId": "h-1", "hours": 8}])
    assert employee(server).fixed_hours(year=2026, period=3) == [
        {"hourComponentId": "h-1", "hours": 8}
    ]
    assert server.paths == ["/api/employees/e-1/fixedhours"]
    assert "employeeId" not in server.params[0]


def test_details_returns_the_composite_record() -> None:
    server = Server([{"employeeId": "e-1", "personalInfo": {"firstName": "Ada"}}])
    record = employee(server).details()
    assert record["personalInfo"]["firstName"] == "Ada"
    assert server.paths == ["/api/employees/e-1"]


# --------------------------------------------------------------------------- #
# Filters
# --------------------------------------------------------------------------- #


def test_unset_filters_are_not_sent() -> None:
    server = Server([{"employeeId": "e-1", "contracts": []}])
    employee(server).contracts()
    assert set(server.params[0]) <= {"employeeId", "pageNumber", "pageSize"}


def test_dates_are_sent_as_iso_8601() -> None:
    server = Server([{"employeeId": "e-1", "contracts": []}])
    employee(server).contracts(created_from=date(2026, 1, 31))
    assert server.params[0]["createdFrom"] == "2026-01-31"


def test_datetimes_keep_the_t_separator() -> None:
    """str(datetime) uses a space, which the API rejects."""
    server = Server([{"employeeId": "e-1", "contracts": []}])
    employee(server).contracts(created_from=datetime(2026, 1, 31, 9, 30))
    assert server.params[0]["createdFrom"] == "2026-01-31T09:30:00"


def test_python_names_map_back_to_the_spec_parameter_names() -> None:
    """`request_type` exists only because `type` shadows a builtin."""
    server = Server([{"employeeId": "e-1", "EmployeeLeaveRequests": []}])
    employee(server).leave_requests(request_type="Holiday", status="Approved", year=2026)

    sent = server.params[0]
    assert sent["type"] == "Holiday"
    assert sent["status"] == "Approved"
    assert sent["year"] == "2026"


# --------------------------------------------------------------------------- #
# Caching
# --------------------------------------------------------------------------- #


def test_the_same_read_twice_makes_one_request() -> None:
    server = Server([{"employeeId": "e-1", "contracts": [{"contractId": "k-1"}]}])
    emp = employee(server)

    first, second = emp.contracts(), emp.contracts()

    assert first == second
    assert len(server) == 1


def test_different_filters_are_different_questions() -> None:
    server = Server([{"employeeId": "e-1", "contracts": []}])
    emp = employee(server)

    emp.contracts()
    emp.contracts(created_from=date(2026, 1, 1))
    emp.contracts()

    assert len(server) == 2, "the filtered read must not be served from the unfiltered cache"


def test_refresh_forgets_everything() -> None:
    server = Server([{"employeeId": "e-1", "contracts": []}])
    emp = employee(server)

    emp.contracts()
    assert emp.cached == 1
    emp.refresh()
    assert emp.cached == 0
    emp.contracts()

    assert len(server) == 2


def test_caching_is_per_object_not_global() -> None:
    server = Server([{"employeeId": "e-1", "contracts": []}])
    tr = transport_for(server)

    Employee(tr, "c-1", "e-1").contracts()
    Employee(tr, "c-1", "e-1").contracts()

    assert len(server) == 2


# --------------------------------------------------------------------------- #
# Company and debtor
# --------------------------------------------------------------------------- #


def test_company_reads_are_flat() -> None:
    server = Server([{"period": 8, "periodType": "Month", "displayPeriod": "2026-08"}])
    company = Company(transport_for(server), "c-1")

    assert company.period() == [{"period": 8, "periodType": "Month", "displayPeriod": "2026-08"}]
    assert server.paths == ["/api/companies/c-1/period"]


def test_company_filters_reach_the_query_string() -> None:
    server = Server([])
    Company(transport_for(server), "c-1").wage_taxes(year=2026)
    assert server.params[0]["year"] == "2026"


def test_debtor_companies_come_back_as_company_objects() -> None:
    server = Server([{"companyId": "c-7", "name": "Sub Co", "debtorId": "d-1"}])
    companies = Debtor(transport_for(server), "d-1").companies()

    assert [type(c) for c in companies] == [Company]
    assert companies[0].id == "c-7"
    assert companies[0].name == "Sub Co"
    assert server.paths == ["/api/debtors/d-1/companies"]


def test_debtor_reads_are_flat() -> None:
    server = Server([{"tagNumber": 1, "description": "Payroll"}])
    assert Debtor(transport_for(server), "d-1").tags() == [
        {"tagNumber": 1, "description": "Payroll"}
    ]


# --------------------------------------------------------------------------- #
# The generated surface itself
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("cls", "name"),
    [
        (Employee, "contracts"),
        (Employee, "salaries"),
        (Employee, "leave_requests"),
        (Employee, "fixed_hours"),
        (Employee, "annual_statement"),
        (Company, "period"),
        (Company, "wage_taxes"),
        (Company, "leave_groups"),
        (Debtor, "managers"),
        (Debtor, "tags"),
    ],
)
def test_the_documented_methods_exist(cls: type, name: str) -> None:
    assert callable(getattr(cls, name))


def test_every_generated_template_is_in_the_read_table() -> None:
    """A method whose template is missing would silently skip unwrapping."""
    import inspect

    from nmbrs_rest.resources import _generated

    source = inspect.getsource(_generated)
    for template in READS:
        assert f'"{template}"' in source


def generated_methods(mixin: type) -> list[str]:
    return sorted(
        name for name, value in vars(mixin).items() if not name.startswith("_") and callable(value)
    )


def build_resource(cls: type, server: Server) -> Any:
    transport = transport_for(server)
    if cls is Employee:
        return Employee(transport, "c-1", "e-1")
    if cls is Company:
        return Company(transport, "c-1")
    return Debtor(transport, "d-1")


@pytest.mark.parametrize(
    ("mixin", "cls"),
    [(EmployeeReads, Employee), (CompanyReads, Company), (DebtorReads, Debtor)],
)
def test_every_generated_method_issues_a_fully_substituted_request(mixin: type, cls: type) -> None:
    """Calls all 60 of them.

    A template whose placeholders do not match what the resource supplies would
    otherwise only fail in production, as a request to a literal
    ``/api/companies/{companyId}/...`` path.
    """
    names = generated_methods(mixin)
    assert names, f"{mixin.__name__} generated nothing"

    for name in names:
        server = Server([])
        getattr(build_resource(cls, server), name)()

        assert len(server) == 1, f"{cls.__name__}.{name}() made {len(server)} requests"
        path = server.paths[0]
        assert "{" not in path and "}" not in path, (
            f"{cls.__name__}.{name}() requested an unsubstituted path: {path}"
        )
        assert path.startswith("/api/"), f"{cls.__name__}.{name}() built {path}"


def test_the_generated_surface_is_the_expected_size() -> None:
    counts = {
        "EmployeeReads": len(generated_methods(EmployeeReads)),
        "CompanyReads": len(generated_methods(CompanyReads)),
        "DebtorReads": len(generated_methods(DebtorReads)),
    }
    assert counts == {"EmployeeReads": 34, "CompanyReads": 19, "DebtorReads": 7}
