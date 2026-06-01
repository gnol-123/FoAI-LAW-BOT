from fastembed import TextEmbedding

MODEL_NAME = "BAAI/bge-base-en-v1.5"   # 768 dims, quantized ONNX — runs on CPU, no PyTorch

_model = None


def _get_model() -> TextEmbedding:
    global _model
    if _model is None:
        # Downloads ~100MB on first run, cached in ~/.cache/fastembed afterwards
        _model = TextEmbedding(MODEL_NAME)
    return _model


def embed(text: str) -> list[float]:
    return next(_get_model().embed([text])).tolist()


def embed_batch(texts: list[str]) -> list[list[float]]:
    return [e.tolist() for e in _get_model().embed(texts)]
