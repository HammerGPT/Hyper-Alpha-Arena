use axum::{
    Json,
    extract::{Path, Query, State},
};
use chrono::{DateTime, NaiveDateTime, Utc};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use sqlx::Row;
use std::collections::HashMap;

use crate::{error::AppError, state::AppState};

#[derive(Deserialize)]
pub struct ArenaTradesQuery {
    #[serde(default = "default_trade_limit")]
    limit: i64,
    account_id: Option<i32>,
    trading_mode: Option<String>,
    wallet_address: Option<String>,
    symbol: Option<String>,
    exchange: Option<String>,
}

#[derive(Serialize, Clone)]
pub struct ArenaAccountMeta {
    account_id: i32,
    name: String,
    model: Option<String>,
}

#[derive(Serialize, Clone)]
pub struct ArenaRelatedOrder {
    #[serde(rename = "type")]
    kind: String,
    price: f64,
    quantity: f64,
    notional: f64,
    commission: f64,
    trade_time: Option<String>,
}

#[derive(Serialize, Clone)]
pub struct ArenaTrade {
    trade_id: i32,
    order_id: Option<i32>,
    order_no: Option<String>,
    account_id: i32,
    account_name: String,
    model: Option<String>,
    side: String,
    direction: String,
    symbol: String,
    market: String,
    price: f64,
    quantity: f64,
    notional: f64,
    commission: f64,
    trade_time: Option<String>,
    wallet_address: Option<String>,
    signal_trigger_id: Option<i32>,
    prompt_template_id: Option<i32>,
    prompt_template_name: Option<String>,
    decision_source_type: Option<String>,
    related_orders: Option<Vec<ArenaRelatedOrder>>,
    exchange: Option<String>,
}

#[derive(Serialize)]
pub struct ArenaTradesResponse {
    generated_at: String,
    accounts: Vec<ArenaAccountMeta>,
    trades: Vec<ArenaTrade>,
}

#[derive(Deserialize)]
pub struct ArenaPositionsQuery {
    account_id: Option<i32>,
    trading_mode: Option<String>,
}

#[derive(Serialize, Clone)]
pub struct ArenaPositionItem {
    id: i32,
    symbol: String,
    name: String,
    market: String,
    side: String,
    quantity: f64,
    avg_cost: f64,
    current_price: f64,
    notional: f64,
    current_value: f64,
    unrealized_pnl: f64,
    #[serde(skip_serializing_if = "Option::is_none")]
    leverage: Option<i32>,
    #[serde(skip_serializing_if = "Option::is_none")]
    margin_used: Option<f64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    return_on_equity: Option<f64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    percentage: Option<f64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    margin_mode: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    liquidation_px: Option<f64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    max_leverage: Option<i32>,
    #[serde(skip_serializing_if = "Option::is_none")]
    leverage_type: Option<String>,
}

#[derive(Serialize)]
pub struct ArenaPositionsAccount {
    account_id: i32,
    account_name: String,
    model: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    environment: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    exchange: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    wallet_address: Option<String>,
    total_unrealized_pnl: f64,
    available_cash: f64,
    #[serde(skip_serializing_if = "Option::is_none")]
    used_margin: Option<f64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    positions_value: Option<f64>,
    positions: Vec<ArenaPositionItem>,
    total_assets: f64,
    initial_capital: f64,
    #[serde(skip_serializing_if = "Option::is_none")]
    total_return: Option<f64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    margin_usage_percent: Option<f64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    margin_mode: Option<String>,
}

#[derive(Serialize)]
pub struct ArenaPositionsResponse {
    generated_at: String,
    accounts: Vec<ArenaPositionsAccount>,
}

#[derive(Deserialize)]
pub struct ArenaModelChatQuery {
    #[serde(default = "default_model_chat_limit")]
    limit: i64,
    account_id: Option<i32>,
    trading_mode: Option<String>,
    wallet_address: Option<String>,
    before_time: Option<String>,
    after_time: Option<String>,
    operation: Option<String>,
    #[serde(default)]
    include_snapshots: bool,
    symbol: Option<String>,
    ids: Option<String>,
    exchange: Option<String>,
}

#[derive(Serialize)]
pub struct ArenaModelChatResponse {
    generated_at: String,
    entries: Vec<ArenaModelChatEntry>,
}

#[derive(Serialize)]
pub struct ArenaModelChatEntry {
    id: i32,
    account_id: i32,
    account_name: String,
    model: Option<String>,
    operation: String,
    symbol: Option<String>,
    reason: String,
    executed: bool,
    prev_portion: f64,
    target_portion: f64,
    total_balance: f64,
    order_id: Option<i32>,
    decision_time: Option<String>,
    trigger_mode: Option<String>,
    strategy_enabled: Option<bool>,
    last_trigger_at: Option<String>,
    trigger_latency_seconds: Option<f64>,
    wallet_address: Option<String>,
    signal_trigger_id: Option<i32>,
    prompt_template_id: Option<i32>,
    prompt_template_name: Option<String>,
    realized_pnl: Option<f64>,
    has_snapshot: bool,
    exchange: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    prompt_snapshot: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    reasoning_snapshot: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    decision_snapshot: Option<String>,
}

#[derive(Serialize)]
pub struct ModelChatSnapshots {
    id: i32,
    #[serde(skip_serializing_if = "Option::is_none")]
    prompt_snapshot: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    reasoning_snapshot: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    decision_snapshot: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    error: Option<String>,
}

#[derive(Deserialize)]
pub struct PnlStatusQuery {
    trading_mode: Option<String>,
}

#[derive(Serialize)]
pub struct PnlStatusResponse {
    needs_sync: bool,
    unsync_count: i64,
    ai_unsync_count: i64,
    program_unsync_count: i64,
}

#[derive(Deserialize)]
pub struct ArenaAnalyticsQuery {
    account_id: Option<i32>,
}

#[derive(Serialize)]
pub struct ArenaAnalyticsResponse {
    generated_at: String,
    accounts: Vec<Value>,
    summary: Value,
}

pub async fn get_completed_trades(
    State(state): State<AppState>,
    Query(query): Query<ArenaTradesQuery>,
) -> Result<Json<ArenaTradesResponse>, AppError> {
    let limit = validate_trade_limit(query.limit)?;
    let trading_mode = normalize_trading_mode(query.trading_mode.as_deref())?;
    let exchange = normalize_exchange(query.exchange.as_deref())?;

    if query.wallet_address.is_some()
        && !matches!(trading_mode.as_deref(), Some("testnet" | "mainnet"))
    {
        return Ok(Json(empty_arena_trades_response()));
    }

    let response = match trading_mode.as_deref() {
        Some("testnet" | "mainnet") => {
            load_snapshot_trades(
                &state,
                &query,
                limit,
                trading_mode.as_deref().unwrap(),
                exchange,
            )
            .await?
        }
        _ => load_paper_trades(&state, &query, limit).await?,
    };

    Ok(Json(response))
}

pub async fn get_positions_snapshot(
    State(state): State<AppState>,
    Query(query): Query<ArenaPositionsQuery>,
) -> Result<Json<ArenaPositionsResponse>, AppError> {
    let trading_mode = normalize_trading_mode(query.trading_mode.as_deref())?;
    let accounts = load_dashboard_accounts(&state, query.account_id).await?;
    if accounts.is_empty() {
        return Ok(Json(ArenaPositionsResponse {
            generated_at: Utc::now().to_rfc3339(),
            accounts: Vec::new(),
        }));
    }

    let snapshots = match trading_mode.as_deref() {
        Some("testnet" | "mainnet") => {
            load_live_positions_snapshots(&state, &accounts, trading_mode.as_deref().unwrap())
                .await?
        }
        _ => load_paper_positions_snapshots(&state, &accounts).await?,
    };

    Ok(Json(ArenaPositionsResponse {
        generated_at: Utc::now().to_rfc3339(),
        accounts: snapshots,
    }))
}

