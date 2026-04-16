use axum::{
    Json,
    extract::{Path, Query, State},
};
use chrono::{NaiveDate, NaiveDateTime};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use sqlx::Row;
use std::collections::HashMap;
use tracing::warn;

use crate::{error::AppError, state::AppState};

#[derive(Deserialize)]
pub struct AnalyticsQuery {
    start_date: Option<String>,
    end_date: Option<String>,
    #[serde(default = "default_all")]
    environment: String,
    account_id: Option<i32>,
    #[serde(default = "default_all")]
    exchange: String,
}

#[derive(Serialize, Clone)]
pub struct Metrics {
    total_pnl: f64,
    total_fee: f64,
    net_pnl: f64,
    trade_count: usize,
    win_count: usize,
    loss_count: usize,
    win_rate: f64,
    avg_win: Option<f64>,
    avg_loss: Option<f64>,
    profit_factor: Option<f64>,
}

#[derive(Serialize)]
pub struct SummaryResponse {
    period: PeriodRange,
    overview: Metrics,
    data_completeness: Value,
    by_trigger_type: HashMap<String, TriggerBreakdown>,
    by_source: HashMap<String, TriggerBreakdown>,
}

#[derive(Serialize)]
pub struct PeriodRange {
    start: Option<String>,
    end: Option<String>,
}

#[derive(Serialize, Clone)]
pub struct TriggerBreakdown {
    count: usize,
    net_pnl: f64,
}

#[derive(Serialize)]
pub struct DimensionResponse {
    items: Vec<Value>,
    unattributed: UnattributedBlock,
}

#[derive(Serialize)]
pub struct UnattributedBlock {
    count: usize,
    metrics: Option<Metrics>,
}

#[derive(Clone)]
struct AiDecisionRecord {
    account_id: Option<i32>,
    prompt_template_id: Option<i32>,
    signal_trigger_id: Option<i32>,
    operation: String,
    symbol: Option<String>,
    pnl: f64,
    fee: f64,
    trigger_type: String,
}

#[derive(Clone)]
struct ProgramRecord {
    program_id: Option<i32>,
    program_name: Option<String>,
    signal_pool_id: Option<i32>,
    decision_action: Option<String>,
    decision_symbol: Option<String>,
    pnl: f64,
    fee: f64,
    trigger_type: String,
}

#[derive(Serialize)]
pub struct AttributionConversationsResponse {
    conversations: Vec<AttributionConversationItem>,
}

#[derive(Serialize)]
pub struct AttributionConversationItem {
    id: i32,
    title: String,
    created_at: Option<String>,
    updated_at: Option<String>,
}

#[derive(Serialize)]
pub struct AttributionMessagesResponse {
    messages: Vec<AttributionMessageItem>,
    compression_points: Vec<Value>,
    token_usage: Option<Value>,
}

#[derive(Serialize)]
pub struct AttributionMessageItem {
    id: i32,
    role: String,
    content: String,
    created_at: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    diagnosis_results: Option<Value>,
    #[serde(skip_serializing_if = "Option::is_none")]
    reasoning_snapshot: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    tool_calls_log: Option<Value>,
    is_complete: bool,
}

pub async fn get_analytics_summary(
    State(state): State<AppState>,
    Query(query): Query<AnalyticsQuery>,
) -> Result<Json<SummaryResponse>, AppError> {
    let start_date = parse_query_date(&query.start_date)?;
    let end_date = parse_query_date(&query.end_date)?;
    let ai_records = load_ai_decision_records(&state, &query, start_date, end_date).await?;
    let program_records = load_program_records(&state, &query, start_date, end_date).await?;

    let overview = calculate_metrics_from_pairs(
        ai_records
            .iter()
            .map(|r| (r.pnl, r.fee))
            .chain(program_records.iter().map(|r| (r.pnl, r.fee)))
            .collect(),
    );

    let mut by_trigger_type = HashMap::new();
    by_trigger_type.insert(
        "signal".to_owned(),
        trigger_breakdown(
            ai_records
                .iter()
                .filter(|r| r.trigger_type == "signal")
                .map(|r| (r.pnl, r.fee))
                .chain(
                    program_records
                        .iter()
                        .filter(|r| r.trigger_type == "signal")
                        .map(|r| (r.pnl, r.fee)),
                )
                .collect(),
        ),
    );
    by_trigger_type.insert(
        "scheduled".to_owned(),
        trigger_breakdown(
            ai_records
                .iter()
                .filter(|r| r.trigger_type == "scheduled")
                .map(|r| (r.pnl, r.fee))
                .chain(
                    program_records
                        .iter()
                        .filter(|r| r.trigger_type != "signal")
                        .map(|r| (r.pnl, r.fee)),
                )
                .collect(),
        ),
    );
    by_trigger_type.insert(
        "unknown".to_owned(),
        trigger_breakdown(
            ai_records
                .iter()
                .filter(|r| r.trigger_type == "unknown")
                .map(|r| (r.pnl, r.fee))
                .collect(),
        ),
    );

    let mut by_source = HashMap::new();
    by_source.insert(
        "ai_decision".to_owned(),
        trigger_breakdown(ai_records.iter().map(|r| (r.pnl, r.fee)).collect()),
    );
    by_source.insert(
        "program".to_owned(),
        trigger_breakdown(program_records.iter().map(|r| (r.pnl, r.fee)).collect()),
    );

    Ok(Json(SummaryResponse {
        period: PeriodRange {
            start: query.start_date.clone(),
            end: query.end_date.clone(),
        },
        overview,
        data_completeness: serde_json::json!({
            "total_decisions": ai_records.len(),
            "total_program_executions": program_records.len(),
            "with_strategy": ai_records.iter().filter(|r| r.prompt_template_id.is_some()).count(),
            "with_program": program_records.iter().filter(|r| r.program_id.is_some()).count(),
            "with_signal": ai_records.iter().filter(|r| r.signal_trigger_id.is_some()).count()
                + program_records.iter().filter(|r| r.signal_pool_id.is_some()).count(),
            "with_pnl": ai_records.len() + program_records.len(),
        }),
        by_trigger_type,
        by_source,
    }))
}

