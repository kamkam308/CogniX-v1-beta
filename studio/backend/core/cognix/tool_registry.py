# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

"""Declarative CogniX tool registry.

The registry is intentionally execution-free. It tells the orchestrator which
tool actions exist, what they are allowed to do, and what guardrails must be in
place before a later executor can run them.
"""

from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from typing import Any


TOOL_REGISTRY_VERSION = "cognix_tool_registry_v1"
TOOL_EXECUTION_CONTRACT_VERSION = "cognix_tool_execution_contract_v1"
TOOL_EXECUTION_HANDOFF_VERSION = "cognix_tool_execution_handoff_v1"
TOOL_SECRET_POLICY_VERSION = "cognix_tool_secret_policy_v1"

RISK_ORDER = {
    "low": 1,
    "medium": 2,
    "high": 3,
    "critical": 4,
}

IMPLICIT_AUTHENTICATED_PERMISSION = "authenticated"
DEVELOPER_MODE_PERMISSION = "developer_mode"
ADMIN_PERMISSION = "admin"

DEFAULT_RATE_LIMIT_POLICY = {
    "windowSeconds": 60,
    "maxEvents": 60,
}

RATE_LIMIT_POLICIES: dict[str, dict[str, int]] = {
    "calculator:evaluate": {"windowSeconds": 60, "maxEvents": 240},
    "physics:solve": {"windowSeconds": 60, "maxEvents": 180},
    "github:read": {"windowSeconds": 60, "maxEvents": 120},
    "github:write": {"windowSeconds": 60, "maxEvents": 20},
    "github:merge": {"windowSeconds": 300, "maxEvents": 3},
    "drive:read": {"windowSeconds": 60, "maxEvents": 120},
    "drive:delete": {"windowSeconds": 300, "maxEvents": 3},
    "gmail:read": {"windowSeconds": 60, "maxEvents": 120},
    "gmail:draft": {"windowSeconds": 60, "maxEvents": 30},
    "gmail:send": {"windowSeconds": 300, "maxEvents": 5},
    "notion:read": {"windowSeconds": 60, "maxEvents": 120},
    "notion:write": {"windowSeconds": 60, "maxEvents": 30},
    "rag:index": {"windowSeconds": 300, "maxEvents": 12},
    "codex:plan": {"windowSeconds": 60, "maxEvents": 120},
    "codex:write": {"windowSeconds": 300, "maxEvents": 20},
    "codex:merge": {"windowSeconds": 600, "maxEvents": 2},
    "security:scan": {"windowSeconds": 600, "maxEvents": 5},
    "security:active": {"windowSeconds": 1800, "maxEvents": 1},
    "microsoft365:read": {"windowSeconds": 60, "maxEvents": 120},
    "microsoft365:write": {"windowSeconds": 60, "maxEvents": 30},
    "microsoft365:send": {"windowSeconds": 300, "maxEvents": 5},
    "workspace:read": {"windowSeconds": 60, "maxEvents": 120},
    "workspace:write": {"windowSeconds": 60, "maxEvents": 30},
    "workspace:share": {"windowSeconds": 300, "maxEvents": 5},
    "sharepoint:read": {"windowSeconds": 60, "maxEvents": 120},
    "sharepoint:write": {"windowSeconds": 60, "maxEvents": 20},
    "sharepoint:delete": {"windowSeconds": 300, "maxEvents": 2},
    "teams:read": {"windowSeconds": 60, "maxEvents": 120},
    "teams:post": {"windowSeconds": 300, "maxEvents": 10},
    "slack:read": {"windowSeconds": 60, "maxEvents": 120},
    "slack:post": {"windowSeconds": 300, "maxEvents": 10},
    "moodle:read": {"windowSeconds": 60, "maxEvents": 120},
    "moodle:write": {"windowSeconds": 300, "maxEvents": 20},
    "moodle:grade": {"windowSeconds": 300, "maxEvents": 5},
    "crm:read": {"windowSeconds": 60, "maxEvents": 120},
    "crm:write": {"windowSeconds": 60, "maxEvents": 30},
    "crm:export": {"windowSeconds": 600, "maxEvents": 2},
    "erp:read": {"windowSeconds": 60, "maxEvents": 120},
    "erp:write": {"windowSeconds": 300, "maxEvents": 10},
    "erp:approve": {"windowSeconds": 600, "maxEvents": 2},
    "internal:read": {"windowSeconds": 60, "maxEvents": 120},
    "internal:execute": {"windowSeconds": 300, "maxEvents": 10},
    "internal:admin": {"windowSeconds": 600, "maxEvents": 2},
}


SECRET_SOURCE_BY_CONNECTOR: dict[str, list[str]] = {
    "github": ["connector_oauth_token", "encrypted_user_token"],
    "google-drive": ["connector_oauth_token", "encrypted_user_token"],
    "gmail": ["connector_oauth_token", "encrypted_user_token"],
    "notion": ["connector_oauth_token", "encrypted_user_token"],
    "microsoft-365": ["connector_oauth_token", "encrypted_user_token", "microsoft_graph_app_secret"],
    "google-workspace": ["connector_oauth_token", "encrypted_user_token", "workspace_service_account"],
    "sharepoint": ["connector_oauth_token", "encrypted_user_token", "microsoft_graph_app_secret"],
    "microsoft-teams": ["connector_oauth_token", "encrypted_user_token", "microsoft_graph_app_secret"],
    "slack": ["connector_oauth_token", "encrypted_user_token", "slack_bot_token"],
    "moodle": ["connector_oauth_token", "encrypted_user_token", "moodle_service_token"],
    "crm": ["connector_oauth_token", "encrypted_user_token", "crm_api_token"],
    "erp": ["connector_oauth_token", "encrypted_user_token", "erp_api_token"],
    "internal-tools": ["encrypted_service_token", "internal_gateway_token"],
}


