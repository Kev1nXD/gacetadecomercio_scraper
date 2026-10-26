# Gaceta de Comercio Scraper

Scrapy scraper for [Gaceta Electrónica de Comercio](https://gacetadecomercio.gob.bo/).
Collects publication records across all available types and dates, retrieves their
content, and saves PDF documents or full publication text with company metadata.

## Requirements

- Python 3.11+
- Internet access to `servicios.seprec.gob.bo`

Run the following commands from the project root. Examples use Windows PowerShell.

## Installation

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## Usage

Collect all pages and save a CSV with the downloaded files:

```powershell
.\.venv\Scripts\python.exe main.py
```

Start with a limited run:

```powershell
.\.venv\Scripts\python.exe main.py -a max_pages=1
```

Save files without a CSV:

```powershell
.\.venv\Scripts\python.exe main.py -a output_mode=files
```

Choose an output directory:

```powershell
.\.venv\Scripts\python.exe main.py -a output_dir=output/sample
```

| Argument | Default | Description |
| --- | --- | --- |
| `output_mode` | `csv` | `csv` saves a table and files; `files` saves files only. |
| `output_dir` | Project's `output/` directory | Base directory for timestamped runs. Relative paths resolve from the working directory. |
| `max_sleep` | 5 seconds (or `RATE_LIMIT_MAX_DELAY`) | Positive integer setting the maximum random pause before each request. Must be at least `RATE_LIMIT_MIN_DELAY`. |
| `max_pages` | Unlimited | Positive integer limiting listing pages **per publication type**. Detail requests for those pages still run. |


## Output

Each run uses a separate directory named with local time in `YYYYMMDD_HHMMSS_microseconds` format:

```text
output/
└── 20261026_143000_123456/
    ├── publications_20261026_143000_123456.csv
    └── files/
        ├── Example Company_00123.pdf
        ├── Example Company_00123_2.pdf
        └── Another Company_00456.txt
```

Files are named `company_name_registration_number.pdf` or `.txt`. Unsafe filename
characters are replaced; company names and registration numbers are each limited
to 250 characters in filenames.
Filesystem filename and path length limits still apply. Missing values use placeholders. Existing filenames receive
numeric suffixes (`_2`, `_3`, ...), so separate publications do not overwrite files.

The pipeline prefers a valid PDF from `documento`. If no PDF is saved, it saves
`textoCompleto` as TXT when available. Text is preserved as returned by the
API, including any markup. Invalid PDF data is logged and skipped.

CSV contains exactly three columns:

| Column | Value |
| --- | --- |
| `company_name` | Company name from the listing's `empresa.razonSocial`. |
| `registration_number` | Registration number from `empresa.matricula`. |
| `file_name` | Saved file path relative to the timestamped run directory. Empty if no content could be saved. |


To choose an exact CSV destination, use Scrapy's `-O` option:

```powershell
.\.venv\Scripts\python.exe main.py -a max_pages=1 -O output/report.csv
```

The supplied filename is preserved. `-O` overwrites it; `-o` appends and can add
another header on subsequent runs. Documents still go to the timestamped run
directory, and CSV file paths remain relative to that directory. In `files` mode,
CSV exports are disabled even if `-o` or `-O` is supplied.

## Collection flow

1. Fetch publication types with `POST /api/publicaciones/catalogos/lista`.
2. Fetch listings with `POST /api/publicaciones`, requesting 100 records per page.
3. Schedule `GET /api/publicaciones/{id}` once per unique publication ID in the run.
4. Decode and save the PDF, or save full text when no PDF is available.
5. Export company metadata and the saved file path to CSV when enabled.

API base URL: `https://servicios.seprec.gob.bo`.
Pagination uses the actual number of returned rows because the server may return
fewer records than requested. Pages within each type are fetched sequentially.

## Request pacing and retries

Set the maximum random sleep from the command line:

```powershell
.\.venv\Scripts\python.exe main.py -a max_sleep=10
```

This selects a random integer delay from 1 to 10 seconds for each request.
Omitting max_sleep preserves RATE_LIMIT_MAX_DELAY. This argument overrides that
setting when both are supplied; HTTP 429 cooldowns remain separate and may be longer.


One request runs at a time. Before each request, including retries, the middleware
waits a random integer between RATE_LIMIT_MIN_DELAY and RATE_LIMIT_MAX_DELAY
seconds (1–5 by default). AutoThrottle is disabled and
Scrapy's additional download delay is zero.

| Setting in `gaceta/settings.py` | Default |
| --- | --- |
| `RATE_LIMIT_MIN_DELAY` | 1 second |
| `RATE_LIMIT_MAX_DELAY` | 5 seconds |
| `RATE_LIMIT_BACKOFF` | 30 seconds |
| `RATE_LIMIT_MAX_BACKOFF` | 60 seconds |
| `RETRY_TIMES` | 3 retries |
| `DOWNLOAD_TIMEOUT` | 30 seconds |

HTTP 429 triggers a shared cooldown, initially 30 seconds and then up to 60 seconds
for consecutive responses. The 60-second cap also applies to longer `Retry-After`
values, so retries may occur before the server permits access and may fail again.
A successful response resets the backoff counter. Request failures remaining after
retries close the spider. Random delays and generated User-Agents do not guarantee
that the site will accept requests.

## Logs and completion summary

At shutdown, the spider logs a summary such as:

```text
Collection summary: found=100, saved=97, not_saved=3, files_saved=97, reason=finished, max_pages=1
```

- `found`: unique publication IDs encountered on listing pages in this run.
- `saved`: publications with a successfully saved PDF or TXT.
- `not_saved`: found minus saved, including failures and unfinished work.
- `files_saved`: successfully written files.
- `reason`: why the spider closed.
- `max_pages`: configured per-type page limit or `unlimited`.

These counters describe this run, not the website's total database. `saved` counts
content files, not confirmation that CSV export succeeded. Check error logs and
Scrapy's feed-export stats as well. A `finished` reason alone does not establish
that the whole archive was collected; `max_pages` intentionally limits coverage.


## Limitations

- Resume and failed-publication recovery are not implemented. Restarting creates a new run.
- Missing content is logged and still produces a CSV row with an empty `file_name`.
- A PDF signature check detects obvious non-PDF responses; it is not full document validation.