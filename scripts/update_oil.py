#!/usr/bin/env python3
"""scripts/update_oil.py — RI Oil Check nightly EIA update (v2, Nov 26, 2026)
DRAFT ONLY — not seeded. Paste path in repo: scripts/update_oil.py

Sources, in order:
  PRIMARY: EIA API v2 when the EIA_API_KEY secret is set (series below);
           otherwise the EIA SHOPP page tables (ids rh / rp / wh).
  SECOND CHECK (always): the RI series XLS.
  A new week is applied ONLY when primary and XLS agree exactly on
  week_of + all three values. Disagreement / unreachable / unparseable:
  exit 1, write nothing. Never guess.

XLS endpoint CONFIRMED by test fetch Nov 26, 2026:
  https://www.eia.gov/dnav/pet/xls/PET_PRI_WFR_DCUS_SRI_W.xls
  (HTTP 200, application/vnd.ms-excel, real workbook, sheet "Data 1",
  sourcekeys W_EPD2F_PRS_SRI_DPG / W_EPD2F_PWR_SRI_DPG / W_EPLLPA_PRS_SRI_DPG.
  The /hist_xls/ variant in the v1 draft returns 404 — do not use it.)

Parsers are pinned to snapshots saved Nov 26, 2026
(tests/fixtures/eia_shopp_page.html, tests/fixtures/eia_ri_series.xls)
and covered by tests/test_update_oil.py against the known-good week:
  week of 2026-11-23: heating oil 5.404, propane 4.116, wholesale 4.102;
  changes vs prior week -0.272 / -0.007 / -0.379; vs year ago +1.526 / +0.553 / +1.509.

All date stamps use America/New_York.

index.html is rewritten ONLY through marked placeholders:
  <!--AUTO:checked_date-->...<!--/AUTO-->, <!--AUTO:week_of_long-->...,
  <!--AUTO:heating_oil_price-->... ( likewise propane_price, wholesale_price )
If a marker pair is missing the script exits 1 and writes nothing.
After rewriting, the script asserts the new figure is present inside its
markers before saving. (One-time marker patch to index.html is required
before this script is seeded; the patch is listed in ASSESSMENT.md.)
"""
import json, os, re, sys
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

ET = ZoneInfo("America/New_York")
TODAY_ET = datetime.now(ET).date()
ROOT = Path(__file__).resolve().parent.parent
PRICES = ROOT / "data" / "prices.json"
INDEX = ROOT / "index.html"
EIA_PAGE = "https://www.eia.gov/petroleum/heatingoilpropane/"
EIA_XLS = "https://www.eia.gov/dnav/pet/xls/PET_PRI_WFR_DCUS_SRI_W.xls"
EIA_API = "https://api.eia.gov/v2/seriesid/PET.{series}.W"
SERIES = {  # XLS "Data 1" sourcekeys, same IDs in API v2
    "heating_oil": "W_EPD2F_PRS_SRI_DPG",
    "wholesale": "W_EPD2F_PWR_SRI_DPG",
    "propane": "W_EPLLPA_PRS_SRI_DPG",
}
FUELS = ("heating_oil", "propane", "wholesale")

# ---------- EIA page parser (pinned to the saved snapshot) ----------
# The SHOPP page carries three tables: id="rh" residential heating oil,
# id="rp" residential propane, id="wh" wholesale heating oil. Each table's
# header row carries the week date as MM/DD/YY and each state row is
# <td>Rhode Island</td><td>VALUE</td><td>WEEK-AGO CHANGE</td><td>YEAR-AGO CHANGE</td>
_TABLE_FOR = {"heating_oil": "rh", "propane": "rp", "wholesale": "wh"}

