"""Measure OfficeCLI HTML preview elements without creating another render backend."""

from __future__ import annotations

import html
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from docfit.tools.runtime import JsonObject, ToolFailure

_CHROME_CANDIDATES = (
    Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
    Path("/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"),
    Path("/Applications/Chromium.app/Contents/MacOS/Chromium"),
)

_LAYOUT_SCRIPT = r"""
<script>
(() => {
  const virtualPages = __DOCFIT_VIRTUAL_PAGES__;
  const pageMetrics = new Map();
  let nextPage = 1;
  for (const page of document.querySelectorAll('.page')) {
    const rectangle = page.getBoundingClientRect();
    const style = getComputedStyle(page);
    const paddingTop = parseFloat(style.paddingTop) || 0;
    const paddingBottom = parseFloat(style.paddingBottom) || 0;
    const pageHeight = parseFloat(style.minHeight) || rectangle.height;
    const contentHeight = pageHeight - paddingTop - paddingBottom;
    const scrollContentHeight = Math.max(0, page.scrollHeight - paddingTop - paddingBottom);
    const pageSpan = virtualPages && contentHeight > 0 ?
      Math.max(1, Math.ceil((scrollContentHeight - 0.5) / contentHeight)) : 1;
    pageMetrics.set(page, {
      basePage: virtualPages ? nextPage : Number(page.getAttribute('data-page')),
      rectangle,
      paddingTop,
      paddingBottom,
      pageHeight,
      contentHeight
    });
    nextPage += pageSpan;
  }
  const records = [...document.querySelectorAll('[data-path]')].map((element) => {
    const page = element.closest('.page');
    const rectangle = element.getBoundingClientRect();
    const metrics = page ? pageMetrics.get(page) : null;
    const pageRectangle = metrics ? metrics.rectangle : null;
    const paddingTop = metrics ? metrics.paddingTop : 0;
    const pageHeight = metrics ? metrics.pageHeight : 0;
    const contentHeight = metrics ? metrics.contentHeight : 0;
    const relativeContentTop = metrics ?
      rectangle.top - metrics.rectangle.top - paddingTop : rectangle.top;
    const flowPageOffset = virtualPages && contentHeight > 0 ?
      Math.max(0, Math.floor(relativeContentTop / contentHeight)) : 0;
    const normalizedTop = metrics && virtualPages ?
      paddingTop + relativeContentTop - flowPageOffset * contentHeight :
      (pageRectangle ? rectangle.top - pageRectangle.top : rectangle.top);
    return {
      path: element.getAttribute('data-path'),
      page: metrics ? metrics.basePage + flowPageOffset : null,
      page_width: pageRectangle ? pageRectangle.width : null,
      page_height: pageRectangle ? pageHeight : null,
      bbox: [
        rectangle.left,
        normalizedTop,
        rectangle.right,
        normalizedTop + rectangle.height
      ]
    };
  });
  document.body.innerHTML = '<pre id="docfit-layout">' +
    JSON.stringify(records).replaceAll('&', '&amp;').replaceAll('<', '&lt;') + '</pre>';
})();
</script>
"""


def chrome_executable() -> Path | None:
    for candidate in _CHROME_CANDIDATES:
        if candidate.is_file():
            return candidate
    found = shutil.which("google-chrome") or shutil.which("chromium")
    return Path(found).resolve() if found else None


def measure_html_layout(
    html_path: Path,
    *,
    virtual_pages: bool = False,
) -> tuple[JsonObject, ...]:
    executable = chrome_executable()
    if executable is None:
        raise ToolFailure(
            status="error",
            origin="environment",
            code="layout_browser_not_found",
            message="A local Chromium browser is required to measure OfficeCLI HTML layout.",
        )
    source = html_path.read_text(encoding="utf-8", errors="strict")
    closing = source.lower().rfind("</body>")
    layout_script = _LAYOUT_SCRIPT.replace(
        "__DOCFIT_VIRTUAL_PAGES__",
        "true" if virtual_pages else "false",
    )
    instrumented = (
        source[:closing] + layout_script + source[closing:]
        if closing >= 0
        else source + layout_script
    )
    descriptor, temporary_name = tempfile.mkstemp(
        prefix="docfit-layout-",
        suffix=".html",
        dir=html_path.parent,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(instrumented)
        try:
            completed = subprocess.run(
                [
                    str(executable),
                    "--headless=new",
                    "--disable-gpu",
                    "--no-sandbox",
                    "--allow-file-access-from-files",
                    "--hide-scrollbars",
                    "--window-size=1600,1200",
                    "--force-device-scale-factor=1",
                    "--virtual-time-budget=1000",
                    "--dump-dom",
                    temporary.as_uri(),
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise ToolFailure(
                status="error",
                origin="environment",
                code="layout_measurement_failed",
                message="OfficeCLI HTML layout measurement did not complete.",
            ) from error
        if completed.returncode != 0:
            raise ToolFailure(
                status="error",
                origin="environment",
                code="layout_measurement_failed",
                message="The local browser rejected OfficeCLI HTML layout measurement.",
            )
        marker = '<pre id="docfit-layout">'
        start = completed.stdout.find(marker)
        end = completed.stdout.find("</pre>", start + len(marker))
        if start < 0 or end < 0:
            raise ToolFailure(
                status="error",
                origin="postcondition",
                code="layout_measurement_missing",
                message="The browser returned no structured layout measurement.",
            )
        raw = html.unescape(completed.stdout[start + len(marker) : end])
        values = json.loads(raw)
        if not isinstance(values, list) or not all(isinstance(item, dict) for item in values):
            raise ToolFailure(
                status="error",
                origin="postcondition",
                code="layout_measurement_shape",
                message="The browser returned malformed layout measurement.",
            )
        normalized: list[JsonObject] = []
        for value in values:
            path = value.get("path")
            page = value.get("page")
            page_width = value.get("page_width")
            page_height = value.get("page_height")
            bbox = value.get("bbox")
            if (
                isinstance(path, str)
                and isinstance(page, int)
                and isinstance(page_width, (int, float))
                and isinstance(page_height, (int, float))
                and page_width > 0
                and page_height > 0
                and isinstance(bbox, list)
                and len(bbox) == 4
                and all(isinstance(item, (int, float)) for item in bbox)
            ):
                normalized.append(
                    {
                        "path": path,
                        "page": page,
                        "page_width": round(float(page_width), 2),
                        "page_height": round(float(page_height), 2),
                        "bbox": [round(float(item), 2) for item in bbox],
                    }
                )
        return tuple(normalized)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ToolFailure(
            status="error",
            origin="adapter",
            code="layout_measurement_adapter_error",
            message="OfficeCLI HTML layout evidence could not be normalized.",
        ) from error
    finally:
        temporary.unlink(missing_ok=True)
