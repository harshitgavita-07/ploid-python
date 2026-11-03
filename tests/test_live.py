"""Live tests against the real Ploid API.

Skipped unless PLOID_API_KEY is set.

Two tiers, because Ploid operations bill workspace credits (ACU):
- default tier: UNCHARGED reads only (account metadata + public OpenAPI doc +
  a 401 auth-failure shape check). These never touch the billable surface.
- charged tier: set PLOID_LIVE_CHARGED=1 as well to run operations that
  consume credits (kept to the cheapest documented ops).
"""
import os
import unittest

import ploid

KEY = os.environ.get("PLOID_API_KEY")
CHARGED = os.environ.get("PLOID_LIVE_CHARGED") == "1"


@unittest.skipUnless(KEY, "PLOID_API_KEY not set")
class TestLiveFreeTier(unittest.TestCase):
    def setUp(self):
        self.client = ploid.Client(KEY, max_retries=2)

    def test_credits_shape(self):
        out = self.client.account.credits()
        self.assertIsInstance(out.to_dict(), dict)
        self.assertEqual(out.http_status, 200)

    def test_usage_shape(self):
        out = self.client.account.usage()
        self.assertEqual(out.http_status, 200)

    def test_profile_shape(self):
        out = self.client.account.profile()
        self.assertEqual(out.http_status, 200)

    def test_openapi_document_public(self):
        spec = self.client.openapi_spec()
        self.assertIn("paths", spec)

    def test_bad_key_raises_auth_error(self):
        bad = ploid.Client("pld_definitely_invalid", max_retries=0)
        with self.assertRaises(ploid.AuthenticationError) as ctx:
            bad.account.credits()
        self.assertTrue(ctx.exception.request_id or ctx.exception.code)


@unittest.skipUnless(KEY and CHARGED, "needs PLOID_API_KEY and PLOID_LIVE_CHARGED=1 (bills credits)")
class TestLiveCharged(unittest.TestCase):
    def setUp(self):
        self.client = ploid.Client(KEY, max_retries=2)

    def test_candidates_smallest_billed_op(self):
        out = self.client.search.candidates({"query": "Ploid founders", "limit": 1})
        self.assertIn(out.http_status, (200, 202))

    def test_technographics_free_when_nothing_found(self):
        out = self.client.technographics({"domain": "this-domain-almost-certainly-does-not-exist-zzq.example"})
        self.assertEqual(out.http_status, 200)


if __name__ == "__main__":
    unittest.main()
