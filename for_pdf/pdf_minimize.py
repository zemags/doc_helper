#!/usr/bin/env python3
"""
PDF Size Reduction Script

Reduce a PDF file size by a given percent.
- Compresses embedded images via PyPDF2 + Pillow.
- Optionally uses Ghostscript for whole-file aggressive compression.
- Supports compressing only selected pages while keeping others original.

Usage examples:
  python pdf_minimize.py input.pdf output.pdf -p 50
  python pdf_minimize.py input.pdf output.pdf -p 70 -m ghostscript
  python pdf_minimize.py input.pdf output.pdf -p 60 --pages "3,5,7-10"

Note: Ghostscript is used only for whole-document compression (not per-page).
Install on macOS: brew install ghostscript
"""

import argparse
import io
import os
import shutil
import subprocess
import sys
from typing import Optional, Set

# Lazy import of third-party libs with auto-install fallback
try:
    from PyPDF2 import PdfReader, PdfWriter
    from PyPDF2.generic import IndirectObject
    from PIL import Image
except Exception:  # pragma: no cover
    print("Required packages not found. Installing PyPDF2 and Pillow...", file=sys.stderr)
    subprocess.check_call([sys.executable, "-m", "pip", "install", "PyPDF2", "Pillow"])  # noqa: S603,S607
    from PyPDF2 import PdfReader, PdfWriter
    from PyPDF2.generic import IndirectObject
    from PIL import Image


def check_ghostscript() -> bool:
    """Return True if Ghostscript binary is available in PATH."""
    return shutil.which("gs") is not None


def get_ghostscript_settings(reduction_percent: int) -> dict:
    """Map desired reduction to Ghostscript preset and resolution."""
    if reduction_percent <= 20:
        return {"setting": "/prepress", "resolution": 300, "desc": "High quality (prepress)"}
    if reduction_percent <= 40:
        return {"setting": "/printer", "resolution": 300, "desc": "Good quality (printer)"}
    if reduction_percent <= 60:
        return {"setting": "/ebook", "resolution": 150, "desc": "Medium quality (ebook)"}
    return {"setting": "/screen", "resolution": 72, "desc": "Lower quality (screen)"}


def calculate_target_quality(reduction_percent: int) -> int:
    """Convert requested reduction percent into JPEG quality (1-95)."""
    # 0% -> 95, 50% -> 50, 90% -> 10
    return int(max(10, min(95, 100 - reduction_percent)))


def parse_page_ranges(pages: Optional[str]) -> Optional[Set[int]]:
    """Parse a string like "1,3,5-8" into a set of 1-indexed page numbers."""
    if not pages:
        return None
    acc: Set[int] = set()
    for part in pages.split(','):
        part = part.strip()
        if not part:
            continue
        if '-' in part:
            a, b = part.split('-', 1)
            try:
                start = int(a.strip())
                end = int(b.strip())
            except ValueError:
                raise ValueError(f"Invalid page range: {part}") from None
            if start <= 0 or end <= 0 or end < start:
                raise ValueError(f"Invalid page range bounds: {part}")
            acc.update(range(start, end + 1))
        else:
            try:
                n = int(part)
            except ValueError:
                raise ValueError(f"Invalid page number: {part}") from None
            if n <= 0:
                raise ValueError(f"Invalid page number (must be >=1): {part}")
            acc.add(n)
    return acc


def compress_image(image_data: bytes, quality: int) -> bytes:
    """Compress image bytes using Pillow JPEG encoder."""
    try:
        img = Image.open(io.BytesIO(image_data))
        img.load()  # ensure data is read
        # Convert to RGB, remove alpha by placing on white background
        if img.mode in ("RGBA", "LA"):
            bg = Image.new("RGB", img.size, (255, 255, 255))
            alpha = img.split()[-1]
            bg.paste(img.convert("RGBA"), mask=alpha)
            img = bg
        elif img.mode == "P":
            img = img.convert("RGB")
        elif img.mode != "RGB":
            img = img.convert("RGB")
        out = io.BytesIO()
        img.save(out, format="JPEG", quality=quality, optimize=True)  # type: ignore[arg-type]
        return out.getvalue()
    except Exception as e:  # fallback to original on errors
        print(f"Warning: image compression failed ({e}). Keeping original.", file=sys.stderr)
        return image_data


def _get_obj(obj):
    """Resolve indirect objects to direct objects if needed."""
    if isinstance(obj, IndirectObject):
        return obj.get_object()
    return obj


