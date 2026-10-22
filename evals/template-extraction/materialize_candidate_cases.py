import argparse
import json
from pathlib import Path

from template_extraction_prep.candidate_package import build_candidate_packages

DEFAULT_SOURCE_ROOT = (
    Path(__file__).resolve().parent / "candidate-sources/v0.5.yaml"
)
DEFAULT_OUTPUT_ROOT = Path(__file__).resolve().parent / "cases"


def _manifest_path(source_root: Path) -> Path:
    if source_root.is_file() or source_root.suffix in {".yaml", ".yml"}:
        return source_root
    return source_root / "sources.yaml"


def materialize_cases(source_root: Path, output_root: Path) -> list[Path]:
    """Compatibility wrapper over template_extraction_prep.

    The old source_root directory contract was a temp-layout adapter.  The new
    contract is an explicit source manifest.  Keep this function name for
    existing callers while moving all package semantics behind the prep module.
    """

    manifest_path = _manifest_path(source_root)
    return [
        receipt.case_root
        for receipt in build_candidate_packages(manifest_path, output_root)
    ]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Materialize template-extraction candidate case packages."
    )
    parser.add_argument("--source-root", type=Path, default=DEFAULT_SOURCE_ROOT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    args = parser.parse_args()
    generated = materialize_cases(args.source_root.resolve(), args.output_root.resolve())
    print(
        json.dumps(
            {"status": "ok", "cases": [path.as_posix() for path in generated]},
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