pub async fn get_model_chat(
    State(state): State<AppState>,
    Query(query): Query<ArenaModelChatQuery>,
) -> Result<Json<ArenaModelChatResponse>, AppError> {
    let ids = parse_ids(query.ids.as_deref());
    let before_time = parse_optional_timestamp(query.before_time.as_deref())?;
    let after_time = parse_optional_timestamp(query.after_time.as_deref())?;
    let trading_mode = normalize_trading_mode(query.trading_mode.as_deref())?;
    let operation = normalize_operation(query.operation.as_deref())?;
    let exchange = normalize_exchange(query.exchange.as_deref())?;

    let rows = sqlx::query(
        r#"
        SELECT
            l.id, l.account_id, l.operation, l.symbol, l.reason, l.executed,
            l.prev_portion::float8 AS prev_portion,
            l.target_portion::float8 AS target_portion,
            l.total_balance::float8 AS total_balance,
            l.order_id, l.decision_time, l.wallet_address, l.signal_trigger_id,
            l.prompt_template_id, l.realized_pnl::float8 AS realized_pnl,
            l.prompt_snapshot, l.reasoning_snapshot, l.decision_snapshot,
            l.exchange,
            a.name AS account_name, a.model AS account_model
        FROM ai_decision_logs l
        JOIN accounts a ON a.id = l.account_id
        WHERE ($1::int4 IS NULL OR l.account_id = $1)
          AND ($2::text IS NULL OR l.wallet_address = $2)
          AND ($3::timestamp IS NULL OR l.decision_time < $3)
          AND ($4::timestamp IS NULL OR l.decision_time >= $4)
          AND ($5::text IS NULL OR l.operation = $5)
          AND ($6::text IS NULL OR l.symbol = $6)
          AND (
                $7::text IS NULL OR
                ($7 = 'paper' AND l.hyperliquid_environment IS NULL) OR
                ($7 != 'paper' AND l.hyperliquid_environment = $7 AND l.hyperliquid_environment IS NOT NULL)
          )
          AND (
                $8::text IS NULL OR
                ($8 = 'hyperliquid' AND (l.exchange = 'hyperliquid' OR l.exchange IS NULL)) OR
                ($8 != 'hyperliquid' AND l.exchange = $8)
          )
          AND ($9::int4[] IS NULL OR l.id = ANY($9))
        ORDER BY l.decision_time DESC
        LIMIT $10
        "#,
    )
    .bind(query.account_id)
    .bind(query.wallet_address.as_deref())
    .bind(before_time)
    .bind(after_time)
    .bind(operation.as_deref())
    .bind(query.symbol.as_deref())
    .bind(trading_mode.as_deref())
    .bind(exchange.as_deref())
    .bind(if ids.is_empty() { None } else { Some(ids.clone()) })
    .bind(query.limit)
    .fetch_all(&state.db)
    .await
    .map_err(|error| AppError::internal(format!("Failed to get model chat: {error}")))?;

    let account_ids = rows
        .iter()
        .filter_map(|row| row.try_get::<i32, _>("account_id").ok())
        .collect::<Vec<_>>();
    let strategy_map = load_strategy_context(&state, &account_ids).await?;
    let prompt_template_ids = rows
        .iter()
        .filter_map(|row| {
            row.try_get::<Option<i32>, _>("prompt_template_id")
                .ok()
                .flatten()
        })
        .collect::<Vec<_>>();
    let prompt_template_names = load_prompt_names(&state, &prompt_template_ids).await?;

    let entries = rows
        .into_iter()
        .map(|row| {
            let account_id = row
                .try_get::<i32, _>("account_id")
                .map_err(read_arena_error)?;
            let decision_time = row
                .try_get::<Option<NaiveDateTime>, _>("decision_time")
                .map_err(read_arena_error)?;
            let strategy = strategy_map.get(&account_id);
            let last_trigger_at = strategy.and_then(|ctx| ctx.last_trigger_at.map(format_utc_iso));
            let trigger_latency_seconds =
                match (decision_time, strategy.and_then(|ctx| ctx.last_trigger_at)) {
                    (Some(decision_time), Some(last_trigger_at)) => Some(
                        (decision_time.and_utc().timestamp_millis()
                            - last_trigger_at.and_utc().timestamp_millis())
                        .unsigned_abs() as f64
                            / 1000.0,
                    ),
                    _ => None,
                };
            let prompt_template_id = row
                .try_get::<Option<i32>, _>("prompt_template_id")
                .map_err(read_arena_error)?;
            Ok(ArenaModelChatEntry {
                id: row.try_get("id").map_err(read_arena_error)?,
                account_id,
                account_name: row.try_get("account_name").map_err(read_arena_error)?,
                model: row.try_get("account_model").map_err(read_arena_error)?,
                operation: row.try_get("operation").map_err(read_arena_error)?,
                symbol: row.try_get("symbol").map_err(read_arena_error)?,
                reason: row.try_get("reason").map_err(read_arena_error)?,
                executed: row
                    .try_get::<String, _>("executed")
                    .map_err(read_arena_error)?
                    == "true",
                prev_portion: row.try_get("prev_portion").map_err(read_arena_error)?,
                target_portion: row.try_get("target_portion").map_err(read_arena_error)?,
                total_balance: row.try_get("total_balance").map_err(read_arena_error)?,
                order_id: row.try_get("order_id").map_err(read_arena_error)?,
                decision_time: decision_time.map(format_utc_iso),
                trigger_mode: strategy.map(|_| "unified".to_owned()),
                strategy_enabled: strategy.map(|ctx| ctx.enabled),
                last_trigger_at,
                trigger_latency_seconds,
                wallet_address: row.try_get("wallet_address").map_err(read_arena_error)?,
                signal_trigger_id: row.try_get("signal_trigger_id").map_err(read_arena_error)?,
                prompt_template_id,
                prompt_template_name: prompt_template_id
                    .and_then(|id| prompt_template_names.get(&id).cloned()),
                realized_pnl: row.try_get("realized_pnl").map_err(read_arena_error)?,
                has_snapshot: row
                    .try_get::<Option<String>, _>("prompt_snapshot")
                    .map_err(read_arena_error)?
                    .is_some(),
                exchange: row
                    .try_get::<Option<String>, _>("exchange")
                    .map_err(read_arena_error)?
                    .unwrap_or_else(|| "hyperliquid".to_owned()),
                prompt_snapshot: if query.include_snapshots {
                    row.try_get("prompt_snapshot").map_err(read_arena_error)?
                } else {
                    None
                },
                reasoning_snapshot: if query.include_snapshots {
                    row.try_get("reasoning_snapshot")
                        .map_err(read_arena_error)?
                } else {
                    None
                },
                decision_snapshot: if query.include_snapshots {
                    row.try_get("decision_snapshot").map_err(read_arena_error)?
                } else {
                    None
                },
            })
        })
        .collect::<Result<Vec<_>, AppError>>()?;

    Ok(Json(ArenaModelChatResponse {
        generated_at: Utc::now().to_rfc3339(),
        entries,
    }))
}

pub async fn get_model_chat_snapshots(
    State(state): State<AppState>,
    Path(decision_id): Path<i32>,
) -> Result<Json<ModelChatSnapshots>, AppError> {
    let row = sqlx::query(
        r#"
        SELECT id, prompt_snapshot, reasoning_snapshot, decision_snapshot
        FROM ai_decision_logs
        WHERE id = $1
        LIMIT 1
        "#,
    )
    .bind(decision_id)
    .fetch_optional(&state.db)
    .await
    .map_err(|error| AppError::internal(format!("Failed to get model chat snapshots: {error}")))?;

    let Some(row) = row else {
        return Ok(Json(ModelChatSnapshots {
            id: decision_id,
            prompt_snapshot: None,
            reasoning_snapshot: None,
            decision_snapshot: None,
            error: Some("Decision not found".to_owned()),
        }));
    };

    Ok(Json(ModelChatSnapshots {
        id: row.try_get("id").map_err(read_arena_error)?,
        prompt_snapshot: row.try_get("prompt_snapshot").map_err(read_arena_error)?,
        reasoning_snapshot: row
            .try_get("reasoning_snapshot")
            .map_err(read_arena_error)?,
        decision_snapshot: row.try_get("decision_snapshot").map_err(read_arena_error)?,
        error: None,
    }))
}

pub async fn check_pnl_sync_status(
    State(state): State<AppState>,
    Query(query): Query<PnlStatusQuery>,
) -> Result<Json<PnlStatusResponse>, AppError> {
    let trading_mode = normalize_trading_mode(query.trading_mode.as_deref())?;

    let ai_unsync_count = sqlx::query_scalar::<_, i64>(
        r#"
        SELECT COUNT(*)::bigint
        FROM ai_decision_logs
        WHERE operation = ANY($1)
          AND executed = 'true'
          AND pnl_updated_at IS NULL
          AND (
                hyperliquid_order_id IS NOT NULL OR
                tp_order_id IS NOT NULL OR
                sl_order_id IS NOT NULL
          )
          AND (
                $2::text IS NULL OR
                ($2 = 'paper' AND hyperliquid_environment IS NULL) OR
                ($2 != 'paper' AND hyperliquid_environment = $2)
          )
        "#,
    )
    .bind(vec!["buy", "sell", "close"])
    .bind(trading_mode.as_deref())
    .fetch_one(&state.db)
    .await
    .map_err(|error| AppError::internal(format!("Failed to check AI PnL sync status: {error}")))?;

    let program_unsync_count = sqlx::query_scalar::<_, i64>(
        r#"
        SELECT COUNT(*)::bigint
        FROM program_execution_logs
        WHERE success = true
          AND decision_action = ANY($1)
          AND pnl_updated_at IS NULL
          AND (
                hyperliquid_order_id IS NOT NULL OR
                tp_order_id IS NOT NULL OR
                sl_order_id IS NOT NULL
          )
          AND (
                $2::text IS NULL OR
                ($2 = 'paper' AND environment IS NULL) OR
                ($2 != 'paper' AND environment = $2)
          )
        "#,
    )
    .bind(vec!["buy", "sell", "close"])
    .bind(trading_mode.as_deref())
    .fetch_one(&state.db)
    .await
    .map_err(|error| {
        AppError::internal(format!("Failed to check program PnL sync status: {error}"))
    })?;

    Ok(Json(PnlStatusResponse {
        needs_sync: ai_unsync_count + program_unsync_count > 0,
        unsync_count: ai_unsync_count + program_unsync_count,
        ai_unsync_count,
        program_unsync_count,
    }))
}

