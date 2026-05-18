"""Batch convert PDFs in data/raw to Markdown files in data/processed.

The script uses PyMuPDF4LLM for layout-aware Markdown extraction and falls
back to Tesseract OCR for pages where the native text layer is missing or
effectively empty.
"""

from __future__ import annotations

import argparse
import io
import os
import re
import sys
from pathlib import Path
from typing import Iterable


ROOT_DIR = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT_DIR / "data" / "raw"
PROCESSED_DIR = ROOT_DIR / "data" / "processed"


def _import_dependencies():
    try:
        import fitz  # type: ignore
        import pymupdf4llm  # type: ignore
        import pytesseract  # type: ignore
        from PIL import Image  # type: ignore
    except ImportError as exc:  # pragma: no cover - runtime dependency guard
        raise SystemExit(
            "Missing dependencies. Install: pymupdf, pymupdf4llm, pytesseract, pillow"
        ) from exc

    return fitz, pymupdf4llm, pytesseract, Image


def iter_pdf_files(root: Path) -> Iterable[Path]:
    yield from sorted(root.rglob("*.pdf"))


def normalize_markdown(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def image_to_text(page, fitz, pytesseract, Image, lang: str, dpi: int) -> str:
    zoom = dpi / 72.0
    matrix = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=matrix, alpha=False)
    image = Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")
    return pytesseract.image_to_string(image, lang=lang, config="--psm 6")


def page_to_markdown(
    pdf_path: Path,
    page_number: int,
    fitz,
    pymupdf4llm,
    pytesseract,
    Image,
    *,
    min_text_chars: int,
    ocr_lang: str,
    ocr_dpi: int,
) -> str:
    extracted = ""
    try:
        extracted = pymupdf4llm.to_markdown(
            str(pdf_path),
            pages=[page_number],
            use_ocr=False,
        )
    except Exception:
        extracted = ""

    extracted = normalize_markdown(extracted or "")
    if len(re.sub(r"\s+", "", extracted)) >= min_text_chars:
        return extracted

    with fitz.open(pdf_path) as doc:
        page = doc.load_page(page_number)
        ocr_text = normalize_markdown(
            image_to_text(page, fitz, pytesseract, Image, ocr_lang, ocr_dpi)
        )

    if not extracted and not ocr_text:
        return ""
    if not extracted:
        return f"## Page {page_number + 1}\n\n{ocr_text}"
    if not ocr_text:
        return extracted
    return f"{extracted}\n\n## OCR Page {page_number + 1}\n\n{ocr_text}"


def convert_pdf(
    pdf_path: Path,
    raw_dir: Path,
    output_root: Path,
    fitz,
    pymupdf4llm,
    pytesseract,
    Image,
    *,
    min_text_chars: int,
    ocr_lang: str,
    ocr_dpi: int,
    overwrite: bool,
) -> Path:
    relative_output = pdf_path.relative_to(raw_dir).with_suffix(".md")
    output_path = output_root / relative_output
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if output_path.exists() and not overwrite:
        return output_path

    with fitz.open(pdf_path) as doc:
        page_count = doc.page_count

    pages = []
    for page_number in range(page_count):
        page_md = page_to_markdown(
            pdf_path,
            page_number,
            fitz,
            pymupdf4llm,
            pytesseract,
            Image,
            min_text_chars=min_text_chars,
            ocr_lang=ocr_lang,
            ocr_dpi=ocr_dpi,
        )
        if page_md:
            pages.append(f"<!-- page: {page_number + 1} -->\n\n{page_md}")

    output_text = normalize_markdown("\n\n---\n\n".join(pages))
    output_path.write_text(output_text + "\n", encoding="utf-8")
    return output_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Convert PDFs from data/raw into Markdown files in data/processed."
    )
    parser.add_argument(
        "--raw-dir",
        type=Path,
        default=RAW_DIR,
        help="Input directory containing PDF files.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROCESSED_DIR,
        help="Directory where Markdown files will be written.",
    )
    parser.add_argument(
        "--ocr-lang",
        default=os.getenv("TESSERACT_LANG", "vie+eng"),
        help="Tesseract language code, e.g. vie+eng or eng.",
    )
    parser.add_argument(
        "--ocr-dpi",
        type=int,
        default=int(os.getenv("OCR_DPI", "300")),
        help="Render DPI used before OCR.",
    )
    parser.add_argument(
        "--min-text-chars",
        type=int,
        default=int(os.getenv("MIN_TEXT_CHARS", "20")),
        help="Minimum non-whitespace characters to accept native extraction.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing Markdown files.",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    raw_dir: Path = args.raw_dir
    output_dir: Path = args.output_dir

    if not raw_dir.exists():
        print(f"Input directory not found: {raw_dir}", file=sys.stderr)
        return 1

    fitz, pymupdf4llm, pytesseract, Image = _import_dependencies()

    if not hasattr(pytesseract, "image_to_string"):
        print("pytesseract is not available in this environment.", file=sys.stderr)
        return 1

    tesseract_cmd = os.getenv("TESSERACT_CMD")
    if tesseract_cmd:
        pytesseract.pytesseract.tesseract_cmd = tesseract_cmd
    try:
        pytesseract.get_tesseract_version()
    except Exception as exc:
        print(
            "Tesseract executable not found or not configured. Set TESSERACT_CMD to the binary path.",
            file=sys.stderr,
        )
        return 1

    pdf_files = list(iter_pdf_files(raw_dir))
    if not pdf_files:
        print(f"No PDF files found in {raw_dir}")
        return 0

    processed = 0
    for pdf_path in pdf_files:
        try:
            output_path = convert_pdf(
                pdf_path,
                raw_dir,
                output_dir,
                fitz,
                pymupdf4llm,
                pytesseract,
                Image,
                min_text_chars=args.min_text_chars,
                ocr_lang=args.ocr_lang,
                ocr_dpi=args.ocr_dpi,
                overwrite=args.overwrite,
            )
            print(f"{pdf_path} -> {output_path}")
            processed += 1
        except Exception as exc:
            print(f"Failed: {pdf_path} ({exc})", file=sys.stderr)

    print(f"Done. Processed {processed}/{len(pdf_files)} PDFs.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
