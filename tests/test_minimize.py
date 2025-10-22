from pathlib import Path

import os

import pytest
from PIL import Image
from PyPDF2 import PdfReader

from for_pdf.pdf_minimize import parse_page_ranges, reduce_pdf_size


def make_image_pdf(path: Path, pages: int = 3, size=(1200, 1200)) -> None:
    # Create noisy RGB images to avoid solid-color high-compressibility quirks
    imgs = []
    for i in range(pages):
        img = Image.effect_noise(size, 100.0).convert("RGB")
        imgs.append(img)
    # Save multi-page PDF using Pillow
    first, *rest = imgs
    first.save(path, format="PDF", save_all=True, append_images=rest)


def test_parse_page_ranges():
    assert parse_page_ranges("1,3,5-7") == {1, 3, 5, 6, 7}
    assert parse_page_ranges(" 2 - 4 , 6 ") == {2, 3, 4, 6}
    with pytest.raises(ValueError):
        parse_page_ranges("0")
    with pytest.raises(ValueError):
        parse_page_ranges("3-2")


@pytest.mark.parametrize("method", ["pypdf2"])  # ghostscript not required in CI
def test_reduce_pdf_size_runs_and_preserves_pages(tmp_path: Path, method: str):
    src = tmp_path / "src_images.pdf"
    dst = tmp_path / "dst.pdf"
    make_image_pdf(src, pages=4)

    reduce_pdf_size(str(src), str(dst), reduction_percent=60, method=method, pages=None, recompress_jpeg=True)

    assert dst.exists()
    src_pages = len(PdfReader(str(src)).pages)
    dst_pages = len(PdfReader(str(dst)).pages)
    assert src_pages == dst_pages

    # Expect some reduction with recompress_jpeg and noisy images
    assert os.path.getsize(dst) <= os.path.getsize(src)


def test_reduce_pdf_size_selective_pages(tmp_path: Path):
    src = tmp_path / "src_images.pdf"
    dst = tmp_path / "dst.pdf"
    make_image_pdf(src, pages=5)

    # Compress only pages 2-4
    reduce_pdf_size(str(src), str(dst), reduction_percent=60, method="pypdf2", pages={2, 3, 4}, recompress_jpeg=True)

    assert dst.exists()
    assert len(PdfReader(str(dst)).pages) == 5
import os
from pathlib import Path

import pytest

from for_pdf.pdf_devider import compute_chunks, split_pdf
from PyPDF2 import PdfWriter, PdfReader


def make_pdf(path: Path, pages: int = 7) -> None:
    writer = PdfWriter()
    # add_blank_page requires width/height for first page in recent PyPDF2
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

