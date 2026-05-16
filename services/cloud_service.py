import asyncio
import logging
from pathlib import Path
from typing import Optional
from config.settings import settings

logger = logging.getLogger(__name__)


class CloudService:

    @staticmethod
    async def upload_to_gdrive(file_path: Path, folder_id: Optional[str] = None) -> str:
        """Upload file to Google Drive. Returns shareable link."""
        if not settings.GDRIVE_CREDENTIALS_JSON:
            raise RuntimeError("Google Drive not configured (GDRIVE_CREDENTIALS_JSON missing)")

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, lambda: _gdrive_upload(file_path, folder_id)
        )

    @staticmethod
    async def upload_to_dropbox(file_path: Path, dropbox_token: str) -> str:
        """Upload to Dropbox. Returns shared link."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, lambda: _dropbox_upload(file_path, dropbox_token)
        )

    @staticmethod
    async def upload_to_mega(file_path: Path, email: str, password: str) -> str:
        """Upload to MEGA. Returns file link."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, lambda: _mega_upload(file_path, email, password)
        )


def _gdrive_upload(file_path: Path, folder_id: Optional[str]) -> str:
    import json
    from google.oauth2.service_account import Credentials
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload

    creds_data = json.loads(settings.GDRIVE_CREDENTIALS_JSON)
    creds = Credentials.from_service_account_info(
        creds_data,
        scopes=["https://www.googleapis.com/auth/drive.file"]
    )
    service = build("drive", "v3", credentials=creds)

    file_metadata = {"name": file_path.name}
    if folder_id:
        file_metadata["parents"] = [folder_id]

    media = MediaFileUpload(str(file_path), resumable=True)
    uploaded = service.files().create(
        body=file_metadata, media_body=media, fields="id"
    ).execute()

    file_id = uploaded.get("id")
    service.permissions().create(
        fileId=file_id,
        body={"type": "anyone", "role": "reader"}
    ).execute()

    return f"https://drive.google.com/file/d/{file_id}/view"


def _dropbox_upload(file_path: Path, token: str) -> str:
    import dropbox

    dbx = dropbox.Dropbox(token)
    dropbox_path = f"/{file_path.name}"

    with open(file_path, "rb") as f:
        dbx.files_upload(f.read(), dropbox_path, mode=dropbox.files.WriteMode.overwrite)

    shared = dbx.sharing_create_shared_link_with_settings(dropbox_path)
    return shared.url.replace("?dl=0", "?dl=1")


def _mega_upload(file_path: Path, email: str, password: str) -> str:
    from mega import Mega

    mega = Mega()
    m = mega.login(email, password)
    uploaded = m.upload(str(file_path))
    return m.get_upload_link(uploaded)
