#!/usr/bin/env python3
"""
Secret scanner — run before any git push.
Exits 1 if anything suspicious is found.
"""

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SKIP_FILES = {".env", ".env.example"}
SKIP_DIRS  = {"node_modules", "__pycache__", "dist", ".git", "scripts"}
SCAN_EXTS  = {".py", ".js", ".jsx", ".ts", ".tsx",
              ".yml", ".yaml", ".json", ".txt", ".md",
              ".sh", ".cfg", ".ini", ".toml", "Dockerfile"}

# Patterns that should never appear in committed files
PATTERNS = [
    # Real key fragments from this project
    (r"7CuGrT5J",                             "CrowdSec API key fragment"),
    (r"sk-proj-",                             "OpenAI API key"),
    (r"7eea4c1d|ee584044|9129e0e0",           "Proxmox token UUID fragments"),
    (r"CCccCC",                               "UniFi password fragment"),
    # Generic high-entropy patterns
    (r"(?i)(api[_-]?key|secret|password|token)\s*=\s*['\"][A-Za-z0-9+/=!@#$%^&*]{12,}['\"]",
                                              "Inline credential assignment"),
    # Hardcoded internal IPs as string literals (not inside comments)
    (r"['\"]https?://192\.168\.",             "Hardcoded internal IP as string literal"),
    # Gate code in source
    (r"security_gate_code\s*[:=]\s*['\"]?\d{4,}['\"]?(?!\s*$)",
                                              "Hardcoded gate code value"),
]

IGNORE_IN = {
    # .env.example is intentionally showing placeholder structure
    ".env.example",
    # Check scripts themselves reference pattern strings, not real values
    "check-secrets.py",
    "check-secrets.sh",
}


def should_scan(path: str) -> bool:
    rel = os.path.relpath(path, ROOT)
    parts = rel.split(os.sep)
    if any(d in SKIP_DIRS for d in parts[:-1]):
        return False
    fname = parts[-1]
    if fname in SKIP_FILES or fname in IGNORE_IN:
        return False
    ext = os.path.splitext(fname)[1] or fname  # for bare "Dockerfile"
    return ext in SCAN_EXTS or fname.startswith("Dockerfile")


def scan_file(path: str) -> list[tuple[int, str, str]]:
    hits = []
    try:
        with open(path, encoding="utf-8", errors="ignore") as f:
            for lineno, line in enumerate(f, 1):
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                for pattern, label in PATTERNS:
                    if re.search(pattern, line):
                        hits.append((lineno, label, stripped[:120]))
    except OSError:
        pass
    return hits


def main():
    findings = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fname in filenames:
            fpath = os.path.join(dirpath, fname)
            if not should_scan(fpath):
                continue
            hits = scan_file(fpath)
            for lineno, label, snippet in hits:
                rel = os.path.relpath(fpath, ROOT)
                findings.append((rel, lineno, label, snippet))

    if findings:
        print(f"\n❌  SECRET SCAN FAILED — {len(findings)} issue(s) found:\n")
        for rel, lineno, label, snippet in findings:
            print(f"  {rel}:{lineno}  [{label}]")
            print(f"    {snippet}\n")
        print("Fix all issues before pushing to GitHub.\n")
        sys.exit(1)
    else:
        print("✅  Secret scan passed — nothing sensitive found in source files.")
        sys.exit(0)


if __name__ == "__main__":
    main()
