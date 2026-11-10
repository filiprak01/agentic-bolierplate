from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import tarfile
import tempfile


POLICY_PATH = "scripts/release/public_release_private_policy.json"
PUBLISHED_ROOTS = {
    ".agents",
    ".dockerignore",
    ".env.example",
    ".gitattributes",
    ".github",
    ".gitignore",
    "AGENTS.md",
    "CLAUDE.md",
    "Dockerfile",
    "LICENSE",
    "README.md",
    "SECURITY.md",
    "ai_agents",
    "alembic.ini",
    "docker-compose.ssh.example.yml",
    "docker-compose.yml",
    "docs",
    "migrations",
    "pyproject.toml",
    "scripts",
    "src",
    "tests",
    "ui",
}

REQUIRED_PATHS = (
    "AGENTS.md",
    "CLAUDE.md",
    "LICENSE",
    "README.md",
    "SECURITY.md",
    ".agents/skills",
    "ai_agents/roles",
    "ai_agents/session_starters",
    "docs",
    "docs/reports/index.md",
)

DENIED_PREFIXES = ("data/", "docs/reports/")
DENIED_PATHS = {POLICY_PATH}
DENIED_PARTS = {
    ".git",
    ".idea",
    ".release-worktrees",
    ".venv",
    ".vscode",
    "__pycache__",
    "node_modules",
}
DENIED_SUFFIXES = {".key", ".p12", ".pem", ".pfx"}

SECRET_PATTERNS = {
    "github_token": re.compile(rb"(?:github_pat_[A-Za-z0-9_]{20,}|\bghp_[A-Za-z0-9]{20,}\b)"),
    "aws_access_key": re.compile(rb"\bAKIA[0-9A-Z]{16}\b"),
    "private_key": re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "jwt": re.compile(rb"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"),
}

PUBLIC_REPORT_INDEX = """# Public Release Reports

Internal execution logs, Jira evidence, PO messages, and runtime reports are not
part of the public source release. Public release metadata and the reproducible
source tree are available in `PUBLIC_RELEASE_MANIFEST.json`.
"""


def _run_git(source: Path, *args: str, binary: bool = False) -> str | bytes:
    result = subprocess.run(
        ["git", "-C", str(source), *args],
        check=True,
        capture_output=True,
        text=not binary,
    )
    return result.stdout


def _load_replacements(source: Path, commit: str) -> tuple[tuple[str, str], ...]:
    try:
        raw = str(_run_git(source, "show", f"{commit}:{POLICY_PATH}"))
    except subprocess.CalledProcessError:
        return ()
    payload = json.loads(raw)
    replacements = tuple(
        (str(item["private"]), str(item["public"]))
        for item in payload.get("replacements", ())
    )
    if any(not private or private == public for private, public in replacements):
        raise ValueError("Public release replacement policy is invalid")
    return replacements


def _is_published(path: PurePosixPath) -> bool:
    rendered = path.as_posix()
    if not path.parts or path.parts[0] not in PUBLISHED_ROOTS:
        return False
    if rendered in DENIED_PATHS or rendered.startswith(DENIED_PREFIXES):
        return False
    if any(part in DENIED_PARTS for part in path.parts):
        return False
    if path.suffix.lower() in DENIED_SUFFIXES:
        return False
    return path.name == ".env.example" or not path.name.startswith(".env")


def _sanitize_text(data: bytes, replacements: tuple[tuple[str, str], ...]) -> bytes:
    if b"\0" in data:
        return data
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return data
    for private, public in replacements:
        text = text.replace(private, public)
    text = re.sub(
        r"\]\((\.\./)?reports/[^)\s]+\.md\)",
        lambda match: "](" + (match.group(1) or "") + "reports/index.md)",
        text,
    )
    return text.encode("utf-8")


