"""
Text file parser.
Decodes raw bytes into text using UTF-8 or Latin-1 fallback.
"""

def parse_text(file_bytes: bytes) -> str:
    """Decode raw bytes into a string."""
    try:
        return file_bytes.decode("utf-8")
    except UnicodeDecodeError:
        try:
            return file_bytes.decode("latin-1")
        except Exception as e:
            raise ValueError(f"Failed to decode text file: {str(e)}")
