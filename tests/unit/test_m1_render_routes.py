from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from adobe.pdfservices.operation.config.client_config import ClientConfig
from adobe.pdfservices.operation.exception.exceptions import (
    SdkException,
    ServiceApiException,
    ServiceUsageException,
)
from adobe.pdfservices.operation.io.cloud_asset import CloudAsset
from PIL import Image

from docfit.tools.adobe import (
    ADOBE_CONNECT_TIMEOUT_MS,
    ADOBE_FIDELITY,
    ADOBE_READ_TIMEOUT_MS,
    AdobePdfServicesAdapter,
    AdobePdfServicesCredentials,
)
from docfit.tools.runtime import JsonObject, ToolFailure
from docfit.tools.service import DocFitToolService


class _FakeOffice:
    calls = 0

    def evidence(self) -> JsonObject:
        return {"name": "officecli", "version": "1.0.143"}

    def __getattr__(self, name: str) -> Any:
        self.calls += 1
        raise AssertionError(f"Adobe routes must not fall back to OfficeCLI: {name}")


class _FailingAdobe:
    def evidence(self) -> JsonObject:
        return {"name": "adobe_pdf_services", "version": "4.2.0"}

    def font_environment(self) -> JsonObject:
        return {
            "fingerprint": None,
            "font_file_count": None,
            "substitutions": None,
            "source": "adobe_managed_service",
            "visibility": "opaque",
        }

    def export_pdf(self, document: Path, output_pdf: Path) -> None:
        raise ToolFailure(
            status="error",
            origin="provider",
            code="adobe_pdf_services_api_failed",
            message="Adobe unavailable in test.",
        )


class _SuccessfulAdobe(_FailingAdobe):
    def __init__(self) -> None:
        self.calls = 0

    def export_pdf(self, document: Path, output_pdf: Path) -> None:
        self.calls += 1
        output_pdf.write_bytes(b"%PDF-test")


def _fake_pdf_pages(pdf: Path, directory: Path, *, dpi: int) -> list[Path]:
    assert pdf.read_bytes() == b"%PDF-test"
    assert dpi == 144
    directory.mkdir(parents=True, exist_ok=True)
    page = directory / "page-1.png"
    Image.new("RGB", (100, 140), "white").save(page)
    return [page]


def test_adobe_failure_does_not_call_officecli(tmp_path: Path) -> None:
    document = tmp_path / "input.docx"
    document.write_bytes(b"test-only-input")
    office = _FakeOffice()
    service = DocFitToolService(
        office=office,  # type: ignore[arg-type]
        adobe=_FailingAdobe(),  # type: ignore[arg-type]
    )

    with pytest.raises(ToolFailure) as failure:
        service.render(
            {
                "task_root": str(tmp_path),
                "input_docx": document.name,
                "render_intent": "baseline",
                "output_dir": "adobe-baseline",
            }
        )

    assert failure.value.code == "adobe_pdf_services_api_failed"
    assert office.calls == 0
    assert not (tmp_path / "adobe-baseline").exists()