def reduce_pdf_with_pypdf(input_path: str, output_path: str, reduction_percent: int, pages: Optional[Set[int]] = None,
                           recompress_jpeg: bool = False) -> None:
    """Compress images on selected pages using PyPDF2 and save to output_path.

    If recompress_jpeg is True, also recompress images already encoded with DCT (JPEG),
    which can increase reduction at the cost of quality.
    """
    reader = PdfReader(input_path)
    writer = PdfWriter()

    total_pages = len(reader.pages)
    quality = calculate_target_quality(reduction_percent)

    compressed_pages = 0
    skipped_pages = 0

    for idx, page in enumerate(reader.pages, start=1):
        should_compress = (pages is None) or (idx in pages)
        if should_compress:
            compressed_pages += 1
            try:
                resources = _get_obj(page.get("/Resources"))
                if resources and "/XObject" in resources:
                    xobjects = _get_obj(resources["/XObject"])  # dict of image/xobj
                    for name in list(xobjects.keys()):
                        xobj = _get_obj(xobjects[name])
                        if xobj.get("/Subtype") == "/Image":
                            filt = xobj.get("/Filter")
                            # Skip already-JPEG images unless forced recompress
                            if (filt == "/DCTDecode") and not recompress_jpeg:
                                continue
                            data = xobj.get_data()
                            new_data = compress_image(data, quality)
                            if len(new_data) < len(data):
                                # Replace stream data and mark as JPEG
                                xobj._data = new_data  # type: ignore[attr-defined]
                                xobj["/Filter"] = "/DCTDecode"
                                # Remove color space inconsistencies for JPEG
                                if "/ColorSpace" in xobj and xobj["/ColorSpace"] == "/DeviceCMYK":
                                    del xobj["/ColorSpace"]
            except Exception as e:
                print(f"Warning: page {idx} compression skipped due to error: {e}", file=sys.stderr)
        else:
            skipped_pages += 1
        writer.add_page(page)

    with open(output_path, "wb") as f:
        writer.write(f)

    print(f"PyPDF2: compressed pages={compressed_pages}, kept original pages={skipped_pages}")


def reduce_pdf_with_ghostscript(input_path: str, output_path: str, reduction_percent: int, *,
                                gs_dpi: Optional[int] = None,
                                gs_jpegq: Optional[int] = None,
                                gs_pdfsettings: Optional[str] = None) -> bool:
    """Compress the whole PDF using Ghostscript. Returns True on success.

    Optional tuning:
      - gs_dpi: override target DPI for downsampling (e.g., 150)
      - gs_jpegq: JPEG quality 1-95 for DCTEncode
      - gs_pdfsettings: override preset like '/screen', '/ebook', '/printer', '/prepress'
    """
    if not check_ghostscript():
        return False
    settings = get_ghostscript_settings(reduction_percent)
    preset = gs_pdfsettings if gs_pdfsettings else settings['setting']
    dpi = gs_dpi if gs_dpi else settings['resolution']

    cmd = [
        "gs",
        "-sDEVICE=pdfwrite",
        "-dCompatibilityLevel=1.4",
        f"-dPDFSETTINGS={preset}",
        "-dNOPAUSE",
        "-dQUIET",
        "-dBATCH",
        f"-r{dpi}",
        # Fonts
        "-dCompressFonts=true",
        "-dSubsetFonts=true",
        # Image downsampling + filters
        "-dDownsampleColorImages=true",
        "-dDownsampleGrayImages=true",
        "-dDownsampleMonoImages=true",
        "-dColorImageDownsampleType=/Bicubic",
        "-dGrayImageDownsampleType=/Bicubic",
        "-dMonoImageDownsampleType=/Bicubic",
        f"-dColorImageResolution={dpi}",
        f"-dGrayImageResolution={dpi}",
        f"-dMonoImageResolution={dpi}",
        # Force JPEG encoding for color/gray images; tune quality
        "-dAutoFilterColorImages=false",
        "-dAutoFilterGrayImages=false",
        "-dEncodeColorImages=true",
        "-dEncodeGrayImages=true",
        "-sColorImageFilter=/DCTEncode",
        "-sGrayImageFilter=/DCTEncode",
    ]

    if gs_jpegq is not None:
        jq = max(1, min(95, int(gs_jpegq)))
        cmd.append(f"-dJPEGQ={jq}")

    cmd += [
        f"-sOutputFile={output_path}",
        input_path,
    ]

    try:
        subprocess.run(cmd, check=True, capture_output=True)  # noqa: S603
        print(f"Ghostscript: preset={preset}, dpi={dpi}, jpegq={gs_jpegq if gs_jpegq is not None else 'default'}")
        return True
    except Exception as e:
        print(f"Ghostscript failed: {e}", file=sys.stderr)
        return False


