"""Unit tests for deterministic project-evidence extraction."""

from __future__ import annotations

import builtins
import socket
from pathlib import Path

import pytest
from app.providers.project_files import (
    ProjectFile,
    ProjectFileIssue,
    ProjectFilesScan,
    ProjectFilesUnreadableError,
    ProjectPathNotAccessibleError,
    ProjectPathNotFoundError,
)
from app.schemas import (
    EvidenceConfidence,
    EvidenceScanResult,
    EvidenceScanSuccess,
    InspectProjectEvidenceInput,
    ToolFailure,
)
from app.tools import inspect_project_evidence
from pydantic import TypeAdapter


class FakeProvider:
    def __init__(
        self,
        result: ProjectFilesScan | Exception,
    ) -> None:
        self.result = result
        self.calls: list[tuple[Path, tuple[str, ...], int]] = []

    def scan_files(
        self,
        project_path: Path,
        *,
        allowed_extensions: tuple[str, ...],
        max_files: int,
    ) -> ProjectFilesScan:
        self.calls.append((project_path, allowed_extensions, max_files))
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def project_file(
    relative_path: str,
    content: str,
    *,
    truncated: bool = False,
) -> ProjectFile:
    encoded = content.encode("utf-8")
    return ProjectFile(
        relative_path=relative_path,
        extension=PurePathHelper.suffix(relative_path),
        content=content,
        size_bytes=len(encoded),
        bytes_read=len(encoded),
        truncated=truncated,
    )


class PurePathHelper:
    @staticmethod
    def suffix(relative_path: str) -> str:
        return Path(relative_path).suffix.casefold()


def scan(
    *files: ProjectFile,
    root_digest: str = "root-a",
    truncated: bool = False,
    issues: tuple[ProjectFileIssue, ...] = (),
    files_attempted: int | None = None,
) -> ProjectFilesScan:
    return ProjectFilesScan(
        files=files,
        files_attempted=len(files) if files_attempted is None else files_attempted,
        truncated=truncated,
        issues=issues,
        project_root_digest=root_digest,
    )


def tool_input(
    *,
    skills: list[str] | None = None,
    keywords: list[str] | None = None,
    project_path: str = "demo-project",
    max_files: int = 200,
) -> InspectProjectEvidenceInput:
    return InspectProjectEvidenceInput(
        project_path=project_path,
        skills_to_verify=skills or [],
        keywords=keywords or [],
        max_files=max_files,
        allowed_extensions=["py", "toml", "md", "txt"],
    )


def run_tool(
    provider_scan: ProjectFilesScan | Exception,
    *,
    skills: list[str] | None = None,
    keywords: list[str] | None = None,
    project_path: str = "demo-project",
) -> EvidenceScanSuccess | ToolFailure:
    return inspect_project_evidence(
        tool_input(
            skills=skills,
            keywords=keywords,
            project_path=project_path,
        ),
        provider=FakeProvider(provider_scan),
    )


@pytest.mark.parametrize(
    ("target", "content", "expected_kind"),
    [
        ("FastAPI", "from fastapi import FastAPI", "source_token"),
        ("Fast API", "framework = 'Fast API'", "source_token"),
        ("数据分析", "实现数据分析流水线", "source_token"),
        ("job pilot", "job_pilot = True", "source_token"),
        ("job pilot", "jobPilot = True", "source_token"),
        ("http server", "class HTTPServer:", "source_token"),
        ("job pilot", "job-pilot = true", "source_token"),
        ("C++", "languages = ['C++']", "source_token"),
        ("C#", "languages = ['C#']", "source_token"),
    ],
)
def test_content_normalization_and_complete_token_matching(
    target: str,
    content: str,
    expected_kind: str,
) -> None:
    result = run_tool(
        scan(project_file("src/main.py", content)),
        skills=[target],
    )

    assert isinstance(result, EvidenceScanSuccess)
    assert len(result.evidence_hits) == 1
    assert result.evidence_hits[0].metadata["match_kind"] == expected_kind
    assert result.evidence_hits[0].confidence is EvidenceConfidence.MEDIUM


