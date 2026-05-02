# US Generation Map (Site Potentials)

Interactive map of every operating US power generator. Data comes from the
[EIA-860M](https://www.eia.gov/electricity/data/eia860m/) monthly preliminary
inventory; the build script downloads the latest file and rewrites `map.html`
in place so the map can be refreshed every month.

## Files

| Path | What it is |
|------|------------|
| `map.html` | The map. Open directly in a browser (file://). |
| `build_map.py` | Ingest script. Reads the xlsx, regenerates `map.html`. |
| `data/eia860m/YYYY-MM.xlsx` | Downloaded EIA-860M files, one per month. |
| `map.html.bak` | One-time backup taken before the first script run. |

## Usage

### Refresh from the latest EIA-860M (typical case)

```bash
cd "/Users/jasonmasters/Desktop/Ground Floor Energy/Research/Site Potentials"
python3 build_map.py
```

The script tries the current month, then walks backward up to four months
to find the most recent published file. EIA only hosts the latest at
`/xls/`; older months live at `/archive/xls/`. Both paths are tried.

Downloaded files are saved to `data/eia860m/YYYY-MM.xlsx` and reused on
later runs (no redownload if the file already exists).

### Run against a specific local file

```bash
python3 build_map.py --xlsx data/eia860m/2026-02.xlsx
```

### Run offline (use the most recent local file)

```bash
python3 build_map.py --no-download
```

### Pin to a specific month

```bash
python3 build_map.py --month 2026-03
```

## How the script edits map.html

`build_map.py` only touches six pieces of the file. Everything else is
preserved byte-for-byte.

1. The `const plants = [...]` line (the inline JSON dataset).
2. The state-toggle list in the layer panel, between
   `<!-- BEGIN AUTOGEN STATE_PANEL -->` and `<!-- END AUTOGEN STATE_PANEL -->`.
3. The four stat values (Plants / Generators / Total MW / States), between
   `<!-- BEGIN AUTOGEN STATS -->` and `<!-- END AUTOGEN STATS -->`.
4. The `stateLayers` declaration in JS, between
   `// BEGIN AUTOGEN STATE_LAYERS` and `// END AUTOGEN STATE_LAYERS`.
5. The `wireToggle` calls in JS, between
   `// BEGIN AUTOGEN WIRE_TOGGLES` and `// END AUTOGEN WIRE_TOGGLES`.
6. The county FIPS array used by the Census tigerweb fetch, between
   `// BEGIN AUTOGEN COUNTY_FIPS` and `// END AUTOGEN COUNTY_FIPS`.

If you edit the surrounding HTML or JS by hand, leave the marker pairs
intact and the script will keep working.

## Idempotency

Running the script twice with the same xlsx produces a byte-identical
`map.html`. Plants are sorted by Plant ID and generators are sorted by
Generator ID so the diff between months is minimal.

## Data filter

Only the `Operating` sheet is read. `Planned`, `Retired`, `Canceled`, and
the Puerto Rico `_PR` sheets are skipped. US territories (AS, GU, MP, PR,
VI) are dropped from the result.

## Monthly automation

The next step is wiring this into `/schedule` so the script runs once a
month and the map stays current without manual work. The cron-side
command is just:

```bash
python3 "/Users/jasonmasters/Desktop/Ground Floor Energy/Research/Site Potentials/build_map.py"
```

EIA typically publishes the new EIA-860M around the 22nd of each month, so
running on the 5th of the following month gives a comfortable buffer.

## Dependencies

- Python 3.9 or newer
- `openpyxl` (already installed; verified on this machine)
- Network access to `www.eia.gov` for the download path
