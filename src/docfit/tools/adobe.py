"""Adobe PDF Services adapter for the fixed DOCX-to-PDF delivery route."""

from __future__ import annotations

import os
import tempfile
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

from adobe.pdfservices.operation.auth.service_principal_credentials import (
    ServicePrincipalCredentials,
)
from adobe.pdfservices.operation.config.client_config import ClientConfig
from adobe.pdfservices.operation.exception.exceptions import (
    SdkException,
    ServiceApiException,
    ServiceUsageException,
)
from adobe.pdfservices.operation.pdf_services import PDFServices
from adobe.pdfservices.operation.pdf_services_media_type import PDFServicesMediaType
from adobe.pdfservices.operation.pdfjobs.jobs.create_pdf_job import CreatePDFJob
from adobe.pdfservices.operation.pdfjobs.result.create_pdf_result import CreatePDFResult

from docfit.config import ConfigurationError, env_file_is_private, merged_environment
from docfit.tools.runtime import JsonObject, ToolFailure

ADOBE_PDF_SERVICES_EXPECTED_VERSION = "4.2.0"
ADOBE_PDF_SERVICES_CLIENT_ID = "DOCFIT_ADOBE_PDF_SERVICES_CLIENT_ID"
ADOBE_PDF_SERVICES_CLIENT_SECRET = "DOCFIT_ADOBE_PDF_SERVICES_CLIENT_SECRET"
ADOBE_PDF_SERVICES_ORGANIZATION_ID = "DOCFIT_ADOBE_PDF_SERVICES_ORGANIZATION_ID"
ADOBE_CONVERSION_PROFILE = "adobe_pdf_services_default"
ADOBE_REVISION_DISPLAY = "document_default"
ADOBE_FIDELITY = "official_service_conversion"
ADOBE_CONNECT_TIMEOUT_MS = 30_000
ADOBE_READ_TIMEOUT_MS = 120_000


def _pdf_services_factory(credentials: Any, client_config: ClientConfig) -> PDFServices:
    return PDFServices(credentials, client_config=client_config)


@dataclass(frozen=True, slots=True)
class AdobePdfServicesCredentials:
    """One service-principal credential set with secret-safe representation."""

    client_id: str = field(repr=False)
    client_secret: str = field(repr=False)
    organization_id: str = field(repr=False)

    @classmethod
    def from_environment(
        cls,
        environment: Mapping[str, str] | None = None,
        *,
        env_file: Path | None = None,
    ) -> AdobePdfServicesCredentials:
        try:
            values, selected_file = merged_environment(environment, env_file=env_file)
        except ConfigurationError as error:
            raise ToolFailure(
                status="error",
                origin="environment",
                code="adobe_credentials_configuration_invalid",
                message="The shared DocFit environment file is structurally invalid.",
            ) from error
        if selected_file is not None and selected_file.is_file() and not env_file_is_private(
            selected_file
        ):
            raise ToolFailure(
                status="error",
                origin="environment",
                code="adobe_credentials_permissions_invalid",
                message="The shared DocFit environment file must have mode 0600.",
                suggested_actions=("chmod_docfit_env_0600",),
            )
        names = (
            ADOBE_PDF_SERVICES_CLIENT_ID,
            ADOBE_PDF_SERVICES_CLIENT_SECRET,
            ADOBE_PDF_SERVICES_ORGANIZATION_ID,
        )
        resolved = tuple(values.get(name, "").strip() for name in names)
        if not all(resolved):
            raise ToolFailure(
                status="error",
                origin="environment",
                code="adobe_credentials_missing",
                message="Adobe PDF Services credentials are not completely configured.",
                suggested_actions=("configure_adobe_pdf_services_credentials",),
            )
        return cls(*resolved)


