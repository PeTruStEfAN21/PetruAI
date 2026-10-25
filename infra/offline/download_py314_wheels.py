#!/usr/bin/env python3
"""
Downloads Python 3.14 wheels for PetruAI offline manifest.
Target folder: infra/offline/wheels/py314/
"""
import subprocess
import sys
import os
from pathlib import Path

PACKAGES = [
    # web / API
    "fastapi", "uvicorn[standard]", "starlette", "flask", "django", "djangorestframework",
    "pydantic", "pydantic-settings", "python-multipart", "jinja2", "httpx", "requests", "websockets", "aiofiles",
    # date / stocare
    "sqlalchemy", "alembic", "psycopg[binary]", "asyncpg", "aiosqlite", "redis", "supabase",
    # auth / securitate
    "passlib[bcrypt]", "bcrypt", "pyjwt", "python-dotenv", "cryptography",
    # CLI / util
    "typer", "click", "rich", "pyyaml", "tomli-w", "orjson", "python-dateutil", "pillow",
    # test / calitate
    "pytest", "pytest-asyncio", "pytest-cov", "hypothesis", "ruff", "black", "mypy",
    # date / ML ușor
    "numpy", "pandas", "matplotlib",
    # agentul însuși (dependențele pachetului petru)
    "prompt_toolkit", "openai", "watchdog", "tree-sitter", "tree-sitter-language-pack", "sqlite-vec", "huggingface_hub", "tiktoken", "tomlkit", "platformdirs"
]

OUTPUT_DIR = Path("infra/offline/wheels/py314")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

def main():
    print(f"Downloading wheels for {len(PACKAGES)} packages into {OUTPUT_DIR}...")
    success = []
    failed = []
    
    for pkg in PACKAGES:
        print(f"--> pip download: {pkg}")
        cmd = [
            sys.executable, "-m", "pip", "download",
            "--dest", str(OUTPUT_DIR),
            "--only-binary=:all:",
            pkg
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode == 0:
            success.append(pkg)
            print(f"    [OK] {pkg}")
        else:
            # Fallback without --only-binary in case pure python sdist or platform-agnostic
            cmd_fallback = [
                sys.executable, "-m", "pip", "download",
                "--dest", str(OUTPUT_DIR),
                pkg
            ]
            res2 = subprocess.run(cmd_fallback, capture_output=True, text=True)
            if res2.returncode == 0:
                success.append(pkg)
                print(f"    [OK-sdist/any] {pkg}")
            else:
                failed.append((pkg, res.stderr.strip()[:200]))
                print(f"    [FAIL] {pkg}: {res.stderr.strip()[:100]}")
                
    wheel_files = list(OUTPUT_DIR.glob("*"))
    total_size_mb = sum(f.stat().st_size for f in wheel_files) / (1024 * 1024)
    
    print("\n" + "="*60)
    print("DOWNLOAD SUMMARY (Python 3.14 Wheels)")
    print("="*60)
    print(f"Total files in {OUTPUT_DIR}: {len(wheel_files)}")
    print(f"Total size: {total_size_mb:.1f} MB")
    print(f"Succeeded packages: {len(success)} / {len(PACKAGES)}")
    print(f"Failed packages: {len(failed)}")
    if failed:
        for p, err in failed:
            print(f"  - {p}: {err}")
    print("="*60)
    
    # Save report
    with open("infra/offline/wheels_py314_report.json", "w", encoding="utf-8") as f:
        import json
        json.dump({
            "total_files": len(wheel_files),
            "total_size_mb": total_size_mb,
            "success": success,
            "failed": failed
        }, f, indent=2)

if __name__ == "__main__":
    main()
