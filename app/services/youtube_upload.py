import glob
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from loguru import logger

from app.utils import utils


YOUTUBE_UPLOAD_SCOPE = "https://www.googleapis.com/auth/youtube.upload"
YOUTUBE_API_SERVICE_NAME = "youtube"
YOUTUBE_API_VERSION = "v3"


def find_default_client_secret_file() -> str:
    candidates = glob.glob(
        os.path.expanduser("~/Downloads/client_secret_*.apps.googleusercontent.com.json")
    )
    if not candidates:
        return ""

    candidates.sort(key=lambda path: os.path.getmtime(path), reverse=True)
    return candidates[0]


def default_token_file() -> str:
    youtube_dir = utils.storage_dir("youtube", create=True)
    return os.path.join(youtube_dir, "oauth_token.json")


def _load_google_modules():
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload
    except ImportError as exc:
        raise RuntimeError(
            "YouTube upload dependencies are missing. Install "
            "google-api-python-client, google-auth-httplib2, and google-auth-oauthlib."
        ) from exc

    return Request, Credentials, InstalledAppFlow, build, MediaFileUpload


def _ensure_client_secret_file(client_secret_file: str) -> str:
    client_secret_file = os.path.abspath(os.path.expanduser(client_secret_file or ""))
    if not client_secret_file or not os.path.isfile(client_secret_file):
        raise FileNotFoundError("YouTube OAuth client JSON file was not found.")

    with open(client_secret_file, "r", encoding="utf-8") as fp:
        data = json.load(fp)
    if "installed" not in data and "web" not in data:
        raise ValueError("The selected JSON file is not a Google OAuth client file.")

    return client_secret_file


def get_authenticated_service(
    client_secret_file: str,
    token_file: Optional[str] = None,
    force_reauth: bool = False,
):
    Request, Credentials, InstalledAppFlow, build, _ = _load_google_modules()
    client_secret_file = _ensure_client_secret_file(client_secret_file)
    token_file = token_file or default_token_file()
    os.makedirs(os.path.dirname(token_file), exist_ok=True)

    credentials = None
    if os.path.exists(token_file) and not force_reauth:
        credentials = Credentials.from_authorized_user_file(
            token_file, [YOUTUBE_UPLOAD_SCOPE]
        )

    if credentials and credentials.expired and credentials.refresh_token:
        credentials.refresh(Request())

    if not credentials or not credentials.valid:
        flow = InstalledAppFlow.from_client_secrets_file(
            client_secret_file, [YOUTUBE_UPLOAD_SCOPE]
        )
        credentials = flow.run_local_server(port=0, prompt="consent")

    with open(token_file, "w", encoding="utf-8") as fp:
        fp.write(credentials.to_json())

    return build(YOUTUBE_API_SERVICE_NAME, YOUTUBE_API_VERSION, credentials=credentials)


def revoke_saved_token(token_file: Optional[str] = None):
    token_file = token_file or default_token_file()
    if os.path.exists(token_file):
        os.remove(token_file)


def token_exists(token_file: Optional[str] = None) -> bool:
    return os.path.exists(token_file or default_token_file())


def parse_tags(raw_tags: str) -> list[str]:
    tags = []
    for item in (raw_tags or "").split(","):
        tag = item.strip()
        if tag:
            tags.append(tag)
    return tags


def normalize_publish_at(value: Optional[datetime]) -> Optional[str]:
    if not value:
        return None

    if value.tzinfo is None:
        value = value.astimezone()

    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def upload_video(
    video_path: str,
    title: str,
    description: str = "",
    tags: Optional[list[str]] = None,
    privacy_status: str = "private",
    publish_at: Optional[datetime] = None,
    client_secret_file: str = "",
    token_file: Optional[str] = None,
    category_id: str = "22",
    made_for_kids: bool = False,
):
    _, _, _, _, MediaFileUpload = _load_google_modules()
    youtube = get_authenticated_service(client_secret_file, token_file)

    video_path = os.path.abspath(os.path.expanduser(video_path or ""))
    if not os.path.isfile(video_path):
        raise FileNotFoundError("Video file was not found.")

    title = (title or "").strip() or Path(video_path).stem
    description = description or ""
    status = {
        "privacyStatus": privacy_status,
        "selfDeclaredMadeForKids": made_for_kids,
    }

    normalized_publish_at = normalize_publish_at(publish_at)
    if normalized_publish_at:
        status["privacyStatus"] = "private"
        status["publishAt"] = normalized_publish_at

    body = {
        "snippet": {
            "title": title[:100],
            "description": description[:5000],
            "tags": tags or [],
            "categoryId": category_id,
        },
        "status": status,
    }

    logger.info(
        "uploading video to YouTube: "
        f"path={video_path}, privacy={status['privacyStatus']}, scheduled={bool(normalized_publish_at)}"
    )
    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=MediaFileUpload(video_path, chunksize=-1, resumable=True),
    )
    response = request.execute()
    video_id = response.get("id", "")
    return {
        "id": video_id,
        "url": f"https://www.youtube.com/watch?v={video_id}" if video_id else "",
        "privacy_status": status["privacyStatus"],
        "publish_at": normalized_publish_at or "",
        "raw": response,
    }