def parse_eia_page(html: str) -> dict:
    out = {}
    weeks = set()
    for fuel, tid in _TABLE_FOR.items():
        m = re.search(rf'<table[^>]*id="{tid}"[^>]*>(.*?)</table>', html, re.S)
        if not m:
            raise ValueError(f"EIA page: table id={tid} not found")
        table = m.group(1)
        d = re.search(r'(\d{1,2})/(\d{1,2})/(\d{2})', table)
        if not d:
            raise ValueError(f"EIA page: no week date in table {tid}")
        weeks.add(date(2000 + int(d.group(3)), int(d.group(1)), int(d.group(2))))
        row = re.search(
            r'<td>Rhode Island</td>\s*<td>([\d.]+)</td>\s*'
            r'<td>(-?[\d.]+)<span[^>]*></span></td>\s*'
            r'<td>(-?[\d.]+)<span[^>]*></span></td>', table)
        if not row:
            raise ValueError(f"EIA page: Rhode Island row not found in table {tid}")
        out[fuel] = {"value": float(row.group(1)),
                     "change_vs_prior_week": float(row.group(2)),
                     "change_vs_year_ago": float(row.group(3))}
    if len(weeks) != 1:
        raise ValueError(f"EIA page: tables disagree on week {weeks}")
    out["week_of"] = weeks.pop().isoformat()
    return out

# ---------- EIA XLS parser (pinned to the saved snapshot) ----------
# Workbook sheet "Data 1": row 1 sourcekeys, row 2 headers, then weekly
# rows [excel_serial_date, heating_oil, wholesale, propane], ascending.
def parse_eia_xls(data: bytes) -> dict:
    import io, xlrd
    wb = xlrd.open_workbook(file_contents=data)
    sh = wb.sheet_by_name("Data 1")
    keys = [str(sh.cell_value(1, c)).strip() for c in range(1, 4)]
    expect = [SERIES["heating_oil"], SERIES["wholesale"], SERIES["propane"]]
    if keys != expect:
        raise ValueError(f"EIA XLS: sourcekeys changed {keys} != {expect}")
    rows = []
    for r in range(3, sh.nrows):
        serial = sh.cell_value(r, 0)
        if not isinstance(serial, (int, float)):
            continue
        vals = [sh.cell_value(r, c) for c in range(1, 4)]
        if not all(isinstance(v, (int, float)) for v in vals):
            continue
        d = xlrd.xldate_as_datetime(serial, wb.datemode).date()
        rows.append((d, vals))
    if not rows:
        raise ValueError("EIA XLS: no data rows")
    rows.sort()
    latest_d, latest_v = rows[-1]
    prior = dict(rows)
    out = {"week_of": latest_d.isoformat()}
    for fuel, v in zip(("heating_oil", "wholesale", "propane"), latest_v):
        out[fuel] = {"value": float(v)}
    for fuel in ("heating_oil", "wholesale", "propane"):
        i = ("heating_oil", "wholesale", "propane").index(fuel)
        pw = prior.get(latest_d - timedelta(days=7))
        ya = prior.get(latest_d - timedelta(days=364))
        if pw is None or ya is None:
            raise ValueError("EIA XLS: prior-week or year-ago row missing")
        out[fuel]["prior_week_value"] = float(pw[i])
        out[fuel]["year_ago_value"] = float(ya[i])
        out[fuel]["change_vs_prior_week"] = round(out[fuel]["value"] - pw[i], 3)
        out[fuel]["change_vs_year_ago"] = round(out[fuel]["value"] - ya[i], 3)
    return out

# ---------- EIA API v2 parser (primary when a key is provisioned) ----------
def parse_eia_api(payload: dict, fuel: str) -> dict:
    rows = payload["response"]["data"]
    rows = sorted(rows, key=lambda r: r["period"])
    if len(rows) < 53:
        raise ValueError(f"EIA API: only {len(rows)} rows for {fuel}")
    latest, prior_w, year_a = rows[-1], rows[-2], rows[-53]
    v = float(latest["value"])
    return {"week_of": latest["period"], "value": v,
            "prior_week_value": float(prior_w["value"]),
            "year_ago_value": float(year_a["value"]),
            "change_vs_prior_week": round(v - float(prior_w["value"]), 3),
            "change_vs_year_ago": round(v - float(year_a["value"]), 3)}

