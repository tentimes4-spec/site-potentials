#!/usr/bin/env python3
"""
build_map.py - EIA-860M ingest pipeline for the US generation map.

Reads the latest EIA-860M Operating Generators sheet, groups generators by
plant, and rewrites the inline data and panel sections of map.html. Designed
to be re-runnable monthly so /schedule can refresh the map automatically.

Default:
    python3 build_map.py
        Downloads the latest EIA-860M into data/eia860m/, regenerates map.html.

Other modes:
    python3 build_map.py --xlsx PATH       Use a specific local xlsx.
    python3 build_map.py --month YYYY-MM   Use a specific month (downloads if missing).
    python3 build_map.py --no-download     Use the most recent local xlsx; never fetch.
"""

import argparse
import calendar
import json
import re
import sys
import urllib.error
import urllib.request
from collections import defaultdict
from datetime import date
from pathlib import Path

import openpyxl


SCRIPT_DIR = Path(__file__).parent.resolve()
DATA_DIR = SCRIPT_DIR / "data" / "eia860m"
MAP_HTML = SCRIPT_DIR / "map.html"

SKIP_STATES = {"AS", "GU", "MP", "PR", "VI"}

# state -> (region label, full name, FIPS code)
STATE_INFO = {
    "AL": ("Non-RTO Southeast", "Alabama", "01"),
    "AK": ("Other", "Alaska", "02"),
    "AZ": ("WECC (non-CAISO)", "Arizona", "04"),
    "AR": ("MISO / SPP", "Arkansas", "05"),
    "CA": ("CAISO", "California", "06"),
    "CO": ("WECC (non-CAISO)", "Colorado", "08"),
    "CT": ("ISO-NE / NY-ISO", "Connecticut", "09"),
    "DE": ("PJM", "Delaware", "10"),
    "DC": ("PJM", "District of Columbia", "11"),
    "FL": ("Non-RTO Southeast", "Florida", "12"),
    "GA": ("Non-RTO Southeast", "Georgia", "13"),
    "HI": ("Other", "Hawaii", "15"),
    "ID": ("WECC (non-CAISO)", "Idaho", "16"),
    "IL": ("PJM / MISO", "Illinois", "17"),
    "IN": ("PJM / MISO", "Indiana", "18"),
    "IA": ("MISO / SPP", "Iowa", "19"),
    "KS": ("MISO / SPP", "Kansas", "20"),
    "KY": ("PJM / MISO", "Kentucky", "21"),
    "LA": ("MISO / SPP", "Louisiana", "22"),
    "ME": ("ISO-NE / NY-ISO", "Maine", "23"),
    "MD": ("PJM", "Maryland", "24"),
    "MA": ("ISO-NE / NY-ISO", "Massachusetts", "25"),
    "MI": ("PJM / MISO", "Michigan", "26"),
    "MN": ("MISO / SPP", "Minnesota", "27"),
    "MS": ("MISO / SPP", "Mississippi", "28"),
    "MO": ("MISO / SPP", "Missouri", "29"),
    "MT": ("WECC (non-CAISO)", "Montana", "30"),
    "NE": ("MISO / SPP", "Nebraska", "31"),
    "NV": ("WECC (non-CAISO)", "Nevada", "32"),
    "NH": ("ISO-NE / NY-ISO", "New Hampshire", "33"),
    "NJ": ("PJM", "New Jersey", "34"),
    "NM": ("WECC (non-CAISO)", "New Mexico", "35"),
    "NY": ("ISO-NE / NY-ISO", "New York", "36"),
    "NC": ("PJM / MISO", "North Carolina", "37"),
    "ND": ("MISO / SPP", "North Dakota", "38"),
    "OH": ("PJM / MISO", "Ohio", "39"),
    "OK": ("MISO / SPP", "Oklahoma", "40"),
    "OR": ("WECC (non-CAISO)", "Oregon", "41"),
    "PA": ("PJM", "Pennsylvania", "42"),
    "RI": ("ISO-NE / NY-ISO", "Rhode Island", "44"),
    "SC": ("Non-RTO Southeast", "South Carolina", "45"),
    "SD": ("MISO / SPP", "South Dakota", "46"),
    "TN": ("PJM / MISO", "Tennessee", "47"),
    "TX": ("ERCOT", "Texas", "48"),
    "UT": ("WECC (non-CAISO)", "Utah", "49"),
    "VT": ("ISO-NE / NY-ISO", "Vermont", "50"),
    "VA": ("PJM", "Virginia", "51"),
    "WA": ("WECC (non-CAISO)", "Washington", "53"),
    "WV": ("PJM", "West Virginia", "54"),
    "WI": ("MISO / SPP", "Wisconsin", "55"),
    "WY": ("WECC (non-CAISO)", "Wyoming", "56"),
}

