from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LONG_TERM_DOCS = (
    ROOT / "docs/contracts/template-extraction.md",
    ROOT / "docs/modules/template-extraction.md",
    ROOT / "docs/agents/ai-coding-boundary-guardrails.md",
)


def test_long_term_docs_define_source_entry_as_the_only_judgment_scope() -> None:
    combined = "\n".join(path.read_text(encoding="utf-8") for path in LONG_TERM_DOCS)

    assert "canonical `source_entry_id`" in combined
    assert "过渡期兼容 `scope.reading_block_id`" not in combined
    assert "仍可用 `reading_block_id` / `reading_range_id` 表达 view scope" not in combined
    assert "以 `scope.reading_block_id`" not in combined


def test_long_term_docs_keep_reading_ids_as_input_view_only() -> None:
    contract = LONG_TERM_DOCS[0].read_text(encoding="utf-8")
    module = LONG_TERM_DOCS[1].read_text(encoding="utf-8")

    assert "reading view token" in contract
    assert "不能成为 judgment scope" in contract
    assert "只能组织 reading view，不能表达 judgment scope" in module
