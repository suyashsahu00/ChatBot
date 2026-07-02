"""
Report Builder for RAG offline evaluation runs.
Creates formatted JSON and Markdown summaries, mapping cases to PASS/FAIL/SKIPPED status.
"""

import os
import json
import time
from typing import Optional


def classify_case_status(res: dict) -> tuple[str, list[str]]:
    """
    Classifies a single evaluation case result into PASS, FAIL, or SKIPPED
    and returns a list of failure/skip reasons.
    """
    reasons = []
    
    # 1. Deterministic checks
    if res.get("context_recall", 0.0) < 0.80:
        reasons.append("Low Recall")
    if res.get("context_precision", 0.0) < 0.80:
        reasons.append("Low Precision")
    if res.get("attribution_correctness", 0.0) < 1.0:
        reasons.append("Attribution Mismatch")
    if res.get("keyword_match", 0.0) < 0.70:
        reasons.append("Low Keyword Match")
    if res.get("answer_keyword_match", 0.0) < 0.70:
        reasons.append("Low Answer Keyword Match")

    # 2. Judge checks
    if res.get("judge_skipped", False):
        reasons.append("Judge Skipped")
    elif not res.get("judge_passed", False):
        reasons.append("Judge Failed")

    # 3. Status logic
    deterministic_fail = any(
        r in reasons
        for r in ("Low Recall", "Low Precision", "Attribution Mismatch", "Low Keyword Match", "Low Answer Keyword Match")
    )
    
    if deterministic_fail or "Judge Failed" in reasons:
        status = "FAIL"
    elif "Judge Skipped" in reasons:
        status = "SKIPPED"
    else:
        status = "PASS"

    return status, reasons


def build_markdown_report(metrics: dict, timestamp: str) -> str:
    """Generate a clean, readable Markdown report for human review."""
    lines = [
        f"# RAG Evaluation Run Report - {timestamp}",
        "",
        "## 1. Aggregate Metrics Summary",
        "",
        "| Metric | Score / Value |",
        "| --- | --- |",
        f"| Average Recall | {metrics['average_recall']:.2f} |",
        f"| Average Precision | {metrics['average_precision']:.2f} |",
        f"| Average Attribution Correctness | {metrics['average_attribution_correctness']:.2f} |",
        f"| Average Keyword Match | {metrics['average_keyword_match']:.2f} |",
        f"| Average Answer Keyword Match | {metrics['average_answer_keyword_match']:.2f} |",
        f"| Average Judge Score | {metrics['average_judge_score']:.2f} |",
        f"| Judge Pass Rate | {metrics['judge_pass_rate']:.2f} |",
        "",
        "## 2. Per-Case Human Review Table",
        "",
        "| Status | Query | Expected Doc | Recall | Precision | Attrib | KW Match | Judge Score | Reasons |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]

    failed_skipped_blocks = []

    for idx, case in enumerate(metrics["results"]):
        status = case["status"]
        reasons_str = ", ".join(case["reasons"]) if case["reasons"] else "None"
        
        lines.append(
            f"| **{status}** | {case['query']} | {case['expected_attachment_id']} | "
            f"{case['context_recall']:.2f} | {case['context_precision']:.2f} | "
            f"{case['attribution_correctness']:.2f} | {case['keyword_match']:.2f} | "
            f"{case['judge_score']:.2f} | {reasons_str} |"
        )

        if status in ("FAIL", "SKIPPED"):
            failed_skipped_blocks.append(
                f"### Case {idx + 1}: {status}\n"
                f"- **Query**: {case['query']}\n"
                f"- **Expected Attachment ID**: {case['expected_attachment_id']}\n"
                f"- **Reasons**: {reasons_str}\n"
                f"- **Detail**: Recall={case['context_recall']:.2f}, Precision={case['context_precision']:.2f}, "
                f"Attribution={case['attribution_correctness']:.2f}, KW Match={case['keyword_match']:.2f}, "
                f"Judge Score={case['judge_score']:.2f} (Reason: {case.get('judge_reason', 'N/A')})\n"
            )

    lines.append("")
    lines.append("## 3. Failed and Skipped Cases Section")
    lines.append("")
    if failed_skipped_blocks:
        lines.extend(failed_skipped_blocks)
    else:
        lines.append("No failed or skipped cases detected! All checks passed perfectly.")
        lines.append("")

    lines.extend([
        "## 4. Performance & Operational Summary",
        "",
        f"- **Average Retrieval Latency**: {metrics['average_retrieval_latency_ms']:.2f} ms",
        f"- **Average Generation Latency**: {metrics['average_generation_latency_ms']:.2f} ms",
        f"- **Average Total Latency**: {metrics['average_total_latency_ms']:.2f} ms",
        f"- **Average Estimated Cost**: ${metrics['average_estimated_cost_usd']:.6f} USD",
        "",
    ])

    return "\n".join(lines)


def save_report_runs(metrics: dict, output_dir: Optional[str] = None) -> tuple[str, str]:
    """
    Saves the JSON and Markdown report outputs to the eval_runs directory on disk.
    Creates directories automatically if they do not exist.
    """
    if not output_dir:
        output_dir = os.path.join("app", "services", "retrieval", "eval_runs")

    os.makedirs(output_dir, exist_ok=True)
    
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    json_filename = f"eval_run_{timestamp}.json"
    md_filename = f"eval_run_{timestamp}.md"

    json_path = os.path.join(output_dir, json_filename)
    md_path = os.path.join(output_dir, md_filename)

    # Compile Markdown content
    md_content = build_markdown_report(metrics, timestamp)

    # Save Markdown report
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md_content)

    # Save JSON report
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2)

    return os.path.abspath(json_path), os.path.abspath(md_path)