REGION_ORDER = [
    "ISO-NE / NY-ISO",
    "PJM",
    "PJM / MISO",
    "MISO / SPP",
    "ERCOT",
    "CAISO",
    "WECC (non-CAISO)",
    "Non-RTO Southeast",
    "Other",
]


def _coerce_float(v):
    if v is None:
        return None
    if isinstance(v, str) and not v.strip():
        return None
    try:
        return float(v)
    except (ValueError, TypeError):
        return None


def _coerce_int(v):
    if v is None:
        return None
    if isinstance(v, str) and not v.strip():
        return None
    try:
        return int(float(v))
    except (ValueError, TypeError):
        return None


def _coerce_str(v):
    if v is None:
        return ""
    s = str(v).strip()
    return s


def parse_xlsx(xlsx_path):
    """Read the Operating sheet and return a list of plant dicts."""
    print(f"Opening {xlsx_path.name}...")
    wb = openpyxl.load_workbook(xlsx_path, read_only=True, data_only=True)
    ws = wb["Operating"]

    plants = {}
    rowcount = 0
    skipped_state = 0
    skipped_coords = 0

    for r in ws.iter_rows(min_row=4, values_only=True):
        if not r or r[2] is None:
            continue
        rowcount += 1

        plant_id = _coerce_int(r[2])
        if plant_id is None:
            continue

        state = _coerce_str(r[6])
        if not state or state in SKIP_STATES or state not in STATE_INFO:
            skipped_state += 1
            continue

        lat = _coerce_float(r[35])
        lng = _coerce_float(r[36])

        cap = _coerce_float(r[12]) or 0.0
        sum_cap = _coerce_float(r[13]) or 0.0
        win_cap = _coerce_float(r[14]) or 0.0
        fuel = _coerce_str(r[16]) or "OT"
        pm = _coerce_str(r[17])
        yr = _coerce_int(r[19])

        if plant_id not in plants:
            plants[plant_id] = {
                "id": plant_id,
                "n": _coerce_str(r[3]),
                "lat": lat,
                "lng": lng,
                "s": state,
                "ba": _coerce_str(r[8]),
                "e": _coerce_str(r[1]),
                "county": _coerce_str(r[7]),
                "tc": 0.0,
                "sc": 0.0,
                "wc": 0.0,
                "g": [],
                "_max_cap": -1.0,
                "_pf": "OT",
            }

        p = plants[plant_id]
        if p["lat"] is None and lat is not None:
            p["lat"] = lat
        if p["lng"] is None and lng is not None:
            p["lng"] = lng

        p["tc"] += cap
        p["sc"] += sum_cap
        p["wc"] += win_cap
        p["g"].append({
            "id": _coerce_str(r[10]),
            "fuel": fuel,
            "cap": round(cap, 2),
            "pm": pm,
            "yr": yr if yr is not None else 0,
        })

        if cap > p["_max_cap"]:
            p["_max_cap"] = cap
            p["_pf"] = fuel

    out = []
    for p in plants.values():
        if p["lat"] is None or p["lng"] is None:
            skipped_coords += 1
            continue
        p["pf"] = p["_pf"]
        del p["_max_cap"]
        del p["_pf"]
        p["tc"] = round(p["tc"], 2)
        p["sc"] = round(p["sc"], 2)
        p["wc"] = round(p["wc"], 2)
        p["g"].sort(key=lambda g: str(g["id"]))
        out.append(p)

    out.sort(key=lambda p: p["id"])
    print(f"  Read {rowcount:,} generator rows.")
    if skipped_state:
        print(f"  Skipped {skipped_state:,} non-CONUS rows.")
    if skipped_coords:
        print(f"  Skipped {skipped_coords:,} plants without coordinates.")
    print(f"  Built {len(out):,} plants in {len({p['s'] for p in out})} states.")
    return out


