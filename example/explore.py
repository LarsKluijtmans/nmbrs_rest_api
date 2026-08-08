"""Reading data: filters, caching, and errors worth catching.

    python explore.py

Assumes you have already run main.py once. Everything here is a read - the SDK
does not implement writes yet.
"""

from datetime import date

from global_variables import (
    client_id,
    client_secret,
    refresh_token,
    save_refresh_token,
    subscription_key,
)
from nmbrs_rest import Nmbrs
from nmbrs_rest.errors import (
    InsufficientScopeError,
    NmbrsError,
    RateLimitError,
    ResourceNotFoundError,
)

if not refresh_token:
    raise SystemExit("No NMBRS_REFRESH_TOKEN in .env yet. Run `python main.py` first.")


def rule(title: str) -> None:
    print(f"\n{title}\n{'-' * len(title)}")


with Nmbrs(
    client_id,
    client_secret,
    subscription_key,
    refresh_token=refresh_token,
    on_token_refresh=save_refresh_token,
) as api:
    # ----------------------------------------------------------------- #
    # Getting to a company
    # ----------------------------------------------------------------- #
    rule("Companies")

    # One call. If the token is consented for several debtors, /api/companies
    # refuses outright and the SDK falls back to walking debtors for you.
    companies = api.companies()
    for company in companies:
        print(f"  {company.id}  {company.name}")

    if not companies:
        raise SystemExit("This token cannot see any companies.")

    company = companies[0]

    # ----------------------------------------------------------------- #
    # Company-level reads
    # ----------------------------------------------------------------- #
    rule(f"Company: {company.name}")

    print("  current period :", company.period())
    print("  cost centers   :", len(company.cost_centers()))
    print("  hour codes     :", len(company.hour_codes()))

    # Filters are ordinary keyword arguments; pass Python dates, not strings.
    print("  wage taxes 2026:", len(company.wage_taxes(year=2026)))

    # ----------------------------------------------------------------- #
    # Employees
    # ----------------------------------------------------------------- #
    rule("Employees")

    employees = company.employees()
    print(f"  {len(employees)} in {company.name}")

    for employee in employees[:5]:
        # Name fields came with the listing, so reading them costs nothing.
        print(f"  {employee.id}  {employee.full_name}")

    if not employees:
        raise SystemExit("No employees to read.")

    employee = employees[0]

    # ----------------------------------------------------------------- #
    # Employee reads are methods, because most of them take filters
    # ----------------------------------------------------------------- #
    rule(f"Employee: {employee.full_name}")

    print("  contracts   :", len(employee.contracts()))
    print("  salaries    :", len(employee.salaries()))
    print("  addresses   :", len(employee.addresses()))
    print("  departments :", len(employee.departments()))

    # year/period where the endpoint supports it.
    print("  fixed hours :", len(employee.fixed_hours(year=2026, period=1)))

    # created_from takes a date object.
    print("  contracts since 2020:", len(employee.contracts(created_from=date(2020, 1, 1))))

    # The composite record: personalInfo, manager, department, function, address
    # in one request.
    details = employee.details()
    print("  detail keys :", sorted(details))

    # ----------------------------------------------------------------- #
    # Caching
    # ----------------------------------------------------------------- #
    rule("Caching")

    employee.refresh()  # start from a clean slate for the demonstration
    employee.contracts()  # one request
    employee.contracts()  # served from cache
    employee.contracts(created_from=date(2020, 1, 1))  # different question, own entry
    print(f"  {employee.cached} cached reads on this employee")
    print("  Same arguments are asked once; different arguments are a different question.")

    # Caching is per object, and api.company(id) hands back the same object every
    # time, so the cache survives across your own code.
    print("  same object:", api.company(company.id) is company)

    # ----------------------------------------------------------------- #
    # Errors worth catching
    # ----------------------------------------------------------------- #
    rule("Errors")

    try:
        company.employee("00000000-0000-0000-0000-000000000000")
    except ResourceNotFoundError as exc:
        print(f"  ResourceNotFoundError: {str(exc).splitlines()[0]}")

    try:
        # Needs employee.payment*; if it was not consented, the SDK names the
        # exact scope that is missing rather than saying "Forbidden".
        rate = employee.cost_per_hour(year=2026, period=1)
        print(f"  cost per hour: {rate} (employee.payment* was consented)")
    except InsufficientScopeError as exc:
        print(f"  InsufficientScopeError - missing: {', '.join(sorted(exc.missing))}")
    except RateLimitError as exc:
        print(f"  RateLimitError, retry after {exc.retry_after}s")
    except NmbrsError as exc:
        print(f"  {type(exc).__name__}: {str(exc).splitlines()[0]}")

    # ----------------------------------------------------------------- #
    # Anything the SDK does not surface
    # ----------------------------------------------------------------- #
    rule("Raw access")

    print("  company.raw :", company.raw)
    print("  employee.raw:", employee.raw)

    # And the underlying HTTP layer, for an endpoint with no method yet.
    payload = api.transport.get_json("/api/countries")
    print(f"  {len(payload.get('data', []))} countries via api.transport")
