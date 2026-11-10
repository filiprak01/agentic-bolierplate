import io
import urllib.error
import urllib.request
from pathlib import Path

from agentic_boilerplate.config import settings_from_mapping
from agentic_boilerplate.integrations import (
    ConfluenceAdapterConfig,
    ConfluenceAdapterError,
    ConfluenceCloudDocumentationAdapter,
    ConfluenceCloudTransport,
    ConfluenceMirrorRecord,
    ConfluencePage,
    ConfluencePageFields,
    MockConfluenceDocumentationAdapter,
    confluence_config_from_settings,
    redacted_confluence_config,
    validate_confluence_mirror_readiness,
)


class RecordingConfluenceTransport:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, object]] = []

    def request(self, method: str, path: str, payload: object = None) -> object:
        self.calls.append((method, path, payload))
        if method == "GET" and path == "/rest/api/space/DOCS?expand=homepage":
            return {
                "id": "100",
                "key": "DOCS",
                "name": "Documentation",
                "homepage": {"id": "12345"},
            }
        if method == "GET" and path == "/rest/api/content/12345?expand=space,body.storage,version,ancestors":
            return confluence_page_json(
                page_id="12345",
                title="Home",
                body_storage="<p>Home</p>",
                version=1,
            )
        if method == "GET" and path.startswith("/rest/api/content?"):
            if "Existing" in path:
                return {
                    "results": [
                        confluence_page_json(
                            page_id="999",
                            title="Existing",
                            body_storage="<p>Old</p>",
                            version=3,
                            parent_page_id="12345",
                        )
                    ]
                }
            return {"results": []}
        if method == "POST" and path == "/rest/api/content":
            return confluence_page_json(
                page_id="777",
                title=payload["title"],
                body_storage=payload["body"]["storage"]["value"],
                version=1,
                parent_page_id=payload["ancestors"][0]["id"],
            )
        if method == "PUT" and path == "/rest/api/content/999":
            return confluence_page_json(
                page_id="999",
                title=payload["title"],
                body_storage=payload["body"]["storage"]["value"],
                version=payload["version"]["number"],
                parent_page_id=payload["ancestors"][0]["id"],
            )
        raise AssertionError(f"Unexpected request: {method} {path}")


def confluence_page_json(
    *,
    page_id: str,
    title: str,
    body_storage: str,
    version: int,
    parent_page_id: str = "",
) -> dict[str, object]:
    ancestors = [{"id": parent_page_id}] if parent_page_id else []
    return {
        "id": page_id,
        "type": "page",
        "title": title,
        "space": {"key": "DOCS"},
        "ancestors": ancestors,
        "version": {"number": version},
        "body": {"storage": {"value": body_storage, "representation": "storage"}},
        "_links": {"webui": f"/spaces/DOCS/pages/{page_id}/{title}"},
    }


def confluence_adapter_with_transport() -> tuple[
    ConfluenceCloudDocumentationAdapter,
    RecordingConfluenceTransport,
]:
    transport = RecordingConfluenceTransport()
    adapter = ConfluenceCloudDocumentationAdapter(
        ConfluenceAdapterConfig(
            base_url="https://example.atlassian.net/wiki",
            space_key="DOCS",
            parent_page_id="12345",
            email="docs@example.com",
            api_token="secret-token",
        ),
        transport=transport,
    )
    return adapter, transport


def test_confluence_config_from_settings_uses_configured_space_and_parent() -> None:
    settings = settings_from_mapping(
        {
            "CONFLUENCE_BASE_URL": "https://example.atlassian.net/wiki",
            "CONFLUENCE_SPACE_KEY": "DOCS",
            "CONFLUENCE_PARENT_PAGE_ID": "12345",
            "CONFLUENCE_EMAIL": "docs@example.com",
            "CONFLUENCE_API_TOKEN": "secret-token",
        }
    )

    config = confluence_config_from_settings(settings)

    assert config.normalized_base_url == "https://example.atlassian.net/wiki"
    assert config.space_key == "DOCS"
    assert config.parent_page_id == "12345"
    assert config.email == "docs@example.com"
    assert config.api_token == "secret-token"


def test_redacted_confluence_config_never_exposes_token() -> None:
    config = ConfluenceAdapterConfig(
        base_url="https://example.atlassian.net/wiki/",
        space_key="DOCS",
        parent_page_id="12345",
        email="docs@example.com",
        api_token="super-secret",
    )

    redacted = redacted_confluence_config(config)

    assert redacted["api_token"] == "<redacted>"
    assert "super-secret" not in str(redacted)


def test_confluence_page_fields_support_parent_override() -> None:
    fields = ConfluencePageFields(
        title="Architecture",
        body_storage="<p>Architecture notes</p>",
        parent_page_id="999",
    )

    assert fields.parent_page_id == "999"
    assert fields.body_storage.startswith("<p>")


def test_confluence_mirror_record_uses_path() -> None:
    page = ConfluencePage(
        id="123",
        title="Architecture",
        space_key="DOCS",
        version=4,
        body_storage="<p>Architecture notes</p>",
    )
    record = ConfluenceMirrorRecord(
        page_id=page.id,
        title=page.title,
        path=Path("data/confluence-mirror/DOCS/123.md"),
    )

    assert record.page_id == "123"
    assert record.path.name == "123.md"


