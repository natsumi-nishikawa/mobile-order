import os
from io import BytesIO
from pathlib import Path
from uuid import uuid4

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from fastapi import HTTPException, UploadFile


MAX_IMAGE_SIZE = 5 * 1024 * 1024
ALLOWED_IMAGE_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}


def _settings() -> tuple[str, str]:
    region = os.getenv("AWS_REGION")
    bucket = os.getenv("AWS_S3_BUCKET_NAME")
    if not region or not bucket:
        raise HTTPException(status_code=503, detail="S3の設定が完了していません")
    return region, bucket


def _client():
    region, _ = _settings()
    return boto3.client("s3", region_name=region)


def _has_valid_signature(data: bytes, content_type: str) -> bool:
    if content_type == "image/jpeg":
        return data.startswith(b"\xff\xd8\xff")
    if content_type == "image/png":
        return data.startswith(b"\x89PNG\r\n\x1a\n")
    if content_type == "image/webp":
        return len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP"
    return False


async def upload_product_image(file: UploadFile) -> str:
    content_type = (file.content_type or "").lower()
    extension = ALLOWED_IMAGE_TYPES.get(content_type)
    filename_extension = Path(file.filename or "").suffix.lower()
    if extension is None or filename_extension not in {".jpg", ".jpeg", ".png", ".webp"}:
        raise HTTPException(status_code=422, detail="jpg、jpeg、png、webp画像を選択してください")

    data = await file.read(MAX_IMAGE_SIZE + 1)
    await file.close()
    if len(data) > MAX_IMAGE_SIZE:
        raise HTTPException(status_code=413, detail="画像サイズは5MB以下にしてください")
    if not data or not _has_valid_signature(data, content_type):
        raise HTTPException(status_code=422, detail="画像ファイルの内容を確認できません")

    _, bucket = _settings()
    object_key = f"products/{uuid4().hex}{extension}"
    try:
        _client().upload_fileobj(
            BytesIO(data),
            bucket,
            object_key,
            ExtraArgs={"ContentType": content_type},
        )
    except (BotoCoreError, ClientError):
        raise HTTPException(status_code=502, detail="画像をS3へ保存できませんでした")
    return object_key


def create_image_url(object_key: str | None) -> str | None:
    if not object_key:
        return None
    if object_key.startswith(("http://", "https://")):
        return object_key
    _, bucket = _settings()
    try:
        return _client().generate_presigned_url(
            "get_object",
            Params={"Bucket": bucket, "Key": object_key},
            ExpiresIn=3600,
        )
    except (BotoCoreError, ClientError):
        return None


def delete_product_image(object_key: str | None) -> bool:
    if not object_key or object_key.startswith(("http://", "https://")):
        return True
    _, bucket = _settings()
    try:
        _client().delete_object(Bucket=bucket, Key=object_key)
        return True
    except (BotoCoreError, ClientError):
        return False

