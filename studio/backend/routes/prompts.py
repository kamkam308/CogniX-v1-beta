# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026-present the Unsloth AI Inc. team. All rights reserved. See /studio/LICENSE.AGPL-3.0

"""
Prompt storage API routes backed by studio.db.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from auth.authentication import get_current_jwt_subject
from storage.studio_db import (
    bulk_upsert_prompt_entries,
    bulk_upsert_prompt_lists,
    delete_prompt_entry,
    delete_prompt_list_db,
    list_prompt_entries,
    list_prompt_lists_db,
    upsert_prompt_entry,
    upsert_prompt_list,
)

router = APIRouter()


class PromptEntry(BaseModel):
    id: str = Field(max_length = 128)
    name: str = Field(max_length = 500)
    text: str = Field(max_length = 100_000)
    createdAt: int
    updatedAt: int


class PromptList(BaseModel):
    id: str = Field(max_length = 128)
    name: str = Field(max_length = 500)
    items: list[str] = Field(max_length = 10_000)
    createdAt: int
    updatedAt: int


class BulkEntriesRequest(BaseModel):
    entries: list[PromptEntry]


class BulkListsRequest(BaseModel):
    lists: list[PromptList]


@router.get("/entries")
def get_entries(current_subject: str = Depends(get_current_jwt_subject)):
    return {"entries": list_prompt_entries(owner_username = current_subject)}


@router.put("/entries/{entry_id}")
def put_entry(
    entry_id: str,
    entry: PromptEntry,
    current_subject: str = Depends(get_current_jwt_subject),
):
    if entry.id != entry_id:
        raise HTTPException(status_code = 400, detail = "ID mismatch")
    return upsert_prompt_entry(entry.model_dump(), owner_username = current_subject)


@router.delete("/entries/{entry_id}", status_code = 204)
def remove_entry(entry_id: str, current_subject: str = Depends(get_current_jwt_subject)):
    delete_prompt_entry(entry_id, owner_username = current_subject)


@router.post("/entries/bulk")
def bulk_entries(req: BulkEntriesRequest, current_subject: str = Depends(get_current_jwt_subject)):
    count = bulk_upsert_prompt_entries(
        [e.model_dump() for e in req.entries], owner_username = current_subject
    )
    return {"count": count}


@router.get("/lists")
def get_lists(current_subject: str = Depends(get_current_jwt_subject)):
    return {"lists": list_prompt_lists_db(owner_username = current_subject)}


@router.put("/lists/{list_id}")
def put_list(
    list_id: str,
    lst: PromptList,
    current_subject: str = Depends(get_current_jwt_subject),
):
    if lst.id != list_id:
        raise HTTPException(status_code = 400, detail = "ID mismatch")
    return upsert_prompt_list(lst.model_dump(), owner_username = current_subject)


@router.delete("/lists/{list_id}", status_code = 204)
def remove_list(list_id: str, current_subject: str = Depends(get_current_jwt_subject)):
    delete_prompt_list_db(list_id, owner_username = current_subject)


@router.post("/lists/bulk")
def bulk_lists(req: BulkListsRequest, current_subject: str = Depends(get_current_jwt_subject)):
    count = bulk_upsert_prompt_lists(
        [l.model_dump() for l in req.lists], owner_username = current_subject
    )
    return {"count": count}
