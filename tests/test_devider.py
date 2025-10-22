import os
from pathlib import Path

import pytest

from for_pdf.pdf_devider import compute_chunks, split_pdf
from PyPDF2 import PdfWriter, PdfReader


def make_pdf(path: Path, pages: int = 7) -> None:
    writer = PdfWriter()
    # add_blank_page requires dimensions for the first page in PyPDF2>=3
    for i in range(pages):
        if i == 0:
            writer.add_blank_page(width=595, height=842)  # A4-ish points
        else:
            writer.add_blank_page()
    with open(path, "wb") as f:
        writer.write(f)


def test_compute_chunks_distribution():
    # 10 pages into 3 parts -> 4,3,3
    ranges = compute_chunks(10, 3)
    sizes = [end - start + 1 for start, end in ranges]
    assert sizes == [4, 3, 3]

    # n_parts > total_pages -> one page per part, no empties
    ranges = compute_chunks(5, 10)
    sizes = [end - start + 1 for start, end in ranges]
    assert sizes == [1, 1, 1, 1, 1]


@pytest.mark.parametrize("pages,n_parts", [(10, 3), (9, 2), (5, 10)])
def test_split_pdf_creates_parts(tmp_path: Path, pages: int, n_parts: int):
    src = tmp_path / "src.pdf"
    make_pdf(src, pages=pages)

    out_dir = tmp_path / "out"
    written = split_pdf(str(src), n_parts, output_dir=str(out_dir), overwrite=True)

    # Check files exist
    assert len(written) == min(n_parts, pages)
    assert all(Path(p).exists() for p in written)

    # Check page counts sum to original and are balanced
    total = 0
    counts = []
    for p in written:
        r = PdfReader(p)
        counts.append(len(r.pages))
        total += len(r.pages)
    assert total == pages
    # difference between max and min chunk size at most 1
    assert (max(counts) - min(counts)) <= 1


def test_split_overwrite_flag(tmp_path: Path):
    src = tmp_path / "src.pdf"
    make_pdf(src, pages=3)
    out_dir = tmp_path / "out"
    # first pass
    split_pdf(str(src), 2, output_dir=str(out_dir), overwrite=True)
    # second pass without overwrite should raise
    with pytest.raises(FileExistsError):
        split_pdf(str(src), 2, output_dir=str(out_dir), overwrite=False)