pub async fn get_aggregated_analytics(
    State(state): State<AppState>,
    Query(query): Query<ArenaAnalyticsQuery>,
) -> Result<Json<ArenaAnalyticsResponse>, AppError> {
    let accounts = sqlx::query(
        r#"
        SELECT id, name, model,
               initial_capital::float8 AS initial_capital,
               current_cash::float8 AS current_cash
        FROM accounts
        WHERE account_type = 'AI'
          AND is_deleted IS DISTINCT FROM true
          AND ($1::int4 IS NULL OR id = $1)
        ORDER BY id
        "#,
    )
    .bind(query.account_id)
    .fetch_all(&state.db)
    .await
    .map_err(|error| AppError::internal(format!("Failed to get arena analytics: {error}")))?;

    if accounts.is_empty() {
        return Ok(Json(ArenaAnalyticsResponse {
            generated_at: Utc::now().to_rfc3339(),
            accounts: Vec::new(),
            summary: serde_json::json!({
                "total_assets": 0.0,
                "total_pnl": 0.0,
                "total_return_pct": null,
                "total_fees": 0.0,
                "total_volume": 0.0,
                "average_sharpe_ratio": null
            }),
        }));
    }

    let mut account_items = Vec::new();
    let mut total_assets_all = 0.0;
    let mut total_initial = 0.0;
    let mut total_fees_all = 0.0;
    let mut total_volume_all = 0.0;
    let mut sharpe_values = Vec::new();

    for account in accounts {
        let stats = aggregate_account_stats(&state, &account).await?;
        total_assets_all += stats["total_assets"].as_f64().unwrap_or(0.0);
        total_initial += stats["initial_capital"].as_f64().unwrap_or(0.0);
        total_fees_all += stats["total_fees"].as_f64().unwrap_or(0.0);
        total_volume_all += stats["total_volume"].as_f64().unwrap_or(0.0);
        if let Some(sharpe) = stats["sharpe_ratio"].as_f64() {
            sharpe_values.push(sharpe);
        }
        account_items.push(stats);
    }

    account_items.sort_by(|a, b| {
        b["total_return_pct"]
            .as_f64()
            .unwrap_or(f64::NEG_INFINITY)
            .partial_cmp(&a["total_return_pct"].as_f64().unwrap_or(f64::NEG_INFINITY))
            .unwrap_or(std::cmp::Ordering::Equal)
    });

    let total_pnl_all = total_assets_all - total_initial;
    let total_return_pct = if total_initial != 0.0 {
        Some(total_pnl_all / total_initial)
    } else {
        None
    };
    let average_sharpe = if sharpe_values.is_empty() {
        None
    } else {
        Some(sharpe_values.iter().sum::<f64>() / sharpe_values.len() as f64)
    };

    Ok(Json(ArenaAnalyticsResponse {
        generated_at: Utc::now().to_rfc3339(),
        accounts: account_items,
        summary: serde_json::json!({
            "total_assets": total_assets_all,
            "total_pnl": total_pnl_all,
            "total_return_pct": total_return_pct,
            "total_fees": total_fees_all,
            "total_volume": total_volume_all,
            "average_sharpe_ratio": average_sharpe
        }),
    }))
}

#[derive(Clone)]
struct StrategyContext {
    enabled: bool,
    last_trigger_at: Option<NaiveDateTime>,
}

#[derive(Clone)]
struct DecisionTradeLink {
    signal_trigger_id: Option<i32>,
    prompt_template_id: Option<i32>,
    decision_source_type: String,
    exchange: String,
}

#[derive(Clone)]
struct ProgramTradeLink {
    signal_pool_id: Option<i32>,
    program_id: Option<i32>,
    program_name: Option<String>,
    exchange: String,
}

#[derive(Clone)]
struct DashboardAccount {
    account_id: i32,
    account_name: String,
    model: Option<String>,
    initial_capital: f64,
    current_cash: f64,
}