TOOL_MANIFESTS: list[dict[str, Any]] = [
    {
        "id": "calculator",
        "name": "CogniX Calculator",
        "category": "math",
        "description": "Calcul deterministe local pour maths, physique et verification numerique.",
        "connector": "local-calculator",
        "enabled": True,
        "dataIsolation": "none",
        "actions": [
            {
                "id": "evaluate_expression",
                "label": "Evaluer une expression",
                "description": "Evaluer une expression mathematique bornee sans modele ni reseau.",
                "mode": "execute",
                "permissions": [IMPLICIT_AUTHENTICATED_PERMISSION],
                "riskLevel": "low",
                "requiresConfirmation": False,
                "auditRequired": True,
                "sandboxRequired": False,
                "rateLimitKey": "calculator:evaluate",
                "secretsRequired": False,
            },
        ],
    },
    {
        "id": "physics-solver",
        "name": "CogniX Physics Solver",
        "category": "physics",
        "description": "Resolution deterministe de formules physiques de base sans modele ni reseau.",
        "connector": "local-physics-solver",
        "enabled": True,
        "dataIsolation": "none",
        "actions": [
            {
                "id": "solve_formula",
                "label": "Resoudre une formule",
                "description": "Resoudre une variable manquante dans une formule physique bornee.",
                "mode": "execute",
                "permissions": [IMPLICIT_AUTHENTICATED_PERMISSION],
                "riskLevel": "low",
                "requiresConfirmation": False,
                "auditRequired": True,
                "sandboxRequired": False,
                "rateLimitKey": "physics:solve",
                "secretsRequired": False,
            },
        ],
    },
    {
        "id": "github",
        "name": "GitHub",
        "category": "code",
        "description": "Depots, issues, pull requests et workflow de developpement.",
        "connector": "github",
        "enabled": False,
        "dataIsolation": "user",
        "actions": [
            {
                "id": "read_repository",
                "label": "Lire un depot",
                "description": "Lire les fichiers, issues et pull requests accessibles.",
                "mode": "read",
                "permissions": [IMPLICIT_AUTHENTICATED_PERMISSION, "github:read"],
                "riskLevel": "low",
                "requiresConfirmation": False,
                "auditRequired": True,
                "sandboxRequired": False,
                "rateLimitKey": "github:read",
                "secretsRequired": True,
            },
            {
                "id": "create_issue",
                "label": "Creer une issue",
                "description": "Creer une issue ou un brouillon de suivi dans un depot.",
                "mode": "write",
                "permissions": [DEVELOPER_MODE_PERMISSION, "github:write"],
                "riskLevel": "medium",
                "requiresConfirmation": True,
                "auditRequired": True,
                "sandboxRequired": False,
                "rateLimitKey": "github:write",
                "secretsRequired": True,
            },
            {
                "id": "merge_pull_request",
                "label": "Fusionner une pull request",
                "description": "Action critique reservee aux admins ou validations humaines.",
                "mode": "write",
                "permissions": [ADMIN_PERMISSION, "github:merge"],
                "riskLevel": "critical",
                "requiresConfirmation": True,
                "auditRequired": True,
                "sandboxRequired": False,
                "rateLimitKey": "github:merge",
                "secretsRequired": True,
            },
        ],
    },
    {
        "id": "google-drive",
        "name": "Google Drive",
        "category": "files",
        "description": "Lecture, indexation et organisation de documents utilisateur.",
        "connector": "google-drive",
        "enabled": False,
        "dataIsolation": "user",
        "actions": [
            {
                "id": "read_document",
                "label": "Lire un document",
                "description": "Lire un document accessible pour alimenter RAG ou contexte.",
                "mode": "read",
                "permissions": [IMPLICIT_AUTHENTICATED_PERMISSION, "drive:read"],
                "riskLevel": "low",
                "requiresConfirmation": False,
                "auditRequired": True,
                "sandboxRequired": False,
                "rateLimitKey": "drive:read",
                "secretsRequired": True,
            },
            {
                "id": "index_document",
                "label": "Indexer un document",
                "description": "Importer un document dans la memoire documentaire CogniX.",
                "mode": "write",
                "permissions": [IMPLICIT_AUTHENTICATED_PERMISSION, "rag:write"],
                "riskLevel": "medium",
                "requiresConfirmation": True,
                "auditRequired": True,
                "sandboxRequired": True,
                "rateLimitKey": "rag:index",
                "secretsRequired": True,
            },
            {
                "id": "delete_file",
                "label": "Supprimer un fichier",
                "description": "Suppression distante; interdite sans role admin et confirmation.",
                "mode": "delete",
                "permissions": [ADMIN_PERMISSION, "drive:delete"],
                "riskLevel": "critical",
                "requiresConfirmation": True,
                "auditRequired": True,
                "sandboxRequired": False,
                "rateLimitKey": "drive:delete",
                "secretsRequired": True,
            },
        ],
    },
    {
        "id": "gmail",
        "name": "Gmail",
        "category": "communication",
        "description": "Recherche mail, brouillons et envoi controle.",
        "connector": "gmail",
        "enabled": False,
        "dataIsolation": "user",
        "actions": [
            {
                "id": "search_mail",
                "label": "Chercher des emails",
                "description": "Lire les emails accessibles pour resumer ou preparer une reponse.",
                "mode": "read",
                "permissions": [IMPLICIT_AUTHENTICATED_PERMISSION, "gmail:read"],
                "riskLevel": "low",
                "requiresConfirmation": False,
                "auditRequired": True,
                "sandboxRequired": False,
                "rateLimitKey": "gmail:read",
                "secretsRequired": True,
            },
            {
                "id": "create_draft",
                "label": "Creer un brouillon",
                "description": "Creer un brouillon sans envoyer de message.",
                "mode": "write",
                "permissions": [IMPLICIT_AUTHENTICATED_PERMISSION, "gmail:draft"],
                "riskLevel": "medium",
                "requiresConfirmation": True,
                "auditRequired": True,
                "sandboxRequired": False,
                "rateLimitKey": "gmail:draft",
                "secretsRequired": True,
            },
            {
                "id": "send_mail",
                "label": "Envoyer un email",
                "description": "Envoi reel; confirmation humaine obligatoire.",
                "mode": "write",
                "permissions": [DEVELOPER_MODE_PERMISSION, "gmail:send"],
                "riskLevel": "high",
                "requiresConfirmation": True,
                "auditRequired": True,
                "sandboxRequired": False,
                "rateLimitKey": "gmail:send",
                "secretsRequired": True,
            },
        ],
    },
    {
        "id": "notion",
        "name": "Notion",
        "category": "productivity",
        "description": "Lecture et creation de pages de travail.",
        "connector": "notion",
        "enabled": False,
        "dataIsolation": "user",
        "actions": [
            {
                "id": "read_page",
                "label": "Lire une page",
                "description": "Lire une page ou base Notion accessible.",
                "mode": "read",
                "permissions": [IMPLICIT_AUTHENTICATED_PERMISSION, "notion:read"],
                "riskLevel": "low",
                "requiresConfirmation": False,
                "auditRequired": True,
                "sandboxRequired": False,
                "rateLimitKey": "notion:read",
                "secretsRequired": True,
            },
            {
                "id": "create_page",
                "label": "Creer une page",
                "description": "Creer une page ou note structuree.",
                "mode": "write",
                "permissions": [IMPLICIT_AUTHENTICATED_PERMISSION, "notion:write"],
                "riskLevel": "medium",
                "requiresConfirmation": True,
                "auditRequired": True,
                "sandboxRequired": False,
                "rateLimitKey": "notion:write",
                "secretsRequired": True,
            },
        ],
    },
    {
        "id": "microsoft-365",
        "name": "Microsoft 365",
        "category": "productivity",
        "description": "Calendrier, documents et brouillons Microsoft Graph sous controle CogniX.",
        "connector": "microsoft-365",
        "enabled": False,
        "dataIsolation": "organization",
        "actions": [
            {
                "id": "read_calendar",
                "label": "Lire le calendrier",
                "description": "Lire les evenements accessibles pour preparer un planning.",
                "mode": "read",
                "permissions": [IMPLICIT_AUTHENTICATED_PERMISSION, "microsoft365:read"],
                "riskLevel": "low",
                "requiresConfirmation": False,
                "auditRequired": True,
                "sandboxRequired": False,
                "rateLimitKey": "microsoft365:read",
                "secretsRequired": True,
            },
            {
                "id": "create_event_draft",
                "label": "Preparer un evenement",
                "description": "Creer un brouillon d'evenement sans envoyer d'invitation.",
                "mode": "write",
                "permissions": [IMPLICIT_AUTHENTICATED_PERMISSION, "microsoft365:write"],
                "riskLevel": "medium",
                "requiresConfirmation": True,
                "auditRequired": True,
                "sandboxRequired": False,
                "rateLimitKey": "microsoft365:write",
                "secretsRequired": True,
            },
            {
                "id": "send_meeting_invite",
                "label": "Envoyer une invitation",
                "description": "Envoyer une invitation reelle via Microsoft 365.",
                "mode": "write",
                "permissions": [DEVELOPER_MODE_PERMISSION, "microsoft365:send"],
                "riskLevel": "high",
                "requiresConfirmation": True,
                "auditRequired": True,
                "sandboxRequired": False,
                "rateLimitKey": "microsoft365:send",
                "secretsRequired": True,
            },
        ],
    },
    {
        "id": "google-workspace",
        "name": "Google Workspace",
        "category": "productivity",
        "description": "Calendrier, Docs et Sheets au niveau workspace avec garde-fous.",
        "connector": "google-workspace",
        "enabled": False,
        "dataIsolation": "organization",
        "actions": [
            {
                "id": "read_calendar",
                "label": "Lire le calendrier",
                "description": "Lire les evenements Workspace accessibles.",
                "mode": "read",
                "permissions": [IMPLICIT_AUTHENTICATED_PERMISSION, "workspace:read"],
                "riskLevel": "low",
                "requiresConfirmation": False,
                "auditRequired": True,
                "sandboxRequired": False,
                "rateLimitKey": "workspace:read",
                "secretsRequired": True,
            },
            {
                "id": "create_doc_draft",
                "label": "Creer un brouillon Doc",
                "description": "Preparer un document sans partage automatique.",
                "mode": "write",
                "permissions": [IMPLICIT_AUTHENTICATED_PERMISSION, "workspace:write"],
                "riskLevel": "medium",
                "requiresConfirmation": True,
                "auditRequired": True,
                "sandboxRequired": False,
                "rateLimitKey": "workspace:write",
                "secretsRequired": True,
            },
            {
                "id": "share_document",
                "label": "Partager un document",
                "description": "Modifier les permissions de partage d'un document Workspace.",
                "mode": "write",
                "permissions": [DEVELOPER_MODE_PERMISSION, "workspace:share"],
                "riskLevel": "high",
                "requiresConfirmation": True,
                "auditRequired": True,
                "sandboxRequired": False,
                "rateLimitKey": "workspace:share",
                "secretsRequired": True,
            },
        ],
    },
    {
        "id": "sharepoint",
        "name": "SharePoint",
        "category": "files",
        "description": "Lecture, indexation et gouvernance documentaire entreprise.",
        "connector": "sharepoint",
        "enabled": False,
        "dataIsolation": "organization",
        "actions": [
            {
                "id": "read_site_document",
                "label": "Lire un document site",
                "description": "Lire un document SharePoint accessible a l'utilisateur.",
                "mode": "read",
                "permissions": [IMPLICIT_AUTHENTICATED_PERMISSION, "sharepoint:read"],
                "riskLevel": "low",
                "requiresConfirmation": False,
                "auditRequired": True,
                "sandboxRequired": False,
                "rateLimitKey": "sharepoint:read",
                "secretsRequired": True,
            },
            {
                "id": "index_site_document",
                "label": "Indexer un document site",
                "description": "Preparer l'indexation RAG d'un document SharePoint.",
                "mode": "write",
                "permissions": [IMPLICIT_AUTHENTICATED_PERMISSION, "sharepoint:write", "rag:write"],
                "riskLevel": "medium",
                "requiresConfirmation": True,
                "auditRequired": True,
                "sandboxRequired": True,
                "rateLimitKey": "sharepoint:write",
                "secretsRequired": True,
            },
            {
                "id": "delete_site_file",
                "label": "Supprimer un fichier site",
                "description": "Suppression distante SharePoint; admin et confirmation obligatoires.",
                "mode": "delete",
                "permissions": [ADMIN_PERMISSION, "sharepoint:delete"],
                "riskLevel": "critical",
                "requiresConfirmation": True,
                "auditRequired": True,
                "sandboxRequired": False,
                "rateLimitKey": "sharepoint:delete",
                "secretsRequired": True,
            },
        ],
    },
    {
        "id": "microsoft-teams",
        "name": "Microsoft Teams",
        "category": "communication",
        "description": "Lecture de canaux, brouillons et publication Teams auditee.",
        "connector": "microsoft-teams",
        "enabled": False,
        "dataIsolation": "organization",
        "actions": [
            {
                "id": "read_channel",
                "label": "Lire un canal",
                "description": "Lire les messages accessibles d'un canal Teams.",
                "mode": "read",
                "permissions": [IMPLICIT_AUTHENTICATED_PERMISSION, "teams:read"],
                "riskLevel": "low",
                "requiresConfirmation": False,
                "auditRequired": True,
                "sandboxRequired": False,
                "rateLimitKey": "teams:read",
                "secretsRequired": True,
            },
            {
                "id": "create_message_draft",
                "label": "Creer un brouillon",
                "description": "Preparer un message Teams sans publication.",
                "mode": "write",
                "permissions": [IMPLICIT_AUTHENTICATED_PERMISSION, "teams:post"],
                "riskLevel": "medium",
                "requiresConfirmation": True,
                "auditRequired": True,
                "sandboxRequired": False,
                "rateLimitKey": "teams:post",
                "secretsRequired": True,
            },
            {
                "id": "post_message",
                "label": "Publier un message",
                "description": "Publier un message reel dans Teams.",
                "mode": "write",
                "permissions": [DEVELOPER_MODE_PERMISSION, "teams:post"],
                "riskLevel": "high",
                "requiresConfirmation": True,
                "auditRequired": True,
                "sandboxRequired": False,
                "rateLimitKey": "teams:post",
                "secretsRequired": True,
            },
        ],
    },
    {
        "id": "slack",
        "name": "Slack",
        "category": "communication",
        "description": "Lecture de canaux, brouillons et publication Slack auditee.",
        "connector": "slack",
        "enabled": False,
        "dataIsolation": "organization",
        "actions": [
            {
                "id": "read_channel",
                "label": "Lire un canal",
                "description": "Lire les messages Slack accessibles.",
                "mode": "read",
                "permissions": [IMPLICIT_AUTHENTICATED_PERMISSION, "slack:read"],
                "riskLevel": "low",
                "requiresConfirmation": False,
                "auditRequired": True,
                "sandboxRequired": False,
                "rateLimitKey": "slack:read",
                "secretsRequired": True,
            },
            {
                "id": "create_message_draft",
                "label": "Creer un brouillon",
                "description": "Preparer une reponse Slack sans publication.",
                "mode": "write",
                "permissions": [IMPLICIT_AUTHENTICATED_PERMISSION, "slack:post"],
                "riskLevel": "medium",
                "requiresConfirmation": True,
                "auditRequired": True,
                "sandboxRequired": False,
                "rateLimitKey": "slack:post",
                "secretsRequired": True,
            },
            {
                "id": "post_message",
                "label": "Publier un message",
                "description": "Publier un message Slack reel.",
                "mode": "write",
                "permissions": [DEVELOPER_MODE_PERMISSION, "slack:post"],
                "riskLevel": "high",
                "requiresConfirmation": True,
                "auditRequired": True,
                "sandboxRequired": False,
                "rateLimitKey": "slack:post",
                "secretsRequired": True,
            },
        ],
    },
    {
        "id": "moodle",
        "name": "Moodle",
        "category": "education",
        "description": "Cours, devoirs et notes avec separation professeur/administration.",
        "connector": "moodle",
        "enabled": False,
        "dataIsolation": "organization",
        "actions": [
            {
                "id": "read_course",
                "label": "Lire un cours",
                "description": "Lire le contenu d'un cours accessible.",
                "mode": "read",
                "permissions": [IMPLICIT_AUTHENTICATED_PERMISSION, "moodle:read"],
                "riskLevel": "low",
                "requiresConfirmation": False,
                "auditRequired": True,
                "sandboxRequired": False,
                "rateLimitKey": "moodle:read",
                "secretsRequired": True,
            },
            {
                "id": "create_assignment_draft",
                "label": "Preparer un devoir",
                "description": "Creer un brouillon de devoir sans publication aux etudiants.",
                "mode": "write",
                "permissions": [DEVELOPER_MODE_PERMISSION, "moodle:write"],
                "riskLevel": "medium",
                "requiresConfirmation": True,
                "auditRequired": True,
                "sandboxRequired": False,
                "rateLimitKey": "moodle:write",
                "secretsRequired": True,
            },
            {
                "id": "publish_grade",
                "label": "Publier une note",
                "description": "Modifier ou publier une note etudiante.",
                "mode": "write",
                "permissions": [ADMIN_PERMISSION, "moodle:grade"],
                "riskLevel": "critical",
                "requiresConfirmation": True,
                "auditRequired": True,
                "sandboxRequired": False,
                "rateLimitKey": "moodle:grade",
                "secretsRequired": True,
            },
        ],
    },
    {
        "id": "crm",
        "name": "CRM",
        "category": "business",
        "description": "Comptes clients, taches commerciales et export controle.",
        "connector": "crm",
        "enabled": False,
        "dataIsolation": "organization",
        "actions": [
            {
                "id": "read_customer",
                "label": "Lire une fiche client",
                "description": "Lire une fiche client autorisee.",
                "mode": "read",
                "permissions": [IMPLICIT_AUTHENTICATED_PERMISSION, "crm:read"],
                "riskLevel": "low",
                "requiresConfirmation": False,
                "auditRequired": True,
                "sandboxRequired": False,
                "rateLimitKey": "crm:read",
                "secretsRequired": True,
            },
            {
                "id": "create_followup_task",
                "label": "Creer une tache de suivi",
                "description": "Ajouter une tache commerciale sans contacter le client.",
                "mode": "write",
                "permissions": [DEVELOPER_MODE_PERMISSION, "crm:write"],
                "riskLevel": "medium",
                "requiresConfirmation": True,
                "auditRequired": True,
                "sandboxRequired": False,
                "rateLimitKey": "crm:write",
                "secretsRequired": True,
            },
            {
                "id": "export_customer_data",
                "label": "Exporter des donnees client",
                "description": "Exporter des donnees client; action critique soumise a admin.",
                "mode": "export",
                "permissions": [ADMIN_PERMISSION, "crm:export"],
                "riskLevel": "critical",
                "requiresConfirmation": True,
                "auditRequired": True,
                "sandboxRequired": True,
                "rateLimitKey": "crm:export",
                "secretsRequired": True,
            },
        ],
    },
    {
        "id": "erp",
        "name": "ERP",
        "category": "business",
        "description": "Inventaire, achats et validations operationnelles auditees.",
        "connector": "erp",
        "enabled": False,
        "dataIsolation": "organization",
        "actions": [
            {
                "id": "read_inventory",
                "label": "Lire l'inventaire",
                "description": "Lire les donnees d'inventaire autorisees.",
                "mode": "read",
                "permissions": [IMPLICIT_AUTHENTICATED_PERMISSION, "erp:read"],
                "riskLevel": "low",
                "requiresConfirmation": False,
                "auditRequired": True,
                "sandboxRequired": False,
                "rateLimitKey": "erp:read",
                "secretsRequired": True,
            },
            {
                "id": "create_purchase_request",
                "label": "Creer une demande d'achat",
                "description": "Preparer une demande d'achat sans approbation finale.",
                "mode": "write",
                "permissions": [DEVELOPER_MODE_PERMISSION, "erp:write"],
                "riskLevel": "medium",
                "requiresConfirmation": True,
                "auditRequired": True,
                "sandboxRequired": False,
                "rateLimitKey": "erp:write",
                "secretsRequired": True,
            },
            {
                "id": "approve_payment",
                "label": "Approuver un paiement",
                "description": "Approbation financiere; action critique admin uniquement.",
                "mode": "write",
                "permissions": [ADMIN_PERMISSION, "erp:approve"],
                "riskLevel": "critical",
                "requiresConfirmation": True,
                "auditRequired": True,
                "sandboxRequired": False,
                "rateLimitKey": "erp:approve",
                "secretsRequired": True,
            },
        ],
    },
    {
        "id": "internal-tools",
        "name": "Internal Tools",
        "category": "operations",
        "description": "Runbooks, tickets internes et jobs operationnels sous sandbox.",
        "connector": "internal-tools",
        "enabled": False,
        "dataIsolation": "organization",
        "actions": [
            {
                "id": "read_runbook",
                "label": "Lire un runbook",
                "description": "Lire une procedure interne autorisee.",
                "mode": "read",
                "permissions": [IMPLICIT_AUTHENTICATED_PERMISSION, "internal:read"],
                "riskLevel": "low",
                "requiresConfirmation": False,
                "auditRequired": True,
                "sandboxRequired": False,
                "rateLimitKey": "internal:read",
                "secretsRequired": True,
            },
            {
                "id": "create_internal_ticket",
                "label": "Creer un ticket interne",
                "description": "Ouvrir un ticket operationnel sans executer de job.",
                "mode": "write",
                "permissions": [DEVELOPER_MODE_PERMISSION, "internal:execute"],
                "riskLevel": "medium",
                "requiresConfirmation": True,
                "auditRequired": True,
                "sandboxRequired": False,
                "rateLimitKey": "internal:execute",
                "secretsRequired": True,
            },
            {
                "id": "run_internal_job",
                "label": "Executer un job interne",
                "description": "Execution operationnelle; sandbox et admin obligatoires.",
                "mode": "execute",
                "permissions": [ADMIN_PERMISSION, "internal:admin"],
                "riskLevel": "critical",
                "requiresConfirmation": True,
                "auditRequired": True,
                "sandboxRequired": True,
                "rateLimitKey": "internal:admin",
                "secretsRequired": True,
            },
        ],
    },
    {
        "id": "codex-secure-agent",
        "name": "Codex Secure Agent",
        "category": "development",
        "description": "Pipeline interne branche Git, tests, build et validation humaine.",
        "connector": "local-codex",
        "enabled": True,
        "dataIsolation": "workspace",
        "actions": [
            {
                "id": "plan_feature",
                "label": "Planifier une feature",
                "description": "Analyser une demande et produire un plan sans modifier le code.",
                "mode": "read",
                "permissions": [IMPLICIT_AUTHENTICATED_PERMISSION],
                "riskLevel": "low",
                "requiresConfirmation": False,
                "auditRequired": True,
                "sandboxRequired": False,
                "rateLimitKey": "codex:plan",
                "secretsRequired": False,
            },
            {
                "id": "modify_code",
                "label": "Modifier le code",
                "description": "Modifier le code sur branche avec tests et build obligatoires.",
                "mode": "write",
                "permissions": [DEVELOPER_MODE_PERMISSION],
                "riskLevel": "high",
                "requiresConfirmation": True,
                "auditRequired": True,
                "sandboxRequired": True,
                "rateLimitKey": "codex:write",
                "secretsRequired": False,
            },
            {
                "id": "merge_to_main",
                "label": "Fusionner vers main",
                "description": "Merge final; reserve aux admins apres validation humaine.",
                "mode": "write",
                "permissions": [ADMIN_PERMISSION],
                "riskLevel": "critical",
                "requiresConfirmation": True,
                "auditRequired": True,
                "sandboxRequired": True,
                "rateLimitKey": "codex:merge",
                "secretsRequired": False,
            },
        ],
    },
    {
        "id": "kali-isolated",
        "name": "Kali Isolated Toolkit",
        "category": "security",
        "description": "Boite a outils cyber uniquement en VM/container isole.",
        "connector": "isolated-container",
        "enabled": False,
        "dataIsolation": "ephemeral_container",
        "actions": [
            {
                "id": "passive_scan",
                "label": "Scan passif",
                "description": "Analyse passive autorisee uniquement sur cible validee.",
                "mode": "execute",
                "permissions": [DEVELOPER_MODE_PERMISSION, "security:passive_scan"],
                "riskLevel": "high",
                "requiresConfirmation": True,
                "auditRequired": True,
                "sandboxRequired": True,
                "rateLimitKey": "security:scan",
                "secretsRequired": False,
            },
            {
                "id": "active_test",
                "label": "Test actif",
                "description": "Action critique exigeant isolation, admin et autorisation explicite.",
                "mode": "execute",
                "permissions": [ADMIN_PERMISSION, "security:active_test"],
                "riskLevel": "critical",
                "requiresConfirmation": True,
                "auditRequired": True,
                "sandboxRequired": True,
                "rateLimitKey": "security:active",
                "secretsRequired": False,
            },
        ],
    },
]