def build_state_panel(plants):
    counts = defaultdict(int)
    for p in plants:
        counts[p["s"]] += 1

    by_region = defaultdict(list)
    for st in counts:
        region = STATE_INFO[st][0]
        by_region[region].append(st)

    blocks = []
    for region in REGION_ORDER:
        if region not in by_region:
            continue
        section = []
        section.append(f'    <div class="section-title">{region} States</div>')
        for st in sorted(by_region[region], key=lambda s: STATE_INFO[s][1]):
            full = STATE_INFO[st][1]
            cnt = counts[st]
            section.append(
                f'    <div class="layer-toggle">\n'
                f'      <label for="t-{st}">{full} <span style="color:#888;font-size:11px">({cnt:,})</span></label>\n'
                f'      <label class="switch"><input type="checkbox" id="t-{st}" checked><span class="slider"></span></label>\n'
                f'    </div>'
            )
        blocks.append("\n".join(section))
    return '\n    <div class="divider"></div>\n'.join(blocks)


def build_state_layers_js(plants):
    states = sorted({p["s"] for p in plants})
    entries = ",\n      ".join(f"'{s}': L.layerGroup().addTo(map)" for s in states)
    return "    const stateLayers = {\n      " + entries + "\n    };"


def build_wire_toggles_js(plants):
    states = sorted({p["s"] for p in plants})
    return "\n".join(f"    wireToggle('t-{s}', stateLayers['{s}']);" for s in states)


def build_county_fips_js(plants):
    states = sorted({p["s"] for p in plants})
    fips = sorted({STATE_INFO[s][2] for s in states})
    fips_str = ", ".join(f'"{f}"' for f in fips)
    return f"        const fipsCodes = [{fips_str}];"


def build_stats_html(plants):
    n_plants = len(plants)
    n_gens = sum(len(p["g"]) for p in plants)
    total_mw = sum(p["tc"] for p in plants)
    n_states = len({p["s"] for p in plants})
    return (
        f'    <div class="stat"><div class="stat-value">{n_plants:,}</div><div class="stat-label">Plants</div></div>\n'
        f'    <div class="stat"><div class="stat-value">{n_gens:,}</div><div class="stat-label">Generators</div></div>\n'
        f'    <div class="stat"><div class="stat-value">{int(total_mw):,}</div><div class="stat-label">Total MW</div></div>\n'
        f'    <div class="stat"><div class="stat-value">{n_states}</div><div class="stat-label">States</div></div>'
    )


def _replace_marked(html, name, content, html_comment=True):
    if html_comment:
        begin = f"<!-- BEGIN AUTOGEN {name} -->"
        end = f"<!-- END AUTOGEN {name} -->"
    else:
        begin = f"// BEGIN AUTOGEN {name}"
        end = f"// END AUTOGEN {name}"
    pattern = re.compile(re.escape(begin) + r".*?" + re.escape(end), re.DOTALL)
    replacement = f"{begin}\n{content}\n    {end}"
    new_html, n = pattern.subn(replacement, html)
    if n == 0:
        raise RuntimeError(f"Marker pair {name} not found.")
    if n > 1:
        raise RuntimeError(f"Marker pair {name} found {n} times; expected 1.")
    return new_html


def update_html(html_path, plants):
    html = html_path.read_text(encoding="utf-8")

    backup = html_path.with_suffix(".html.bak")
    if not backup.exists():
        backup.write_text(html, encoding="utf-8")
        print(f"  Wrote backup to {backup.name}")

    plants_json = json.dumps(plants, separators=(",", ":"))
    lines = html.splitlines(keepends=True)
    found = False
    for i, ln in enumerate(lines):
        stripped = ln.lstrip()
        if stripped.startswith("const plants = "):
            indent = ln[: len(ln) - len(stripped)]
            lines[i] = f"{indent}const plants = {plants_json};\n"
            found = True
            break
    if not found:
        raise RuntimeError("Could not find 'const plants = ' line.")
    html = "".join(lines)

    html = _replace_marked(html, "STATE_PANEL", build_state_panel(plants), html_comment=True)
    html = _replace_marked(html, "STATS", build_stats_html(plants), html_comment=True)
    html = _replace_marked(html, "STATE_LAYERS", build_state_layers_js(plants), html_comment=False)
    html = _replace_marked(html, "WIRE_TOGGLES", build_wire_toggles_js(plants), html_comment=False)
    html = _replace_marked(html, "COUNTY_FIPS", build_county_fips_js(plants), html_comment=False)

    html_path.write_text(html, encoding="utf-8")
    size_kb = html_path.stat().st_size / 1024
    print(f"  Wrote {html_path.name} ({size_kb:,.1f} KB)")


