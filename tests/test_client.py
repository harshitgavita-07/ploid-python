import unittest

import ploid
from ploid import (AuthenticationError, ConflictError, GoneError, NotFoundError,
                   PaymentRequiredError, PermissionDeniedError, RateLimitError,
                   ServerError, ValidationError)
from mock_server import MockPloid, api_error


def client(mock, **kw):
    kw.setdefault("base_url", mock.base_url)
    c = ploid.Client("pld_test_key", **kw)
    c._http._sleep = lambda s: None  # never really sleep in tests
    return c


class TestTransport(unittest.TestCase):
    def test_bearer_auth_default(self):
        with MockPloid() as m:
            m.add("GET", "/v1/account/credits", body={"balance_acu": 42})
            out = client(m).account.credits()
            self.assertEqual(out.balance_acu, 42)
            headers = m.requests[0][3]
            self.assertEqual(headers.get("authorization"), "Bearer pld_test_key")
            self.assertNotIn("x-api-key", headers)

    def test_x_api_key_scheme(self):
        with MockPloid() as m:
            m.add("GET", "/v1/account/credits", body={"balance_acu": 1})
            client(m, auth_scheme="x-api-key").account.credits()
            headers = m.requests[0][3]
            self.assertEqual(headers.get("x-api-key"), "pld_test_key")
            self.assertNotIn("authorization", headers)

    def test_query_params_encoded_and_none_dropped(self):
        with MockPloid() as m:
            m.add("GET", "/v1/linkedin/profile", body={"ok": True})
            client(m).linkedin.profile(url="https://www.linkedin.com/in/a b", identifier=None)
            self.assertEqual(m.requests[0][2], {"url": ["https://www.linkedin.com/in/a b"]})

    def test_path_params(self):
        with MockPloid() as m:
            m.add("GET", "/v1/monitors/mon_123", body={"id": "mon_123"})
            out = client(m).monitors.get("mon_123")
            self.assertEqual(out.id, "mon_123")
            self.assertEqual(m.requests[0][1], "/v1/monitors/mon_123")

    def test_post_json_body(self):
        with MockPloid() as m:
            m.add("POST", "/v1/resolve", body={"person_id": "p_1"})
            out = client(m).resolve_person({"name": "Kamran Karic", "company": "Ploid"})
            self.assertEqual(out.person_id, "p_1")
            self.assertEqual(m.requests[0][4], {"name": "Kamran Karic", "company": "Ploid"})
            self.assertEqual(m.requests[0][3].get("content-type"), "application/json")

    def test_idempotency_key_auto_and_stable_across_retries(self):
        with MockPloid() as m:
            m.add("POST", "/v1/search", status=503, body=api_error("upstream", "down"))
            m.add("POST", "/v1/search", body={"people": []})
            out = client(m).search.people({"query": "yc founders"})
            self.assertEqual(out.http_status, 200)
            keys = [r[3].get("idempotency-key") for r in m.requests]
            self.assertEqual(len(m.requests), 2)
            self.assertTrue(keys[0])
            self.assertEqual(keys[0], keys[1])  # same logical request, one key

    def test_idempotency_key_override(self):
        with MockPloid() as m:
            m.add("POST", "/v1/search", body={"people": []})
            client(m).search.people({"query": "x"}, idempotency_key="my-key-1")
            self.assertEqual(m.requests[0][3].get("idempotency-key"), "my-key-1")

    def test_get_requests_send_no_idempotency_key(self):
        with MockPloid() as m:
            m.add("GET", "/v1/account/usage", body={"ok": 1})
            client(m).account.usage()
            self.assertNotIn("idempotency-key", m.requests[0][3])


class TestErrors(unittest.TestCase):
    def check(self, status, exc, code="some_code"):
        with MockPloid() as m:
            m.add("GET", "/v1/account/credits", status=status,
                  body=api_error(code, "boom", retryable=False))
            with self.assertRaises(exc) as ctx:
                client(m).account.credits()
            self.assertEqual(ctx.exception.code, code)
            self.assertEqual(ctx.exception.request_id, "req_test")
            self.assertEqual(ctx.exception.status, status)
            self.assertEqual(len(m.requests), 1)  # never retried

    def test_401(self): self.check(401, AuthenticationError)
    def test_402(self): self.check(402, PaymentRequiredError)
    def test_403(self): self.check(403, PermissionDeniedError)
    def test_404(self): self.check(404, NotFoundError)
    def test_409(self): self.check(409, ConflictError)
    def test_410(self): self.check(410, GoneError)
    def test_422(self): self.check(422, ValidationError)

    def test_semantic_http_status_override(self):
        # error body may carry a semantic http_status different from transport
        with MockPloid() as m:
            m.add("GET", "/v1/account/credits", status=200,
                  body=api_error("rate_limited", "slow down", http_status=429))
            # 200 transport is returned as-is; semantic status only applies to errors
            out = client(m).account.credits()
            self.assertEqual(out["error"]["code"], "rate_limited")

    def test_429_retry_after_then_raise(self):
        with MockPloid() as m:
            for _ in range(4):
                m.add("GET", "/v1/account/credits", status=429,
                      body=api_error("rate_limited", "slow down"),
                      headers={"Retry-After": "7"})
            with self.assertRaises(RateLimitError) as ctx:
                client(m, max_retries=3).account.credits()
            self.assertEqual(ctx.exception.retry_after, 7.0)
            self.assertEqual(len(m.requests), 4)  # 1 + 3 retries

    def test_503_retried_then_succeeds(self):
        with MockPloid() as m:
            m.add("GET", "/v1/account/credits", status=503,
                  body=api_error("unavailable", "try later"))
            m.add("GET", "/v1/account/credits", body={"balance_acu": 9})
            out = client(m).account.credits()
            self.assertEqual(out.balance_acu, 9)
            self.assertEqual(len(m.requests), 2)

    def test_503_exhausts_retries(self):
        with MockPloid() as m:
            for _ in range(3):
                m.add("GET", "/v1/account/credits", status=503,
                      body=api_error("unavailable", "down"))
            with self.assertRaises(ServerError):
                client(m, max_retries=2).account.credits()
            self.assertEqual(len(m.requests), 3)


