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
    Enforces upload size limit, magic-bytes checks, and type validation with DB logging.
    """
    if db_file is None:
        db_file = settings.database_file

    attachment_id = str(uuid.uuid4())

    # 1. Zero-byte Upload validation (empty_upload)
    if not file_bytes or len(file_bytes) == 0:
        await attachments.create_attachment(
            db_file=db_file,
            id=attachment_id,
            session_id=None,
            original_filename=filename,
            content_type=content_type,
            size_bytes=0,
            storage_path="uploads/empty",
        )
        await attachments.create_extraction_result(
            db_file=db_file,
            id=str(uuid.uuid4()),
            attachment_id=attachment_id,
            extraction_source="zero_byte_check",
            status="failed",
            error_message="Uploaded file is empty.",
            error_code="empty_upload",
            extracted_char_count=0,
            extraction_confidence=0.0,
            normalization_applied=0,
        )
        raise ValueError("Uploaded file is empty.")

    # 2. Enforce size limits before disk write
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
            error_code="file_too_large",
            extracted_char_count=0,
            extraction_confidence=0.0,
            normalization_applied=0,
        )
        raise ValueError("File too large")

    # 3. Clean and validate extension / content-type consistency
    raw_ext = os.path.splitext(filename)[1].lower()
    
    allowed_extensions = {
        ".txt", ".md", ".json", ".csv", ".yaml", ".yml", ".xml", ".html", ".py", ".js", ".css",
        ".pdf",
        ".png", ".jpg", ".jpeg", ".webp"
    }

    is_valid = True
    error_code = ""
    error_reason = ""

    if raw_ext not in allowed_extensions:
        is_valid = False
        error_code = "unsupported_extension"
        error_reason = f"Unsupported file type: {raw_ext}"
    else:
        # Check MIME type consistency (secondary sanity check)
        if raw_ext == ".pdf" and content_type != "application/pdf":
            is_valid = False
            error_code = "content_type_mismatch"
            error_reason = f"Mismatched content type: {content_type} for .pdf"
        elif raw_ext in {".png", ".jpg", ".jpeg", ".webp"} and not content_type.startswith("image/"):
            is_valid = False
            error_code = "content_type_mismatch"
            error_reason = f"Mismatched content type: {content_type} for image"
        elif raw_ext in {".txt", ".md", ".json", ".csv", ".yaml", ".yml", ".xml", ".html", ".py", ".js", ".css"}:
            text_mimes = {
                "application/json", "application/xml", "application/x-yaml", "text/yaml",
                "text/x-python", "application/x-python-code", "application/javascript",
                "text/javascript", "text/css"
            }
            if not content_type.startswith("text/") and content_type not in text_mimes:
                is_valid = False
                error_code = "content_type_mismatch"
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
            error_code=error_code,
            extracted_char_count=0,
            extraction_confidence=0.0,
            normalization_applied=0,
        )
        raise ValueError(f"Unsupported file type: {raw_ext}")

    # 4. File signature (magic-byte) validation
    sig_valid = True
    sig_reason = ""
    if raw_ext == ".pdf":
        if not file_bytes.startswith(b"%PDF"):
            sig_valid = False
            sig_reason = "Invalid PDF signature."
    elif raw_ext == ".png":
        if not file_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
            sig_valid = False
            sig_reason = "Invalid PNG signature."
    elif raw_ext in {".jpg", ".jpeg"}:
        if not file_bytes.startswith(b"\xff\xd8\xff"):
            sig_valid = False
            sig_reason = "Invalid JPEG signature."
    elif raw_ext == ".webp":
        if len(file_bytes) < 12 or file_bytes[0:4] != b"RIFF" or file_bytes[8:12] != b"WEBP":
            sig_valid = False
            sig_reason = "Invalid WEBP signature."

    if not sig_valid:
        await attachments.create_attachment(
            db_file=db_file,
            id=attachment_id,
            session_id=None,
            original_filename=filename,
            content_type=content_type,
            size_bytes=len(file_bytes),
            storage_path="uploads/invalid_sig",
        )
        await attachments.create_extraction_result(
            db_file=db_file,
            id=str(uuid.uuid4()),
            attachment_id=attachment_id,
            extraction_source="signature_validator",
            status="failed",
            error_message=sig_reason,
            error_code="invalid_signature",
            extracted_char_count=0,
            extraction_confidence=0.0,
            normalization_applied=0,
        )
        raise ValueError("Invalid file signature")

    # 5. Path sanitization & write bounds check
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
    raw_text = ""
    extraction_id = str(uuid.uuid4())
    confidence = 0.5

    try:
        # Determine extraction type and run parser
        if ext in [
            ".txt", ".py", ".js", ".css", ".json", ".md",
            ".csv", ".html", ".xml", ".yaml", ".yml",
        ]:
            parser_source = "text_parser"
            confidence = 0.95
            raw_text = text_parser.parse_text(file_bytes)
        elif ext == ".pdf":
            parser_source = "pdf_parser"
            confidence = 0.50
            raw_text = pdf_parser.parse_pdf(file_bytes)
        elif ext in [".png", ".jpg", ".jpeg", ".webp"]:
            parser_source = "image_parser"
            confidence = 0.50
            raw_text = image_parser.parse_image(file_bytes, filename, content_type)
        else:
            parser_source = "unsupported"
            raise ValueError(f"Unsupported file type: {ext}")

        # Apply Text Normalization
        norm_text = raw_text.replace("\r\n", "\n")
        
        # Trim null bytes and control noise (excluding \t, \n, \r)
        control_chars = ''.join(chr(i) for i in range(32) if i not in (9, 10, 13)) + chr(127)
        translation_table = str.maketrans("", "", control_chars)
        norm_text = norm_text.translate(translation_table)

        # Collapse consecutive blank lines (3 or more newlines become 2 newlines)
        import re
        norm_text = re.sub(r"\n{3,}", "\n\n", norm_text)
        
        # Strip surrounding whitespace
        norm_text = norm_text.strip()

        normalization_applied = 1 if norm_text != raw_text else 0

        # Check Empty Extraction (yields no text)
        if not norm_text:
            await attachments.create_extraction_result(
                db_file=db_file,
                id=extraction_id,
                attachment_id=attachment_id,
                extraction_source=parser_source,
                status="failed",
                error_message="No extractable text found",
                error_code="empty_extraction",
                extracted_char_count=0,
                extraction_confidence=confidence,
                normalization_applied=normalization_applied,
            )
            raise ValueError("No extractable text found")

        # Save success extraction result
        await attachments.create_extraction_result(
            db_file=db_file,
            id=extraction_id,
            attachment_id=attachment_id,
            extraction_source=parser_source,
            status="succeeded",
            error_message=None,
            extracted_text=norm_text,
            error_code=None,
            extracted_char_count=len(norm_text),
            extraction_confidence=confidence,
            normalization_applied=normalization_applied,
        )
        return norm_text

    except Exception as e:
        if isinstance(e, ValueError) and str(e) in ("No extractable text found", "Uploaded file is empty.", "Invalid file signature"):
            raise

        # Save failure extraction result
        await attachments.create_extraction_result(
            db_file=db_file,
            id=extraction_id,
            attachment_id=attachment_id,
            extraction_source=parser_source,
            status="failed",
            error_message=str(e),
            error_code="parser_failure",
            extracted_char_count=0,
            extraction_confidence=confidence,
            normalization_applied=0,
        )
        raise


