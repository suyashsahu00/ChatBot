"""
LLM-as-a-Judge module for RAG quality evaluation.
Includes structured prompts and JSON parsing helpers.
"""

import json
import re
import asyncio
from app.core.config import settings


def parse_judge_json(text: str) -> dict:
    """Extract and parse structured JSON result from LLM conversational output."""
    try:
        # Extract JSON from code block markdown if present
        match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if match:
            text = match.group(1)
        cleaned = text.strip()
        return json.loads(cleaned)
    except Exception as e:
        return {
            "score": 0.0,
            "passed": False,
            "reason": f"Failed to parse LLM judge response: {str(e)}",
            "skipped": False,
        }


async def judge_faithfulness(query: str, context: str, answer: str) -> dict:
    """
    Evaluate if the generated answer is faithful to the context (no hallucinations).
    Returns {"score": float, "passed": bool, "reason": str, "skipped": bool}.
    """
    if not (settings.openai_api_key or settings.google_api_key or settings.openrouter_api_key):
        return {
            "score": 0.0,
            "passed": False,
            "reason": "Judge skipped (API key missing)",
            "skipped": True,
        }

    prompt = (
        "You are an expert evaluator. Evaluate if the given Answer is faithful to the context (i.e. does not hallucinate or fabricate facts outside the context).\n\n"
        f"Context:\n{context}\n\n"
        f"Query:\n{query}\n\n"
        f"Answer:\n{answer}\n\n"
        "Output ONLY a raw JSON object containing these keys (do not include any other conversational text or markdown packaging):\n"
        '{"score": 1.0 (if faithful) or 0.0 (if not), "passed": true or false, "reason": "short explanation"}'
    )

    try:
        from app.services.llm.service import generate_response
        loop = asyncio.get_event_loop()
        response_text = await loop.run_in_executor(
            None, generate_response, [{"role": "user", "content": prompt}]
        )
        parsed = parse_judge_json(response_text)
        parsed["skipped"] = False
        return parsed
    except Exception as e:
        return {
            "score": 0.0,
            "passed": False,
            "reason": f"Judge execution error: {str(e)}",
            "skipped": True,
        }


async def judge_answer_relevance(query: str, answer: str) -> dict:
    """
    Evaluate if the generated answer is directly relevant to the user query.
    Returns {"score": float, "passed": bool, "reason": str, "skipped": bool}.
    """
    if not (settings.openai_api_key or settings.google_api_key or settings.openrouter_api_key):
        return {
            "score": 0.0,
            "passed": False,
            "reason": "Judge skipped (API key missing)",
            "skipped": True,
        }

    prompt = (
        "You are an expert evaluator. Evaluate if the given Answer is directly relevant to the user query.\n\n"
        f"Query:\n{query}\n\n"
        f"Answer:\n{answer}\n\n"
        "Output ONLY a raw JSON object containing these keys (do not include any other conversational text or markdown packaging):\n"
        '{"score": 1.0 (if relevant) or 0.0 (if not), "passed": true or false, "reason": "short explanation"}'
    )

    try:
        from app.services.llm.service import generate_response
        loop = asyncio.get_event_loop()
        response_text = await loop.run_in_executor(
            None, generate_response, [{"role": "user", "content": prompt}]
        )
        parsed = parse_judge_json(response_text)
        parsed["skipped"] = False
        return parsed
    except Exception as e:
        return {
            "score": 0.0,
            "passed": False,
            "reason": f"Judge execution error: {str(e)}",
            "skipped": True,
        }
