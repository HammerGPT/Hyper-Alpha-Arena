from __future__ import annotations

from typing import Dict, List, Optional

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
        SUPPORTED_SYMBOLS,
    )
    from services.market_data import get_last_price
    from services.news_feed import fetch_latest_news
    from services.sampling_pool import sampling_pool
    from database.models import Account
    import logging
    from services.hyperliquid_symbol_service import (
        get_selected_symbols as get_hyperliquid_selected_symbols,
        get_available_symbol_map as get_hyperliquid_symbol_map,
    )

    logger = logging.getLogger(__name__)

    prompt_key = payload.get("promptTemplateKey", "default")
    account_ids = payload.get("accountIds", [])

    raw_symbols = [str(sym).upper() for sym in payload.get("symbols", []) if sym]
    requested_symbols: List[str] = []
    seen_requested = set()
    for symbol in raw_symbols:
        if symbol and symbol not in seen_requested:
            seen_requested.add(symbol)
            requested_symbols.append(symbol)

    base_symbol_order = list(SUPPORTED_SYMBOLS.keys())
    hyper_watchlist = get_hyperliquid_selected_symbols()
    hyper_symbol_map = get_hyperliquid_symbol_map()

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

    # Import multi-symbol sampling data builder
    from services.ai_decision_service import _build_multi_symbol_sampling_data

    previews = []

    for account_id in account_ids:
        account = db.get(Account, account_id)
        if not account:
            logger.warning(f"Account {account_id} not found, skipping")
            continue

        # Check if account uses Hyperliquid
        hyperliquid_environment = getattr(account, "hyperliquid_environment", None)

        hyperliquid_state = None

        if hyperliquid_environment in ["testnet", "mainnet"]:
            # Get Hyperliquid real-time data
            try:
                from services.hyperliquid_environment import get_hyperliquid_client

                client = get_hyperliquid_client(db, account_id)
                account_state = client.get_account_state(db)
                positions = client.get_positions(db)

                # Build portfolio with Hyperliquid data
                portfolio = {
                    'cash': account_state['available_balance'],
                    'frozen_cash': account_state.get('used_margin', 0),
                    'positions': {},
                    'total_assets': account_state['total_equity']
                }

                for pos in positions:
                    symbol = pos['coin']
                    portfolio['positions'][symbol] = {
                        'quantity': pos['szi'],
                        'avg_cost': pos['entry_px'],
                        'current_value': pos['position_value'],
                        'unrealized_pnl': pos['unrealized_pnl'],
                        'leverage': pos['leverage']
                    }

                # Build Hyperliquid state for prompt context
                hyperliquid_state = {
                    'total_equity': account_state['total_equity'],
                    'available_balance': account_state['available_balance'],
                    'used_margin': account_state.get('used_margin', 0),
                    'margin_usage_percent': account_state['margin_usage_percent'],
                    'maintenance_margin': account_state.get('maintenance_margin', 0),
                    'positions': positions
                }

                logger.info(
                    f"Preview: Using Hyperliquid {hyperliquid_environment} data for {account.name}: "
                    f"equity=${account_state['total_equity']:.2f}"
                )

            except Exception as hl_err:
                logger.error(f"Failed to get Hyperliquid data for {account.name}: {hl_err}")
                raise HTTPException(
                    status_code=502,
                    detail=f"Failed to fetch Hyperliquid {hyperliquid_environment} data: {hl_err}",
                )
        else:
            # Paper trading mode
            portfolio = _get_portfolio_data(db, account)

        # Determine active symbols + metadata for this account
        if hyperliquid_environment in ["testnet", "mainnet"]:
            active_symbols = requested_symbols or hyper_watchlist or base_symbol_order
            symbol_metadata_map = {}
            for sym in active_symbols:
                entry = dict(hyper_symbol_map.get(sym, {}))
                entry.setdefault("name", sym)
                symbol_metadata_map[sym] = entry
        else:
            active_symbols = requested_symbols or base_symbol_order
            symbol_metadata_map = {sym: SUPPORTED_SYMBOLS.get(sym, sym) for sym in active_symbols}

        if not active_symbols:
            active_symbols = base_symbol_order

        prices: Dict[str, float] = {}
        for sym in active_symbols:
            try:
                prices[sym] = get_last_price(sym, "CRYPTO")
            except Exception as err:
                logger.warning(f"Failed to get price for {sym}: {err}")
                prices[sym] = 0.0

        sampling_data = _build_multi_symbol_sampling_data(active_symbols, sampling_pool)
        context = _build_prompt_context(
            account,
            portfolio,
            prices,
            news_section,
            None,
            None,
            hyperliquid_state,
            symbol_metadata=symbol_metadata_map,
            symbol_order=active_symbols,
        )
        context["sampling_data"] = sampling_data

        try:
            filled_prompt = template.template_text.format_map(SafeDict(context))
        except Exception as err:
            logger.error(f"Failed to fill prompt for {account.name}: {err}")
            filled_prompt = f"Error filling prompt: {err}"

        previews.append({
            "accountId": account.id,
            "accountName": account.name,
            "symbols": requested_symbols if requested_symbols else [],
            "filledPrompt": filled_prompt,
        })

    return {"previews": previews}
