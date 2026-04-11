from celery import shared_task
from core.models import Document, DocumentPage
from core.services.minio_client import MinioService
from core.tasks.embedding_task import process_page_embedding
import pdfplumber
import io
import logging

logger = logging.getLogger(__name__)


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=5, retry_kwargs={"max_retries": 3})
def process_document(self, document_id):
    logger.info(f"Processing document {document_id}")

    doc = Document.objects.filter(id=document_id).first()

    if not doc:
        logger.error("Document not found")
        return "Document not found"

    try:
        doc.status = "processing"
        doc.save(update_fields=["status"])

        if not doc.object_name:
            raise Exception("No object_name found")

        minio_service = MinioService()

        # ✅ Download file from MinIO
        response = minio_service.client.get_object(
            minio_service.bucket_name,
            doc.object_name
        )
        file_bytes = response.read()

        full_text = ""

        # ✅ Parse PDF
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            total_pages = len(pdf.pages)
            logger.info(f"Total pages: {total_pages}")

            # ✅ Save total pages (optional but useful)
            doc.total_pages = total_pages
            doc.save(update_fields=["total_pages"])

            for i, page in enumerate(pdf.pages):
                page_number = i + 1

                try:
                    # 🔹 Mark page as processing
                    page_obj, _ = DocumentPage.objects.update_or_create(
                        document=doc,
                        page_number=page_number,
                        defaults={"status": "processing"}
                    )

                    # 🔹 Extract text
                    text = page.extract_text() or ""

                    if text.strip():
                        full_text += text
                    else:
                        logger.warning(f"⚠️ Page {page_number} has no extractable text")

                    # 🔹 Convert page → image
                    page_image = page.to_image(resolution=150)
                    img_bytes = io.BytesIO()
                    page_image.save(img_bytes, format="PNG")
                    img_bytes.seek(0)

                    # 🔹 Upload image to MinIO
                    image_name = f"documents/{doc.id}/pages/page_{page_number}.png"

                    minio_service.client.put_object(
                        minio_service.bucket_name,
                        image_name,
                        img_bytes,
                        length=len(img_bytes.getvalue()),
                        content_type="image/png"
                    )

                    # 🔹 Build public URL
                    image_url = minio_service.get_file_url(image_name)
                    # image_url = f"http://localhost:9000/{minio_service.bucket_name}/{image_name}"

                    # 🔹 Save final page data
                    page_obj.text_content = text
                    page_obj.image_url = image_url
                    page_obj.status = "done" if text.strip() else "failed"
                    page_obj.save()

                    # 🔥 Queue embedding task for this page
                    process_page_embedding.apply_async(
                        args=[doc.id, page_number],
                        queue="embedding"
                    )

                except Exception as page_error:
                    logger.error(f"❌ Error processing page {page_number}: {str(page_error)}")

                    DocumentPage.objects.update_or_create(
                        document=doc,
                        page_number=page_number,
                        defaults={"status": "failed"}
                    )

        logger.info(f"Extracted text length: {len(full_text)}")

        if len(full_text.strip()) == 0:
            logger.warning("⚠️ No text found → likely scanned PDF")

        doc.status = "done"
        doc.save(update_fields=["status"])

        return "Done"

    except Exception as e:
        doc.status = "failed"
        doc.save(update_fields=["status"])
        logger.error(f"❌ Error processing document {document_id}: {str(e)}")
        raise