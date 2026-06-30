"""Unit tests for safe local project-file scanning."""

from __future__ import annotations

import errno
import stat
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace

import pytest
from app.providers import (
    LocalProjectFilesProvider,
    ProjectFilesUnreadableError,
    ProjectPathNotAccessibleError,
    ProjectPathNotFoundError,
)
from app.providers.project_files import ProjectFilesScan


def issue_codes(scan: ProjectFilesScan) -> set[str]:
    return {issue.code for issue in scan.issues}


def make_symlink(link: Path, target: Path, *, directory: bool = False) -> None:
    try:
        link.symlink_to(target, target_is_directory=directory)
    except NotImplementedError as exc:
        pytest.skip(f"symbolic links are unavailable: {exc}")
    except OSError as exc:
        unsupported_errors = {
            errno.EACCES,
            errno.ENOSYS,
            errno.ENOTSUP,
            errno.EPERM,
            errno.EROFS,
        }
        if exc.errno in unsupported_errors or getattr(exc, "winerror", None) in {
            5,
            1314,
        }:
            pytest.skip(
                f"symbolic links require unavailable platform support or permission: {exc}"
            )
        raise


@pytest.mark.parametrize(
    "argument",
    [
        {"max_file_bytes": 0},
        {"max_total_bytes": 0},
        {"max_directory_entries": 0},
        {"max_issue_samples_per_code": 0},
    ],
)
def test_provider_requires_positive_constructor_limits(
    argument: dict[str, int],
) -> None:
    with pytest.raises(ValueError, match="positive"):
        LocalProjectFilesProvider(**argument)


def test_provider_scans_valid_utf8_files_in_stable_relative_order(
    tmp_path: Path,
) -> None:
    (tmp_path / "z.py").write_text("z = 1", encoding="utf-8")
    source = tmp_path / "src"
    source.mkdir()
    (source / "A.py").write_text("a = 1", encoding="utf-8")
    (source / "b.py").write_text("b = 1", encoding="utf-8")

    scan = LocalProjectFilesProvider().scan_files(
        tmp_path,
        allowed_extensions=(".py",),
        max_files=10,
    )

    assert [file.relative_path for file in scan.files] == [
        "src/A.py",
        "src/b.py",
        "z.py",
    ]
    assert all("\\" not in file.relative_path for file in scan.files)
    assert scan.files_attempted == 3
    assert not scan.truncated


def test_provider_filters_allowed_extensions(tmp_path: Path) -> None:
    (tmp_path / "main.py").write_text("python", encoding="utf-8")
    (tmp_path / "notes.md").write_text("markdown", encoding="utf-8")

    scan = LocalProjectFilesProvider().scan_files(
        tmp_path,
        allowed_extensions=(".PY",),
        max_files=10,
    )

    assert [file.relative_path for file in scan.files] == ["main.py"]
    assert scan.files[0].extension == ".py"


def test_provider_rejects_invalid_call_limits(tmp_path: Path) -> None:
    provider = LocalProjectFilesProvider()
    with pytest.raises(ValueError, match="max_files"):
        provider.scan_files(tmp_path, allowed_extensions=(".py",), max_files=0)
    with pytest.raises(ValueError, match="allowed_extensions"):
        provider.scan_files(tmp_path, allowed_extensions=(), max_files=1)


def test_provider_wraps_missing_root_with_cause(tmp_path: Path) -> None:
    with pytest.raises(ProjectPathNotFoundError) as exc_info:
        LocalProjectFilesProvider().scan_files(
            tmp_path / "missing",
            allowed_extensions=(".py",),
            max_files=1,
        )

    assert isinstance(exc_info.value.__cause__, FileNotFoundError)


def test_provider_wraps_non_directory_root_with_cause(tmp_path: Path) -> None:
    project_file = tmp_path / "project.py"
    project_file.write_text("python", encoding="utf-8")

    with pytest.raises(ProjectPathNotAccessibleError) as exc_info:
        LocalProjectFilesProvider().scan_files(
            project_file,
            allowed_extensions=(".py",),
            max_files=1,
        )

    assert exc_info.value.category == "not_directory"
    assert isinstance(exc_info.value.__cause__, NotADirectoryError)


