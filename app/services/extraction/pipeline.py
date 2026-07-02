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
    Enforces upload size limit and strict type validation with DB fallback logging.
    """
    # Set default db file
    if db_file is None:
        db_file = settings.database_file

    attachment_id = str(uuid.uuid4())

    # 1. Enforce size limits before disk write
    if len(file_bytes) > settings.max_upload_bytes:
        await attachments.create_attachment(
            db_file=db_file,
            id=attachment_id,
            session_id=None,
            original_filename=filename,
            content_type=content_type,
            size_bytes=len(file_bytes),
            storage_path="uploads/oversized",
        )
        await attachments.create_extraction_result(
            db_file=db_file,
            id=str(uuid.uuid4()),
            attachment_id=attachment_id,
            extraction_source="size_validator",
            status="failed",
            error_message="File too large",
            extracted_text=None,
        )
        raise ValueError("File too large")

    # 2. Clean and validate extension / content-type consistency
    raw_ext = os.path.splitext(filename)[1].lower()
    
    allowed_extensions = {
        ".txt", ".md", ".json", ".csv", ".yaml", ".yml", ".xml", ".html", ".py", ".js", ".css",
        ".pdf",
        ".png", ".jpg", ".jpeg", ".webp"
    }

    is_valid = True
    error_reason = ""

    if raw_ext not in allowed_extensions:
        is_valid = False
        error_reason = f"Unsupported file type: {raw_ext}"
    else:
        # Check MIME type consistency (secondary sanity check)
        if raw_ext == ".pdf" and content_type != "application/pdf":
            is_valid = False
            error_reason = f"Mismatched content type: {content_type} for .pdf"
        elif raw_ext in {".png", ".jpg", ".jpeg", ".webp"} and not content_type.startswith("image/"):
            is_valid = False
            error_reason = f"Mismatched content type: {content_type} for image"
        elif raw_ext in {".txt", ".md", ".json", ".csv", ".yaml", ".yml", ".xml", ".html", ".py", ".js", ".css"}:
            text_mimes = {
                "application/json", "application/xml", "application/x-yaml", "text/yaml",
                "text/x-python", "application/x-python-code", "application/javascript",
                "text/javascript", "text/css"
            }
            if not content_type.startswith("text/") and content_type not in text_mimes:
                is_valid = False
                error_reason = f"Mismatched content type: {content_type} for text file"

    if not is_valid:
        await attachments.create_attachment(
            db_file=db_file,
            id=attachment_id,
            session_id=None,
            original_filename=filename,
            content_type=content_type,
            size_bytes=len(file_bytes),
            storage_path="uploads/invalid",
        )
        await attachments.create_extraction_result(
            db_file=db_file,
            id=str(uuid.uuid4()),
            attachment_id=attachment_id,
            extraction_source="type_validator",
            status="failed",
            error_message=error_reason,
            extracted_text=None,
        )
        raise ValueError(f"Unsupported file type: {raw_ext}")

    # 3. Path sanitization & write bounds check
    ext = raw_ext
    uploads_dir = os.path.abspath("uploads")
    os.makedirs(uploads_dir, exist_ok=True)

    storage_filename = f"{attachment_id}{ext}"
    physical_path = os.path.abspath(os.path.join(uploads_dir, storage_filename))

    if not physical_path.startswith(uploads_dir):
        raise ValueError("Invalid file storage path.")

    # Save physical file
    with open(physical_path, "wb") as f:
        f.write(file_bytes)

    storage_path = os.path.join("uploads", storage_filename).replace("\\", "/")

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


