"""Ploid API client. Covers every operation in the public OpenAPI 2.0.0 doc."""
from __future__ import annotations

from typing import Any, Dict, Iterator, Optional

from ._http import DEFAULT_BASE_URL, HttpClient
from ._models import PloidObject, next_cursor, page_items
from .polling import wait as _wait


class _Resource:
    def __init__(self, http: HttpClient) -> None:
        self._http = http

    def _call(self, method: str, path: str, **kw: Any) -> PloidObject:
        status, _headers, body = self._http.request(method, path, **kw)
        return PloidObject(body, _status=status)

    def _get(self, path: str, query: Optional[Dict[str, Any]] = None) -> PloidObject:
        return self._call("GET", path, query=query)

    def _post(self, path: str, body: Any = None, **kw: Any) -> PloidObject:
        return self._call("POST", path, body=body if body is not None else {}, **kw)

    def _pages(self, path: str, query: Optional[Dict[str, Any]] = None) -> Iterator[Any]:
        cursor = None
        while True:
            q = dict(query or {})
            if cursor:
                q["cursor"] = cursor
            page = self._get(path, q)
            yield from page_items(page)
            cursor = next_cursor(page)
            if not cursor:
                return


class SearchResource(_Resource):
    def people(self, body: Dict[str, Any], **kw: Any) -> PloidObject:
        """POST /v1/search - synchronous people search.

        A 202 response means a background People Set started; the body
        carries ``set_id``, ``items_url`` and ``events_url`` - use
        :meth:`wait_for_set`.
        """
        return self._post("/v1/search", body, **kw)

    def candidates(self, body: Dict[str, Any], **kw: Any) -> PloidObject:
        """POST /v1/search/candidates - candidate identities (1 ACU)."""
        return self._post("/v1/search/candidates", body, **kw)

    def wait_for_set(self, handoff: PloidObject, **wait_kw: Any) -> PloidObject:
        """Poll a 202 handoff's ``items_url`` until the set is complete."""
        items_url = handoff.get("items_url")
        if not items_url:
            raise ValueError("handoff has no items_url (was the response a 202?)")
        if items_url.startswith("http"):
            from urllib.parse import urlparse
            path = urlparse(items_url).path
        else:
            path = items_url
        return _wait("people set", lambda: self._get(path), **wait_kw)


class CompaniesResource(_Resource):
    def recruiters(self, body: Dict[str, Any], **kw: Any) -> PloidObject:
        """POST /v1/companies/recruiters."""
        return self._post("/v1/companies/recruiters", body, **kw)


class PersonResource(_Resource):
    def get(self, body: Dict[str, Any], **kw: Any) -> PloidObject:
        """POST /v1/person - evidence-backed person record (202 = deep run)."""
        return self._post("/v1/person", body, **kw)

    def get_run(self, run_id: str) -> PloidObject:
        """GET /v1/person/runs/{id}."""
        return self._get(f"/v1/person/runs/{run_id}")

    def cancel_run(self, run_id: str) -> PloidObject:
        """DELETE /v1/person/runs/{id}."""
        return self._call("DELETE", f"/v1/person/runs/{run_id}")

    def wait_for_run(self, run_id: str, **wait_kw: Any) -> PloidObject:
        """Poll a deep person run until it reaches a terminal state."""
        return _wait("person run", lambda: self.get_run(run_id), **wait_kw)


