"""Generated read methods. Do not edit - run tools/generate_resources.py."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Final, NamedTuple, cast


class ReadSpec(NamedTuple):
    """How to turn one endpoint's response into the value a caller wants."""

    payload_key: str | None
    """Employee rows arrive as ``{"employeeId": ..., "<payload_key>": ...}``."""

    employee_filter: bool
    """Whether the endpoint accepts ``?employeeId=``; if not, filter client-side."""


READS: Final[dict[str, ReadSpec]] = {
    "/api/companies/{companyId}/addresses": ReadSpec(None, False),
    "/api/companies/{companyId}/bankaccounts": ReadSpec(None, False),
    "/api/companies/{companyId}/contactpersons": ReadSpec(None, False),
    "/api/companies/{companyId}/costCenters": ReadSpec(None, False),
    "/api/companies/{companyId}/costUnits": ReadSpec(None, False),
    "/api/companies/{companyId}/defaultTemplates": ReadSpec(None, False),
    "/api/companies/{companyId}/employees/absences": ReadSpec("employeeAbsenceDossiers", True),
    "/api/companies/{companyId}/employees/addresses": ReadSpec("addresses", True),
    "/api/companies/{companyId}/employees/bankaccounts": ReadSpec("bankAccounts", True),
    "/api/companies/{companyId}/employees/children": ReadSpec("children", True),
    "/api/companies/{companyId}/employees/contracts": ReadSpec("contracts", True),
    "/api/companies/{companyId}/employees/costcenters": ReadSpec("employeeCostCenters", True),
    "/api/companies/{companyId}/employees/costperhour": ReadSpec("costPerHour", True),
    "/api/companies/{companyId}/employees/departments": ReadSpec("departments", True),
    "/api/companies/{companyId}/employees/employments": ReadSpec("employments", True),
    "/api/companies/{companyId}/employees/extraFields": ReadSpec("extraFields", False),
    "/api/companies/{companyId}/employees/fixedWageComponents": ReadSpec("fixedWageComponents", True),
    "/api/companies/{companyId}/employees/functions": ReadSpec("functions", True),
    "/api/companies/{companyId}/employees/labouragreementsettings": ReadSpec("labourAgreementSettings", True),
    "/api/companies/{companyId}/employees/leasecars": ReadSpec("leaseCars", True),
    "/api/companies/{companyId}/employees/leaveBalances": ReadSpec("leaveBalances", True),
    "/api/companies/{companyId}/employees/leaverequests": ReadSpec("EmployeeLeaveRequests", True),
    "/api/companies/{companyId}/employees/managers": ReadSpec("managers", True),
    "/api/companies/{companyId}/employees/parentalleave": ReadSpec("EmployeeParentalLeaves", True),
    "/api/companies/{companyId}/employees/personalinfo": ReadSpec("info", True),
    "/api/companies/{companyId}/employees/privateInfos": ReadSpec("privateInfos", False),
    "/api/companies/{companyId}/employees/salaries": ReadSpec("salaries", True),
    "/api/companies/{companyId}/employees/schedules": ReadSpec("schedules", True),
    "/api/companies/{companyId}/employees/svwsettings": ReadSpec("employeeSVWSettings", True),
    "/api/companies/{companyId}/employees/useraccounts": ReadSpec("userAccount", False),
    "/api/companies/{companyId}/employees/variablewagecomponents": ReadSpec("variablewagecomponents", True),
    "/api/companies/{companyId}/employees/wagetaxsettings": ReadSpec("wageTaxSettings", True),
    "/api/companies/{companyId}/extrafieldSettings": ReadSpec(None, False),
    "/api/companies/{companyId}/fixedwagecomponents": ReadSpec(None, False),
    "/api/companies/{companyId}/hourcodes": ReadSpec(None, False),
    "/api/companies/{companyId}/leaveGroups": ReadSpec(None, False),
    "/api/companies/{companyId}/pensionexport": ReadSpec(None, False),
    "/api/companies/{companyId}/period": ReadSpec(None, False),
    "/api/companies/{companyId}/salarytables": ReadSpec(None, False),
    "/api/companies/{companyId}/schedules": ReadSpec(None, False),
    "/api/companies/{companyId}/svwsettings": ReadSpec(None, False),
    "/api/companies/{companyId}/variablewagecomponents": ReadSpec(None, False),
    "/api/companies/{companyId}/wagemodels": ReadSpec(None, False),
    "/api/companies/{companyId}/wagetaxes": ReadSpec(None, False),
    "/api/companies/{companyId}/workcost": ReadSpec(None, False),
    "/api/debtors/{debtorId}/absencecasemanagers": ReadSpec(None, False),
    "/api/debtors/{debtorId}/accountantcontact": ReadSpec(None, False),
    "/api/debtors/{debtorId}/departments": ReadSpec(None, False),
    "/api/debtors/{debtorId}/functions": ReadSpec(None, False),
    "/api/debtors/{debtorId}/managers": ReadSpec(None, False),
    "/api/debtors/{debtorId}/managers/useraccounts": ReadSpec(None, False),
    "/api/debtors/{debtorId}/tags": ReadSpec(None, False),
    "/api/employees/{employeeId}/annualstatement": ReadSpec(None, False),
    "/api/employees/{employeeId}/documents/folders": ReadSpec(None, False),
    "/api/employees/{employeeId}/documents/types": ReadSpec(None, False),
    "/api/employees/{employeeId}/fixeddays": ReadSpec(None, False),
    "/api/employees/{employeeId}/fixedhours": ReadSpec(None, False),
    "/api/employees/{employeeId}/payslipperperiod": ReadSpec(None, False),
    "/api/employees/{employeeId}/variabledays": ReadSpec(None, False),
    "/api/employees/{employeeId}/variablehours": ReadSpec(None, False),
}


