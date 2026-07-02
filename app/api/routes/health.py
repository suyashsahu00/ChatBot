"""
Health check endpoint.
"""

from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
async def health_check():
    """Simple health check to verify the API is running."""
    return {"status": "healthy"}
