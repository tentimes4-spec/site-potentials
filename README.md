# US Generation Map (Site Potentials)

Interactive map of every operating US power generator, refreshed monthly from
the [EIA-860M](https://www.eia.gov/electricity/data/eia860m/) inventory. The
map shows ~14,000 plants and ~28,000 generators across all 50 states plus DC,
color-coded by primary fuel and sized by nameplate capacity.

**Live URL: https://tentimes4-spec.github.io/site-potentials/**

## How it stays current

A GitHub Actions workflow (`.github/workflows/refresh.yml`) fires on the 5th
of each month at ~9:37 AM ET. On every run it:

1. Downloads the latest EIA-860M xlsx from `eia.gov`
2. Runs `build_map.py` to regenerate `map.html`
3. Commits the new `map.html` back to the repo if anything changed
4. Redeploys GitHub Pages so the live URL serves the new version

You can also fire the workflow on demand from the Actions tab of the repo:
**Actions** → **Monthly map refresh** → **Run workflow**.

## Files in this repo

| Path | What it is |
|------|------------|
| `map.html` | The map. Open the live URL above, or open this file directly in a browser. |
| `build_map.py` | The ingest script. Reads the xlsx, regenerates `map.html`. |
| `.github/workflows/refresh.yml` | The Actions workflow that runs the script monthly. |
| `.gitignore` | Keeps downloaded xlsx files and local logs out of the repo. |

## Running locally

If you want to test changes to `build_map.py` or rebuild `map.html` from a
specific month without waiting for the cron, you can run it on your Mac:

```bash
cd "/Users/jasonmasters/Desktop/Ground Floor Energy/Research/Site Potentials"
python3 build_map.py
```

Defaults: downloads the latest EIA-860M into `data/eia860m/`, regenerates
`map.html` next to the script. The xlsx files are cached locally so re-runs
of the same month do not re-download.

Other modes:
```bash
python3 build_map.py --xlsx data/eia860m/2026-02.xlsx   # specific local file
python3 build_map.py --month 2026-03                    # specific month
python3 build_map.py --no-download                      # use newest local file
```

Dependencies: Python 3.9+ and `openpyxl` (install with `pip3 install --user openpyxl`).

## Keeping your local copy in sync

The Action updates the *cloud* copy of `map.html` every month. Your local
copy stays at whatever version you last pulled. You have two options:

- **Just use the live URL.** Bookmark `https://tentimes4-spec.github.io/site-potentials/`
  and the latest map is always one click away. No git knowledge needed.
- **Pull the latest into your local folder.** When you want the file on your
  Mac to match the cloud:
  ```bash
  cd "/Users/jasonmasters/Desktop/Ground Floor Energy/Research/Site Potentials"
  git pull
  ```

## How the map.html edits work

`build_map.py` rewrites six narrow sections of `map.html` and leaves
everything else untouched. Five of them are bracketed by HTML/JS comment
markers like `<!-- BEGIN AUTOGEN STATE_PANEL -->` and
`<!-- END AUTOGEN STATE_PANEL -->`; the sixth is the inline
`const plants = [...]` line. As long as those markers stay in the file, you
can edit any surrounding HTML, CSS, or JS by hand and the script will respect
your edits.

## Data source and filter

Reads only the `Operating` sheet from EIA-860M. Skips `Planned`, `Retired`,
`Canceled`, and the Puerto Rico `_PR` sheets. US territories (AS, GU, MP, PR,
VI) are dropped from the result so the map is CONUS + AK + HI + DC.