class EmployeeReads:
    """Generated employee reads. Mixed into the resource class."""

    def _read_list(
        self, template: str, params: dict[str, Any]
    ) -> list[dict[str, Any]]:
        raise NotImplementedError

    def _read_object(
        self, template: str, params: dict[str, Any]
    ) -> dict[str, Any] | None:
        raise NotImplementedError

    def _read_scalar(
        self, template: str, params: dict[str, Any]
    ) -> Any:
        raise NotImplementedError

    def absences(
        self,
        *,
        changed_from: date | datetime | str | None = None,
        created_from: date | datetime | str | None = None,
    ) -> list[dict[str, Any]]:
        """``GET /api/companies/{companyId}/employees/absences``

        Filters: changed_from, created_from
        """
        params: dict[str, Any] = {
            "changedFrom": changed_from,
            "createdFrom": created_from,
        }
        return self._read_list("/api/companies/{companyId}/employees/absences", params)

    def addresses(
        self,
        *,
        created_from: date | datetime | str | None = None,
    ) -> list[dict[str, Any]]:
        """``GET /api/companies/{companyId}/employees/addresses``

        Filters: created_from
        """
        params: dict[str, Any] = {
            "createdFrom": created_from,
        }
        return self._read_list("/api/companies/{companyId}/employees/addresses", params)

    def annual_statement(
        self,
        *,
        year: int | None = None,
    ) -> list[dict[str, Any]]:
        """``GET /api/employees/{employeeId}/annualstatement``

        Filters: year
        """
        params: dict[str, Any] = {
            "year": year,
        }
        return self._read_list("/api/employees/{employeeId}/annualstatement", params)

    def bank_accounts(
        self,
        *,
        created_from: date | datetime | str | None = None,
    ) -> list[dict[str, Any]]:
        """``GET /api/companies/{companyId}/employees/bankaccounts``

        Filters: created_from
        """
        params: dict[str, Any] = {
            "createdFrom": created_from,
        }
        return self._read_list("/api/companies/{companyId}/employees/bankaccounts", params)

    def children(self) -> list[dict[str, Any]]:
        """``GET /api/companies/{companyId}/employees/children``

        Filters: none
        """
        params: dict[str, Any] = {}
        return self._read_list("/api/companies/{companyId}/employees/children", params)

    def contracts(
        self,
        *,
        created_from: date | datetime | str | None = None,
    ) -> list[dict[str, Any]]:
        """``GET /api/companies/{companyId}/employees/contracts``

        Filters: created_from
        """
        params: dict[str, Any] = {
            "createdFrom": created_from,
        }
        return self._read_list("/api/companies/{companyId}/employees/contracts", params)

    def cost_centers(
        self,
        *,
        created_from: date | datetime | str | None = None,
    ) -> list[dict[str, Any]]:
        """``GET /api/companies/{companyId}/employees/costcenters``

        Filters: created_from
        """
        params: dict[str, Any] = {
            "createdFrom": created_from,
        }
        return self._read_list("/api/companies/{companyId}/employees/costcenters", params)

    def cost_per_hour(
        self,
        *,
        period: int | None = None,
        year: int | None = None,
    ) -> str | None:
        """``GET /api/companies/{companyId}/employees/costperhour``

        Filters: period, year
        """
        params: dict[str, Any] = {
            "period": period,
            "year": year,
        }
        return cast('str | None', self._read_scalar("/api/companies/{companyId}/employees/costperhour", params))

    def departments(
        self,
        *,
        created_from: date | datetime | str | None = None,
    ) -> list[dict[str, Any]]:
        """``GET /api/companies/{companyId}/employees/departments``

        Filters: created_from
        """
        params: dict[str, Any] = {
            "createdFrom": created_from,
        }
        return self._read_list("/api/companies/{companyId}/employees/departments", params)

    def document_folders(self) -> list[dict[str, Any]]:
        """``GET /api/employees/{employeeId}/documents/folders``

        Filters: none
        """
        params: dict[str, Any] = {}
        return self._read_list("/api/employees/{employeeId}/documents/folders", params)

    def document_types(self) -> list[dict[str, Any]]:
        """``GET /api/employees/{employeeId}/documents/types``

        Filters: none
        """
        params: dict[str, Any] = {}
        return self._read_list("/api/employees/{employeeId}/documents/types", params)

    def employments(
        self,
        *,
        changed_from: date | datetime | str | None = None,
        created_from: date | datetime | str | None = None,
    ) -> list[dict[str, Any]]:
        """``GET /api/companies/{companyId}/employees/employments``

        Filters: changed_from, created_from
        """
        params: dict[str, Any] = {
            "changedFrom": changed_from,
            "createdFrom": created_from,
        }
        return self._read_list("/api/companies/{companyId}/employees/employments", params)

    def extra_fields(
        self,
        *,
        extra_field_type: str | None = None,
    ) -> list[dict[str, Any]]:
        """``GET /api/companies/{companyId}/employees/extraFields``

        Filters: extra_field_type
        """
        params: dict[str, Any] = {
            "extraFieldType": extra_field_type,
        }
        return self._read_list("/api/companies/{companyId}/employees/extraFields", params)

    def fixed_days(
        self,
        *,
        period: int | None = None,
        year: int | None = None,
    ) -> list[dict[str, Any]]:
        """``GET /api/employees/{employeeId}/fixeddays``

        Filters: period, year
        """
        params: dict[str, Any] = {
            "period": period,
            "year": year,
        }
        return self._read_list("/api/employees/{employeeId}/fixeddays", params)

    def fixed_hours(
        self,
        *,
        created_from: date | datetime | str | None = None,
        period: int | None = None,
        year: int | None = None,
    ) -> list[dict[str, Any]]:
        """``GET /api/employees/{employeeId}/fixedhours``

        Filters: created_from, period, year
        """
        params: dict[str, Any] = {
            "createdFrom": created_from,
            "period": period,
            "year": year,
        }
        return self._read_list("/api/employees/{employeeId}/fixedhours", params)

    def fixed_wage_components(
        self,
        *,
        created_from: date | datetime | str | None = None,
        period: int | None = None,
        year: int | None = None,
    ) -> list[dict[str, Any]]:
        """``GET /api/companies/{companyId}/employees/fixedWageComponents``

        Filters: created_from, period, year
        """
        params: dict[str, Any] = {
            "createdFrom": created_from,
            "period": period,
            "year": year,
        }
        return self._read_list("/api/companies/{companyId}/employees/fixedWageComponents", params)

    def functions(
        self,
        *,
        created_from: date | datetime | str | None = None,
    ) -> list[dict[str, Any]]:
        """``GET /api/companies/{companyId}/employees/functions``

        Filters: created_from
        """
        params: dict[str, Any] = {
            "createdFrom": created_from,
        }
        return self._read_list("/api/companies/{companyId}/employees/functions", params)

    def labour_agreement_settings(
        self,
        *,
        created_from: date | datetime | str | None = None,
    ) -> list[dict[str, Any]]:
        """``GET /api/companies/{companyId}/employees/labouragreementsettings``

        Filters: created_from
        """
        params: dict[str, Any] = {
            "createdFrom": created_from,
        }
        return self._read_list("/api/companies/{companyId}/employees/labouragreementsettings", params)

    def lease_cars(
        self,
        *,
        changed_from: date | datetime | str | None = None,
        created_from: date | datetime | str | None = None,
    ) -> list[dict[str, Any]]:
        """``GET /api/companies/{companyId}/employees/leasecars``

        Filters: changed_from, created_from
        """
        params: dict[str, Any] = {
            "changedFrom": changed_from,
            "createdFrom": created_from,
        }
        return self._read_list("/api/companies/{companyId}/employees/leasecars", params)

    def leave_balances(
        self,
        *,
        leave_group_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """``GET /api/companies/{companyId}/employees/leaveBalances``

        Filters: leave_group_id
        """
        params: dict[str, Any] = {
            "leaveGroupId": leave_group_id,
        }
        return self._read_list("/api/companies/{companyId}/employees/leaveBalances", params)

    def leave_requests(
        self,
        *,
        changed_from: date | datetime | str | None = None,
        leave_group_id: str | None = None,
        status: str | None = None,
        request_type: str | None = None,
        year: int | None = None,
    ) -> list[dict[str, Any]]:
        """``GET /api/companies/{companyId}/employees/leaverequests``

        Filters: changed_from, leave_group_id, status, request_type, year
        """
        params: dict[str, Any] = {
            "changedFrom": changed_from,
            "leaveGroupId": leave_group_id,
            "status": status,
            "type": request_type,
            "year": year,
        }
        return self._read_list("/api/companies/{companyId}/employees/leaverequests", params)

    def managers(
        self,
        *,
        created_from: date | datetime | str | None = None,
    ) -> list[dict[str, Any]]:
        """``GET /api/companies/{companyId}/employees/managers``

        Filters: created_from
        """
        params: dict[str, Any] = {
            "createdFrom": created_from,
        }
        return self._read_list("/api/companies/{companyId}/employees/managers", params)

    def parental_leave(
        self,
        *,
        created_from: date | datetime | str | None = None,
        year: int | None = None,
    ) -> list[dict[str, Any]]:
        """``GET /api/companies/{companyId}/employees/parentalleave``

        Filters: created_from, year
        """
        params: dict[str, Any] = {
            "createdFrom": created_from,
            "year": year,
        }
        return self._read_list("/api/companies/{companyId}/employees/parentalleave", params)

    def payslips(
        self,
        *,
        period: int | None = None,
        year: int | None = None,
    ) -> list[dict[str, Any]]:
        """``GET /api/employees/{employeeId}/payslipperperiod``

        Filters: period, year
        """
        params: dict[str, Any] = {
            "period": period,
            "year": year,
        }
        return self._read_list("/api/employees/{employeeId}/payslipperperiod", params)

    def personal_info(
        self,
        *,
        created_from: date | datetime | str | None = None,
    ) -> list[dict[str, Any]]:
        """``GET /api/companies/{companyId}/employees/personalinfo``

        Filters: created_from
        """
        params: dict[str, Any] = {
            "createdFrom": created_from,
        }
        return self._read_list("/api/companies/{companyId}/employees/personalinfo", params)

    def private_info(
        self,
        *,
        created_from: date | datetime | str | None = None,
    ) -> list[dict[str, Any]]:
        """``GET /api/companies/{companyId}/employees/privateInfos``

        Filters: created_from
        """
        params: dict[str, Any] = {
            "createdFrom": created_from,
        }
        return self._read_list("/api/companies/{companyId}/employees/privateInfos", params)

    def salaries(
        self,
        *,
        created_from: date | datetime | str | None = None,
    ) -> list[dict[str, Any]]:
        """``GET /api/companies/{companyId}/employees/salaries``

        Filters: created_from
        """
        params: dict[str, Any] = {
            "createdFrom": created_from,
        }
        return self._read_list("/api/companies/{companyId}/employees/salaries", params)

    def schedules(
        self,
        *,
        created_from: date | datetime | str | None = None,
    ) -> list[dict[str, Any]]:
        """``GET /api/companies/{companyId}/employees/schedules``

        Filters: created_from
        """
        params: dict[str, Any] = {
            "createdFrom": created_from,
        }
        return self._read_list("/api/companies/{companyId}/employees/schedules", params)

    def svw_settings(
        self,
        *,
        created_from: date | datetime | str | None = None,
    ) -> list[dict[str, Any]]:
        """``GET /api/companies/{companyId}/employees/svwsettings``

        Filters: created_from
        """
        params: dict[str, Any] = {
            "createdFrom": created_from,
        }
        return self._read_list("/api/companies/{companyId}/employees/svwsettings", params)

    def user_account(self) -> dict[str, Any] | None:
        """``GET /api/companies/{companyId}/employees/useraccounts``

        Filters: none
        """
        params: dict[str, Any] = {}
        return self._read_object("/api/companies/{companyId}/employees/useraccounts", params)

    def variable_days(
        self,
        *,
        period: int | None = None,
        year: int | None = None,
    ) -> list[dict[str, Any]]:
        """``GET /api/employees/{employeeId}/variabledays``

        Filters: period, year
        """
        params: dict[str, Any] = {
            "period": period,
            "year": year,
        }
        return self._read_list("/api/employees/{employeeId}/variabledays", params)

    def variable_hours(
        self,
        *,
        created_from: date | datetime | str | None = None,
        period: int | None = None,
        year: int | None = None,
    ) -> list[dict[str, Any]]:
        """``GET /api/employees/{employeeId}/variablehours``

        Filters: created_from, period, year
        """
        params: dict[str, Any] = {
            "createdFrom": created_from,
            "period": period,
            "year": year,
        }
        return self._read_list("/api/employees/{employeeId}/variablehours", params)

    def variable_wage_components(
        self,
        *,
        created_from: date | datetime | str | None = None,
        period: int | None = None,
        year: int | None = None,
    ) -> list[dict[str, Any]]:
        """``GET /api/companies/{companyId}/employees/variablewagecomponents``

        Filters: created_from, period, year
        """
        params: dict[str, Any] = {
            "createdFrom": created_from,
            "period": period,
            "year": year,
        }
        return self._read_list("/api/companies/{companyId}/employees/variablewagecomponents", params)

    def wage_tax_settings(
        self,
        *,
        created_from: date | datetime | str | None = None,
    ) -> list[dict[str, Any]]:
        """``GET /api/companies/{companyId}/employees/wagetaxsettings``

        Filters: created_from
        """
        params: dict[str, Any] = {
            "createdFrom": created_from,
        }
        return self._read_list("/api/companies/{companyId}/employees/wagetaxsettings", params)


class CompanyReads:
    """Generated company reads. Mixed into the resource class."""

    def _read_list(
        self, template: str, params: dict[str, Any]
    ) -> list[dict[str, Any]]:
        raise NotImplementedError

    def _read_object(
        self, template: str, params: dict[str, Any]
    ) -> dict[str, Any] | None:
        raise NotImplementedError

    def _read_scalar(
        self, template: str, params: dict[str, Any]
    ) -> Any:
        raise NotImplementedError

    def addresses(self) -> list[dict[str, Any]]:
        """``GET /api/companies/{companyId}/addresses``

        Filters: none
        """
        params: dict[str, Any] = {}
        return self._read_list("/api/companies/{companyId}/addresses", params)

    def bank_accounts(self) -> list[dict[str, Any]]:
        """``GET /api/companies/{companyId}/bankaccounts``

        Filters: none
        """
        params: dict[str, Any] = {}
        return self._read_list("/api/companies/{companyId}/bankaccounts", params)

    def contact_persons(self) -> list[dict[str, Any]]:
        """``GET /api/companies/{companyId}/contactpersons``

        Filters: none
        """
        params: dict[str, Any] = {}
        return self._read_list("/api/companies/{companyId}/contactpersons", params)

    def cost_centers(self) -> list[dict[str, Any]]:
        """``GET /api/companies/{companyId}/costCenters``

        Filters: none
        """
        params: dict[str, Any] = {}
        return self._read_list("/api/companies/{companyId}/costCenters", params)

    def cost_units(self) -> list[dict[str, Any]]:
        """``GET /api/companies/{companyId}/costUnits``

        Filters: none
        """
        params: dict[str, Any] = {}
        return self._read_list("/api/companies/{companyId}/costUnits", params)

    def default_templates(self) -> list[dict[str, Any]]:
        """``GET /api/companies/{companyId}/defaultTemplates``

        Filters: none
        """
        params: dict[str, Any] = {}
        return self._read_list("/api/companies/{companyId}/defaultTemplates", params)

    def extra_field_settings(self) -> list[dict[str, Any]]:
        """``GET /api/companies/{companyId}/extrafieldSettings``

        Filters: none
        """
        params: dict[str, Any] = {}
        return self._read_list("/api/companies/{companyId}/extrafieldSettings", params)

    def fixed_wage_components(
        self,
        *,
        created_from: date | datetime | str | None = None,
        period: int | None = None,
        year: int | None = None,
    ) -> list[dict[str, Any]]:
        """``GET /api/companies/{companyId}/fixedwagecomponents``

        Filters: created_from, period, year
        """
        params: dict[str, Any] = {
            "createdFrom": created_from,
            "period": period,
            "year": year,
        }
        return self._read_list("/api/companies/{companyId}/fixedwagecomponents", params)

    def hour_codes(self) -> list[dict[str, Any]]:
        """``GET /api/companies/{companyId}/hourcodes``

        Filters: none
        """
        params: dict[str, Any] = {}
        return self._read_list("/api/companies/{companyId}/hourcodes", params)

    def leave_groups(self) -> list[dict[str, Any]]:
        """``GET /api/companies/{companyId}/leaveGroups``

        Filters: none
        """
        params: dict[str, Any] = {}
        return self._read_list("/api/companies/{companyId}/leaveGroups", params)

    def pension_export(
        self,
        *,
        year: int | None = None,
    ) -> list[dict[str, Any]]:
        """``GET /api/companies/{companyId}/pensionexport``

        Filters: year
        """
        params: dict[str, Any] = {
            "year": year,
        }
        return self._read_list("/api/companies/{companyId}/pensionexport", params)

    def period(self) -> list[dict[str, Any]]:
        """``GET /api/companies/{companyId}/period``

        Filters: none
        """
        params: dict[str, Any] = {}
        return self._read_list("/api/companies/{companyId}/period", params)

    def salary_tables(self) -> list[dict[str, Any]]:
        """``GET /api/companies/{companyId}/salarytables``

        Filters: none
        """
        params: dict[str, Any] = {}
        return self._read_list("/api/companies/{companyId}/salarytables", params)

    def schedules(
        self,
        *,
        period: int | None = None,
        year: int | None = None,
    ) -> list[dict[str, Any]]:
        """``GET /api/companies/{companyId}/schedules``

        Filters: period, year
        """
        params: dict[str, Any] = {
            "period": period,
            "year": year,
        }
        return self._read_list("/api/companies/{companyId}/schedules", params)

    def svw_settings(
        self,
        *,
        created_from: date | datetime | str | None = None,
        period: int | None = None,
        year: int | None = None,
    ) -> list[dict[str, Any]]:
        """``GET /api/companies/{companyId}/svwsettings``

        Filters: created_from, period, year
        """
        params: dict[str, Any] = {
            "createdFrom": created_from,
            "period": period,
            "year": year,
        }
        return self._read_list("/api/companies/{companyId}/svwsettings", params)

    def variable_wage_components(
        self,
        *,
        created_from: date | datetime | str | None = None,
        year: int | None = None,
    ) -> list[dict[str, Any]]:
        """``GET /api/companies/{companyId}/variablewagecomponents``

        Filters: created_from, year
        """
        params: dict[str, Any] = {
            "createdFrom": created_from,
            "year": year,
        }
        return self._read_list("/api/companies/{companyId}/variablewagecomponents", params)

    def wage_models(
        self,
        *,
        period: int | None = None,
        year: int | None = None,
    ) -> list[dict[str, Any]]:
        """``GET /api/companies/{companyId}/wagemodels``

        Filters: period, year
        """
        params: dict[str, Any] = {
            "period": period,
            "year": year,
        }
        return self._read_list("/api/companies/{companyId}/wagemodels", params)

    def wage_taxes(
        self,
        *,
        year: int | None = None,
    ) -> list[dict[str, Any]]:
        """``GET /api/companies/{companyId}/wagetaxes``

        Filters: year
        """
        params: dict[str, Any] = {
            "year": year,
        }
        return self._read_list("/api/companies/{companyId}/wagetaxes", params)

    def work_cost(
        self,
        *,
        year: int | None = None,
    ) -> list[dict[str, Any]]:
        """``GET /api/companies/{companyId}/workcost``

        Filters: year
        """
        params: dict[str, Any] = {
            "year": year,
        }
        return self._read_list("/api/companies/{companyId}/workcost", params)


class DebtorReads:
    """Generated debtor reads. Mixed into the resource class."""

    def _read_list(
        self, template: str, params: dict[str, Any]
    ) -> list[dict[str, Any]]:
        raise NotImplementedError

    def _read_object(
        self, template: str, params: dict[str, Any]
    ) -> dict[str, Any] | None:
        raise NotImplementedError

    def _read_scalar(
        self, template: str, params: dict[str, Any]
    ) -> Any:
        raise NotImplementedError

    def absence_case_managers(self) -> list[dict[str, Any]]:
        """``GET /api/debtors/{debtorId}/absencecasemanagers``

        Filters: none
        """
        params: dict[str, Any] = {}
        return self._read_list("/api/debtors/{debtorId}/absencecasemanagers", params)

    def accountant_contact(self) -> list[dict[str, Any]]:
        """``GET /api/debtors/{debtorId}/accountantcontact``

        Filters: none
        """
        params: dict[str, Any] = {}
        return self._read_list("/api/debtors/{debtorId}/accountantcontact", params)

    def departments(self) -> list[dict[str, Any]]:
        """``GET /api/debtors/{debtorId}/departments``

        Filters: none
        """
        params: dict[str, Any] = {}
        return self._read_list("/api/debtors/{debtorId}/departments", params)

    def functions(self) -> list[dict[str, Any]]:
        """``GET /api/debtors/{debtorId}/functions``

        Filters: none
        """
        params: dict[str, Any] = {}
        return self._read_list("/api/debtors/{debtorId}/functions", params)

    def manager_user_accounts(self) -> list[dict[str, Any]]:
        """``GET /api/debtors/{debtorId}/managers/useraccounts``

        Filters: none
        """
        params: dict[str, Any] = {}
        return self._read_list("/api/debtors/{debtorId}/managers/useraccounts", params)

    def managers(self) -> list[dict[str, Any]]:
        """``GET /api/debtors/{debtorId}/managers``

        Filters: none
        """
        params: dict[str, Any] = {}
        return self._read_list("/api/debtors/{debtorId}/managers", params)

    def tags(self) -> list[dict[str, Any]]:
        """``GET /api/debtors/{debtorId}/tags``

        Filters: none
        """
        params: dict[str, Any] = {}
        return self._read_list("/api/debtors/{debtorId}/tags", params)
