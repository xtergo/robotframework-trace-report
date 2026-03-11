# Robot Framework Output XML Format Reference (7.x)

Internal reference for the RF 7.x output.xml schema, used when building
the output.xml → OTLP converter.

## Schema Versions

| RF Version | Schema Version | Key Changes |
|------------|---------------|-------------|
| ≤ 6.x     | ≤ 4           | Legacy format — control structures encoded as `<kw type="...">` |
| 7.0        | 5             | Breaking change — control structures become own elements |
| 7.1        | 6             | Minor refinements |
| 7.2+       | 6             | JSON output support (`output.json`), `<group>` element added |
| 7.4.x      | 6             | Secret variables; no schema change |

The schema file is `result.xsd` (renamed from `robot.xsd` in 7.x).

## RF 7.0+ Output XML Structure (schemaversion ≥ 5)

### Root Element

```xml
<robot generator="Robot 7.4.2 (Python 3.12 on linux)"
       generated="2025-06-01T12:00:00.000000"
       rpa="false"
       schemaversion="6">
```

### Control Structure Elements (new in 7.0)

In RF 6.x these were `<kw type="if">`, `<kw type="for">`, etc.
In RF 7.0+ they are first-class elements:

- `<if>` — contains `<branch>` children with `type="if"`, `type="elseif"`, `type="else"`
- `<try>` — contains `<branch>` children with `type="try"`, `type="except"`, `type="finally"`
- `<for>` — contains `<iter>` children (one per iteration)
- `<while>` — contains `<iter>` children
- `<var>` — VAR syntax
- `<return>` — RETURN statement
- `<break>` — BREAK statement
- `<continue>` — CONTINUE statement
- `<group>` — GROUP syntax (RF 7.2+)

### `<kw>` Element (simplified)

The `type` attribute is now only used for `setup` and `teardown`.
Regular keywords have no `type` attribute.

```xml
<kw name="Log" library="BuiltIn">
    <arg>Hello</arg>
    <doc>Logs the given message.</doc>
    <msg time="2025-06-01T12:00:00.001000" level="INFO">Hello</msg>
    <status status="PASS" start="2025-06-01T12:00:00.000000"
            elapsed="0.001"/>
</kw>
```

### `<status>` Element

```xml
<status status="PASS|FAIL|SKIP"
        start="2025-06-01T12:00:00.000000"
        elapsed="0.123"/>
```

- `start` — ISO 8601 timestamp (was `starttime`/`endtime` in 6.x)
- `elapsed` — seconds as float (replaces computing from start/end)

### `<msg>` Element

Can appear directly under `<test>` (not just under `<kw>`).

```xml
<msg time="2025-06-01T12:00:00.001000"
     level="INFO|WARN|ERROR|DEBUG|TRACE"
     html="true|false">Message text</msg>
```

### Hierarchy

```
<robot>
  <suite name="..." source="...">
    <suite ...>              <!-- nested suites -->
    <test name="..." id="...">
      <kw name="..." library="...">   <!-- setup (type="setup") -->
      <kw name="..." library="...">   <!-- regular keywords -->
        <for>/<while>/<if>/<try>       <!-- control structures -->
      <kw name="..." library="...">   <!-- teardown (type="teardown") -->
      <tag>tagname</tag>
      <status .../>
    </test>
    <status .../>
  </suite>
  <statistics>...</statistics>
  <errors>...</errors>
</robot>
```

### Legacy Output

`--legacyoutput` flag produces RF 6.x-compatible output for tools
that haven't been updated. Uses `<kw type="if">` style and
`starttime`/`endtime` attributes.

## Sources

- [RF 7.0 release announcement](https://forum.robotframework.org/t/robot-framework-7-0-has-been-released/6646)
- [RF 7.4.2 User Guide](https://robotframework.org/robotframework/7.4.2/RobotFrameworkUserGuide.html)
- [RF result.xsd schema](https://github.com/robotframework/robotframework/blob/master/doc/schema/result.xsd)