pub async fn get_analytics_by_strategy(
    State(state): State<AppState>,
    Query(query): Query<AnalyticsQuery>,
) -> Result<Json<DimensionResponse>, AppError> {
    let records = load_ai_decision_records(
        &state,
        &query,
        parse_query_date(&query.start_date)?,
        parse_query_date(&query.end_date)?,
    )
    .await?;
    let names = load_prompt_template_names(
        &state,
        &records
            .iter()
            .filter_map(|r| r.prompt_template_id)
            .collect::<Vec<_>>(),
    )
    .await?;
    Ok(Json(group_ai_dimension(
        records,
        |r| r.prompt_template_id,
        |key| {
            key.map(|id| {
                serde_json::json!({
                    "strategy_id": id,
                    "strategy_name": names.get(&id).cloned().unwrap_or_else(|| format!("Strategy {id}")),
                })
            })
        },
    )))
}

pub async fn get_analytics_by_account(
    State(state): State<AppState>,
    Query(mut query): Query<AnalyticsQuery>,
) -> Result<Json<DimensionResponse>, AppError> {
    query.account_id = None;
    let records = load_ai_decision_records(
        &state,
        &query,
        parse_query_date(&query.start_date)?,
        parse_query_date(&query.end_date)?,
    )
    .await?;
    let accounts = load_account_info(
        &state,
        &records
            .iter()
            .filter_map(|r| r.account_id)
            .collect::<Vec<_>>(),
    )
    .await?;
    Ok(Json(group_ai_dimension(
        records,
        |r| r.account_id,
        |key| {
            key.map(|id| {
                let info = accounts.get(&id);
                serde_json::json!({
                    "account_id": id,
                    "account_name": info.map(|v| v.0.clone()).unwrap_or_else(|| format!("Account {id}")),
                    "model": info.and_then(|v| v.1.clone()),
                    "environment": info.and_then(|v| v.2.clone()),
                })
            })
        },
    )))
}

pub async fn get_analytics_by_symbol(
    State(state): State<AppState>,
    Query(query): Query<AnalyticsQuery>,
) -> Result<Json<DimensionResponse>, AppError> {
    let records = load_ai_decision_records(
        &state,
        &query,
        parse_query_date(&query.start_date)?,
        parse_query_date(&query.end_date)?,
    )
    .await?;
    Ok(Json(group_ai_dimension_string(
        records,
        |r| r.symbol.clone(),
        |value| value.map(|symbol| serde_json::json!({ "symbol": symbol })),
        true,
    )))
}

pub async fn get_analytics_by_operation(
    State(state): State<AppState>,
    Query(query): Query<AnalyticsQuery>,
) -> Result<Json<DimensionResponse>, AppError> {
    let records = load_ai_decision_records(
        &state,
        &query,
        parse_query_date(&query.start_date)?,
        parse_query_date(&query.end_date)?,
    )
    .await?;
    Ok(Json(group_ai_dimension_string(
        records,
        |r| Some(r.operation.clone()),
        |value| value.map(|operation| serde_json::json!({ "operation": operation })),
        false,
    )))
}

pub async fn get_analytics_by_trigger_type(
    State(state): State<AppState>,
    Query(query): Query<AnalyticsQuery>,
) -> Result<Json<DimensionResponse>, AppError> {
    let records = load_ai_decision_records(
        &state,
        &query,
        parse_query_date(&query.start_date)?,
        parse_query_date(&query.end_date)?,
    )
    .await?;
    Ok(Json(group_ai_dimension_string(
        records,
        |r| Some(r.trigger_type.clone()),
        |value| value.map(|trigger_type| serde_json::json!({ "trigger_type": trigger_type })),
        false,
    )))
}

