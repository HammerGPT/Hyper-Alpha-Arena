from __future__ import annotations

from sqlalchemy.orm import Session
from sqlalchemy import text

from config.prompt_templates import DEFAULT_PROMPT_TEMPLATE, PRO_PROMPT_TEMPLATE, HYPERLIQUID_PROMPT_TEMPLATE
from repositories import prompt_repo

SYSTEM_USER = "system"


def seed_prompt_templates(db: Session) -> None:
    """Ensure default prompt templates exist in the database."""
    # Clean up legacy table if it still exists
    try:
        db.execute(text("DROP TABLE IF EXISTS model_prompt_overrides"))
        db.commit()
    except Exception:
        db.rollback()

    templates_to_seed = [
        {
            "key": "default",
            "name": "Default Prompt",
            "description": "Baseline prompt used for AI trading decisions.",
            "template_text": DEFAULT_PROMPT_TEMPLATE,
        },
        {
            "key": "pro",
            "name": "Pro Prompt",
            "description": "Structured prompt inspired by Alpha Arena with richer context.",
            "template_text": PRO_PROMPT_TEMPLATE,
        },
        {
            "key": "hyperliquid",
            "name": "Hyperliquid Prompt",
            "description": "Specialized prompt for Hyperliquid perpetual contract trading with detailed margin and leverage information.",
            "template_text": HYPERLIQUID_PROMPT_TEMPLATE,
        },
    ]

    updated = False

    for item in templates_to_seed:
        existing = prompt_repo.get_template_by_key(db, item["key"])
        if not existing:
            prompt_repo.create_template(
                db,
                key=item["key"],
                name=item["name"],
                description=item["description"],
                template_text=item["template_text"],
                system_template_text=item["template_text"],
                updated_by=SYSTEM_USER,
            )
            updated = True
        else:
            has_changes = False
            if existing.name != item["name"]:
                existing.name = item["name"]
                has_changes = True
            if existing.description != item["description"]:
                existing.description = item["description"]
                has_changes = True
            if existing.system_template_text != item["template_text"]:
                existing.system_template_text = item["template_text"]
                has_changes = True

            if has_changes:
                existing.updated_by = SYSTEM_USER
                db.add(existing)
                updated = True

    if updated:
        db.commit()