async fn load_snapshot_trades(
    state: &AppState,
    query: &ArenaTradesQuery,
    limit: i64,
    trading_mode: &str,
    exchange: Option<String>,
) -> Result<ArenaTradesResponse, AppError> {
    let rows = sqlx::query(
        r#"
        SELECT
            id,
            account_id,
            wallet_address,
            symbol,
            side,
            quantity::float8 AS quantity,
            price::float8 AS price,
            order_id,
            trade_value::float8 AS trade_value,
            fee::float8 AS fee,
            trade_time
        FROM hyperliquid_trades
        WHERE environment = $1
          AND ($2::int4 IS NULL OR account_id = $2)
          AND ($3::text IS NULL OR wallet_address = $3)
          AND ($4::text IS NULL OR symbol = $4)
        ORDER BY trade_time DESC
        LIMIT $5
        "#,
    )
    .bind(trading_mode)
    .bind(query.account_id)
    .bind(query.wallet_address.as_deref())
    .bind(query.symbol.as_deref())
    .bind(limit)
    .fetch_all(&state.snapshot_db)
    .await
    .map_err(|error| {
        AppError::internal(format!("Failed to load arena snapshot trades: {error}"))
    })?;

    if rows.is_empty() {
        return Ok(empty_arena_trades_response());
    }

    let account_ids = rows
        .iter()
        .filter_map(|row| row.try_get::<i32, _>("account_id").ok())
        .collect::<Vec<_>>();
    let account_rows = sqlx::query(
        r#"
        SELECT id, name, model
        FROM accounts
        WHERE id = ANY($1)
          AND COALESCE(is_deleted, false) = false
        "#,
    )
    .bind(&account_ids)
    .fetch_all(&state.db)
    .await
    .map_err(|error| AppError::internal(format!("Failed to load arena accounts: {error}")))?;

    let account_map = account_rows
        .into_iter()
        .map(|row| {
            let meta = ArenaAccountMeta {
                account_id: row.try_get("id").map_err(read_arena_error)?,
                name: row.try_get("name").map_err(read_arena_error)?,
                model: row.try_get("model").map_err(read_arena_error)?,
            };
            Ok((meta.account_id, meta))
        })
        .collect::<Result<HashMap<_, _>, AppError>>()?;

    let order_ids = rows
        .iter()
        .filter_map(|row| row.try_get::<Option<String>, _>("order_id").ok().flatten())
        .collect::<Vec<_>>();
    let order_ids_ref = if order_ids.is_empty() {
        None
    } else {
        Some(&order_ids)
    };

    let mut decision_by_main_order = HashMap::<String, DecisionTradeLink>::new();
    let mut sl_to_main = HashMap::<String, String>::new();
    let mut tp_to_main = HashMap::<String, String>::new();
    let mut prompt_template_ids = Vec::new();
    let mut program_ids = Vec::new();

    if let Some(order_ids) = order_ids_ref {
        let decision_rows = sqlx::query(
            r#"
            SELECT
                hyperliquid_order_id,
                sl_order_id,
                tp_order_id,
                signal_trigger_id,
                prompt_template_id,
                decision_source_type,
                exchange
            FROM ai_decision_logs
            WHERE hyperliquid_order_id = ANY($1)
               OR sl_order_id = ANY($1)
               OR tp_order_id = ANY($1)
            "#,
        )
        .bind(order_ids)
        .fetch_all(&state.db)
        .await
        .map_err(|error| {
            AppError::internal(format!("Failed to load arena decision links: {error}"))
        })?;

        for row in decision_rows {
            let main_order_id = row
                .try_get::<Option<String>, _>("hyperliquid_order_id")
                .map_err(read_arena_error)?;
            let sl_order_id = row
                .try_get::<Option<String>, _>("sl_order_id")
                .map_err(read_arena_error)?;
            let tp_order_id = row
                .try_get::<Option<String>, _>("tp_order_id")
                .map_err(read_arena_error)?;
            let prompt_template_id = row
                .try_get::<Option<i32>, _>("prompt_template_id")
                .map_err(read_arena_error)?;
            let decision_source_type = row
                .try_get::<Option<String>, _>("decision_source_type")
                .map_err(read_arena_error)?
                .unwrap_or_else(|| "prompt_template".to_owned());

            if let Some(main_order_id) = main_order_id {
                if let Some(prompt_template_id) = prompt_template_id {
                    if decision_source_type == "program" {
                        program_ids.push(prompt_template_id);
                    } else {
                        prompt_template_ids.push(prompt_template_id);
                    }
                }
                decision_by_main_order.insert(
                    main_order_id.clone(),
                    DecisionTradeLink {
                        signal_trigger_id: row
                            .try_get("signal_trigger_id")
                            .map_err(read_arena_error)?,
                        prompt_template_id,
                        decision_source_type,
                        exchange: row
                            .try_get::<Option<String>, _>("exchange")
                            .map_err(read_arena_error)?
                            .unwrap_or_else(|| "hyperliquid".to_owned()),
                    },
                );
                if let Some(sl_order_id) = sl_order_id {
                    sl_to_main.insert(sl_order_id, main_order_id.clone());
                }
                if let Some(tp_order_id) = tp_order_id {
                    tp_to_main.insert(tp_order_id, main_order_id);
                }
            }
        }
    }

    let prompt_name_map = load_prompt_names(state, &prompt_template_ids).await?;
    let mut program_name_map = load_program_names(state, &program_ids).await?;

    let mut program_log_by_main_order = HashMap::<String, ProgramTradeLink>::new();
    let mut program_sl_to_main = HashMap::<String, String>::new();
    let mut program_tp_to_main = HashMap::<String, String>::new();

    if let Some(order_ids) = order_ids_ref {
        let program_rows = sqlx::query(
            r#"
            SELECT
                hyperliquid_order_id,
                sl_order_id,
                tp_order_id,
                program_id,
                program_name,
                signal_pool_id,
                exchange
            FROM program_execution_logs
            WHERE hyperliquid_order_id = ANY($1)
               OR sl_order_id = ANY($1)
               OR tp_order_id = ANY($1)
            "#,
        )
        .bind(order_ids)
        .fetch_all(&state.db)
        .await
        .map_err(|error| {
            AppError::internal(format!("Failed to load arena program links: {error}"))
        })?;

        let mut extra_program_ids = Vec::new();
        for row in &program_rows {
            if let Some(program_id) = row
                .try_get::<Option<i32>, _>("program_id")
                .map_err(read_arena_error)?
            {
                extra_program_ids.push(program_id);
            }
        }
        for (id, name) in load_program_names(state, &extra_program_ids).await? {
            program_name_map.insert(id, name);
        }

        for row in program_rows {
            let main_order_id = row
                .try_get::<Option<String>, _>("hyperliquid_order_id")
                .map_err(read_arena_error)?;
            let sl_order_id = row
                .try_get::<Option<String>, _>("sl_order_id")
                .map_err(read_arena_error)?;
            let tp_order_id = row
                .try_get::<Option<String>, _>("tp_order_id")
                .map_err(read_arena_error)?;
            let program_id = row
                .try_get::<Option<i32>, _>("program_id")
                .map_err(read_arena_error)?;
            let program_name = match program_id {
                Some(program_id) => program_name_map.get(&program_id).cloned().or_else(|| {
                    row.try_get::<Option<String>, _>("program_name")
                        .ok()
                        .flatten()
                }),
                None => row
                    .try_get::<Option<String>, _>("program_name")
                    .map_err(read_arena_error)?,
            };

            if let Some(main_order_id) = main_order_id {
                program_log_by_main_order.insert(
                    main_order_id.clone(),
                    ProgramTradeLink {
                        signal_pool_id: row.try_get("signal_pool_id").map_err(read_arena_error)?,
                        program_id,
                        program_name,
                        exchange: row
                            .try_get::<Option<String>, _>("exchange")
                            .map_err(read_arena_error)?
                            .unwrap_or_else(|| "hyperliquid".to_owned()),
                    },
                );
                if let Some(sl_order_id) = sl_order_id {
                    program_sl_to_main.insert(sl_order_id, main_order_id.clone());
                }
                if let Some(tp_order_id) = tp_order_id {
                    program_tp_to_main.insert(tp_order_id, main_order_id);
                }
            }
        }
    }

    let mut main_trades = HashMap::<String, ArenaTrade>::new();
    let mut sl_trades = HashMap::<String, ArenaRelatedOrder>::new();
    let mut tp_trades = HashMap::<String, ArenaRelatedOrder>::new();
    let mut other_trades = Vec::<ArenaTrade>::new();
    let mut accounts_meta = HashMap::<i32, ArenaAccountMeta>::new();

    for row in rows {
        let account_id = row
            .try_get::<i32, _>("account_id")
            .map_err(read_arena_error)?;
        let Some(account) = account_map.get(&account_id) else {
            continue;
        };
        let order_no = row
            .try_get::<Option<String>, _>("order_id")
            .map_err(read_arena_error)?;
        let side = row
            .try_get::<String, _>("side")
            .map_err(read_arena_error)?
            .to_uppercase();
        let trade_time = row
            .try_get::<Option<NaiveDateTime>, _>("trade_time")
            .map_err(read_arena_error)?
            .map(format_utc_iso);
        let price = row.try_get::<f64, _>("price").map_err(read_arena_error)?;
        let quantity = row
            .try_get::<f64, _>("quantity")
            .map_err(read_arena_error)?;
        let base_trade = ArenaTrade {
            trade_id: row.try_get("id").map_err(read_arena_error)?,
            order_id: None,
            order_no: order_no.clone(),
            account_id,
            account_name: account.name.clone(),
            model: account.model.clone(),
            side: side.clone(),
            direction: if side == "BUY" {
                "LONG".to_owned()
            } else {
                "SHORT".to_owned()
            },
            symbol: row.try_get("symbol").map_err(read_arena_error)?,
            market: "HYPERLIQUID_PERP".to_owned(),
            price,
            quantity,
            notional: row
                .try_get::<f64, _>("trade_value")
                .map_err(read_arena_error)?,
            commission: row.try_get::<f64, _>("fee").map_err(read_arena_error)?,
            trade_time,
            wallet_address: row.try_get("wallet_address").map_err(read_arena_error)?,
            signal_trigger_id: None,
            prompt_template_id: None,
            prompt_template_name: None,
            decision_source_type: None,
            related_orders: Some(Vec::new()),
            exchange: Some("hyperliquid".to_owned()),
        };

        accounts_meta
            .entry(account_id)
            .or_insert_with(|| account.clone());

        let Some(order_no) = order_no else {
            other_trades.push(base_trade);
            continue;
        };

        if let Some(decision) = decision_by_main_order.get(&order_no) {
            let mut trade = base_trade;
            trade.signal_trigger_id = decision.signal_trigger_id;
            trade.prompt_template_id = decision.prompt_template_id;
            trade.decision_source_type = Some(decision.decision_source_type.clone());
            trade.exchange = Some(decision.exchange.clone());
            trade.prompt_template_name = decision.prompt_template_id.and_then(|template_id| {
                if decision.decision_source_type == "program" {
                    program_name_map.get(&template_id).cloned()
                } else {
                    prompt_name_map.get(&template_id).cloned()
                }
            });
            main_trades.insert(order_no, trade);
        } else if sl_to_main.contains_key(&order_no) {
            sl_trades.insert(order_no, build_related_order(&base_trade, "sl"));
        } else if tp_to_main.contains_key(&order_no) {
            tp_trades.insert(order_no, build_related_order(&base_trade, "tp"));
        } else if let Some(program_log) = program_log_by_main_order.get(&order_no) {
            let mut trade = base_trade;
            trade.signal_trigger_id = program_log.signal_pool_id;
            trade.prompt_template_id = program_log.program_id;
            trade.prompt_template_name = program_log.program_name.clone();
            trade.decision_source_type = Some("program".to_owned());
            trade.exchange = Some(program_log.exchange.clone());
            main_trades.insert(order_no, trade);
        } else if program_sl_to_main.contains_key(&order_no) {
            sl_trades.insert(order_no, build_related_order(&base_trade, "sl"));
        } else if program_tp_to_main.contains_key(&order_no) {
            tp_trades.insert(order_no, build_related_order(&base_trade, "tp"));
        } else {
            other_trades.push(base_trade);
        }
    }

    attach_related_orders(
        &mut main_trades,
        &sl_trades,
        &sl_to_main,
        &program_sl_to_main,
    );
    attach_related_orders(
        &mut main_trades,
        &tp_trades,
        &tp_to_main,
        &program_tp_to_main,
    );

    let mut trades = main_trades.into_values().collect::<Vec<_>>();
    trades.extend(other_trades);
    trades.sort_by(|left, right| right.trade_time.cmp(&left.trade_time));

    if let Some(exchange) = exchange.as_deref() {
        trades.retain(|trade| match exchange {
            "hyperliquid" => trade.exchange.as_deref().unwrap_or("hyperliquid") == "hyperliquid",
            _ => trade.exchange.as_deref() == Some(exchange),
        });
    }

    let mut accounts = accounts_meta.into_values().collect::<Vec<_>>();
    accounts.sort_by_key(|account| account.account_id);

    Ok(ArenaTradesResponse {
        generated_at: Utc::now().to_rfc3339(),
        accounts,
        trades,
    })
}

async fn load_dashboard_accounts(
    state: &AppState,
    account_id: Option<i32>,
) -> Result<Vec<DashboardAccount>, AppError> {
    let rows = sqlx::query(
        r#"
        SELECT
            id,
            name,
            model,
            initial_capital::float8 AS initial_capital,
            current_cash::float8 AS current_cash
        FROM accounts
        WHERE account_type = 'AI'
          AND is_active = 'true'
          AND COALESCE(show_on_dashboard, true) = true
          AND COALESCE(is_deleted, false) = false
          AND ($1::int4 IS NULL OR id = $1)
        ORDER BY id
        "#,
    )
    .bind(account_id)
    .fetch_all(&state.db)
    .await
    .map_err(|error| {
        AppError::internal(format!("Failed to load arena position accounts: {error}"))
    })?;

    rows.into_iter()
        .map(|row| {
            Ok(DashboardAccount {
                account_id: row.try_get("id").map_err(read_arena_error)?,
                account_name: row.try_get("name").map_err(read_arena_error)?,
                model: row.try_get("model").map_err(read_arena_error)?,
                initial_capital: row.try_get("initial_capital").map_err(read_arena_error)?,
                current_cash: row.try_get("current_cash").map_err(read_arena_error)?,
            })
        })
        .collect()
}

