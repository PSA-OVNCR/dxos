# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Kho đối tượng S3 (SeaweedFS) với 3 bucket: staging, objects (CAS theo sha256), quarantine.

- staging: khóa ``<upload_id>``; **không có API nào đọc** (AT-04), chỉ worker đọc để quét.
- objects: khóa ``<sha256>``; không bao giờ ghi đè; đọc thì băm lại để phát hiện sửa trên đĩa.
- quarantine: khóa ``<upload_id>``; tệp nhiễm hoặc bị từ chối.

Các phương thức là đồng bộ (boto3); mã async gọi qua ``asyncio.to_thread``.
"""

import hashlib
from uuid import UUID

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from dxos_core.settings import Settings, read_secret


class IntegrityError(Exception):
    """Nội dung đọc từ kho không khớp sha256 của nó."""


def _missing(exc: ClientError) -> bool:
    return exc.response.get("Error", {}).get("Code") in ("404", "NoSuchKey", "NotFound", "NoSuchBucket")


class ObjectStore:
    def __init__(self, settings: Settings) -> None:
        self.staging = settings.s3_bucket_staging
        self.objects = settings.s3_bucket_objects
        self.quarantine = settings.s3_bucket_quarantine
        self._s3 = boto3.client(
            "s3", endpoint_url=settings.s3_endpoint, region_name="us-east-1",
            aws_access_key_id=read_secret(settings.s3_access_key_file),
            aws_secret_access_key=read_secret(settings.s3_secret_key_file),
            config=Config(s3={"addressing_style": "path"}, retries={"max_attempts": 3},
                          connect_timeout=5, read_timeout=30),
        )

    # -------------------------------------------------------- bucket
    def ensure_buckets(self) -> None:
        for b in (self.staging, self.objects, self.quarantine):
            try:
                self._s3.head_bucket(Bucket=b)
            except ClientError:
                self._s3.create_bucket(Bucket=b)

    def drop_buckets(self) -> None:
        """Chỉ dùng trong test."""
        for b in (self.staging, self.objects, self.quarantine):
            try:
                for key in self.list_keys(b):
                    self._s3.delete_object(Bucket=b, Key=key)
                self._s3.delete_bucket(Bucket=b)
            except ClientError:
                pass

    def list_keys(self, bucket: str) -> list[str]:
        out = []
        for page in self._s3.get_paginator("list_objects_v2").paginate(Bucket=bucket):
            out += [o["Key"] for o in page.get("Contents", [])]
        return sorted(out)

    # -------------------------------------------------------- thấp
    def put_raw(self, bucket: str, key: str, data: bytes) -> None:
        self._s3.put_object(Bucket=bucket, Key=key, Body=data)

    def get_raw(self, bucket: str, key: str) -> bytes:
        return self._s3.get_object(Bucket=bucket, Key=key)["Body"].read()

    def exists(self, bucket: str, key: str) -> bool:
        try:
            self._s3.head_object(Bucket=bucket, Key=key)
            return True
        except ClientError as exc:
            if _missing(exc):
                return False
            raise

    def _copy(self, src_bucket: str, src_key: str, dst_bucket: str, dst_key: str, data: bytes | None) -> None:
        """Chép object; có sẵn ``data`` thì ghi thẳng (nhanh hơn copy phía server)."""
        if data is None:
            self._s3.copy_object(Bucket=dst_bucket, Key=dst_key,
                                 CopySource={"Bucket": src_bucket, "Key": src_key})
        else:
            self._s3.put_object(Bucket=dst_bucket, Key=dst_key, Body=data)

    def delete_staging(self, upload_id: UUID) -> None:
        self._s3.delete_object(Bucket=self.staging, Key=str(upload_id))

    # -------------------------------------------------------- theo Plan 01 Task 14
    def put_staging(self, upload_id: UUID, data: bytes) -> None:
        self.put_raw(self.staging, str(upload_id), data)

    def read_staging(self, upload_id: UUID) -> bytes:
        return self.get_raw(self.staging, str(upload_id))

    def promote(self, upload_id: UUID, sha256: str, *, data: bytes | None = None,
                delete_staging: bool = True) -> bool:
        """Đưa tệp staging vào CAS. Đã có object cùng sha256 thì trả False và **không ghi đè**.

        ``delete_staging=False``: giữ bản staging tới khi DB đã commit (worker gọi ``delete_staging`` sau),
        để lỗi giữa chừng không làm mất tệp và việc thử lại vẫn đọc được staging.
        """
        created = False
        if not self.exists(self.objects, sha256):
            if data is not None and hashlib.sha256(data).hexdigest() != sha256:
                raise IntegrityError("data không khớp sha256")
            self._copy(self.staging, str(upload_id), self.objects, sha256, data)
            created = True
        if delete_staging:
            self.delete_staging(upload_id)
        return created

    def move_to_quarantine(self, upload_id: UUID, *, data: bytes | None = None,
                           delete_staging: bool = True) -> None:
        self._copy(self.staging, str(upload_id), self.quarantine, str(upload_id), data)
        if delete_staging:
            self.delete_staging(upload_id)

    def read_object(self, sha256: str) -> bytes:
        data = self.get_raw(self.objects, sha256)
        if hashlib.sha256(data).hexdigest() != sha256:
            raise IntegrityError(f"object {sha256} bị sửa trong kho")
        return data
