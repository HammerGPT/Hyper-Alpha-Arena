from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field, ConfigDict


class PromptTemplateResponse(BaseModel):
    id: int
    key: str
    name: str
    description: Optional[str] = None
    template_text: str = Field(..., alias="templateText")
    system_template_text: str = Field(..., alias="systemTemplateText")
    updated_by: Optional[str] = Field(None, alias="updatedBy")
    updated_at: Optional[datetime] = Field(None, alias="updatedAt")

    model_config = ConfigDict(populate_by_name=True, from_attributes=True)


class PromptBindingResponse(BaseModel):
    id: int
    account_id: int = Field(..., alias="accountId")
    account_name: str = Field(..., alias="accountName")
    account_model: Optional[str] = Field(None, alias="accountModel")
    prompt_template_id: int = Field(..., alias="promptTemplateId")
    prompt_key: str = Field(..., alias="promptKey")
    prompt_name: str = Field(..., alias="promptName")
    updated_by: Optional[str] = Field(None, alias="updatedBy")
    updated_at: Optional[datetime] = Field(None, alias="updatedAt")

    model_config = ConfigDict(populate_by_name=True, from_attributes=True)


class PromptListResponse(BaseModel):
    templates: List[PromptTemplateResponse]
    bindings: List[PromptBindingResponse]


class PromptTemplateUpdateRequest(BaseModel):
    template_text: str = Field(..., alias="templateText")
    description: Optional[str] = None
    updated_by: Optional[str] = Field(None, alias="updatedBy")

    model_config = ConfigDict(populate_by_name=True)


class PromptTemplateRestoreRequest(BaseModel):
    updated_by: Optional[str] = Field(None, alias="updatedBy")

    model_config = ConfigDict(populate_by_name=True)


class PromptBindingUpsertRequest(BaseModel):
    id: Optional[int] = None
    account_id: Optional[int] = Field(None, alias="accountId")
    prompt_template_id: Optional[int] = Field(None, alias="promptTemplateId")
    updated_by: Optional[str] = Field(None, alias="updatedBy")

    model_config = ConfigDict(populate_by_name=True)