pub async fn get_analytics_by_factor(
    State(state): State<AppState>,
    Query(query): Query<AnalyticsQuery>,
) -> Result<Json<DimensionResponse>, AppError> {
    let records = load_ai_decision_records(
        &state,
        &query,
        parse_query_date(&query.start_date)?,
        parse_query_date(&query.end_date)?,
    )
    .await?;
    let mut decision_by_trigger: HashMap<i32, Vec<AiDecisionRecord>> = HashMap::new();
    let trigger_ids = records
        .iter()
        .filter_map(|r| r.signal_trigger_id)
        .collect::<Vec<_>>();
    for record in records {
        if let Some(trigger_id) = record.signal_trigger_id {
            decision_by_trigger
                .entry(trigger_id)
                .or_default()
                .push(record);
        }
    }

    if trigger_ids.is_empty() {
        return Ok(Json(DimensionResponse {
            items: Vec::new(),
            unattributed: UnattributedBlock {
                count: 0,
                metrics: None,
            },
        }));
    }

    let rows = sqlx::query(
        r#"
        SELECT id, trigger_value
        FROM signal_trigger_logs
        WHERE id = ANY($1)
        "#,
    )
    .bind(&trigger_ids)
    .fetch_all(&state.db)
    .await
    .map_err(|error| AppError::internal(format!("Failed to get factor analytics: {error}")))?;

    let mut by_factor: HashMap<String, Vec<(f64, f64)>> = HashMap::new();
    for row in rows {
        let trigger_id = row.try_get::<i32, _>("id").map_err(read_analytics_error)?;
        let factor_name = parse_optional_json(
            row.try_get::<Option<String>, _>("trigger_value")
                .map_err(read_analytics_error)?,
        )
        .and_then(extract_factor_name_from_trigger_value);
        let Some(factor_name) = factor_name else {
            continue;
        };
        for decision in decision_by_trigger.get(&trigger_id).into_iter().flatten() {
            by_factor
                .entry(factor_name.clone())
                .or_default()
                .push((decision.pnl, decision.fee));
        }
    }

    let mut items = by_factor
        .into_iter()
        .map(|(factor_name, pairs)| {
            serde_json::json!({
                "factor_name": factor_name,
                "metrics": calculate_metrics_from_pairs(pairs),
            })
        })
        .collect::<Vec<_>>();
    items.sort_by(|a, b| {
        b["metrics"]["trade_count"]
            .as_u64()
            .unwrap_or(0)
            .cmp(&a["metrics"]["trade_count"].as_u64().unwrap_or(0))
    });

    Ok(Json(DimensionResponse {
        items,
        unattributed: UnattributedBlock {
            count: 0,
            metrics: None,
        },
    }))
}

pub async fn get_program_analytics_summary(
    State(state): State<AppState>,
    Query(query): Query<AnalyticsQuery>,
) -> Result<Json<SummaryResponse>, AppError> {
    let records = load_program_records(
        &state,
        &query,
        parse_query_date(&query.start_date)?,
        parse_query_date(&query.end_date)?,
    )
    .await?;
    let overview = calculate_metrics_from_pairs(records.iter().map(|r| (r.pnl, r.fee)).collect());
    let mut by_trigger_type = HashMap::new();
    by_trigger_type.insert(
        "signal".to_owned(),
        trigger_breakdown(
            records
                .iter()
                .filter(|r| r.trigger_type == "signal")
                .map(|r| (r.pnl, r.fee))
                .collect(),
        ),
    );
    by_trigger_type.insert(
        "scheduled".to_owned(),
        trigger_breakdown(
            records
                .iter()
                .filter(|r| r.trigger_type != "signal")
                .map(|r| (r.pnl, r.fee))
                .collect(),
        ),
    );

    Ok(Json(SummaryResponse {
        period: PeriodRange {
            start: query.start_date.clone(),
            end: query.end_date.clone(),
        },
        overview,
        data_completeness: serde_json::json!({
            "total_executions": records.len(),
            "with_program": records.iter().filter(|r| r.program_id.is_some()).count(),
            "with_signal": records.iter().filter(|r| r.signal_pool_id.is_some()).count(),
            "with_pnl": records.len(),
        }),
        by_trigger_type,
        by_source: HashMap::new(),
    }))
}

pub async fn get_program_analytics_by_symbol(
    State(state): State<AppState>,
    Query(query): Query<AnalyticsQuery>,
) -> Result<Json<DimensionResponse>, AppError> {
    let records = load_program_records(
        &state,
        &query,
        parse_query_date(&query.start_date)?,
        parse_query_date(&query.end_date)?,
    )
    .await?;
    Ok(Json(group_program_dimension_string(
        records,
        |r| r.decision_symbol.clone(),
        |value| value.map(|symbol| serde_json::json!({ "symbol": symbol })),
        true,
    )))
}

pub async fn get_program_analytics_by_program(
    State(state): State<AppState>,
    Query(query): Query<AnalyticsQuery>,
) -> Result<Json<DimensionResponse>, AppError> {
    let records = load_program_records(
        &state,
        &query,
        parse_query_date(&query.start_date)?,
        parse_query_date(&query.end_date)?,
    )
    .await?;
    Ok(Json(group_program_dimension(
        records,
        |r| r.program_id,
        |key, first| {
            key.map(|id| {
                serde_json::json!({
                    "program_id": id,
                    "program_name": first.program_name.clone().unwrap_or_else(|| format!("Program {id}")),
                })
            })
        },
    )))
}

pub async fn get_program_analytics_by_trigger_type(
    State(state): State<AppState>,
    Query(query): Query<AnalyticsQuery>,
) -> Result<Json<DimensionResponse>, AppError> {
    let records = load_program_records(
        &state,
        &query,
        parse_query_date(&query.start_date)?,
        parse_query_date(&query.end_date)?,
    )
    .await?;
    Ok(Json(group_program_dimension_string(
        records,
        |r| Some(r.trigger_type.clone()),
        |value| value.map(|trigger_type| serde_json::json!({ "trigger_type": trigger_type })),
        false,
    )))
}

pub async fn get_program_analytics_by_operation(
    State(state): State<AppState>,
    Query(query): Query<AnalyticsQuery>,
) -> Result<Json<DimensionResponse>, AppError> {
    let records = load_program_records(
        &state,
        &query,
        parse_query_date(&query.start_date)?,
        parse_query_date(&query.end_date)?,
    )
    .await?;
    Ok(Json(group_program_dimension_string(
        records,
        |r| r.decision_action.clone(),
        |value| value.map(|operation| serde_json::json!({ "operation": operation })),
        false,
    )))
}

