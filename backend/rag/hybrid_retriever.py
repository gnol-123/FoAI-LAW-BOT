"""
Hybrid retrieval: Pinecone (dense) + Whoosh BM25 (sparse) fused with RRF.
Accepts multiple query expansions and fuses all result lists together.
"""
from .embeddings import embed
from .vectorstore import get_index as get_pinecone
from .sparse_index import search as bm25_search

RRF_K = 60   # standard constant; higher → less weight on top ranks


def _rrf(rank: int) -> float:
    return 1.0 / (RRF_K + rank + 1)


def _dense(query: str, top_k: int = 15) -> list[dict]:
    results = get_pinecone().query(
        vector=embed(query),
        top_k=top_k,
        include_metadata=True,
    )
    return [
        {
            "chunk_id":    m.id,
            "document_id": m.metadata.get("documentId", ""),
            "filename":    m.metadata.get("filename", ""),
            "text":        m.metadata.get("text", ""),
            "page_number": int(m.metadata.get("pageNumber", 0)),
            "rank":        i,
        }
        for i, m in enumerate(results.matches)
        if m.score > 0.2
    ]


def _rrf_fuse(result_lists: list[list[dict]], top_k: int) -> list[dict]:
    scores: dict[str, float] = {}
    meta:   dict[str, dict]  = {}

    for ranked_list in result_lists:
        for item in ranked_list:
            cid = item["chunk_id"]
            scores[cid] = scores.get(cid, 0.0) + _rrf(item["rank"])
            # Prefer items that have text (dense results always do; sparse do too now)
            if cid not in meta or not meta[cid].get("text"):
                meta[cid] = item

    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:top_k]
    return [
        {
            "documentId": meta[cid]["document_id"],
            "filename":   meta[cid]["filename"],
            "text":       meta[cid]["text"],
            "pageNumber": meta[cid]["page_number"],
            "score":      round(score, 4),
        }
        for cid, score in ranked
        if meta.get(cid, {}).get("text")
    ]


def retrieve(queries: list[str], top_k: int = 5) -> list[dict]:
    """
    For each query variant: get dense + sparse results, fuse per-query with RRF.
    Then fuse all per-query results with a final RRF pass.
    """
    per_query: list[list[dict]] = []

    for q in queries:
        dense  = _dense(q)
        sparse = bm25_search(q)
        fused  = _rrf_fuse([dense, sparse], top_k=top_k * 3)
        # Re-add rank field for the outer RRF pass
        for rank, item in enumerate(fused):
            item["chunk_id"] = f"{item['documentId']}_{item['pageNumber']}_{rank}"
            item["document_id"] = item["documentId"]
            item["page_number"]  = item["pageNumber"]
            item["rank"] = rank
        per_query.append(fused)

    return _rrf_fuse(per_query, top_k=top_k)
