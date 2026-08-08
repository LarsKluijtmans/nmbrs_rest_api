#!/usr/bin/env python3
"""Generate typed read methods for the resource classes from the vendored spec.

    python tools/generate_resources.py            # write
    python tools/generate_resources.py --check    # CI: fail if stale

The Nmbrs read surface is 84 GET operations and 33 of the 38 employee-facing ones
take at least one filter (``year``, ``period``, ``createdFrom``, ...). Hand-writing
that many signatures invites drift from the spec, so the mixins in
``src/nmbrs_rest/resources/_generated.py`` are derived from it.

Two spec facts drive the shape of what is emitted:

*   Employee data reached through a company comes back wrapped, one row per
    employee, as ``{"employeeId": ..., "<payloadKey>": ...}`` - and the payload key
    differs per endpoint (``contracts``, ``info``, ``EmployeeLeaveRequests``). The
    generated table records it so callers get the payload, not the wrapper.
*   Company and debtor rows are flat; the row *is* the payload.

Endpoint paths and payload keys come from the spec. Method *names* come from the
maps below, because the spec's own segments are inconsistent (``costperhour``,
``fixedWageComponents``, ``privateInfos``) and mechanical snake_casing produces a
surface nobody would design on purpose. The maps are the public API contract, so
they are human-reviewed and asserted exhaustive against the spec.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
SPEC = ROOT / "src" / "nmbrs_rest" / "_spec" / "nmbrs-openapi.yaml"
TARGET = ROOT / "src" / "nmbrs_rest" / "resources" / "_generated.py"

PAGING = {"pageNumber", "pageSize"}
WRAPPER_IDS = ("employeeId", "companyId", "debtorId")

# Query parameter -> (python name, annotation).
FILTERS: dict[str, tuple[str, str]] = {
    "createdFrom": ("created_from", "date | datetime | str | None"),
    "changedFrom": ("changed_from", "date | datetime | str | None"),
    "paymentDate": ("payment_date", "date | datetime | str | None"),
    "year": ("year", "int | None"),
    "period": ("period", "int | None"),
    "employeeType": ("employee_type", "str | None"),
    "extraFieldType": ("extra_field_type", "str | None"),
    "leaveGroupId": ("leave_group_id", "str | None"),
    "status": ("status", "str | None"),
    "type": ("request_type", "str | None"),
    "wageCodes": ("wage_codes", "str | None"),
}

SPEC_TYPE_TO_PY = {"string": "str", "integer": "int", "number": "float", "boolean": "bool"}

# --------------------------------------------------------------------------- #
# The public API contract: spec path segment -> python method name.
# --------------------------------------------------------------------------- #

EMPLOYEE_VIA_COMPANY: dict[str, str] = {
    "absences": "absences",
    "addresses": "addresses",
    "bankaccounts": "bank_accounts",
    "children": "children",
    "contracts": "contracts",
    "costcenters": "cost_centers",
    "costperhour": "cost_per_hour",
    "departments": "departments",
    "employments": "employments",
    "extraFields": "extra_fields",
    "fixedWageComponents": "fixed_wage_components",
    "functions": "functions",
    "labouragreementsettings": "labour_agreement_settings",
    "leasecars": "lease_cars",
    "leaveBalances": "leave_balances",
    "leaverequests": "leave_requests",
    "managers": "managers",
    "parentalleave": "parental_leave",
    "personalinfo": "personal_info",
    "privateInfos": "private_info",
    "salaries": "salaries",
    "schedules": "schedules",
    "svwsettings": "svw_settings",
    "useraccounts": "user_account",
    "variablewagecomponents": "variable_wage_components",
    "wagetaxsettings": "wage_tax_settings",
}

EMPLOYEE_DIRECT: dict[str, str] = {
    "annualstatement": "annual_statement",
    "documents/folders": "document_folders",
    "documents/types": "document_types",
    "fixeddays": "fixed_days",
    "fixedhours": "fixed_hours",
    "payslipperperiod": "payslips",
    "variabledays": "variable_days",
    "variablehours": "variable_hours",
}

COMPANY: dict[str, str] = {
    "addresses": "addresses",
    "bankaccounts": "bank_accounts",
    "contactpersons": "contact_persons",
    "costCenters": "cost_centers",
    "costUnits": "cost_units",
    "defaultTemplates": "default_templates",
    "extrafieldSettings": "extra_field_settings",
    "fixedwagecomponents": "fixed_wage_components",
    "hourcodes": "hour_codes",
    "leaveGroups": "leave_groups",
    "pensionexport": "pension_export",
    "period": "period",
    "salarytables": "salary_tables",
    "schedules": "schedules",
    "svwsettings": "svw_settings",
    "variablewagecomponents": "variable_wage_components",
    "wagemodels": "wage_models",
    "wagetaxes": "wage_taxes",
    "workcost": "work_cost",
}

DEBTOR: dict[str, str] = {
    "absencecasemanagers": "absence_case_managers",
    "accountantcontact": "accountant_contact",
    "departments": "departments",
    "functions": "functions",
    "managers": "managers",
    "managers/useraccounts": "manager_user_accounts",
    "tags": "tags",
}

# Handled by hand on the resource classes, or belonging to no resource.
SKIP = {
    "/api/companies",
    "/api/companies/{companyId}/employees",
    "/api/debtors",
    "/api/debtors/info",
    # Hand-written so they return Company / Employee objects rather than dicts.
    "/api/debtors/{debtorId}/companies",
    "/api/debtors/endcontractreasons/{Year}",
    "/api/employees/{employeeId}",
    "/api/countries",
    "/api/documents/{taskId}",
    "/api/salarytable/{salaryTableId}",
    "/api/subscription/{subscriptionName}/info",
    "/api/user/info",
    "/api/companies/{companyId}/salarytable/{salaryTableVersionId}/content",
    "/api/companies/{companyId}/wagetaxes/{wageTaxId}/sepa",
    "/api/companies/{companyId}/wagetaxes/{wageTaxId}/xml",
}
SKIP_PREFIX = ("/api/companies/{companyId}/runs",)


def resolve(spec: dict[str, Any], node: Any, depth: int = 0) -> Any:
    if isinstance(node, dict) and "$ref" in node and depth < 20:
        cur: Any = spec
        for part in node["$ref"].lstrip("#/").split("/"):
            cur = cur[part]
        return resolve(spec, cur, depth + 1)
    return node


def query_params(spec: dict[str, Any], item: dict[str, Any]) -> set[str]:
    raw = (item.get("parameters") or []) + (item["get"].get("parameters") or [])
    names = {p["name"] for p in (resolve(spec, x) for x in raw) if p.get("in") == "query"}
    return names - PAGING


def payload_shape(spec: dict[str, Any], item: dict[str, Any]) -> tuple[str | None, str]:
    """Return (payload_key, python return annotation) for a GET operation."""
    try:
        schema = resolve(
            spec, item["get"]["responses"]["200"]["content"]["application/json"]["schema"]
        )
        data = resolve(spec, schema["properties"]["data"])
        row = resolve(spec, data.get("items", {}))
        props = row.get("properties", {})
    except (KeyError, TypeError):
        return None, "list[dict[str, Any]]"

    keys = list(props)
    if len(keys) == 2 and keys[0] in WRAPPER_IDS:
        inner = resolve(spec, props[keys[1]])
        kind = inner.get("type")
        if kind == "array":
            return keys[1], "list[dict[str, Any]]"
        if kind == "object":
            return keys[1], "dict[str, Any] | None"
        return keys[1], f"{SPEC_TYPE_TO_PY.get(str(kind), 'Any')} | None"
    return None, "list[dict[str, Any]]"


def collect(
    spec: dict[str, Any],
) -> tuple[dict[str, list[Any]], dict[str, tuple[str | None, bool]]]:
    groups: dict[str, list[Any]] = {"EmployeeReads": [], "CompanyReads": [], "DebtorReads": []}
    table: dict[str, tuple[str | None, bool]] = {}
    seen: dict[str, set[str]] = {k: set() for k in ("emp_co", "emp", "co", "deb")}

    for path, item in spec.get("paths", {}).items():
        if "get" not in item or path in SKIP or path.startswith(SKIP_PREFIX):
            continue

        params = query_params(spec, item)
        payload_key, returns = payload_shape(spec, item)
        takes_employee_id = "employeeId" in params
        filters = sorted(params - {"employeeId"})

        target = bucket = key = None
        if path.startswith("/api/companies/{companyId}/employees/"):
            key = path.removeprefix("/api/companies/{companyId}/employees/")
            target, bucket = EMPLOYEE_VIA_COMPANY.get(key), "emp_co"
            group = "EmployeeReads"
        elif path.startswith("/api/employees/{employeeId}/"):
            key = path.removeprefix("/api/employees/{employeeId}/")
            target, bucket = EMPLOYEE_DIRECT.get(key), "emp"
            group = "EmployeeReads"
        elif path.startswith("/api/companies/{companyId}/"):
            key = path.removeprefix("/api/companies/{companyId}/")
            target, bucket = COMPANY.get(key), "co"
            group = "CompanyReads"
        elif path.startswith("/api/debtors/{debtorId}/"):
            key = path.removeprefix("/api/debtors/{debtorId}/")
            target, bucket = DEBTOR.get(key), "deb"
            group = "DebtorReads"
        else:
            continue

        if not target:
            continue
        seen[bucket].add(key)
        groups[group].append((target, path, filters, returns))
        table[path] = (payload_key, takes_employee_id)

    # A name map that has drifted from the spec is the exact failure this generator
    # exists to prevent, so refuse to emit a silently partial surface.
    for label, mapping, bucket in (
        ("EMPLOYEE_VIA_COMPANY", EMPLOYEE_VIA_COMPANY, "emp_co"),
        ("EMPLOYEE_DIRECT", EMPLOYEE_DIRECT, "emp"),
        ("COMPANY", COMPANY, "co"),
        ("DEBTOR", DEBTOR, "deb"),
    ):
        missing = set(mapping) - seen[bucket]
        if missing:
            sys.exit(f"{label} names endpoints absent from the spec: {sorted(missing)}")

    for rows in groups.values():
        rows.sort()
    return groups, table


def render_method(name: str, path: str, filters: list[str], returns: str) -> list[str]:
    out: list[str] = []
    if filters:
        out.append(f"    def {name}(")
        out.append("        self,")
        out.append("        *,")
        for raw in filters:
            if raw not in FILTERS:
                sys.exit(f"unmapped query parameter {raw!r} on {path}")
            py, annotation = FILTERS[raw]
            out.append(f"        {py}: {annotation} = None,")
        out.append(f"    ) -> {returns}:")
    else:
        out.append(f"    def {name}(self) -> {returns}:")

    out.append(f'        """``GET {path}``')
    out.append("")
    out.append(f"        Filters: {', '.join(FILTERS[f][0] for f in filters) or 'none'}")
    out.append('        """')

    if filters:
        out.append("        params: dict[str, Any] = {")
        for raw in filters:
            out.append(f'            "{raw}": {FILTERS[raw][0]},')
        out.append("        }")
    else:
        out.append("        params: dict[str, Any] = {}")

    reader = {
        "list[dict[str, Any]]": "_read_list",
        "dict[str, Any] | None": "_read_object",
    }.get(returns, "_read_scalar")
    cast_open, cast_close = ("", "")
    if reader == "_read_scalar":
        cast_open, cast_close = f"cast({returns!r}, ", ")"
    out.append(f'        return {cast_open}self.{reader}("{path}", params){cast_close}')
    out.append("")
    return out