pub async fn list_attribution_conversations(
    State(state): State<AppState>,
) -> Result<Json<AttributionConversationsResponse>, AppError> {
    let rows = sqlx::query(
        r#"
        SELECT id, title, created_at, updated_at
        FROM ai_attribution_conversations
        WHERE user_id = 1
        ORDER BY updated_at DESC
        LIMIT 20
        "#,
    )
    .fetch_all(&state.db)
    .await
    .map_err(|error| {
        AppError::internal(format!("Failed to list attribution conversations: {error}"))
    })?;

    let conversations = rows
        .into_iter()
        .map(|row| {
            Ok(AttributionConversationItem {
                id: row.try_get("id").map_err(read_analytics_error)?,
                title: row.try_get("title").map_err(read_analytics_error)?,
                created_at: row
                    .try_get::<Option<NaiveDateTime>, _>("created_at")
                    .map_err(read_analytics_error)?
                    .map(format_naive_iso),
                updated_at: row
                    .try_get::<Option<NaiveDateTime>, _>("updated_at")
                    .map_err(read_analytics_error)?
                    .map(format_naive_iso),
            })
        })
        .collect::<Result<Vec<_>, AppError>>()?;

    Ok(Json(AttributionConversationsResponse { conversations }))
}

pub async fn get_attribution_messages(
    State(state): State<AppState>,
    Path(conversation_id): Path<i32>,
) -> Result<Json<AttributionMessagesResponse>, AppError> {
    let conversation = sqlx::query(
        r#"
        SELECT compression_points
        FROM ai_attribution_conversations
        WHERE id = $1 AND user_id = 1
        LIMIT 1
        "#,
    )
    .bind(conversation_id)
    .fetch_optional(&state.db)
    .await
    .map_err(|error| {
        AppError::internal(format!("Failed to get attribution conversation: {error}"))
    })?;

    let Some(conversation) = conversation else {
        return Ok(Json(AttributionMessagesResponse {
            messages: Vec::new(),
            compression_points: Vec::new(),
            token_usage: None,
        }));
    };

    let compression_points = conversation
        .try_get::<Option<String>, _>("compression_points")
        .map_err(read_analytics_error)?
        .and_then(|raw| serde_json::from_str::<Vec<Value>>(&raw).ok())
        .unwrap_or_default();

    let rows = sqlx::query(
        r#"
        SELECT id, role, content, diagnosis_result, reasoning_snapshot,
               tool_calls_log, is_complete, created_at
        FROM ai_attribution_messages
        WHERE conversation_id = $1
        ORDER BY created_at
        "#,
    )
    .bind(conversation_id)
    .fetch_all(&state.db)
    .await
    .map_err(|error| AppError::internal(format!("Failed to get attribution messages: {error}")))?;

    let messages = rows
        .into_iter()
        .map(row_to_attribution_message)
        .collect::<Result<Vec<_>, _>>()?;

    Ok(Json(AttributionMessagesResponse {
        messages,
        compression_points,
        token_usage: None,
    }))
}

fn row_to_attribution_message(
    row: sqlx::postgres::PgRow,
) -> Result<AttributionMessageItem, AppError> {
    Ok(AttributionMessageItem {
        id: row.try_get("id").map_err(read_analytics_error)?,
        role: row.try_get("role").map_err(read_analytics_error)?,
        content: row.try_get("content").map_err(read_analytics_error)?,
        created_at: row
            .try_get::<Option<NaiveDateTime>, _>("created_at")
            .map_err(read_analytics_error)?
            .map(format_naive_iso),
        diagnosis_results: parse_optional_json(
            row.try_get::<Option<String>, _>("diagnosis_result")
                .map_err(read_analytics_error)?,
        ),
        reasoning_snapshot: row
            .try_get("reasoning_snapshot")
            .map_err(read_analytics_error)?,
        tool_calls_log: parse_optional_json(
            row.try_get::<Option<String>, _>("tool_calls_log")
                .map_err(read_analytics_error)?,
        ),
        is_complete: row
            .try_get::<Option<bool>, _>("is_complete")
            .map_err(read_analytics_error)?
            .unwrap_or(true),
    })
}

async fn load_ai_decision_records(
    state: &AppState,
    query: &AnalyticsQuery,
    start_date: Option<NaiveDate>,
    end_date: Option<NaiveDate>,
) -> Result<Vec<AiDecisionRecord>, AppError> {
    let rows = sqlx::query(
        r#"
        SELECT id, account_id, prompt_template_id, signal_trigger_id, operation, symbol,
               realized_pnl::float8 AS realized_pnl,
               hyperliquid_order_id, tp_order_id, sl_order_id, exchange
        FROM ai_decision_logs
        WHERE operation = ANY($1)
          AND executed = 'true'
          AND realized_pnl IS NOT NULL
          AND realized_pnl != 0
          AND ($2::timestamp IS NULL OR decision_time >= $2)
          AND ($3::timestamp IS NULL OR decision_time <= $3)
          AND ($4::text IS NULL OR hyperliquid_environment = $4)
          AND ($5::int4 IS NULL OR account_id = $5)
          AND (
                $6::text IS NULL OR
                ($6 = 'hyperliquid' AND (exchange = 'hyperliquid' OR exchange IS NULL)) OR
                ($6 != 'hyperliquid' AND exchange = $6)
          )
        "#,
    )
    .bind(vec!["buy", "sell", "close"])
    .bind(start_date.map(start_of_day))
    .bind(end_date.map(end_of_day))
    .bind(normalize_filter(&query.environment))
    .bind(query.account_id)
    .bind(normalize_filter(&query.exchange))
    .fetch_all(&state.db)
    .await
    .map_err(|error| {
        AppError::internal(format!("Failed to load AI decision analytics: {error}"))
    })?;

    let fee_map = load_fee_map_for_decisions(state, &rows).await;
    rows.into_iter()
        .map(|row| {
            let id = row.try_get::<i32, _>("id").map_err(read_analytics_error)?;
            let signal_trigger_id = row
                .try_get::<Option<i32>, _>("signal_trigger_id")
                .map_err(read_analytics_error)?;
            let operation = row
                .try_get::<String, _>("operation")
                .map_err(read_analytics_error)?;
            Ok(AiDecisionRecord {
                account_id: row.try_get("account_id").map_err(read_analytics_error)?,
                prompt_template_id: row
                    .try_get("prompt_template_id")
                    .map_err(read_analytics_error)?,
                signal_trigger_id,
                operation: operation.clone(),
                symbol: row.try_get("symbol").map_err(read_analytics_error)?,
                pnl: row
                    .try_get::<f64, _>("realized_pnl")
                    .map_err(read_analytics_error)?,
                fee: *fee_map.get(&id).unwrap_or(&0.0),
                trigger_type: if signal_trigger_id.is_some() {
                    "signal".to_owned()
                } else if matches!(operation.as_str(), "buy" | "sell" | "close") {
                    "scheduled".to_owned()
                } else {
                    "unknown".to_owned()
                },
            })
        })
        .collect()
}

