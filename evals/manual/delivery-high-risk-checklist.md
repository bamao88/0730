# Adobe delivery high-risk page review

Use this checklist only with a current `candidate_verification` render produced by Adobe
PDF Services. Record metadata and findings; never copy student body text into the repository.

## Evidence identity

- [ ] Authorized or deidentified sample ID recorded
- [ ] Final DOCX SHA-256 recorded
- [ ] Candidate `render_sha256` recorded
- [ ] Adobe PDF Services SDK version, conversion profile, opaque font-environment marker, and DPI recorded
- [ ] Candidate PDF page count matches the render ref
- [ ] Every final page was supplied to and reviewed by the main Agent

## Human high-risk checks

- [ ] Cover title, identity slots, logos, and fixed wording neither overflow nor disappear
- [ ] No unexpected blank page; every intentional blank page is explained
- [ ] TOC entries, leaders, indentation, and page numbers align
- [ ] Heading pagination has no stranded heading, widow, or orphan at a page boundary
- [ ] Tables retain borders, merged cells, column widths, captions, and readable page breaks
- [ ] Pictures, equations, footnotes, text boxes, headers, and footers remain positioned
- [ ] Section breaks, numbering restarts, page orientation, and margins change only where intended
- [ ] Placeholders and template instruction text are removed or explicitly retained with evidence
- [ ] No visible application error marker, broken field result, or broken cross-reference remains;
      use a focused crop when full-page scale cannot resolve small field, caption, or boundary text
- [ ] No visible tracked-change markup, hidden instruction, repair symptom, unexplained substitution, or blocking finding remains

## Result record

Record `PASS`, `FAIL`, or `UNKNOWN` for each checked page/range, the evidence ref, finding
category, severity, and suggested action. A missing page, unavailable Adobe conversion,
unverifiable managed font environment, or unverifiable layout is `UNKNOWN`, never `PASS`.
Record the external human reviewer's identity or approved reviewer ID and review date outside the
repository when the sample is private. Agent review and an internal engineering visual check are
supporting evidence, not the required human sign-off.