class MonitorsResource(_Resource):
    def compile(self, body: Dict[str, Any]) -> PloidObject:
        """POST /v1/monitors/compile - preview a monitor plan."""
        return self._post("/v1/monitors/compile", body)

    def create(self, body: Dict[str, Any]) -> PloidObject:
        """POST /v1/monitors."""
        return self._post("/v1/monitors", body)

    def list(self, *, cursor: Optional[str] = None, limit: Optional[int] = None) -> PloidObject:
        return self._get("/v1/monitors", {"cursor": cursor, "limit": limit})

    def list_all(self, *, limit: Optional[int] = None) -> Iterator[Any]:
        yield from self._pages("/v1/monitors", {"limit": limit})

    def get(self, monitor_id: str) -> PloidObject:
        return self._get(f"/v1/monitors/{monitor_id}")

    def update(self, monitor_id: str, body: Dict[str, Any], **kw: Any) -> PloidObject:
        """PATCH /v1/monitors/{id} - update, pause or resume."""
        return self._call("PATCH", f"/v1/monitors/{monitor_id}", body=body, **kw)

    def delete(self, monitor_id: str) -> PloidObject:
        return self._call("DELETE", f"/v1/monitors/{monitor_id}")

    def run(self, monitor_id: str) -> PloidObject:
        """POST /v1/monitors/{id}/run (202)."""
        return self._post(f"/v1/monitors/{monitor_id}/run")

    def test(self, monitor_id: str) -> PloidObject:
        return self._post(f"/v1/monitors/{monitor_id}/test")

    def test_webhook(self, monitor_id: str) -> PloidObject:
        return self._post(f"/v1/monitors/{monitor_id}/webhook/test")

    def list_runs(self, monitor_id: str, *, cursor: Optional[str] = None,
                  limit: Optional[int] = None) -> PloidObject:
        return self._get(f"/v1/monitors/{monitor_id}/runs", {"cursor": cursor, "limit": limit})

    def runs_all(self, monitor_id: str, *, limit: Optional[int] = None) -> Iterator[Any]:
        yield from self._pages(f"/v1/monitors/{monitor_id}/runs", {"limit": limit})

    def get_run(self, monitor_id: str, run_id: str) -> PloidObject:
        return self._get(f"/v1/monitors/{monitor_id}/runs/{run_id}")

    def wait_for_run(self, monitor_id: str, run_id: str, **wait_kw: Any) -> PloidObject:
        return _wait("monitor run", lambda: self.get_run(monitor_id, run_id), **wait_kw)

    def list_items(self, monitor_id: str, *, run_id: Optional[str] = None,
                   cursor: Optional[str] = None, limit: Optional[int] = None) -> PloidObject:
        return self._get(f"/v1/monitors/{monitor_id}/items",
                         {"run_id": run_id, "cursor": cursor, "limit": limit})

    def items_all(self, monitor_id: str, *, run_id: Optional[str] = None,
                  limit: Optional[int] = None) -> Iterator[Any]:
        yield from self._pages(f"/v1/monitors/{monitor_id}/items",
                               {"run_id": run_id, "limit": limit})


class DatasetsResource(_Resource):
    def create(self, body: Dict[str, Any], **kw: Any) -> PloidObject:
        """POST /v1/datasets - fill typed columns (202 when mode=async)."""
        return self._post("/v1/datasets", body, **kw)

    def get(self, dataset_id: str) -> PloidObject:
        return self._get(f"/v1/datasets/{dataset_id}")

    def rows(self, dataset_id: str, *, cursor: Optional[str] = None,
             limit: Optional[int] = None) -> PloidObject:
        return self._get(f"/v1/datasets/{dataset_id}/rows", {"cursor": cursor, "limit": limit})

    def rows_all(self, dataset_id: str, *, limit: Optional[int] = None) -> Iterator[Any]:
        yield from self._pages(f"/v1/datasets/{dataset_id}/rows", {"limit": limit})

    def wait_until_ready(self, dataset_id: str, **wait_kw: Any) -> PloidObject:
        return _wait("dataset", lambda: self.get(dataset_id), **wait_kw)


class GitHubResource(_Resource):
    def search(self, body: Dict[str, Any], **kw: Any) -> PloidObject:
        """POST /v1/github/search (beta)."""
        return self._post("/v1/github/search", body, **kw)

    def people_search(self, body: Dict[str, Any], **kw: Any) -> PloidObject:
        """POST /v1/github/people-search (beta)."""
        return self._post("/v1/github/people-search", body, **kw)


class LinkedInResource(_Resource):
    def profile(self, *, url: Optional[str] = None, identifier: Optional[str] = None) -> PloidObject:
        return self._get("/v1/linkedin/profile", {"url": url, "identifier": identifier})

    def search(self, body: Dict[str, Any]) -> PloidObject:
        return self._post("/v1/linkedin/search", body)

    def posts(self, *, identifier: Optional[str] = None, url: Optional[str] = None,
              limit: Optional[int] = None) -> PloidObject:
        return self._get("/v1/linkedin/posts",
                         {"identifier": identifier, "url": url, "limit": limit})

    def profile_comments(self, **query: Any) -> PloidObject:
        """GET /v1/linkedin/profiles/comments (profile/profileId/postedLimit/
        page/paginationToken)."""
        return self._get("/v1/linkedin/profiles/comments", query)

    def company(self, *, url: Optional[str] = None, universal_name: Optional[str] = None,
                search: Optional[str] = None) -> PloidObject:
        return self._get("/v1/linkedin/companies/get",
                         {"url": url, "universalName": universal_name, "search": search})

    def company_posts(self, **query: Any) -> PloidObject:
        """GET /v1/linkedin/companies/posts (company/companyId/
        companyUniversalName/postedLimit/scrapePostedLimit/page/paginationToken)."""
        return self._get("/v1/linkedin/companies/posts", query)