async fn load_paper_positions_snapshots(
    state: &AppState,
    accounts: &[DashboardAccount],
) -> Result<Vec<ArenaPositionsAccount>, AppError> {
    let mut snapshots = Vec::with_capacity(accounts.len());

    for account in accounts {
        let rows = sqlx::query(
            r#"
            SELECT
                id,
                symbol,
                name,
                market,
                quantity::float8 AS quantity,
                avg_cost::float8 AS avg_cost
            FROM positions
            WHERE account_id = $1
              AND quantity != 0
            ORDER BY symbol ASC
            "#,
        )
        .bind(account.account_id)
        .fetch_all(&state.db)
        .await
        .map_err(|error| AppError::internal(format!("Failed to load paper positions: {error}")))?;

        let mut positions = Vec::with_capacity(rows.len());
        let mut total_unrealized_pnl = 0.0;
        let mut positions_value = 0.0;

        for row in rows {
            let symbol = row
                .try_get::<String, _>("symbol")
                .map_err(read_arena_error)?;
            let market = row
                .try_get::<String, _>("market")
                .map_err(read_arena_error)?;
            let raw_quantity = row
                .try_get::<f64, _>("quantity")
                .map_err(read_arena_error)?;
            let avg_cost = row
                .try_get::<f64, _>("avg_cost")
                .map_err(read_arena_error)?;
            let current_price = latest_kline_price(state, &symbol, "hyperliquid", "mainnet")
                .await?
                .unwrap_or(avg_cost);
            let display_quantity = raw_quantity.abs();
            let notional = display_quantity * avg_cost;
            let current_value = display_quantity * current_price;
            let unrealized_pnl = if raw_quantity >= 0.0 {
                (current_price - avg_cost) * display_quantity
            } else {
                (avg_cost - current_price) * display_quantity
            };

            total_unrealized_pnl += unrealized_pnl;
            positions_value += current_value;

            positions.push(ArenaPositionItem {
                id: row.try_get("id").map_err(read_arena_error)?,
                symbol: symbol.clone(),
                name: row.try_get("name").map_err(read_arena_error)?,
                market,
                side: if raw_quantity >= 0.0 {
                    "LONG".to_owned()
                } else {
                    "SHORT".to_owned()
                },
                quantity: display_quantity,
                avg_cost,
                current_price,
                notional,
                current_value,
                unrealized_pnl,
                leverage: None,
                margin_used: None,
                return_on_equity: None,
                percentage: None,
                margin_mode: None,
                liquidation_px: None,
                max_leverage: None,
                leverage_type: None,
            });
        }

        let total_assets = account.current_cash + positions_value;
        snapshots.push(ArenaPositionsAccount {
            account_id: account.account_id,
            account_name: account.account_name.clone(),
            model: account.model.clone(),
            environment: Some("paper".to_owned()),
            exchange: None,
            wallet_address: None,
            total_unrealized_pnl,
            available_cash: account.current_cash,
            used_margin: None,
            positions_value: Some(positions_value),
            positions,
            total_assets,
            initial_capital: account.initial_capital,
            total_return: compute_total_return(account.initial_capital, total_assets),
            margin_usage_percent: None,
            margin_mode: None,
        });
    }

    Ok(snapshots)
}

async fn load_live_positions_snapshots(
    state: &AppState,
    accounts: &[DashboardAccount],
    trading_mode: &str,
) -> Result<Vec<ArenaPositionsAccount>, AppError> {
    let mut snapshots = Vec::new();

    for account in accounts {
        if let Some(snapshot) =
            load_hyperliquid_position_snapshot(state, account, trading_mode).await?
        {
            snapshots.push(snapshot);
        }
        if let Some(snapshot) = load_binance_position_snapshot(state, account, trading_mode).await?
        {
            snapshots.push(snapshot);
        }
    }

    Ok(snapshots)
}

async fn load_hyperliquid_position_snapshot(
    state: &AppState,
    account: &DashboardAccount,
    trading_mode: &str,
) -> Result<Option<ArenaPositionsAccount>, AppError> {
    let wallet_row = sqlx::query(
        r#"
        SELECT wallet_address
        FROM hyperliquid_wallets
        WHERE account_id = $1
          AND environment = $2
          AND is_active = 'true'
        LIMIT 1
        "#,
    )
    .bind(account.account_id)
    .bind(trading_mode)
    .fetch_optional(&state.db)
    .await
    .map_err(|error| {
        AppError::internal(format!(
            "Failed to load hyperliquid wallet metadata: {error}"
        ))
    })?;

    let Some(wallet_row) = wallet_row else {
        return Ok(None);
    };
    let wallet_address = wallet_row
        .try_get::<Option<String>, _>("wallet_address")
        .map_err(read_arena_error)?;

    let latest_snapshot_time = sqlx::query_scalar::<_, Option<NaiveDateTime>>(
        r#"
        SELECT MAX(snapshot_time)
        FROM hyperliquid_account_snapshots
        WHERE account_id = $1
          AND environment = $2
        "#,
    )
    .bind(account.account_id)
    .bind(trading_mode)
    .fetch_one(&state.db)
    .await
    .map_err(|error| {
        AppError::internal(format!("Failed to load hyperliquid snapshot time: {error}"))
    })?;

    let Some(snapshot_time) = latest_snapshot_time else {
        return Ok(Some(ArenaPositionsAccount {
            account_id: account.account_id,
            account_name: account.account_name.clone(),
            model: account.model.clone(),
            environment: Some(trading_mode.to_owned()),
            exchange: Some("hyperliquid".to_owned()),
            wallet_address,
            total_unrealized_pnl: 0.0,
            available_cash: 0.0,
            used_margin: Some(0.0),
            positions_value: Some(0.0),
            positions: Vec::new(),
            total_assets: account.initial_capital,
            initial_capital: account.initial_capital,
            total_return: Some(0.0),
            margin_usage_percent: Some(0.0),
            margin_mode: Some("cross".to_owned()),
        }));
    };

    let snapshot = sqlx::query(
        r#"
        SELECT
            wallet_address,
            total_equity::float8 AS total_equity,
            available_balance::float8 AS available_balance,
            used_margin::float8 AS used_margin
        FROM hyperliquid_account_snapshots
        WHERE account_id = $1
          AND environment = $2
          AND snapshot_time = $3
        ORDER BY id DESC
        LIMIT 1
        "#,
    )
    .bind(account.account_id)
    .bind(trading_mode)
    .bind(snapshot_time)
    .fetch_optional(&state.db)
    .await
    .map_err(|error| AppError::internal(format!("Failed to load hyperliquid snapshot: {error}")))?;

    let Some(snapshot) = snapshot else {
        return Ok(None);
    };

    let position_rows = sqlx::query(
        r#"
        SELECT
            id,
            symbol,
            position_size::float8 AS position_size,
            entry_price::float8 AS entry_price,
            current_price::float8 AS current_price,
            position_value::float8 AS position_value,
            unrealized_pnl::float8 AS unrealized_pnl,
            margin_used::float8 AS margin_used,
            liquidation_price::float8 AS liquidation_price,
            leverage
        FROM hyperliquid_positions
        WHERE account_id = $1
          AND environment = $2
          AND snapshot_time = $3
          AND position_size != 0
        ORDER BY symbol ASC
        "#,
    )
    .bind(account.account_id)
    .bind(trading_mode)
    .bind(snapshot_time)
    .fetch_all(&state.db)
    .await
    .map_err(|error| {
        AppError::internal(format!("Failed to load hyperliquid positions: {error}"))
    })?;

    let positions = position_rows
        .into_iter()
        .map(|row| {
            let position_size = row
                .try_get::<f64, _>("position_size")
                .map_err(read_arena_error)?;
            let entry_price = row
                .try_get::<f64, _>("entry_price")
                .map_err(read_arena_error)?;
            let current_price = row
                .try_get::<f64, _>("current_price")
                .map_err(read_arena_error)?;
            let quantity = position_size.abs();
            Ok(ArenaPositionItem {
                id: row.try_get("id").map_err(read_arena_error)?,
                symbol: row.try_get("symbol").map_err(read_arena_error)?,
                name: row.try_get("symbol").map_err(read_arena_error)?,
                market: "HYPERLIQUID_PERP".to_owned(),
                side: if position_size >= 0.0 {
                    "LONG".to_owned()
                } else {
                    "SHORT".to_owned()
                },
                quantity,
                avg_cost: entry_price,
                current_price,
                notional: quantity * entry_price,
                current_value: row.try_get("position_value").map_err(read_arena_error)?,
                unrealized_pnl: row.try_get("unrealized_pnl").map_err(read_arena_error)?,
                leverage: row.try_get("leverage").map_err(read_arena_error)?,
                margin_used: row.try_get("margin_used").map_err(read_arena_error)?,
                return_on_equity: None,
                percentage: None,
                margin_mode: Some("cross".to_owned()),
                liquidation_px: row.try_get("liquidation_price").map_err(read_arena_error)?,
                max_leverage: None,
                leverage_type: Some("cross".to_owned()),
            })
        })
        .collect::<Result<Vec<_>, AppError>>()?;

    let total_assets = snapshot
        .try_get::<f64, _>("total_equity")
        .map_err(read_arena_error)?;
    let used_margin = snapshot
        .try_get::<f64, _>("used_margin")
        .map_err(read_arena_error)?;
    Ok(Some(ArenaPositionsAccount {
        account_id: account.account_id,
        account_name: account.account_name.clone(),
        model: account.model.clone(),
        environment: Some(trading_mode.to_owned()),
        exchange: Some("hyperliquid".to_owned()),
        wallet_address: snapshot
            .try_get::<Option<String>, _>("wallet_address")
            .map_err(read_arena_error)?
            .or(wallet_address),
        total_unrealized_pnl: positions
            .iter()
            .map(|position| position.unrealized_pnl)
            .sum(),
        available_cash: snapshot
            .try_get::<f64, _>("available_balance")
            .map_err(read_arena_error)?,
        used_margin: Some(used_margin),
        positions_value: Some(used_margin),
        positions,
        total_assets,
        initial_capital: account.initial_capital,
        total_return: compute_total_return(account.initial_capital, total_assets),
        margin_usage_percent: if total_assets > 0.0 {
            Some(used_margin / total_assets * 100.0)
        } else {
            Some(0.0)
        },
        margin_mode: Some("cross".to_owned()),
    }))
}

