# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

"""Native CogniX education and university spaces.

The education module models school/university spaces, classes, courses,
assignments, and exam safety policy. It is intentionally plan-first: it does
not generate answers, call external tools, or enforce browser lockdown by
itself.
"""

from __future__ import annotations

import hashlib
from typing import Any


COGNIX_EDUCATION_SPACE_SERVICE_VERSION = "cognix_education_space_service_v1"
COGNIX_CLASSROOM_MANAGER_VERSION = "cognix_classroom_manager_v1"
COGNIX_COURSE_PLANNER_VERSION = "cognix_course_planner_v1"
COGNIX_ASSESSMENT_POLICY_ENGINE_VERSION = "cognix_assessment_policy_engine_v1"
COGNIX_EXAM_GUARD_VERSION = "cognix_exam_guard_v1"

EDUCATION_SERVICES = [
    "EducationSpaceService",
    "ClassroomManager",
    "CoursePlanner",
    "AssessmentPolicyEngine",
    "ExamGuard",
]

EDUCATION_TABLES = [
    "education_spaces",
    "education_classes",
    "education_members",
    "education_courses",
    "education_assignments",
    "education_exam_policies",
]

EDUCATION_ROLES = {"teacher", "student", "admin", "guardian"}
ASSIGNMENT_TYPES = {"homework", "quiz", "exam", "project"}
EXAM_MODES = {"open_book", "restricted", "lockdown_planned"}
ANTI_ABUSE_LEVELS = {"low", "medium", "high", "strict"}


def _text(value: Any, limit: int = 240, fallback: str = "") -> str:
    text = str(value if value is not None else fallback).replace("\r\n", "\n").strip()
    return " ".join(text.split())[:limit].strip()


def _multiline(value: Any, limit: int = 4000) -> str:
    text = str(value or "").replace("\r\n", "\n").strip()
    while "\n\n\n" in text:
        text = text.replace("\n\n\n", "\n\n")
    return text[:limit].strip()


def _key(value: Any, fallback: str = "") -> str:
    text = _text(value, 160, fallback).lower()
    cleaned = "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in text)
    return cleaned.strip("_")[:120] or fallback


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _stable_id(prefix: str, *parts: Any) -> str:
    payload = "|".join(str(part or "") for part in parts)
    return f"{prefix}_{hashlib.sha256(payload.encode('utf-8')).hexdigest()[:14]}"


def _normalize_role(role: str | None) -> str:
    normalized = _key(role, "student")
    return normalized if normalized in EDUCATION_ROLES else "student"


def _normalize_assignment_type(value: str | None) -> str:
    normalized = _key(value, "homework")
    return normalized if normalized in ASSIGNMENT_TYPES else "homework"


def _normalize_exam_mode(value: str | None) -> str:
    normalized = _key(value, "restricted")
    return normalized if normalized in EXAM_MODES else "restricted"


def _normalize_anti_abuse(value: str | None) -> str:
    normalized = _key(value, "medium")
    return normalized if normalized in ANTI_ABUSE_LEVELS else "medium"


def build_education_blueprint() -> dict[str, Any]:
    return {
        "educationSpaceServiceVersion": COGNIX_EDUCATION_SPACE_SERVICE_VERSION,
        "classroomManagerVersion": COGNIX_CLASSROOM_MANAGER_VERSION,
        "coursePlannerVersion": COGNIX_COURSE_PLANNER_VERSION,
        "assessmentPolicyEngineVersion": COGNIX_ASSESSMENT_POLICY_ENGINE_VERSION,
        "examGuardVersion": COGNIX_EXAM_GUARD_VERSION,
        "mode": "native_education_space_contract",
        "services": EDUCATION_SERVICES,
        "tables": EDUCATION_TABLES,
        "roles": sorted(EDUCATION_ROLES),
        "assignmentTypes": sorted(ASSIGNMENT_TYPES),
        "examModes": sorted(EXAM_MODES),
        "antiAbuseLevels": sorted(ANTI_ABUSE_LEVELS),
        "educationEditionTargets": ["university", "school", "enterprise"],
        "security": {
            "roleScopedAccess": True,
            "teacherStudentSeparation": True,
            "examAntiAbusePolicy": True,
            "studentModelCallAllowed": False,
            "teacherModelCallAllowed": False,
            "frontendDirectModelCallAllowed": False,
            "externalToolUseDuringExamRequiresPolicy": True,
        },
        "sideEffects": {
            "databaseWrite": False,
            "spaceWrite": False,
            "classWrite": False,
            "memberWrite": False,
            "courseWrite": False,
            "assignmentWrite": False,
            "examPolicyWrite": False,
            "auditWrite": False,
            "modelLoad": False,
            "generation": False,
            "toolExecution": False,
            "networkCall": False,
        },
    }


