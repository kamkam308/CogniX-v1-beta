from __future__ import annotations

import asyncio
import secrets
import sqlite3
import sys
from pathlib import Path

import pytest
from fastapi import HTTPException

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from auth import storage as auth_storage
from core.cognix import api_surface as cognix_api_surface
from core.cognix import education_spaces as cognix_education_spaces
from core.cognix import module_registry as cognix_module_registry
from routes import auth as auth_routes
from routes import cognix as cognix_routes
from storage import cognix_db
from storage import studio_db as studio_db_storage


@pytest.fixture(autouse = True)
def isolated_state(tmp_path, monkeypatch):
    studio_home = tmp_path / "studio_home"
    studio_home.mkdir(parents = True, exist_ok = True)
    monkeypatch.setenv("UNSLOTH_STUDIO_HOME", str(studio_home))
    monkeypatch.setenv("UNSLOTH_STUDIO_PROJECTS_HOME", str(tmp_path / "project_workspaces"))
    monkeypatch.setattr(auth_storage, "DB_PATH", tmp_path / "auth.db")
    monkeypatch.setattr(auth_storage, "_BOOTSTRAP_PW_PATH", tmp_path / ".bootstrap_password")
    monkeypatch.setattr(auth_storage, "_bootstrap_password", None)
    monkeypatch.setattr(auth_storage, "_api_key_pbkdf2_salt_cache", None)
    monkeypatch.setattr(cognix_db, "_schema_ready", False)
    monkeypatch.setattr(studio_db_storage, "_schema_ready", False)
    auth_routes._LOGIN_BUCKETS.clear()
    auth_routes._LOGIN_IP_BUCKETS.clear()
    auth_routes._REGISTER_IP_BUCKETS.clear()
    yield
    cognix_db._schema_ready = False
    studio_db_storage._schema_ready = False
    auth_routes._LOGIN_BUCKETS.clear()
    auth_routes._LOGIN_IP_BUCKETS.clear()
    auth_routes._REGISTER_IP_BUCKETS.clear()


def run_async(coro):
    return asyncio.run(coro)


def seed_accounts() -> None:
    auth_storage.create_initial_user(
        username = auth_storage.DEFAULT_ADMIN_USERNAME,
        password = "admin-password-123",
        jwt_secret = secrets.token_urlsafe(64),
        must_change_password = False,
    )
    auth_storage.create_user(
        username = "alice",
        email = "alice@example.com",
        password = "alice-password-123",
    )
    auth_storage.create_user(
        username = "bob",
        email = "bob@example.com",
        password = "bob-password-123",
    )


def test_education_spaces_blueprint_schema_module_registry_and_surface_contract():
    blueprint = cognix_education_spaces.build_education_blueprint()
    assert blueprint["educationSpaceServiceVersion"] == "cognix_education_space_service_v1"
    assert blueprint["examGuardVersion"] == "cognix_exam_guard_v1"
    assert blueprint["services"] == [
        "EducationSpaceService",
        "ClassroomManager",
        "CoursePlanner",
        "AssessmentPolicyEngine",
        "ExamGuard",
    ]
    assert {
        "education_spaces",
        "education_classes",
        "education_members",
        "education_courses",
        "education_assignments",
        "education_exam_policies",
    }.issubset(set(blueprint["tables"]))
    assert blueprint["security"]["teacherStudentSeparation"] is True
    assert blueprint["security"]["studentModelCallAllowed"] is False
    assert blueprint["sideEffects"]["generation"] is False
    assert blueprint["sideEffects"]["toolExecution"] is False

    conn = sqlite3.connect(":memory:")
    try:
        cognix_db._ensure_education_space_columns(conn)
        space_columns = {row[1] for row in conn.execute("PRAGMA table_info(education_spaces)").fetchall()}
        class_columns = {row[1] for row in conn.execute("PRAGMA table_info(education_classes)").fetchall()}
        member_columns = {row[1] for row in conn.execute("PRAGMA table_info(education_members)").fetchall()}
        assignment_columns = {row[1] for row in conn.execute("PRAGMA table_info(education_assignments)").fetchall()}
        policy_columns = {row[1] for row in conn.execute("PRAGMA table_info(education_exam_policies)").fetchall()}
        assert {"name", "institution_type", "created_by", "visibility", "settings_json"}.issubset(space_columns)
        assert {"space_id", "teacher_username", "class_code"}.issubset(class_columns)
        assert {"member_username", "role", "added_by"}.issubset(member_columns)
        assert {"assignment_type", "instructions", "policy_json"}.issubset(assignment_columns)
        assert {"exam_mode", "anti_abuse_level", "allowed_tools_json", "restrictions_json"}.issubset(policy_columns)
    finally:
        conn.close()

    modules = {item["id"]: item for item in cognix_module_registry.build_module_registry()["modules"]}
    education = modules["cognix-education-spaces"]
    assert "education_space_service" in education["capabilities"]
    assert "exam_guard" in education["capabilities"]
    assert "/api/cognix/education/assignments/{assignment_id}/exam-access-decision" in education["routes"]

    contract = cognix_api_surface.build_api_surface_contract(
        [{"path": "/api/cognix/education/spaces", "methods": ["GET"]}]
    )
    routes = {item["path"]: item for item in contract["productNavigationContract"]["routes"]}
    assert routes["/education"]["status"] == "equivalent"
    assert routes["/education"]["matchedRoute"] == "/api/cognix/education/spaces"


