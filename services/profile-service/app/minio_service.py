from __future__ import annotations

import io
import uuid
from datetime import timedelta

from minio import Minio
from minio.error import S3Error

from shared.logging import get_logger

from .config import settings

logger = get_logger(__name__)


class MinioService:
    def __init__(self) -> None:
        self.client = Minio(
            settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure,
        )
        self.bucket = settings.minio_bucket
        self._ensure_bucket()

    def _ensure_bucket(self) -> None:
        try:
            if not self.client.bucket_exists(self.bucket):
                self.client.make_bucket(self.bucket)
                logger.info("minio_bucket_created", bucket=self.bucket)
        except S3Error:
            logger.exception("minio_bucket_check_failed", bucket=self.bucket)
            raise

    def upload(
        self, telegram_id: int, data: bytes, content_type: str = "image/jpeg"
    ) -> str:
        ext = "jpg" if "jpeg" in content_type else content_type.split("/")[-1]
        key = f"users/{telegram_id}/{uuid.uuid4().hex}.{ext}"
        self.client.put_object(
            self.bucket,
            key,
            io.BytesIO(data),
            length=len(data),
            content_type=content_type,
        )
        return key

    def delete(self, key: str) -> None:
        try:
            self.client.remove_object(self.bucket, key)
        except S3Error:
            logger.exception("minio_delete_failed", key=key)

    def presigned_url(self, key: str) -> str:
        return self.client.presigned_get_object(
            self.bucket,
            key,
            expires=timedelta(seconds=settings.presigned_url_ttl_seconds),
        )


_singleton: MinioService | None = None


def get_minio() -> MinioService:
    global _singleton
    if _singleton is None:
        _singleton = MinioService()
    return _singleton