def build_space_plan(
    *,
    name: str,
    institution_type: str = "school",
    created_by: str,
    visibility: str = "restricted",
) -> dict[str, Any]:
    normalized_name = _text(name, 240, "Education space")
    normalized_type = _key(institution_type, "school")
    normalized_visibility = _key(visibility, "restricted")
    return {
        "educationSpaceServiceVersion": COGNIX_EDUCATION_SPACE_SERVICE_VERSION,
        "mode": "native_education_space_plan",
        "spacePlanId": _stable_id("eduspace_plan", normalized_name, normalized_type, created_by),
        "space": {
            "name": normalized_name,
            "institutionType": normalized_type,
            "createdBy": _text(created_by, 160),
            "visibility": normalized_visibility,
            "defaultRoles": ["admin", "teacher", "student"],
            "defaultPolicies": {
                "studentsCanCreateCourses": False,
                "teachersCanCreateAssignments": True,
                "examModeRequiresPolicy": True,
                "auditEveryExamPolicyChange": True,
            },
        },
        "sideEffects": build_education_blueprint()["sideEffects"],
    }


def build_class_plan(
    *,
    space_id: str,
    name: str,
    subject: str,
    teacher_username: str,
    class_code: str | None = None,
) -> dict[str, Any]:
    normalized_name = _text(name, 240, "Class")
    normalized_subject = _text(subject, 160, "general")
    return {
        "classroomManagerVersion": COGNIX_CLASSROOM_MANAGER_VERSION,
        "mode": "native_classroom_plan",
        "classPlanId": _stable_id("educlass_plan", space_id, normalized_name, teacher_username),
        "class": {
            "spaceId": _text(space_id, 160),
            "name": normalized_name,
            "subject": normalized_subject,
            "teacherUsername": _text(teacher_username, 160),
            "classCode": _text(class_code, 80) or _stable_id("class", space_id, normalized_name)[-8:],
            "rolePolicy": {
                "teacherCanManageAssignments": True,
                "studentsCanViewOwnWork": True,
                "guardiansReadOnly": True,
            },
        },
        "sideEffects": build_education_blueprint()["sideEffects"],
    }


def build_course_plan(
    *,
    space_id: str,
    class_id: str,
    title: str,
    subject: str,
    outline: list[Any] | None = None,
    created_by: str = "",
) -> dict[str, Any]:
    outline_items = [_text(item, 240) for item in _as_list(outline) if _text(item, 240)]
    return {
        "coursePlannerVersion": COGNIX_COURSE_PLANNER_VERSION,
        "mode": "native_course_plan",
        "coursePlanId": _stable_id("educourse_plan", space_id, class_id, title),
        "course": {
            "spaceId": _text(space_id, 160),
            "classId": _text(class_id, 160),
            "title": _text(title, 240, "Course"),
            "subject": _text(subject, 160, "general"),
            "outline": outline_items,
            "createdBy": _text(created_by, 160),
        },
        "sideEffects": build_education_blueprint()["sideEffects"],
    }


def build_assignment_plan(
    *,
    space_id: str,
    class_id: str,
    course_id: str | None,
    title: str,
    assignment_type: str = "homework",
    instructions: str = "",
    due_at: str | None = None,
    created_by: str = "",
) -> dict[str, Any]:
    normalized_type = _normalize_assignment_type(assignment_type)
    requires_exam_policy = normalized_type == "exam"
    return {
        "assessmentPolicyEngineVersion": COGNIX_ASSESSMENT_POLICY_ENGINE_VERSION,
        "mode": "native_assignment_plan",
        "assignmentPlanId": _stable_id("eduassign_plan", space_id, class_id, title, normalized_type),
        "assignment": {
            "spaceId": _text(space_id, 160),
            "classId": _text(class_id, 160),
            "courseId": _text(course_id, 160) or None,
            "title": _text(title, 240, "Assignment"),
            "assignmentType": normalized_type,
            "instructions": _multiline(instructions, 4000),
            "dueAt": _text(due_at, 120) or None,
            "createdBy": _text(created_by, 160),
            "requiresExamPolicy": requires_exam_policy,
        },
        "policy": {
            "examPolicyRequired": requires_exam_policy,
            "generationAllowedForStudent": False,
            "answerLeakPrevention": True,
            "teacherReviewRequired": normalized_type in {"exam", "quiz"},
        },
        "sideEffects": build_education_blueprint()["sideEffects"],
    }


