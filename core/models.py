import uuid
from django.db import models

# Create your models here.
class Session(models.Model):
    session_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    ip_address = models.GenericIPAddressField()
    user_agent = models.TextField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    last_active = models.DateTimeField(auto_now=True)

    def __str__(self):
        return str(self.session_id)

class Document(models.Model):

    STATUS_CHOICES = [
        ("uploaded", "Uploaded"),
        ("processing", "Processing"),
        ("done", "Done"),
        ("failed", "Failed"),
    ]

    session = models.ForeignKey(
        "Session",
        on_delete=models.CASCADE,
        related_name="documents"
    )

    file_name = models.CharField(max_length=255)
    file_url = models.TextField()
    object_name = models.CharField(max_length=500, null=True, blank=True)
    total_pages = models.IntegerField(null=True, blank=True)

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="uploaded",
        db_index=True
    )

    file_size = models.BigIntegerField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.file_name
    
class DocumentPage(models.Model):

    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("processing", "Processing"),
        ("done", "Done"),
        ("failed", "Failed"),
    ]

    document = models.ForeignKey(
        "Document",
        on_delete=models.CASCADE,
        related_name="pages"
    )

    page_number = models.IntegerField()

    image_url = models.TextField(null=True, blank=True)

    text_content = models.TextField(null=True, blank=True)

    # embedding = models.JSONField(null=True, blank=True)

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="pending",
        db_index=True
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("document", "page_number")
        ordering = ["page_number"]

    def __str__(self):
        return f"{self.document.id} - Page {self.page_number}"


class ChatSession(models.Model):
    session = models.ForeignKey("Session", on_delete=models.CASCADE)
    document = models.ForeignKey("Document", on_delete=models.CASCADE)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("session", "document")
        indexes = [
            models.Index(fields=["session", "document"]),
        ]

class ChatMessage(models.Model):

    ROLE_CHOICES = [
        ("user", "User"),
        ("assistant", "Assistant"),
    ]

    INTENT_CHOICES = [
        ("question", "Question"),
        ("summary", "Summary"),
        ("highlight", "Highlight"),
        ("generate_questions", "Generate Questions"),
        ("global_query", "Global Query"),
    ]

    STATUS_CHOICES = [
        ("processing", "Processing"),
        ("done", "Done"),
        ("failed", "Failed"),
    ]

    chat = models.ForeignKey(
        "ChatSession",
        on_delete=models.CASCADE,
        related_name="messages"
    )

    role = models.CharField(max_length=10, choices=ROLE_CHOICES)
    intent = models.CharField(max_length=30, choices=INTENT_CHOICES)

    content = models.TextField()

    # 🔥 async tracking
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="processing"
    )

    error = models.TextField(null=True, blank=True)

    # 🔥 context
    page = models.ForeignKey(
        "DocumentPage",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="chat_messages"
    )

    selected_text = models.TextField(null=True, blank=True)

    # 🔥 structured outputs (questions, etc.)
    metadata = models.JSONField(null=True, blank=True)

    # 🔥 follow-up threading
    parent = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="replies"
    )

    # 🔥 OPTIONAL (huge optimization)
    embedding = models.JSONField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["chat", "created_at"]),
            models.Index(fields=["chat", "page"]),
            models.Index(fields=["status"]),
        ]