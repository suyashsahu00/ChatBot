"""
Document content extraction pipeline.
Orchestrates text, PDF, and image parsers by file extension.
Saves uploaded files securely and persists metadata in database.
"""

import os
import re
import uuid
from app.core.config import settings
from app.services.data import attachments
from app.services.extraction import text_parser, pdf_parser, image_parser


async def extract_content(
    file_bytes: bytes,
    filename: str,
    content_type: str,
    db_file: str = None,
) -> str:
    """
    Saves the uploaded file securely, inserts metadata into the database,
    and routes parsing to the appropriate extractor based on extension.
    """
    # 1. Clean the extension and check path bounds
    attachment_id = str(uuid.uuid4())
    raw_ext = os.path.splitext(filename)[1].lower()
    # Sanitize extension (only allow alphanumeric characters, maximum length 10)
    if re.match(r"^\.[a-z0-9]{1,10}$", raw_ext):
        ext = raw_ext
    else:
        ext = ".bin"

    # Directory absolute path
    uploads_dir = os.path.abspath("uploads")
    os.makedirs(uploads_dir, exist_ok=True)

    # Output file path
    storage_filename = f"{attachment_id}{ext}"
    physical_path = os.path.abspath(os.path.join(uploads_dir, storage_filename))

    # Path traversal protection: Ensure the path is inside the uploads directory
    if not physical_path.startswith(uploads_dir):
        raise ValueError("Invalid file storage path.")

    # Save file on disk
    with open(physical_path, "wb") as f:
        f.write(file_bytes)

    # Relative path for storage_path in database
    storage_path = os.path.join("uploads", storage_filename).replace("\\", "/")

    # Set default db file
    if db_file is None:
        db_file = settings.database_file

    # Save initial attachment record
    await attachments.create_attachment(
        db_file=db_file,
        id=attachment_id,
        session_id=None,
        original_filename=filename,
        content_type=content_type,
        size_bytes=len(file_bytes),
        storage_path=storage_path,
    )

    parser_source = "unknown"
    extracted_text = ""
    extraction_id = str(uuid.uuid4())

    try:
        # Determine extraction type and run parser
        if ext in [
            ".txt", ".py", ".js", ".css", ".json", ".md",
            ".csv", ".html", ".xml", ".yaml", ".yml",
        ]:
            parser_source = "text_parser"
            extracted_text = text_parser.parse_text(file_bytes)
        elif ext == ".pdf":
            parser_source = "pdf_parser"
            extracted_text = pdf_parser.parse_pdf(file_bytes)
        elif ext in [".png", ".jpg", ".jpeg", ".webp"]:
            parser_source = "image_parser"
            extracted_text = image_parser.parse_image(file_bytes, filename, content_type)
        else:
            parser_source = "unsupported"
            raise ValueError(f"Unsupported file type: {ext}")

        # Save success extraction result
        await attachments.create_extraction_result(
            db_file=db_file,
            id=extraction_id,
            attachment_id=attachment_id,
            extraction_source=parser_source,
            status="succeeded",
            error_message=None,
            extracted_text=extracted_text,
        )
        return extracted_text

    except Exception as e:
        # Save failure extraction result
        await attachments.create_extraction_result(
            db_file=db_file,
            id=extraction_id,
            attachment_id=attachment_id,
            extraction_source=parser_source,
            status="failed",
            error_message=str(e),
            extracted_text=None,
        )
        raise

