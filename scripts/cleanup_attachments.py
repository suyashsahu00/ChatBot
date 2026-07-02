"""
Manual CLI script to clean up expired attachments and their extractions.
"""

import asyncio
from app.core.config import settings
from app.services.data.attachments import cleanup_expired_attachments


async def main():
    db_file = settings.database_file
    retention_days = settings.attachment_retention_days
    print(f"Starting cleanup of attachments older than {retention_days} days in {db_file}...")
    await cleanup_expired_attachments(db_file, retention_days)
    print("Cleanup completed successfully.")


if __name__ == "__main__":
    asyncio.run(main())