def test_education_routes_create_class_assignment_and_guard_exam_tools():
    seed_accounts()
    admin = auth_storage.DEFAULT_ADMIN_USERNAME

    with pytest.raises(HTTPException) as non_admin_create:
        run_async(
            cognix_routes.create_education_space(
                cognix_routes.EducationSpaceRequest(name = "Physics School"),
                current_subject = "alice",
            )
        )
    assert non_admin_create.value.status_code == 403

    created = run_async(
        cognix_routes.create_education_space(
            cognix_routes.EducationSpaceRequest(
                name = "Physics School",
                institutionType = "university",
                visibility = "organization",
            ),
            current_subject = admin,
        )
    )
    space_id = created["space"]["id"]
    assert created["sideEffects"]["spaceWrite"] is True
    assert created["sideEffects"]["generation"] is False

    class_response = run_async(
        cognix_routes.create_education_class(
            space_id,
            cognix_routes.EducationClassRequest(
                name = "Mechanics 101",
                subject = "physics",
                teacherUsername = "alice",
            ),
            current_subject = admin,
        )
    )
    class_id = class_response["class"]["id"]
    assert class_response["teacherMember"]["role"] == "teacher"

    member_response = run_async(
        cognix_routes.add_education_class_member(
            class_id,
            cognix_routes.EducationMemberRequest(memberUsername = "bob", role = "student"),
            current_subject = admin,
        )
    )
    assert member_response["member"]["memberUsername"] == "bob"

    course_response = run_async(
        cognix_routes.create_education_course(
            class_id,
            cognix_routes.EducationCourseRequest(
                title = "Forces",
                subject = "physics",
                outline = ["Newton laws", "Friction"],
            ),
            current_subject = admin,
        )
    )
    assert course_response["course"]["outline"] == ["Newton laws", "Friction"]

    assignment_response = run_async(
        cognix_routes.create_education_assignment(
            class_id,
            cognix_routes.EducationAssignmentRequest(
                title = "Final exam",
                assignmentType = "exam",
                courseId = course_response["course"]["id"],
                instructions = "Solve without external models.",
            ),
            current_subject = admin,
        )
    )
    assignment_id = assignment_response["assignment"]["id"]
    assert assignment_response["assignmentPlan"]["assignment"]["requiresExamPolicy"] is True

    policy_response = run_async(
        cognix_routes.upsert_education_exam_policy(
            assignment_id,
            cognix_routes.EducationExamPolicyRequest(
                examMode = "restricted",
                antiAbuseLevel = "strict",
                allowedTools = ["calculator"],
            ),
            current_subject = admin,
        )
    )
    assert policy_response["examPolicy"]["allowedTools"] == ["calculator"]
    assert policy_response["sideEffects"]["examPolicyWrite"] is True

    blocked = run_async(
        cognix_routes.education_exam_access_decision(
            assignment_id,
            cognix_routes.EducationExamAccessRequest(role = "student", action = "use_tool", toolId = "web_search"),
            current_subject = "bob",
        )
    )
    assert blocked["decision"]["allowed"] is False
    assert "tool_not_allowed_by_exam_policy" in blocked["decision"]["blockedReasons"]

    allowed = run_async(
        cognix_routes.education_exam_access_decision(
            assignment_id,
            cognix_routes.EducationExamAccessRequest(role = "student", action = "use_tool", toolId = "calculator"),
            current_subject = "bob",
        )
    )
    assert allowed["decision"]["allowed"] is True

    bob_spaces = run_async(cognix_routes.education_spaces(current_subject = "bob"))
    assert [space["id"] for space in bob_spaces["spaces"]] == [space_id]

    audit_actions = {item.get("action") for item in cognix_db.list_audit_logs(limit = 20)}
    assert {
        "education_space_created",
        "education_class_created",
        "education_member_added",
        "education_course_created",
        "education_assignment_created",
        "education_exam_policy_updated",
    }.issubset(audit_actions)
