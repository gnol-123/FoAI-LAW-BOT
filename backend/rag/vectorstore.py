import os
from pinecone import Pinecone, ServerlessSpec

INDEX_NAME = "loraai-legal"
DIMENSION  = 768    # togethercomputer/m2-bert-80M-8k-retrieval

_index = None


def get_index():
    global _index
    if _index is None:
        pc = Pinecone(api_key=os.environ["PINECONE_API_KEY"])
        existing = [i.name for i in pc.list_indexes()]
        if INDEX_NAME not in existing:
            pc.create_index(
                name=INDEX_NAME,
                dimension=DIMENSION,
                metric="cosine",
                spec=ServerlessSpec(cloud="aws", region="us-east-1"),
            )
        _index = pc.Index(INDEX_NAME)
    return _index
