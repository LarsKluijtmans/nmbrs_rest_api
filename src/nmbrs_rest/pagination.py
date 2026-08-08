"""Lazy pagination over the ``{"data": [...], "pagination": {...}}`` envelope.

Nmbrs paginates with ``pageNumber`` (from 1) and ``pageSize`` (default 20, **max
100**). Every response is a list, even single-item reads, which is why
:func:`unwrap_one` exists.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Generic, TypeVar

from nmbrs_rest.errors import Operation, ResourceNotFoundError

if TYPE_CHECKING:
    from nmbrs_rest.transport import Transport

__all__ = ["MAX_PAGE_SIZE", "Page", "PageInfo", "unwrap_one"]

T = TypeVar("T")

#: Nmbrs rejects anything above this.
MAX_PAGE_SIZE = 100


@dataclass(frozen=True, slots=True)
class PageInfo:
    """The ``pagination`` block from a response."""

    page_number: int | None = None
    page_size: int | None = None
    total_pages: int | None = None
    total_records: int | None = None
    next_page: str | None = None
    previous_page: str | None = None

    @classmethod
    def from_payload(cls, raw: Any) -> PageInfo:
        if not isinstance(raw, dict):
            return cls()
        return cls(
            page_number=raw.get("pageNumber"),
            page_size=raw.get("pageSize"),
            total_pages=raw.get("totalPages"),
            total_records=raw.get("totalRecords"),
            next_page=raw.get("nextPage"),
            previous_page=raw.get("previousPage"),
        )


class Page(Generic[T]):
    """A lazily-walked collection.

    Nothing is requested until iteration starts, and pages are fetched one at a
    time as the consumer advances::

        for employee in company.employees():   # page 1, then 2, ... on demand
            ...

    Iterating twice re-fetches; call ``list()`` if you need to reuse the results.
    """

    def __init__(
        self,
        transport: Transport,
        template: str,
        *,
        path: str | None = None,
        params: dict[str, Any] | None = None,
        factory: Callable[[dict[str, Any]], T],
        page_size: int = MAX_PAGE_SIZE,
    ) -> None:
        if page_size > MAX_PAGE_SIZE:
            raise ValueError(f"page_size must be <= {MAX_PAGE_SIZE} (Nmbrs rejects larger)")
        self._transport = transport
        self._template = template
        self._path = path or template
        self._params = dict(params or {})
        self._factory = factory
        self._page_size = page_size
        self._info: PageInfo | None = None

    # -- internals --------------------------------------------------------- #

    def _fetch(self, page_number: int) -> tuple[list[dict[str, Any]], PageInfo]:
        params = dict(self._params)
        params["pageNumber"] = page_number
        params["pageSize"] = self._page_size
        payload = self._transport.get_json(self._template, path=self._path, params=params)
        raw = payload.get("data")
        rows = [row for row in raw if isinstance(row, dict)] if isinstance(raw, list) else []
        return rows, PageInfo.from_payload(payload.get("pagination"))

    # -- public ------------------------------------------------------------ #

    def __iter__(self) -> Iterator[T]:
        page_number = 1
        while True:
            rows, info = self._fetch(page_number)
            self._info = info
            for row in rows:
                yield self._factory(row)

            # Prefer the server's own view of where we are; fall back to a short
            # page meaning the end.
            if info.total_pages is not None:
                if page_number >= info.total_pages:
                    return
            elif info.next_page is None or len(rows) < self._page_size:
                return
            page_number += 1

    @property
    def info(self) -> PageInfo:
        """Pagination metadata. Triggers a fetch of the first page if needed."""
        if self._info is None:
            _, self._info = self._fetch(1)
        return self._info

    @property
    def total_records(self) -> int | None:
        return self.info.total_records

    def first(self) -> T | None:
        """The first item, fetching only one page."""
        for item in self:
            return item
        return None

    def one(self) -> T:
        """The single expected item, raising if there is none."""
        item = self.first()
        if item is None:
            raise ResourceNotFoundError(
                http_status=404,
                detail="expected exactly one result but the response contained none",
                operation=Operation(method="GET", template=self._template, path=self._path),
            )
        return item

    def __repr__(self) -> str:
        return (
            f"<Page {self._template} (not yet fetched)>"
            if self._info is None
            else (f"<Page {self._template} total_records={self._info.total_records}>")
        )


def unwrap_one(
    payload: dict[str, Any],
    *,
    template: str,
    path: str | None = None,
) -> dict[str, Any]:
    """Take the single row out of a ``data`` array.

    Nmbrs returns a list even for single-item reads, and signals "not found" with an
    empty array rather than a 404.
    """
    raw = payload.get("data")
    rows = [row for row in raw if isinstance(row, dict)] if isinstance(raw, list) else []
    if not rows:
        raise ResourceNotFoundError(
            http_status=404,
            detail="the resource does not exist, or is not visible to this token",
            operation=Operation(method="GET", template=template, path=path or template),
        )
    return rows[0]
