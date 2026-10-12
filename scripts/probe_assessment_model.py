"""Minimal connectivity diagnostic. Never print credentials or provider response bodies."""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from langchain_core.messages import HumanMessage  # noqa: E402

from src.agents.llm import get_agent_llm  # noqa: E402

start = time.perf_counter()
try:
    llm = get_agent_llm(temperature=0)
    result = llm.invoke([HumanMessage(content="Reply OK.")])
    print(
        {
            "status": "responded",
            "model": llm.model_name,
            "response_type": type(result.content).__name__,
            "length": len(str(result.content)),
        }
    )
except Exception as exc:
    print({"error_type": type(exc).__name__, "http_status": getattr(exc, "status_code", None)})
print({"elapsed_seconds": round(time.perf_counter() - start, 2)})