def _normalize_permission(permission: str) -> str:
    return permission.strip().lower()


def _risk_at_least(risk: str, threshold: str) -> bool:
    return RISK_ORDER.get(risk, 0) >= RISK_ORDER.get(threshold, 0)


def _permission_context(
    *,
    username: str,
    is_admin: bool,
    has_developer_mode: bool,
    granted_permissions: set[str] | None,
) -> dict[str, Any]:
    explicit_permissions = sorted(
        {
            _normalize_permission(str(item))
            for item in (granted_permissions or set())
            if str(item or "").strip()
        }
    )
    effective_permissions = set(explicit_permissions)
    effective_permissions.add(IMPLICIT_AUTHENTICATED_PERMISSION)
    if is_admin:
        effective_permissions.add(ADMIN_PERMISSION)
        effective_permissions.add(DEVELOPER_MODE_PERMISSION)
    if has_developer_mode:
        effective_permissions.add(DEVELOPER_MODE_PERMISSION)
    return {
        "username": username,
        "isAdmin": bool(is_admin),
        "developerMode": bool(is_admin or has_developer_mode),
        "explicitPermissions": explicit_permissions,
        "effectivePermissions": sorted(effective_permissions),
        "derivedPermissions": sorted(
            permission
            for permission in effective_permissions
            if permission not in set(explicit_permissions)
        ),
        "sideEffects": {
            "permissionWrite": False,
            "secretRead": False,
            "toolExecution": False,
        },
    }


