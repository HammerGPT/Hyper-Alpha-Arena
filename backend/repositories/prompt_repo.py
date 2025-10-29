from __future__ import annotations

from typing import List, Optional, Tuple

from sqlalchemy.orm import Session
from sqlalchemy import select

from database.models import PromptTemplate, AccountPromptBinding, Account


def get_all_templates(db: Session) -> List[PromptTemplate]:
    statement = select(PromptTemplate).order_by(PromptTemplate.key.asc())
    return list(db.execute(statement).scalars().all())


def get_template_by_key(db: Session, key: str) -> Optional[PromptTemplate]:
    statement = select(PromptTemplate).where(PromptTemplate.key == key)
    return db.execute(statement).scalar_one_or_none()


def create_template(
    db: Session,
    *,
    key: str,
    name: str,
    description: Optional[str],
    template_text: str,
    system_template_text: Optional[str] = None,
    updated_by: Optional[str] = None,
) -> PromptTemplate:
    template = PromptTemplate(
        key=key,
        name=name,
        description=description,
        template_text=template_text,
        system_template_text=system_template_text or template_text,
        updated_by=updated_by,
    )
    db.add(template)
    db.commit()
    db.refresh(template)
    return template


def update_template(
    db: Session,
    *,
    key: str,
    template_text: str,
    description: Optional[str] = None,
    updated_by: Optional[str] = None,
) -> PromptTemplate:
    template = get_template_by_key(db, key)
    if not template:
        raise ValueError(f"Prompt template with key '{key}' not found")
    template.template_text = template_text
    if description is not None:
        template.description = description
    template.updated_by = updated_by
    db.add(template)
    db.commit()
    db.refresh(template)
    return template


def restore_template(db: Session, *, key: str, updated_by: Optional[str] = None) -> PromptTemplate:
    template = get_template_by_key(db, key)
    if not template:
        raise ValueError(f"Prompt template with key '{key}' not found")
    template.template_text = template.system_template_text
    template.updated_by = updated_by
    db.add(template)
    db.commit()
    db.refresh(template)
    return template


def list_bindings(db: Session) -> List[Tuple[AccountPromptBinding, Account, PromptTemplate]]:
    statement = (
        select(AccountPromptBinding, Account, PromptTemplate)
        .join(Account, AccountPromptBinding.account_id == Account.id)
        .join(PromptTemplate, AccountPromptBinding.prompt_template_id == PromptTemplate.id)
        .order_by(Account.name.asc())
    )
    return list(db.execute(statement).all())


def get_binding_by_account(db: Session, account_id: int) -> Optional[AccountPromptBinding]:
    statement = select(AccountPromptBinding).where(AccountPromptBinding.account_id == account_id)
    return db.execute(statement).scalar_one_or_none()


def upsert_binding(
    db: Session,
    *,
    account_id: int,
    prompt_template_id: int,
    updated_by: Optional[str] = None,
) -> AccountPromptBinding:
    binding = get_binding_by_account(db, account_id)

    if binding:
        binding.prompt_template_id = prompt_template_id
        binding.updated_by = updated_by
    else:
        binding = AccountPromptBinding(
            account_id=account_id,
            prompt_template_id=prompt_template_id,
            updated_by=updated_by,
        )
        db.add(binding)

    db.commit()
    db.refresh(binding)
    return binding


def delete_binding(db: Session, binding_id: int) -> None:
    binding = db.get(AccountPromptBinding, binding_id)
    if not binding:
        raise ValueError(f"Prompt binding with id '{binding_id}' not found")
    db.delete(binding)
    db.commit()


def get_prompt_for_account(db: Session, account_id: int) -> Optional[PromptTemplate]:
    binding = get_binding_by_account(db, account_id)
    if binding:
        template = db.get(PromptTemplate, binding.prompt_template_id)
        if template:
            return template
    return None


def ensure_default_prompt(db: Session) -> PromptTemplate:
    template = get_template_by_key(db, "default")
    if not template:
        raise ValueError("Default prompt template not found")
    return template
