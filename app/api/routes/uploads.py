"""
File upload endpoint with text/PDF/image extraction.
Orchestrated via services.
"""

from fastapi import APIRouter, HTTPException, UploadFile, File

from app.services.extraction.pipeline import extract_content

router = APIRouter()


@router.post("/upload")
async def upload_file_endpoint(file: UploadFile = File(...)):
    filename = file.filename
    content_type = file.content_type or ""
    print(f"Received file upload: {filename}, type: {content_type}")

    try:
        file_bytes = await file.read()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to read file: {str(e)}")

    try:
        extracted_text = await extract_content(file_bytes, filename, content_type)
    except ValueError as val_err:
        raise HTTPException(status_code=400, detail=str(val_err))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Extraction failed: {str(e)}")

    return {"filename": filename, "extracted_text": extracted_text}
