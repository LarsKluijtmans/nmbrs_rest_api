"""Resource objects: Debtor, Company, Employee."""

from __future__ import annotations

from nmbrs_rest.resources.base import Resource
from nmbrs_rest.resources.company import Company
from nmbrs_rest.resources.debtor import Debtor
from nmbrs_rest.resources.employee import Employee

__all__ = ["Company", "Debtor", "Employee", "Resource"]
