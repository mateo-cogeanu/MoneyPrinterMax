import glob
import json
import os
import secrets
import webbrowser
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Optional
from urllib.parse import urlencode, urlparse, parse_qs

import requests
from loguru import logger

from app.utils import utils


YOUTUBE_UPLOAD_SCOPE = "https://www.googleapis.com/auth/youtube.upload"
YOUTUBE_API_SERVICE_NAME = "youtube"
YOUTUBE_API_VERSION = "v3"


def _friendly_oauth_error(error: str, description: str = "") -> str:
    if error == "access_denied":
        return (
            "Google denied access before YouTube was called. This usually means "
            "the OAuth consent screen is still in Testing and your Google account "
            "is not listed as a test user, or the app is blocked/unverified for "
            "the YouTube upload scope. Add your Google account as a test user in "
            "Google Cloud Console > OAuth consent screen, then try Connect YouTube "
            "again."
        )

    return description or error


def _oauth_loopback_host(client_info: dict) -> str:
    for redirect_uri in client_info.get("redirect_uris") or []:
        host = urlparse(redirect_uri).hostname
        if host in {"localhost", "127.0.0.1"}:
            return host

    return "localhost"


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
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload
    except ImportError as exc:
        raise RuntimeError(
            "YouTube upload dependencies are missing. Install "
            "google-api-python-client and google-auth-httplib2."
        ) from exc

    return Request, Credentials, build, MediaFileUpload


def _ensure_client_secret_file(client_secret_file: str) -> str:
    client_secret_file = os.path.abspath(os.path.expanduser(client_secret_file or ""))
    if not client_secret_file or not os.path.isfile(client_secret_file):
        raise FileNotFoundError("YouTube OAuth client JSON file was not found.")

    with open(client_secret_file, "r", encoding="utf-8") as fp:
        data = json.load(fp)
    if "installed" not in data and "web" not in data:
        raise ValueError("The selected JSON file is not a Google OAuth client file.")

    return client_secret_file


def _exchange_code_for_credentials(client_secret_file: str, credentials_cls):
    with open(client_secret_file, "r", encoding="utf-8") as fp:
        client_config = json.load(fp)

    client_info = client_config.get("installed") or client_config.get("web") or {}
    client_id = client_info.get("client_id", "")
    client_secret = client_info.get("client_secret", "")
    auth_uri = client_info.get("auth_uri", "")
    token_uri = client_info.get("token_uri", "")
    if not client_id or not auth_uri or not token_uri:
        raise ValueError("The YouTube OAuth client JSON is missing required fields.")

    auth_result = {}

    class OAuthCallbackHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            parsed_url = urlparse(self.path)
            params = parse_qs(parsed_url.query)
            auth_result["code"] = params.get("code", [""])[0]
            auth_result["state"] = params.get("state", [""])[0]
            auth_result["error"] = params.get("error", [""])[0]
            auth_result["error_description"] = params.get("error_description", [""])[0]

            self.send_response(200)
            self.send_header("Content-type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(
                b"<html><body><h2>YouTube connected.</h2>"
                b"<p>You can close this tab and return to MoneyPrinterMax.</p>"
                b"</body></html>"
            )

        def log_message(self, format, *args):
            return

    redirect_host = _oauth_loopback_host(client_info)
    bind_host = "127.0.0.1" if redirect_host == "localhost" else redirect_host
    server = HTTPServer((bind_host, 0), OAuthCallbackHandler)
    server.timeout = 300
    redirect_uri = f"http://{redirect_host}:{server.server_port}/"
    state = secrets.token_urlsafe(24)
    auth_url = f"{auth_uri}?{urlencode({
        'client_id': client_id,
        'redirect_uri': redirect_uri,
        'response_type': 'code',
        'scope': YOUTUBE_UPLOAD_SCOPE,
        'access_type': 'offline',
        'prompt': 'consent',
        'state': state,
    })}"

    webbrowser.open(auth_url)
    server.handle_request()
    server.server_close()

    if auth_result.get("error"):
        details = _friendly_oauth_error(
            auth_result["error"], auth_result.get("error_description", "")
        )
        raise RuntimeError(f"YouTube authorization failed: {details}")
    if not auth_result.get("code"):
        raise TimeoutError("Timed out waiting for YouTube authorization.")
    if auth_result.get("state") != state:
        raise RuntimeError("YouTube authorization state did not match.")

    token_response = requests.post(
        token_uri,
        data={
            "code": auth_result["code"],
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        },
        timeout=30,
    )
    token_response.raise_for_status()
    token_data = token_response.json()

    return credentials_cls(
        token=token_data.get("access_token"),
        refresh_token=token_data.get("refresh_token"),
        token_uri=token_uri,
        client_id=client_id,
        client_secret=client_secret,
        scopes=[YOUTUBE_UPLOAD_SCOPE],
    )


def get_authenticated_service(
    client_secret_file: str,
    token_file: Optional[str] = None,
    force_reauth: bool = False,
):
    Request, Credentials, build, _ = _load_google_modules()
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
        credentials = _exchange_code_for_credentials(
            client_secret_file, Credentials
        )

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
    _, _, _, MediaFileUpload = _load_google_modules()
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