def fetch_api(key: str) -> dict:
    out, weeks = {}, set()
    for fuel in FUELS:
        series = SERIES["wholesale" if fuel == "wholesale" else fuel]
        r = requests.get(EIA_API.format(series=series),
                         params={"api_key": key}, timeout=60)
        r.raise_for_status()
        one = parse_eia_api(r.json(), fuel)
        weeks.add(one.pop("week_of"))
        out[fuel] = one
    if len(weeks) != 1:
        raise ValueError(f"EIA API: series disagree on week {weeks}")
    out["week_of"] = weeks.pop()
    return out

# ---------- agreement + apply ----------
def core(d: dict) -> tuple:
    return (d["week_of"],) + tuple(d[f]["value"] for f in ("heating_oil", "propane", "wholesale"))

def rewrite_index(html: str, values: dict) -> str:
    # A marker pair may occur several times (week and price appear in two
    # FAQ spots plus the static propane/wholesale lines). EVERY occurrence
    # is rewritten, and every occurrence is asserted to hold the new value.
    for key, val in values.items():
        pat = re.compile(rf'(<!--AUTO:{key}-->).*?(<!--/AUTO-->)', re.S)
        if not pat.search(html):
            raise ValueError(f"index.html: marker pair AUTO:{key} missing — refusing to write")
        html = pat.sub(lambda m: f"{m.group(1)}{val}{m.group(2)}", html)
        landed = re.findall(rf'<!--AUTO:{key}-->(.*?)<!--/AUTO-->', html, re.S)
        assert landed and all(v == val for v in landed), \
            f"index.html: {key} rewrite did not land everywhere ({landed!r} != {val!r})"
    return html

def main() -> int:
    current = json.loads(PRICES.read_text())
    live_week = current["heating_oil"]["week_of"]
    key = os.environ.get("EIA_API_KEY")
    try:
        primary = fetch_api(key) if key else parse_eia_page(
            requests.get(EIA_PAGE, timeout=60).text)
        second = parse_eia_xls(requests.get(EIA_XLS, timeout=60).content)
    except Exception as e:
        print(f"UNVERIFIED: source fetch/parse failed: {e}")
        return 1
    if core(primary) != core(second):
        print(f"UNVERIFIED: primary {core(primary)} != XLS {core(second)}")
        return 1
    new = second  # XLS carries prior/year-ago absolutes; both agree on core
    if new["week_of"] <= live_week:
        print(f"No new week (live {live_week}, EIA {new['week_of']}).")
        return 0
    week = date.fromisoformat(new["week_of"])
    for fuel, field in (("heating_oil", "heating_oil"), ("propane", "propane"),
                        ("wholesale", "wholesale_heating_oil")):
        e = current[field]
        e.update({"value": new[fuel]["value"],
                  "display_value": round(new[fuel]["value"], 2),
                  "week_of": new["week_of"],
                  "published": (week + timedelta(days=2)).isoformat(),
                  "prior_week_value": new[fuel]["prior_week_value"],
                  "year_ago_value": new[fuel]["year_ago_value"],
                  "change_vs_prior_week": new[fuel]["change_vs_prior_week"],
                  "change_vs_year_ago": new[fuel]["change_vs_year_ago"]})
    current["checked_date"] = TODAY_ET.isoformat()
    long_week = week.strftime("%B %-d, %Y")
    new_index = rewrite_index(INDEX.read_text(), {
        "checked_date": TODAY_ET.isoformat(),
        "week_of_long": long_week,
        "heating_oil_price": f"${new['heating_oil']['value']:.3f}",
        "propane_price": f"${new['propane']['value']:.3f}",
        "wholesale_price": f"${new['wholesale']['value']:.3f}",
    })
    PRICES.write_text(json.dumps(current, indent=1, sort_keys=True) + "\n")
    INDEX.write_text(new_index)
    print(f"Applied verified week {new['week_of']}: heating oil "
          f"${new['heating_oil']['value']:.3f}, checked {TODAY_ET} ET.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
