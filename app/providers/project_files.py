"""Safe, bounded access to files in a user-authorized local project."""

from __future__ import annotations

import codecs
import hashlib
import os
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

_IGNORED_DIRECTORY_NAMES = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
    "venv",
}
_SENSITIVE_EXTENSIONS = {".key", ".p12", ".pem", ".pfx"}
_PRIVATE_KEY_MARKERS = (
    "-----BEGIN PRIVATE KEY-----",
    "-----BEGIN RSA PRIVATE KEY-----",
    "-----BEGIN EC PRIVATE KEY-----",
    "-----BEGIN OPENSSH PRIVATE KEY-----",
    "-----BEGIN ENCRYPTED PRIVATE KEY-----",
)


@dataclass(frozen=True, slots=True)
class ProjectFile:
    """One decoded text prefix returned across the Provider boundary."""

    relative_path: str
    extension: str
    content: str
    size_bytes: int
    bytes_read: int
    truncated: bool


@dataclass(frozen=True, slots=True)
class ProjectFileIssue:
    """A bounded, path-safe description of one class of scan issue."""

    code: str
    category: str
    relative_path: str | None
    recoverable: bool
    count: int = 1
    sample_relative_paths: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ProjectFilesScan:
    """Internal result returned by a project-files Provider."""

    files: tuple[ProjectFile, ...]
    files_attempted: int
    truncated: bool
    issues: tuple[ProjectFileIssue, ...]
    project_root_digest: str


class ProjectFilesProviderError(Exception):
    """Base exception for fatal project-files Provider failures."""


class ProjectPathNotFoundError(ProjectFilesProviderError):
    """Raised when the authorized project root cannot be resolved."""

    def __init__(self, project_path: Path) -> None:
        self.project_path = project_path
        super().__init__("project path was not found")


class ProjectPathNotAccessibleError(ProjectFilesProviderError):
    """Raised when the authorized project root cannot be scanned."""

    def __init__(self, project_path: Path, *, category: str) -> None:
        self.project_path = project_path
        self.category = category
        super().__init__("project path is not accessible")


class ProjectFilesUnreadableError(ProjectFilesProviderError):
    """Raised when every attempted text file failed to decode or read."""

    def __init__(
        self,
        *,
        files_attempted: int,
        issues: tuple[ProjectFileIssue, ...],
    ) -> None:
        self.files_attempted = files_attempted
        self.issues = issues
        super().__init__("all attempted project files were unreadable")


class ProjectFilesProvider(Protocol):
    """File-system access boundary consumed by the evidence Tool."""

    def scan_files(
        self,
        project_path: Path,
        *,
        allowed_extensions: tuple[str, ...],
        max_files: int,
    ) -> ProjectFilesScan:
        """Return safe text prefixes from the authorized project root."""


@dataclass(frozen=True, slots=True)
class _CandidateFile:
    relative_path: str
    resolved_path: Path
    extension: str


@dataclass(slots=True)
class _IssueAccumulator:
    recoverable: bool
    categories: set[str]
    count: int
    sample_relative_paths: list[str]


class _IssueCollector:
    def __init__(self, max_samples_per_code: int) -> None:
        self._max_samples_per_code = max_samples_per_code
        self._issues: dict[str, _IssueAccumulator] = {}

    def add(
        self,
        *,
        code: str,
        category: str,
        relative_path: str | None = None,
        recoverable: bool = True,
        count: int = 1,
    ) -> None:
        accumulator = self._issues.get(code)
        if accumulator is None:
            accumulator = _IssueAccumulator(
                recoverable=recoverable,
                categories=set(),
                count=0,
                sample_relative_paths=[],
            )
            self._issues[code] = accumulator
        accumulator.recoverable = accumulator.recoverable and recoverable
        accumulator.categories.add(category)
        accumulator.count += count
        if (
            relative_path is not None
            and relative_path not in accumulator.sample_relative_paths
            and len(accumulator.sample_relative_paths) < self._max_samples_per_code
        ):
            accumulator.sample_relative_paths.append(relative_path)

    def build(self) -> tuple[ProjectFileIssue, ...]:
        issues: list[ProjectFileIssue] = []
        for code in sorted(self._issues):
            accumulator = self._issues[code]
            samples = tuple(accumulator.sample_relative_paths)
            issues.append(
                ProjectFileIssue(
                    code=code,
                    category=",".join(sorted(accumulator.categories)),
                    relative_path=samples[0] if samples else None,
                    recoverable=accumulator.recoverable,
                    count=accumulator.count,
                    sample_relative_paths=samples,
                )
            )
        return tuple(issues)


