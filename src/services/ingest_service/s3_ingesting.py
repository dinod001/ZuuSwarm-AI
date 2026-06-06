import json
import sys
from pathlib import Path

# Allow running this file directly: python src/services/ingest_service/s3_ingesting.py
_SRC_ROOT = Path(__file__).resolve().parents[2]
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))

from dotenv import load_dotenv

load_dotenv(_SRC_ROOT.parent / ".env")

from infrastructure.db.s3_client import S3Client
from infrastructure.log import get_logger
log = get_logger(__name__)


def load_transcript(file_path: Path) -> dict:
    with file_path.open(encoding="utf-8") as handle:
        return json.load(handle)


def validate_transcript(data: dict, file_path: Path) -> str | None:
    transcript_id = data.get("transcript_id")
    if not transcript_id:
        log.error("Missing transcript_id in {}", file_path.name)
        return None

    if not isinstance(data.get("messages"), list):
        log.error("Missing or invalid messages in {}", file_path.name)
        return None

    return transcript_id


def ingest_transcripts_to_s3() -> bool:
    """Validate AWS + files, load JSON, then upload each transcript to S3."""
    client = S3Client()
    files = client.validate_upload_ready()

    if not files:
        log.warning("No files to ingest")
        return False

    log.info("Starting ingest for {} transcript file(s)", len(files))

    for file_path in files:
        data = load_transcript(file_path)
        transcript_id = validate_transcript(data, file_path)
        if not transcript_id:
            return False

        log.info("Validated {} ({})", file_path.name, transcript_id)

        if not client.upload_transcript(data):
            return False

    log.info("Ingest complete: {} transcript(s) uploaded", len(files))
    return True

if __name__ == "__main__":
    success = ingest_transcripts_to_s3()
    raise SystemExit(0 if success else 1)