async fn load_binance_position_snapshot(
    state: &AppState,
    account: &DashboardAccount,
    trading_mode: &str,
) -> Result<Option<ArenaPositionsAccount>, AppError> {
    let has_wallet = sqlx::query_scalar::<_, Option<i32>>(
        r#"
        SELECT 1
        FROM binance_wallets
        WHERE account_id = $1
          AND environment = $2
          AND is_active = 'true'
        LIMIT 1
        "#,
    )
    .bind(account.account_id)
    .bind(trading_mode)
    .fetch_optional(&state.db)
    .await
    .map_err(|error| {
        AppError::internal(format!("Failed to load binance wallet metadata: {error}"))
    })?
    .flatten()
    .is_some();

    if !has_wallet {
        return Ok(None);
    }

    let snapshot = sqlx::query(
        r#"
        SELECT
            total_wallet_balance::float8 AS total_wallet_balance,
            available_balance::float8 AS available_balance,
            total_unrealized_profit::float8 AS total_unrealized_profit,
            total_margin_balance::float8 AS total_margin_balance,
            total_initial_margin::float8 AS total_initial_margin
        FROM binance_account_snapshots
        WHERE account_id = $1
          AND environment = $2
        ORDER BY snapshot_time DESC, id DESC
        LIMIT 1
        "#,
    )
    .bind(account.account_id)
    .bind(trading_mode)
    .fetch_optional(&state.db)
    .await
    .map_err(|error| AppError::internal(format!("Failed to load binance snapshot: {error}")))?;

    let Some(snapshot) = snapshot else {
        return Ok(Some(ArenaPositionsAccount {
            account_id: account.account_id,
            account_name: account.account_name.clone(),
            model: account.model.clone(),
            environment: Some(trading_mode.to_owned()),
            exchange: Some("binance".to_owned()),
            wallet_address: None,
            total_unrealized_pnl: 0.0,
            available_cash: 0.0,
            used_margin: Some(0.0),
            positions_value: Some(0.0),
            positions: Vec::new(),
            total_assets: account.initial_capital,
            initial_capital: account.initial_capital,
            total_return: Some(0.0),
            margin_usage_percent: Some(0.0),
            margin_mode: Some("cross".to_owned()),
        }));
    };

    let total_assets = snapshot
        .try_get::<f64, _>("total_margin_balance")
        .map_err(read_arena_error)?;
    let used_margin = snapshot
        .try_get::<Option<f64>, _>("total_initial_margin")
        .map_err(read_arena_error)?
        .unwrap_or(0.0);

    Ok(Some(ArenaPositionsAccount {
        account_id: account.account_id,
        account_name: account.account_name.clone(),
        model: account.model.clone(),
        environment: Some(trading_mode.to_owned()),
        exchange: Some("binance".to_owned()),
        wallet_address: None,
        total_unrealized_pnl: snapshot
            .try_get::<f64, _>("total_unrealized_profit")
            .map_err(read_arena_error)?,
        available_cash: snapshot
            .try_get::<f64, _>("available_balance")
            .map_err(read_arena_error)?,
        used_margin: Some(used_margin),
        positions_value: Some(used_margin),
        positions: Vec::new(),
        total_assets,
        initial_capital: account.initial_capital,
        total_return: compute_total_return(account.initial_capital, total_assets),
        margin_usage_percent: if total_assets > 0.0 {
            Some(used_margin / total_assets * 100.0)
        } else {
            Some(0.0)
        },
        margin_mode: Some("cross".to_owned()),
    }))
}

async fn latest_kline_price(
    state: &AppState,
    symbol: &str,
    exchange: &str,
    environment: &str,
) -> Result<Option<f64>, AppError> {
    sqlx::query_scalar::<_, Option<f64>>(
        r#"
        SELECT close_price::float8
        FROM crypto_klines
        WHERE symbol = $1
          AND exchange = $2
          AND period = '1m'
          AND environment = $3
        ORDER BY timestamp DESC
        LIMIT 1
        "#,
    )
    .bind(symbol)
    .bind(exchange)
    .bind(environment)
    .fetch_optional(&state.db)
    .await
    .map(|value| value.flatten())
    .map_err(|error| AppError::internal(format!("Failed to load latest price: {error}")))
}

async fn load_paper_trades(
    state: &AppState,
    query: &ArenaTradesQuery,
    limit: i64,
) -> Result<ArenaTradesResponse, AppError> {
    let rows = sqlx::query(
        r#"
        SELECT
            t.id,
            t.order_id,
            t.account_id,
            t.side,
            t.symbol,
            t.market,
            t.price::float8 AS price,
            t.quantity::float8 AS quantity,
            t.commission::float8 AS commission,
            t.trade_time,
            o.order_no,
            a.name AS account_name,
            a.model AS account_model
        FROM trades t
        JOIN accounts a ON a.id = t.account_id
        LEFT JOIN orders o ON o.id = t.order_id
        WHERE ($1::int4 IS NULL OR t.account_id = $1)
          AND (
                $2::text IS NULL OR
                ($2 = 'paper' AND t.hyperliquid_environment IS NULL) OR
                ($2 != 'paper' AND t.hyperliquid_environment = $2)
          )
          AND ($3::text IS NULL OR t.symbol = $3)
        ORDER BY t.trade_time DESC
        LIMIT $4
        "#,
    )
    .bind(query.account_id)
    .bind(query.trading_mode.as_deref())
    .bind(query.symbol.as_deref())
    .bind(limit)
    .fetch_all(&state.db)
    .await
    .map_err(|error| AppError::internal(format!("Failed to load paper arena trades: {error}")))?;

    if rows.is_empty() {
        return Ok(empty_arena_trades_response());
    }

    let mut trades = Vec::with_capacity(rows.len());
    let mut accounts_meta = HashMap::<i32, ArenaAccountMeta>::new();

    for row in rows {
        let account_id = row
            .try_get::<i32, _>("account_id")
            .map_err(read_arena_error)?;
        let side = row.try_get::<String, _>("side").map_err(read_arena_error)?;
        let quantity = row
            .try_get::<f64, _>("quantity")
            .map_err(read_arena_error)?;
        let price = row.try_get::<f64, _>("price").map_err(read_arena_error)?;
        let trade_time = row
            .try_get::<Option<NaiveDateTime>, _>("trade_time")
            .map_err(read_arena_error)?
            .map(format_utc_iso);

        accounts_meta
            .entry(account_id)
            .or_insert_with(|| ArenaAccountMeta {
                account_id,
                name: row
                    .try_get::<String, _>("account_name")
                    .unwrap_or_else(|_| String::new()),
                model: row
                    .try_get::<Option<String>, _>("account_model")
                    .ok()
                    .flatten(),
            });

        trades.push(ArenaTrade {
            trade_id: row.try_get("id").map_err(read_arena_error)?,
            order_id: row.try_get("order_id").map_err(read_arena_error)?,
            order_no: row.try_get("order_no").map_err(read_arena_error)?,
            account_id,
            account_name: row.try_get("account_name").map_err(read_arena_error)?,
            model: row.try_get("account_model").map_err(read_arena_error)?,
            side: side.clone(),
            direction: if side.to_uppercase() == "BUY" {
                "LONG".to_owned()
            } else {
                "SHORT".to_owned()
            },
            symbol: row.try_get("symbol").map_err(read_arena_error)?,
            market: row.try_get("market").map_err(read_arena_error)?,
            price,
            quantity,
            notional: price * quantity,
            commission: row.try_get("commission").map_err(read_arena_error)?,
            trade_time,
            wallet_address: None,
            signal_trigger_id: None,
            prompt_template_id: None,
            prompt_template_name: None,
            decision_source_type: None,
            related_orders: None,
            exchange: None,
        });
    }

    let mut accounts = accounts_meta.into_values().collect::<Vec<_>>();
    accounts.sort_by_key(|account| account.account_id);

    Ok(ArenaTradesResponse {
        generated_at: Utc::now().to_rfc3339(),
        accounts,
        trades,
    })
}

