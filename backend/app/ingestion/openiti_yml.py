from __future__ import annotations

import json


def parse_openiti_yml_text(raw: str) -> dict[str, str]:
    """Parse OpenITI's line-oriented YML metadata without treating it as strict YAML.

    OpenITI metadata uses ``KEY: value`` records, but continuation lines may contain
    unquoted colons. Those files are therefore not guaranteed to be accepted by a
    generic YAML parser. Continuation lines belong to the preceding key and are
    preserved with newline separators.
    """

    metadata: dict[str, str] = {}
    current_key: str | None = None

    for line_number, raw_line in enumerate(raw.splitlines(), start=1):
        if not raw_line.strip():
            continue

        if raw_line[:1].isspace():
            if current_key is None:
                raise ValueError(
                    f"OpenITI YML continuation without a preceding key at line {line_number}"
                )
            continuation = raw_line.strip()
            if continuation:
                previous = metadata[current_key]
                metadata[current_key] = (
                    f"{previous}\n{continuation}" if previous else continuation
                )
            continue

        if ":" not in raw_line:
            raise ValueError(
                f"OpenITI YML record is missing ':' at line {line_number}: {raw_line!r}"
            )

        key, value = raw_line.split(":", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            raise ValueError(f"OpenITI YML key is empty at line {line_number}")

        if key in metadata:
            # Preserve repeated records instead of silently discarding source metadata.
            previous = metadata[key]
            metadata[key] = f"{previous}\n{value}" if previous and value else previous or value
        else:
            metadata[key] = value
        current_key = key

    return metadata


def as_strict_yaml_input(raw: str) -> str:
    """Return a JSON mapping, which is valid YAML input for the existing parser.

    Values remain strings and the source file itself is not modified.
    """

    return json.dumps(parse_openiti_yml_text(raw), ensure_ascii=False)
