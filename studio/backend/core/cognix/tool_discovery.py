# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

"""Automatic CogniX tool discovery.

This module analyzes project signals and prepares recommendations only. It does
not install tools, execute connectors, read secrets, or call a model.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from core.cognix import tool_registry as cognix_tool_registry


COGNIX_TOOL_DISCOVERY_VERSION = "cognix_tool_discovery_v1"
COGNIX_TOOL_CAPABILITY_REGISTRY_VERSION = "cognix_tool_capability_registry_v1"

DISCOVERABLE_TOOL_CAPABILITIES: list[dict[str, Any]] = [
    {
        "toolId": "calculator",
        "name": "CogniX Calculator",
        "category": "math",
        "capabilities": ["safe_arithmetic", "formula_checking", "physics_numeric_checks"],
        "installHint": "Native CogniX tool; no installation required.",
        "connectorBacked": False,
        "enabledByDefault": True,
    },
    {
        "toolId": "physics-solver",
        "name": "CogniX Physics Solver",
        "category": "physics",
        "capabilities": ["formula_solving", "unit_aware_physics", "mechanics_checks"],
        "installHint": "Native CogniX tool; no installation required.",
        "connectorBacked": False,
        "enabledByDefault": True,
    },
    {
        "toolId": "latex-renderer",
        "name": "CogniX LaTeX Renderer",
        "category": "rendering",
        "capabilities": ["latex_safety_validation", "katex_math_rendering", "markdown_render_packet"],
        "installHint": "Native CogniX tool; no installation required for chat rendering.",
        "connectorBacked": False,
        "enabledByDefault": True,
    },
    {
        "toolId": "python-runtime",
        "name": "Python Runtime",
        "category": "code",
        "capabilities": ["python_execution", "script_validation", "package_checks"],
        "installHint": "Use a local Python runtime and project venv.",
        "connectorBacked": False,
        "enabledByDefault": False,
    },
    {
        "toolId": "python-venv",
        "name": "Python venv",
        "category": "code",
        "capabilities": ["isolated_dependencies", "pip_install_planning"],
        "installHint": "Create a venv before installing project dependencies.",
        "connectorBacked": False,
        "enabledByDefault": False,
    },
    {
        "toolId": "pytorch",
        "name": "PyTorch",
        "category": "ml",
        "capabilities": ["tensor_runtime", "training_runtime", "cuda_runtime_detection"],
        "installHint": "Install the CPU or CUDA build matching the machine.",
        "connectorBacked": False,
        "enabledByDefault": False,
    },
    {
        "toolId": "ollama",
        "name": "Ollama",
        "category": "ml",
        "capabilities": ["local_model_runtime", "model_pull_planning"],
        "installHint": "Use Ollama only after the user validates local model usage.",
        "connectorBacked": False,
        "enabledByDefault": False,
    },
    {
        "toolId": "llama-cpp",
        "name": "llama.cpp",
        "category": "ml",
        "capabilities": ["gguf_runtime", "llama_server_runtime"],
        "installHint": "Use llama.cpp for compatible GGUF models.",
        "connectorBacked": False,
        "enabledByDefault": False,
    },
    {
        "toolId": "rag-indexer",
        "name": "CogniX RAG Indexer",
        "category": "rag",
        "capabilities": ["document_indexing", "source_grounding", "context_retrieval"],
        "installHint": "Use the native CogniX RAG service after user approval.",
        "connectorBacked": False,
        "enabledByDefault": True,
    },
    {
        "toolId": "google-drive",
        "name": "Google Drive",
        "category": "files",
        "capabilities": ["cloud_document_read", "workspace_indexing"],
        "installHint": "Connect Google Drive before reading workspace documents.",
        "connectorBacked": True,
        "enabledByDefault": False,
    },
    {
        "toolId": "gmail",
        "name": "Gmail",
        "category": "communication",
        "capabilities": ["email_search", "draft_planning"],
        "installHint": "Connect Gmail before email search or draft creation.",
        "connectorBacked": True,
        "enabledByDefault": False,
    },
    {
        "toolId": "notion",
        "name": "Notion",
        "category": "productivity",
        "capabilities": ["workspace_pages", "knowledge_capture"],
        "installHint": "Connect Notion before reading or creating workspace notes.",
        "connectorBacked": True,
        "enabledByDefault": False,
    },
    {
        "toolId": "github",
        "name": "GitHub",
        "category": "code",
        "capabilities": ["repository_read", "issue_tracking", "pull_request_workflow"],
        "installHint": "Connect GitHub before repository operations.",
        "connectorBacked": True,
        "enabledByDefault": False,
    },
    {
        "toolId": "microsoft-365",
        "name": "Microsoft 365",
        "category": "enterprise",
        "capabilities": ["office_documents", "teams_context", "sharepoint_indexing"],
        "installHint": "Connect Microsoft 365 through an enterprise connector.",
        "connectorBacked": True,
        "enabledByDefault": False,
    },
    {
        "toolId": "google-workspace",
        "name": "Google Workspace",
        "category": "enterprise",
        "capabilities": ["workspace_docs", "calendar_context", "drive_indexing"],
        "installHint": "Connect Google Workspace through approved connectors.",
        "connectorBacked": True,
        "enabledByDefault": False,
    },
]

PROJECT_NEED_RULES: list[dict[str, Any]] = [
    {
        "needId": "latex_rendering",
        "label": "LaTeX rendering",
        "description": "Projet contenant des formules, documents TeX ou rendu mathematique.",
        "projectTypes": ["math", "maths", "physics", "physique", "research"],
        "keywords": [
            "latex",
            "tex",
            "equation",
            "formula",
            "formule",
            "theorem",
            "algebra",
            "calculus",
            "force",
            "vitesse",
            "ohm",
            "mecanique",
            "physique",
        ],
        "extensions": [".tex", ".bib"],
        "toolIds": ["calculator", "physics-solver", "latex-renderer"],
    },
    {
        "needId": "python_environment",
        "label": "Python environment",
        "description": "Projet Python ou notebook necessitant runtime, pip et venv.",
        "projectTypes": ["code", "python", "developer"],
        "keywords": ["python", "pip", "venv", "fastapi", "script", "notebook", "requirements"],
        "extensions": [".py", ".ipynb", "requirements.txt", "pyproject.toml"],
        "toolIds": ["python-runtime", "python-venv"],
    },
    {
        "needId": "ml_runtime",
        "label": "ML runtime",
        "description": "Projet IA local necessitant PyTorch, Ollama ou llama.cpp.",
        "projectTypes": ["ml", "ai", "ia", "training", "fine-tuning"],
        "keywords": ["ml", "training", "fine-tuning", "qwen", "ollama", "llama.cpp", "pytorch", "cuda", "gguf", "unsloth"],
        "extensions": [".gguf", ".safetensors", ".pt", ".pth"],
        "toolIds": ["pytorch", "ollama", "llama-cpp"],
    },
    {
        "needId": "document_rag",
        "label": "Document RAG",
        "description": "Projet documentaire ou PDF qui beneficie d'indexation et sources internes.",
        "projectTypes": ["rag", "docs", "documents", "school", "university", "business"],
        "keywords": ["pdf", "document", "documents", "rag", "source", "sources", "knowledge", "cours", "indexer"],
        "extensions": [".pdf", ".docx", ".md", ".txt"],
        "toolIds": ["rag-indexer", "google-drive", "notion"],
    },
    {
        "needId": "code_repository",
        "label": "Code repository",
        "description": "Projet code necessitant lecture de depot, issues ou workflow pull request.",
        "projectTypes": ["code", "developer", "software"],
        "keywords": ["github", "git", "repository", "repo", "pull request", "issue", "branche"],
        "extensions": [".gitignore", "package.json", "vite.config.ts", "tsconfig.json"],
        "toolIds": ["github", "codex-secure-agent"],
    },
    {
        "needId": "enterprise_workspace",
        "label": "Enterprise workspace",
        "description": "Projet entreprise avec documents, emails ou espace collaboratif.",
        "projectTypes": ["business", "enterprise", "company", "organisation", "organization"],
        "keywords": ["enterprise", "business", "workspace", "mail", "email", "teams", "sharepoint", "drive", "notion"],
        "extensions": [".docx", ".xlsx", ".pptx"],
        "toolIds": ["google-workspace", "microsoft-365", "google-drive", "gmail", "notion"],
    },
    {
        "needId": "education_workspace",
        "label": "Education workspace",
        "description": "Projet ecole/universite avec cours, devoirs, documents et recherche.",
        "projectTypes": ["school", "university", "education", "student"],
        "keywords": ["school", "university", "devoir", "cours", "exam", "teacher", "student"],
        "extensions": [".pdf", ".docx", ".pptx"],
        "toolIds": ["rag-indexer", "google-drive", "notion"],
    },
]


def _normalize(value: Any) -> str:
    return str(value or "").strip().lower()


def _clean_words(value: Any) -> str:
    return " ".join(str(value or "").replace("_", " ").replace("-", " ").split()).lower()


def _file_signal(file_name: str) -> str:
    lowered = _normalize(file_name)
    if lowered in {"requirements.txt", "pyproject.toml", "package.json", "vite.config.ts", "tsconfig.json", ".gitignore"}:
        return lowered
    dot_index = lowered.rfind(".")
    return lowered[dot_index:] if dot_index >= 0 else lowered


def _tool_lookup() -> dict[str, dict[str, Any]]:
    return {str(tool["toolId"]): deepcopy(tool) for tool in _capability_records()}


def _connector_backed_from_manifest(manifest: dict[str, Any]) -> bool:
    connector = str(manifest.get("connector") or "")
    return not connector.startswith("local-")


def _manifest_risk_level(actions: list[dict[str, Any]]) -> str:
    risk_order = cognix_tool_registry.RISK_ORDER
    risks = [str(action.get("riskLevel") or "low") for action in actions]
    return max(risks or ["low"], key = lambda item: risk_order.get(item, 0))


def _manifest_action_summary(action: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(action.get("id") or ""),
        "mode": str(action.get("mode") or "read"),
        "riskLevel": str(action.get("riskLevel") or "low"),
        "permissions": [str(item) for item in action.get("permissions") or [] if str(item or "").strip()],
        "requiresConfirmation": bool(action.get("requiresConfirmation")),
        "auditRequired": bool(action.get("auditRequired")),
        "sandboxRequired": bool(action.get("sandboxRequired")),
        "secretsRequired": bool(action.get("secretsRequired")),
        "rateLimitKey": str(action.get("rateLimitKey") or ""),
    }


def _merge_manifest_capability(base: dict[str, Any], manifest: dict[str, Any] | None) -> dict[str, Any]:
    record = deepcopy(base)
    if manifest is None:
        record.update(
            {
                "registeredInToolRegistry": False,
                "registryToolEnabled": bool(record.get("enabledByDefault")),
                "connectorId": None,
                "dataIsolation": "none" if not record.get("connectorBacked") else "user",
                "registryActionCount": 0,
                "actionIds": [],
                "registryActions": [],
                "permissions": [],
                "maxRiskLevel": "low",
                "requiresAnyConfirmation": False,
                "requiresAnySandbox": False,
                "requiresAnySecret": False,
                "auditRequired": False,
            }
        )
    else:
        actions = [action for action in manifest.get("actions") or [] if isinstance(action, dict)]
        action_ids = [str(action.get("id") or "") for action in actions if str(action.get("id") or "").strip()]
        permissions = sorted(
            {
                str(permission)
                for action in actions
                for permission in action.get("permissions") or []
                if str(permission or "").strip()
            }
        )
        capabilities = list(record.get("capabilities") or [])
        for action_id in action_ids:
            if action_id not in capabilities:
                capabilities.append(action_id)
        record.update(
            {
                "toolId": str(manifest.get("id") or record.get("toolId") or ""),
                "name": str(manifest.get("name") or record.get("name") or manifest.get("id") or ""),
                "category": str(manifest.get("category") or record.get("category") or "integration"),
                "capabilities": capabilities,
                "registeredInToolRegistry": True,
                "registryToolEnabled": bool(manifest.get("enabled")),
                "connectorId": manifest.get("connector"),
                "connectorBacked": bool(record.get("connectorBacked", _connector_backed_from_manifest(manifest))),
                "enabledByDefault": bool(record.get("enabledByDefault") or manifest.get("enabled")),
                "dataIsolation": str(manifest.get("dataIsolation") or "user"),
                "registryActionCount": len(actions),
                "actionIds": action_ids,
                "registryActions": [_manifest_action_summary(action) for action in actions],
                "permissions": permissions,
                "maxRiskLevel": _manifest_risk_level(actions),
                "requiresAnyConfirmation": any(bool(action.get("requiresConfirmation")) for action in actions),
                "requiresAnySandbox": any(bool(action.get("sandboxRequired")) for action in actions),
                "requiresAnySecret": any(bool(action.get("secretsRequired")) for action in actions),
                "auditRequired": any(bool(action.get("auditRequired")) for action in actions),
            }
        )
    record["runtimeBoundary"] = {
        "frontendDirectExecutionAllowed": False,
        "executionAllowedFromDiscovery": False,
        "toolExecutionContractRequired": bool(record.get("registeredInToolRegistry")),
        "secretValuesIncluded": False,
        "rawPayloadIncluded": False,
        "auditRequired": bool(record.get("auditRequired") or record.get("connectorBacked")),
    }
    return record


def _capability_records() -> list[dict[str, Any]]:
    manifest_lookup = {
        str(manifest.get("id")): manifest
        for manifest in cognix_tool_registry.TOOL_MANIFESTS
        if str(manifest.get("id") or "").strip()
    }
    ordered_ids: list[str] = []
    records: dict[str, dict[str, Any]] = {}
    for tool in DISCOVERABLE_TOOL_CAPABILITIES:
        tool_id = str(tool.get("toolId") or "")
        if not tool_id:
            continue
        ordered_ids.append(tool_id)
        records[tool_id] = _merge_manifest_capability(tool, manifest_lookup.get(tool_id))
    for manifest in cognix_tool_registry.TOOL_MANIFESTS:
        tool_id = str(manifest.get("id") or "")
        if tool_id and tool_id not in records:
            ordered_ids.append(tool_id)
            records[tool_id] = _merge_manifest_capability(
                {
                    "toolId": tool_id,
                    "name": manifest.get("name") or tool_id,
                    "category": manifest.get("category") or "integration",
                    "capabilities": [],
                    "installHint": "Enable the registered CogniX connector before use.",
                    "connectorBacked": _connector_backed_from_manifest(manifest),
                    "enabledByDefault": bool(manifest.get("enabled")),
                },
                manifest,
            )
    return [records[tool_id] for tool_id in ordered_ids]


def _enabled_registry_tool_ids() -> set[str]:
    return {
        str(tool.get("id"))
        for tool in cognix_tool_registry.TOOL_MANIFESTS
        if tool.get("id") and bool(tool.get("enabled"))
    }


def build_tool_capability_registry() -> dict[str, Any]:
    capabilities = _capability_records()
    return {
        "capabilityRegistryVersion": COGNIX_TOOL_CAPABILITY_REGISTRY_VERSION,
        "toolDiscoveryVersion": COGNIX_TOOL_DISCOVERY_VERSION,
        "mode": "declarative_discovery",
        "capabilities": capabilities,
        "summary": {
            "toolCount": len(capabilities),
            "connectorBackedCount": sum(1 for item in capabilities if item.get("connectorBacked")),
            "registeredToolCount": sum(1 for item in capabilities if item.get("registeredInToolRegistry")),
            "enabledRegisteredToolCount": sum(1 for item in capabilities if item.get("registryToolEnabled")),
            "confirmationRequiredToolCount": sum(1 for item in capabilities if item.get("requiresAnyConfirmation")),
            "secretBackedToolCount": sum(1 for item in capabilities if item.get("requiresAnySecret")),
            "highRiskToolCount": sum(
                1
                for item in capabilities
                if cognix_tool_registry.RISK_ORDER.get(str(item.get("maxRiskLevel") or "low"), 0) >= 3
            ),
            "automaticInstallAllowed": False,
        },
        "policies": {
            "automaticInstallationAllowed": False,
            "humanConfirmationRequired": True,
            "frontendDirectInstallationAllowed": False,
            "frontendDirectExecutionAllowed": False,
            "toolExecutionContractRequired": True,
            "secretsMustStayServerSide": True,
            "auditRequired": True,
        },
        "sideEffects": {
            "toolExecution": False,
            "installation": False,
            "networkToolCall": False,
            "secretRead": False,
            "permissionWrite": False,
        },
    }


def _installed_tool_ids(
    installed_tool_ids: list[str] | None,
    installed_records: list[dict[str, Any]] | None,
) -> set[str]:
    ids = {_normalize(item) for item in (installed_tool_ids or []) if _normalize(item)}
    ids.update(_enabled_registry_tool_ids())
    for record in installed_records or []:
        tool_id = _normalize(record.get("tool_id") or record.get("toolId"))
        status = _normalize(record.get("status") or "installed")
        if tool_id and status in {"installed", "active", "connected", "enabled"}:
            ids.add(tool_id)
    for item in DISCOVERABLE_TOOL_CAPABILITIES:
        if item.get("enabledByDefault"):
            ids.add(str(item.get("toolId")))
    return ids


def _context_blob(
    *,
    objective: str | None,
    project_type: str | None,
    project_name: str | None,
    file_names: list[str] | None,
    documents: list[dict[str, Any]] | None,
    tags: list[str] | None,
) -> dict[str, Any]:
    document_text = " ".join(
        " ".join(
            str(item.get(key) or "")
            for key in ("name", "title", "kind", "mimeType", "summary")
        )
        for item in (documents or [])
        if isinstance(item, dict)
    )
    files = [str(item) for item in (file_names or []) if str(item or "").strip()]
    return {
        "text": _clean_words(" ".join([objective or "", project_name or "", document_text, " ".join(tags or []), " ".join(files)])),
        "projectType": _normalize(project_type),
        "fileSignals": {_file_signal(file_name) for file_name in files},
    }


def _match_need(rule: dict[str, Any], context: dict[str, Any]) -> dict[str, Any] | None:
    matched: list[dict[str, str]] = []
    project_type = context["projectType"]
    if project_type and project_type in {str(item).lower() for item in rule.get("projectTypes") or []}:
        matched.append({"type": "project_type", "value": project_type})
    text = context["text"]
    for keyword in rule.get("keywords") or []:
        needle = _clean_words(keyword)
        if needle and needle in text:
            matched.append({"type": "keyword", "value": str(keyword)})
    file_signals = context["fileSignals"]
    for extension in rule.get("extensions") or []:
        signal = _normalize(extension)
        if signal in file_signals:
            matched.append({"type": "file", "value": str(extension)})
    if not matched:
        return None
    confidence = min(0.97, 0.42 + (0.12 * len(matched)))
    return {
        "needId": rule["needId"],
        "label": rule["label"],
        "description": rule["description"],
        "matchedSignals": matched[:12],
        "confidence": round(confidence, 3),
        "toolIds": list(rule.get("toolIds") or []),
    }


def build_tool_discovery_plan(
    *,
    username: str,
    objective: str | None = None,
    project_type: str | None = None,
    project_name: str | None = None,
    project_id: str | None = None,
    file_names: list[str] | None = None,
    documents: list[dict[str, Any]] | None = None,
    tags: list[str] | None = None,
    installed_tool_ids: list[str] | None = None,
    installed_records: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    context = _context_blob(
        objective = objective,
        project_type = project_type,
        project_name = project_name,
        file_names = file_names,
        documents = documents,
        tags = tags,
    )
    needs = [
        match
        for rule in PROJECT_NEED_RULES
        if (match := _match_need(rule, context)) is not None
    ]
    capabilities = _tool_lookup()
    installed_ids = _installed_tool_ids(installed_tool_ids, installed_records)
    recommendations: dict[str, dict[str, Any]] = {}
    for need in needs:
        for tool_id in need["toolIds"]:
            tool = capabilities.get(tool_id)
            if tool is None:
                continue
            status = "installed" if tool_id in installed_ids else "recommended"
            registry_manifest = next(
                (item for item in cognix_tool_registry.TOOL_MANIFESTS if item.get("id") == tool_id),
                None,
            )
            if registry_manifest and not registry_manifest.get("enabled") and status != "installed":
                status = "connector_disabled"
            recommendation = recommendations.get(tool_id)
            reason = f"{need['label']}: {need['description']}"
            if recommendation is None:
                recommendations[tool_id] = {
                    "id": f"rec_{need['needId']}_{tool_id}".replace("-", "_"),
                    "toolId": tool_id,
                    "toolName": tool["name"],
                    "category": tool["category"],
                    "needId": need["needId"],
                    "needs": [need],
                    "reason": reason,
                    "confidence": need["confidence"],
                    "status": status,
                    "capabilities": list(tool.get("capabilities") or []),
                    "installHint": tool.get("installHint"),
                    "connectorBacked": bool(tool.get("connectorBacked")),
                    "actions": {
                        "primary": "configure" if status == "installed" else "install",
                        "ignoreAllowed": True,
                        "automaticInstallAllowed": False,
                        "requiresHumanConfirmation": True,
                    },
                    "guardrails": {
                        "noAutomaticInstallation": True,
                        "noFrontendDirectExecution": True,
                        "auditRequired": True,
                        "secretRead": False,
                        "toolExecution": False,
                    },
                }
                continue
            recommendation["needs"].append(need)
            recommendation["confidence"] = max(float(recommendation["confidence"]), float(need["confidence"]))
            recommendation["reason"] = f"{recommendation['reason']} | {reason}"
            if recommendation["status"] != "installed" and status == "installed":
                recommendation["status"] = "installed"
                recommendation["actions"]["primary"] = "configure"
    ordered_recommendations = sorted(
        recommendations.values(),
        key = lambda item: (-float(item["confidence"]), str(item["toolName"])),
    )
    return {
        "toolDiscoveryVersion": COGNIX_TOOL_DISCOVERY_VERSION,
        "capabilityRegistryVersion": COGNIX_TOOL_CAPABILITY_REGISTRY_VERSION,
        "mode": "recommendation_dry_run",
        "username": username,
        "projectId": project_id,
        "projectType": project_type,
        "projectName": project_name,
        "objectiveExcerpt": " ".join(str(objective or "").split())[:500],
        "needs": needs,
        "recommendations": ordered_recommendations,
        "summary": {
            "needCount": len(needs),
            "recommendationCount": len(ordered_recommendations),
            "installedMatchCount": sum(1 for item in ordered_recommendations if item["status"] == "installed"),
            "connectorDisabledCount": sum(1 for item in ordered_recommendations if item["status"] == "connector_disabled"),
            "automaticInstallAllowed": False,
        },
        "policies": {
            "automaticInstallationAllowed": False,
            "humanConfirmationRequired": True,
            "frontendDirectInstallationAllowed": False,
            "installPlanOnly": True,
            "auditRequired": True,
        },
        "sideEffects": {
            "modelLoad": False,
            "generation": False,
            "toolExecution": False,
            "installation": False,
            "networkToolCall": False,
            "secretRead": False,
            "recommendationWrite": False,
            "installedToolWrite": False,
        },
    }
