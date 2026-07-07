# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

"""CogniX automatic dataset builder.

The builder derives deterministic, reviewable dataset examples from provided
documents. It does not call a model, export files, upload datasets, or start
training jobs.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any


COGNIX_DATASET_BUILDER_VERSION = "cognix_dataset_builder_v1"
COGNIX_SYNTHETIC_EXAMPLE_GENERATOR_VERSION = "cognix_synthetic_example_generator_v1"
COGNIX_DATASET_QUALITY_FILTER_VERSION = "cognix_dataset_quality_filter_v1"
COGNIX_DATASET_EXPORT_SERVICE_VERSION = "cognix_dataset_export_service_v1"

SUPPORTED_FORMATS = {"jsonl", "alpaca_json", "chatml_jsonl"}
SENSITIVE_TERMS = ("secret", "token", "password", "mot de passe", "api key", "private key", "jwt")


def _normalize(value: Any) -> str:
    return " ".join(str(value or "").replace("\r\n", "\n").split()).strip()


def _keywords(text: str) -> set[str]:
    return {
        item.casefold()
        for item in re.findall(r"[a-zA-Z0-9_+-]{4,}", text or "")
        if item.casefold() not in {"avec", "dans", "pour", "that", "this", "from", "have", "will", "document"}
    }


def _sentences(text: str) -> list[str]:
    normalized = _normalize(text)
    if not normalized:
        return []
    chunks = re.split(r"(?<=[.!?])\s+|\n+", normalized)
    return [chunk.strip() for chunk in chunks if len(chunk.strip()) >= 20]


def _estimate_tokens(text: str) -> int:
    return max(1, len(re.findall(r"\S+", text or "")))


def _format_id(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]+", "_", value.strip())[:120].strip("_") or "source"


def build_dataset_builder_blueprint() -> dict[str, Any]:
    return {
        "datasetBuilderVersion": COGNIX_DATASET_BUILDER_VERSION,
        "syntheticExampleGeneratorVersion": COGNIX_SYNTHETIC_EXAMPLE_GENERATOR_VERSION,
        "qualityFilterVersion": COGNIX_DATASET_QUALITY_FILTER_VERSION,
        "exportServiceVersion": COGNIX_DATASET_EXPORT_SERVICE_VERSION,
        "mode": "dry_run_dataset_builder",
        "services": ["DatasetBuilder", "SyntheticExampleGenerator", "DatasetQualityFilter", "ExportService"],
        "pipeline": ["documents", "chunking", "question_generation", "answer_generation", "filtering", "dataset_export"],
        "supportedFormats": sorted(SUPPORTED_FORMATS),
        "policies": {
            "modelGenerationAllowed": False,
            "rawSensitiveExportAllowed": False,
            "frontendDirectDatasetWriteAllowed": False,
            "humanReviewRequiredBeforeTraining": True,
        },
        "sideEffects": {
            "datasetWrite": False,
            "exampleWrite": False,
            "qualityScoreWrite": False,
            "fileWrite": False,
            "datasetExport": False,
            "datasetUpload": False,
            "trainingJob": False,
            "modelLoad": False,
            "generation": False,
            "networkCall": False,
        },
    }


def _document_record(document: dict[str, Any], index: int) -> dict[str, Any]:
    title = _normalize(document.get("title") or document.get("name") or f"Document {index + 1}")[:180]
    source_id = _normalize(document.get("sourceId") or document.get("id") or _format_id(title))[:180]
    text = _normalize(document.get("text") or document.get("content") or document.get("summary") or "")
    source_type = _normalize(document.get("sourceType") or document.get("type") or "document").casefold().replace(" ", "_")
    sensitive_terms = [term for term in SENSITIVE_TERMS if term in text.casefold()]
    return {
        "sourceId": source_id,
        "sourceType": source_type,
        "title": title,
        "text": text,
        "tokenCount": _estimate_tokens(text),
        "sensitiveTerms": sensitive_terms[:8],
        "metadata": document.get("metadata") if isinstance(document.get("metadata"), dict) else {},
    }


def _quality_score(*, chunk: str, objective_terms: set[str], sensitive_terms: list[str]) -> dict[str, Any]:
    terms = _keywords(chunk)
    overlap = sorted(terms & objective_terms)[:12]
    token_count = _estimate_tokens(chunk)
    length_score = 1.0 if 24 <= token_count <= 160 else 0.72 if token_count <= 220 else 0.48
    objective_score = min(1.0, 0.42 + (len(overlap) * 0.14)) if objective_terms else 0.74
    sensitivity_penalty = 0.28 if sensitive_terms else 0.0
    score = round(max(0.0, min(1.0, (length_score * 0.45) + (objective_score * 0.45) + 0.10 - sensitivity_penalty)), 3)
    return {
        "qualityScore": score,
        "qualityLabel": "ready" if score >= 0.72 and not sensitive_terms else "review" if score >= 0.48 else "filtered",
        "matchedObjectiveTerms": overlap,
        "sensitiveTerms": sensitive_terms,
        "tokenCount": token_count,
    }


def _question_from_chunk(chunk: str, *, title: str, objective: str | None) -> str:
    objective_text = _normalize(objective)
    if objective_text:
        return f"Quelle information utile pour {objective_text[:90]} se trouve dans {title} ?"
    first_terms = sorted(_keywords(chunk))[:4]
    suffix = " ".join(first_terms) if first_terms else "ce document"
    return f"Quelle est l'information principale concernant {suffix} ?"


def _example_record(
    *,
    dataset_id: str,
    document: dict[str, Any],
    chunk: str,
    index: int,
    objective: str | None,
    objective_terms: set[str],
    output_format: str,
) -> dict[str, Any]:
    quality = _quality_score(
        chunk = chunk,
        objective_terms = objective_terms,
        sensitive_terms = document["sensitiveTerms"],
    )
    instruction = "Reponds avec une reponse precise et verifiable a partir du contexte fourni."
    question = _question_from_chunk(chunk, title = document["title"], objective = objective)
    example_seed = f"{dataset_id}:{document['sourceId']}:{index}"
    example_id = f"ex_{hashlib.sha256(example_seed.encode('utf-8')).hexdigest()[:18]}"
    metadata = {
        "sourceId": document["sourceId"],
        "sourceType": document["sourceType"],
        "sourceTitle": document["title"],
        "chunkIndex": index,
        "format": output_format,
        "dataUsedPreview": chunk[:240],
        "requiresHumanReview": quality["qualityLabel"] != "ready",
    }
    return {
        "id": example_id,
        "datasetId": dataset_id,
        "instruction": instruction,
        "input": f"Question: {question}\nContexte: {chunk}",
        "output": chunk,
        "metadata": metadata,
        **quality,
        "status": quality["qualityLabel"],
    }


def _preview_jsonl(examples: list[dict[str, Any]], *, limit: int = 5) -> str:
    lines = []
    for example in examples[:limit]:
        lines.append(
            json.dumps(
                {
                    "instruction": example["instruction"],
                    "input": example["input"],
                    "output": example["output"],
                    "metadata": example["metadata"],
                    "quality_score": example["qualityScore"],
                },
                ensure_ascii = False,
            )
        )
    return "\n".join(lines)


def build_dataset_plan(
    *,
    username: str,
    documents: list[dict[str, Any]],
    objective: str | None = None,
    output_format: str | None = None,
    max_examples: int = 50,
    project_id: str | None = None,
) -> dict[str, Any]:
    fmt = str(output_format or "jsonl").strip().lower()
    if fmt not in SUPPORTED_FORMATS:
        fmt = "jsonl"
    safe_max = max(1, min(int(max_examples or 50), 500))
    objective_terms = _keywords(objective or "")
    document_records = [_document_record(item, index) for index, item in enumerate(documents or []) if isinstance(item, dict)]
    dataset_seed = "|".join(f"{item['sourceId']}:{item['tokenCount']}" for item in document_records)
    dataset_hash = hashlib.sha256(f"{username}:{project_id}:{objective}:{dataset_seed}".encode("utf-8")).hexdigest()
    dataset_id = f"ds_{dataset_hash[:24]}"
    examples: list[dict[str, Any]] = []
    for document in document_records:
        for chunk_index, chunk in enumerate(_sentences(document["text"])):
            if len(examples) >= safe_max:
                break
            examples.append(
                _example_record(
                    dataset_id = dataset_id,
                    document = document,
                    chunk = chunk[:1600],
                    index = chunk_index,
                    objective = objective,
                    objective_terms = objective_terms,
                    output_format = fmt,
                )
            )
        if len(examples) >= safe_max:
            break
    ready_examples = [item for item in examples if item["status"] == "ready"]
    review_examples = [item for item in examples if item["status"] == "review"]
    filtered_examples = [item for item in examples if item["status"] == "filtered"]
    sensitive_sources = [item for item in document_records if item["sensitiveTerms"]]
    return {
        "datasetBuilderVersion": COGNIX_DATASET_BUILDER_VERSION,
        "syntheticExampleGeneratorVersion": COGNIX_SYNTHETIC_EXAMPLE_GENERATOR_VERSION,
        "qualityFilterVersion": COGNIX_DATASET_QUALITY_FILTER_VERSION,
        "exportServiceVersion": COGNIX_DATASET_EXPORT_SERVICE_VERSION,
        "mode": "dry_run_dataset_builder",
        "username": username,
        "projectId": project_id,
        "dataset": {
            "datasetId": dataset_id,
            "objective": objective,
            "format": fmt,
            "status": "review_required" if review_examples or sensitive_sources else "ready",
            "exampleCount": len(examples),
            "readyExampleCount": len(ready_examples),
            "reviewExampleCount": len(review_examples),
            "filteredExampleCount": len(filtered_examples),
        },
        "dataSources": [
            {
                "sourceId": item["sourceId"],
                "sourceType": item["sourceType"],
                "title": item["title"],
                "tokenCount": item["tokenCount"],
                "sensitiveTermCount": len(item["sensitiveTerms"]),
            }
            for item in document_records
        ],
        "examples": examples,
        "qualitySummary": {
            "averageQualityScore": round(sum(float(item["qualityScore"]) for item in examples) / max(1, len(examples)), 3),
            "readyExampleCount": len(ready_examples),
            "reviewExampleCount": len(review_examples),
            "filteredExampleCount": len(filtered_examples),
            "sensitiveSourceCount": len(sensitive_sources),
        },
        "exportPlan": {
            "format": fmt,
            "previewJsonl": _preview_jsonl(examples),
            "willWriteFile": False,
            "willUploadDataset": False,
            "requiresHumanReview": bool(review_examples or sensitive_sources),
        },
        "sideEffects": build_dataset_builder_blueprint()["sideEffects"],
    }
