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

    async def upload_pdf(
        self,
        contents: bytes,
        filename: str,
        content_type: str,
        company_id: str,
    ) -> tuple[str, float]:

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

        file_url = (
            f"https://{settings.AWS_BUCKET_NAME}.s3."
            f"{settings.AWS_REGION}.amazonaws.com/{key}"
        )

        size_mb = round(len(contents) / (1024 * 1024), 2)

        return file_url, size_mb

    async def download_pdf(self, file_url: str) -> bytes:
        """Download a PDF file from S3 using its public URL."""
        parsed = urlparse(file_url)
        path = parsed.path.lstrip("/")

        if path.startswith(f"{settings.AWS_BUCKET_NAME}/"):
            key = path[len(settings.AWS_BUCKET_NAME) + 1 :]
        else:
            key = path

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