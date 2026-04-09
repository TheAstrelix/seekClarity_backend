from celery import shared_task
from core.models import Document, DocumentPage
from core.services.minio_client import MinioService
import pdfplumber
import io
import logging
import time

logger = logging.getLogger(__name__)


@shared_task(bind=True)
def process_document(self, document_id):
    logger.info(f"Processing document {document_id}")

    doc = Document.objects.filter(id=document_id).first()

    if not doc:
        logger.error("Document not found")
        return "Document not found"

    try:
        doc.status = "processing"
        doc.save()

        if not doc.object_name:
            raise Exception("No object_name found")

        # ✅ Download from MinIO
        minio_service = MinioService()
        response = minio_service.client.get_object(
            minio_service.bucket_name,
            doc.object_name
        )

        file_bytes = response.read()

        full_text = ""

        # ✅ Parse PDF
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            logger.info(f"Pages: {len(pdf.pages)}")
            time.sleep(1)  # Simulate processing time
            for i, page in enumerate(pdf.pages):
                text = page.extract_text() or ""

                if text.strip():
                    full_text += text
                else:
                    logger.warning(f"⚠️ Page {i+1} has no extractable text")

                # ✅ Store page in DB
                DocumentPage.objects.update_or_create(
                    document=doc,
                    page_number=i + 1,
                    defaults={
                        "text_content": text,
                        "status": "done" if text.strip() else "failed"
                    }
                )

        logger.info(f"Extracted text length: {len(full_text)}")

        # ⚠️ fallback indicator (OCR can be added later)
        if len(full_text.strip()) == 0:
            logger.warning("⚠️ No text found → likely scanned PDF")

        doc.status = "done"
        doc.save()

        return "Done"

    except Exception as e:
        doc.status = "failed"
        doc.save()
        logger.error(f"Error processing document {document_id}: {str(e)}")
        raise