def test_provider_wraps_unlistable_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_iterdir = Path.iterdir
    resolved_root = tmp_path.resolve()

    def deny_root(path: Path) -> Iterator[Path]:
        if path == resolved_root:
            raise PermissionError("denied")
        return original_iterdir(path)

    monkeypatch.setattr(Path, "iterdir", deny_root)

    with pytest.raises(ProjectPathNotAccessibleError) as exc_info:
        LocalProjectFilesProvider().scan_files(
            tmp_path,
            allowed_extensions=(".py",),
            max_files=1,
        )

    assert exc_info.value.category == "root_list_failed"
    assert isinstance(exc_info.value.__cause__, PermissionError)


def test_provider_applies_max_files_after_stable_sort(tmp_path: Path) -> None:
    for name in ("c.py", "a.py", "b.py"):
        (tmp_path / name).write_text(name, encoding="utf-8")

    scan = LocalProjectFilesProvider().scan_files(
        tmp_path,
        allowed_extensions=(".py",),
        max_files=2,
    )

    assert [file.relative_path for file in scan.files] == ["a.py", "b.py"]
    assert scan.files_attempted == 2
    assert scan.truncated
    assert "scan_limit_exceeded" in issue_codes(scan)


def test_provider_stops_at_directory_entry_limit(tmp_path: Path) -> None:
    for name in ("a.py", "b.py", "c.py"):
        (tmp_path / name).write_text(name, encoding="utf-8")

    scan = LocalProjectFilesProvider(max_directory_entries=2).scan_files(
        tmp_path,
        allowed_extensions=(".py",),
        max_files=10,
    )

    assert [file.relative_path for file in scan.files] == ["a.py", "b.py"]
    assert scan.truncated
    limit_issue = next(
        issue for issue in scan.issues if issue.code == "scan_limit_exceeded"
    )
    assert "max_directory_entries" in limit_issue.category


