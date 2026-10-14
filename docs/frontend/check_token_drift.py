#!/usr/bin/env python3
"""Read-only Model B token mirror and page-adapter check; stdlib only."""

import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def normalized(value):
    return re.sub(r"\s+", " ", value.strip())


def css_rules(path):
    text = re.sub(r"/\*.*?\*/", "", path.read_text(encoding="utf-8"), flags=re.S)
    return [(normalized(match.group(1)), match.group(2))
            for match in re.finditer(r"([^{}]+)\{([^{}]*)\}", text)]


def runtime_tokens(path):
    selectors = {}
    for selector, body in css_rules(path):
        values = {match.group(1): normalized(match.group(2))
                  for match in re.finditer(r"(--app-[\w-]+)\s*:\s*([^;]+);", body)}
        if values:
            selectors.setdefault(selector, {}).update(values)
    return selectors


def documented_values(path):
    """Parse only the simple scalar YAML subset used by our token mirror.

    This is deliberately not a YAML linter; official designmd owns that check.
    Token strings are JSON-quoted (valid YAML), so CSS quotes remain unambiguous.
    """
    text = path.read_text(encoding="utf-8")
    match = re.match(r"---\s*\n(.*?)\n---(?:\n|$)", text, re.S)
    if not match:
        raise ValueError("DESIGN.md has no YAML frontmatter")
    values, stack = {}, []
    for line in match.group(1).splitlines():
        item = re.match(r"^( *)([A-Za-z][\w-]*):(?: +(.*))?$", line)
        if not item:
            continue
        indent, key, raw = len(item.group(1)), item.group(2), item.group(3)
        while stack and stack[-1][0] >= indent:
            stack.pop()
        key_path = ".".join([entry[1] for entry in stack] + [key])
        if raw is None or not raw.strip():
            stack.append((indent, key))
        elif raw.startswith('"'):
            values[key_path] = json.loads(raw)
        elif raw.startswith("'") and raw.endswith("'"):
            values[key_path] = raw[1:-1].replace("''", "'")
        elif raw not in ("{}", "[]"):
            values[key_path] = raw
    return values


def check():
    mapping = json.loads((ROOT / "docs/frontend/token-mapping.json").read_text(encoding="utf-8"))
    if mapping.get("ownershipModel") != "B":
        raise ValueError("Expected ownershipModel B")
    canonical = ROOT / mapping["canonicalStylesheet"]
    actual = runtime_tokens(canonical)
    expected = mapping["selectors"]
    errors = []
    for selector in sorted(set(actual) | set(expected)):
        current, mirror = actual.get(selector, {}), expected.get(selector, {})
        for token in sorted(set(current) | set(mirror)):
            if current.get(token) != mirror.get(token):
                errors.append({"rule": "canonical.mirror-drift", "selector": selector,
                               "token": token, "runtime": current.get(token), "mirror": mirror.get(token)})
    documentation = documented_values(ROOT / "DESIGN.md")
    for mirror in mapping["designMirrors"]:
        runtime = actual.get(mirror["selector"], {}).get(mirror["token"])
        documented = documentation.get(mirror["designPath"])
        if runtime != documented:
            errors.append({"rule": "design.mirror-drift", "token": mirror["token"],
                           "designPath": mirror["designPath"], "runtime": runtime, "documented": documented})
    defined = {token for declarations in actual.values() for token in declarations}
    inspected = []
    color_literal = re.compile(r"#[0-9a-fA-F]{3,8}\b|\b(?:rgba?|hsla?|oklch|oklab)\s*\(")
    for relative in mapping["pageAdapters"]:
        path = ROOT / relative
        inspected.append(relative)
        for selector, body in css_rules(path):
            for match in re.finditer(r"([\w-]+)\s*:\s*([^;{}]+)(?:;|$)", body):
                prop, value = match.group(1), match.group(2).strip()
                if prop.startswith("--app-"):
                    errors.append({"rule": "page.canonical-redefinition", "file": relative,
                                   "selector": selector, "property": prop})
                if color_literal.search(value) or re.search(r"\b(?:white|black)\b", value, re.I):
                    errors.append({"rule": "page.raw-color", "file": relative,
                                   "selector": selector, "property": prop, "value": value})
                for token in re.findall(r"var\(\s*(--app-[\w-]+)", value):
                    if token not in defined:
                        errors.append({"rule": "page.unknown-token", "file": relative,
                                       "selector": selector, "token": token})
        # Every legacy alias is an adapter, never a second literal palette.
        for alias, value in re.findall(r"(--(?:creator|hall)-[\w-]+)\s*:\s*([^;{}]+);", path.read_text(encoding="utf-8")):
            if not value.strip().startswith("var(--app-"):
                errors.append({"rule": "page.literal-adapter", "file": relative, "alias": alias, "value": value.strip()})
    return {"schemaVersion": 1, "check": "tokenDrift", "ownershipModel": "B",
            "canonical": mapping["canonicalStylesheet"], "adapters": inspected,
            "selectors": len(actual), "runtimeDeclarations": sum(map(len, actual.values())),
            "designMirrors": len(mapping["designMirrors"]), "passed": not errors,
            "errors": errors,
            "limits": "Static token ownership only; browser contrast, focus, popup and cascade verification remain separate."}


if __name__ == "__main__":
    try:
        report = check()
    except (OSError, ValueError, KeyError, TypeError) as error:
        report = {"schemaVersion": 1, "check": "tokenDrift", "passed": False,
                  "errors": [{"rule": "configuration.unreadable", "message": str(error)}]}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    sys.exit(0 if report["passed"] else 1)
