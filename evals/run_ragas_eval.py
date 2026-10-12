"""Run semantic RAGAS metrics on at least 100 labeled PaceWise samples."""

from __future__ import annotations

import argparse
import json
import math
import os
import re
from pathlib import Path
from typing import Any

QUALITY_THRESHOLDS = {
    "faithfulness": 0.8,
    "answer_relevancy": 0.9,
    "llm_context_precision_with_reference": 0.7,
    "context_recall": 0.7,
}


def load_samples(path: Path, *, min_samples: int = 100) -> list[dict[str, Any]]:
    samples = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(samples) < min_samples:
        raise ValueError(f"RAGAS requires at least {min_samples} samples; received {len(samples)}")
    required = {"user_input", "response", "retrieved_contexts", "reference"}
    questions = set()
    for index, sample in enumerate(samples):
        missing = required - sample.keys()
        if missing:
            raise ValueError(f"sample {index} is missing {sorted(missing)}")
        if not isinstance(sample["retrieved_contexts"], list) or not all(
            isinstance(text, str) and text.strip() for text in sample["retrieved_contexts"]
        ):
            raise ValueError(f"sample {index} has invalid contexts")
        if not all(
            isinstance(sample[key], str) and sample[key].strip() for key in ("user_input", "response", "reference")
        ):
            raise ValueError(f"sample {index} has empty text")
        normalized_question = " ".join(sample["user_input"].casefold().split())
        if normalized_question in questions:
            raise ValueError(f"sample {index} duplicates a question; do not inflate the sample count")
        questions.add(normalized_question)
    return samples