def test_config_complete_phrase_is_medium_confidence() -> None:
    result = run_tool(
        scan(project_file("pyproject.toml", 'framework = "Fast API"')),
        skills=["Fast API"],
    )

    assert isinstance(result, EvidenceScanSuccess)
    assert result.evidence_hits[0].metadata["match_kind"] == "config_token"
    assert result.evidence_hits[0].confidence is EvidenceConfidence.MEDIUM


def test_readme_match_is_low_confidence() -> None:
    result = run_tool(
        scan(project_file("README.md", "Built with FastAPI")),
        skills=["FastAPI"],
    )

    assert isinstance(result, EvidenceScanSuccess)
    assert result.evidence_hits[0].metadata["match_kind"] == "documentation_token"
    assert result.evidence_hits[0].confidence is EvidenceConfidence.LOW


def test_exact_path_component_match_omits_file_content() -> None:
    result = run_tool(
        scan(project_file("src/router/handlers.py", "nothing relevant")),
        skills=["router"],
    )

    assert isinstance(result, EvidenceScanSuccess)
    evidence = result.evidence_hits[0]
    assert evidence.metadata["match_kind"] == "path_exact"
    assert evidence.excerpt == "Path match: src/router/handlers.py"
    assert evidence.locator == "src/router/handlers.py:path"
    assert evidence.confidence is EvidenceConfidence.LOW


def test_file_extension_is_not_a_skill_match() -> None:
    result = run_tool(
        scan(project_file("main.py", "nothing relevant")),
        skills=["py"],
    )

    assert isinstance(result, EvidenceScanSuccess)
    assert result.evidence_hits == []


def test_short_latin_target_does_not_use_arbitrary_substring() -> None:
    result = run_tool(
        scan(project_file("main.py", "concatenate values")),
        skills=["C"],
    )

    assert isinstance(result, EvidenceScanSuccess)
    assert result.evidence_hits == []


def test_short_latin_target_can_match_independent_token() -> None:
    result = run_tool(
        scan(project_file("main.py", "language = C")),
        skills=["C"],
    )

    assert isinstance(result, EvidenceScanSuccess)
    assert len(result.evidence_hits) == 1


def test_skill_wins_when_normalized_keyword_is_duplicate() -> None:
    result = run_tool(
        scan(project_file("main.py", "Python")),
        skills=[" Python "],
        keywords=["python"],
    )

    assert isinstance(result, EvidenceScanSuccess)
    assert len(result.evidence_hits) == 1
    assert result.evidence_hits[0].related_skills == ["Python"]
    assert result.evidence_hits[0].metadata["target_type"] == "skill"


def test_keyword_evidence_has_no_related_skills() -> None:
    result = run_tool(
        scan(project_file("main.py", "workflow orchestration")),
        keywords=["orchestration"],
    )

    assert isinstance(result, EvidenceScanSuccess)
    assert result.evidence_hits[0].related_skills == []
    assert result.evidence_hits[0].related_requirement_ids == []


def test_repeated_target_in_one_file_is_merged_and_counted() -> None:
    result = run_tool(
        scan(project_file("main.py", "Python\nnone\nPython and Python")),
        skills=["Python"],
    )

    assert isinstance(result, EvidenceScanSuccess)
    assert len(result.evidence_hits) == 1
    assert result.evidence_hits[0].metadata["occurrence_count"] == 3
    assert result.evidence_hits[0].metadata["line_start"] == 1


def test_occurrence_count_includes_lower_quality_hits_on_token_line() -> None:
    result = run_tool(
        scan(project_file("main.py", "Python and pythonic")),
        skills=["Python"],
    )

    assert isinstance(result, EvidenceScanSuccess)
    assert len(result.evidence_hits) == 1
    assert result.evidence_hits[0].metadata["match_kind"] == "source_token"
    assert result.evidence_hits[0].metadata["occurrence_count"] == 2


def test_one_file_can_produce_evidence_for_multiple_skills() -> None:
    result = run_tool(
        scan(project_file("main.py", "Python\nFastAPI")),
        skills=["Python", "FastAPI"],
    )

    assert isinstance(result, EvidenceScanSuccess)
    assert {item.related_skills[0] for item in result.evidence_hits} == {
        "FastAPI",
        "Python",
    }