def _neutralize_test_secret_literals(path: str, data: bytes) -> bytes:
    if not path.startswith("tests/") or not path.endswith(".py"):
        return data
    for pattern in SECRET_PATTERNS.values():
        for match in reversed(tuple(pattern.finditer(data))):
            if match.start() == 0 or data[match.start() - 1] not in (34, 39):
                continue
            quote = bytes((data[match.start() - 1],))
            value = match.group()
            if value.startswith(b"github_pat_"):
                split = len(b"github_")
            elif value.startswith(b"ghp_"):
                split = len(b"gh")
            elif value.startswith(b"AKIA"):
                split = len(b"AK")
            elif value.startswith(b"-----BEGIN "):
                split = len(b"-----BEGIN")
            else:
                split = max(1, len(value) // 3)
            prefix = (
                bytes((data[match.start() - 2],))
                if match.start() >= 2 and data[match.start() - 2] in b"bBrRfF"
                else b""
            )
            replacement = value[:split] + quote + b" " + prefix + quote + value[split:]
            data = data[: match.start()] + replacement + data[match.end() :]
    return data


def _scan(path: str, data: bytes) -> list[str]:
    return [name for name, pattern in SECRET_PATTERNS.items() if pattern.search(data)]


def _tree_hash(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        digest.update(path.relative_to(root).as_posix().encode("utf-8") + b"\0")
        digest.update(path.read_bytes())
    return digest.hexdigest()


def export_public_release(source: Path, destination: Path, ref: str = "HEAD") -> dict[str, object]:
    source = source.resolve()
    destination = destination.resolve()
    if destination.exists():
        raise ValueError(f"Destination already exists: {destination}")
    if destination == source or source in destination.parents:
        raise ValueError("Destination must be outside the source repository")

    commit = str(_run_git(source, "rev-parse", f"{ref}^{{commit}}")).strip()
    replacements = _load_replacements(source, commit)
    archive = _run_git(source, "archive", "--format=tar", commit, binary=True)
    assert isinstance(archive, bytes)

    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="public-release-", dir=destination.parent) as temporary:
        candidate = Path(temporary) / "candidate"
        candidate.mkdir()
        included = 0
        excluded = 0
        findings: list[str] = []

        with tarfile.open(fileobj=io.BytesIO(archive), mode="r:") as tar:
            for member in tar:
                path = PurePosixPath(member.name)
                if member.isdir():
                    continue
                if not _is_published(path):
                    excluded += 1
                    continue
                if not member.isfile():
                    findings.append(f"{path.as_posix()}:unsupported_file_type")
                    continue
                extracted = tar.extractfile(member)
                if extracted is None:
                    findings.append(f"{path.as_posix()}:unreadable")
                    continue
                data = _sanitize_text(extracted.read(), replacements)
                data = _neutralize_test_secret_literals(path.as_posix(), data)
                findings.extend(f"{path.as_posix()}:{kind}" for kind in _scan(path.as_posix(), data))
                output = candidate / path.as_posix()
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_bytes(data)
                os.chmod(output, member.mode & 0o777)
                included += 1

        public_report_index = candidate / "docs/reports/index.md"
        public_report_index.parent.mkdir(parents=True, exist_ok=True)
        public_report_index.write_text(PUBLIC_REPORT_INDEX, encoding="utf-8")
        included += 1

        findings.extend(
            f"{path}:required_path_missing"
            for path in REQUIRED_PATHS
            if not (candidate / path).exists()
        )
        for private, _ in replacements:
            marker = private.encode("utf-8")
            for path in candidate.rglob("*"):
                if path.is_file() and marker in path.read_bytes():
                    findings.append(f"{path.relative_to(candidate).as_posix()}:private_context")

        if findings:
            raise ValueError("Public release audit failed:\n" + "\n".join(sorted(set(findings))))

        manifest = {
            "format_version": 1,
            "license": "Apache-2.0",
            "source_commit": commit,
            "included_files": included,
            "excluded_files": excluded,
            "excluded_roots": ["data/", "docs/reports/"],
            "replacement_count": len(replacements),
            "tree_sha256": _tree_hash(candidate),
        }
        (candidate / "PUBLIC_RELEASE_MANIFEST.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(candidate, destination)
        return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Export an audited public release snapshot.")
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--ref", default="HEAD")
    args = parser.parse_args()
    print(json.dumps(export_public_release(args.source, args.destination, args.ref), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