def run(samples: list[dict[str, Any]], *, pilot: bool = False) -> dict[str, Any]:
    from src.agents.llm import get_agent_llm
    from src.agents.telemetry import collect_model_usage
    from src.config import get_settings

    settings = get_settings()
    if not settings.openai_api_key:
        raise RuntimeError("Configured LLM credentials are required for RAGAS judge calls")
    if pilot and not 3 <= len(samples) <= 12:
        raise ValueError("Pilot requires 3 to 12 samples to bound evaluation cost")
    if not pilot and len(samples) < 100:
        raise ValueError("Release evaluation requires at least 100 samples")
    os.environ["RAGAS_DO_NOT_TRACK"] = "true"
    try:
        from datasets import Dataset
        from langchain_core.embeddings import Embeddings
        from ragas import evaluate
        from ragas.embeddings import LangchainEmbeddingsWrapper
        from ragas.llms import LangchainLLMWrapper
        from ragas.metrics import Faithfulness, LLMContextPrecisionWithReference, LLMContextRecall, ResponseRelevancy
        from ragas.run_config import RunConfig
    except ImportError as exc:
        raise RuntimeError(
            "RAGAS is an optional online evaluation. Run it only in a separately "
            "audited evaluation environment; it is intentionally excluded from "
            "the production and deterministic-CI dependency set."
        ) from exc

    def semantic_text(text: str) -> str:
        value = re.sub(r"\\[()]", " ", str(text))
        value = re.sub(r"\\(?:subseteq|times|in|notin|ne|forall)", " ", value)
        value = re.sub(r"[^\w\sÀ-ỹ?]", " ", value, flags=re.UNICODE)
        return " ".join(value.split())

    class LocalEmbeddings(Embeddings):
        def __init__(self):
            from fastembed import TextEmbedding

            # RAGAS compares an answer-derived question with the original
            # question. Use a stronger multilingual paraphrase encoder than the
            # latency-oriented production retriever.
            self._embedding_model = TextEmbedding(
                model_name="sentence-transformers/paraphrase-multilingual-mpnet-base-v2",
                cache_dir="./data/models/ragas-mpnet",
                threads=1,
            )

        @staticmethod
        def _semantic_text(text: str) -> str:
            # RAG answers preserve LaTeX for the UI, while generated reverse
            # questions may use plain notation. Presentation markup must not
            # dominate semantic similarity in a multilingual relevancy metric.
            return semantic_text(text)

        def embed_documents(self, texts):
            normalized = [self._semantic_text(text) for text in texts]
            return [vector.tolist() for vector in self._embedding_model.embed(normalized)]

        def embed_query(self, text):
            return self.embed_documents([text])[0]

    class MultilingualResponseRelevancy(ResponseRelevancy):
        def calculate_similarity(self, question: str, generated_questions: list[str]):
            # Apply normalization here as well as in the embedding adapter.
            # Some RAGAS versions wrap or replace the metric embedder during
            # evaluation; the metric contract must remain stable either way.
            return super().calculate_similarity(
                semantic_text(question),
                [semantic_text(item) for item in generated_questions],
            )

    config = RunConfig(timeout=90, max_retries=0, max_workers=1)
    judge = LangchainLLMWrapper(
        get_agent_llm(
            model=settings.llm_fast_model or settings.model_name,
            temperature=0,
            timeout=45,
            max_retries=0,
            max_tokens=2048,
        ),
        run_config=config,
    )
    embeddings = LangchainEmbeddingsWrapper(LocalEmbeddings())
    response_relevancy = MultilingualResponseRelevancy(llm=judge, embeddings=embeddings, strictness=1)
    response_relevancy.question_generation.instruction += (
        " Generate the question in the same language as the answer. Preserve the domain terminology and notation."
    )
    metric_objects = [
        Faithfulness(llm=judge),
        # The configured OpenAI-compatible gateway returns one generation per
        # request. Declare that capability honestly instead of asking RAGAS for
        # three and silently receiving one.
        response_relevancy,
        LLMContextPrecisionWithReference(llm=judge),
        LLMContextRecall(llm=judge),
    ]
    with collect_model_usage() as usage:
        result = evaluate(
            Dataset.from_list(samples),
            metrics=metric_objects,
            llm=judge,
            embeddings=embeddings,
            run_config=config,
            raise_exceptions=False,
            show_progress=False,
        )
    frame = result.to_pandas()
    metrics, coverage = {}, {}
    thresholds = QUALITY_THRESHOLDS
    for metric in metric_objects:
        name = metric.name
        values = [float(value) for value in frame[name] if math.isfinite(float(value))] if name in frame else []
        coverage[name] = len(values)
        metrics[name] = round(sum(values) / len(values), 4) if values else None
    per_sample = [
        {
            "sample": index + 1,
            **{
                metric.name: round(float(row[metric.name]), 4)
                if metric.name in frame and math.isfinite(float(row[metric.name]))
                else None
                for metric in metric_objects
            },
        }
        for index, (_, row) in enumerate(frame.iterrows())
    ]
    quality_passed = all(
        coverage[name] == len(samples) and metrics[name] >= thresholds.get(name, 0.7) for name in metrics
    )
    pricing_configured = max(settings.llm_input_cost_per_million, settings.llm_output_cost_per_million) > 0
    return {
        "sample_count": len(samples),
        "evaluation_mode": "pilot" if pilot else "release",
        "metrics": metrics,
        "thresholds": thresholds,
        "scored_samples": coverage,
        "per_sample": per_sample,
        "quality_passed": quality_passed,
        "passed": quality_passed and not pilot,
        "usage": {
            "input_tokens": usage.input_tokens,
            "output_tokens": usage.output_tokens,
            "estimated_cost_usd": usage.estimated_cost_usd if pricing_configured else None,
            "pricing_configured": pricing_configured,
            "missing_usage": usage.missing_usage,
        },
        "limitations": ["Pilot cannot establish release quality or 1000-user capacity."] if pilot else [],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path, help="JSONL produced from real PaceWise QA traces")
    parser.add_argument("--output", type=Path, default=Path("evals/reports/ragas-latest.json"))
    parser.add_argument(
        "--pilot", action="store_true", help="Explicit small 3-12 sample check; never passes the release gate"
    )
    args = parser.parse_args()
    report = run(load_samples(args.input, min_samples=3 if args.pilot else 100), pilot=args.pilot)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["quality_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
