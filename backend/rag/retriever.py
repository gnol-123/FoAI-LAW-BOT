from .embeddings import embed
from .vectorstore import get_index

MIN_SCORE = 0.3   # discard low-confidence matches


def retrieve(query: str, top_k: int = 5) -> list[dict]:
    """Return the top_k most relevant document chunks for a query."""
    query_vec = embed(query)
    results = get_index().query(
        vector=query_vec,
        top_k=top_k,
        include_metadata=True,
    )
    return [
        {
            "documentId": m.metadata.get("documentId", ""),
            "filename":   m.metadata.get("filename", ""),
            "text":       m.metadata.get("text", ""),
            "pageNumber": int(m.metadata.get("pageNumber", 0)),
            "score":      round(m.score, 3),
        }
        for m in results.matches
        if m.score >= MIN_SCORE
    ]
