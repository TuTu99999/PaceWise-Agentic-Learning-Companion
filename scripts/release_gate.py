"""Run the same blocking release checks as CI from a clean checkout.

Usage:
    python scripts/release_gate.py --install

Python, Node.js, Docker and Trivy must already be available on PATH. The
``--install`` option installs the exact Python and npm dependency sets before
running the checks.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend" / "pacewise"
LMS = ROOT / "lms-simulator"


def run(*command: str, cwd: Path = ROOT, env: dict[str, str] | None = None) -> None:
    print(f"\n> {' '.join(command)}", flush=True)
    subprocess.run(command, cwd=cwd, env=env, check=True)  # noqa: S603


def require(executable: str) -> str:
    resolved = shutil.which(executable)
    if not resolved:
        raise SystemExit(f"Required executable is not on PATH: {executable}")
    return resolved


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--install", action="store_true")
    parser.add_argument(
        "--skip-container-scan",
        action="store_true",
        help="Local diagnostic only; CI never skips image scanning.",
    )
    args = parser.parse_args()

    python = sys.executable
    npm = require("npm.cmd" if os.name == "nt" else "npm")
    test_env = os.environ | {
        "APP_ENV": "test",
        "OPENAI_API_KEY": "test-key",
        "PYTHONUTF8": "1",
    }
    node_env = os.environ | {"NODE_OPTIONS": "--max-old-space-size=1536"}

    if args.install:
        run(python, "-m", "pip", "install", "--require-hashes", "-r", "requirements.lock")
        run(npm, "ci", "--no-audit", "--no-fund", cwd=FRONTEND)

    run(
        python,
        "-m",
        "ruff",
        "check",
        "src/",
        "evals/",
        "tests/",
        "lms-simulator/app/",
        "lms-simulator/tests/",
        "scripts/release_gate.py",
        "scripts/migrate_database.py",
        "scripts/migrate_course_materials_to_s3.py",
        "scripts/evaluate_plan_background.py",
        "scripts/evaluate_plan_personas.py",
        "scripts/benchmark_replan_architecture.py",
        "--no-cache",
    )
    run(
        python,
        "-m",
        "pytest",
        "tests/",
        "-q",
        "--cov=src",
        "--cov-report=term-missing",
        "--cov-fail-under=83",
        env=test_env,
    )
    run(python, "-m", "evals.run_agent_eval", env=test_env)
    run(python, "-m", "evals.run_manual_evidence", env=test_env)
    run(python, "-m", "pytest", "tests/", "-q", cwd=LMS, env=test_env)
    run(npm, "test", cwd=FRONTEND, env=node_env)
    run(npm, "run", "typecheck", cwd=FRONTEND, env=node_env)
    run(npm, "run", "build", cwd=FRONTEND, env=node_env)
    run(
        python,
        "-m",
        "pip_audit",
        "--disable-pip",
        "--no-deps",
        "-r",
        "requirements.lock",
    )
    run(npm, "audit", "--omit=dev", "--audit-level=high", cwd=FRONTEND)

    if not args.skip_container_scan:
        docker = require("docker")
        trivy = require("trivy")
        images = (
            ("pacewise-backend:release-gate", "Dockerfile"),
            ("pacewise-frontend:release-gate", "frontend/pacewise/Dockerfile"),
        )
        for image, dockerfile in images:
            run(docker, "build", "--file", dockerfile, "--tag", image, ".")
            run(
                trivy,
                "image",
                "--exit-code",
                "1",
                "--ignore-unfixed",
                "--severity",
                "HIGH,CRITICAL",
                image,
            )

    print("\nRelease gate passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