def test_content_token_is_preferred_over_path_match() -> None:
    result = run_tool(
        scan(project_file("python/module.py", "Python is used here")),
        skills=["Python"],
    )

    assert isinstance(result, EvidenceScanSuccess)
    assert result.evidence_hits[0].metadata["match_kind"] == "source_token"
    assert result.evidence_hits[0].locator == "python/module.py:L1-L1"


def test_same_quality_uses_earliest_line() -> None:
    result = run_tool(
        scan(project_file("main.py", "zero\nPython\nPython")),
        skills=["Python"],
    )

    assert isinstance(result, EvidenceScanSuccess)
    assert result.evidence_hits[0].metadata["line_start"] == 1
    assert result.evidence_hits[0].locator == "main.py:L1-L3"


def test_evidence_is_limited_to_five_per_target() -> None:
    files = tuple(
        project_file(f"{index}.py", "Python") for index in range(6)
    )
    result = run_tool(scan(*files), skills=["Python"])

    assert isinstance(result, EvidenceScanSuccess)
    assert len(result.evidence_hits) == 5
    assert result.truncated
    assert "evidence_limit_reached" in {
        warning.code for warning in result.warnings
    }


def test_total_evidence_is_limited_to_fifty() -> None:
    targets = [f"skill{index}" for index in range(51)]
    files = tuple(
        project_file(f"{index:02}.py", target)
        for index, target in enumerate(targets)
    )
    result = run_tool(scan(*files), skills=targets)

    assert isinstance(result, EvidenceScanSuccess)
    assert len(result.evidence_hits) == 50
    assert result.truncated


def test_final_sort_is_deterministic() -> None:
    provider_scan = scan(
        project_file("z.py", "Python"),
        project_file("a.py", "Python"),
        project_file("README.md", "FastAPI"),
    )
    first = run_tool(provider_scan, skills=["Python", "FastAPI"])
    second = run_tool(provider_scan, skills=["Python", "FastAPI"])

    assert isinstance(first, EvidenceScanSuccess)
    assert isinstance(second, EvidenceScanSuccess)
    assert [item.evidence_id for item in first.evidence_hits] == [
        item.evidence_id for item in second.evidence_hits
    ]
    assert [item.metadata["relative_path"] for item in first.evidence_hits] == [
        "a.py",
        "z.py",
        "README.md",
    ]


def test_excerpt_has_context_actual_line_range_and_bounded_length() -> None:
    long_context = "x" * 500
    result = run_tool(
        scan(
            project_file(
                "main.py",
                f"{long_context}\nPython\n{long_context}\nafter",
            )
        ),
        skills=["Python"],
    )

    assert isinstance(result, EvidenceScanSuccess)
    evidence = result.evidence_hits[0]
    assert evidence.locator == "main.py:L1-L3"
    assert evidence.excerpt.startswith("1: ")
    assert "\n2: Python\n" in evidence.excerpt
    assert len(evidence.excerpt) <= 600


@pytest.mark.parametrize(
    ("line", "secret_value"),
    [
        ("password = hunter2", "hunter2"),
        ("secret: value", "value"),
        ("token='abc'", "abc"),
        ('api_key = "api-secret"', "api-secret"),
        ("access-key: access-secret", "access-secret"),
        ("private_key = private-secret", "private-secret"),
        ('"api_key": "json-secret"', "json-secret"),
        ("'token': 'mapping-secret'", "mapping-secret"),
    ],
)
def test_excerpt_redacts_common_secret_assignments(
    line: str,
    secret_value: str,
) -> None:
    result = run_tool(
        scan(project_file("main.py", f"{line}\nPython")),
        skills=["Python"],
    )

    assert isinstance(result, EvidenceScanSuccess)
    excerpt = result.evidence_hits[0].excerpt
    assert "<redacted>" in excerpt
    assert secret_value not in excerpt


