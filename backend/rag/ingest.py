import os
import tempfile

from pypdf import PdfReader
from langchain_text_splitters import RecursiveCharacterTextSplitter

from .embeddings import embed_batch
from .vectorstore import get_index
from .sparse_index import add_chunks as whoosh_add, delete_document as whoosh_delete

CHUNK_SIZE    = 1000
CHUNK_OVERLAP = 150
UPSERT_BATCH  = 96


def ingest_pdf(file_bytes: bytes, doc_id: str, filename: str) -> int:
    """
    PDF bytes → extract text → chunk → embed (Pinecone) + index (Whoosh).
    Returns number of chunks stored.
    """
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(file_bytes)
        tmp_path = tmp.name

    try:
        reader = PdfReader(tmp_path)
        raw_pages = []
        for page_num, page in enumerate(reader.pages, 1):
            text = (page.extract_text() or "").strip()
            if text:
                raw_pages.append({"text": text, "page": page_num})
    finally:
        os.unlink(tmp_path)

    if not raw_pages:
        raise ValueError("No extractable text found. The PDF may be scanned/image-based.")

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
    )

    chunks = []
    for page in raw_pages:
        for chunk_text in splitter.split_text(page["text"]):
            chunks.append({
                "text":  chunk_text,
                "page":  page["page"],
                "index": len(chunks),
            })

    # ── Pinecone (dense) ─────────────────────────────────────────────────────
    index = get_index()
    for batch_start in range(0, len(chunks), UPSERT_BATCH):
        batch = chunks[batch_start : batch_start + UPSERT_BATCH]
        embeddings = embed_batch([c["text"] for c in batch])
        vectors = [
            {
                "id":     f"{doc_id}_{c['index']}",
                "values": emb,
                "metadata": {
                    "documentId": doc_id,
                    "filename":   filename,
                    "text":       c["text"],
                    "pageNumber": c["page"],
                },
            }
            for c, emb in zip(batch, embeddings)
        ]
        index.upsert(vectors=vectors)

    # ── Whoosh (sparse / BM25) ────────────────────────────────────────────────
    whoosh_add([
        {
            "chunk_id":    f"{doc_id}_{c['index']}",
            "document_id": doc_id,
            "filename":    filename,
            "page_number": c["page"],
            "text":        c["text"],
        }
        for c in chunks
    ])

    return len(chunks)


def delete_document_vectors(doc_id: str, chunk_count: int) -> None:
    # Remove from Pinecone
    ids = [f"{doc_id}_{i}" for i in range(chunk_count)]
    index = get_index()
    for i in range(0, len(ids), 1000):
        index.delete(ids=ids[i : i + 1000])

    # Remove from Whoosh
    whoosh_delete(doc_id)