def test_adobe_baseline_candidate_parent_and_cache(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document = tmp_path / "input.docx"
    document.write_bytes(b"test-only-input")
    monkeypatch.setattr("docfit.tools.service.pdf_to_png_pages", _fake_pdf_pages)
    adobe = _SuccessfulAdobe()
    service = DocFitToolService(
        office=_FakeOffice(),  # type: ignore[arg-type]
        adobe=adobe,  # type: ignore[arg-type]
    )
    baseline = service.render(
        {
            "task_root": str(tmp_path),
            "input_docx": document.name,
            "render_intent": "baseline",
            "output_dir": "baseline",
        }
    )
    assert baseline["render_ref"]["fidelity"] == ADOBE_FIDELITY
    assert baseline["render_ref"]["target_application"] is None
    assert baseline["render_ref"]["provider"]["name"] == "adobe_pdf_services"
    assert baseline["render_ref"]["font_environment"]["visibility"] == "opaque"
    assert baseline["render_ref"]["font_substitutions"] is None
    assert baseline["render_ref"]["artifacts"]["pdf"].endswith("document.pdf")
    cached = service.render(
        {
            "task_root": str(tmp_path),
            "input_docx": document.name,
            "render_intent": "baseline",
            "output_dir": "baseline",
        }
    )
    assert cached["cache_hit"] is True
    assert cached["render_ref"]["render_sha256"] == baseline["render_ref"]["render_sha256"]
    assert adobe.calls == 1

    candidate = service.render(
        {
            "task_root": str(tmp_path),
            "input_docx": document.name,
            "render_intent": "candidate_verification",
            "baseline_render_ref": "baseline",
            "output_dir": "candidate",
        }
    )
    assert (
        candidate["render_ref"]["parent_render_ref"]["render_sha256"]
        == baseline["render_ref"]["render_sha256"]
    )
    assert adobe.calls == 2


def test_public_render_rejects_backend_selector(tmp_path: Path) -> None:
    document = tmp_path / "input.docx"
    document.write_bytes(b"test-only-input")
    service = DocFitToolService(
        office=_FakeOffice(),  # type: ignore[arg-type]
        adobe=_FailingAdobe(),  # type: ignore[arg-type]
    )
    with pytest.raises(ToolFailure) as failure:
        service.render(
            {
                "task_root": str(tmp_path),
                "input_docx": document.name,
                "render_intent": "baseline",
                "output_dir": "output",
                "provider": "officecli",
            }
        )
    assert failure.value.code == "backend_selection_denied"


class _ResultAsset:
    def get_asset(self) -> object:
        return object()


class _Response:
    def get_result(self) -> _ResultAsset:
        return _ResultAsset()


class _Stream:
    def get_input_stream(self) -> bytes:
        return b"%PDF-1.7\nsynthetic"


class _FakePdfServices:
    received_config: ClientConfig | None = None

    def __init__(self, credentials: object, client_config: ClientConfig) -> None:
        self.credentials = credentials
        type(self).received_config = client_config

    def upload(self, *, input_stream: bytes, mime_type: str) -> CloudAsset:
        assert input_stream == b"synthetic-docx"
        assert mime_type
        return CloudAsset("test-input-asset")

    def submit(self, job: object) -> str:
        assert job is not None
        return "test-polling-url"

    def get_job_result(self, polling_url: str, result_type: object) -> _Response:
        assert polling_url == "test-polling-url"
        assert result_type is not None
        return _Response()

    def get_content(self, asset: object) -> _Stream:
        assert asset is not None
        return _Stream()


def test_adobe_adapter_uses_service_principal_and_publishes_complete_pdf(
    tmp_path: Path,
) -> None:
    credentials = AdobePdfServicesCredentials("client", "secret", "organization")
    adapter = AdobePdfServicesAdapter(credentials, services_factory=_FakePdfServices)
    document = tmp_path / "input.docx"
    output = tmp_path / "output.pdf"
    document.write_bytes(b"synthetic-docx")

    adapter.export_pdf(document, output)

    assert output.read_bytes().startswith(b"%PDF-")
    assert _FakePdfServices.received_config is not None
    assert _FakePdfServices.received_config.get_connect_timeout() == (
        ADOBE_CONNECT_TIMEOUT_MS / 1000
    )
    assert _FakePdfServices.received_config.get_read_timeout() == (
        ADOBE_READ_TIMEOUT_MS / 1000
    )
    assert "secret" not in repr(credentials)
    assert "client" not in repr(credentials)


def test_adobe_credentials_require_all_three_values() -> None:
    with pytest.raises(ToolFailure) as failure:
        AdobePdfServicesCredentials.from_environment(
            {"DOCFIT_ADOBE_PDF_SERVICES_CLIENT_ID": "client"}
        )

    assert failure.value.code == "adobe_credentials_missing"


class _RaisingPdfServices:
    def __init__(self, error: Exception) -> None:
        self.error = error

    def upload(self, *, input_stream: bytes, mime_type: str) -> object:
        raise self.error


@pytest.mark.parametrize(
    ("provider_error", "expected_code"),
    (
        (
            ServiceUsageException("raw-provider-detail", "tracking-id"),
            "adobe_pdf_services_quota_exhausted",
        ),
        (
            ServiceApiException("raw-provider-detail", "tracking-id", 500),
            "adobe_pdf_services_api_failed",
        ),
        (
            SdkException("raw-provider-detail", "tracking-id"),
            "adobe_pdf_services_sdk_failed",
        ),
    ),
)
def test_adobe_adapter_normalizes_provider_failures_without_raw_detail(
    tmp_path: Path,
    provider_error: Exception,
    expected_code: str,
) -> None:
    credentials = AdobePdfServicesCredentials("client", "secret", "organization")
    adapter = AdobePdfServicesAdapter(
        credentials,
        services_factory=lambda _credentials, _config: _RaisingPdfServices(provider_error),
    )
    document = tmp_path / "input.docx"
    output = tmp_path / "output.pdf"
    document.write_bytes(b"synthetic-docx")

    with pytest.raises(ToolFailure) as failure:
        adapter.export_pdf(document, output)

    assert failure.value.code == expected_code
    assert "raw-provider-detail" not in failure.value.message
    assert not output.exists()
