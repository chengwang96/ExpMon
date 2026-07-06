from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

SKIP_DIRS = {
    ".git",
    "node_modules",
    "dist",
    "screenshots",
    "__pycache__",
    ".venv",
    "venv",
}

SKIP_SUFFIXES = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".ico",
    ".webp",
    ".pyc",
    ".pyd",
    ".dll",
    ".exe",
    ".zip",
    ".gz",
    ".tar",
    ".log",
    ".lock",
    ".err.log",
    ".tsbuildinfo",
}

SKIP_FILES = {
    ".env",
    ".env.local",
    "expmon-local.yaml",
    "expmon-local.yml",
    "expmon-run-metadata.json",
    "expmon-ssh-servers.json",
    "scripts/privacy_scan.py",
}

PATTERNS = {
    "windows_drive_path": re.compile(r"\b[A-Za-z]:[\\/](?:Users|Dataset|Code|ProgramData|Anaconda|Miniconda)\b", re.IGNORECASE),
    "user_profile": re.compile(r"C:[\\/]Users[\\/][^\\/\s\"']+", re.IGNORECASE),
    "known_username": re.compile(r"\b45846\b"),
    "local_dataset_project": re.compile(r"\bARDS\b"),
    "local_hostname": re.compile(r"\b(?:hp-win11|Win11)\b", re.IGNORECASE),
    "fake_gpu_server": re.compile(r"\b(?:a100-node|A100)\b", re.IGNORECASE),
    "training_script": re.compile(r"\bmain_retrain\b", re.IGNORECASE),
    "local_python_env": re.compile(r"\b(?:anaconda|miniconda)\b", re.IGNORECASE),
}

ALLOWLIST: dict[str, set[str]] = {
    "scripts/local_collector.py": {"anaconda", "miniconda"},
}


def should_scan(path: Path) -> bool:
    relative = path.relative_to(ROOT)
    relative_text = str(relative).replace("\\", "/")
    if relative_text in SKIP_FILES:
        return False
    if any(part in SKIP_DIRS for part in relative.parts):
        return False
    if path.suffix.lower() in SKIP_SUFFIXES:
        return False
    return path.is_file()


def read_text(path: Path) -> str | None:
    try:
        data = path.read_bytes()
    except OSError:
        return None
    if b"\x00" in data[:4096]:
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        try:
            return data.decode("utf-8", errors="replace")
        except Exception:
            return None


def allowed(relative: str, value: str) -> bool:
    return value in ALLOWLIST.get(relative, set())


def main() -> int:
    hits: list[str] = []
    for path in sorted(ROOT.rglob("*")):
        if not should_scan(path):
            continue
        text = read_text(path)
        if text is None:
            continue
        relative = str(path.relative_to(ROOT)).replace("\\", "/")
        for line_number, line in enumerate(text.splitlines(), start=1):
            for name, pattern in PATTERNS.items():
                for match in pattern.finditer(line):
                    value = match.group(0)
                    if allowed(relative, value):
                        continue
                    excerpt = line.strip()
                    if len(excerpt) > 180:
                        excerpt = f"{excerpt[:177]}..."
                    hits.append(f"{relative}:{line_number}: {name}: {excerpt}")

    if hits:
        print("Privacy scan found local or sensitive-looking strings:")
        for hit in hits:
            print(hit)
        return 1
    print("PASS: privacy scan found no local machine or experiment identifiers")
    return 0


if __name__ == "__main__":
    sys.exit(main())
