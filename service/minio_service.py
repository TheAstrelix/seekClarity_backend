from minio import Minio
from minio.error import S3Error
from django.conf import settings

class MinIOService:
    def __init__(self):
        self.client = Minio(
            endpoint=settings.MINIO_ENDPOINT,
            access_key=settings.MINIO_ACCESS_KEY,
            secret_key=settings.MINIO_SECRET_KEY,
            secure=settings.MINIO_SECURE
        )
    def ensure_bucket_exists(self, bucket_name: str):
        try:
            if not self.client.bucket_exists(bucket_name):
                self.client.make_bucket(bucket_name)
        except S3Error as e:
            raise Exception(f"Bucket error: {e}")
    def upload_file(self, bucket_name: str, file_path: str, object_name: str):
        self.ensure_bucket_exists(bucket_name)
        try:
            self.client.fput_object(bucket_name, object_name, file_path)
            return object_name
        except S3Error as e:
            raise Exception(f"File upload error: {e}")
        
    def upload_fileobj(self, bucket_name, object_name, file_obj, size):
        self.ensure_bucket_exists(bucket_name)
        try:
            self.client.put_object(bucket_name, object_name, file_obj, size)
            return object_name
        except S3Error as e:
            raise Exception(f"Upload error: {e}")

    def get_url(self, bucket_name, object_name):
        try:
            return self.client.presigned_get_object(bucket_name, object_name)
        except S3Error as e:
            raise Exception(f"URL error: {e}")