def _permission_set_from_context(context: dict[str, Any]) -> set[str]:
    return {
        _normalize_permission(str(item))
        for item in context.get("effectivePermissions", [])
        if str(item or "").strip()
    }


def _secret_policy(tool: dict[str, Any], action: dict[str, Any]) -> dict[str, Any]:
    requires_secret = bool(action.get("secretsRequired"))
    connector = str(tool.get("connector") or "unknown")
    risk_level = str(action.get("riskLevel") or "medium").lower()
    return {
        "policyVersion": TOOL_SECRET_POLICY_VERSION,
        "mode": "server_side_secret_resolution_only",
        "toolId": tool.get("id"),
        "connector": connector,
        "actionId": action.get("id"),
        "requiresSecret": requires_secret,
        "serverSideResolutionRequired": requires_secret,
        "secretReadAllowedHere": False,
        "rawSecretExposureAllowed": False,
        "clientSecretTransmitAllowed": False,
        "auditSecretValueAllowed": False,
        "executorLogSecretValueAllowed": False,
        "logRedactionRequired": requires_secret,
        "rotationRecommended": requires_secret and _risk_at_least(risk_level, "high"),
        "allowedSecretSources": deepcopy(SECRET_SOURCE_BY_CONNECTOR.get(connector, [])) if requires_secret else [],
        "secretResolutionAllowedOnlyAfter": [
            "connector_enabled",
            "permissions_resolved",
            "rate_limit_checked",
            "human_confirmation_if_required",
        ]
        if requires_secret
        else [],
        "blockedActions": [
            "frontend_secret_access",
            "client_secret_transmit",
            "raw_secret_read",
            "audit_secret_value",
            "executor_log_secret_value",
        ],
        "sideEffects": {
            "secretRead": False,
            "secretWrite": False,
            "secretExposure": False,
        },
    }