class AdobePdfServicesAdapter:
    """Upload one DOCX and download one complete PDF through Adobe PDF Services."""

    def __init__(
        self,
        credentials: AdobePdfServicesCredentials | None = None,
        *,
        services_factory: Callable[[Any, ClientConfig], Any] = _pdf_services_factory,
    ) -> None:
        self.credentials = credentials or AdobePdfServicesCredentials.from_environment()
        self._services_factory = services_factory
        try:
            self.version = version("pdfservices-sdk")
        except PackageNotFoundError as error:
            raise ToolFailure(
                status="error",
                origin="environment",
                code="adobe_pdf_services_sdk_missing",
                message="The locked Adobe PDF Services SDK is not installed.",
            ) from error
        if self.version != ADOBE_PDF_SERVICES_EXPECTED_VERSION:
            raise ToolFailure(
                status="error",
                origin="environment",
                code="adobe_pdf_services_sdk_version_mismatch",
                message="The installed Adobe PDF Services SDK does not match the locked version.",
            )

    @classmethod
    def from_environment(
        cls,
        environment: Mapping[str, str] | None = None,
        *,
        env_file: Path | None = None,
        services_factory: Callable[[Any, ClientConfig], Any] = _pdf_services_factory,
    ) -> AdobePdfServicesAdapter:
        return cls(
            AdobePdfServicesCredentials.from_environment(environment, env_file=env_file),
            services_factory=services_factory,
        )

    def evidence(self) -> JsonObject:
        return {
            "name": "adobe_pdf_services",
            "version": self.version,
            "api_family": "PDF Services API",
            "operation": "create_pdf_from_docx",
            "execution_environment": "adobe_managed_cloud",
            "conversion_profile": ADOBE_CONVERSION_PROFILE,
            "credential_type": "service_principal",
            "organization_id_configured": bool(self.credentials.organization_id),
            "connect_timeout_ms": ADOBE_CONNECT_TIMEOUT_MS,
            "read_timeout_ms": ADOBE_READ_TIMEOUT_MS,
        }

    def font_environment(self) -> JsonObject:
        return {
            "fingerprint": None,
            "font_file_count": None,
            "substitutions": None,
            "source": "adobe_managed_service",
            "visibility": "opaque",
        }

    def export_pdf(self, document: Path, output_pdf: Path) -> None:
        output_pdf.unlink(missing_ok=True)
        try:
            sdk_credentials = ServicePrincipalCredentials(
                client_id=self.credentials.client_id,
                client_secret=self.credentials.client_secret,
            )
            client_config = ClientConfig(
                connect_timeout=ADOBE_CONNECT_TIMEOUT_MS,
                read_timeout=ADOBE_READ_TIMEOUT_MS,
            )
            pdf_services = self._services_factory(sdk_credentials, client_config)
            input_asset = pdf_services.upload(
                input_stream=document.read_bytes(),
                mime_type=PDFServicesMediaType.DOCX,
            )
            polling_url = pdf_services.submit(CreatePDFJob(input_asset))
            response = pdf_services.get_job_result(polling_url, CreatePDFResult)
            result_asset = response.get_result().get_asset()
            payload = pdf_services.get_content(result_asset).get_input_stream()
        except ServiceUsageException as error:
            raise ToolFailure(
                status="error",
                origin="provider",
                code="adobe_pdf_services_quota_exhausted",
                message="Adobe PDF Services rejected the conversion because usage is exhausted.",
                suggested_actions=("check_adobe_transaction_quota",),
            ) from error
        except ServiceApiException as error:
            raise ToolFailure(
                status="error",
                origin="provider",
                code="adobe_pdf_services_api_failed",
                message="Adobe PDF Services could not complete the DOCX-to-PDF conversion.",
                retryable=True,
                suggested_actions=("verify_adobe_credentials", "retry_adobe_conversion"),
            ) from error
        except SdkException as error:
            raise ToolFailure(
                status="error",
                origin="provider",
                code="adobe_pdf_services_sdk_failed",
                message="The Adobe PDF Services SDK failed before a complete PDF was returned.",
                retryable=True,
                suggested_actions=("retry_adobe_conversion",),
            ) from error
        except OSError as error:
            raise ToolFailure(
                status="error",
                origin="environment",
                code="adobe_pdf_services_io_failed",
                message="The Adobe conversion input or result could not be read locally.",
            ) from error
        except Exception as error:
            raise ToolFailure(
                status="error",
                origin="provider",
                code="adobe_pdf_services_unexpected_response",
                message="Adobe PDF Services returned no usable conversion result.",
                retryable=True,
            ) from error

        if not isinstance(payload, bytes) or not payload.startswith(b"%PDF-"):
            raise ToolFailure(
                status="error",
                origin="postcondition",
                code="adobe_pdf_services_pdf_invalid",
                message="Adobe PDF Services returned no complete PDF artifact.",
            )
        output_pdf.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{output_pdf.name}.", suffix=".tmp", dir=output_pdf.parent
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, output_pdf)
        finally:
            temporary.unlink(missing_ok=True)
