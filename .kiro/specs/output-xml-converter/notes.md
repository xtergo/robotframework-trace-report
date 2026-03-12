# Output XML Converter — Gap Analysis & Future Work

Items identified during requirements review that are not yet covered
by the current spec. Grouped by priority.

## Should Add (high impact for viewer experience)

- [x] **`<doc>` elements** — Suites, tests, and keywords all have optional
  `<doc>` children. The rf_model has `doc` fields and the trace format
  uses `rf.suite.doc`, `rf.test.doc`, `rf.keyword.doc`. ✅ Mapped in b88afaf.

- [x] **Suite `<metadata>`** — `<metadata><item name="key">value</item></metadata>`
  maps to `rf.suite.metadata.*` attributes. ✅ Mapped in b88afaf.

- [x] **Failure messages in `<status>`** — Status elements can contain text
  content for failures: `<status status="FAIL">Error message here</status>`.
  Maps to `status.message` on the OTLP span and `status_message` on the
  rf_model. ✅ Mapped in b88afaf.

## Conscious Deferrals (low impact / no current trace mapping)

- [ ] **`<var>` elements** — Variable assignments under `<kw>` (e.g.
  `<var>${result}</var>`). The existing tracer listener doesn't capture
  these. Can skip for v1.

- [ ] **`<return>`, `<break>`, `<continue>`** — RF 7.x control flow
  statements. No clear mapping in the current OTLP span attribute
  contract. Can skip for v1.

- [ ] **`rf.keyword.lineno`** — The `<kw>` element in output.xml does NOT
  have a `line` attribute (only `<test>` does, e.g. `line="8"`). Keyword
  line numbers come from the listener at runtime. The converter can
  populate `rf.test.lineno` but not `rf.keyword.lineno`.

## Notes

- The existing output.xml files in the repo are all RF 7.4.1 schemaversion 5.
- The `<group>` element (RF 7.2+) is not present in any repo fixtures yet.
  Req 5 doesn't cover it — add when we encounter real-world usage.
