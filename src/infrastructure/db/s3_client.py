"""S3 client for uploading validated transcript data."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import re
import boto3
from botocore.exceptions import BotoCoreError, ClientError

from infrastructure.config import (
    AWS_ACCESS_KEY_ID,
    AWS_REGION,
    AWS_S3_BUCKET_NAME,
    AWS_S3_PREFIX,
    AWS_SECRET_ACCESS_KEY,
    KB_DIR,
)
from infrastructure.log import get_logger

log = get_logger(__name__)


class S3Client:
    """Validate AWS S3 access and upload transcript JSON objects."""

    def __init__(self, source_dir: Path | None = None) -> None:
        self.source_dir = source_dir or KB_DIR
        self.bucket = AWS_S3_BUCKET_NAME
        self.prefix = AWS_S3_PREFIX
        self.region = AWS_REGION
        self._client: Any | None = None
        self._run_prefix: str | None = None

    def _build_run_prefix(self) -> str:
        """Build a unique prefix for this upload run: raw/YYYYMMDD-HHMMSS/."""
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        base = self.prefix if self.prefix.endswith("/") else f"{self.prefix}/"
        return f"{base}{stamp}/"

    def _object_key(self, transcript_id: str) -> str:
        if self._run_prefix is None:
            self._run_prefix = self._build_run_prefix()
        return f"{self._run_prefix}{transcript_id}.json"

    def _get_client(self) -> Any:
        if self._client is None:
            self._client = boto3.client(
                "s3",
                aws_access_key_id=AWS_ACCESS_KEY_ID,
                aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
                region_name=self.region,
            )
        return self._client

    def validate_config(self) -> None:
        """Ensure required AWS settings from config are present."""
        missing = [
            name
            for name, value in {
                "AWS_ACCESS_KEY_ID": AWS_ACCESS_KEY_ID,
                "AWS_SECRET_ACCESS_KEY": AWS_SECRET_ACCESS_KEY,
                "AWS_S3_BUCKET_NAME": AWS_S3_BUCKET_NAME,
                "AWS_REGION": AWS_REGION,
            }.items()
            if not value
        ]
        if missing:
            log.error("Missing required AWS configuration: {}", ", ".join(missing))
            raise ValueError(f"Missing required AWS configuration: {', '.join(missing)}")

        log.info("AWS configuration validated")

    def bucket_exists(self) -> bool:
        """Check whether the target S3 bucket exists and is reachable."""
        if not self.bucket:
            log.error("AWS_S3_BUCKET_NAME is not set")
            return False

        try:
            self._get_client().head_bucket(Bucket=self.bucket)
            log.info("Bucket exists and is reachable: {}", self.bucket)
            return True
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            if code in {"404", "NoSuchBucket", "NotFound"}:
                log.error("Bucket does not exist: {}", self.bucket)
            else:
                log.error("Unable to access bucket {}: {}", self.bucket, exc)
            return False
        except BotoCoreError as exc:
            log.error("AWS connection error while checking bucket {}: {}", self.bucket, exc)
            return False

    def validate_source_dir(self) -> list[Path]:
        """Validate the local transcript folder and return JSON files ready for upload."""
        if not self.source_dir.is_dir():
            log.error("Source directory does not exist: {}", self.source_dir)
            raise FileNotFoundError(f"Source directory does not exist: {self.source_dir}")

        files = sorted(
            p for p in self.source_dir.iterdir() if p.is_file() and p.suffix.lower() == ".json"
        )
        if not files:
            log.warning("No JSON files found to upload in {}", self.source_dir)
            return []

        log.info("Found {} JSON file(s) ready for upload in {}", len(files), self.source_dir)
        return files

    def validate_upload_ready(self) -> list[Path]:
        """Run AWS and folder checks before upload."""
        self.validate_config()

        if not self.bucket_exists():
            raise ValueError(f"S3 bucket does not exist or is not accessible: {self.bucket}")

        files = self.validate_source_dir()
        self._run_prefix = self._build_run_prefix()
        log.success(
            "Pre-upload validation passed for s3://{}/{}",
            self.bucket,
            self._run_prefix,
        )
        return files

    def upload_transcript(self, data: dict[str, Any]) -> bool:
        """Upload validated transcript data to S3."""
        transcript_id = data["transcript_id"]
        s3_key = self._object_key(transcript_id)
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")

        try:
            self._get_client().put_object(
                Bucket=self.bucket,
                Key=s3_key,
                Body=body,
                ContentType="application/json",
            )
            log.success("Uploaded {} -> s3://{}/{}", transcript_id, self.bucket, s3_key)
            return True
        except (BotoCoreError, ClientError) as exc:
            log.error("Failed to upload {}: {}", transcript_id, exc)
            return False
    
    def load_json_objects(self) -> list[dict[str, Any]]:
        data=[]

        """geeting latest JSON objects from S3."""
        s3_client = self._get_client()

        # lsit all folders under raw/ prefix and get the latest one
        response = s3_client.list_objects_v2(
            Bucket=self.bucket,
            Prefix="raw/",
        )
        if response.get("Contents") is None:
            log.warning("No JSON files found to upload in {}", self.source_dir)
            return []
        
        # sort by last modified date
        response["Contents"].sort(key=lambda x: x["LastModified"])
        latest_folder = response["Contents"][-1]["Key"]
        log.info("Latest folder: {}", latest_folder)

        # return all json files withing that folder and append the file name as welll to body
        files = [item["Key"] for item in response["Contents"] if item["Key"].endswith(".json")]
        log.info("Found {} JSON file(s) in {}", len(files), latest_folder)

        count=0

        for file in files:
            count+=1
            response = s3_client.get_object(Bucket=self.bucket, Key=file)

            json_data = json.load(response["Body"])

            # Add source file name
            json_data["source_file"] = re.search(r'([^/]+\.json)$', file).group(1)

            data.append(json_data)
            log.info("Loaded {}", file)
            if count==3:
                break

        return data
        
        
        
       

