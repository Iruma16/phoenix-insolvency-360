from typing import List


def chunk_text(
    text: str,
    max_chars: int = 1000,
    overlap: int = 200,
) -> List[str]:
    """
    Divide texto en chunks solapados.
    """
    chunks: List[str] = []
    start = 0
    length = len(text)

    while start < length:
        end = start + max_chars
        chunk = text[start:end]
        chunks.append(chunk)
        start = end - overlap
        if start < 0:
            start = 0

    return chunks
