"""Configurable Confluence integration boundary."""

from __future__ import annotations

import base64
import json
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol


class ConfluenceAdapterError(RuntimeError):
    """Raised when Confluence adapter operations fail."""


class ConfluenceTransport(Protocol):
    """HTTP transport used by the Confluence Cloud adapter."""

    def request(
        self,
        method: str,
        path: str,
        payload: Mapping[str, object] | None = None,
    ) -> object:
        """Send one Confluence request and return a decoded JSON object."""


@dataclass(frozen=True)
class ConfluenceAdapterConfig:
    """Configuration for one target Confluence space and parent page."""

    base_url: str
    space_key: str
    parent_page_id: str
    email: str = ""
    api_token: str = ""

    @property
    def normalized_base_url(self) -> str:
        return self.base_url.rstrip("/")


@dataclass(frozen=True)
class ConfluenceSpaceMetadata:
    key: str
    name: str
    id: str = ""
    homepage_id: str = ""


@dataclass(frozen=True)
class ConfluencePage:
    id: str
    title: str
    space_key: str
    version: int
    body_storage: str = ""
    parent_page_id: str = ""
    web_url: str = ""


@dataclass(frozen=True)
class ConfluencePageFields:
    title: str
    body_storage: str
    parent_page_id: str = ""


@dataclass(frozen=True)
class ConfluenceMirrorRecord:
    page_id: str
    title: str
    path: Path


@dataclass(frozen=True)
class ConfluenceMirrorReadiness:
    space_key: str
    path: Path
    passed: bool
    message: str


@dataclass(frozen=True)
class ConfluenceSpaceConfiguration:
    space: ConfluenceSpaceMetadata
    parent_page: ConfluencePage


class ConfluenceDocumentationAdapter(Protocol):
    """Configurable Confluence documentation adapter contract."""

    config: ConfluenceAdapterConfig

    def validate_access(self) -> ConfluenceSpaceConfiguration:
        """Read configured space and parent page metadata."""

    def get_space(self) -> ConfluenceSpaceMetadata:
        """Read configured Confluence space metadata."""

    def get_page(self, page_id: str) -> ConfluencePage:
        """Read one Confluence page with storage content."""

    def create_or_update_child_page(self, fields: ConfluencePageFields) -> ConfluencePage:
        """Create or update a child page under the configured parent."""

    def mirror_page(self, page: ConfluencePage, mirror_root: Path) -> ConfluenceMirrorRecord:
        """Mirror page content into durable local storage."""


