# Integration review targets

- Verify load_initial_inventory always compares canonical inventory digest against task manifest, not only on resume. Current early version checks self-consistent digests but not manifest; recomputed inventory payload could otherwise become a new initial view in Tool reads. Production initial creation writes manifest before first query.
- Check all Agent-visible source evidence has original source_entry_id and read-only visual/layout clues; no raw object identity alternative.
- Verify published source_partition entries re-resolve slot spans as well as proof extents; independent targets remain impossible.
- Full CLI run before latest worker final changes must be replayed on final code and final baseline recorded.
- Three-school initial-read and split probes are real-input mechanical probes with test-authored boundary semantics, not fresh Agent E2E/replay by themselves.
- Combined minimal input-package builder failed namespace package validation; original unit and original school files passed. Record build defect separately, no weakened package check.
