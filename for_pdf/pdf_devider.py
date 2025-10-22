#!/usr/bin/env python3
"""
PDF Divider Script

Split a PDF into N separate parts and save into separate PDF files.

- Splits pages as evenly as possible across parts.
- Preserves original page order.
- Outputs files named like: <name>_part_<i>of<N>.pdf

Usage examples:
  python pdf_devider.py input.pdf -n 3
  python pdf_devider.py input.pdf -n 5 -o /path/to/output_dir
  python pdf_devider.py input.pdf -n 4 --output-prefix mydoc
  python pdf_devider.py input.pdf -n 2 --overwrite
"""

import argparse
import os
import sys
from pathlib import Path
from typing import List, Tuple

# Lazy import with auto-install
try:
    from PyPDF2 import PdfReader, PdfWriter
except Exception:  # pragma: no cover
    import subprocess
    print("Installing PyPDF2...", file=sys.stderr)
    subprocess.check_call([sys.executable, "-m", "pip", "install", "PyPDF2"])  # noqa: S603,S607
    from PyPDF2 import PdfReader, PdfWriter


def compute_chunks(total_pages: int, n_parts: int) -> List[Tuple[int, int]]:
    """Return a list of (start_index, end_index) page ranges (0-based, inclusive) for N parts.

    The first `remainder` parts will have one extra page when total_pages is not divisible by n_parts.
    """
    if n_parts <= 0:
        raise ValueError("n_parts must be >= 1")
    if total_pages <= 0:
        raise ValueError("PDF must have at least one page")

    parts = min(n_parts, total_pages)  # Do not create empty parts
    base = total_pages // parts
    rem = total_pages % parts

    ranges: List[Tuple[int, int]] = []
    start = 0
    for i in range(parts):
        size = base + (1 if i < rem else 0)
        end = start + size - 1
        ranges.append((start, end))
        start = end + 1
    return ranges


def split_pdf(input_path: str, n_parts: int, output_dir: str | None = None,
              output_prefix: str | None = None, overwrite: bool = False) -> list[str]:
    """Split the PDF at input_path into n_parts and write files to output_dir.

    Returns list of written file paths.
    """
    if not os.path.exists(input_path):
        raise FileNotFoundError(f"Input file not found: {input_path}")

    reader = PdfReader(input_path)
    total = len(reader.pages)
    if total == 0:
        raise ValueError("Input PDF has no pages")

    ranges = compute_chunks(total, n_parts)

    in_path = Path(input_path)
    out_dir = Path(output_dir) if output_dir else in_path.parent
    out_dir.mkdir(parents=True, exist_ok=True)

    base_name = output_prefix if output_prefix else in_path.stem

    written: list[str] = []
    for idx, (start, end) in enumerate(ranges, start=1):
        writer = PdfWriter()
        for p in range(start, end + 1):
            writer.add_page(reader.pages[p])
        out_name = f"{base_name}_part_{idx}of{len(ranges)}.pdf"
        out_path = out_dir / out_name
        if out_path.exists() and not overwrite:
            raise FileExistsError(f"Output exists: {out_path} (use --overwrite to replace)")
        with open(out_path, 'wb') as fh:
            writer.write(fh)
        written.append(str(out_path))
    return written


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Split a PDF into N separate parts",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Pages are distributed as evenly as possible across parts.\n"
            "Outputs named '<name>_part_<i>of<N>.pdf' in the selected directory.\n"
        ),
    )
    parser.add_argument("input_pdf", help="Path to input PDF")
    parser.add_argument("-n", "--parts", type=int, required=True, help="Number of parts to split into (>=1)")
    parser.add_argument("-o", "--output-dir", type=str, default=None, help="Directory to place output PDFs")
    parser.add_argument("--output-prefix", type=str, default=None, help="Prefix (base name) for output files")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing output files if present")

    args = parser.parse_args()

    try:
        written = split_pdf(
            input_path=args.input_pdf,
            n_parts=args.parts,
            output_dir=args.output_dir,
            output_prefix=args.output_prefix,
            overwrite=args.overwrite,
        )
        print("Created:")
        for p in written:
            print(f"  {p}")
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

