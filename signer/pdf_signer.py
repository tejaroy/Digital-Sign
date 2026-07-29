"""Stamp a local signature image onto PDF pages with per-page positions."""
import io
import os
from typing import Any, BinaryIO, Dict, List, Optional, Sequence, Tuple, Union

from PyPDF2 import PdfReader, PdfWriter
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas


PathLike = Union[str, os.PathLike]
Placement = Dict[str, Any]


def _page_size(page) -> Tuple[float, float]:
    box = page.mediabox
    return float(box.width), float(box.height)


def get_pdf_page_info(pdf_source: Union[PathLike, BinaryIO]) -> List[Dict[str, float]]:
    """Return [{width, height}, ...] for each page."""
    reader = PdfReader(pdf_source)
    info = []
    for page in reader.pages:
        w, h = _page_size(page)
        info.append({"width": w, "height": h})
    return info


def _make_signature_overlay(
    page_width: float,
    page_height: float,
    signature_path: PathLike,
    *,
    x: float,
    y: float,
    width: float,
    height: Optional[float] = None,
) -> PdfReader:
    packet = io.BytesIO()
    c = canvas.Canvas(packet, pagesize=(page_width, page_height))

    img = ImageReader(str(signature_path))
    img_w, img_h = img.getSize()
    if height is None:
        height = width * (img_h / float(img_w)) if img_w else width * 0.4

    c.drawImage(
        img,
        x,
        y,
        width=width,
        height=height,
        mask="auto",
        preserveAspectRatio=True,
        anchor="sw",
    )
    c.save()
    packet.seek(0)
    return PdfReader(packet)


def stamp_with_placements(
    pdf_source: Union[PathLike, BinaryIO],
    signature_path: PathLike,
    placements: Sequence[Placement],
) -> bytes:
    """
    Place signature using per-page placements.

    Each placement dict:
      page (int, 0-based), x, y, width, optional height,
      enabled (bool, default True)
    """
    if not os.path.isfile(str(signature_path)):
        raise FileNotFoundError("Signature image not found: {}".format(signature_path))

    reader = PdfReader(pdf_source)
    if not reader.pages:
        raise ValueError("PDF has no pages")

    by_page = {}
    for item in placements:
        if not item.get("enabled", True):
            continue
        page = int(item["page"])
        by_page[page] = item

    writer = PdfWriter()
    for i, page in enumerate(reader.pages):
        if i in by_page:
            p = by_page[i]
            width = float(p.get("width", 150))
            height = p.get("height")
            height = float(height) if height not in (None, "") else None
            overlay = _make_signature_overlay(
                *_page_size(page),
                signature_path,
                x=float(p["x"]),
                y=float(p["y"]),
                width=width,
                height=height,
            )
            page.merge_page(overlay.pages[0])
        writer.add_page(page)

    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def _read_pdf_bytes(pdf_source: Union[PathLike, BinaryIO]) -> bytes:
    if hasattr(pdf_source, "read"):
        data = pdf_source.read()
        if hasattr(pdf_source, "seek"):
            try:
                pdf_source.seek(0)
            except Exception:
                pass
        return data
    with open(str(pdf_source), "rb") as fh:
        return fh.read()


def stamp_signature_on_pdf(
    pdf_source: Union[PathLike, BinaryIO],
    signature_path: PathLike,
    *,
    page_index: Optional[Union[int, Sequence[int]]] = -1,
    x: Optional[float] = None,
    y: Optional[float] = None,
    signature_width: float = 150.0,
    signature_height: Optional[float] = None,
    margin_right: float = 50.0,
    margin_bottom: float = 50.0,
) -> bytes:
    """Legacy helper: same position rules on selected pages."""
    raw = _read_pdf_bytes(pdf_source)
    reader = PdfReader(io.BytesIO(raw))
    total = len(reader.pages)
    if total == 0:
        raise ValueError("PDF has no pages")

    if page_index is None:
        pages = list(range(total))
    elif isinstance(page_index, (list, tuple)):
        pages = [i if i >= 0 else total + i for i in page_index]
    else:
        pages = [page_index if page_index >= 0 else total + page_index]

    placements = []
    for i in pages:
        pw, _ph = _page_size(reader.pages[i])
        draw_x = x if x is not None else max(0.0, pw - signature_width - margin_right)
        draw_y = y if y is not None else margin_bottom
        placements.append(
            {
                "page": i,
                "x": draw_x,
                "y": draw_y,
                "width": signature_width,
                "height": signature_height,
                "enabled": True,
            }
        )
    return stamp_with_placements(io.BytesIO(raw), signature_path, placements)


def list_pdfs_in_path(path: PathLike) -> List[str]:
    """If path is a PDF file return [path]; if folder return all PDFs inside."""
    path = str(path).strip().strip('"')
    if not path:
        return []
    if os.path.isfile(path) and path.lower().endswith(".pdf"):
        return [path]
    if os.path.isdir(path):
        names = sorted(os.listdir(path))
        return [
            os.path.join(path, n)
            for n in names
            if n.lower().endswith(".pdf") and os.path.isfile(os.path.join(path, n))
        ]
    return []


def stamp_many(
    pdf_paths: List[PathLike],
    signature_path: PathLike,
    output_dir: PathLike,
    **stamp_kwargs,
) -> List[str]:
    """Stamp signature on many PDFs. Saves with the same original filenames."""
    os.makedirs(str(output_dir), exist_ok=True)
    results = []
    for path in pdf_paths:
        out_name = os.path.basename(str(path))
        if not out_name.lower().endswith(".pdf"):
            out_name = out_name + ".pdf"
        out_path = os.path.join(str(output_dir), out_name)
        data = stamp_signature_on_pdf(path, signature_path, **stamp_kwargs)
        with open(out_path, "wb") as fh:
            fh.write(data)
        results.append(out_path)
    return results


def stamp_many_with_placements(
    pdf_paths: List[PathLike],
    signature_path: PathLike,
    output_dir: PathLike,
    placements: Sequence[Placement],
) -> List[str]:
    os.makedirs(str(output_dir), exist_ok=True)
    results = []
    for path in pdf_paths:
        # Keep the original filename in the output folder
        out_name = os.path.basename(str(path))
        if not out_name.lower().endswith(".pdf"):
            out_name = out_name + ".pdf"
        out_path = os.path.join(str(output_dir), out_name)
        data = stamp_with_placements(path, signature_path, placements)
        with open(out_path, "wb") as fh:
            fh.write(data)
        results.append(out_path)
    return results