class AccountResource(_Resource):
    def credits(self) -> PloidObject:
        """GET /v1/account/credits - balance and key budget (account:read)."""
        return self._get("/v1/account/credits")

    def usage(self) -> PloidObject:
        """GET /v1/account/usage - usage and active key context."""
        return self._get("/v1/account/usage")

    def profile(self) -> PloidObject:
        return self._get("/v1/account/profile")

    def update_profile(self, body: Dict[str, Any], **kw: Any) -> PloidObject:
        return self._call("PATCH", "/v1/account/profile", body=body, **kw)

    def revoke_current_key(self) -> PloidObject:
        """DELETE /v1/account/key - revokes the key used on this request."""
        return self._call("DELETE", "/v1/account/key")


class HarnessResource(_Resource):
    def context(self, body: Dict[str, Any]) -> PloidObject:
        """POST /v1/harness/context - canonical memory for another runtime."""
        return self._post("/v1/harness/context", body)

    def chat_completion(self, body: Dict[str, Any], **kw: Any) -> PloidObject:
        """POST /v1/harness/chat/completions - bounded tool-calling request."""
        return self._post("/v1/harness/chat/completions", body, **kw)


class Client:
    """Ploid API client.

    >>> client = ploid.Client("pld_...")
    >>> client.account.credits()
    """

    def __init__(self, api_key: str, *, base_url: str = DEFAULT_BASE_URL,
                 auth_scheme: str = "bearer", timeout: float = 30.0,
                 max_retries: int = 3) -> None:
        self._http = HttpClient(api_key, base_url=base_url, auth_scheme=auth_scheme,
                                timeout=timeout, max_retries=max_retries)
        self.search = SearchResource(self._http)
        self.companies = CompaniesResource(self._http)
        self.person = PersonResource(self._http)
        self.monitors = MonitorsResource(self._http)
        self.datasets = DatasetsResource(self._http)
        self.github = GitHubResource(self._http)
        self.linkedin = LinkedInResource(self._http)
        self.account = AccountResource(self._http)
        self.harness = HarnessResource(self._http)

    def resolve_person(self, body: Dict[str, Any], **kw: Any) -> PloidObject:
        """POST /v1/resolve - one person from name + clue (free if not found)."""
        s, _h, b = self._http.request("POST", "/v1/resolve", body=body, **kw)
        return PloidObject(b, _status=s)

    def reverse_email(self, body: Dict[str, Any]) -> PloidObject:
        """POST /v1/reverse - person behind an email address."""
        s, _h, b = self._http.request("POST", "/v1/reverse", body=body)
        return PloidObject(b, _status=s)

    def technographics(self, body: Dict[str, Any], **kw: Any) -> PloidObject:
        """POST /v1/technographics - a website's stack with evidence (beta)."""
        s, _h, b = self._http.request("POST", "/v1/technographics", body=body, **kw)
        return PloidObject(b, _status=s)

    def enrich_person(self, body: Dict[str, Any], **kw: Any) -> PloidObject:
        """POST /v1/enrich - work/personal emails and phones for a person."""
        s, _h, b = self._http.request("POST", "/v1/enrich", body=body, **kw)
        return PloidObject(b, _status=s)

    def enrich_social(self, body: Dict[str, Any], **kw: Any) -> PloidObject:
        """POST /v1/socials - one public social profile."""
        s, _h, b = self._http.request("POST", "/v1/socials", body=body, **kw)
        return PloidObject(b, _status=s)

    def openapi_spec(self) -> PloidObject:
        """GET /v1/openapi.json - the live OpenAPI document (unauthenticated)."""
        s, _h, b = self._http.request("GET", "/v1/openapi.json")
        return PloidObject(b, _status=s)
