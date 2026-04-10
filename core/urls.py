from django.urls import path
from .views import ChatSendView, ChatStatusView, CreateSessionView, UploadBookView, ProcessDocumentView, GetSessionDocumentsView, GetDocumentPageView, ChatHistoryView

urlpatterns = [
    path("session/init/", CreateSessionView.as_view()),
    path("books/upload/", UploadBookView.as_view()),
    path("books/process/", ProcessDocumentView.as_view()),
    path("books/documents/", GetSessionDocumentsView.as_view()),
    path("books/page/", GetDocumentPageView.as_view()),
    path("chat/send/", ChatSendView.as_view()),
    path("chat/status/<int:message_id>/", ChatStatusView.as_view()),
    path("chat/history/", ChatHistoryView.as_view()),
]