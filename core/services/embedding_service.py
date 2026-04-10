from sentence_transformers import SentenceTransformer

# load once (important)
_model = None


def get_embedding(texts):
    global _model

    if _model is None:
        _model = SentenceTransformer("all-MiniLM-L6-v2")

    embeddings = _model.encode(
        texts,
        normalize_embeddings=True
    )

    return embeddings.tolist()