#!/usr/bin/env python3
"""Validate the owned RuleGo engineering documentation without dependencies."""

from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ENTRY = Path(".trellis/spec/guides/rulego-engineering.md")
GITIGNORE = Path(".gitignore")
REQUIRED_IGNORE_RULES = frozenset({"/tmp/", "__pycache__/", "*.py[cod]"})
REQUIRED = (
    Path("README.md"),
    Path("AGENTS.md"),
    Path(".trellis/spec/guides/index.md"),
    ENTRY,
    Path(".trellis/spec/guides/rulego-ownership.md"),
    Path(".trellis/spec/guides/rulego-capability-design.md"),
    Path(".trellis/spec/guides/rulego-plugin-delivery.md"),
    Path(".trellis/spec/guides/rulego-runtime-verification.md"),
    Path(".trellis/spec/guides/rulego-delivery-workflow.md"),
    Path(".trellis/spec/backend/index.md"),
    Path(".trellis/spec/frontend/index.md"),
)
OWNED_MARKDOWN = (
    Path("README.md"),
    Path("AGENTS.md"),
    *sorted(path.relative_to(ROOT) for path in (ROOT / ".trellis/spec").rglob("*.md")),
)
CREDENTIAL_SCAN_FILES = (
    Path("README.md"),
    Path("AGENTS.md"),
    GITIGNORE,
    *sorted(
        path.relative_to(ROOT)
        for directory, suffixes in (
            (Path(".trellis/spec"), {".md"}),
            (Path(".trellis/tasks/00-bootstrap-guidelines"), {".json", ".jsonl", ".md"}),
            (Path("scripts"), {".py"}),
            (Path(".github/workflows"), {".yaml", ".yml"}),
        )
        for path in (ROOT / directory).rglob("*")
        if path.is_file() and path.suffix in suffixes
    ),
)
ENTRY_POINTS = (
    Path("README.md"),
    Path("AGENTS.md"),
    Path(".trellis/spec/guides/index.md"),
)
SPECIALIZED = REQUIRED[4:9]
LINK_RE = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")
PLACEHOLDER_RE = re.compile(
    r"\b(?:TO" r"DO|T" r"BD|FIX" r"ME|CHANGE" r"ME)\b", re.IGNORECASE
)
CREDENTIAL_RES = (
    re.compile(r"github_" r"pat_[A-Za-z0-9_]+"),
    re.compile(r"\bg" r"hp_[A-Za-z0-9]+"),
    re.compile(r"\bAKIA[A-Z0-9]{16}\b"),
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{12,}"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(
        r"(?i)\b(?:api[_-]?key|access[_-]?token|authorization|password|secret)"
        r"['\"]?\s*[:=]\s*['\"](?!ref://|\$\{|\{\{)[^'\"\r\n]{4,}['\"]"
    ),
    re.compile(
        r"(?im)^\s*(?:api[_-]?key|access[_-]?token|authorization|password|secret)"
        r"\s*[:=]\s*(?!['\"])(?!ref://|\$\{|\{\{)[^\s#]{8,}\s*$"
    ),
)


def relative_links(path: Path, text: str) -> list[str]:
    errors: list[str] = []
    for raw_target in LINK_RE.findall(text):
        target = raw_target.strip().split(maxsplit=1)[0].strip("<>")
        if not target or target.startswith(("#", "http://", "https://", "mailto:")):
            continue
        file_part = target.split("#", 1)[0]
        resolved = (ROOT / path.parent / file_part).resolve()
        try:
            resolved.relative_to(ROOT)
        except ValueError:
            errors.append(f"{path}: link escapes repository: {raw_target}")
            continue
        if not resolved.exists():
            errors.append(f"{path}: missing relative link target: {raw_target}")
    return errors


def main() -> int:
    errors: list[str] = []
    texts: dict[Path, str] = {}

    for path in OWNED_MARKDOWN:
        full_path = ROOT / path
        if full_path.is_file():
            texts[path] = full_path.read_text(encoding="utf-8")

    for path in REQUIRED:
        if path not in texts:
            errors.append(f"missing required file: {path}")

    gitignore_path = ROOT / GITIGNORE
    if not gitignore_path.is_file():
        errors.append(f"missing required file: {GITIGNORE}")
    else:
        ignore_rules = {
            line.strip()
            for line in gitignore_path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        }
        for rule in sorted(REQUIRED_IGNORE_RULES - ignore_rules):
            errors.append(f"{GITIGNORE}: missing required ignore rule: {rule}")

    for path, text in texts.items():
        errors.extend(relative_links(path, text))
        if PLACEHOLDER_RE.search(text):
            errors.append(f"{path}: unresolved placeholder marker")

    for path in CREDENTIAL_SCAN_FILES:
        text = (ROOT / path).read_text(encoding="utf-8")
        for pattern in CREDENTIAL_RES:
            if pattern.search(text):
                errors.append(f"{path}: possible credential value")

    entry_target = ENTRY.as_posix()
    for path in ENTRY_POINTS:
        text = texts.get(path, "")
        relative = Path(".trellis/spec/guides/rulego-engineering.md")
        if path.parent != Path("."):
            relative = Path("rulego-engineering.md")
        if relative.as_posix() not in text:
            errors.append(f"{path}: does not route to {entry_target}")

    entry_text = texts.get(ENTRY, "")
    for path in SPECIALIZED:
        if path.name not in entry_text:
            errors.append(f"{ENTRY}: does not route to {path.name}")

    for layer in (Path(".trellis/spec/backend/index.md"), Path(".trellis/spec/frontend/index.md")):
        text = texts.get(layer, "").lower()
        if "no backend application layer" not in text and "no frontend application layer" not in text:
            errors.append(f"{layer}: documentation-only layer boundary is missing")

    stale_layer_guides = sorted(
        path.relative_to(ROOT)
        for directory in (ROOT / ".trellis/spec/backend", ROOT / ".trellis/spec/frontend")
        for path in directory.glob("*.md")
        if path.name != "index.md"
    )
    for path in stale_layer_guides:
        errors.append(f"irrelevant generated layer guide remains: {path}")

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1

    print(f"Validated {len(texts)} RuleGo engineering documentation files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