def test_evidence_id_is_stable_and_uses_project_digest() -> None:
    project = project_file("main.py", "Python")
    first = run_tool(scan(project, root_digest="root-a"), skills=["Python"])
    second = run_tool(scan(project, root_digest="root-a"), skills=["Python"])
    other_project = run_tool(
        scan(project, root_digest="root-b"),
        skills=["Python"],
    )

    assert isinstance(first, EvidenceScanSuccess)
    assert isinstance(second, EvidenceScanSuccess)
    assert isinstance(other_project, EvidenceScanSuccess)
    assert first.evidence_hits[0].evidence_id == second.evidence_hits[0].evidence_id
    assert first.evidence_hits[0].evidence_id != other_project.evidence_hits[0].evidence_id
    assert first.evidence_hits[0].evidence_id.startswith("pe-")
    assert len(first.evidence_hits[0].evidence_id) == 35


def test_evidence_id_varies_by_file_and_target() -> None:
    result = run_tool(
        scan(
            project_file("a.py", "Python FastAPI"),
            project_file("b.py", "Python"),
        ),
        skills=["Python", "FastAPI"],
    )

    assert isinstance(result, EvidenceScanSuccess)
    ids = {item.evidence_id for item in result.evidence_hits}
    assert len(ids) == 3


def test_match_line_change_changes_id_but_context_change_does_not() -> None:
    base = run_tool(
        scan(project_file("main.py", "context one\nPython")),
        skills=["Python"],
    )
    context_changed = run_tool(
        scan(project_file("main.py", "context two\nPython")),
        skills=["Python"],
    )
    match_changed = run_tool(
        scan(project_file("main.py", "context one\nPython framework")),
        skills=["Python"],
    )

    assert isinstance(base, EvidenceScanSuccess)
    assert isinstance(context_changed, EvidenceScanSuccess)
    assert isinstance(match_changed, EvidenceScanSuccess)
    assert base.evidence_hits[0].evidence_id == context_changed.evidence_hits[0].evidence_id
    assert base.evidence_hits[0].evidence_id != match_changed.evidence_hits[0].evidence_id


def test_no_match_is_success_with_warning() -> None:
    result = run_tool(
        scan(project_file("main.py", "Ruby")),
        skills=["Python"],
    )

    assert isinstance(result, EvidenceScanSuccess)
    assert result.evidence_hits == []
    assert "no_project_evidence" in {warning.code for warning in result.warnings}


def test_no_scannable_files_is_success_with_warning() -> None:
    result = run_tool(scan(), skills=["Python"])

    assert isinstance(result, EvidenceScanSuccess)
    assert result.files_scanned == 0
    assert "no_scannable_project_files" in {
        warning.code for warning in result.warnings
    }


def test_partial_file_failure_is_success_with_recoverable_error() -> None:
    issue = ProjectFileIssue(
        code="project_file_unreadable",
        category="file_read",
        relative_path="bad.py",
        recoverable=True,
        count=3,
        sample_relative_paths=("bad.py", "worse.py"),
    )
    result = run_tool(
        scan(project_file("ok.py", "Python"), issues=(issue,), files_attempted=4),
        skills=["Python"],
    )

    assert isinstance(result, EvidenceScanSuccess)
    assert result.errors[0].code == "project_file_unreadable"
    assert result.errors[0].recoverable
    assert result.errors[0].context["count"] == 3
    assert result.errors[0].context["sample_relative_paths"] == [
        "bad.py",
        "worse.py",
    ]


def test_provider_warnings_are_aggregated_by_code() -> None:
    issues = (
        ProjectFileIssue(
            code="unsafe_symlink_skipped",
            category="outside_root",
            relative_path="one.py",
            recoverable=True,
            count=2,
            sample_relative_paths=("one.py",),
        ),
        ProjectFileIssue(
            code="unsafe_symlink_skipped",
            category="broken",
            relative_path="two.py",
            recoverable=True,
            count=1,
            sample_relative_paths=("two.py",),
        ),
    )
    result = run_tool(scan(issues=issues), skills=["Python"])

    assert isinstance(result, EvidenceScanSuccess)
    warning = next(
        warning
        for warning in result.warnings
        if warning.code == "unsafe_symlink_skipped"
    )
    assert warning.context["count"] == 3
    assert warning.context["categories"] == ["broken", "outside_root"]


