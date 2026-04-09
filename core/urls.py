from django.urls import path
from .views import CreateSessionView, UploadBookView, ProcessDocumentView, GetSessionDocumentsView

urlpatterns = [
    path("session/init/", CreateSessionView.as_view()),
    path("books/upload/", UploadBookView.as_view()),
    path("books/process/", ProcessDocumentView.as_view()),
    path("books/documents/", GetSessionDocumentsView.as_view()),
]