def _action_decision(
    *,
    tool: dict[str, Any],
    action: dict[str, Any],
    permission_set: set[str],
) -> dict[str, Any]:
    required_permissions = [
        _normalize_permission(str(item))
        for item in action.get("permissions", [])
        if str(item or "").strip()
    ]
    missing = [
        permission for permission in required_permissions if permission not in permission_set
    ]
    enabled = bool(tool.get("enabled"))
    risk_level = str(action.get("riskLevel") or "medium").lower()
    mode = str(action.get("mode") or "read")
    rate_limit_key = action.get("rateLimitKey")
    requires_confirmation = bool(action.get("requiresConfirmation")) or _risk_at_least(risk_level, "medium")
    admin_required = ADMIN_PERMISSION in required_permissions or _risk_at_least(risk_level, "critical")
    allowed = enabled and not missing
    status = "allowed" if allowed else ("connector_disabled" if not enabled else "missing_permission")
    blockers: list[dict[str, Any]] = []
    if not enabled:
        blockers.append(
            {
                "id": "connector_disabled",
                "reason": "Connector is declared in CogniX but not enabled.",
            }
        )
    if missing:
        blockers.append(
            {
                "id": "missing_permissions",
                "reason": "User is missing required tool permissions.",
                "permissions": missing,
            }
        )
    return {
        "allowed": allowed,
        "status": status,
        "reason": (
            "Action allowed by CogniX guardrails."
            if allowed
            else (
                "Connector is declared but not enabled yet."
                if not enabled
                else "User is missing required tool permissions."
            )
        ),
        "mode": mode,
        "riskLevel": risk_level,
        "requiredPermissions": required_permissions,
        "missingPermissions": missing,
        "requiresConfirmation": requires_confirmation,
        "auditRequired": bool(action.get("auditRequired", True)),
        "sandboxRequired": bool(action.get("sandboxRequired")),
        "rateLimitKey": rate_limit_key,
        "rateLimitPolicy": rate_limit_policy_for_key(
            str(rate_limit_key) if rate_limit_key else None
        ),
        "secretsRequired": bool(action.get("secretsRequired")),
        "secretPolicy": _secret_policy(tool, action),
        "dataIsolation": tool.get("dataIsolation"),
        "adminRequired": admin_required,
        "guardrails": {
            "humanConfirmationRequired": requires_confirmation,
            "auditRequired": bool(action.get("auditRequired", True)),
            "rateLimitRequired": bool(rate_limit_key),
            "sandboxRequired": bool(action.get("sandboxRequired")),
            "secretsStayServerSide": bool(action.get("secretsRequired")),
            "secretPolicyRequired": True,
            "adminRequired": admin_required,
            "frontendDirectExecutionAllowed": False,
        },
        "blockers": blockers,
        "sideEffects": {
            "toolExecution": False,
            "networkToolCall": False,
            "externalWrite": False,
            "secretRead": False,
            "permissionWrite": False,
        },
    }