class TestAsyncFlows(unittest.TestCase):
    def test_search_202_handoff_and_wait(self):
        with MockPloid() as m:
            m.add("POST", "/v1/search", status=202,
                  body={"set_id": "set_1",
                        "items_url": None,  # filled below once port is known
                        "events_url": "https://api.ploid.com/v1/sets/set_1/events"})
            m.routes[0] = ("POST", "/v1/search", 202,
                           {"set_id": "set_1",
                            "items_url": f"{m.base_url}/v1/sets/set_1/items",
                            "events_url": "https://api.ploid.com/v1/sets/set_1/events"}, {})
            m.add("GET", "/v1/sets/set_1/items", body={"status": "running", "items": []})
            m.add("GET", "/v1/sets/set_1/items",
                  body={"status": "complete", "items": [{"person_id": "p1"}]})
            c = client(m)
            handoff = c.search.people({"query": "big async search", "async": True})
            self.assertEqual(handoff.http_status, 202)
            self.assertEqual(handoff.set_id, "set_1")
            final = c.search.wait_for_set(handoff, interval=0, max_interval=0)
            self.assertEqual(final.status, "complete")
            self.assertEqual(final.items[0].person_id, "p1")
            # waited through the running state first
            self.assertEqual([r[1] for r in m.requests].count("/v1/sets/set_1/items"), 2)

    def test_person_deep_run_wait(self):
        with MockPloid() as m:
            m.add("POST", "/v1/person", status=202, body={"run_id": "run_1", "status": "running"})
            m.add("GET", "/v1/person/runs/run_1", body={"run_id": "run_1", "status": "completed",
                                                         "person": {"name": "K Karic"}})
            c = client(m)
            accepted = c.person.get({"person_id": "p_1", "depth": "deep"})
            self.assertEqual(accepted.http_status, 202)
            final = c.person.wait_for_run("run_1", interval=0, max_interval=0)
            self.assertEqual(final.person.name, "K Karic")

    def test_dataset_async_wait(self):
        with MockPloid() as m:
            m.add("POST", "/v1/datasets", status=202, body={"dataset_id": "ds_1", "status": "running"})
            m.add("GET", "/v1/datasets/ds_1", body={"dataset_id": "ds_1", "status": "ready"})
            c = client(m)
            accepted = c.datasets.create({"rows": [], "columns": [], "mode": "async"})
            self.assertEqual(accepted.http_status, 202)
            final = c.datasets.wait_until_ready("ds_1", interval=0, max_interval=0)
            self.assertEqual(final.status, "ready")

    def test_monitor_run_202(self):
        with MockPloid() as m:
            m.add("POST", "/v1/monitors/mon_9/run", status=202, body={"run_id": "r_2"})
            out = client(m).monitors.run("mon_9")
            self.assertEqual(out.http_status, 202)
            self.assertEqual(out.run_id, "r_2")

    def test_poll_timeout(self):
        with MockPloid() as m:
            m.add("GET", "/v1/person/runs/run_x", body={"run_id": "run_x", "status": "running"})
            with self.assertRaises(ploid.PollTimeout):
                client(m).person.wait_for_run("run_x", deadline_seconds=-1, interval=0, max_interval=0)


class TestPagination(unittest.TestCase):
    def test_monitors_list_all_follows_cursor(self):
        with MockPloid() as m:
            m.add("GET", "/v1/monitors",
                  body={"monitors": [{"id": "m1"}], "next_cursor": "abc"})
            m.add("GET", "/v1/monitors", body={"monitors": [{"id": "m2"}]})
            ids = [mon["id"] for mon in client(m).monitors.list_all()]
            self.assertEqual(ids, ["m1", "m2"])
            self.assertEqual(m.requests[1][2], {"cursor": ["abc"]})

    def test_dataset_rows_all(self):
        with MockPloid() as m:
            m.add("GET", "/v1/datasets/ds_1/rows",
                  body={"rows": [{"row": 1}, {"row": 2}]})
            rows = list(client(m).datasets.rows_all("ds_1"))
            self.assertEqual(len(rows), 2)

class TestModelsAndSSE(unittest.TestCase):
    def test_ploid_object_nested_and_additive(self):
        obj = ploid.PloidObject({"a": {"b": [1, {"c": 2}]}, "new_field": True})
        self.assertEqual(obj.a.b[1].c, 2)
        self.assertTrue(obj.new_field)
        self.assertEqual(obj.to_dict()["a"]["b"][1]["c"], 2)

    def test_missing_attr_raises(self):
        with self.assertRaises(AttributeError):
            ploid.PloidObject({}).nope

    def test_sse_parser(self):
        lines = [
            ": comment", "",
            "event: progress", "data: {\"pct\": 50}", "id: 7", "",
            "data: {\"pct\": 100}", "data: ", "",
        ]
        events = list(ploid.iter_sse(lines))
        self.assertEqual(len(events), 2)
        self.assertEqual(events[0].event, "progress")
        self.assertEqual(events[0].id, "7")
        self.assertEqual(events[0].json()["pct"], 50)
        self.assertEqual(events[1].data, '{"pct": 100}\n')


if __name__ == "__main__":
    unittest.main()
