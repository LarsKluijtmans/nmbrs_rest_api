"""Lazy pagination."""

from __future__ import annotations

from typing import Any

import httpx
import pytest
import respx

from nmbrs_rest.errors import ResourceNotFoundError
from nmbrs_rest.pagination import MAX_PAGE_SIZE, Page, unwrap_one
from nmbrs_rest.transport import DEFAULT_BASE_URL, Transport
from tests.helpers import SUBSCRIPTION_KEY, make_token

TEMPLATE = "/api/companies"
URL = f"{DEFAULT_BASE_URL}{TEMPLATE}"


def transport() -> Transport:
    return Transport(subscription_key=SUBSCRIPTION_KEY, token=make_token())


def page(**kwargs: Any) -> Page[dict[str, Any]]:
    return Page(transport(), TEMPLATE, factory=lambda row: row, **kwargs)


def envelope(rows: list[dict[str, Any]], **pagination: Any) -> dict[str, Any]:
    return {"data": rows, "pagination": pagination}


@respx.mock
def test_nothing_is_requested_until_iteration() -> None:
    route = respx.get(URL).mock(return_value=httpx.Response(200, json=envelope([])))
    page()
    assert route.call_count == 0


@respx.mock
def test_walks_every_page() -> None:
    respx.get(URL).mock(
        side_effect=[
            httpx.Response(200, json=envelope([{"i": 1}, {"i": 2}], totalPages=3, pageNumber=1)),
            httpx.Response(200, json=envelope([{"i": 3}, {"i": 4}], totalPages=3, pageNumber=2)),
            httpx.Response(200, json=envelope([{"i": 5}], totalPages=3, pageNumber=3)),
        ]
    )
    assert [row["i"] for row in page()] == [1, 2, 3, 4, 5]


@respx.mock
def test_uses_the_maximum_page_size_by_default() -> None:
    route = respx.get(URL).mock(return_value=httpx.Response(200, json=envelope([], totalPages=1)))
    list(page())
    query = route.calls[0].request.url.params
    assert query["pageSize"] == str(MAX_PAGE_SIZE)
    assert query["pageNumber"] == "1"


def test_page_size_above_the_maximum_is_rejected() -> None:
    with pytest.raises(ValueError, match="must be <= 100"):
        page(page_size=500)


@respx.mock
def test_stops_on_a_short_page_when_total_pages_is_absent() -> None:
    respx.get(URL).mock(
        side_effect=[
            httpx.Response(200, json=envelope([{"i": n} for n in range(100)], nextPage="p2")),
            httpx.Response(200, json=envelope([{"i": 100}])),
        ]
    )
    assert len(list(page())) == 101


@respx.mock
def test_stops_when_next_page_is_null() -> None:
    respx.get(URL).mock(return_value=httpx.Response(200, json=envelope([{"i": 1}], nextPage=None)))
    assert len(list(page())) == 1


@respx.mock
def test_first_only_fetches_one_page() -> None:
    route = respx.get(URL).mock(
        return_value=httpx.Response(200, json=envelope([{"i": 1}, {"i": 2}], totalPages=9))
    )
    assert page().first() == {"i": 1}
    assert route.call_count == 1


@respx.mock
def test_first_on_an_empty_collection_is_none() -> None:
    respx.get(URL).mock(return_value=httpx.Response(200, json=envelope([], totalPages=1)))
    assert page().first() is None


@respx.mock
def test_one_raises_when_empty() -> None:
    respx.get(URL).mock(return_value=httpx.Response(200, json=envelope([], totalPages=1)))
    with pytest.raises(ResourceNotFoundError):
        page().one()


@respx.mock
def test_total_records_is_exposed() -> None:
    respx.get(URL).mock(
        return_value=httpx.Response(200, json=envelope([{"i": 1}], totalRecords=328, totalPages=1))
    )
    assert page().total_records == 328


@respx.mock
def test_extra_params_are_forwarded() -> None:
    route = respx.get(URL).mock(return_value=httpx.Response(200, json=envelope([], totalPages=1)))
    list(page(params={"employeeId": "e1"}))
    assert route.calls[0].request.url.params["employeeId"] == "e1"


@respx.mock
def test_factory_builds_items() -> None:
    respx.get(URL).mock(
        return_value=httpx.Response(200, json=envelope([{"companyId": "c1"}], totalPages=1))
    )
    items = list(Page(transport(), TEMPLATE, factory=lambda row: str(row["companyId"]).upper()))
    assert items == ["C1"]


@respx.mock
def test_non_dict_rows_are_skipped() -> None:
    respx.get(URL).mock(
        return_value=httpx.Response(200, json={"data": [{"i": 1}, "junk", None], "pagination": {}})
    )
    assert list(page()) == [{"i": 1}]


# --------------------------------------------------------------------------- #
# unwrap_one
# --------------------------------------------------------------------------- #


def test_unwrap_one_returns_the_single_row() -> None:
    assert unwrap_one({"data": [{"employeeId": "e1"}]}, template=TEMPLATE) == {"employeeId": "e1"}


def test_unwrap_one_treats_an_empty_array_as_not_found() -> None:
    """Nmbrs signals a missing single item with [] rather than a 404."""
    with pytest.raises(ResourceNotFoundError, match="does not exist"):
        unwrap_one({"data": []}, template=TEMPLATE)


def test_unwrap_one_handles_a_missing_data_key() -> None:
    with pytest.raises(ResourceNotFoundError):
        unwrap_one({}, template=TEMPLATE)
