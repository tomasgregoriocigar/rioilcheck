#!/usr/bin/env python3
"""Unit tests for scripts/update_oil.py — run: python3 -m unittest discover tests
Fixtures are the snapshots saved Nov 26, 2026. Known-good week (verified by
hand Nov 25-26 against both EIA sources and the live site):
week of 2026-11-23 — heating oil 5.404, propane 4.116, wholesale 4.102.
"""
import re, sys, unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
FIX = Path(__file__).resolve().parent / "fixtures"
import update_oil as u

KNOWN = {"week_of": "2026-11-23",
         "heating_oil": (5.404, -0.272, 1.526, 5.676, 3.878),
         "propane": (4.116, -0.007, 0.553, 4.123, 3.563),
         "wholesale": (4.102, -0.379, 1.509, 4.481, 2.593)}

class TestPageParser(unittest.TestCase):
    def setUp(self):
        self.d = u.parse_eia_page((FIX / "eia_shopp_page.html").read_text())
    def test_week(self):
        self.assertEqual(self.d["week_of"], KNOWN["week_of"])
    def test_values_and_changes(self):
        for fuel, vals in KNOWN.items():
            if fuel == "week_of":
                continue
            v, cpw, cya, _, _ = vals
            self.assertAlmostEqual(self.d[fuel]["value"], v, places=3, msg=fuel)
            self.assertAlmostEqual(self.d[fuel]["change_vs_prior_week"], cpw, places=3, msg=fuel)
            self.assertAlmostEqual(self.d[fuel]["change_vs_year_ago"], cya, places=3, msg=fuel)

class TestXlsParser(unittest.TestCase):
    def setUp(self):
        self.d = u.parse_eia_xls((FIX / "eia_ri_series.xls").read_bytes())
    def test_week_and_values(self):
        self.assertEqual(self.d["week_of"], KNOWN["week_of"])
        for fuel, vals in KNOWN.items():
            if fuel == "week_of":
                continue
            v, cpw, cya, pw, ya = vals
            self.assertAlmostEqual(self.d[fuel]["value"], v, places=3, msg=fuel)
            self.assertAlmostEqual(self.d[fuel]["prior_week_value"], pw, places=3, msg=fuel)
            self.assertAlmostEqual(self.d[fuel]["change_vs_prior_week"], cpw, places=3, msg=fuel)
            self.assertAlmostEqual(self.d[fuel]["change_vs_year_ago"], cya, places=3, msg=fuel)
    def test_sources_agree(self):
        page = u.parse_eia_page((FIX / "eia_shopp_page.html").read_text())
        self.assertEqual(u.core(page), u.core(self.d))

class TestApiParser(unittest.TestCase):
    def test_seriesid_shape(self):
        # Fixture shape mirrors /v2/seriesid/PET.<series>.W responses,
        # values taken from the XLS known-good rows around the Nov 23 week.
        from datetime import date, timedelta
        start = date(2025, 11, 24)  # year-ago row for the Nov 23, 2026 week
        rows = []
        for i in range(53):
            d = start + timedelta(days=7 * i)
            rows.append({"period": d.isoformat(), "value": "3.878"})
        rows[-2] = {"period": "2026-11-16", "value": "5.676"}
        rows[-1] = {"period": "2026-11-23", "value": "5.404"}
        payload = {"response": {"data": rows}}
        d = u.parse_eia_api(payload, "heating_oil")
        self.assertEqual(d["week_of"], "2026-11-23")
        self.assertAlmostEqual(d["value"], 5.404, places=3)

class TestMissingRowsAndRounding(unittest.TestCase):
    def test_missing_year_ago_writes_nulls(self):
        from datetime import date, timedelta
        rows = []
        d0 = date(2026, 11, 2)
        for i in range(4):  # only 4 weeks of history — no year-ago row exists
            rows.append((d0 + timedelta(days=7 * i), [5.0 + i, 4.0, 4.1]))
        out = u.summarize_rows(rows)
        self.assertIsNone(out["heating_oil"]["year_ago_value"])
        self.assertIsNone(out["heating_oil"]["change_vs_year_ago"])
        self.assertIsNotNone(out["heating_oil"]["change_vs_prior_week"])
    def test_core_rounds_to_3_places(self):
        d = {"week_of": "2026-11-23",
             "heating_oil": {"value": 5.40404}, "propane": {"value": 4.116},
             "wholesale": {"value": 4.102}}
        self.assertEqual(u.core(d), ("2026-11-23", 5.404, 4.116, 4.102))

class TestRewriteIndex(unittest.TestCase):
    def test_markers_rewrite_and_assert(self):
        html = "x <!--AUTO:checked_date-->2026-11-21<!--/AUTO--> y"
        out = u.rewrite_index(html, {"checked_date": "2026-11-26"})
        self.assertIn("<!--AUTO:checked_date-->2026-11-26<!--/AUTO-->", out)
    def test_missing_marker_refuses(self):
        with self.assertRaises(ValueError):
            u.rewrite_index("<html>no markers</html>", {"checked_date": "2026-11-26"})
    def test_every_pair_rewritten_and_counted(self):
        html = ("<!--AUTO:week_of_long-->November 16, 2026<!--/AUTO--> and "
                "<!--AUTO:week_of_long-->November 16, 2026<!--/AUTO-->")
        out = u.rewrite_index(html, {"week_of_long": "November 23, 2026"})
        self.assertEqual(out.count("November 23, 2026"), 2)
        self.assertNotIn("November 16", out)

class TestRealIndexMarkers(unittest.TestCase):
    """Loads the REAL index.html shipped in this repo and asserts all five
    AUTO marker keys are present (Tomás, Nov 26, 2026): checked_date,
    week_of_long, heating_oil_price, propane_price, wholesale_price."""
    def test_real_index_has_all_five_marker_keys(self):
        index = Path(__file__).resolve().parent.parent / "index.html"
        html = index.read_text()
        for key in ("checked_date", "week_of_long", "heating_oil_price",
                    "propane_price", "wholesale_price"):
            self.assertIn(f"<!--AUTO:{key}-->", html, f"missing open marker {key}")
            self.assertIn("<!--/AUTO-->", html)
            landed = re.findall(rf'<!--AUTO:{key}-->(.*?)<!--/AUTO-->', html, re.S)
            self.assertTrue(landed and all(v.strip() for v in landed),
                            f"marker {key} present but empty")

if __name__ == "__main__":
    unittest.main()