def _contract_blocked_when(decision: dict[str, Any]) -> list[str]:
    blocked = [
        str(item.get("id"))
        for item in decision.get("blockers", [])
        if isinstance(item, dict) and item.get("id")
    ]
    if decision.get("requiresConfirmation"):
        blocked.append("human_confirmation_required")
    if decision.get("secretsRequired"):
        blocked.append("secret_resolution_required")
    if decision.get("sandboxRequired"):
        blocked.append("sandbox_required")
    if decision.get("rateLimitKey"):
        blocked.append("rate_limit_check_required")
    return sorted(set(blocked))


def _execution_contract(
    *,
    tool: dict[str, Any],
    action: dict[str, Any],
    decision: dict[str, Any],
    permission_context: dict[str, Any],
) -> dict[str, Any]:
    allowed_to_prepare = bool(decision.get("allowed"))
    blocked_when = _contract_blocked_when(decision)
    connector = str(tool.get("connector") or "unknown")
    secret_policy = decision.get("secretPolicy")
    if not isinstance(secret_policy, dict):
        secret_policy = _secret_policy(tool, action)
    return {
        "contractVersion": TOOL_EXECUTION_CONTRACT_VERSION,
        "mode": "guarded_plan_only",
        "toolId": tool.get("id"),
        "connector": connector,
        "actionId": action.get("id"),
        "actionMode": action.get("mode"),
        "allowedToPrepare": allowed_to_prepare,
        "readyForExecution": False,
        "automaticExecutionAllowed": False,
        "frontendDirectExecutionAllowed": False,
        "executorRequired": allowed_to_prepare,
        "plannedExecutor": f"cognix_tool_executor:{connector}" if allowed_to_prepare else None,
        "nextRequiredGate": (
            blocked_when[0]
            if blocked_when
            else "executor_approval_gate"
        ),
        "allowedActions": [
            "record_tool_plan",
            "check_rate_limit",
            "request_human_confirmation",
            "resolve_secrets_server_side",
            "prepare_sandbox",
            "enqueue_tool_job_after_approval",
        ]
        if allowed_to_prepare
        else ["record_tool_plan"],
        "blockedActions": [
            "tool_execution",
            "network_tool_call",
            "external_write",
            "secret_read",
            "permission_write",
            "frontend_direct_execution",
        ],
        "preconditions": {
            "connectorEnabled": bool(tool.get("enabled")),
            "permissionsResolved": not bool(decision.get("missingPermissions")),
            "humanConfirmationRequired": bool(decision.get("requiresConfirmation")),
            "auditRequired": bool(decision.get("auditRequired")),
            "sandboxRequired": bool(decision.get("sandboxRequired")),
            "rateLimitRequired": bool(decision.get("rateLimitKey")),
            "rateLimitChecked": False,
            "rateLimitAllowed": None,
            "secretsRequired": bool(decision.get("secretsRequired")),
            "secretsStayServerSide": True,
            "secretPolicyVersion": secret_policy.get("policyVersion"),
            "adminRequired": bool(decision.get("adminRequired")),
        },
        "permissionContext": {
            "username": permission_context.get("username"),
            "isAdmin": bool(permission_context.get("isAdmin")),
            "developerMode": bool(permission_context.get("developerMode")),
            "effectivePermissionCount": len(permission_context.get("effectivePermissions") or []),
        },
        "dataBoundary": {
            "dataIsolation": tool.get("dataIsolation"),
            "secretsStayServerSide": True,
            "secretPolicyVersion": secret_policy.get("policyVersion"),
            "rawSecretExposureAllowed": False,
            "clientSecretTransmitAllowed": False,
            "auditRawPayloadAllowed": False,
            "auditSecretValueAllowed": False,
        },
        "secretPolicy": secret_policy,
        "blockedWhen": blocked_when,
        "sideEffects": {
            "toolExecution": False,
            "networkToolCall": False,
            "externalWrite": False,
            "secretRead": False,
            "permissionWrite": False,
        },
    }


def build_tool_registry() -> dict[str, Any]:
    tools = deepcopy(TOOL_MANIFESTS)
    for tool in tools:
        for action in tool.get("actions") or []:
            action["secretPolicy"] = _secret_policy(tool, action)
    action_count = sum(len(tool.get("actions") or []) for tool in tools)
    high_risk_count = sum(
        1
        for tool in tools
        for action in tool.get("actions") or []
        if _risk_at_least(str(action.get("riskLevel") or ""), "high")
    )
    return {
        "registryVersion": TOOL_REGISTRY_VERSION,
        "mode": "declarative_guarded",
        "tools": tools,
        "summary": {
            "toolCount": len(tools),
            "actionCount": action_count,
            "highRiskActionCount": high_risk_count,
            "executionEnabled": False,
            "auditRequiredByDefault": True,
        },
        "globalPolicies": {
            "humanConfirmationForRiskAtLeast": "medium",
            "adminOnlyForRiskAtLeast": "critical",
            "auditRequired": True,
            "rateLimitsEnabled": True,
            "executionContractRequired": True,
            "secretPolicyRequired": True,
            "secretPolicyVersion": TOOL_SECRET_POLICY_VERSION,
            "secretsMustStayServerSide": True,
            "permissionMatrixAvailable": True,
            "frontendDirectExecutionAllowed": False,
        },
        "sideEffects": {
            "toolExecution": False,
            "networkToolCall": False,
            "externalWrite": False,
        },
    }