def reduce_pdf_size(input_path: str, output_path: str, reduction_percent: int, method: str = "auto",
                     pages: Optional[Set[int]] = None,
                     gs_dpi: Optional[int] = None,
                     gs_jpegq: Optional[int] = None,
                     gs_pdfsettings: Optional[str] = None,
                     recompress_jpeg: bool = False) -> None:
    """Reduce PDF file size by compressing images.

    method: 'auto' | 'ghostscript' | 'pypdf2'
    pages: if provided, only those 1-indexed pages are compressed (PyPDF2 method).
    """
    if not os.path.exists(input_path):
        raise FileNotFoundError(f"Input file not found: {input_path}")
    if not (0 <= reduction_percent <= 100):
        raise ValueError("Percent must be between 0 and 100")

    original_size = os.path.getsize(input_path)
    print(f"Original size: {original_size/1024:.2f} KB ({original_size/(1024*1024):.2f} MB)")

    use_gs = False
    if pages:
        print("Selective pages requested -> using PyPDF2 method")
    else:
        if method == "ghostscript":
            use_gs = check_ghostscript()
            if not use_gs:
                print("Ghostscript not found, falling back to PyPDF2", file=sys.stderr)
        elif method == "auto":
            use_gs = check_ghostscript() and reduction_percent >= 35
            print("Auto method:", "Ghostscript" if use_gs else "PyPDF2")
        else:
            use_gs = False

    if use_gs and not pages:
        success = reduce_pdf_with_ghostscript(input_path, output_path, reduction_percent,
                                              gs_dpi=gs_dpi, gs_jpegq=gs_jpegq, gs_pdfsettings=gs_pdfsettings)
        if not success:
            print("Falling back to PyPDF2 method", file=sys.stderr)
            reduce_pdf_with_pypdf(input_path, output_path, reduction_percent, pages=None, recompress_jpeg=recompress_jpeg)
    else:
        reduce_pdf_with_pypdf(input_path, output_path, reduction_percent, pages=pages, recompress_jpeg=recompress_jpeg)

    new_size = os.path.getsize(output_path)
    reduction = (original_size - new_size) / original_size * 100 if original_size > 0 else 0
    print(f"New size:      {new_size/1024:.2f} KB ({new_size/(1024*1024):.2f} MB)")
    print(f"Actual reduction: {reduction:.2f}%")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Reduce PDF file size by a given percent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Methods:\n"
            "  auto        - choose Ghostscript if available and percent >= 35\n"
            "  ghostscript - force Ghostscript (whole file)\n"
            "  pypdf2      - Python-only image compression\n\n"
            "Pages format: '1,3,5-8' (1-indexed). If omitted, compresses all pages.\n"
        ),
    )
    parser.add_argument("input_pdf", help="Path to input PDF")
    parser.add_argument("output_pdf", help="Path to output PDF")
    parser.add_argument("-p", "--percent", type=int, required=True, help="Reduction percent (0-100)")
    parser.add_argument("-m", "--method", choices=["auto", "ghostscript", "pypdf2"], default="auto", help="Compression method")
    parser.add_argument("--pages", type=str, default=None, help="Pages to compress, e.g. '3,5,7-10'")
    parser.add_argument("--gs-dpi", type=int, default=None, help="Override Ghostscript target DPI (e.g., 150)")
    parser.add_argument("--gs-jpegq", type=int, default=None, help="Override Ghostscript JPEG quality 1-95")
    parser.add_argument("--gs-pdfsettings", type=str, default=None,
                        choices=["/screen", "/ebook", "/printer", "/prepress"],
                        help="Override Ghostscript PDFSETTINGS preset")
    parser.add_argument("--recompress-jpeg", action="store_true",
                        help="Also recompress images already encoded as JPEG (more reduction, lower quality)")

    args = parser.parse_args()

    pages = parse_page_ranges(args.pages) if args.pages else None

    try:
        reduce_pdf_size(
            args.input_pdf,
            args.output_pdf,
            args.percent,
            method=args.method,
            pages=pages,
            gs_dpi=args.gs_dpi,
            gs_jpegq=args.gs_jpegq,
            gs_pdfsettings=args.gs_pdfsettings,
            recompress_jpeg=args.recompress_jpeg,
        )
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