def build_exam_policy_plan(
    *,
    space_id: str,
    class_id: str,
    assignment_id: str,
    exam_mode: str = "restricted",
    anti_abuse_level: str = "medium",
    allowed_tools: list[Any] | None = None,
    created_by: str = "",
) -> dict[str, Any]:
    mode = _normalize_exam_mode(exam_mode)
    abuse_level = _normalize_anti_abuse(anti_abuse_level)
    tools = [_key(item, "") for item in _as_list(allowed_tools) if _key(item, "")]
    external_tools_allowed = any(tool not in {"calculator", "latex_renderer", "course_documents"} for tool in tools)
    restrictions = {
        "blockExternalModels": mode != "open_book",
        "blockUnapprovedTools": True,
        "disableAnswerSharing": True,
        "requireTeacherReview": abuse_level in {"high", "strict"},
        "logSuspiciousActivity": abuse_level in {"medium", "high", "strict"},
        "externalToolsAllowed": external_tools_allowed,
    }
    return {
        "assessmentPolicyEngineVersion": COGNIX_ASSESSMENT_POLICY_ENGINE_VERSION,
        "examGuardVersion": COGNIX_EXAM_GUARD_VERSION,
        "mode": "native_exam_policy_plan",
        "examPolicyPlanId": _stable_id("eduexam_plan", space_id, class_id, assignment_id, mode, abuse_level),
        "examPolicy": {
            "spaceId": _text(space_id, 160),
            "classId": _text(class_id, 160),
            "assignmentId": _text(assignment_id, 160),
            "examMode": mode,
            "antiAbuseLevel": abuse_level,
            "allowedTools": tools,
            "restrictions": restrictions,
            "createdBy": _text(created_by, 160),
        },
        "risk": {
            "level": "high" if external_tools_allowed or abuse_level in {"high", "strict"} else "medium",
            "approvalRecommended": external_tools_allowed,
            "reason": "external_exam_tools_need_policy_review" if external_tools_allowed else "native_exam_guard_policy",
        },
        "sideEffects": build_education_blueprint()["sideEffects"],
    }


def build_exam_access_decision(
    *,
    role: str,
    action: str,
    exam_policy: dict[str, Any] | None = None,
    tool_id: str | None = None,
) -> dict[str, Any]:
    normalized_role = _normalize_role(role)
    normalized_action = _key(action, "view")
    policy = exam_policy or {}
    restrictions = policy.get("restrictions") if isinstance(policy.get("restrictions"), dict) else {}
    tool = _key(tool_id, "")
    allowed_tools = {_key(item, "") for item in _as_list(policy.get("allowedTools") or policy.get("allowed_tools"))}
    blocked_reasons: list[str] = []
    if normalized_role == "student" and normalized_action in {"grade", "view_answers", "edit_policy"}:
        blocked_reasons.append("student_role_cannot_perform_teacher_action")
    if normalized_action == "use_tool" and restrictions.get("blockUnapprovedTools", True) and tool and tool not in allowed_tools:
        blocked_reasons.append("tool_not_allowed_by_exam_policy")
    if normalized_action in {"call_external_model", "use_cloud"} and restrictions.get("blockExternalModels", True):
        blocked_reasons.append("external_model_blocked_by_exam_policy")
    return {
        "examGuardVersion": COGNIX_EXAM_GUARD_VERSION,
        "mode": "native_exam_access_decision",
        "role": normalized_role,
        "action": normalized_action,
        "toolId": tool or None,
        "allowed": not blocked_reasons,
        "blockedReasons": blocked_reasons,
        "visibleToTeacher": True,
        "sideEffects": build_education_blueprint()["sideEffects"],
    }
