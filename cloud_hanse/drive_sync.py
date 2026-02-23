from __future__ import annotations

import hashlib
import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

import requests

try:
    from google.auth.transport.requests import Request as GoogleRequest
    from google.oauth2 import service_account
except ImportError:  # pragma: no cover - optional dependency in runtime
    GoogleRequest = None
    service_account = None


DEFAULT_FOLDER_URL = "https://drive.google.com/drive/folders/16O5AiugmonSzX1pfZ5a5bjZZ4Y_MoRCO"
DRIVE_V3_API = "https://www.googleapis.com/drive/v3"
DRIVE_V3_UPLOAD = "https://www.googleapis.com/upload/drive/v3"


class DriveSyncError(RuntimeError):
    """Allgemeiner Fehler beim Lesen/Schreiben des globalen Zustands."""


class DriveConflictError(DriveSyncError):
    """Optimistic-Locking Konflikt beim Schreiben."""


class DriveWriteUnavailable(DriveSyncError):
    """Service-Account nicht verfuegbar, daher nur Read-Only Sync."""


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def extract_folder_id(folder_url: str) -> str:
    match = re.search(r"/folders/([a-zA-Z0-9_-]+)", folder_url)
    if not match:
        raise DriveSyncError(f"Konnte keine Folder-ID aus URL lesen: {folder_url}")
    return match.group(1)