_LIVE_URL = "https://www.eia.gov/electricity/data/eia860m/xls/{month}_generator{year}.xlsx"
_ARCHIVE_URL = "https://www.eia.gov/electricity/data/eia860m/archive/xls/{month}_generator{year}.xlsx"


def _looks_like_xlsx(data):
    # xlsx is a zip archive; first 4 bytes are PK\x03\x04 (or PK\x05\x06 for empty zip).
    return len(data) > 1_000_000 and data[:2] == b"PK"


def _try_fetch(url):
    """Fetch URL and return body bytes only if it's a real xlsx; else None."""
    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": "GroundFloorEnergy-MapBuilder/1.0"}
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            final_url = resp.geturl()
            data = resp.read()
        if final_url != url:
            print(f"  -> redirected to {final_url}; not the expected xlsx")
            return None
        if not _looks_like_xlsx(data):
            print(f"  -> response is not a valid xlsx ({len(data):,} bytes)")
            return None
        return data
    except urllib.error.HTTPError as e:
        print(f"  -> HTTP {e.code}")
        return None
    except Exception as e:
        print(f"  -> error: {e}")
        return None


def download_xlsx(target_dir, requested_month=None):
    target_dir.mkdir(parents=True, exist_ok=True)

    if requested_month:
        y, m = (int(x) for x in requested_month.split("-"))
        candidates = [(y, m)]
    else:
        today = date.today()
        candidates = []
        for delta in range(0, 4):
            m = today.month - delta
            y = today.year
            if m <= 0:
                m += 12
                y -= 1
            candidates.append((y, m))

    for y, m in candidates:
        target = target_dir / f"{y:04d}-{m:02d}.xlsx"
        if target.exists() and target.stat().st_size > 1_000_000:
            print(f"Using existing {target.name}")
            return target

        month_name = calendar.month_name[m].lower()

        # Try live URL first (only the most recent month is hosted here),
        # then the archive URL (older months).
        for url in (
            _LIVE_URL.format(month=month_name, year=y),
            _ARCHIVE_URL.format(month=month_name, year=y),
        ):
            print(f"Trying {url}")
            data = _try_fetch(url)
            if data is not None:
                target.write_bytes(data)
                print(f"  Saved {target.name} ({len(data) / 1024:,.1f} KB)")
                return target

    raise RuntimeError(
        "Could not download a valid EIA-860M xlsx for any of the last 4 months."
    )


def find_latest_local(data_dir):
    if not data_dir.exists():
        return None
    files = sorted(data_dir.glob("????-??.xlsx"))
    return files[-1] if files else None


def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--xlsx", type=Path, help="Path to a specific xlsx file.")
    parser.add_argument("--month", help="Use month YYYY-MM (downloads if missing).")
    parser.add_argument("--no-download", action="store_true",
                        help="Use the most recent local xlsx; never fetch.")
    parser.add_argument("--map-html", type=Path, default=MAP_HTML,
                        help="Path to map.html.")
    args = parser.parse_args()

    if args.xlsx:
        xlsx = args.xlsx
        if not xlsx.exists():
            print(f"error: {xlsx} not found", file=sys.stderr)
            return 2
    elif args.no_download:
        xlsx = find_latest_local(DATA_DIR)
        if xlsx is None:
            print(f"error: no local xlsx in {DATA_DIR}", file=sys.stderr)
            return 2
        print(f"Using latest local: {xlsx.name}")
    else:
        xlsx = download_xlsx(DATA_DIR, args.month)

    plants = parse_xlsx(xlsx)
    if not plants:
        print("error: no plants parsed", file=sys.stderr)
        return 1

    update_html(args.map_html, plants)
    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
