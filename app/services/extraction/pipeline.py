"""
Document content extraction pipeline.
Orchestrates text, PDF, and image parsers by file extension.
"""

import os
from app.services.extraction import text_parser, pdf_parser, image_parser


def extract_content(file_bytes: bytes, filename: str, content_type: str) -> str:
    """
    Direct parsing to the appropriate extractor based on extension.
    Supported types:
    - Text files (.txt, .py, .js, .css, etc.)
    - PDF documents (.pdf)
    - Image attachments (.png, .jpg, .jpeg, .webp)
    """
    ext = os.path.splitext(filename)[1].lower()

    # 1. Text Files
    if ext in [
        ".txt", ".py", ".js", ".css", ".json", ".md",
        ".csv", ".html", ".xml", ".yaml", ".yml",
    ]:
        try:
            return text_parser.parse_text(file_bytes)
        except ValueError as e:
            raise ValueError(str(e))

    # 2. PDF Documents
    elif ext == ".pdf":
        return pdf_parser.parse_pdf(file_bytes)

    # 3. Image Attachments
    elif ext in [".png", ".jpg", ".jpeg", ".webp"]:
        return image_parser.parse_image(file_bytes, filename, content_type)

    # 4. Unsupported
    else:
        raise ValueError(f"Unsupported file type: {ext}")
