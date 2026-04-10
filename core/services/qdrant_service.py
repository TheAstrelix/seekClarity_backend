from qdrant_client import QdrantClient
from qdrant_client.models import VectorParams, Distance
from django.conf import settings
import time


class QdrantService:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)

            cls._instance.client = QdrantClient(
                host=settings.QDRANT_HOST,
                port=settings.QDRANT_PORT
            )

            cls._instance.collection_name = settings.QDRANT_COLLECTION

            cls._instance._ensure_collection()

        return cls._instance

    def _ensure_collection(self):
        # retry if qdrant not ready
        for _ in range(5):
            try:
                collections = self.client.get_collections().collections
                break
            except Exception:
                time.sleep(2)
        else:
            raise Exception("Qdrant not ready")

        collection_names = [c.name for c in collections]

        if self.collection_name not in collection_names:
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(
                    size=settings.QDRANT_VECTOR_SIZE,
                    distance=Distance.COSINE
                )
            )

    # 🔹 Insert vectors
    def upsert(self, points):
        self.client.upsert(
            collection_name=self.collection_name,
            points=points
        )

    # 🔹 Delete vectors by document and page
    def delete_by_page(self, document_id, page_number):
        # Qdrant supports delete with a filter; use must conditions for payload match
        filter_ = {
            "must": [
                {"key": "document_id", "match": {"value": document_id}},
                {"key": "page_number", "match": {"value": page_number}}
            ]
        }

        # The client.delete API accepts a filter param
        try:
            self.client.delete(
                collection_name=self.collection_name,
                filter=filter_
            )
        except Exception:
            # best-effort: ignore if delete fails (caller will retry via Celery)
            pass

    # 🔹 Search vectors
    def search(self, query_vector, document_id, page=None, limit=5):
        must_filters = [
            {"key": "document_id", "match": {"value": document_id}}
        ]

        if page:
            must_filters.append({
                "key": "page_number",
                "range": {"gte": page - 2, "lte": page + 2}
            })

        return self.client.search(
            collection_name=self.collection_name,
            query_vector=query_vector,
            limit=limit,
            query_filter={"must": must_filters}
        )