async fn load_program_records(
    state: &AppState,
    query: &AnalyticsQuery,
    start_date: Option<NaiveDate>,
    end_date: Option<NaiveDate>,
) -> Result<Vec<ProgramRecord>, AppError> {
    let rows = sqlx::query(
        r#"
        SELECT id, account_id, program_id, program_name, signal_pool_id, decision_action, decision_symbol,
               trigger_type, realized_pnl::float8 AS realized_pnl,
               hyperliquid_order_id, tp_order_id, sl_order_id, exchange
        FROM program_execution_logs
        WHERE success = true
          AND decision_action = ANY($1)
          AND realized_pnl IS NOT NULL
          AND realized_pnl != 0
          AND ($2::timestamp IS NULL OR created_at >= $2)
          AND ($3::timestamp IS NULL OR created_at <= $3)
          AND ($4::int4 IS NULL OR account_id = $4)
          AND ($5::text IS NULL OR environment = $5)
          AND (
                $6::text IS NULL OR
                ($6 = 'hyperliquid' AND (exchange = 'hyperliquid' OR exchange IS NULL)) OR
                ($6 != 'hyperliquid' AND exchange = $6)
          )
        "#,
    )
    .bind(vec!["buy", "sell", "close"])
    .bind(start_date.map(start_of_day))
    .bind(end_date.map(end_of_day))
    .bind(query.account_id)
    .bind(normalize_filter(&query.environment))
    .bind(normalize_filter(&query.exchange))
    .fetch_all(&state.db)
    .await
    .map_err(|error| AppError::internal(format!("Failed to load program analytics: {error}")))?;

    let fee_map = load_fee_map_for_program_logs(state, &rows).await;
    rows.into_iter()
        .map(|row| {
            let id = row.try_get::<i32, _>("id").map_err(read_analytics_error)?;
            Ok(ProgramRecord {
                program_id: row.try_get("program_id").map_err(read_analytics_error)?,
                program_name: row.try_get("program_name").map_err(read_analytics_error)?,
                signal_pool_id: row
                    .try_get("signal_pool_id")
                    .map_err(read_analytics_error)?,
                decision_action: row
                    .try_get("decision_action")
                    .map_err(read_analytics_error)?,
                decision_symbol: row
                    .try_get("decision_symbol")
                    .map_err(read_analytics_error)?,
                pnl: row
                    .try_get::<f64, _>("realized_pnl")
                    .map_err(read_analytics_error)?,
                fee: *fee_map.get(&id).unwrap_or(&0.0),
                trigger_type: row
                    .try_get::<Option<String>, _>("trigger_type")
                    .map_err(read_analytics_error)?
                    .unwrap_or_else(|| "scheduled".to_owned()),
            })
        })
        .collect()
}

async fn load_fee_map_for_decisions(
    state: &AppState,
    rows: &[sqlx::postgres::PgRow],
) -> HashMap<i32, f64> {
    let mut order_ids = Vec::new();
    let mut decision_orders: HashMap<i32, Vec<String>> = HashMap::new();
    for row in rows {
        let id = match row.try_get::<i32, _>("id") {
            Ok(id) => id,
            Err(_) => continue,
        };
        let orders = ["hyperliquid_order_id", "tp_order_id", "sl_order_id"]
            .iter()
            .filter_map(|column| row.try_get::<Option<String>, _>(*column).ok().flatten())
            .collect::<Vec<_>>();
        order_ids.extend(orders.clone());
        decision_orders.insert(id, orders);
    }
    build_fee_map(state, &order_ids, decision_orders).await
}

async fn load_fee_map_for_program_logs(
    state: &AppState,
    rows: &[sqlx::postgres::PgRow],
) -> HashMap<i32, f64> {
    let mut order_ids = Vec::new();
    let mut log_orders: HashMap<i32, Vec<String>> = HashMap::new();
    for row in rows {
        let id = match row.try_get::<i32, _>("id") {
            Ok(id) => id,
            Err(_) => continue,
        };
        let orders = ["hyperliquid_order_id", "tp_order_id", "sl_order_id"]
            .iter()
            .filter_map(|column| row.try_get::<Option<String>, _>(*column).ok().flatten())
            .collect::<Vec<_>>();
        order_ids.extend(orders.clone());
        log_orders.insert(id, orders);
    }
    build_fee_map(state, &order_ids, log_orders).await
}

