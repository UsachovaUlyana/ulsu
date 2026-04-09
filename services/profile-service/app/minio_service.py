"""MinIO (S3) service for photo storage."""

import io
import uuid
from typing import Optional

from minio import Minio
from minio.error import S3Error
import structlog

from app.config import settings

logger = structlog.get_logger(__name__)

# Initialize MinIO client
minio_client = Minio(
    settings.minio_endpoint,
    access_key=settings.minio_access_key,
    secret_key=settings.minio_secret_key,
    secure=False,  # HTTP for local development
)


def _ensure_bucket() -> None:
    """Create bucket if it doesn't exist."""
    try:
        if not minio_client.bucket_exists(settings.minio_bucket):
            minio_client.make_bucket(settings.minio_bucket)
            logger.info("bucket_created", bucket=settings.minio_bucket)
    except S3Error as e:
        logger.error("bucket_creation_failed", error=str(e))
        raise


def generate_s3_key(filename: str) -> str:
    """Generate a unique S3 key for a photo."""
    ext = filename.rsplit(".", 1)[-1] if "." in filename else "jpg"
    unique_id = uuid.uuid4().hex
    return f"photos/{unique_id}.{ext}"


async def upload_photo(photo_bytes: bytes, filename: str) -> str:
    """Upload a photo to MinIO and return the S3 key."""
    _ensure_bucket()

    s3_key = generate_s3_key(filename)
    content_type = "image/jpeg" if filename.lower().endswith((".jpg", ".jpeg")) else "image/png"

    try:
        minio_client.put_object(
            bucket_name=settings.minio_bucket,
            object_name=s3_key,
            data=io.BytesIO(photo_bytes),
            length=len(photo_bytes),
            content_type=content_type,
        )
        logger.info("photo_uploaded_to_s3", s3_key=s3_key, size=len(photo_bytes))
        return s3_key
    except S3Error as e:
        logger.error("s3_upload_failed", error=str(e))
        raise


async def delete_photo(s3_key: str) -> None:
    """Delete a photo from MinIO."""
    try:
        minio_client.remove_object(bucket_name=settings.minio_bucket, object_name=s3_key)
        logger.info("photo_deleted_from_s3", s3_key=s3_key)
    except S3Error as e:
        logger.error("s3_delete_failed", error=str(e))
        raise


async def get_presigned_url(s3_key: str, expires_seconds: int = 3600) -> Optional[str]:
    """Generate a presigned URL for temporary access to a photo."""
    try:
        url = minio_client.presigned_get_object(
            bucket_name=settings.minio_bucket,
            object_name=s3_key,
            expires=expires_seconds,
        )
        return url
    except S3Error as e:
        logger.error("presigned_url_failed", s3_key=s3_key, error=str(e))
        return None