def calculate_state_hash(state: Dict[str, Any]) -> str:
    # Hash ohne gespeichertes state_hash erzeugen, damit sich die Signatur selbst nicht rekursiv veraendert.
    cloned = json.loads(json.dumps(state))
    integrity = cloned.get("integrity", {})
    if isinstance(integrity, dict):
        integrity["state_hash"] = ""
    payload = json.dumps(cloned, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


class GoogleDriveWorldStateStore:
    def __init__(
        self,
        *,
        folder_url: str = DEFAULT_FOLDER_URL,
        file_name: str = "world_state.json",
        local_cache_path: Path | str = Path("cloud_hanse/world_state.local.json"),
        api_key: str | None = None,
        service_account_file: str | None = None,
        service_account_json: str | None = None,
        file_id: str | None = None,
        timeout_seconds: float = 20.0,
    ) -> None:
        self.folder_url = folder_url
        self.folder_id = extract_folder_id(folder_url)
        self.file_name = file_name
        self.local_cache_path = Path(local_cache_path)
        self.api_key = (api_key or os.getenv("GOOGLE_DRIVE_API_KEY", "")).strip() or None
        self.service_account_file = (
            service_account_file
            or os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "").strip()
            or None
        )
        self.service_account_json = (
            service_account_json
            or os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
            or None
        )
        self.file_id = (file_id or os.getenv("GOOGLE_DRIVE_WORLD_FILE_ID", "")).strip() or None
        self.timeout_seconds = float(timeout_seconds)
        self.session = requests.Session()
        self._resolved_file_id: str | None = self.file_id

    # ---------- Public API ----------
    def read_world_state(self) -> Dict[str, Any]:
        errors: list[str] = []
        try:
            state = self._read_from_drive_public()
            self._stamp_sync_meta(state, sync_source="drive_public", pulled=True)
            self._cache_world_state(state)
            return state
        except Exception as exc:  # noqa: BLE001 - fallback chain
            errors.append(f"Public read fehlgeschlagen: {exc}")

        try:
            token = self._service_account_token()
            state = self._read_from_drive_authorized(token)
            self._stamp_sync_meta(state, sync_source="drive_service_account", pulled=True)
            self._cache_world_state(state)
            return state
        except Exception as exc:  # noqa: BLE001 - fallback chain
            errors.append(f"Authorized read fehlgeschlagen: {exc}")

        try:
            state = self._read_from_local_cache()
            self._stamp_sync_meta(state, sync_source="local_cache", pulled=False)
            return state
        except Exception as exc:  # noqa: BLE001 - fallback chain
            errors.append(f"Local cache fehlgeschlagen: {exc}")

        raise DriveSyncError(" | ".join(errors))

    def write_world_state(self, world_state: Dict[str, Any], *, expected_version: int | None = None) -> Dict[str, Any]:
        token = self._service_account_token()
        current_version = 0
        try:
            latest = self._read_from_drive_authorized(token)
            current_version = int(latest.get("meta", {}).get("version", 0))
        except DriveSyncError as exc:
            # Wenn die Datei noch nicht existiert, wird sie neu angelegt.
            if "nicht gefunden" not in str(exc).lower():
                raise

        if expected_version is not None and current_version != int(expected_version):
            raise DriveConflictError(
                f"Versionskonflikt: erwartet={expected_version}, remote={current_version}"
            )

        candidate = json.loads(json.dumps(world_state))
        self._prepare_state_for_write(candidate, base_version=current_version)

        file_id = self._ensure_file_id_authorized(token)
        if file_id:
            self._update_file_media(token, file_id, candidate)
        else:
            created_file_id = self._create_file_multipart(token, candidate)
            self._resolved_file_id = created_file_id

        self._cache_world_state(candidate)
        return candidate

    def write_world_state_local_fallback(self, world_state: Dict[str, Any]) -> Dict[str, Any]:
        candidate = json.loads(json.dumps(world_state))
        current_version = int(candidate.get("meta", {}).get("version", 1))
        self._prepare_state_for_write(candidate, base_version=max(0, current_version - 1))
        self._stamp_sync_meta(candidate, sync_source="local_cache", pushed=False)
        self._cache_world_state(candidate)
        return candidate

    # ---------- Public / API key ----------
    def _read_from_drive_public(self) -> Dict[str, Any]:
        if self.api_key:
            file_id = self._resolved_file_id or self._discover_file_id_public()
            payload = self._download_file_v3(file_id, api_key=self.api_key)
            self._resolved_file_id = file_id
            return payload

        # Falls kein API-Key existiert, probiere den direkten Export-Link (wenn file_id bekannt).
        if self._resolved_file_id:
            return self._download_file_direct(self._resolved_file_id)

        scraped_id = self._discover_file_id_scrape()
        if scraped_id:
            self._resolved_file_id = scraped_id
            return self._download_file_direct(scraped_id)

        raise DriveSyncError(
            "Kein API-Key und keine world_state file_id verfuegbar. "
            "Setze GOOGLE_DRIVE_API_KEY oder GOOGLE_DRIVE_WORLD_FILE_ID."
        )

    def _discover_file_id_public(self) -> str:
        if not self.api_key:
            raise DriveSyncError("API-Key fehlt fuer file discovery.")
        params = {
            "key": self.api_key,
            "q": f"'{self.folder_id}' in parents and trashed=false and name='{self.file_name}'",
            "fields": "files(id,name,modifiedTime)",
            "orderBy": "modifiedTime desc",
            "pageSize": 5,
            "supportsAllDrives": "true",
            "includeItemsFromAllDrives": "true",
        }
        response = self.session.get(f"{DRIVE_V3_API}/files", params=params, timeout=self.timeout_seconds)
        if response.status_code != 200:
            raise DriveSyncError(f"Drive file listing fehlgeschlagen (status={response.status_code}).")
        files = response.json().get("files", [])
        if not files:
            raise DriveSyncError(f"Datei '{self.file_name}' im Zielordner nicht gefunden.")
        return str(files[0]["id"])

    def _discover_file_id_scrape(self) -> str | None:
        # Best effort Fallback. Die Drive-HTML-Struktur kann sich aendern.
        response = self.session.get(self.folder_url, timeout=self.timeout_seconds)
        if response.status_code != 200:
            return None
        html = response.text
        pattern = r'"([a-zA-Z0-9_-]{20,})","' + re.escape(self.file_name) + r'"'
        match = re.search(pattern, html)
        return match.group(1) if match else None

    def _download_file_v3(self, file_id: str, *, api_key: str | None = None, token: str | None = None) -> Dict[str, Any]:
        url = f"{DRIVE_V3_API}/files/{file_id}"
        headers: Dict[str, str] = {}
        params: Dict[str, str] = {"alt": "media", "supportsAllDrives": "true"}
        if api_key:
            params["key"] = api_key
        if token:
            headers["Authorization"] = f"Bearer {token}"
        response = self.session.get(url, params=params, headers=headers, timeout=self.timeout_seconds)
        if response.status_code != 200:
            raise DriveSyncError(f"Download von Drive fehlgeschlagen (status={response.status_code}).")
        try:
            data = response.json()
        except json.JSONDecodeError as exc:
            raise DriveSyncError(f"world_state.json ist kein valides JSON: {exc}") from exc
        if not isinstance(data, dict):
            raise DriveSyncError("world_state.json muss ein JSON-Objekt sein.")
        return data

    def _download_file_direct(self, file_id: str) -> Dict[str, Any]:
        url = "https://drive.google.com/uc"
        params = {"export": "download", "id": file_id}
        response = self.session.get(url, params=params, timeout=self.timeout_seconds)
        if response.status_code != 200:
            raise DriveSyncError(f"Direkter Drive-Download fehlgeschlagen (status={response.status_code}).")
        text = response.text.strip()
        if text.startswith("<!DOCTYPE html"):
            raise DriveSyncError("Direkter Download lieferte HTML statt JSON. API-Key oder file_id pruefen.")
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise DriveSyncError(f"Direkter Drive-Download ist kein JSON: {exc}") from exc
        if not isinstance(data, dict):
            raise DriveSyncError("Direkt geladene world_state.json muss ein JSON-Objekt sein.")
        return data

    # ---------- Service account ----------
    def _service_account_token(self) -> str:
        if service_account is None or GoogleRequest is None:
            raise DriveWriteUnavailable(
                "google-auth ist nicht installiert. Benoetigt: pip install google-auth"
            )
        info: Dict[str, Any] | None = None
        if self.service_account_json:
            try:
                info = json.loads(self.service_account_json)
            except json.JSONDecodeError as exc:
                raise DriveWriteUnavailable(f"GOOGLE_SERVICE_ACCOUNT_JSON ist ungueltig: {exc}") from exc
        elif self.service_account_file:
            try:
                info = json.loads(Path(self.service_account_file).read_text(encoding="utf-8"))
            except OSError as exc:
                raise DriveWriteUnavailable(f"Service-Account Datei nicht lesbar: {exc}") from exc
            except json.JSONDecodeError as exc:
                raise DriveWriteUnavailable(f"Service-Account Datei ist kein JSON: {exc}") from exc
        else:
            raise DriveWriteUnavailable(
                "Schreibzugriff nicht konfiguriert. Setze GOOGLE_SERVICE_ACCOUNT_FILE oder GOOGLE_SERVICE_ACCOUNT_JSON."
            )

        scopes = ["https://www.googleapis.com/auth/drive"]
        creds = service_account.Credentials.from_service_account_info(info, scopes=scopes)
        creds.refresh(GoogleRequest())
        if not creds.token:
            raise DriveWriteUnavailable("Konnte keinen Access-Token vom Service-Account erhalten.")
        return creds.token

    def _read_from_drive_authorized(self, token: str) -> Dict[str, Any]:
        file_id = self._ensure_file_id_authorized(token)
        if not file_id:
            raise DriveSyncError(
                f"Datei '{self.file_name}' wurde im Ordner {self.folder_id} nicht gefunden."
            )
        payload = self._download_file_v3(file_id, token=token)
        self._resolved_file_id = file_id
        return payload

    def _ensure_file_id_authorized(self, token: str) -> str | None:
        if self._resolved_file_id:
            return self._resolved_file_id

        headers = {"Authorization": f"Bearer {token}"}
        params = {
            "q": f"'{self.folder_id}' in parents and trashed=false and name='{self.file_name}'",
            "fields": "files(id,name,modifiedTime)",
            "orderBy": "modifiedTime desc",
            "pageSize": 5,
            "supportsAllDrives": "true",
            "includeItemsFromAllDrives": "true",
        }
        response = self.session.get(
            f"{DRIVE_V3_API}/files",
            params=params,
            headers=headers,
            timeout=self.timeout_seconds,
        )
        if response.status_code != 200:
            raise DriveSyncError(f"Authorized file listing fehlgeschlagen (status={response.status_code}).")
        files = response.json().get("files", [])
        if not files:
            return None
        file_id = str(files[0]["id"])
        self._resolved_file_id = file_id
        return file_id

    def _update_file_media(self, token: str, file_id: str, world_state: Dict[str, Any]) -> None:
        url = f"{DRIVE_V3_UPLOAD}/files/{file_id}"
        params = {"uploadType": "media", "supportsAllDrives": "true"}
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8",
        }
        payload = json.dumps(world_state, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        response = self.session.patch(
            url, params=params, headers=headers, data=payload, timeout=self.timeout_seconds
        )
        if response.status_code not in {200, 201}:
            raise DriveSyncError(f"Drive update fehlgeschlagen (status={response.status_code}): {response.text}")

    def _create_file_multipart(self, token: str, world_state: Dict[str, Any]) -> str:
        url = f"{DRIVE_V3_UPLOAD}/files"
        params = {"uploadType": "multipart", "supportsAllDrives": "true"}
        boundary = f"cloudhanse_{int(time.time() * 1000)}"
        metadata = {
            "name": self.file_name,
            "parents": [self.folder_id],
            "mimeType": "application/json",
        }
        metadata_json = json.dumps(metadata, ensure_ascii=False)
        media_json = json.dumps(world_state, ensure_ascii=False, separators=(",", ":"))
        body = (
            f"--{boundary}\r\n"
            "Content-Type: application/json; charset=UTF-8\r\n\r\n"
            f"{metadata_json}\r\n"
            f"--{boundary}\r\n"
            "Content-Type: application/json; charset=UTF-8\r\n\r\n"
            f"{media_json}\r\n"
            f"--{boundary}--\r\n"
        ).encode("utf-8")
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": f"multipart/related; boundary={boundary}",
        }
        response = self.session.post(
            url, params=params, headers=headers, data=body, timeout=self.timeout_seconds
        )
        if response.status_code not in {200, 201}:
            raise DriveSyncError(f"Drive create fehlgeschlagen (status={response.status_code}): {response.text}")
        file_id = response.json().get("id")
        if not file_id:
            raise DriveSyncError("Drive create erfolgreich, aber ohne file_id im Response.")
        return str(file_id)

    # ---------- Local cache + metadata ----------
    def _cache_world_state(self, state: Dict[str, Any]) -> None:
        self.local_cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.local_cache_path.write_text(
            json.dumps(state, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _read_from_local_cache(self) -> Dict[str, Any]:
        raw = self.local_cache_path.read_text(encoding="utf-8")
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise DriveSyncError("Lokaler Cache enthaelt kein JSON-Objekt.")
        return payload

    def _prepare_state_for_write(self, state: Dict[str, Any], *, base_version: int) -> None:
        state.setdefault("meta", {})
        meta = state["meta"]
        if not isinstance(meta, dict):
            raise DriveSyncError("Ungueltiger world_state: meta fehlt.")
        meta["version"] = int(base_version) + 1
        meta["updated_at"] = utc_now()
        meta.setdefault("created_at", meta["updated_at"])

        self._stamp_sync_meta(state, sync_source="drive_service_account", pushed=True)

        state.setdefault("integrity", {})
        integrity = state["integrity"]
        if not isinstance(integrity, dict):
            raise DriveSyncError("Ungueltiger world_state: integrity fehlt.")
        integrity.setdefault("anomaly_history", [])
        integrity.setdefault("immunity_events", [])
        integrity.setdefault("manipulation_flags", {})
        integrity.setdefault("last_guard_scan_at", utc_now())
        integrity["state_hash"] = calculate_state_hash(state)

    def _stamp_sync_meta(self, state: Dict[str, Any], *, sync_source: str, pulled: bool = False, pushed: bool = False) -> None:
        state.setdefault("meta", {})
        meta = state["meta"]
        if not isinstance(meta, dict):
            return
        meta.setdefault("drive", {})
        drive = meta["drive"] if isinstance(meta.get("drive"), dict) else {}
        meta["drive"] = drive
        drive["folder_url"] = self.folder_url
        drive["folder_id"] = self.folder_id
        drive["file_name"] = self.file_name
        drive["file_id"] = self._resolved_file_id
        drive["sync_source"] = sync_source
        drive.setdefault("last_pull_at", None)
        drive.setdefault("last_push_at", None)
        now = utc_now()
        if pulled:
            drive["last_pull_at"] = now
        if pushed:
            drive["last_push_at"] = now