class LocalProjectFilesProvider:
    """Standard-library implementation of bounded local project scanning."""

    def __init__(
        self,
        *,
        max_file_bytes: int = 512 * 1024,
        max_total_bytes: int = 16 * 1024 * 1024,
        max_directory_entries: int = 10_000,
        max_issue_samples_per_code: int = 5,
    ) -> None:
        limits = {
            "max_file_bytes": max_file_bytes,
            "max_total_bytes": max_total_bytes,
            "max_directory_entries": max_directory_entries,
            "max_issue_samples_per_code": max_issue_samples_per_code,
        }
        invalid = [name for name, value in limits.items() if value <= 0]
        if invalid:
            raise ValueError(f"provider limits must be positive: {', '.join(invalid)}")

        self._max_file_bytes = max_file_bytes
        self._max_total_bytes = max_total_bytes
        self._max_directory_entries = max_directory_entries
        self._max_issue_samples_per_code = max_issue_samples_per_code

    def scan_files(
        self,
        project_path: Path,
        *,
        allowed_extensions: tuple[str, ...],
        max_files: int,
    ) -> ProjectFilesScan:
        if max_files <= 0:
            raise ValueError("max_files must be positive")
        normalized_extensions = {
            extension.casefold() for extension in allowed_extensions if extension
        }
        if not normalized_extensions:
            raise ValueError("allowed_extensions must not be empty")

        root = self._resolve_root(project_path)
        root_digest = hashlib.sha256(
            os.path.normcase(str(root)).encode("utf-8")
        ).hexdigest()
        issues = _IssueCollector(self._max_issue_samples_per_code)
        candidates, discovery_truncated = self._discover_candidates(
            root,
            normalized_extensions,
            issues,
            project_path,
        )

        scan_truncated = discovery_truncated
        if len(candidates) > max_files:
            issues.add(
                code="scan_limit_exceeded",
                category="max_files",
                recoverable=True,
                count=len(candidates) - max_files,
            )
            candidates = candidates[:max_files]
            scan_truncated = True

        files: list[ProjectFile] = []
        files_attempted = 0
        unreadable_attempts = 0
        total_bytes_read = 0
        for candidate_index, candidate in enumerate(candidates):
            remaining_total = self._max_total_bytes - total_bytes_read
            if remaining_total <= 1:
                issues.add(
                    code="scan_limit_exceeded",
                    category="max_total_bytes",
                    recoverable=True,
                    count=len(candidates) - candidate_index,
                )
                scan_truncated = True
                break

            files_attempted += 1
            try:
                project_file, physical_bytes_read, was_unreadable = self._read_candidate(
                    candidate,
                    byte_limit=min(self._max_file_bytes, remaining_total - 1),
                    issues=issues,
                )
            except (FileNotFoundError, PermissionError, OSError):
                issues.add(
                    code="project_file_unreadable",
                    category="file_read",
                    relative_path=candidate.relative_path,
                    recoverable=True,
                )
                unreadable_attempts += 1
                continue

            total_bytes_read += physical_bytes_read
            if was_unreadable:
                unreadable_attempts += 1
            if project_file is None:
                continue
            files.append(project_file)
            if project_file.truncated:
                scan_truncated = True

        built_issues = issues.build()
        if files_attempted > 0 and unreadable_attempts == files_attempted:
            raise ProjectFilesUnreadableError(
                files_attempted=files_attempted,
                issues=built_issues,
            )

        return ProjectFilesScan(
            files=tuple(files),
            files_attempted=files_attempted,
            truncated=scan_truncated,
            issues=built_issues,
            project_root_digest=root_digest,
        )

    def _resolve_root(self, project_path: Path) -> Path:
        try:
            root = project_path.resolve(strict=True)
        except FileNotFoundError as exc:
            raise ProjectPathNotFoundError(project_path) from exc
        except (OSError, RuntimeError) as exc:
            raise ProjectPathNotAccessibleError(
                project_path,
                category="resolve_failed",
            ) from exc

        try:
            root_mode = root.stat().st_mode
        except OSError as exc:
            raise ProjectPathNotAccessibleError(
                project_path,
                category="root_stat_failed",
            ) from exc
        try:
            if not stat.S_ISDIR(root_mode):
                raise NotADirectoryError("project path is not a directory")
        except NotADirectoryError as exc:
            raise ProjectPathNotAccessibleError(
                project_path,
                category="not_directory",
            ) from exc
        return root

    def _discover_candidates(
        self,
        root: Path,
        allowed_extensions: set[str],
        issues: _IssueCollector,
        original_project_path: Path,
    ) -> tuple[list[_CandidateFile], bool]:
        candidates: list[_CandidateFile] = []
        entries_seen = 0
        truncated = False

        def visit(directory: Path) -> None:
            nonlocal entries_seen, truncated
            if truncated:
                return
            try:
                entries = sorted(
                    directory.iterdir(),
                    key=lambda entry: (
                        entry.relative_to(root).as_posix().casefold(),
                        entry.relative_to(root).as_posix(),
                    ),
                )
            except OSError as exc:
                if directory == root:
                    raise ProjectPathNotAccessibleError(
                        original_project_path,
                        category="root_list_failed",
                    ) from exc
                relative_directory = directory.relative_to(root).as_posix()
                issues.add(
                    code="project_file_unreadable",
                    category="directory_list",
                    relative_path=relative_directory,
                    recoverable=True,
                )
                return

            for entry in entries:
                if entries_seen >= self._max_directory_entries:
                    issues.add(
                        code="scan_limit_exceeded",
                        category="max_directory_entries",
                        recoverable=True,
                    )
                    truncated = True
                    return
                entries_seen += 1
                relative_path = entry.relative_to(root).as_posix()

                if self._is_sensitive_file(entry):
                    issues.add(
                        code="sensitive_file_skipped",
                        category="sensitive_name",
                        relative_path=relative_path,
                        recoverable=True,
                    )
                    continue
                if self._is_hidden(entry):
                    continue

                try:
                    is_symlink = entry.is_symlink()
                    is_junction = entry.is_junction()
                except OSError:
                    issues.add(
                        code="project_file_unreadable",
                        category="entry_stat",
                        relative_path=relative_path,
                        recoverable=True,
                    )
                    continue

                if is_symlink or is_junction:
                    self._handle_link(
                        entry,
                        relative_path,
                        root,
                        allowed_extensions,
                        candidates,
                        issues,
                    )
                    continue

                try:
                    if entry.is_dir():
                        if entry.name.casefold() in _IGNORED_DIRECTORY_NAMES:
                            continue
                        visit(entry)
                        if truncated:
                            return
                    elif entry.is_file():
                        self._add_regular_candidate(
                            entry,
                            relative_path,
                            root,
                            allowed_extensions,
                            candidates,
                            issues,
                        )
                except OSError:
                    issues.add(
                        code="project_file_unreadable",
                        category="entry_stat",
                        relative_path=relative_path,
                        recoverable=True,
                    )

        visit(root)
        candidates.sort(
            key=lambda candidate: (
                candidate.relative_path.casefold(),
                candidate.relative_path,
            )
        )
        return candidates, truncated

    def _handle_link(
        self,
        entry: Path,
        relative_path: str,
        root: Path,
        allowed_extensions: set[str],
        candidates: list[_CandidateFile],
        issues: _IssueCollector,
    ) -> None:
        try:
            if entry.is_junction() or entry.is_dir():
                issues.add(
                    code="unsafe_symlink_skipped",
                    category="directory_link",
                    relative_path=relative_path,
                    recoverable=True,
                )
                return
            resolved = entry.resolve(strict=True)
            if not resolved.is_relative_to(root) or not resolved.is_file():
                issues.add(
                    code="unsafe_symlink_skipped",
                    category="outside_root_or_not_file",
                    relative_path=relative_path,
                    recoverable=True,
                )
                return
        except (FileNotFoundError, OSError, RuntimeError):
            issues.add(
                code="unsafe_symlink_skipped",
                category="broken_or_cyclic",
                relative_path=relative_path,
                recoverable=True,
            )
            return

        extension = entry.suffix.casefold()
        if extension in allowed_extensions:
            candidates.append(
                _CandidateFile(
                    relative_path=relative_path,
                    resolved_path=resolved,
                    extension=extension,
                )
            )

    def _add_regular_candidate(
        self,
        entry: Path,
        relative_path: str,
        root: Path,
        allowed_extensions: set[str],
        candidates: list[_CandidateFile],
        issues: _IssueCollector,
    ) -> None:
        extension = entry.suffix.casefold()
        if extension not in allowed_extensions:
            return
        try:
            resolved = entry.resolve(strict=True)
        except (FileNotFoundError, OSError, RuntimeError):
            issues.add(
                code="project_file_unreadable",
                category="file_resolve",
                relative_path=relative_path,
                recoverable=True,
            )
            return
        if not resolved.is_relative_to(root) or not resolved.is_file():
            issues.add(
                code="unsafe_symlink_skipped",
                category="outside_root_or_not_file",
                relative_path=relative_path,
                recoverable=True,
            )
            return
        candidates.append(
            _CandidateFile(
                relative_path=relative_path,
                resolved_path=resolved,
                extension=extension,
            )
        )

    def _read_candidate(
        self,
        candidate: _CandidateFile,
        *,
        byte_limit: int,
        issues: _IssueCollector,
    ) -> tuple[ProjectFile | None, int, bool]:
        with candidate.resolved_path.open("rb") as file_handle:
            size_bytes = os.fstat(file_handle.fileno()).st_size
            raw_with_probe = file_handle.read(byte_limit + 1)

        physical_bytes_read = len(raw_with_probe)
        raw_content = raw_with_probe[:byte_limit]
        file_truncated = len(raw_with_probe) > byte_limit or size_bytes > byte_limit
        if b"\x00" in raw_with_probe:
            issues.add(
                code="binary_file_skipped",
                category="nul_byte",
                relative_path=candidate.relative_path,
                recoverable=True,
            )
            return None, physical_bytes_read, False

        decoder = codecs.getincrementaldecoder("utf-8-sig")("strict")
        try:
            content = decoder.decode(raw_content, final=not file_truncated)
        except UnicodeDecodeError:
            issues.add(
                code="project_file_decode_failed",
                category="utf8_decode",
                relative_path=candidate.relative_path,
                recoverable=True,
            )
            return None, physical_bytes_read, True
        if any(marker in content.upper() for marker in _PRIVATE_KEY_MARKERS):
            issues.add(
                code="sensitive_file_skipped",
                category="private_key_block",
                relative_path=candidate.relative_path,
                recoverable=True,
            )
            return None, physical_bytes_read, False

        if file_truncated:
            issues.add(
                code="project_file_truncated",
                category="max_file_bytes",
                relative_path=candidate.relative_path,
                recoverable=True,
            )

        return (
            ProjectFile(
                relative_path=candidate.relative_path,
                extension=candidate.extension,
                content=content,
                size_bytes=size_bytes,
                bytes_read=len(raw_content),
                truncated=file_truncated,
            ),
            physical_bytes_read,
            False,
        )

    @staticmethod
    def _is_sensitive_file(path: Path) -> bool:
        name = path.name.casefold()
        if name == ".env" or name.startswith(".env."):
            return True
        if name in {"id_ed25519", "id_rsa", "credentials.json"}:
            return True
        if name.startswith("credentials.") and name.endswith(".json"):
            return True
        return path.suffix.casefold() in _SENSITIVE_EXTENSIONS

    @staticmethod
    def _is_hidden(path: Path) -> bool:
        if path.name.startswith("."):
            return True
        hidden_flag = getattr(stat, "FILE_ATTRIBUTE_HIDDEN", 0)
        if not hidden_flag:
            return False
        try:
            file_attributes = getattr(
                path.stat(follow_symlinks=False),
                "st_file_attributes",
                0,
            )
        except OSError:
            return False
        return bool(file_attributes & hidden_flag)
