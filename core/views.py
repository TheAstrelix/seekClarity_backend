import uuid
import json
import pika
from rest_framework.views import APIView
from rest_framework.response import Response
from .models import Session, Document
from .services.minio_client import MinioService
from django.conf import settings
from core.tasks import process_document 


class CreateSessionView(APIView):

    def get(self, request):
        # Check if session already exists in cookie
        session_id = request.COOKIES.get("session_id")

        if session_id:
            try:
                # Validate that session_id is a proper UUID before querying
                uuid.UUID(session_id)
                session = Session.objects.get(session_id=session_id)
                return Response({
                    "message": "Session already exists",
                    "session_id": str(session.session_id)
                })
            except (Session.DoesNotExist, ValueError):
                # ValueError is raised if session_id is not a valid UUID
                pass

        # Create new session
        new_session_id = uuid.uuid4()
        session = Session.objects.create(
            session_id=new_session_id,
            ip_address=request.META.get("REMOTE_ADDR"),
            user_agent=request.META.get("HTTP_USER_AGENT", "")
        )

        response = Response({
            "message": "New session created",
            "session_id": str(session.session_id)
        })

        # 🔥 Set cookie (30 days) - Make sure to convert UUID to string
        response.set_cookie(
            key="session_id",
            value=str(new_session_id),
            max_age=60 * 60 * 24 * 30,
            httponly=True,
            samesite="Lax",
            path="/"
        )

        return response
    
from rest_framework.views import APIView




class UploadBookView(APIView):

    def post(self, request):
        file = request.FILES.get("file")

        if not file:
            return Response({"error": "No file"}, status=400)

        # ✅ get session
        session_id = request.COOKIES.get("session_id")

        if not session_id:
            return Response({"error": "No session"}, status=401)

        # Validate that session_id is a proper UUID
        try:
            uuid.UUID(session_id)
        except ValueError:
            return Response({"error": "Invalid session ID format"}, status=401)

        session = Session.objects.filter(session_id=session_id).first()

        if not session:
            return Response({"error": "Invalid session"}, status=401)

        # ✅ upload to MinIO
        minio = MinioService()
        result = minio.upload_file(file, folder="documents")

        # ✅ save document
        doc = Document.objects.create(
            session=session,
            file_name=file.name,
            file_url=result["file_url"],
            object_name=result["object_name"],
            file_size=file.size,
            status="uploaded"
        )

        return Response({
            "document_id": doc.id,
            "file_url": doc.file_url,
            "status": doc.status
        })
    

class ProcessDocumentView(APIView):

    QUEUE_NAME = "document_processing"

    def post(self, request):
        document_id = request.data.get("document_id")

        if not document_id:
            return Response({"error": "document_id required"}, status=400)

        doc = Document.objects.filter(id=document_id).first()

        if not doc:
            return Response({"error": "Document not found"}, status=404)

        doc.status = "queued"
        doc.save()

        try:
            # ✅ send task to Celery
            process_document.apply_async(
                args=[doc.id],
                queue="document_processing"
            )

        except Exception as e:
            doc.status = "failed"
            doc.save()

            return Response({
                "error": "Failed to queue task",
                "details": str(e)
            }, status=500)

        return Response({
            "message": "Queued successfully",
            "document_id": doc.id
        })


class GetSessionDocumentsView(APIView):
    """Get all documents for the current session"""

    def get(self, request):
        session_id = request.COOKIES.get("session_id")

        if not session_id:
            return Response({"error": "No session"}, status=401)

        # Validate UUID format
        try:
            uuid.UUID(session_id)
        except ValueError:
            return Response({"error": "Invalid session ID format"}, status=401)

        session = Session.objects.filter(session_id=session_id).first()

        if not session:
            return Response({"error": "Invalid session"}, status=401)

        # Get all documents for this session
        documents = Document.objects.filter(session=session).order_by("-created_at")

        docs_data = [
            {
                "id": doc.id,
                "file_name": doc.file_name,
                "file_url": doc.file_url,
                "file_size": doc.file_size,
                "status": doc.status,
                "created_at": doc.created_at.isoformat(),
            }
            for doc in documents
        ]

        return Response({
            "session_id": str(session.session_id),
            "documents": docs_data
        })