def test_confluence_cloud_adapter_reads_space_and_parent_page() -> None:
    adapter, transport = confluence_adapter_with_transport()

    configuration = adapter.validate_access()

    assert configuration.space.key == "DOCS"
    assert configuration.space.homepage_id == "12345"
    assert configuration.parent_page.id == "12345"
    assert configuration.parent_page.body_storage == "<p>Home</p>"
    assert ("GET", "/rest/api/space/DOCS?expand=homepage", None) in transport.calls


def test_confluence_cloud_adapter_creates_child_page_under_parent() -> None:
    adapter, transport = confluence_adapter_with_transport()

    page = adapter.create_or_update_child_page(
        ConfluencePageFields(
            title="New",
            body_storage="<p>New page</p>",
        )
    )

    create_payload = next(
        payload
        for method, path, payload in transport.calls
        if method == "POST" and path == "/rest/api/content"
    )
    assert create_payload["ancestors"][0]["id"] == "12345"
    assert create_payload["body"]["storage"]["value"] == "<p>New page</p>"
    assert page.id == "777"


def test_confluence_cloud_adapter_updates_existing_child_page() -> None:
    adapter, transport = confluence_adapter_with_transport()

    page = adapter.create_or_update_child_page(
        ConfluencePageFields(
            title="Existing",
            body_storage="<p>Updated</p>",
        )
    )

    update_payload = next(
        payload
        for method, path, payload in transport.calls
        if method == "PUT" and path == "/rest/api/content/999"
    )
    assert update_payload["id"] == "999"
    assert update_payload["version"]["number"] == 4
    assert update_payload["body"]["storage"]["value"] == "<p>Updated</p>"
    assert page.version == 4


def test_confluence_cloud_transport_errors_do_not_expose_token(monkeypatch) -> None:
    def fail_urlopen(request, timeout):  # noqa: ANN001
        raise urllib.error.HTTPError(
            request.full_url,
            403,
            "Forbidden",
            {},
            io.BytesIO(b'{"message":"Current user not permitted"}'),
        )

    monkeypatch.setattr(urllib.request, "urlopen", fail_urlopen)
    transport = ConfluenceCloudTransport(
        ConfluenceAdapterConfig(
            base_url="https://example.atlassian.net/wiki",
            space_key="DOCS",
            parent_page_id="12345",
            email="docs@example.com",
            api_token="super-secret-token",
        )
    )

    try:
        transport.request("GET", "/rest/api/space/DOCS")
    except ConfluenceAdapterError as exc:
        assert "Current user not permitted" in str(exc)
        assert "super-secret-token" not in str(exc)
    else:
        raise AssertionError("Expected ConfluenceAdapterError for permission error.")


def test_confluence_adapter_mirrors_page_to_durable_path(tmp_path) -> None:
    adapter, _transport = confluence_adapter_with_transport()
    page = ConfluencePage(
        id="123",
        title="Architecture",
        space_key="DOCS",
        version=4,
        body_storage="<p>Architecture notes</p>",
        parent_page_id="100",
        web_url="/spaces/DOCS/pages/123/Architecture",
    )

    record = adapter.mirror_page(page, tmp_path)

    assert record.path == tmp_path / "DOCS" / "123.md"
    assert record.path.exists()
    content = record.path.read_text(encoding="utf-8")
    assert "# Architecture" in content
    assert "version: 4" in content
    assert "<p>Architecture notes</p>" in content


def test_confluence_mirror_readiness_checks_space_specific_directory(tmp_path) -> None:
    result = validate_confluence_mirror_readiness(
        mirror_root=tmp_path / "confluence-mirror",
        space_key="DOCS",
    )

    assert result.passed
    assert result.path == tmp_path / "confluence-mirror" / "DOCS"
    assert result.path.is_dir()
    assert not (result.path / ".confluence-mirror-readiness-check").exists()


def test_confluence_mirror_readiness_rejects_unusable_space_path(tmp_path) -> None:
    blocked_space_path = tmp_path / "confluence-mirror" / "DOCS"
    blocked_space_path.parent.mkdir()
    blocked_space_path.write_text("not a directory", encoding="utf-8")

    result = validate_confluence_mirror_readiness(
        mirror_root=tmp_path / "confluence-mirror",
        space_key="DOCS",
    )

    assert not result.passed
    assert "Confluence mirror write check failed" in result.message


def test_mock_confluence_adapter_creates_updates_and_mirrors_pages(tmp_path) -> None:
    adapter = MockConfluenceDocumentationAdapter(
        ConfluenceAdapterConfig(
            base_url="https://example.atlassian.net/wiki",
            space_key="DOCS",
            parent_page_id="12345",
        )
    )

    configuration = adapter.validate_access()
    created = adapter.create_or_update_child_page(
        ConfluencePageFields(title="Shared Context", body_storage="<p>Context v1</p>")
    )
    updated = adapter.create_or_update_child_page(
        ConfluencePageFields(title="Shared Context", body_storage="<p>Context v2</p>")
    )
    record = adapter.mirror_page(updated, tmp_path)

    assert configuration.space.homepage_id == "12345"
    assert created.id == updated.id
    assert updated.version == 2
    assert record.path.read_text(encoding="utf-8").count("Context v2") == 1