async fn build_fee_map(
    state: &AppState,
    order_ids: &[String],
    mapping: HashMap<i32, Vec<String>>,
) -> HashMap<i32, f64> {
    if order_ids.is_empty() {
        return mapping.keys().map(|id| (*id, 0.0)).collect();
    }

    let fee_lookup = match sqlx::query(
        r#"
        SELECT order_id, fee::float8 AS fee
        FROM hyperliquid_trades
        WHERE order_id = ANY($1)
        "#,
    )
    .bind(order_ids)
    .fetch_all(&state.snapshot_db)
    .await
    {
        Ok(rows) => rows
            .into_iter()
            .filter_map(|row| {
                Some((
                    row.try_get::<String, _>("order_id").ok()?,
                    row.try_get::<Option<f64>, _>("fee")
                        .ok()
                        .flatten()
                        .unwrap_or(0.0),
                ))
            })
            .collect::<HashMap<_, _>>(),
        Err(error) => {
            warn!(%error, "failed to fetch analytics fees from snapshot database");
            HashMap::new()
        }
    };

    mapping
        .into_iter()
        .map(|(id, orders)| {
            let total_fee = orders
                .iter()
                .map(|order| fee_lookup.get(order).copied().unwrap_or(0.0))
                .sum::<f64>();
            (id, total_fee)
        })
        .collect()
}

async fn load_prompt_template_names(
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
    .map_err(|error| {
        AppError::internal(format!("Failed to load prompt template names: {error}"))
    })?;
    rows.into_iter()
        .map(|row| {
            Ok((
                row.try_get::<i32, _>("id").map_err(read_analytics_error)?,
                row.try_get::<String, _>("name")
                    .map_err(read_analytics_error)?,
            ))
        })
        .collect()
}

async fn load_account_info(
    state: &AppState,
    ids: &[i32],
) -> Result<HashMap<i32, (String, Option<String>, Option<String>)>, AppError> {
    if ids.is_empty() {
        return Ok(HashMap::new());
    }
    let rows = sqlx::query(
        r#"
        SELECT id, name, model, hyperliquid_environment
        FROM accounts
        WHERE id = ANY($1)
          AND is_deleted IS DISTINCT FROM true
        "#,
    )
    .bind(ids)
    .fetch_all(&state.db)
    .await
    .map_err(|error| AppError::internal(format!("Failed to load account info: {error}")))?;
    rows.into_iter()
        .map(|row| {
            Ok((
                row.try_get::<i32, _>("id").map_err(read_analytics_error)?,
                (
                    row.try_get::<String, _>("name")
                        .map_err(read_analytics_error)?,
                    row.try_get::<Option<String>, _>("model")
                        .map_err(read_analytics_error)?,
                    row.try_get::<Option<String>, _>("hyperliquid_environment")
                        .map_err(read_analytics_error)?,
                ),
            ))
        })
        .collect()
}

fn group_ai_dimension<F, G>(
    records: Vec<AiDecisionRecord>,
    key_fn: F,
    extra_fn: G,
) -> DimensionResponse
where
    F: Fn(&AiDecisionRecord) -> Option<i32>,
    G: Fn(Option<i32>) -> Option<Value>,
{
    let mut by_key: HashMap<Option<i32>, Vec<AiDecisionRecord>> = HashMap::new();
    for record in records {
        by_key.entry(key_fn(&record)).or_default().push(record);
    }

    let unattributed = build_unattributed_ai(&by_key.get(&None).cloned().unwrap_or_default());
    let mut items = by_key
        .into_iter()
        .filter_map(|(key, grouped)| {
            let key_value = extra_fn(key)?;
            let metrics =
                calculate_metrics_from_pairs(grouped.iter().map(|r| (r.pnl, r.fee)).collect());
            let trigger = trigger_breakdown_by_kind_ai(&grouped);
            let mut item = key_value.as_object().cloned().unwrap_or_default();
            item.insert(
                "metrics".to_owned(),
                serde_json::to_value(metrics).unwrap_or(Value::Null),
            );
            item.insert(
                "by_trigger_type".to_owned(),
                serde_json::to_value(trigger).unwrap_or(Value::Null),
            );
            Some(Value::Object(item))
        })
        .collect::<Vec<_>>();
    items.sort_by(sort_by_net_pnl_desc);
    DimensionResponse {
        items,
        unattributed,
    }
}

fn group_ai_dimension_string<F, G>(
    records: Vec<AiDecisionRecord>,
    key_fn: F,
    extra_fn: G,
    allow_unattributed: bool,
) -> DimensionResponse
where
    F: Fn(&AiDecisionRecord) -> Option<String>,
    G: Fn(Option<String>) -> Option<Value>,
{
    let mut by_key: HashMap<Option<String>, Vec<AiDecisionRecord>> = HashMap::new();
    for record in records {
        by_key.entry(key_fn(&record)).or_default().push(record);
    }
    let unattributed_records = if allow_unattributed {
        by_key.get(&None).cloned().unwrap_or_default()
    } else {
        Vec::new()
    };
    let unattributed = build_unattributed_ai(&unattributed_records);
    let mut items = by_key
        .into_iter()
        .filter_map(|(key, grouped)| {
            let key_value = extra_fn(key.clone())?;
            if key.is_none() && allow_unattributed {
                return None;
            }
            let metrics =
                calculate_metrics_from_pairs(grouped.iter().map(|r| (r.pnl, r.fee)).collect());
            let trigger = trigger_breakdown_by_kind_ai(&grouped);
            let mut item = key_value.as_object().cloned().unwrap_or_default();
            item.insert(
                "metrics".to_owned(),
                serde_json::to_value(metrics).unwrap_or(Value::Null),
            );
            item.insert(
                "by_trigger_type".to_owned(),
                serde_json::to_value(trigger).unwrap_or(Value::Null),
            );
            Some(Value::Object(item))
        })
        .collect::<Vec<_>>();
    if allow_unattributed {
        items.sort_by(sort_by_net_pnl_desc);
    } else {
        items.sort_by(sort_by_trade_count_desc);
    }
    DimensionResponse {
        items,
        unattributed,
    }
}

