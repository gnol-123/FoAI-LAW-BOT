import os

from whoosh import index
from whoosh.analysis import StemmingAnalyzer
from whoosh.fields import ID, STORED, TEXT, Schema
from whoosh.qparser import QueryParser

INDEX_DIR = os.path.join(os.path.dirname(__file__), "..", "whoosh_index")

SCHEMA = Schema(
    chunk_id=ID(stored=True, unique=True),
    document_id=ID(stored=True),
    filename=STORED,
    page_number=STORED,
    text=STORED,
    content=TEXT(analyzer=StemmingAnalyzer()),
)


def get_ix():
    os.makedirs(INDEX_DIR, exist_ok=True)
    if index.exists_in(INDEX_DIR):
        return index.open_dir(INDEX_DIR)
    return index.create_in(INDEX_DIR, SCHEMA)


def add_chunks(chunks: list[dict]) -> None:
    """chunks: list of {chunk_id, document_id, filename, page_number, text}"""
    ix = get_ix()
    writer = ix.writer()
    for c in chunks:
        writer.update_document(
            chunk_id=c["chunk_id"],
            document_id=c["document_id"],
            filename=c["filename"],
            page_number=c["page_number"],
            text=c["text"],
            content=c["text"],
        )
    writer.commit()


def search(query_text: str, top_k: int = 20) -> list[dict]:
    ix = get_ix()
    with ix.searcher() as searcher:
        try:
            q = QueryParser("content", ix.schema).parse(query_text)
        except Exception:
            return []
        results = searcher.search(q, limit=top_k)
        return [
            {
                "chunk_id":    r["chunk_id"],
                "document_id": r["document_id"],
                "filename":    r["filename"],
                "page_number": r["page_number"],
                "text":        r["text"],
                "rank":        i,
            }
            for i, r in enumerate(results)
        ]


def delete_document(document_id: str) -> None:
    ix = get_ix()
    writer = ix.writer()
    writer.delete_by_term("document_id", document_id)
    writer.commit()
