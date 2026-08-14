"""The one fixed Docker LibreOffice rendering adapter."""

from __future__ import annotations

import os
import shutil
import subprocess
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path

from docfit.tools.runtime import JsonObject, ToolFailure

DEFAULT_IMAGE = "docfit-libreoffice-visual:25.2.3.2"
EXPECTED_VERSION = "LibreOffice 25.2.3.2"
EXPECTED_LOCALE = "zh_CN.UTF-8"
PDF_FILTER_OPTIONS = (
    'pdf:writer_pdf_Export:{"UseLosslessCompression":{"type":"boolean","value":"true"},'
    '"ReduceImageResolution":{"type":"boolean","value":"false"},'
    '"ExportBookmarks":{"type":"boolean","value":"true"}}'
)


@dataclass(frozen=True, slots=True)
class RendererEnvironment:
    name: str
    version: str
    container_image: str
    container_image_digest: str
    font_environment_digest: str
    locale: str
    pdf_export_options: str

    def public(self) -> JsonObject:
        return asdict(self)


class LibreOfficeRenderer:
    """Run one immutable, network-disabled LibreOffice container per DOCX."""

    def __init__(
        self,
        image: str | None = None,
        *,
        timeout_seconds: int = 180,
        docker: str | None = None,
    ) -> None:
        self.image = image or os.environ.get("DOCFIT_VISUAL_IMAGE", DEFAULT_IMAGE)
        self.timeout_seconds = timeout_seconds
        self.docker = docker or shutil.which("docker") or "docker"
        self._environment: RendererEnvironment | None = None
        self._resolved_image: str | None = None

    def _resolve_image(self) -> str:
        """Resolve the configured tag once and run every container by immutable ID.

        Docker Desktop can briefly list a local tag while ``image inspect <tag>``
        returns ``No such image``.  Falling back to the exact ID from the
        reference-filtered image list avoids making Agent runs depend on that
        tag lookup race.
        """

        if self._resolved_image is not None:
            return self._resolved_image
        try:
            image_id = self._run(
                [
                    self.docker,
                    "inspect",
                    "--type=image",
                    "--format",
                    "{{.Id}}",
                    self.image,
                ],
                code="visual_renderer_unavailable",
            ).stdout.strip()
        except ToolFailure as initial_error:
            listed = self._run(
                [
                    self.docker,
                    "image",
                    "ls",
                    "--filter",
                    f"reference={self.image}",
                    "--no-trunc",
                    "--format",
                    "{{.ID}}",
                ],
                code="visual_renderer_unavailable",
            ).stdout.splitlines()
            candidates = [value.strip() for value in listed if value.strip()]
            if len(candidates) != 1 or not candidates[0].startswith("sha256:"):
                raise initial_error
            image_id = self._run(
                [
                    self.docker,
                    "inspect",
                    "--type=image",
                    "--format",
                    "{{.Id}}",
                    candidates[0],
                ],
                code="visual_renderer_unavailable",
            ).stdout.strip()
        if not image_id.startswith("sha256:"):
            raise ToolFailure(
                status="error",
                origin="environment",
                code="visual_renderer_unavailable",
                message="The fixed Docker LibreOffice renderer has no immutable image ID.",
            )
        self._resolved_image = image_id
        return image_id

    def environment(self) -> RendererEnvironment:
        if self._environment is not None:
            return self._environment
        image_digest = self._resolve_image()
        audit_command = (
            "printf 'version='; cat /opt/docfit/libreoffice-version.txt; "
            "printf 'locale=%s\\n' \"$LANG\"; "
            "printf 'fonts='; "
            "find /usr/share/fonts -type f -print0 | sort -z | "
            "xargs -0 sha256sum | sha256sum | cut -d' ' -f1"
        )
        completed = self._run(
            [
                self.docker,
                "run",
                "--rm",
                "--network",
                "none",
                "--read-only",
                "--cap-drop",
                "ALL",
                "--security-opt",
                "no-new-privileges",
                "--tmpfs",
                "/tmp:rw,size=128m",
                image_digest,
                "sh",
                "-lc",
                audit_command,
            ],
            code="visual_renderer_audit_failed",
        )
        audit = dict(
            line.split("=", 1)
            for line in completed.stdout.splitlines()
            if "=" in line
        )
        version = audit.get("version", "")
        locale = audit.get("locale", "")
        font_digest = audit.get("fonts", "")
        if not version.startswith(EXPECTED_VERSION) or locale != EXPECTED_LOCALE:
            raise ToolFailure(
                status="error",
                origin="environment",
                code="visual_renderer_identity_mismatch",
                message="The LibreOffice image does not match the locked renderer identity.",
            )
        if len(font_digest) != 64:
            raise ToolFailure(
                status="error",
                origin="environment",
                code="visual_renderer_font_identity_missing",
                message="The LibreOffice image returned no stable font environment digest.",
            )
        self._environment = RendererEnvironment(
            name="libreoffice",
            version=version,
            container_image=self.image,
            container_image_digest=image_digest,
            font_environment_digest=font_digest,
            locale=locale,
            pdf_export_options=PDF_FILTER_OPTIONS,
        )
        return self._environment

    def render(self, input_docx: Path, output_pdf: Path) -> None:
        self.environment()
        assert self._resolved_image is not None
        output_pdf.parent.mkdir(parents=True, exist_ok=True)
        container_name = f"docfit-visual-{uuid.uuid4().hex[:16]}"
        command = (
            "mkdir -p /tmp/home /tmp/lo-profile && "
            "soffice --headless --nologo --nodefault --nofirststartwizard "
            "--nolockcheck --norestore "
            "-env:UserInstallation=file:///tmp/lo-profile "
            f"--convert-to '{PDF_FILTER_OPTIONS}' --outdir /output /input/document.docx"
        )
        arguments = [
            self.docker,
            "run",
            "--rm",
            "--name",
            container_name,
            "--network",
            "none",
            "--read-only",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--user",
            f"{os.getuid()}:{os.getgid()}",
            "--tmpfs",
            "/tmp:rw,size=2g,mode=1777",
            "-e",
            "HOME=/tmp/home",
            "-v",
            f"{input_docx.resolve(strict=True)}:/input/document.docx:ro",
            "-v",
            f"{output_pdf.parent.resolve(strict=True)}:/output:rw",
            self._resolved_image,
            "sh",
            "-lc",
            command,
        ]
        try:
            completed = subprocess.run(
                arguments,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as error:
            subprocess.run(
                [self.docker, "rm", "-f", container_name],
                capture_output=True,
                timeout=30,
                check=False,
            )
            raise ToolFailure(
                status="error",
                origin="renderer",
                code="visual_renderer_timeout",
                message="LibreOffice did not finish within the configured timeout.",
                retryable=True,
            ) from error
        except OSError as error:
            raise ToolFailure(
                status="error",
                origin="environment",
                code="visual_renderer_launch_failed",
                message="The Docker LibreOffice renderer could not be started.",
            ) from error
        if completed.returncode != 0:
            raise ToolFailure(
                status="error",
                origin="renderer",
                code="visual_renderer_failed",
                message="LibreOffice failed to convert the DOCX to PDF.",
            )
        generated = output_pdf.parent / "document.pdf"
        if output_pdf != generated and generated.is_file():
            os.replace(generated, output_pdf)
        if not output_pdf.is_file() or output_pdf.stat().st_size == 0:
            raise ToolFailure(
                status="error",
                origin="postcondition",
                code="visual_renderer_pdf_missing",
                message="LibreOffice reported success but produced no complete PDF.",
            )

    @staticmethod
    def _run(arguments: list[str], *, code: str) -> subprocess.CompletedProcess[str]:
        try:
            completed = subprocess.run(
                arguments,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=60,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise ToolFailure(
                status="error",
                origin="environment",
                code=code,
                message="The fixed Docker LibreOffice renderer is not ready.",
            ) from error
        if completed.returncode != 0:
            raise ToolFailure(
                status="error",
                origin="environment",
                code=code,
                message="The fixed Docker LibreOffice renderer is not ready.",
            )
        return completed