fn group_program_dimension<F, G>(
    records: Vec<ProgramRecord>,
    key_fn: F,
    extra_fn: G,
) -> DimensionResponse
where
    F: Fn(&ProgramRecord) -> Option<i32>,
    G: Fn(Option<i32>, &ProgramRecord) -> Option<Value>,
{
    let mut by_key: HashMap<Option<i32>, Vec<ProgramRecord>> = HashMap::new();
    for record in records {
        by_key.entry(key_fn(&record)).or_default().push(record);
    }
    let unattributed_records = by_key.get(&None).cloned().unwrap_or_default();
    let unattributed = build_unattributed_program(&unattributed_records);
    let mut items = by_key
        .into_iter()
        .filter_map(|(key, grouped)| {
            let first = grouped.first()?;
            let key_value = extra_fn(key, first)?;
            if key.is_none() {
                return None;
            }
            let metrics =
                calculate_metrics_from_pairs(grouped.iter().map(|r| (r.pnl, r.fee)).collect());
            let trigger = trigger_breakdown_by_kind_program(&grouped);
            let mut item = key_value.as_object().cloned().unwrap_or_default();
            item.insert(
                "metrics".to_owned(),
                serde_json::to_value(metrics).unwrap_or(Value::Null),
            );
            item.insert(
                "by_trigger_type".to_owned(),
                serde_json::to_value(trigger).unwrap_or(Value::Null),
            );
            Some(Value::Object(item))
        })
        .collect::<Vec<_>>();
    items.sort_by(sort_by_net_pnl_desc);
    DimensionResponse {
        items,
        unattributed,
    }
}

fn group_program_dimension_string<F, G>(
    records: Vec<ProgramRecord>,
    key_fn: F,
    extra_fn: G,
    allow_unattributed: bool,
) -> DimensionResponse
where
    F: Fn(&ProgramRecord) -> Option<String>,
    G: Fn(Option<String>) -> Option<Value>,
{
    let mut by_key: HashMap<Option<String>, Vec<ProgramRecord>> = HashMap::new();
    for record in records {
        by_key.entry(key_fn(&record)).or_default().push(record);
    }
    let unattributed_records = if allow_unattributed {
        by_key.get(&None).cloned().unwrap_or_default()
    } else {
        Vec::new()
    };
    let unattributed = build_unattributed_program(&unattributed_records);
    let mut items = by_key
        .into_iter()
        .filter_map(|(key, grouped)| {
            let key_value = extra_fn(key.clone())?;
            if key.is_none() && allow_unattributed {
                return None;
            }
            let metrics =
                calculate_metrics_from_pairs(grouped.iter().map(|r| (r.pnl, r.fee)).collect());
            let trigger = trigger_breakdown_by_kind_program(&grouped);
            let mut item = key_value.as_object().cloned().unwrap_or_default();
            item.insert(
                "metrics".to_owned(),
                serde_json::to_value(metrics).unwrap_or(Value::Null),
            );
            item.insert(
                "by_trigger_type".to_owned(),
                serde_json::to_value(trigger).unwrap_or(Value::Null),
            );
            Some(Value::Object(item))
        })
        .collect::<Vec<_>>();
    if allow_unattributed {
        items.sort_by(sort_by_net_pnl_desc);
    } else {
        items.sort_by(sort_by_trade_count_desc);
    }
    DimensionResponse {
        items,
        unattributed,
    }
}

fn build_unattributed_ai(records: &[AiDecisionRecord]) -> UnattributedBlock {
    if records.is_empty() {
        UnattributedBlock {
            count: 0,
            metrics: None,
        }
    } else {
        UnattributedBlock {
            count: records.len(),
            metrics: Some(calculate_metrics_from_pairs(
                records.iter().map(|r| (r.pnl, r.fee)).collect(),
            )),
        }
    }
}

fn build_unattributed_program(records: &[ProgramRecord]) -> UnattributedBlock {
    if records.is_empty() {
        UnattributedBlock {
            count: 0,
            metrics: None,
        }
    } else {
        UnattributedBlock {
            count: records.len(),
            metrics: Some(calculate_metrics_from_pairs(
                records.iter().map(|r| (r.pnl, r.fee)).collect(),
            )),
        }
    }
}

fn trigger_breakdown_by_kind_ai(records: &[AiDecisionRecord]) -> HashMap<String, TriggerBreakdown> {
    let mut map = HashMap::new();
    for trigger in ["signal", "scheduled"] {
        map.insert(
            trigger.to_owned(),
            trigger_breakdown(
                records
                    .iter()
                    .filter(|r| r.trigger_type == trigger)
                    .map(|r| (r.pnl, r.fee))
                    .collect(),
            ),
        );
    }
    map
}

fn trigger_breakdown_by_kind_program(
    records: &[ProgramRecord],
) -> HashMap<String, TriggerBreakdown> {
    let mut map = HashMap::new();
    map.insert(
        "signal".to_owned(),
        trigger_breakdown(
            records
                .iter()
                .filter(|r| r.trigger_type == "signal")
                .map(|r| (r.pnl, r.fee))
                .collect(),
        ),
    );
    map.insert(
        "scheduled".to_owned(),
        trigger_breakdown(
            records
                .iter()
                .filter(|r| r.trigger_type != "signal")
                .map(|r| (r.pnl, r.fee))
                .collect(),
        ),
    );
    map
}