fn build_related_order(trade: &ArenaTrade, kind: &str) -> ArenaRelatedOrder {
    ArenaRelatedOrder {
        kind: kind.to_owned(),
        price: trade.price,
        quantity: trade.quantity,
        notional: trade.notional,
        commission: trade.commission,
        trade_time: trade.trade_time.clone(),
    }
}

fn attach_related_orders(
    main_trades: &mut HashMap<String, ArenaTrade>,
    related_orders: &HashMap<String, ArenaRelatedOrder>,
    primary_map: &HashMap<String, String>,
    secondary_map: &HashMap<String, String>,
) {
    for (order_id, related_order) in related_orders {
        let main_order_id = primary_map
            .get(order_id)
            .or_else(|| secondary_map.get(order_id));
        if let Some(main_order_id) = main_order_id {
            if let Some(main_trade) = main_trades.get_mut(main_order_id) {
                main_trade
                    .related_orders
                    .get_or_insert_with(Vec::new)
                    .push(related_order.clone());
            }
        }
    }
}

async fn load_program_names(
    state: &AppState,
    ids: &[i32],
) -> Result<HashMap<i32, String>, AppError> {
    if ids.is_empty() {
        return Ok(HashMap::new());
    }
    let rows = sqlx::query(
        r#"
        SELECT id, name
        FROM trading_programs
        WHERE id = ANY($1)
          AND COALESCE(is_deleted, false) = false
        "#,
    )
    .bind(ids)
    .fetch_all(&state.db)
    .await
    .map_err(|error| AppError::internal(format!("Failed to load program names: {error}")))?;

    rows.into_iter()
        .map(|row| {
            Ok((
                row.try_get::<i32, _>("id").map_err(read_arena_error)?,
                row.try_get::<String, _>("name").map_err(read_arena_error)?,
            ))
        })
        .collect()
}

async fn load_strategy_context(
    state: &AppState,
    account_ids: &[i32],
) -> Result<HashMap<i32, StrategyContext>, AppError> {
    if account_ids.is_empty() {
        return Ok(HashMap::new());
    }
    let rows = sqlx::query(
        r#"
        SELECT account_id, enabled, last_trigger_at
        FROM account_strategy_configs
        WHERE account_id = ANY($1)
        "#,
    )
    .bind(account_ids)
    .fetch_all(&state.db)
    .await
    .map_err(|error| AppError::internal(format!("Failed to load strategy context: {error}")))?;

    rows.into_iter()
        .map(|row| {
            Ok((
                row.try_get::<i32, _>("account_id")
                    .map_err(read_arena_error)?,
                StrategyContext {
                    enabled: row
                        .try_get::<String, _>("enabled")
                        .map_err(read_arena_error)?
                        == "true",
                    last_trigger_at: row
                        .try_get::<Option<NaiveDateTime>, _>("last_trigger_at")
                        .map_err(read_arena_error)?,
                },
            ))
        })
        .collect()
}

async fn load_prompt_names(
    state: &AppState,
    ids: &[i32],
) -> Result<HashMap<i32, String>, AppError> {
    if ids.is_empty() {
        return Ok(HashMap::new());
    }
    let rows = sqlx::query(
        r#"
        SELECT id, name
        FROM prompt_templates
        WHERE id = ANY($1)
          AND is_deleted = 'false'
        "#,
    )
    .bind(ids)
    .fetch_all(&state.db)
    .await
    .map_err(|error| AppError::internal(format!("Failed to load prompt names: {error}")))?;
    rows.into_iter()
        .map(|row| {
            Ok((
                row.try_get::<i32, _>("id").map_err(read_arena_error)?,
                row.try_get::<String, _>("name").map_err(read_arena_error)?,
            ))
        })
        .collect()
}

fn parse_optional_timestamp(value: Option<&str>) -> Result<Option<NaiveDateTime>, AppError> {
    let Some(value) = value else {
        return Ok(None);
    };
    DateTime::parse_from_rfc3339(&value.replace('Z', "+00:00"))
        .map(|value| Some(value.naive_utc()))
        .map_err(|error| AppError::bad_request(format!("Invalid timestamp `{value}`: {error}")))
}

fn parse_ids(value: Option<&str>) -> Vec<i32> {
    value
        .unwrap_or_default()
        .split(',')
        .filter_map(|part| part.trim().parse::<i32>().ok())
        .collect()
}

fn normalize_trading_mode(value: Option<&str>) -> Result<Option<String>, AppError> {
    match value {
        Some("paper" | "testnet" | "mainnet") => Ok(value.map(str::to_owned)),
        Some(other) => Err(AppError::bad_request(format!(
            "Invalid trading_mode `{other}`"
        ))),
        None => Ok(None),
    }
}

fn normalize_operation(value: Option<&str>) -> Result<Option<String>, AppError> {
    match value {
        Some("buy" | "sell" | "hold" | "close") => Ok(value.map(str::to_owned)),
        Some(other) => Err(AppError::bad_request(format!(
            "Invalid operation `{other}`"
        ))),
        None => Ok(None),
    }
}

fn normalize_exchange(value: Option<&str>) -> Result<Option<String>, AppError> {
    match value {
        Some("hyperliquid" | "binance") => Ok(value.map(str::to_owned)),
        Some(other) => Err(AppError::bad_request(format!("Invalid exchange `{other}`"))),
        None => Ok(None),
    }
}

fn format_utc_iso(value: NaiveDateTime) -> String {
    value.and_utc().to_rfc3339()
}

fn read_arena_error(error: sqlx::Error) -> AppError {
    AppError::internal(format!("Failed to read arena data: {error}"))
}

async fn aggregate_account_stats(
    state: &AppState,
    account: &sqlx::postgres::PgRow,
) -> Result<Value, AppError> {
    let account_id = account.try_get::<i32, _>("id").map_err(read_arena_error)?;
    let initial_capital = account
        .try_get::<f64, _>("initial_capital")
        .map_err(read_arena_error)?;
    let current_cash = account
        .try_get::<f64, _>("current_cash")
        .map_err(read_arena_error)?;
    let positions_value = estimate_positions_value_local(state, account_id).await?;
    let total_assets = positions_value + current_cash;
    let total_pnl = total_assets - initial_capital;
    let total_return_pct = if initial_capital != 0.0 {
        Some((total_assets - initial_capital) / initial_capital)
    } else {
        None
    };

    let trades = sqlx::query(
        r#"
        SELECT price::float8 AS price,
               quantity::float8 AS quantity,
               commission::float8 AS commission,
               trade_time
        FROM trades
        WHERE account_id = $1
        ORDER BY trade_time ASC
        "#,
    )
    .bind(account_id)
    .fetch_all(&state.db)
    .await
    .map_err(|error| AppError::internal(format!("Failed to load arena trades: {error}")))?;
    let total_fees = trades
        .iter()
        .map(|row| row.try_get::<f64, _>("commission").unwrap_or(0.0))
        .sum::<f64>();
    let total_volume = trades
        .iter()
        .map(|row| {
            row.try_get::<f64, _>("price").unwrap_or(0.0)
                * row.try_get::<f64, _>("quantity").unwrap_or(0.0).abs()
        })
        .sum::<f64>();
    let first_trade_time = trades
        .first()
        .and_then(|row| {
            row.try_get::<Option<NaiveDateTime>, _>("trade_time")
                .ok()
                .flatten()
        })
        .map(format_utc_iso);
    let last_trade_time = trades
        .last()
        .and_then(|row| {
            row.try_get::<Option<NaiveDateTime>, _>("trade_time")
                .ok()
                .flatten()
        })
        .map(format_utc_iso);

    let decisions = sqlx::query(
        r#"
        SELECT decision_time,
               total_balance::float8 AS total_balance,
               target_portion::float8 AS target_portion,
               executed
        FROM ai_decision_logs
        WHERE account_id = $1
        ORDER BY decision_time ASC
        "#,
    )
    .bind(account_id)
    .fetch_all(&state.db)
    .await
    .map_err(|error| AppError::internal(format!("Failed to load arena decisions: {error}")))?;
    let balances = decisions
        .iter()
        .filter_map(|row| {
            row.try_get::<Option<f64>, _>("total_balance")
                .ok()
                .flatten()
        })
        .collect::<Vec<_>>();
    let (biggest_gain, biggest_loss, returns, balance_volatility) =
        analyze_balance_series(&balances);
    let sharpe_ratio = compute_sharpe_ratio(&returns);
    let wins = returns.iter().filter(|value| **value > 0.0).count();
    let losses = returns.iter().filter(|value| **value < 0.0).count();
    let win_rate = if returns.is_empty() {
        None
    } else {
        Some(wins as f64 / returns.len() as f64)
    };
    let loss_rate = if returns.is_empty() {
        None
    } else {
        Some(losses as f64 / returns.len() as f64)
    };
    let executed_decisions = decisions
        .iter()
        .filter(|row| row.try_get::<String, _>("executed").unwrap_or_default() == "true")
        .count();
    let decision_execution_rate = if decisions.is_empty() {
        None
    } else {
        Some(executed_decisions as f64 / decisions.len() as f64)
    };
    let avg_target_portion = if decisions.is_empty() {
        None
    } else {
        Some(
            decisions
                .iter()
                .filter_map(|row| {
                    row.try_get::<Option<f64>, _>("target_portion")
                        .ok()
                        .flatten()
                })
                .sum::<f64>()
                / decisions.len() as f64,
        )
    };
    let avg_decision_interval_minutes = average_decision_interval_minutes(&decisions);

    Ok(serde_json::json!({
        "account_id": account_id,
        "account_name": account.try_get::<String, _>("name").map_err(read_arena_error)?,
        "model": account.try_get::<Option<String>, _>("model").map_err(read_arena_error)?,
        "initial_capital": initial_capital,
        "current_cash": current_cash,
        "positions_value": positions_value,
        "total_assets": total_assets,
        "total_pnl": total_pnl,
        "total_return_pct": total_return_pct,
        "total_fees": total_fees,
        "trade_count": trades.len(),
        "total_volume": total_volume,
        "first_trade_time": first_trade_time,
        "last_trade_time": last_trade_time,
        "biggest_gain": biggest_gain,
        "biggest_loss": biggest_loss,
        "win_rate": win_rate,
        "loss_rate": loss_rate,
        "sharpe_ratio": sharpe_ratio,
        "balance_volatility": balance_volatility,
        "decision_count": decisions.len(),
        "executed_decisions": executed_decisions,
        "decision_execution_rate": decision_execution_rate,
        "avg_target_portion": avg_target_portion,
        "avg_decision_interval_minutes": avg_decision_interval_minutes,
    }))
}