class ConfluenceCloudTransport:
    """Small urllib-based Confluence Cloud transport."""

    def __init__(self, config: ConfluenceAdapterConfig, *, timeout_seconds: int = 45) -> None:
        self.config = config
        self.timeout_seconds = timeout_seconds

    def request(
        self,
        method: str,
        path: str,
        payload: Mapping[str, object] | None = None,
    ) -> object:
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            self.config.normalized_base_url + path,
            data=data,
            headers=self._headers(),
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                raw = response.read().decode("utf-8")
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            message = _confluence_error_message(raw)
            raise ConfluenceAdapterError(
                f"Confluence request failed: HTTP {exc.code} {message}"
            ) from exc
        except urllib.error.URLError as exc:
            raise ConfluenceAdapterError(f"Confluence request failed: {exc.reason}") from exc

    def _headers(self) -> dict[str, str]:
        token = base64.b64encode(f"{self.config.email}:{self.config.api_token}".encode()).decode()
        return {
            "Authorization": f"Basic {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }


class ConfluenceCloudDocumentationAdapter:
    """Confluence Cloud implementation for one configured space and parent page."""

    def __init__(
        self,
        config: ConfluenceAdapterConfig,
        *,
        transport: ConfluenceTransport | None = None,
    ) -> None:
        self.config = config
        self._transport = transport or ConfluenceCloudTransport(config)

    def validate_access(self) -> ConfluenceSpaceConfiguration:
        space = self.get_space()
        parent_page = self.get_page(self.config.parent_page_id)
        return ConfluenceSpaceConfiguration(space=space, parent_page=parent_page)

    def get_space(self) -> ConfluenceSpaceMetadata:
        response = _dict(
            self._transport.request(
                "GET",
                f"/rest/api/space/{urllib.parse.quote(self.config.space_key)}?expand=homepage",
            )
        )
        return _space_from_json(response)

    def get_page(self, page_id: str) -> ConfluencePage:
        response = _dict(
            self._transport.request(
                "GET",
                f"/rest/api/content/{urllib.parse.quote(page_id)}?expand=space,body.storage,version,ancestors",
            )
        )
        return _page_from_json(response, fallback_space_key=self.config.space_key)

    def create_or_update_child_page(self, fields: ConfluencePageFields) -> ConfluencePage:
        parent_page_id = fields.parent_page_id or self.config.parent_page_id
        existing = self._find_child_page(fields.title, parent_page_id)
        if existing is None:
            return self._create_child_page(fields, parent_page_id)
        return self._update_page(existing, fields, parent_page_id)

    def mirror_page(self, page: ConfluencePage, mirror_root: Path) -> ConfluenceMirrorRecord:
        return _mirror_page_to_storage(page, mirror_root)

    def _find_child_page(self, title: str, parent_page_id: str) -> ConfluencePage | None:
        query = urllib.parse.urlencode(
            {
                "spaceKey": self.config.space_key,
                "title": title,
                "expand": "space,body.storage,version,ancestors",
            }
        )
        response = _dict(self._transport.request("GET", "/rest/api/content?" + query))
        for item in _list(response.get("results")):
            page = _page_from_json(item, fallback_space_key=self.config.space_key)
            if page.parent_page_id == parent_page_id:
                return page
        return None

    def _create_child_page(self, fields: ConfluencePageFields, parent_page_id: str) -> ConfluencePage:
        payload = _page_payload(
            self.config.space_key,
            fields.title,
            fields.body_storage,
            parent_page_id,
        )
        response = _dict(self._transport.request("POST", "/rest/api/content", payload))
        return _page_from_json(response, fallback_space_key=self.config.space_key)

    def _update_page(
        self,
        page: ConfluencePage,
        fields: ConfluencePageFields,
        parent_page_id: str,
    ) -> ConfluencePage:
        payload = _page_payload(
            self.config.space_key,
            fields.title,
            fields.body_storage,
            parent_page_id,
            page_id=page.id,
            version=page.version + 1,
        )
        response = _dict(
            self._transport.request(
                "PUT",
                f"/rest/api/content/{urllib.parse.quote(page.id)}",
                payload,
            )
        )
        return _page_from_json(response, fallback_space_key=self.config.space_key)


class MockConfluenceDocumentationAdapter:
    """In-memory Confluence adapter for local documentation workflow tests."""

    def __init__(
        self,
        config: ConfluenceAdapterConfig,
        *,
        space_name: str = "Documentation",
        homepage_title: str = "Home",
    ) -> None:
        self.config = config
        self._space_name = space_name
        self._pages: dict[str, ConfluencePage] = {
            config.parent_page_id: ConfluencePage(
                id=config.parent_page_id,
                title=homepage_title,
                space_key=config.space_key,
                version=1,
                body_storage="<p>Home</p>",
            )
        }
        self._next_page_id = 1

    def validate_access(self) -> ConfluenceSpaceConfiguration:
        return ConfluenceSpaceConfiguration(
            space=self.get_space(),
            parent_page=self.get_page(self.config.parent_page_id),
        )

    def get_space(self) -> ConfluenceSpaceMetadata:
        return ConfluenceSpaceMetadata(
            key=self.config.space_key,
            name=self._space_name,
            id=f"mock-{self.config.space_key}",
            homepage_id=self.config.parent_page_id,
        )

    def get_page(self, page_id: str) -> ConfluencePage:
        page = self._pages.get(page_id)
        if page is None:
            raise ConfluenceAdapterError(f"Mock Confluence page does not exist: {page_id}")
        return page

    def create_or_update_child_page(self, fields: ConfluencePageFields) -> ConfluencePage:
        parent_page_id = fields.parent_page_id or self.config.parent_page_id
        for page in self._pages.values():
            if page.title == fields.title and page.parent_page_id == parent_page_id:
                updated = ConfluencePage(
                    id=page.id,
                    title=fields.title,
                    space_key=self.config.space_key,
                    version=page.version + 1,
                    body_storage=fields.body_storage,
                    parent_page_id=parent_page_id,
                    web_url=page.web_url,
                )
                self._pages[page.id] = updated
                return updated
        page_id = f"mock-{self._next_page_id}"
        self._next_page_id += 1
        page = ConfluencePage(
            id=page_id,
            title=fields.title,
            space_key=self.config.space_key,
            version=1,
            body_storage=fields.body_storage,
            parent_page_id=parent_page_id,
            web_url=f"/spaces/{self.config.space_key}/pages/{page_id}/{fields.title}",
        )
        self._pages[page_id] = page
        return page

    def mirror_page(self, page: ConfluencePage, mirror_root: Path) -> ConfluenceMirrorRecord:
        return _mirror_page_to_storage(page, mirror_root)


def confluence_config_from_settings(settings: object) -> ConfluenceAdapterConfig:
    """Build adapter config from PlatformSettings or ConfluenceSettings-like objects."""

    confluence = getattr(settings, "confluence", settings)
    return ConfluenceAdapterConfig(
        base_url=getattr(confluence, "base_url"),
        space_key=getattr(confluence, "space_key"),
        parent_page_id=str(getattr(confluence, "parent_page_id")),
        email=getattr(confluence, "email", ""),
        api_token=getattr(confluence, "api_token", ""),
    )


def redacted_confluence_config(config: ConfluenceAdapterConfig) -> dict[str, str]:
    """Return non-secret configuration values for logs and diagnostics."""

    return {
        "base_url": config.normalized_base_url,
        "space_key": config.space_key,
        "parent_page_id": config.parent_page_id,
        "email": config.email,
        "api_token": "<redacted>" if config.api_token else "",
    }


def confluence_cloud_adapter_from_settings(settings: object) -> ConfluenceCloudDocumentationAdapter:
    """Create a Confluence Cloud adapter from PlatformSettings or ConfluenceSettings."""

    return ConfluenceCloudDocumentationAdapter(confluence_config_from_settings(settings))


def validate_confluence_mirror_readiness(
    *,
    mirror_root: Path,
    space_key: str,
) -> ConfluenceMirrorReadiness:
    """Confirm the durable mirror folder for one Confluence space is writable."""

    clean_space_key = space_key.strip()
    if not clean_space_key:
        return ConfluenceMirrorReadiness(
            space_key="",
            path=mirror_root,
            passed=False,
            message="Confluence space key is required before validating mirror readiness.",
        )

    space_root = mirror_root / clean_space_key
    probe_path = space_root / ".confluence-mirror-readiness-check"
    try:
        space_root.mkdir(parents=True, exist_ok=True)
        probe_path.write_text("ok", encoding="utf-8")
        if probe_path.read_text(encoding="utf-8") != "ok":
            return ConfluenceMirrorReadiness(
                space_key=clean_space_key,
                path=space_root,
                passed=False,
                message="Confluence mirror write check could not be read back.",
            )
    except OSError as exc:
        return ConfluenceMirrorReadiness(
            space_key=clean_space_key,
            path=space_root,
            passed=False,
            message=f"Confluence mirror write check failed: {exc.__class__.__name__}.",
        )
    finally:
        try:
            probe_path.unlink(missing_ok=True)
        except OSError:
            pass

    return ConfluenceMirrorReadiness(
        space_key=clean_space_key,
        path=space_root,
        passed=True,
        message="Confluence mirror space directory is writable.",
    )


def _page_payload(
    space_key: str,
    title: str,
    body_storage: str,
    parent_page_id: str,
    *,
    page_id: str = "",
    version: int | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "type": "page",
        "title": title,
        "space": {"key": space_key},
        "ancestors": [{"id": parent_page_id}],
        "body": {
            "storage": {
                "value": body_storage,
                "representation": "storage",
            }
        },
    }
    if page_id:
        payload["id"] = page_id
    if version is not None:
        payload["version"] = {"number": version}
    return payload


def _space_from_json(raw: Mapping[str, Any]) -> ConfluenceSpaceMetadata:
    homepage = _dict(raw.get("homepage"))
    return ConfluenceSpaceMetadata(
        id=str(raw.get("id") or ""),
        key=str(raw.get("key") or ""),
        name=str(raw.get("name") or ""),
        homepage_id=str(homepage.get("id") or ""),
    )


def _page_from_json(raw: Mapping[str, Any], *, fallback_space_key: str) -> ConfluencePage:
    space = _dict(raw.get("space"))
    body = _dict(raw.get("body"))
    storage = _dict(body.get("storage"))
    version = _dict(raw.get("version"))
    links = _dict(raw.get("_links"))
    ancestors = _list(raw.get("ancestors"))
    parent = _dict(ancestors[-1]) if ancestors else {}
    return ConfluencePage(
        id=str(raw.get("id") or ""),
        title=str(raw.get("title") or ""),
        space_key=str(space.get("key") or fallback_space_key),
        version=int(version.get("number") or 1),
        body_storage=str(storage.get("value") or ""),
        parent_page_id=str(parent.get("id") or ""),
        web_url=str(links.get("webui") or ""),
    )


def _mirror_page_to_storage(page: ConfluencePage, mirror_root: Path) -> ConfluenceMirrorRecord:
    space_root = mirror_root / page.space_key
    space_root.mkdir(parents=True, exist_ok=True)
    path = space_root / f"{page.id}.md"
    content = "\n".join(
        (
            f"# {page.title}",
            "",
            f"page_id: {page.id}",
            f"space_key: {page.space_key}",
            f"version: {page.version}",
            f"parent_page_id: {page.parent_page_id}",
            f"web_url: {page.web_url}",
            "",
            page.body_storage,
            "",
        )
    )
    path.write_text(content, encoding="utf-8")
    return ConfluenceMirrorRecord(page_id=page.id, title=page.title, path=path)


def _confluence_error_message(raw: str) -> str:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return "response message unavailable"
    if not isinstance(data, dict):
        return "response message unavailable"
    message = data.get("message") or data.get("authorized") or data.get("reason")
    return str(message) if message else "response message unavailable"


def _dict(raw: object) -> Mapping[str, Any]:
    if isinstance(raw, dict):
        return raw
    return {}


def _list(raw: object) -> list[Any]:
    if isinstance(raw, list):
        return raw
    return []
