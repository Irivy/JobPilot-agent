"""Integration tests for local project scanning and evidence extraction."""

from __future__ import annotations

from pathlib import Path

from app.providers import LocalProjectFilesProvider
from app.schemas import (
    EvidenceScanResult,
    EvidenceScanSuccess,
    InspectProjectEvidenceInput,
)
from app.tools import inspect_project_evidence
from pydantic import TypeAdapter


def test_local_project_provider_and_evidence_tool_end_to_end(tmp_path: Path) -> None:
    source_directory = tmp_path / "src"
    source_directory.mkdir()
    source = source_directory / "service.py"
    source.write_text(
        "from fastapi import FastAPI\n\napp = FastAPI()\n",
        encoding="utf-8",
    )
    readme = tmp_path / "README.md"
    readme.write_text(
        "# Demo\n\n这是一个数据分析服务。\n",
        encoding="utf-8",
    )
    config = tmp_path / "settings.toml"
    config.write_text(
        'api_key = "do-not-expose"\nframework = "Fast API"\n',
        encoding="utf-8",
    )
    snapshots = {
        path.relative_to(tmp_path).as_posix(): (
            path.read_bytes(),
            path.stat().st_mtime_ns,
        )
        for path in (source, readme, config)
    }
    tool_input = InspectProjectEvidenceInput(
        project_path=str(tmp_path),
        skills_to_verify=["FastAPI", "数据分析"],
        keywords=["framework"],
        max_files=20,
        allowed_extensions=["py", "md", "toml"],
    )
    provider = LocalProjectFilesProvider()

    first = inspect_project_evidence(tool_input, provider=provider)
    second = inspect_project_evidence(tool_input, provider=provider)

    assert isinstance(first, EvidenceScanSuccess)
    assert isinstance(second, EvidenceScanSuccess)
    validated = TypeAdapter(EvidenceScanResult).validate_python(
        TypeAdapter(EvidenceScanResult).dump_python(first, mode="json")
    )
    assert validated == first
    assert first.files_scanned == 3
    assert len(first.evidence_hits) >= 3
    assert [item.evidence_id for item in first.evidence_hits] == [
        item.evidence_id for item in second.evidence_hits
    ]
    assert all(
        not Path(item.locator or "").is_absolute()
        for item in first.evidence_hits
    )
    serialized_evidence = "\n".join(
        item.model_dump_json() for item in first.evidence_hits
    )
    assert "do-not-expose" not in serialized_evidence
    assert str(tmp_path.resolve()) not in serialized_evidence
    assert not hasattr(first, "agent_state")

    for relative_path, (content, mtime_ns) in snapshots.items():
        path = tmp_path / relative_path
        assert path.read_bytes() == content
        assert path.stat().st_mtime_ns == mtime_ns
