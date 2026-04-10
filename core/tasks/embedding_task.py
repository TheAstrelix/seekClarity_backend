from celery import shared_task
from core.models import DocumentPage
# from core.services.qdrant_client import QdrantService
from core.services.qdrant_service import QdrantService
from core.services.embedding_service import get_embedding
import uuid
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def chunk_text(text, chunk_size=500, overlap=50):
    chunks = []
    start = 0

    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        start += chunk_size - overlap

    return chunks

@shared_task(bind=True, queue="embedding", autoretry_for=(Exception,), retry_backoff=5, retry_kwargs={"max_retries": 3})
def process_page_embedding(self, document_id, page_number):

    page = DocumentPage.objects.filter(
        document_id=document_id,
        page_number=page_number
    ).first()

    if not page or not page.text_content:
        return

    qdrant = QdrantService()

    # 🔥 remove old embeddings
    qdrant.delete_by_page(document_id, page_number)

    chunks = chunk_text(page.text_content)

    if not chunks:
        return

    # 🔥 batch embedding
    embeddings = get_embedding(chunks)

    points = []

    for idx, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
        logging.info(f"Processing chunk {idx + 1}/{len(chunks)}")
        points.append({
            "id": str(uuid.uuid4()),
            "vector": embedding,
            "payload": {
                "document_id": document_id,
                "page_number": page_number,
                "chunk_index": idx,
                "text": chunk
            }
        })

    qdrant.upsert(points)