def test_all_candidate_files_unreadable_returns_recoverable_failure() -> None:
    issue = ProjectFileIssue(
        code="project_file_decode_failed",
        category="utf8_decode",
        relative_path="legacy.py",
        recoverable=True,
        sample_relative_paths=("legacy.py",),
    )
    error = ProjectFilesUnreadableError(files_attempted=1, issues=(issue,))
    result = run_tool(error, skills=["Python"])

    assert isinstance(result, ToolFailure)
    assert result.errors[0].code == "project_files_unreadable"
    assert result.errors[0].recoverable
    assert result.errors[0].context["files_attempted"] == 1


def test_missing_root_returns_recoverable_failure() -> None:
    result = run_tool(
        ProjectPathNotFoundError(Path("private/absolute/path")),
        skills=["Python"],
    )

    assert isinstance(result, ToolFailure)
    assert result.errors[0].code == "project_path_not_found"
    assert result.errors[0].recoverable
    assert "private" not in str(result.model_dump())


@pytest.mark.parametrize("category", ["not_directory", "root_list_failed"])
def test_inaccessible_root_returns_recoverable_failure(category: str) -> None:
    result = run_tool(
        ProjectPathNotAccessibleError(Path("private/path"), category=category),
        skills=["Python"],
    )

    assert isinstance(result, ToolFailure)
    assert result.errors[0].code == "project_path_not_accessible"
    assert result.errors[0].recoverable
    assert result.errors[0].context["category"] == category


def test_scan_limit_is_success_and_explains_truncation() -> None:
    issue = ProjectFileIssue(
        code="scan_limit_exceeded",
        category="max_files",
        relative_path=None,
        recoverable=True,
    )
    result = run_tool(
        scan(
            project_file("main.py", "Python", truncated=True),
            truncated=True,
            issues=(issue,),
        ),
        skills=["Python"],
    )

    assert isinstance(result, EvidenceScanSuccess)
    assert result.truncated
    assert "scan_limit_exceeded" in {warning.code for warning in result.warnings}


def test_result_round_trips_through_evidence_scan_adapter() -> None:
    result = run_tool(
        scan(project_file("main.py", "Python")),
        skills=["Python"],
    )
    adapter = TypeAdapter(EvidenceScanResult)

    validated = adapter.validate_python(result)
    round_tripped = adapter.validate_python(adapter.dump_python(validated, mode="json"))

    assert round_tripped == result


def test_tool_delegates_provider_arguments_without_file_system_access(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = FakeProvider(scan(project_file("main.py", "Python")))

    def forbidden_open(*args: object, **kwargs: object) -> object:
        raise AssertionError("Tool accessed the file system")

    def forbidden_network(*args: object, **kwargs: object) -> object:
        raise AssertionError("Tool accessed the network")

    monkeypatch.setattr(builtins, "open", forbidden_open)
    monkeypatch.setattr(socket, "create_connection", forbidden_network)
    result = inspect_project_evidence(
        tool_input(skills=["Python"], max_files=7),
        provider=provider,
    )

    assert isinstance(result, EvidenceScanSuccess)
    assert provider.calls == [
        (Path("demo-project"), (".py", ".toml", ".md", ".txt"), 7)
    ]


def test_warning_error_and_evidence_do_not_leak_absolute_paths() -> None:
    private_root = r"C:\Users\secret\project"
    issue = ProjectFileIssue(
        code="project_file_unreadable",
        category="file_read",
        relative_path="src/bad.py",
        recoverable=True,
        sample_relative_paths=("src/bad.py",),
    )
    result = run_tool(
        scan(project_file("src/main.py", "Python"), issues=(issue,)),
        skills=["Python"],
        project_path=private_root,
    )

    assert isinstance(result, EvidenceScanSuccess)
    serialized_evidence = str(
        {
            "evidence": result.evidence_hits,
            "warnings": result.warnings,
            "errors": result.errors,
        }
    )
    assert private_root not in serialized_evidence
