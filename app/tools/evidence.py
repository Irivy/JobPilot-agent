"""Deterministic evidence extraction from Provider-supplied project files."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from app.providers.project_files import (
    ProjectFile,
    ProjectFileIssue,
    ProjectFilesProvider,
    ProjectFilesScan,
    ProjectFilesUnreadableError,
    ProjectPathNotAccessibleError,
    ProjectPathNotFoundError,
)
from app.schemas.base import JsonValue
from app.schemas.common import ToolError, ToolWarning
from app.schemas.evidence import EvidenceConfidence, EvidenceItem, EvidenceSourceType
from app.schemas.tool_inputs import InspectProjectEvidenceInput
from app.schemas.tool_outputs import EvidenceScanResult, EvidenceScanSuccess, ToolFailure

_CAMEL_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
_ACRONYM_BOUNDARY = re.compile(r"(?<=[A-Z])(?=[A-Z][a-z])")
_SECRET_ASSIGNMENT = re.compile(
    r"(?i)((?:[\"']?)(?:password|secret|token|api[_-]?key|access[_-]?key|"
    r"private[_-]?key)(?:[\"']?)\s*[:=]\s*).*$"
)
_DOCUMENT_EXTENSIONS = {".adoc", ".md", ".rst", ".txt"}
_CONFIG_EXTENSIONS = {
    ".cfg",
    ".conf",
    ".ini",
    ".json",
    ".properties",
    ".toml",
    ".xml",
    ".yaml",
    ".yml",
}
_MAX_EVIDENCE_PER_TARGET = 5
_MAX_EVIDENCE_TOTAL = 50
_MAX_EXCERPT_LENGTH = 600
_MAX_EXCERPT_LINE_LENGTH = 180
_NO_LINE_SENTINEL = 0
_ERROR_ISSUE_CODES = {
    "project_file_decode_failed",
    "project_file_unreadable",
}
_ISSUE_MESSAGES = {
    "binary_file_skipped": "Binary project files were skipped.",
    "project_file_decode_failed": "Some project files were not valid UTF-8.",
    "project_file_truncated": "Some project files were scanned only as bounded prefixes.",
    "project_file_unreadable": "Some project files could not be read.",
    "scan_limit_exceeded": "Project scanning stopped at a configured resource limit.",
    "sensitive_file_skipped": "Potentially sensitive project files were skipped.",
    "unsafe_symlink_skipped": "Unsafe or unsupported symbolic links were skipped.",
}


@dataclass(frozen=True, slots=True)
class _Target:
    target_type: str
    display_text: str
    normalized_text: str


@dataclass(frozen=True, slots=True)
class _Match:
    target: _Target
    project_file: ProjectFile
    match_kind: str
    match_rank: int
    line_number: int | None
    matched_line: str
    occurrence_count: int


def _normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value)
    normalized = _ACRONYM_BOUNDARY.sub(" ", normalized)
    normalized = _CAMEL_BOUNDARY.sub(" ", normalized)
    characters: list[str] = []
    for character in normalized:
        if character in {"+", "#"}:
            characters.append(character)
        elif (
            character in {"_", "-", "/", "\\"}
            or unicodedata.category(character).startswith(("P", "Z"))
        ):
            characters.append(" ")
        else:
            characters.append(character)
    return " ".join("".join(characters).split()).casefold().strip()


def _targets(tool_input: InspectProjectEvidenceInput) -> tuple[_Target, ...]:
    targets: list[_Target] = []
    seen: set[str] = set()
    for skill in tool_input.skills_to_verify:
        normalized = _normalize_text(skill)
        if normalized and normalized not in seen:
            targets.append(
                _Target(
                    target_type="skill",
                    display_text=skill.strip(),
                    normalized_text=normalized,
                )
            )
            seen.add(normalized)
    for keyword in tool_input.keywords:
        normalized = _normalize_text(keyword)
        if normalized and normalized not in seen:
            targets.append(
                _Target(
                    target_type="keyword",
                    display_text=keyword.strip(),
                    normalized_text=normalized,
                )
            )
            seen.add(normalized)
    return tuple(targets)


def _contains_cjk(value: str) -> bool:
    return any(
        "\u3400" <= character <= "\u4dbf"
        or "\u4e00" <= character <= "\u9fff"
        for character in value
    )


def _is_short_latin_target(value: str) -> bool:
    return len(value) <= 2 and value.isascii() and value.isalpha()


def _token_pattern(target: str) -> re.Pattern[str]:
    return re.compile(rf"(?<![\w+#]){re.escape(target)}(?![\w+#])")


def _file_category(project_file: ProjectFile) -> str:
    name = PurePosixPath(project_file.relative_path).name.casefold()
    if project_file.extension in _DOCUMENT_EXTENSIONS or name.startswith("readme"):
        return "documentation"
    if project_file.extension in _CONFIG_EXTENSIONS:
        return "config"
    return "source"


def _path_matches(project_file: ProjectFile, target: _Target) -> bool:
    path = PurePosixPath(project_file.relative_path)
    components = list(path.parts[:-1])
    components.append(PurePosixPath(path.name).stem)
    return any(
        _normalize_text(component) == target.normalized_text
        for component in components
    )


def _find_match(project_file: ProjectFile, target: _Target) -> _Match | None:
    category = _file_category(project_file)
    token_pattern = _token_pattern(target.normalized_text)
    content_matches: list[tuple[int, str, int, str]] = []
    total_occurrences = 0

    for line_number, line in enumerate(project_file.content.splitlines(), start=1):
        normalized_line = _normalize_text(line)
        if not normalized_line:
            continue
        if _contains_cjk(target.normalized_text):
            token_count = normalized_line.count(target.normalized_text)
        else:
            token_count = len(token_pattern.findall(normalized_line))
        substring_count = normalized_line.count(target.normalized_text)
        if token_count:
            rank = 1 if category == "documentation" else 0
            kind = (
                "documentation_token"
                if category == "documentation"
                else f"{category}_token"
            )
            content_matches.append((rank, kind, line_number, line))
            total_occurrences += (
                token_count
                if _is_short_latin_target(target.normalized_text)
                else substring_count
            )
            continue

        if (
            not _is_short_latin_target(target.normalized_text)
            and substring_count
        ):
            content_matches.append((3, "content_substring", line_number, line))
            total_occurrences += substring_count

    path_match = _path_matches(project_file, target)
    if path_match:
        total_occurrences += 1
    candidates = list(content_matches)
    if path_match:
        candidates.append((2, "path_exact", _NO_LINE_SENTINEL, project_file.relative_path))
    if not candidates:
        return None

    rank, kind, line_number, matched_line = min(
        candidates,
        key=lambda match: (match[0], match[2], match[1]),
    )
    return _Match(
        target=target,
        project_file=project_file,
        match_kind=kind,
        match_rank=rank,
        line_number=None if kind == "path_exact" else line_number,
        matched_line=matched_line,
        occurrence_count=total_occurrences,
    )


def _evidence_id(match: _Match, project_root_digest: str) -> str:
    normalized_match_line = _normalize_text(match.matched_line)
    line_digest = hashlib.sha256(normalized_match_line.encode("utf-8")).hexdigest()
    fields = (
        "jobpilot-project-evidence-v1",
        project_root_digest,
        match.project_file.relative_path,
        match.target.target_type,
        match.target.normalized_text,
        match.match_kind,
        str(match.line_number) if match.line_number is not None else "path",
        line_digest,
    )
    digest = hashlib.sha256("\0".join(fields).encode("utf-8")).hexdigest()
    return f"pe-{digest[:32]}"


def _redact_line(line: str) -> str:
    return _SECRET_ASSIGNMENT.sub(r"\1<redacted>", line)


def _truncate_line(line: str) -> str:
    if len(line) <= _MAX_EXCERPT_LINE_LENGTH:
        return line
    return f"{line[: _MAX_EXCERPT_LINE_LENGTH - 1]}…"


def _excerpt(match: _Match) -> tuple[str, str, int | None, int | None]:
    relative_path = match.project_file.relative_path
    if match.line_number is None:
        return (
            f"Path match: {relative_path}",
            f"{relative_path}:path",
            None,
            None,
        )

    lines = match.project_file.content.splitlines()
    matched_index = match.line_number - 1
    line_start = max(0, matched_index - 1)
    line_end = min(len(lines), matched_index + 2)
    excerpt_lines = [
        f"{index + 1}: {_truncate_line(_redact_line(lines[index]))}"
        for index in range(line_start, line_end)
    ]
    excerpt = "\n".join(excerpt_lines)
    if len(excerpt) > _MAX_EXCERPT_LENGTH:
        excerpt = f"{excerpt[: _MAX_EXCERPT_LENGTH - 1]}…"
    actual_start = line_start + 1
    actual_end = line_end
    return (
        excerpt,
        f"{relative_path}:L{actual_start}-L{actual_end}",
        actual_start,
        actual_end,
    )


def _to_evidence(
    match: _Match,
    *,
    project_root_digest: str,
    source_label: str,
) -> EvidenceItem:
    excerpt, locator, line_start, line_end = _excerpt(match)
    confidence = (
        EvidenceConfidence.MEDIUM
        if match.match_kind in {"source_token", "config_token"}
        else EvidenceConfidence.LOW
    )
    metadata: dict[str, JsonValue] = {
        "target_type": match.target.target_type,
        "target": match.target.display_text,
        "normalized_target": match.target.normalized_text,
        "match_kind": match.match_kind,
        "relative_path": match.project_file.relative_path,
        "line_start": line_start,
        "line_end": line_end,
        "extension": match.project_file.extension,
        "occurrence_count": match.occurrence_count,
        "file_truncated": match.project_file.truncated,
    }
    return EvidenceItem(
        evidence_id=_evidence_id(match, project_root_digest),
        source_type=EvidenceSourceType.PROJECT,
        source_label=source_label,
        excerpt=excerpt,
        locator=locator,
        confidence=confidence,
        related_skills=(
            [match.target.display_text] if match.target.target_type == "skill" else []
        ),
        related_requirement_ids=[],
        metadata=metadata,
    )


def _issue_context(issues: list[ProjectFileIssue]) -> dict[str, JsonValue]:
    samples: list[str] = []
    categories: set[str] = set()
    count = 0
    for issue in issues:
        count += issue.count
        categories.update(issue.category.split(","))
        for sample in issue.sample_relative_paths:
            if sample not in samples and len(samples) < 5:
                samples.append(sample)
    context: dict[str, JsonValue] = {"count": count}
    if samples:
        sample_values: list[JsonValue] = [sample for sample in samples]
        context["sample_relative_paths"] = sample_values
    if categories:
        category_values: list[JsonValue] = [
            category for category in sorted(categories)
        ]
        context["categories"] = category_values
    return context


def _map_scan_issues(
    scan: ProjectFilesScan,
) -> tuple[list[ToolWarning], list[ToolError]]:
    grouped: dict[str, list[ProjectFileIssue]] = {}
    for issue in scan.issues:
        grouped.setdefault(issue.code, []).append(issue)

    warnings: list[ToolWarning] = []
    errors: list[ToolError] = []
    for code in sorted(grouped):
        issues = grouped[code]
        message = _ISSUE_MESSAGES.get(code, "Project scan reported a recoverable issue.")
        context = _issue_context(issues)
        if code in _ERROR_ISSUE_CODES:
            errors.append(
                ToolError(
                    code=code,
                    message=message,
                    recoverable=True,
                    context=context,
                )
            )
        else:
            warnings.append(
                ToolWarning(
                    code=code,
                    message=message,
                    context=context,
                )
            )
    return warnings, errors


def _failure(
    *,
    code: str,
    message: str,
    category: str,
    context: dict[str, JsonValue] | None = None,
) -> ToolFailure:
    error_context: dict[str, JsonValue] = {"category": category}
    if context:
        error_context.update(context)
    return ToolFailure(
        errors=[
            ToolError(
                code=code,
                message=message,
                recoverable=True,
                context=error_context,
            )
        ]
    )


def inspect_project_evidence(
    tool_input: InspectProjectEvidenceInput,
    *,
    provider: ProjectFilesProvider,
) -> EvidenceScanResult:
    """Inspect a Provider-supplied project snapshot for deterministic evidence."""

    try:
        scan = provider.scan_files(
            Path(tool_input.project_path),
            allowed_extensions=tuple(tool_input.allowed_extensions),
            max_files=tool_input.max_files,
        )
    except ProjectPathNotFoundError:
        return _failure(
            code="project_path_not_found",
            message="The authorized project path was not found.",
            category="not_found",
        )
    except ProjectPathNotAccessibleError as exc:
        return _failure(
            code="project_path_not_accessible",
            message="The authorized project path could not be scanned.",
            category=exc.category,
        )
    except ProjectFilesUnreadableError as exc:
        return _failure(
            code="project_files_unreadable",
            message="All candidate project files were unreadable.",
            category="all_files_unreadable",
            context={
                "files_attempted": exc.files_attempted,
                **_issue_context(list(exc.issues)),
            },
        )

    warnings, errors = _map_scan_issues(scan)
    all_matches = [
        match
        for project_file in scan.files
        for target in _targets(tool_input)
        if (match := _find_match(project_file, target)) is not None
    ]
    source_label = Path(tool_input.project_path).name or "project"
    evidence_with_matches = [
        (
            match,
            _to_evidence(
                match,
                project_root_digest=scan.project_root_digest,
                source_label=source_label,
            ),
        )
        for match in all_matches
    ]
    evidence_with_matches.sort(
        key=lambda pair: (
            pair[0].match_rank,
            0 if pair[0].target.target_type == "skill" else 1,
            pair[0].target.normalized_text,
            pair[0].project_file.relative_path.casefold(),
            pair[0].project_file.relative_path,
            pair[0].line_number
            if pair[0].line_number is not None
            else _NO_LINE_SENTINEL,
            pair[1].evidence_id,
        )
    )

    selected: list[EvidenceItem] = []
    target_counts: dict[tuple[str, str], int] = {}
    evidence_limit_reached = False
    for match, evidence in evidence_with_matches:
        target_key = (match.target.target_type, match.target.normalized_text)
        if target_counts.get(target_key, 0) >= _MAX_EVIDENCE_PER_TARGET:
            evidence_limit_reached = True
            continue
        if len(selected) >= _MAX_EVIDENCE_TOTAL:
            evidence_limit_reached = True
            break
        selected.append(evidence)
        target_counts[target_key] = target_counts.get(target_key, 0) + 1

    if evidence_limit_reached:
        warnings.append(
            ToolWarning(
                code="evidence_limit_reached",
                message="Project evidence was truncated at the deterministic output limit.",
                context={
                    "max_per_target": _MAX_EVIDENCE_PER_TARGET,
                    "max_total": _MAX_EVIDENCE_TOTAL,
                },
            )
        )
    if not scan.files:
        warnings.append(
            ToolWarning(
                code="no_scannable_project_files",
                message="No project files could participate in evidence matching.",
            )
        )
    elif not selected:
        warnings.append(
            ToolWarning(
                code="no_project_evidence",
                message="No project evidence matched the requested targets.",
            )
        )
    if scan.truncated and not any(
        warning.code in {"project_file_truncated", "scan_limit_exceeded"}
        for warning in warnings
    ):
        warnings.append(
            ToolWarning(
                code="scan_limit_exceeded",
                message="Project scanning stopped at a configured resource limit.",
                context={"categories": ["provider_limit"]},
            )
        )

    warnings.sort(key=lambda warning: warning.code)
    errors.sort(key=lambda error: error.code)
    return EvidenceScanSuccess(
        project_path=tool_input.project_path,
        evidence_hits=selected,
        files_scanned=len(scan.files),
        truncated=scan.truncated or evidence_limit_reached,
        warnings=warnings,
        errors=errors,
    )
