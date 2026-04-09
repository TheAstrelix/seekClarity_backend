from minio import Minio
from django.conf import settings
import uuid


class MinioService:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(MinioService, cls).__new__(cls)

            # ✅ initialize client only once
            cls._instance.client = Minio(
                settings.MINIO_ENDPOINT,
                access_key=settings.MINIO_ACCESS_KEY,
                secret_key=settings.MINIO_SECRET_KEY,
                secure=settings.MINIO_SECURE
            )

            cls._instance.bucket_name = settings.MINIO_BUCKET

            # ✅ ensure bucket exists
            cls._instance._ensure_bucket()

        return cls._instance


    def _ensure_bucket(self):
        if not self.client.bucket_exists(self.bucket_name):
            self.client.make_bucket(self.bucket_name)


    def upload_file(self, file, folder="uploads"):
        object_name = f"{folder}/{uuid.uuid4()}_{file.name}"

        self.client.put_object(
            self.bucket_name,
            object_name,
            file,
            length=-1,
            part_size=10 * 1024 * 1024
        )

        return {
            "object_name": object_name,
            "file_url": self.get_file_url(object_name)
        }


    def upload_bytes(self, data: bytes, object_name: str, content_type="image/png"):
        from io import BytesIO

        self.client.put_object(
            self.bucket_name,
            object_name,
            BytesIO(data),
            length=len(data),
            content_type=content_type
        )

        return self.get_file_url(object_name)

    def get_file_url(self, object_name):
        return f"http://{settings.MINIO_ENDPOINT}/{self.bucket_name}/{object_name}"

    def delete_file(self, object_name):
        self.client.remove_object(self.bucket_name, object_name)