def test_provider_stops_at_total_byte_limit(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("1234", encoding="utf-8")
    (tmp_path / "b.py").write_text("5678", encoding="utf-8")

    scan = LocalProjectFilesProvider(
        max_file_bytes=10,
        max_total_bytes=5,
    ).scan_files(
        tmp_path,
        allowed_extensions=(".py",),
        max_files=10,
    )

    assert len(scan.files) == 1
    assert scan.truncated
    assert "scan_limit_exceeded" in issue_codes(scan)


def test_provider_reads_only_bounded_file_prefix(tmp_path: Path) -> None:
    content = "0123456789"
    (tmp_path / "large.py").write_text(content, encoding="utf-8")

    scan = LocalProjectFilesProvider(max_file_bytes=4).scan_files(
        tmp_path,
        allowed_extensions=(".py",),
        max_files=1,
    )

    project_file = scan.files[0]
    assert project_file.content == "0123"
    assert project_file.bytes_read == 4
    assert project_file.size_bytes == len(content)
    assert project_file.truncated
    assert "project_file_truncated" in issue_codes(scan)


def test_provider_handles_utf8_character_crossing_truncation_boundary(
    tmp_path: Path,
) -> None:
    (tmp_path / "unicode.py").write_text("ab你cd", encoding="utf-8")

    scan = LocalProjectFilesProvider(max_file_bytes=4).scan_files(
        tmp_path,
        allowed_extensions=(".py",),
        max_files=1,
    )

    assert scan.files[0].content == "ab"
    assert scan.files[0].truncated
    assert "project_file_decode_failed" not in issue_codes(scan)


def test_provider_decodes_utf8_bom(tmp_path: Path) -> None:
    (tmp_path / "bom.py").write_text("Python", encoding="utf-8-sig")

    scan = LocalProjectFilesProvider().scan_files(
        tmp_path,
        allowed_extensions=(".py",),
        max_files=1,
    )

    assert scan.files[0].content == "Python"


def test_provider_reports_non_utf8_as_all_unreadable(tmp_path: Path) -> None:
    (tmp_path / "legacy.py").write_bytes(b"\xff\xfeinvalid")

    with pytest.raises(ProjectFilesUnreadableError) as exc_info:
        LocalProjectFilesProvider().scan_files(
            tmp_path,
            allowed_extensions=(".py",),
            max_files=1,
        )

    assert exc_info.value.files_attempted == 1
    assert {issue.code for issue in exc_info.value.issues} == {
        "project_file_decode_failed"
    }


def test_provider_skips_nul_binary_without_exposing_content(tmp_path: Path) -> None:
    (tmp_path / "binary.py").write_bytes(b"secret\x00payload")

    scan = LocalProjectFilesProvider().scan_files(
        tmp_path,
        allowed_extensions=(".py",),
        max_files=1,
    )

    assert scan.files == ()
    assert scan.files_attempted == 1
    assert "binary_file_skipped" in issue_codes(scan)
    assert "secret" not in repr(scan.issues)


def test_provider_skips_hidden_and_ignored_directories(tmp_path: Path) -> None:
    for directory_name in (
        ".hidden",
        ".git",
        ".venv",
        "venv",
        "node_modules",
        "dist",
        "build",
        "__pycache__",
        ".mypy_cache",
        ".pytest_cache",
    ):
        directory = tmp_path / directory_name
        directory.mkdir()
        (directory / "ignored.py").write_text("python", encoding="utf-8")
    (tmp_path / ".hidden.py").write_text("python", encoding="utf-8")
    (tmp_path / "visible.py").write_text("python", encoding="utf-8")

    scan = LocalProjectFilesProvider().scan_files(
        tmp_path,
        allowed_extensions=(".py",),
        max_files=100,
    )

    assert [file.relative_path for file in scan.files] == ["visible.py"]


@pytest.mark.parametrize(
    "name",
    [
        ".env",
        ".env.local",
        "id_rsa",
        "id_ed25519",
        "credentials.json",
        "credentials.prod.json",
        "private.pem",
        "private.key",
        "private.p12",
        "private.pfx",
    ],
)
def test_provider_skips_sensitive_file_names(tmp_path: Path, name: str) -> None:
    (tmp_path / name).write_text("do-not-read", encoding="utf-8")

    scan = LocalProjectFilesProvider().scan_files(
        tmp_path,
        allowed_extensions=(
            ".env",
            ".json",
            ".pem",
            ".key",
            ".p12",
            ".pfx",
            "",
        ),
        max_files=10,
    )

    assert scan.files == ()
    assert "sensitive_file_skipped" in issue_codes(scan)
    assert "do-not-read" not in repr(scan)


def test_provider_skips_private_key_block_in_normal_text_file(tmp_path: Path) -> None:
    (tmp_path / "config.py").write_text(
        "value = '''-----BEGIN PRIVATE KEY-----\nsecret\n'''",
        encoding="utf-8",
    )

    scan = LocalProjectFilesProvider().scan_files(
        tmp_path,
        allowed_extensions=(".py",),
        max_files=1,
    )

    assert scan.files == ()
    assert "sensitive_file_skipped" in issue_codes(scan)
    assert "secret" not in repr(scan)


def test_provider_continues_when_one_file_disappears(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    disappearing = tmp_path / "a.py"
    disappearing.write_text("gone", encoding="utf-8")
    (tmp_path / "b.py").write_text("kept", encoding="utf-8")
    original_open = Path.open

    def disappear(path: Path, *args: object, **kwargs: object):
        if path == disappearing.resolve():
            raise FileNotFoundError("gone")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", disappear)
    scan = LocalProjectFilesProvider().scan_files(
        tmp_path,
        allowed_extensions=(".py",),
        max_files=2,
    )

    assert [file.relative_path for file in scan.files] == ["b.py"]
    assert "project_file_unreadable" in issue_codes(scan)


def test_provider_continues_when_one_file_is_unreadable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    denied = tmp_path / "a.py"
    denied.write_text("denied", encoding="utf-8")
    (tmp_path / "b.py").write_text("kept", encoding="utf-8")
    original_open = Path.open

    def deny(path: Path, *args: object, **kwargs: object):
        if path == denied.resolve():
            raise PermissionError("denied")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", deny)
    scan = LocalProjectFilesProvider().scan_files(
        tmp_path,
        allowed_extensions=(".py",),
        max_files=2,
    )

    assert [file.relative_path for file in scan.files] == ["b.py"]
    assert "project_file_unreadable" in issue_codes(scan)


def test_provider_allows_file_symlink_to_inside_root(tmp_path: Path) -> None:
    target = tmp_path / "target.py"
    target.write_text("python", encoding="utf-8")
    link = tmp_path / "linked.py"
    make_symlink(link, target)

    scan = LocalProjectFilesProvider().scan_files(
        tmp_path,
        allowed_extensions=(".py",),
        max_files=10,
    )

    assert {file.relative_path for file in scan.files} == {"linked.py", "target.py"}


def test_provider_skips_file_symlink_to_outside_root(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    outside = tmp_path / "outside.py"
    outside.write_text("outside-secret", encoding="utf-8")
    make_symlink(root / "linked.py", outside)

    scan = LocalProjectFilesProvider().scan_files(
        root,
        allowed_extensions=(".py",),
        max_files=10,
    )

    assert scan.files == ()
    assert "unsafe_symlink_skipped" in issue_codes(scan)
    assert "outside-secret" not in repr(scan)


def test_provider_skips_broken_file_symlink(tmp_path: Path) -> None:
    make_symlink(tmp_path / "broken.py", tmp_path / "missing.py")

    scan = LocalProjectFilesProvider().scan_files(
        tmp_path,
        allowed_extensions=(".py",),
        max_files=10,
    )

    assert scan.files == ()
    assert "unsafe_symlink_skipped" in issue_codes(scan)


def test_provider_does_not_recurse_directory_symlink(tmp_path: Path) -> None:
    real_directory = tmp_path / "real"
    real_directory.mkdir()
    (real_directory / "inside.py").write_text("python", encoding="utf-8")
    make_symlink(tmp_path / "linked", real_directory, directory=True)

    scan = LocalProjectFilesProvider().scan_files(
        tmp_path,
        allowed_extensions=(".py",),
        max_files=10,
    )

    assert [file.relative_path for file in scan.files] == ["real/inside.py"]
    assert "unsafe_symlink_skipped" in issue_codes(scan)


def test_provider_does_not_recurse_junction_like_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    junction = tmp_path / "junction"
    junction.mkdir()
    (junction / "inside.py").write_text("python", encoding="utf-8")
    original_is_junction = Path.is_junction

    def simulate_junction(path: Path) -> bool:
        if path == junction:
            return True
        return original_is_junction(path)

    monkeypatch.setattr(Path, "is_junction", simulate_junction)
    scan = LocalProjectFilesProvider().scan_files(
        tmp_path,
        allowed_extensions=(".py",),
        max_files=10,
    )

    assert scan.files == ()
    assert "unsafe_symlink_skipped" in issue_codes(scan)


def test_provider_limits_issue_samples_by_code(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    denied_paths: set[Path] = set()
    for index in range(5):
        path = tmp_path / f"{index}.py"
        path.write_text("denied", encoding="utf-8")
        denied_paths.add(path.resolve())
    (tmp_path / "ok.py").write_text("ok", encoding="utf-8")
    original_open = Path.open

    def deny(path: Path, *args: object, **kwargs: object):
        if path in denied_paths:
            raise PermissionError("denied")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", deny)
    scan = LocalProjectFilesProvider(max_issue_samples_per_code=2).scan_files(
        tmp_path,
        allowed_extensions=(".py",),
        max_files=10,
    )
    issue = next(
        issue for issue in scan.issues if issue.code == "project_file_unreadable"
    )

    assert issue.count == 5
    assert len(issue.sample_relative_paths) == 2
    assert issue.relative_path == issue.sample_relative_paths[0]


def test_provider_does_not_cache_or_modify_project_files(tmp_path: Path) -> None:
    source = tmp_path / "main.py"
    source.write_text("version = 1", encoding="utf-8")
    original_mtime = source.stat().st_mtime_ns
    provider = LocalProjectFilesProvider()

    first = provider.scan_files(
        tmp_path,
        allowed_extensions=(".py",),
        max_files=1,
    )
    source.write_text("version = 2", encoding="utf-8")
    second_mtime = source.stat().st_mtime_ns
    second = provider.scan_files(
        tmp_path,
        allowed_extensions=(".py",),
        max_files=1,
    )

    assert first.files[0].content == "version = 1"
    assert second.files[0].content == "version = 2"
    assert source.read_text(encoding="utf-8") == "version = 2"
    assert source.stat().st_mtime_ns == second_mtime
    assert second_mtime >= original_mtime


def test_windows_hidden_attribute_is_checked_best_effort(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hidden = tmp_path / "hidden.py"
    hidden.write_text("python", encoding="utf-8")
    visible = tmp_path / "visible.py"
    visible.write_text("python", encoding="utf-8")
    original_stat = Path.stat
    hidden_flag = getattr(stat, "FILE_ATTRIBUTE_HIDDEN", 2)
    monkeypatch.setattr(stat, "FILE_ATTRIBUTE_HIDDEN", hidden_flag, raising=False)

    def simulate_hidden_attribute(
        path: Path,
        *,
        follow_symlinks: bool = True,
    ) -> object:
        if path == hidden and not follow_symlinks:
            return SimpleNamespace(st_file_attributes=hidden_flag)
        return original_stat(path, follow_symlinks=follow_symlinks)

    monkeypatch.setattr(Path, "stat", simulate_hidden_attribute)
    scan = LocalProjectFilesProvider().scan_files(
        tmp_path,
        allowed_extensions=(".py",),
        max_files=10,
    )

    assert [file.relative_path for file in scan.files] == ["visible.py"]
