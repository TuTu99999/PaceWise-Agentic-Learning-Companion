#!/usr/bin/env python3
"""
Shared AI hook logger — works with Claude Code, Gemini CLI, Codex, Cursor, Copilot.
Reads JSON from stdin, normalizes to common format, appends to .ai-log/session.jsonl
"""

import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

VN_TZ = timezone(timedelta(hours=7))

SECRET_PATTERNS = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bB73[A-Za-z0-9]{20,}\b"),
    re.compile(
        r"(?im)^(\s*(?:OPENAI_API_KEY|LANGSMITH_API_KEY|GOOGLE_CLIENT_SECRET|SESSION_SECRET)\s*=)\s*\S+"
    ),
)


def redact(value):
    """Remove common credentials while preserving useful hook context."""
    if isinstance(value, str):
        result = value
        for pattern in SECRET_PATTERNS:
            result = pattern.sub(
                lambda match: f"{match.group(1)}[REDACTED]" if match.lastindex else "[REDACTED]",
                result,
            )
        return result
    if isinstance(value, dict):
        return {key: redact(item) for key, item in value.items()}
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


def git(cmd):
    try:
        return subprocess.check_output(cmd, shell=True, text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return ""


def detect_tool(data: dict) -> str:
    """Detect which AI tool sent this hook event.

    Priority:
      1. --tool=NAME CLI argument (cross-platform: works in cmd.exe, PowerShell, bash)
      2. AI_TOOL_NAME env var (legacy, bash-only when set inline)
      3. Heuristics from payload shape
    """
    for arg in sys.argv[1:]:
        if arg.startswith("--tool="):
            return arg.split("=", 1)[1].lower()
    tool_env = os.environ.get("AI_TOOL_NAME", "").lower()
    if tool_env:
        return tool_env
    # Heuristics
    if "transcript_path" in data:
        return "codex"
    if data.get("hook_event_name", "").startswith(("Before", "After", "Session", "Pre", "Notification")):
        return "gemini"
    if data.get("hook_event_name", "")[0:1].islower():
        # camelCase event names → Cursor or Copilot
        if "workspace_roots" in data:
            return "cursor"
        if "toolName" in data:
            return "copilot"
    if "hook_event_name" in data:
        return "claude"
    return "unknown"


def normalize(data: dict, tool: str) -> dict | None:
    """Normalize tool-specific payload to common log entry."""
    event = data.get("hook_event_name") or data.get("event", "")
    ts = datetime.now(VN_TZ).isoformat()

    # Resolve repo from git origin. When cwd is not a git working tree (or
    # origin isn't set), skip the event entirely — these entries can't be
    # tied back to a team on the server and would just clutter the pending
    # queue forever.
    origin = git("git remote get-url origin")
    if not origin:
        return None
    repo = origin.rstrip("/").split("/")[-1]
    if repo.endswith(".git"):
        repo = repo[:-4]

    base = {
        "ts": ts,
        "tool": tool,
        "event": event,
        "session_id": (data.get("session_id") or data.get("conversation_id") or data.get("generation_id") or ""),
        "model": data.get("model", ""),
        "repo": repo,
        "branch": git("git rev-parse --abbrev-ref HEAD"),
        "commit": git("git rev-parse --short HEAD"),
        "student": git("git config user.email"),
    }

    if tool == "claude":
        prompt = ""
        # UserPromptSubmit: prompt is at top level
        if event == "UserPromptSubmit":
            prompt = data.get("prompt", "")[:1000]
        # PostToolUse: extract from tool_input
        elif isinstance(data.get("tool_input"), dict):
            prompt = data["tool_input"].get("prompt") or data["tool_input"].get("content") or ""
        base.update(
            {
                "prompt": prompt,
                "tool_name": data.get("tool_name", ""),
                "tool_input": data.get("tool_input") if event != "UserPromptSubmit" else None,
                "tool_response": str(data.get("tool_response", ""))[:500],
            }
        )

    elif tool == "gemini":
        if event == "BeforeAgent":
            prompt = data.get("prompt", "")[:1000]
            base.update({"prompt": prompt})
        else:
            req = data.get("request", {})
            contents = req.get("contents", [])
            prompt = ""
            for c in reversed(contents):
                for part in c.get("parts", []):
                    if part.get("text"):
                        prompt = part["text"][:1000]
                        break
                if prompt:
                    break
            resp = data.get("response", {})
            answer = ""
            try:
                answer = resp["candidates"][0]["content"]["parts"][0]["text"][:500]
            except Exception:
                pass
            base.update({"prompt": prompt, "response_summary": answer})

    elif tool == "codex":
        base.update(
            {
                "prompt": data.get("prompt", "")[:1000],
                "turn_id": data.get("turn_id", ""),
                "transcript_path": data.get("transcript_path", ""),
            }
        )

    elif tool == "cursor":
        base.update(
            {
                "prompt": data.get("prompt", "")[:1000],
                "files_context": data.get("attachments", []),
            }
        )

    elif tool == "copilot":
        base.update(
            {
                "prompt": data.get("prompt", "")[:1000],
                "tool_name": data.get("toolName", ""),
                "tool_args": data.get("toolArgs"),
            }
        )

    # Skip only true noise: no prompt AND no tool-specific payload (tool_input,
    # response_summary, tool_response, tool_args, files_context). Previously
    # this only checked `prompt`, which dropped Claude Bash/Edit events (their
    # tool_input has `command` / `file_path`, not `prompt` or `content`) and
    # any Gemini/Cursor/Copilot turn that carried context but no plain prompt.
    base = redact(base)
    payload_keys = ("prompt", "tool_input", "response_summary", "tool_response", "tool_args", "files_context")
    lifecycle_events = ("Stop", "stop", "SessionEnd", "sessionEnd", "AfterModel")
    has_payload = any(base.get(k) for k in payload_keys)
    if not has_payload and event not in lifecycle_events:
        return None

    return base


def main():
    # Codex `Stop` hooks require valid JSON on stdout when they exit 0. Keep a
    # tool hint before parsing stdin so malformed/empty payloads still receive
    # a valid acknowledgement instead of surfacing a hook error in the app.
    tool_hint = detect_tool({})

    def acknowledge_codex(tool_name: str) -> None:
        if tool_name == "codex":
            print(json.dumps({"continue": True}))

    # Read stdin as UTF-8 explicitly. On Windows, sys.stdin defaults to the
    # system code page (e.g. cp1252), which corrupts non-Latin1 prompts
    # (Vietnamese, CJK, emoji) into mojibake. The hook payload is always UTF-8.
    raw = sys.stdin.buffer.read().decode("utf-8", errors="replace").strip()
    if not raw:
        acknowledge_codex(tool_hint)
        return

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        acknowledge_codex(tool_hint)
        return

    tool = detect_tool(data)
    entry = normalize(data, tool)
    if not entry:
        acknowledge_codex(tool)
        return

    log_dir = Path(os.environ.get("AI_LOG_DIR", ".ai-log"))
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / "session.jsonl"

    with open(log_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    # Codex lifecycle hooks only accept their documented control fields.
    # `Stop` specifically requires JSON on stdout when the hook exits 0.
    if tool == "codex":
        acknowledge_codex(tool)
    else:
        # Other integrations only require a valid JSON acknowledgement.
        print(json.dumps({"status": "logged"}))


if __name__ == "__main__":
    main()
