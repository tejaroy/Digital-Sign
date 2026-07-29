"""Upload and list signed PDFs in Amazon S3."""
import os
from datetime import timezone
from typing import Dict, List, Optional

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from django.conf import settings


def s3_enabled() -> bool:
    return bool(
        getattr(settings, "AWS_S3_BUCKET", None)
        and getattr(settings, "AWS_ACCESS_KEY_ID", None)
        and getattr(settings, "AWS_SECRET_ACCESS_KEY", None)
    )


def _client():
    return boto3.client(
        "s3",
        region_name=getattr(settings, "AWS_DEFAULT_REGION", "ap-south-1"),
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
    )


def _normalize_prefix(prefix: Optional[str] = None) -> str:
    if prefix is None:
        prefix = getattr(settings, "AWS_S3_PREFIX", "signed/") or ""
    prefix = prefix.lstrip("/")
    if prefix and not prefix.endswith("/"):
        prefix = prefix + "/"
    return prefix


def presigned_url(key: str, expires_in: int = 3600) -> str:
    """Temporary open/download URL (bucket can stay private)."""
    client = _client()
    bucket = settings.AWS_S3_BUCKET
    return client.generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket, "Key": key},
        ExpiresIn=expires_in,
    )


def upload_files(local_paths: List[str], prefix: Optional[str] = None) -> Dict[str, object]:
    """
    Copy local signed PDFs into the configured S3 bucket.

    Returns:
      {
        "ok": bool,
        "bucket": str,
        "uploaded": [{"local", "key", "url", "name"}, ...],
        "errors": [str, ...],
      }
    """
    bucket = getattr(settings, "AWS_S3_BUCKET", "")
    region = getattr(settings, "AWS_DEFAULT_REGION", "ap-south-1")
    prefix = _normalize_prefix(prefix)

    result = {
        "ok": True,
        "bucket": bucket,
        "region": region,
        "prefix": prefix,
        "uploaded": [],
        "errors": [],
    }

    if not s3_enabled():
        result["ok"] = False
        result["errors"].append("S3 is not configured (missing bucket or credentials).")
        return result

    client = _client()
    for path in local_paths:
        name = os.path.basename(path)
        key = "{}{}".format(prefix, name)
        try:
            extra = {
                "ContentType": "application/pdf",
                "Metadata": {"app": "digital-sign", "signed": "true"},
            }
            client.upload_file(path, bucket, key, ExtraArgs=extra)
            url = presigned_url(key)
            result["uploaded"].append(
                {"local": path, "key": key, "name": name, "url": url}
            )
        except (BotoCoreError, ClientError, OSError) as exc:
            result["ok"] = False
            result["errors"].append("{}: {}".format(name, exc))

    return result


def list_signed_documents(prefix: Optional[str] = None, max_keys: int = 500) -> Dict[str, object]:
    """
    List only signed PDFs saved by this app under the signed/ prefix.
    Other S3 folders/objects are ignored.
    """
    bucket = getattr(settings, "AWS_S3_BUCKET", "")
    region = getattr(settings, "AWS_DEFAULT_REGION", "ap-south-1")
    prefix = _normalize_prefix(prefix)

    result = {
        "ok": True,
        "bucket": bucket,
        "region": region,
        "prefix": prefix,
        "documents": [],
        "errors": [],
    }

    if not s3_enabled():
        result["ok"] = False
        result["errors"].append("S3 is not configured.")
        return result

    try:
        client = _client()
        paginator = client.get_paginator("list_objects_v2")
        pages = paginator.paginate(
            Bucket=bucket,
            Prefix=prefix,
            PaginationConfig={"MaxItems": max_keys},
        )
        docs = []
        for page in pages:
            for obj in page.get("Contents") or []:
                key = obj["Key"]
                # Only PDFs placed by this app under signed/ — skip folders & other types
                if key.endswith("/") or not key.lower().endswith(".pdf"):
                    continue
                # Must live directly under prefix (ignore nested unrelated paths if any)
                relative = key[len(prefix):] if key.startswith(prefix) else key
                if "/" in relative:
                    continue
                name = key.rsplit("/", 1)[-1]
                size = int(obj.get("Size") or 0)
                modified = obj.get("LastModified")
                if modified is not None and getattr(modified, "tzinfo", None):
                    modified = modified.astimezone(timezone.utc).replace(tzinfo=None)
                try:
                    url = presigned_url(key)
                except (BotoCoreError, ClientError):
                    url = ""
                docs.append(
                    {
                        "key": key,
                        "name": name,
                        "size": size,
                        "size_kb": round(size / 1024.0, 1),
                        "modified": modified,
                        "url": url,
                    }
                )
        docs.sort(key=lambda d: d.get("modified") or 0, reverse=True)
        result["documents"] = docs
    except (BotoCoreError, ClientError) as exc:
        result["ok"] = False
        result["errors"].append(str(exc))

    return result