async fn estimate_positions_value_local(
    state: &AppState,
    account_id: i32,
) -> Result<f64, AppError> {
    let positions = sqlx::query(
        r#"
        SELECT symbol, quantity::float8 AS quantity, avg_cost::float8 AS avg_cost
        FROM positions
        WHERE account_id = $1
        "#,
    )
    .bind(account_id)
    .fetch_all(&state.db)
    .await
    .map_err(|error| {
        AppError::internal(format!(
            "Failed to load positions for arena analytics: {error}"
        ))
    })?;

    let mut total = 0.0;
    for position in positions {
        let symbol = position
            .try_get::<String, _>("symbol")
            .map_err(read_arena_error)?;
        let quantity = position
            .try_get::<f64, _>("quantity")
            .map_err(read_arena_error)?;
        let avg_cost = position
            .try_get::<f64, _>("avg_cost")
            .map_err(read_arena_error)?;
        let price = sqlx::query_scalar::<_, Option<f64>>(
            r#"
            SELECT close_price::float8
            FROM crypto_klines
            WHERE symbol = $1
              AND exchange = 'hyperliquid'
              AND period = '1m'
              AND environment = 'mainnet'
            ORDER BY timestamp DESC
            LIMIT 1
            "#,
        )
        .bind(&symbol)
        .fetch_optional(&state.db)
        .await
        .map_err(|error| {
            AppError::internal(format!("Failed to load price for arena analytics: {error}"))
        })?;
        total += quantity * price.flatten().unwrap_or(avg_cost);
    }
    Ok(total)
}

fn analyze_balance_series(balances: &[f64]) -> (f64, f64, Vec<f64>, f64) {
    if balances.len() < 2 {
        return (0.0, 0.0, Vec::new(), 0.0);
    }

    let mut biggest_gain = f64::NEG_INFINITY;
    let mut biggest_loss = f64::INFINITY;
    let mut returns = Vec::new();
    let mut previous = balances[0];

    for current in balances.iter().skip(1) {
        let delta = current - previous;
        biggest_gain = biggest_gain.max(delta);
        biggest_loss = biggest_loss.min(delta);
        if previous != 0.0 {
            returns.push(delta / previous);
        }
        previous = *current;
    }

    let mean = balances.iter().sum::<f64>() / balances.len() as f64;
    let variance = balances
        .iter()
        .map(|value| {
            let diff = value - mean;
            diff * diff
        })
        .sum::<f64>()
        / balances.len() as f64;

    (
        if biggest_gain.is_finite() {
            biggest_gain
        } else {
            0.0
        },
        if biggest_loss.is_finite() {
            biggest_loss
        } else {
            0.0
        },
        returns,
        variance.sqrt(),
    )
}

fn compute_sharpe_ratio(returns: &[f64]) -> Option<f64> {
    if returns.len() < 2 {
        return None;
    }
    let mean = returns.iter().sum::<f64>() / returns.len() as f64;
    let variance = returns
        .iter()
        .map(|value| {
            let diff = value - mean;
            diff * diff
        })
        .sum::<f64>()
        / returns.len() as f64;
    let volatility = variance.sqrt();
    if volatility == 0.0 {
        None
    } else {
        Some(mean / volatility * (returns.len() as f64).sqrt())
    }
}

fn average_decision_interval_minutes(rows: &[sqlx::postgres::PgRow]) -> Option<f64> {
    if rows.len() < 2 {
        return None;
    }
    let mut intervals = Vec::new();
    let mut previous = rows[0]
        .try_get::<Option<NaiveDateTime>, _>("decision_time")
        .ok()
        .flatten();
    for row in rows.iter().skip(1) {
        let current = row
            .try_get::<Option<NaiveDateTime>, _>("decision_time")
            .ok()
            .flatten();
        if let (Some(previous), Some(current)) = (previous, current) {
            intervals.push((current - previous).num_seconds() as f64 / 60.0);
        }
        previous = current;
    }
    if intervals.is_empty() {
        None
    } else {
        Some(intervals.iter().sum::<f64>() / intervals.len() as f64)
    }
}

fn compute_total_return(initial_capital: f64, total_assets: f64) -> Option<f64> {
    if initial_capital > 0.0 {
        Some((total_assets - initial_capital) / initial_capital)
    } else {
        None
    }
}

fn validate_trade_limit(limit: i64) -> Result<i64, AppError> {
    if (1..=500).contains(&limit) {
        Ok(limit)
    } else {
        Err(AppError::bad_request(format!(
            "Invalid limit `{limit}`; expected 1-500"
        )))
    }
}

fn empty_arena_trades_response() -> ArenaTradesResponse {
    ArenaTradesResponse {
        generated_at: Utc::now().to_rfc3339(),
        accounts: Vec::new(),
        trades: Vec::new(),
    }
}

fn default_trade_limit() -> i64 {
    100
}

fn default_model_chat_limit() -> i64 {
    60
}

#[cfg(test)]
mod tests {
    use super::{
        analyze_balance_series, compute_sharpe_ratio, compute_total_return, normalize_exchange,
        normalize_operation, normalize_trading_mode, parse_ids, validate_trade_limit,
    };

    #[test]
    fn parses_id_lists_for_model_chat_batch_fetch() {
        assert_eq!(parse_ids(Some("1, 2,abc,3")), vec![1, 2, 3]);
    }

    #[test]
    fn validates_enums_for_arena_queries() {
        assert!(normalize_trading_mode(Some("mainnet")).is_ok());
        assert!(normalize_operation(Some("hold")).is_ok());
        assert!(normalize_exchange(Some("binance")).is_ok());
        assert!(normalize_trading_mode(Some("invalid")).is_err());
    }

    #[test]
    fn balance_series_analysis_returns_expected_shapes() {
        let (gain, loss, returns, volatility) = analyze_balance_series(&[100.0, 110.0, 90.0]);
        assert_eq!(gain, 10.0);
        assert_eq!(loss, -20.0);
        assert_eq!(returns.len(), 2);
        assert!(volatility > 0.0);
    }

    #[test]
    fn sharpe_requires_nonzero_volatility() {
        assert!(compute_sharpe_ratio(&[0.1, 0.1]).is_none());
        assert!(compute_sharpe_ratio(&[0.1, -0.1]).is_some());
    }

    #[test]
    fn validates_trade_limit_bounds() {
        assert_eq!(validate_trade_limit(1).unwrap(), 1);
        assert_eq!(validate_trade_limit(500).unwrap(), 500);
        assert!(validate_trade_limit(0).is_err());
        assert!(validate_trade_limit(501).is_err());
    }

    #[test]
    fn computes_total_return_when_initial_capital_is_positive() {
        assert_eq!(compute_total_return(100.0, 110.0), Some(0.1));
        assert_eq!(compute_total_return(0.0, 110.0), None);
    }
}