def build_tool_permission_matrix(
    *,
    username: str,
    is_admin: bool = False,
    has_developer_mode: bool = False,
    granted_permissions: set[str] | None = None,
) -> dict[str, Any]:
    context = _permission_context(
        username = username,
        is_admin = is_admin,
        has_developer_mode = has_developer_mode,
        granted_permissions = granted_permissions,
    )
    permission_set = _permission_set_from_context(context)
    tools: list[dict[str, Any]] = []
    allowed_count = 0
    confirmation_count = 0
    blocked_count = 0
    high_risk_count = 0
    for tool in TOOL_MANIFESTS:
        actions: list[dict[str, Any]] = []
        for action in tool.get("actions") or []:
            decision = _action_decision(
                tool = tool,
                action = action,
                permission_set = permission_set,
            )
            if decision["allowed"]:
                allowed_count += 1
            else:
                blocked_count += 1
            if decision["requiresConfirmation"]:
                confirmation_count += 1
            if _risk_at_least(str(decision["riskLevel"]), "high"):
                high_risk_count += 1
            actions.append(
                {
                    "id": action.get("id"),
                    "label": action.get("label"),
                    "connector": tool.get("connector"),
                    **decision,
                }
            )
        tools.append(
            {
                "id": tool.get("id"),
                "name": tool.get("name"),
                "category": tool.get("category"),
                "enabled": bool(tool.get("enabled")),
                "dataIsolation": tool.get("dataIsolation"),
                "actions": actions,
            }
        )
    return {
        "registryVersion": TOOL_REGISTRY_VERSION,
        "mode": "permission_matrix_dry_run",
        "username": username,
        "permissionContext": context,
        "tools": tools,
        "summary": {
            "toolCount": len(tools),
            "actionCount": allowed_count + blocked_count,
            "allowedActionCount": allowed_count,
            "blockedActionCount": blocked_count,
            "confirmationRequiredCount": confirmation_count,
            "highRiskActionCount": high_risk_count,
            "executionEnabled": False,
        },
        "policies": {
            "permissionSource": "cognix_user_permissions_plus_role",
            "humanConfirmationForRiskAtLeast": "medium",
            "adminOnlyForRiskAtLeast": "critical",
            "auditRequired": True,
            "rateLimitsEnabled": True,
            "secretPolicyRequired": True,
            "secretPolicyVersion": TOOL_SECRET_POLICY_VERSION,
            "secretsMustStayServerSide": True,
            "frontendDirectExecutionAllowed": False,
        },
        "sideEffects": {
            "permissionWrite": False,
            "secretRead": False,
            "toolExecution": False,
            "networkToolCall": False,
            "externalWrite": False,
        },
    }


def rate_limit_policy_for_key(rate_limit_key: str | None) -> dict[str, int] | None:
    if not rate_limit_key:
        return None
    policy = RATE_LIMIT_POLICIES.get(rate_limit_key.strip().lower())
    return deepcopy(policy or DEFAULT_RATE_LIMIT_POLICY)


def find_tool_action(tool_id: str, action_id: str) -> tuple[dict[str, Any], dict[str, Any]] | None:
    normalized_tool_id = tool_id.strip()
    normalized_action_id = action_id.strip()
    for tool in TOOL_MANIFESTS:
        if tool["id"] != normalized_tool_id:
            continue
        for action in tool.get("actions") or []:
            if action["id"] == normalized_action_id:
                return deepcopy(tool), deepcopy(action)
    return None


def plan_tool_action(
    *,
    tool_id: str,
    action_id: str,
    username: str,
    is_admin: bool = False,
    has_developer_mode: bool = False,
    granted_permissions: set[str] | None = None,
) -> dict[str, Any]:
    found = find_tool_action(tool_id, action_id)
    if found is None:
        return {
            "registryVersion": TOOL_REGISTRY_VERSION,
            "executionContractVersion": TOOL_EXECUTION_CONTRACT_VERSION,
            "secretPolicyVersion": TOOL_SECRET_POLICY_VERSION,
            "username": username,
            "toolId": tool_id,
            "actionId": action_id,
            "allowed": False,
            "status": "unknown_action",
            "reason": "Tool action is not registered in CogniX.",
            "missingPermissions": [],
            "requiresConfirmation": True,
            "riskLevel": "unknown",
            "sideEffects": {
                "toolExecution": False,
                "networkToolCall": False,
                "externalWrite": False,
                "secretRead": False,
                "permissionWrite": False,
            },
            "secretPolicy": _secret_policy(
                {"id": tool_id, "connector": "unknown"},
                {"id": action_id, "secretsRequired": False},
            ),
            "executionContract": {
                "contractVersion": TOOL_EXECUTION_CONTRACT_VERSION,
                "mode": "guarded_plan_only",
                "toolId": tool_id,
                "actionId": action_id,
                "allowedToPrepare": False,
                "readyForExecution": False,
                "automaticExecutionAllowed": False,
                "frontendDirectExecutionAllowed": False,
                "executorRequired": False,
                "plannedExecutor": None,
                "nextRequiredGate": "unknown_action",
                "allowedActions": ["record_tool_plan"],
                "blockedActions": [
                    "tool_execution",
                    "network_tool_call",
                    "external_write",
                    "secret_read",
                    "permission_write",
                    "frontend_direct_execution",
                ],
                "blockedWhen": ["unknown_action"],
                "sideEffects": {
                    "toolExecution": False,
                    "networkToolCall": False,
                    "externalWrite": False,
                    "secretRead": False,
                    "permissionWrite": False,
                },
            },
        }

    tool, action = found
    permission_context = _permission_context(
        username = username,
        is_admin = is_admin,
        has_developer_mode = has_developer_mode,
        granted_permissions = granted_permissions,
    )
    decision = _action_decision(
        tool = tool,
        action = action,
        permission_set = _permission_set_from_context(permission_context),
    )
    return {
        "registryVersion": TOOL_REGISTRY_VERSION,
        "executionContractVersion": TOOL_EXECUTION_CONTRACT_VERSION,
        "username": username,
        "toolId": tool["id"],
        "toolName": tool["name"],
        "actionId": action["id"],
        "actionLabel": action["label"],
        "permissionContext": permission_context,
        **decision,
        "executionContract": _execution_contract(
            tool = tool,
            action = action,
            decision = decision,
            permission_context = permission_context,
        ),
    }


def apply_rate_limit_result(
    plan: dict[str, Any],
    rate_limit: dict[str, Any] | None,
) -> dict[str, Any]:
    """Attach a rate-limit check to a tool plan without executing the tool."""

    if rate_limit is None:
        return plan
    updated = deepcopy(plan)
    updated["rateLimit"] = rate_limit
    contract = updated.get("executionContract")
    if not isinstance(contract, dict):
        return updated
    preconditions = contract.get("preconditions")
    if isinstance(preconditions, dict):
        preconditions["rateLimitChecked"] = True
        preconditions["rateLimitAllowed"] = bool(rate_limit.get("allowed"))
    contract["rateLimit"] = {
        "allowed": bool(rate_limit.get("allowed")),
        "remaining": rate_limit.get("remaining"),
        "resetAt": rate_limit.get("resetAt"),
    }
    blocked_when = [
        str(item)
        for item in contract.get("blockedWhen", [])
        if str(item or "").strip() and item != "rate_limit_check_required"
    ]
    if rate_limit.get("allowed"):
        contract["blockedWhen"] = blocked_when
        if contract.get("nextRequiredGate") == "rate_limit_check_required":
            contract["nextRequiredGate"] = blocked_when[0] if blocked_when else "executor_approval_gate"
        return updated

    if "rate_limited" not in blocked_when:
        blocked_when.append("rate_limited")
    contract["blockedWhen"] = blocked_when
    contract["nextRequiredGate"] = "rate_limited"
    contract["allowedToPrepare"] = False
    contract["executorRequired"] = False
    contract["plannedExecutor"] = None
    updated["allowed"] = False
    updated["status"] = "rate_limited"
    updated["reason"] = "Tool action rate limit reached."
    return updated


