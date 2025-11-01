from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database.connection import SessionLocal
from repositories import prompt_repo
from database.models import PromptTemplate, Account
from schemas.prompt import (
    PromptListResponse,
    PromptTemplateUpdateRequest,
    PromptTemplateRestoreRequest,
    PromptTemplateResponse,
    PromptBindingUpsertRequest,
    PromptBindingResponse,
)


router = APIRouter(prefix="/api/prompts", tags=["Prompt Templates"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Support both /api/prompts and /api/prompts/
@router.get("", response_model=PromptListResponse, response_model_exclude_none=True)
@router.get("/", response_model=PromptListResponse, response_model_exclude_none=True)
def list_prompt_templates(db: Session = Depends(get_db)) -> PromptListResponse:
    templates = prompt_repo.get_all_templates(db)
    bindings = prompt_repo.list_bindings(db)

    template_responses = [
        PromptTemplateResponse.from_orm(template)
        for template in templates
    ]

    binding_responses = []
    for binding, account, template in bindings:
        binding_responses.append(
            PromptBindingResponse(
                id=binding.id,
                account_id=account.id,
                account_name=account.name,
                account_model=account.model,
                prompt_template_id=binding.prompt_template_id,
                prompt_key=template.key,
                prompt_name=template.name,
                updated_by=binding.updated_by,
                updated_at=binding.updated_at,
            )
        )

    return PromptListResponse(templates=template_responses, bindings=binding_responses)


@router.put("/{key}", response_model=PromptTemplateResponse, response_model_exclude_none=True)
def update_prompt_template(
    key: str,
    payload: PromptTemplateUpdateRequest,
    db: Session = Depends(get_db),
) -> PromptTemplateResponse:
    try:
        template = prompt_repo.update_template(
            db,
            key=key,
            template_text=payload.template_text,
            description=payload.description,
            updated_by=payload.updated_by,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return PromptTemplateResponse.from_orm(template)


@router.post(
    "/{key}/restore",
    response_model=PromptTemplateResponse,
    response_model_exclude_none=True,
)
def restore_prompt_template(
    key: str,
    payload: PromptTemplateRestoreRequest,
    db: Session = Depends(get_db),
) -> PromptTemplateResponse:
    try:
        template = prompt_repo.restore_template(
            db,
            key=key,
            updated_by=payload.updated_by,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return PromptTemplateResponse.from_orm(template)


@router.post(
    "/bindings",
    response_model=PromptBindingResponse,
    response_model_exclude_none=True,
)
def upsert_prompt_binding(
    payload: PromptBindingUpsertRequest,
    db: Session = Depends(get_db),
) -> PromptBindingResponse:
    if not payload.account_id:
        raise HTTPException(status_code=400, detail="accountId is required")
    if not payload.prompt_template_id:
        raise HTTPException(status_code=400, detail="promptTemplateId is required")

    account = db.get(Account, payload.account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    template = db.get(PromptTemplate, payload.prompt_template_id)
    if not template:
        raise HTTPException(status_code=404, detail="Prompt template not found")

    try:
        binding = prompt_repo.upsert_binding(
            db,
            account_id=payload.account_id,
            prompt_template_id=payload.prompt_template_id,
            updated_by=payload.updated_by,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return PromptBindingResponse(
        id=binding.id,
        account_id=account.id,
        account_name=account.name,
        account_model=account.model,
        prompt_template_id=binding.prompt_template_id,
        prompt_key=template.key,
        prompt_name=template.name,
        updated_by=binding.updated_by,
        updated_at=binding.updated_at,
    )


@router.delete("/bindings/{binding_id}")
def delete_prompt_binding(binding_id: int, db: Session = Depends(get_db)) -> dict:
    try:
        prompt_repo.delete_binding(db, binding_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"message": "Binding deleted"}


@router.post("/preview")
def preview_prompt(
    payload: dict,
    db: Session = Depends(get_db),
) -> dict:
    """
    Preview filled prompt for selected accounts and symbols.

    Payload:
    {
        "promptTemplateKey": "pro",
        "accountIds": [1, 2],
        "symbols": ["BTC", "ETH"]
    }

    Returns:
    {
        "previews": [
            {
                "accountId": 1,
                "accountName": "Trader-A",
                "symbol": "BTC",
                "filledPrompt": "..."
            },
            ...
        ]
    }
    """
    from services.ai_decision_service import (
        _get_portfolio_data,
        _build_prompt_context,
        SafeDict,
    )
    from services.market_data import get_last_price
    from services.news_feed import fetch_latest_news
    from services.sampling_pool import sampling_pool
    from database.models import Account
    import logging

    logger = logging.getLogger(__name__)

    prompt_key = payload.get("promptTemplateKey", "default")
    account_ids = payload.get("accountIds", [])
    symbols = payload.get("symbols", [])

    if not account_ids:
        raise HTTPException(status_code=400, detail="At least one account must be selected")

    # Get template
    template = prompt_repo.get_template_by_key(db, prompt_key)
    if not template:
        raise HTTPException(status_code=404, detail=f"Prompt template '{prompt_key}' not found")

    # Get news
    try:
        news_summary = fetch_latest_news()
        news_section = news_summary if news_summary else "No recent CoinJournal news available."
    except Exception as err:
        logger.warning(f"Failed to fetch news: {err}")
        news_section = "No recent CoinJournal news available."

    # Get current prices
    prices = {}
    supported_symbols = ["BTC", "ETH", "SOL", "DOGE", "XRP", "BNB"]
    for sym in supported_symbols:
        try:
            price = get_last_price(sym, "CRYPTO")
            prices[sym] = price
        except Exception as err:
            logger.warning(f"Failed to get price for {sym}: {err}")
            prices[sym] = 0.0

    # Import multi-symbol sampling data builder
    from services.ai_decision_service import _build_multi_symbol_sampling_data

    previews = []

    for account_id in account_ids:
        account = db.get(Account, account_id)
        if not account:
            logger.warning(f"Account {account_id} not found, skipping")
            continue

        portfolio = _get_portfolio_data(db, account)

        # Build context with multi-symbol sampling data if symbols are specified
        if symbols:
            # Build multi-symbol sampling data
            sampling_data = _build_multi_symbol_sampling_data(symbols, sampling_pool)
            context = _build_prompt_context(
                account, portfolio, prices, news_section, None, None
            )
            # Override sampling_data with multi-symbol version
            context["sampling_data"] = sampling_data
        else:
            # No symbol specified, no sampling data
            context = _build_prompt_context(
                account, portfolio, prices, news_section, None, None
            )

        try:
            filled_prompt = template.template_text.format_map(SafeDict(context))
        except Exception as err:
            logger.error(f"Failed to fill prompt for {account.name}: {err}")
            filled_prompt = f"Error filling prompt: {err}"

        previews.append({
            "accountId": account.id,
            "accountName": account.name,
            "symbols": symbols if symbols else [],
            "filledPrompt": filled_prompt,
        })

    return {"previews": previews}
