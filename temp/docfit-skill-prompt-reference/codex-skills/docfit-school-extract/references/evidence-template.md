# Evidence Template

Use this as a scratch or committed planning table when school sources are
messy, conflicting, or not purely templated.

## Source Inventory

| File | Kind | Official? | Converted? | Notes |
| --- | --- | --- | --- | --- |
| `upstream/word/template.doc` | legacy Word template | yes/no/unknown | `template.docx` | |

## Rule Evidence

| Area | Final value | Evidence source | Evidence type | Confidence | Notes |
| --- | --- | --- | --- | --- | --- |
| page.top_margin_mm | 25.4 | requirement doc paragraph 81 | visible normative text | high | Overrides converted OOXML |
| Normal.font_cn | 宋体 | styles.xml Normal + prose | OOXML + visible text | high | |
| Heading1.separator | one space after number | prose uses `1□前言` | visible normative text | high | Add mapping/check if enforced |

## Logical Page Ledger

Use this table for every target-school-owned page before the body and after the
body. Do not omit optional pages just because the student source lacks content.

| Order | Page id | Titles / aliases | Owner | Status | Position | Source policy | Empty policy | Evidence | Implementation notes |
| ---: | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | cover | 封面 | target_school_template | required | front matter | generated from metadata / template form | needs-human placeholders for missing fields | official template | fixed block or cover fragment |
| 8 | academic_achievements | 相关的学术成果目录; 攻读硕士学位期间取得的学术成果 | target_school_template | optional | after references or school-specified slot | copy matching student section if present | placeholder_review in draft/review output; document final removal policy if any | official template | add parser aliases and stop-title behavior so references do not swallow it |
| 10 | dataset | 学位论文数据集 | target_school_template | optional/manual_only | post-body | preserve school table or copy source table | placeholder_review / manual_only | official template | school-owned form, not generic body prose |

## Conflict Log

| Field | Source A | Source B | Decision | Reason |
| --- | --- | --- | --- | --- |
| page.top_margin_mm | OOXML: 20mm | prose: 2.54cm | 25.4mm | Visible normative text wins |
| logical_page.academic_achievements.empty_policy | template says 非必需项 | draft conversion should show missing work | keep placeholder in review output | Optional means deletable by user, not silently omitted by extractor |

## Manual-Only / Future Template Work

| Requirement | Why manual now | Future implementation path |
| --- | --- | --- |
| fixed defense record form | school-owned signed form, not body text | preserve in engineering template |