def _handoff_gate(
    gate_id: str,
    *,
    required: bool,
    passed: bool,
    reason: str,
) -> dict[str, Any]:
    return {
        "id": gate_id,
        "required": required,
        "status": "pass" if passed else ("blocked" if required else "not_required"),
        "passed": passed,
        "reason": reason,
    }


def _handoff_id(
    *,
    username: str,
    tool_id: str,
    action_id: str,
    request_id: str | None,
) -> str:
    seed = "|".join([username, tool_id, action_id, str(request_id or "no_request_id")])
    return f"handoff_{sha256(seed.encode('utf-8')).hexdigest()[:18]}"


def build_tool_execution_handoff(
    *,
    plan: dict[str, Any],
    confirmation_id: str | None = None,
    sandbox_run_id: str | None = None,
    request_id: str | None = None,
    executor_queue: str = "cognix_worker_queue",
) -> dict[str, Any]:
    contract = plan.get("executionContract")
    if not isinstance(contract, dict):
        contract = {}
    secret_policy = plan.get("secretPolicy")
    if not isinstance(secret_policy, dict):
        secret_policy = {}
    preconditions = contract.get("preconditions")
    if not isinstance(preconditions, dict):
        preconditions = {}
    tool_id = str(plan.get("toolId") or contract.get("toolId") or "")
    action_id = str(plan.get("actionId") or contract.get("actionId") or "")
    username = str(plan.get("username") or contract.get("permissionContext", {}).get("username") or "")
    rate_limit_checked = bool(preconditions.get("rateLimitChecked")) or not bool(preconditions.get("rateLimitRequired"))
    rate_limit_allowed = preconditions.get("rateLimitAllowed")
    rate_limit_passed = rate_limit_checked and rate_limit_allowed is not False
    confirmation_required = bool(preconditions.get("humanConfirmationRequired"))
    sandbox_required = bool(preconditions.get("sandboxRequired"))
    secrets_required = bool(preconditions.get("secretsRequired"))
    server_secret_policy_present = (
        not secrets_required
        or secret_policy.get("policyVersion") == TOOL_SECRET_POLICY_VERSION
        and bool(secret_policy.get("serverSideResolutionRequired"))
        and not bool(secret_policy.get("rawSecretExposureAllowed"))
    )
    gates = [
        _handoff_gate(
            "connector_enabled",
            required = True,
            passed = bool(preconditions.get("connectorEnabled")),
            reason = "Connector must be enabled before any executor can run.",
        ),
        _handoff_gate(
            "permissions_resolved",
            required = True,
            passed = bool(preconditions.get("permissionsResolved")),
            reason = "Effective CogniX permissions must satisfy the tool manifest.",
        ),
        _handoff_gate(
            "rate_limit_checked",
            required = bool(preconditions.get("rateLimitRequired")),
            passed = rate_limit_passed,
            reason = "Rate limit must be checked and allowed before executor handoff.",
        ),
        _handoff_gate(
            "human_confirmation",
            required = confirmation_required,
            passed = (not confirmation_required) or bool(str(confirmation_id or "").strip()),
            reason = "Human confirmation is required for medium and higher risk actions.",
        ),
        _handoff_gate(
            "sandbox_ready",
            required = sandbox_required,
            passed = (not sandbox_required) or bool(str(sandbox_run_id or "").strip()),
            reason = "Sandbox run reference is required for isolated or risky tool actions.",
        ),
        _handoff_gate(
            "server_side_secret_resolution",
            required = secrets_required,
            passed = server_secret_policy_present,
            reason = "Secrets must be resolved later by a server-side executor, never in this handoff.",
        ),
    ]
    blocked_gates = [gate["id"] for gate in gates if gate["required"] and not gate["passed"]]
    blocked_when = sorted(
        {
            str(item)
            for item in contract.get("blockedWhen", [])
            if str(item or "").strip()
        }
        | set(blocked_gates)
        | {"executor_approval_required"}
    )
    allowed_to_prepare = bool(contract.get("allowedToPrepare"))
    ready_for_executor_review = allowed_to_prepare and not blocked_gates
    handoff_id = _handoff_id(
        username = username,
        tool_id = tool_id,
        action_id = action_id,
        request_id = request_id,
    )
    return {
        "handoffVersion": TOOL_EXECUTION_HANDOFF_VERSION,
        "executionContractVersion": contract.get("contractVersion") or TOOL_EXECUTION_CONTRACT_VERSION,
        "mode": "executor_handoff_dry_run",
        "handoffId": handoff_id,
        "idempotencyKey": handoff_id,
        "requestId": request_id,
        "username": username,
        "toolId": tool_id,
        "actionId": action_id,
        "connector": contract.get("connector"),
        "plannedExecutor": contract.get("plannedExecutor"),
        "executorQueue": executor_queue,
        "status": "ready_for_executor_review" if ready_for_executor_review else "blocked_missing_gate",
        "readyForExecutorReview": ready_for_executor_review,
        "readyForJobEnqueue": False,
        "executionAllowedHere": False,
        "automaticExecutionAllowed": False,
        "frontendDirectExecutionAllowed": False,
        "gates": gates,
        "blockedWhen": blocked_when,
        "executorInput": {
            "toolRef": tool_id,
            "actionRef": action_id,
            "payloadRef": "client_payload_not_stored_in_handoff",
            "confirmationId": confirmation_id,
            "sandboxRunId": sandbox_run_id,
            "secretRefs": secret_policy.get("allowedSecretSources", []),
            "secretValuesIncluded": False,
            "rateLimit": contract.get("rateLimit"),
        },
        "policies": {
            "jobEnqueueAllowedHere": False,
            "executorMustRecheckPermissions": True,
            "executorMustRecheckRateLimit": True,
            "executorMustResolveSecretsServerSide": True,
            "humanApprovalRequiredBeforeExecution": True,
            "rawPayloadStorageAllowed": False,
            "auditRawPayloadAllowed": False,
        },
        "dataBoundary": {
            "dataIsolation": contract.get("dataBoundary", {}).get("dataIsolation"),
            "secretsStayServerSide": True,
            "rawSecretExposureAllowed": False,
            "clientSecretTransmitAllowed": False,
            "secretValuesIncluded": False,
            "rawPayloadIncluded": False,
        },
        "sideEffects": {
            "toolExecution": False,
            "networkToolCall": False,
            "externalWrite": False,
            "secretRead": False,
            "permissionWrite": False,
            "jobEnqueue": False,
        },
    }
