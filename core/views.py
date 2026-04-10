import uuid
import json
import pika
from rest_framework.views import APIView
from rest_framework.response import Response
from .models import Session, Document, DocumentPage, ChatSession, ChatMessage

from .services.minio_client import MinioService
from django.conf import settings
from core.tasks.Processing_task import process_document 
from rest_framework import status

from core.services.qdrant_service import QdrantService
from core.services.embedding_service import get_embedding
from core.tasks.process_chat import  process_chat_message

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

class GetDocumentPageView(APIView):
    """
    Fetch a single page of a document
    """

    def get(self, request):
        document_id = request.query_params.get("document_id")
        page_number = request.query_params.get("page")
        session_id = request.COOKIES.get("session_id")

        if not document_id or not page_number:
            return Response(
                {"error": "document_id and page are required"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        session_id = request.COOKIES.get("session_id")

        if not session_id:
            return Response({"error": "No session"}, status=401)
        
        try:
            uuid.UUID(session_id)
        except ValueError:
            return Response({"error": "Invalid session"}, status=401)
        
        session = Session.objects.filter(session_id=session_id).first()
        if not session:
            return Response({"error": "Session not found"}, status=401)

        try:
            page_number = int(page_number)
        except ValueError:
            return Response(
                {"error": "page must be an integer"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # 🔍 Check document
        document = Document.objects.filter(
            id=document_id,
            session=session
        ).first()
        if not document:
            return Response(
                {"error": "Document not found"},
                status=status.HTTP_404_NOT_FOUND
            )

        # 🔍 Get page
        page = DocumentPage.objects.filter(
            document=document,
            page_number=page_number
        ).first()

        if not page:
            return Response(
                {
                    "error": "Page not found",
                    "page": page_number,
                    "status": "pending"
                },
                status=status.HTTP_404_NOT_FOUND
            )

        # 🔢 Total pages (optional)
        total_pages = getattr(document, "total_pages", None)

        if not total_pages:
            total_pages = DocumentPage.objects.filter(document=document).count()

        return Response({
            "document_id": document.id,
            "page_number": page.page_number,
            "image_url": page.image_url,
            "text_content": page.text_content,
            "status": page.status,

            # 👉 Navigation helpers
            "has_next": page.page_number < total_pages,
            "has_prev": page.page_number > 1,
            "next_page": page.page_number + 1 if page.page_number < total_pages else None,
            "prev_page": page.page_number - 1 if page.page_number > 1 else None,

            # 👉 Optional metadata
            "total_pages": total_pages,
            "document_status": document.status,
        })
    


# 👉 replace with your LLM call
def call_llm(prompt: str):
    return "LLM response here"

class ChatSendView(APIView):

    def post(self, request):

        # 🔹 SESSION
        session_id = request.COOKIES.get("session_id")
        if not session_id:
            return Response({"error": "No session"}, status=401)

        session = Session.objects.filter(session_id=session_id).first()
        if not session:
            return Response({"error": "Invalid session"}, status=401)

        # 🔹 INPUTS
        document_id = request.data.get("document_id")
        message = request.data.get("message")
        intent = request.data.get("intent", "question")
        page_number = request.data.get("page")
        selected_text = request.data.get("selected_text")

        if not document_id:
            return Response({"error": "document_id required"}, status=400)

        document = Document.objects.filter(id=document_id).first()
        if not document:
            return Response({"error": "Document not found"}, status=404)

        # 🔹 PAGE
        page = None
        if page_number:
            page = DocumentPage.objects.filter(
                document=document,
                page_number=page_number
            ).first()

        # 🔹 CHAT SESSION
        chat, _ = ChatSession.objects.get_or_create(
            session=session,
            document=document
        )

        # 🔹 SAVE USER MESSAGE (NO LOGIC HERE)
        user_msg = ChatMessage.objects.create(
            chat=chat,
            role="user",
            intent=intent,  # optional, worker can override
            content=message or "",
            page=page,
            selected_text=selected_text,
            status="processing"
        )

        # 🔥 QUEUE TASK
        try:
            process_chat_message.apply_async(
                args=[user_msg.id],
                queue="chat_processing"
            )
        except Exception as e:
            user_msg.status = "failed"
            user_msg.error = str(e)
            user_msg.save()

            return Response({
                "error": "Failed to queue task",
                "details": str(e)
            }, status=500)

        return Response({
            "message_id": user_msg.id,
            "chat_id": chat.id,
            "status": "processing"
        })
    



class ChatStatusView(APIView):

    def get(self, request, message_id):

        # 🔹 get user message
        msg = ChatMessage.objects.filter(id=message_id).first()

        if not msg:
            return Response({"error": "Message not found"}, status=404)

        # 🔹 get assistant reply (child message)
        reply = ChatMessage.objects.filter(parent=msg, role="assistant").first()

        return Response({
            "message_id": msg.id,
            "status": msg.status,
            "answer": reply.content if reply else None,
            "error": msg.error
        })


class ChatHistoryView(APIView):
    """Get chat history for a specific document, page, and intent"""

    def get(self, request):
        # 🔹 SESSION
        session_id = request.COOKIES.get("session_id")
        if not session_id:
            return Response({"error": "No session"}, status=401)

        session = Session.objects.filter(session_id=session_id).first()
        if not session:
            return Response({"error": "Invalid session"}, status=401)

        # 🔹 INPUTS
        document_id = request.query_params.get("document_id")
        page_number = request.query_params.get("page")
        intent = request.query_params.get("intent")

        if not document_id:
            return Response({"error": "document_id required"}, status=400)

        document = Document.objects.filter(id=document_id).first()
        if not document:
            return Response({"error": "Document not found"}, status=404)

        # 🔹 CHAT SESSION
        chat = ChatSession.objects.filter(
            session=session,
            document=document
        ).first()

        if not chat:
            return Response({"messages": []})

        # 🔹 GET MESSAGES
        messages_query = ChatMessage.objects.filter(
            chat=chat,
            parent__isnull=True  # Only get user messages (root messages)
        ).order_by("created_at")

        # 🔹 FILTER BY PAGE if provided
        if page_number:
            messages_query = messages_query.filter(page__page_number=int(page_number))

        # 🔹 FILTER BY INTENT if provided
        if intent:
            messages_query = messages_query.filter(intent=intent)

        # 🔹 BUILD RESPONSE
        history = []
        for user_msg in messages_query:
            # Add user message
            history.append({
                "id": user_msg.id,
                "role": "user",
                "content": user_msg.content,
                "intent": user_msg.intent,
                "status": user_msg.status
            })

            # Add assistant reply if it exists
            reply = ChatMessage.objects.filter(parent=user_msg, role="assistant").first()
            if reply:
                history.append({
                    "id": reply.id,
                    "role": "assistant",
                    "content": reply.content,
                    "status": reply.status
                })

        return Response({"messages": history})