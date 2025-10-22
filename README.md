# Document Helper: PDF Tools

Utilities to:
- minimize a PDF by a target percent and save as a new file
- split a PDF into N separate parts and save each part as its own PDF

These scripts live in `for_pdf/`:
- `for_pdf/pdf_minimize.py`
- `for_pdf/pdf_devider.py`

## Requirements

- Python 3.9+
- Install dependencies:
  - required: PyPDF2, Pillow
  - optional (for stronger compression): Ghostscript

Install with pip:

```bash
pip install PyPDF2 Pillow
# optional on macOS for stronger compression
brew install ghostscript
```

Note: the scripts will also try to auto-install missing Python deps on first run.

## Minimize a PDF by percent

Reduce file size by a given percent (best effort; actual reduction depends on PDF contents). You can also compress only specific pages while keeping the rest unchanged.

Usage:

```bash
python for_pdf/pdf_minimize.py INPUT.pdf OUTPUT.pdf -p PERCENT [options]
```

Key options:
- `-p, --percent`: desired reduction percent (0–100)
- `--pages "LIST"`: compress only selected pages, keep others original; pages are 1-indexed. Examples: `"3,5,7-10"`, `"1-2,4,9"`
- `-m, --method`: `auto` (default), `ghostscript`, or `pypdf2`
  - `auto`: uses Ghostscript if available and percent ≥ 35, else PyPDF2
  - `ghostscript`: whole-document compression (ignores `--pages`)
  - `pypdf2`: Python-only image compression (works with `--pages`)
- `--recompress-jpeg`: also recompress already-JPEG images (more reduction, lower quality)
- `--gs-dpi`, `--gs-jpegq`, `--gs-pdfsettings`: advanced Ghostscript tuning

Examples:

- Reduce to ~40% smaller and save to a new file:

```bash
python for_pdf/pdf_minimize.py \
  '/Users/foo/projects/video_cutter/original.pdf' \
  '/Users/foo/projects/video_cutter/small.pdf' \
  --percent 40
```

- Compress only specific pages (3,5,7–10), keep other pages untouched:

```bash
python for_pdf/pdf_minimize.py \
  'input.pdf' \
  'output_selected_pages.pdf' \
  --percent 50 \
  --pages '3,5,7-10' \
  -m pypdf2
```

Check sizes on macOS:

```bash
du -h 'INPUT.pdf' 'OUTPUT.pdf'
# or exact bytes
stat -f%z 'INPUT.pdf'
stat -f%z 'OUTPUT.pdf'
```

Notes:
- Actual reduction is often less than the target; some PDFs have limited compression potential.
- Ghostscript typically achieves stronger reduction on image-heavy PDFs.
- Always review output quality (especially when using `--recompress-jpeg`).

## Split a PDF into N parts

Split a PDF into N nearly equal parts. Pages are preserved in order; parts are distributed as evenly as possible.

Usage:

```bash
python for_pdf/pdf_devider.py INPUT.pdf -n N [options]
```

Options:
- `-n, --parts N`: number of parts (≥ 1)
- `-o, --output-dir DIR`: directory to write output PDFs (default: same as input)
- `--output-prefix NAME`: base name for outputs (default: input filename stem)
- `--overwrite`: allow overwriting existing files

Examples:

```bash
# split into 3 parts, write next to input
python for_pdf/pdf_devider.py 'source.pdf' -n 3

# split into 5 parts to a specific folder with custom prefix
python for_pdf/pdf_devider.py 'source.pdf' -n 5 -o './out' --output-prefix 'mydoc'
```

Output naming pattern:
- `<basename>_part_<i>of<N>.pdf` (e.g., `source_part_1of3.pdf`)

## Troubleshooting

- If Ghostscript isn’t found, install it via Homebrew: `brew install ghostscript`.
- If you see minimal reduction, try a higher percent, enable `--recompress-jpeg`, or use `-m ghostscript`.
- Ensure paths are quoted in zsh if they contain spaces.

## Development and tests

Run tests locally with pytest:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements-test.txt
python -m pytest -q
```

Continuous Integration:
- GitHub Actions workflow at `.github/workflows/python-tests.yml` runs tests on push/PR across Python 3.10–3.12.
- It installs `requirements-test.txt` and executes `pytest`.
