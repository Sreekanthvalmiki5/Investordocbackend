import asyncio
import uuid
from urllib.parse import urlparse

import boto3
from botocore.exceptions import ClientError, NoCredentialsError

from app.core.config import settings


class S3Service:

    def __init__(self):
        access_key = settings.AWS_ACCESS_KEY_ID or settings.AWS_ACCESS_KEY
        secret_key = settings.AWS_SECRET_ACCESS_KEY or settings.AWS_SECRET_KEY

        print("========== AWS CONFIG ==========")
        print("Bucket :", settings.AWS_BUCKET_NAME)
        print("Region :", settings.AWS_REGION)
        print("Access :", access_key[:4] + "********" if access_key else "NOT FOUND")
        print("================================")

        self.client = boto3.client(
            "s3",
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=settings.AWS_REGION,
        )

    @staticmethod
    def _resolve_key(value: str) -> str:
        """
        Resolve an S3 object key from either a direct key or a full S3 URL.

        Backward compatibility: existing documents may have full S3 URLs stored
        in `file_url`. This method detects whether the input is a full URL
        (contains ``://``) or already an S3 key and extracts the key accordingly.

        Args:
            value: Either a direct S3 object key or a full S3 URL.

        Returns:
            The S3 object key.
        """
        if "://" in value:
            # Legacy format: full S3 URL — extract the key
            parsed = urlparse(value)
            path = parsed.path.lstrip("/")
            # Handle both bucket.s3.region.amazonaws.com/key and bucket.s3.amazonaws.com/key formats
            if path.startswith(f"{settings.AWS_BUCKET_NAME}/"):
                return path[len(settings.AWS_BUCKET_NAME) + 1 :]
            return path
        # New format: already an S3 object key, use as-is
        return value

    async def upload_pdf(
        self,
        contents: bytes,
        filename: str,
        content_type: str,
        company_id: str,
    ) -> tuple[str, float]:
        """
        Upload a PDF to S3 and return the S3 object key.

        Returns:
            Tuple of (s3_object_key, size_mb).
            The key (e.g. "documents/<company_id>/<uuid>.pdf") is used to
            reconstruct presigned URLs later — no full S3 URL is stored.
        """
        extension = filename.split(".")[-1]

        key = f"documents/{company_id}/{uuid.uuid4()}.{extension}"

        print("Uploading to S3...")
        print("Bucket :", settings.AWS_BUCKET_NAME)
        print("Key    :", key)
        print("Size   :", len(contents))

        try:
            response = self.client.put_object(
                Bucket=settings.AWS_BUCKET_NAME,
                Key=key,
                Body=contents,
                ContentType=content_type,
            )

            print("Upload Successful")
            print(response)

        except NoCredentialsError:
            print("AWS credentials not found.")
            raise

        except ClientError as e:
            print("AWS Client Error")
            print(e.response)
            raise

        except Exception as e:
            import traceback
            traceback.print_exc()
            raise

        size_mb = round(len(contents) / (1024 * 1024), 2)

        return key, size_mb

    async def generate_presigned_url(self, key_or_url: str, expiration: int = 3600) -> str:
        """
        Generate a presigned GET URL for viewing a PDF in the browser.

        Accepts either a direct S3 object key (new format) or a full S3 URL
        (legacy format for backward compatibility).

        Args:
            key_or_url: The S3 object key or a full S3 URL of the object.
            expiration: Time in seconds until the URL expires (default 1 hour).

        Returns:
            A presigned URL string that can be used to view the PDF.
        """
        key = self._resolve_key(key_or_url)

        print("Generating presigned GET URL...")
        print("Bucket :", settings.AWS_BUCKET_NAME)
        print("Key    :", key)
        print("Expires:", expiration)

        try:
            url = await asyncio.to_thread(
                self.client.generate_presigned_url,
                "get_object",
                Params={
                    "Bucket": settings.AWS_BUCKET_NAME,
                    "Key": key,
                },
                ExpiresIn=expiration,
            )
            print("Presigned URL generated successfully")
            return url
        except NoCredentialsError:
            print("AWS credentials not found when generating presigned URL.")
            raise
        except ClientError as e:
            print("AWS Client Error while generating presigned URL")
            print(e.response)
            raise
        except Exception as e:
            import traceback
            traceback.print_exc()
            raise

    async def generate_download_url(self, key_or_url: str, expiration: int = 3600) -> str:
        """
        Generate a presigned GET URL with attachment disposition for downloading.

        Accepts either a direct S3 object key (new format) or a full S3 URL
        (legacy format for backward compatibility).

        Args:
            key_or_url: The S3 object key or a full S3 URL of the object.
            expiration: Time in seconds until the URL expires (default 1 hour).

        Returns:
            A presigned URL string that triggers a file download.
        """
        key = self._resolve_key(key_or_url)

        print("Generating presigned DOWNLOAD URL...")
        print("Bucket :", settings.AWS_BUCKET_NAME)
        print("Key    :", key)
        print("Expires:", expiration)

        try:
            # Extract filename from the key for the Content-Disposition header
            filename = key.split("/")[-1]

            url = await asyncio.to_thread(
                self.client.generate_presigned_url,
                "get_object",
                Params={
                    "Bucket": settings.AWS_BUCKET_NAME,
                    "Key": key,
                    "ResponseContentDisposition": f'attachment; filename="{filename}"',
                },
                ExpiresIn=expiration,
            )
            print("Presigned download URL generated successfully")
            return url
        except NoCredentialsError:
            print("AWS credentials not found when generating download URL.")
            raise
        except ClientError as e:
            print("AWS Client Error while generating download URL")
            print(e.response)
            raise
        except Exception as e:
            import traceback
            traceback.print_exc()
            raise

    async def download_pdf(self, key_or_url: str) -> bytes:
        """
        Download a PDF file from S3 using its object key.

        Accepts either a direct S3 object key (new format) or a full S3 URL
        (legacy format for backward compatibility).
        """
        key = self._resolve_key(key_or_url)

        print("Downloading from S3...")
        print("Bucket :", settings.AWS_BUCKET_NAME)
        print("Key    :", key)

        try:
            response = await asyncio.to_thread(
                self.client.get_object,
                Bucket=settings.AWS_BUCKET_NAME,
                Key=key,
            )
            body = response["Body"].read()
            return body
        except NoCredentialsError:
            print("AWS credentials not found when downloading.")
            raise
        except ClientError as e:
            print("AWS Client Error while downloading")
            print(e.response)
            raise
        except Exception as e:
            import traceback
            traceback.print_exc()
            raise