def render(groups: dict[str, list[Any]], table: dict[str, tuple[str | None, bool]]) -> str:
    out: list[str] = [
        '"""Generated read methods. Do not edit - run tools/generate_resources.py."""',
        "",
        "from __future__ import annotations",
        "",
        "from datetime import date, datetime",
        "from typing import Any, Final, NamedTuple, cast",
        "",
        "",
        "class ReadSpec(NamedTuple):",
        '    """How to turn one endpoint\'s response into the value a caller wants."""',
        "",
        "    payload_key: str | None",
        '    """Employee rows arrive as ``{"employeeId": ..., "<payload_key>": ...}``."""',
        "",
        "    employee_filter: bool",
        '    """Whether the endpoint accepts ``?employeeId=``; if not, filter client-side."""',
        "",
        "",
        "READS: Final[dict[str, ReadSpec]] = {",
    ]
    for path in sorted(table):
        payload_key, takes = table[path]
        key_repr = "None" if payload_key is None else f'"{payload_key}"'
        out.append(f'    "{path}": ReadSpec({key_repr}, {takes}),')
    out.append("}")
    out.append("")

    docs = {
        "EmployeeReads": "employee",
        "CompanyReads": "company",
        "DebtorReads": "debtor",
    }
    for cls, rows in groups.items():
        out.append("")
        out.append(f"class {cls}:")
        out.append(f'    """Generated {docs[cls]} reads. Mixed into the resource class."""')
        out.append("")
        # Declared here so the generated file stands alone and type-checks; the
        # concrete resource class comes first in the MRO and supplies the real one.
        args = "self, template: str, params: dict[str, Any]"
        for reader, returns in (
            ("_read_list", "list[dict[str, Any]]"),
            ("_read_object", "dict[str, Any] | None"),
            ("_read_scalar", "Any"),
        ):
            out.append(f"    def {reader}(")
            out.append(f"        {args}")
            out.append(f"    ) -> {returns}:")
            out.append("        raise NotImplementedError")
            out.append("")
        for name, path, filters, returns in rows:
            out.extend(render_method(name, path, filters, returns))
    return "\n".join(out).rstrip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    spec = yaml.safe_load(SPEC.read_text(encoding="utf-8"))
    groups, table = collect(spec)
    rendered = render(groups, table)
    total = sum(len(v) for v in groups.values())

    if args.check:
        current = TARGET.read_text(encoding="utf-8") if TARGET.exists() else ""
        if current != rendered:
            sys.exit("resources/_generated.py is stale; run tools/generate_resources.py")
        print(f"up to date ({total} read methods)")
        return 0

    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(rendered, encoding="utf-8")
    for cls, rows in groups.items():
        print(f"  {cls}: {len(rows)}")
    print(f"wrote {TARGET.relative_to(ROOT)} ({total} read methods)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