fn calculate_metrics_from_pairs(records: Vec<(f64, f64)>) -> Metrics {
    if records.is_empty() {
        return Metrics {
            total_pnl: 0.0,
            total_fee: 0.0,
            net_pnl: 0.0,
            trade_count: 0,
            win_count: 0,
            loss_count: 0,
            win_rate: 0.0,
            avg_win: None,
            avg_loss: None,
            profit_factor: None,
        };
    }

    let total_pnl = records.iter().map(|(pnl, _)| *pnl).sum::<f64>();
    let total_fee = records.iter().map(|(_, fee)| *fee).sum::<f64>();
    let net_pnl = total_pnl - total_fee;
    let wins = records
        .iter()
        .filter(|(pnl, _)| *pnl > 0.0)
        .map(|(pnl, _)| *pnl)
        .collect::<Vec<_>>();
    let losses = records
        .iter()
        .filter(|(pnl, _)| *pnl < 0.0)
        .map(|(pnl, _)| *pnl)
        .collect::<Vec<_>>();
    let trade_count = records.len();
    let win_count = wins.len();
    let loss_count = losses.len();
    let win_rate = if trade_count > 0 {
        win_count as f64 / trade_count as f64
    } else {
        0.0
    };
    let total_win = wins.iter().sum::<f64>();
    let total_loss = losses.iter().map(|loss| loss.abs()).sum::<f64>();
    let avg_win = if win_count > 0 {
        Some(round2(total_win / win_count as f64))
    } else {
        None
    };
    let avg_loss = if loss_count > 0 {
        Some(round2(-(total_loss / loss_count as f64)))
    } else {
        None
    };
    let profit_factor = if total_loss > 0.0 {
        Some(round2(total_win / total_loss))
    } else {
        None
    };

    Metrics {
        total_pnl: round2(total_pnl),
        total_fee: round2(total_fee),
        net_pnl: round2(net_pnl),
        trade_count,
        win_count,
        loss_count,
        win_rate: round4(win_rate),
        avg_win,
        avg_loss,
        profit_factor,
    }
}

fn trigger_breakdown(records: Vec<(f64, f64)>) -> TriggerBreakdown {
    TriggerBreakdown {
        count: records.len(),
        net_pnl: round2(records.iter().map(|(pnl, fee)| pnl - fee).sum::<f64>()),
    }
}

fn extract_factor_name_from_trigger_value(value: Value) -> Option<String> {
    value
        .get("signals_triggered")?
        .as_array()?
        .iter()
        .fold(None, |acc, item| {
            item.get("signal_name")
                .and_then(Value::as_str)
                .or_else(|| item.get("metric").and_then(Value::as_str))
                .map(|name| name.to_owned())
                .or(acc)
        })
}

fn normalize_filter(value: &str) -> Option<&str> {
    if value == "all" { None } else { Some(value) }
}

fn start_of_day(date: NaiveDate) -> NaiveDateTime {
    date.and_hms_opt(0, 0, 0).expect("valid start of day")
}

fn end_of_day(date: NaiveDate) -> NaiveDateTime {
    date.and_hms_opt(23, 59, 59).expect("valid end of day")
}

fn round2(value: f64) -> f64 {
    (value * 100.0).round() / 100.0
}

fn round4(value: f64) -> f64 {
    (value * 10_000.0).round() / 10_000.0
}

fn sort_by_net_pnl_desc(left: &Value, right: &Value) -> std::cmp::Ordering {
    let left_value = left["metrics"]["net_pnl"].as_f64().unwrap_or(0.0);
    let right_value = right["metrics"]["net_pnl"].as_f64().unwrap_or(0.0);
    right_value
        .partial_cmp(&left_value)
        .unwrap_or(std::cmp::Ordering::Equal)
}

fn sort_by_trade_count_desc(left: &Value, right: &Value) -> std::cmp::Ordering {
    right["metrics"]["trade_count"]
        .as_u64()
        .unwrap_or(0)
        .cmp(&left["metrics"]["trade_count"].as_u64().unwrap_or(0))
}

fn parse_optional_json(raw: Option<String>) -> Option<Value> {
    raw.and_then(|raw| serde_json::from_str::<Value>(&raw).ok())
}

fn parse_query_date(value: &Option<String>) -> Result<Option<NaiveDate>, AppError> {
    match value {
        Some(value) => NaiveDate::parse_from_str(value, "%Y-%m-%d")
            .map(Some)
            .map_err(|error| AppError::bad_request(format!("Invalid date `{value}`: {error}"))),
        None => Ok(None),
    }
}

fn default_all() -> String {
    "all".to_owned()
}

fn read_analytics_error(error: sqlx::Error) -> AppError {
    AppError::internal(format!("Failed to read analytics data: {error}"))
}

fn format_naive_iso(value: NaiveDateTime) -> String {
    value.format("%Y-%m-%dT%H:%M:%S%.f").to_string()
}

#[cfg(test)]
mod tests {
    use serde_json::json;

    use super::parse_optional_json;

    #[test]
    fn parses_optional_json_fields() {
        assert_eq!(
            parse_optional_json(Some("{\"ok\":true}".to_owned())),
            Some(json!({"ok": true}))
        );
        assert_eq!(parse_optional_json(Some("not-json".to_owned())), None);
        assert_eq!(parse_optional_json(None), None);
    }
}
