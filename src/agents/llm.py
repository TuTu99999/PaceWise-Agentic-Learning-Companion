"""
Khởi tạo và cấu hình LLM cho các Agent trong hệ thống.
"""

import os

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

from src.agents.telemetry import ModelUsageCallback
from src.config import get_settings
from src.services.model_policy import ControlledModel, model_tier

load_dotenv()

# Native tracing exports whole graph state. Only our metadata-only tracing is allowed.
os.environ["LANGCHAIN_TRACING_V2"] = "false"
os.environ["LANGSMITH_TRACING"] = "false"


def get_agent_llm(
    model: str | None = None,
    temperature: float = 0.7,
    *,
    timeout: float | None = None,
    max_retries: int = 1,
    max_tokens: int | None = None,
    task: str | None = None,
    complexity: str = "simple",
    cache_scope: str | None = None,
) -> ChatOpenAI | ControlledModel:
    """
    Trả về đối tượng ChatOpenAI được cấu hình từ .env.
    Tự động chọn mô hình hoạt động phù hợp nhất với proxy endpoint.
    """
    settings = get_settings()

    api_key = settings.openai_api_key or os.getenv("OPENAI_API_KEY", "")
    base_url = settings.openai_base_url or os.getenv("OPENAI_BASE_URL", "")

    # Tự động map localhost sang host.docker.internal khi chạy trong Docker container
    if base_url and ("localhost" in base_url or "127.0.0.1" in base_url):
        if os.path.exists("/.dockerenv") or os.path.exists("/proc/1/cgroup"):
            base_url = base_url.replace("localhost", "host.docker.internal").replace(
                "127.0.0.1", "host.docker.internal"
            )

    # Tham số gọi trực tiếp và MODEL_NAME runtime có độ ưu tiên cao nhất.
    # Proxy screensavers chỉ nhận model đã định tuyến; không dùng một model
    # riêng của môi trường phát triển làm fallback chung cho production.
    runtime_model = os.getenv("MODEL_NAME", "")
    if model:
        chosen_model = model
    elif runtime_model and not runtime_model.startswith("your-"):
        chosen_model = runtime_model
    elif "screensavers-nutten" in base_url:
        chosen_model = "cx/gpt-5.6-luna"
    else:
        chosen_model = os.getenv("MODEL") or settings.model_name or "cx/gpt-5.6-luna"

    tier = model_tier(task or "llm", complexity)
    if task and not model:
        routed = getattr(settings, "llm_reasoning_model" if tier == "reasoning" else "llm_fast_model", "")
        chosen_model = routed or chosen_model
    instance = ChatOpenAI(
        model=chosen_model,
        api_key=api_key,
        base_url=base_url,
        temperature=temperature,
        timeout=timeout if timeout is not None else settings.llm_timeout_seconds,
        max_tokens=max_tokens if max_tokens is not None else settings.llm_max_output_tokens,
        max_retries=max_retries,
        callbacks=[ModelUsageCallback()],
    )
    return ControlledModel(instance, settings, task=task, tier=tier, model_name=chosen_model,
                           cache_scope=f"{cache_scope}:temp={temperature}" if cache_scope else None) if task else instance
