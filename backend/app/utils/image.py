"""
ENCPServices - Image Processing Utilities
===============================================
Image resize and enhancement for Claude Vision document/photo extraction.
Handles EXIF orientation, format conversion, and quality optimization.

Used for processing client-submitted photos (project photos, damage photos,
color swatches, property images) before sending to Claude Vision.

Forked from SegurIA, rebranded for ENCPServices.
"""

import base64
import io
import logging

logger = logging.getLogger("encp.image")

MAX_IMAGE_SIZE = 1568  # optimal for Claude Vision


def resize_for_vision(
    image_bytes: bytes,
    max_dim: int = MAX_IMAGE_SIZE,
    enhance: bool = False,
) -> tuple[str, str]:
    """Resize image for Claude Vision. Returns (base64_str, media_type).

    Args:
        image_bytes: Raw image bytes
        max_dim: Maximum dimension (width or height) — default 1568 (optimal for Claude Vision)
        enhance: If True, apply sharpness/contrast boost for document OCR
    """
    from PIL import Image, ImageOps, ImageEnhance

    img = Image.open(io.BytesIO(image_bytes))

    # CRITICAL: Apply EXIF orientation FIRST
    # Phone cameras save landscape photos as portrait + EXIF rotation tag.
    # Without this, property photos and documents arrive sideways.
    try:
        img = ImageOps.exif_transpose(img)
    except Exception:
        pass  # No EXIF data or unsupported format

    original_size = img.size
    if img.mode in ("RGBA", "LA", "P"):
        bg = Image.new("RGB", img.size, (255, 255, 255))
        if img.mode == "P":
            img = img.convert("RGBA")
        bg.paste(img, mask=img.split()[-1] if "A" in img.mode else None)
        img = bg

    w, h = img.size
    if w > max_dim or h > max_dim:
        ratio = min(max_dim / w, max_dim / h)
        img = img.resize((int(w * ratio), int(h * ratio)), Image.LANCZOS)

    # Document enhancement: sharpen + boost contrast for better OCR
    if enhance:
        img = ImageEnhance.Sharpness(img).enhance(1.3)
        img = ImageEnhance.Contrast(img).enhance(1.1)

    # Higher quality for documents (92) vs regular photos (85)
    quality = 92 if enhance else 85
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality, optimize=True)

    while buf.tell() > 5 * 1024 * 1024 and quality > 20:
        quality -= 10
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=quality, optimize=True)

    logger.info(
        f"[IMAGE] resize_for_vision: {original_size} -> {img.size}, "
        f"quality={quality}, enhance={enhance}, size={buf.tell() // 1024}KB"
    )

    b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
    return b64, "image/jpeg"
