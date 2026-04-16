use axum::{
    Json,
    extract::{Path, Query, State},
    http::{HeaderMap, HeaderValue, Method, header},
    response::{
        IntoResponse, Response,
        sse::{Event, KeepAlive, Sse},
    },
};
use chrono::NaiveDateTime;
use futures_util::stream;
use regex::Regex;
use rustpython_parser::{Parse, ast};
use serde::de::DeserializeOwned;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use sqlx::Row;
use std::{
    collections::HashMap, convert::Infallible, path::PathBuf, process::Stdio, time::Instant,
};
use tokio::{
    io::{AsyncBufReadExt, AsyncReadExt, AsyncWriteExt, BufReader},
    process::Command,
    sync::mpsc,
    time::{Duration, timeout},
};

use crate::{
    error::AppError,
    proxy::{build_downstream_streaming_response, build_upstream_request},
    state::AppState,
};

#[derive(Serialize)]
pub struct ProgramResponse {
    id: i32,
    name: String,
    description: Option<String>,
    code: String,
    params: Option<Value>,
    icon: Option<String>,
    binding_count: i64,
    created_at: String,
    updated_at: String,
}

#[derive(Serialize)]
pub struct SignalPoolInfo {
    id: i32,
    pool_name: String,
    symbols: Vec<String>,
    enabled: bool,
    exchange: String,
    source_type: String,
}

#[derive(Serialize)]
pub struct AccountInfo {
    id: i32,
    name: String,
    model: Option<String>,
}

#[derive(Serialize)]
pub struct WalletInfo {
    environment: String,
    address: String,
}

#[derive(Serialize)]
pub struct BindingResponse {
    id: i32,
    account_id: i32,
    account_name: String,
    program_id: i32,
    program_name: String,
    signal_pool_ids: Vec<i32>,
    signal_pool_names: Vec<String>,
    trigger_interval: i32,
    scheduled_trigger_enabled: bool,
    is_active: bool,
    last_trigger_at: Option<String>,
    params_override: Option<Value>,
    exchange: String,
    wallets: Vec<WalletInfo>,
    created_at: String,
    updated_at: String,
}

#[derive(Deserialize)]
pub struct BindingListQuery {
    program_id: Option<i32>,
    account_id: Option<i32>,
}

#[derive(Deserialize)]
pub struct ProgramCreateRequest {
    name: String,
    description: Option<String>,
    code: String,
    params: Option<Value>,
    icon: Option<String>,
}

#[derive(Deserialize)]
pub struct ProgramUpdateRequest {
    name: Option<String>,
    description: Option<String>,
    code: Option<String>,
    params: Option<Value>,
    icon: Option<String>,
}

#[derive(Deserialize)]
pub struct ProgramValidationRequest {
    code: String,
}

#[derive(Deserialize, Serialize)]
pub struct AiProgramChatRequest {
    message: String,
    account_id: i32,
    conversation_id: Option<i32>,
    program_id: Option<i32>,
    #[serde(default = "default_true")]
    use_background_task: bool,
}

#[derive(Serialize)]
pub struct ProgramValidationResponse {
    is_valid: bool,
    errors: Vec<String>,
    warnings: Vec<String>,
}

#[derive(Deserialize)]
pub struct TestRunRequest {
    code: String,
    #[serde(default = "default_test_symbol")]
    symbol: String,
    #[serde(default = "default_test_period")]
    period: String,
}

#[derive(Deserialize, Serialize, Clone, Debug)]
pub struct ProgramBacktestRequest {
    binding_id: i32,
    start_time_ms: i64,
    end_time_ms: i64,
    #[serde(default = "default_backtest_initial_balance")]
    initial_balance: f64,
    #[serde(default = "default_backtest_slippage_percent")]
    slippage_percent: f64,
    #[serde(default = "default_backtest_fee_rate")]
    fee_rate: f64,
}

#[derive(Serialize, Deserialize, Default, PartialEq, Debug)]
pub struct ErrorLocation {
    file: Option<String>,
    line: Option<i32>,
    column: Option<i32>,
    function: Option<String>,
    code_context: Option<String>,
}

#[derive(Serialize, Deserialize, PartialEq, Debug)]
pub struct DecisionResult {
    action: String,
    symbol: Option<String>,
    size_usd: Option<f64>,
    leverage: Option<i32>,
    reason: Option<String>,
}

#[derive(Serialize, Deserialize, PartialEq, Debug)]
pub struct MarketDataSummary {
    symbol: String,
    current_price: Option<f64>,
    price_change_1h: Option<f64>,
    klines_count: i32,
    indicators_loaded: Vec<String>,
}

#[derive(Serialize, Deserialize, PartialEq, Debug)]
pub struct TestRunResponse {
    success: bool,
    decision: Option<DecisionResult>,
    execution_time_ms: f64,
    market_data: Option<MarketDataSummary>,
    error_type: Option<String>,
    error_message: Option<String>,
    error_traceback: Option<String>,
    error_location: Option<ErrorLocation>,
    suggestions: Vec<String>,
    available_apis: Option<Value>,
}

#[derive(Serialize, Deserialize, PartialEq, Debug)]
pub struct PreviewRunResponse {
    success: bool,
    error: Option<String>,
    input_data: Option<Value>,
    data_queries: Vec<Value>,
    execution_logs: Vec<String>,
    decision: Option<Value>,
    execution_time_ms: f64,
}

#[derive(Deserialize)]
pub struct BindingCreateRequest {
    program_id: i32,
    #[serde(default)]
    signal_pool_ids: Vec<i32>,
    #[serde(default = "default_trigger_interval")]
    trigger_interval: i32,
    #[serde(default)]
    scheduled_trigger_enabled: bool,
    #[serde(default = "default_true")]
    is_active: bool,
    params_override: Option<Value>,
    #[serde(default = "default_exchange")]
    exchange: String,
}

#[derive(Deserialize)]
pub struct BindingUpdateRequest {
    signal_pool_ids: Option<Vec<i32>>,
    trigger_interval: Option<i32>,
    scheduled_trigger_enabled: Option<bool>,
    is_active: Option<bool>,
    params_override: Option<Value>,
    exchange: Option<String>,
}

#[derive(Deserialize)]
pub struct DevGuideQuery {
    #[serde(default = "default_lang")]
    lang: String,
}

#[derive(Serialize)]
pub struct DevGuideResponse {
    content: String,
}

#[derive(Serialize)]
pub struct DeleteResult {
    success: bool,
    deleted: bool,
    #[serde(skip_serializing_if = "Option::is_none")]
    dependencies: Option<Vec<String>>,
    #[serde(skip_serializing_if = "Option::is_none")]
    message: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    entity: Option<Value>,
    #[serde(skip_serializing_if = "Option::is_none")]
    error: Option<String>,
}

pub async fn list_programs(
    State(state): State<AppState>,
) -> Result<Json<Vec<ProgramResponse>>, AppError> {
    let rows = sqlx::query(
        r#"
        SELECT
            p.id,
            p.name,
            p.description,
            p.code,
            p.params,
            p.icon,
            p.created_at,
            p.updated_at,
            COUNT(b.id) FILTER (WHERE b.is_deleted IS DISTINCT FROM true)::bigint AS binding_count
        FROM trading_programs p
        LEFT JOIN account_program_bindings b ON b.program_id = p.id
        WHERE p.user_id = (SELECT id FROM users WHERE username = 'default' LIMIT 1)
          AND p.is_deleted IS DISTINCT FROM true
        GROUP BY p.id
        ORDER BY p.updated_at DESC
        "#,
    )
    .fetch_all(&state.db)
    .await
    .map_err(|error| AppError::internal(format!("Failed to list programs: {error}")))?;

    let programs = rows
        .into_iter()
        .map(row_to_program)
        .collect::<Result<Vec<_>, _>>()?;

    Ok(Json(programs))
}

pub async fn get_program(
    State(state): State<AppState>,
    Path(program_id): Path<i32>,
) -> Result<Json<ProgramResponse>, AppError> {
    let Some(row) = sqlx::query(
        r#"
        SELECT
            p.id,
            p.name,
            p.description,
            p.code,
            p.params,
            p.icon,
            p.created_at,
            p.updated_at,
            COUNT(b.id) FILTER (WHERE b.is_deleted IS DISTINCT FROM true)::bigint AS binding_count
        FROM trading_programs p
        LEFT JOIN account_program_bindings b ON b.program_id = p.id
        WHERE p.id = $1
          AND p.user_id = (SELECT id FROM users WHERE username = 'default' LIMIT 1)
          AND p.is_deleted IS DISTINCT FROM true
        GROUP BY p.id
        "#,
    )
    .bind(program_id)
    .fetch_optional(&state.db)
    .await
    .map_err(|error| AppError::internal(format!("Failed to get program: {error}")))?
    else {
        return Err(AppError::not_found("Program not found"));
    };

    Ok(Json(row_to_program(row)?))
}

pub async fn create_program(
    State(state): State<AppState>,
    Json(payload): Json<ProgramCreateRequest>,
) -> Result<Json<ProgramResponse>, AppError> {
    ensure_program_code_valid(&payload.code)?;
    let user_id = ensure_default_user_id(&state).await?;

    let row = sqlx::query(
        r#"
        INSERT INTO trading_programs (
            user_id, name, description, code, params, icon, created_at, updated_at
        )
        VALUES ($1, $2, $3, $4, $5, $6, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        RETURNING id
        "#,
    )
    .bind(user_id)
    .bind(&payload.name)
    .bind(payload.description.as_deref())
    .bind(&payload.code)
    .bind(payload.params.as_ref().map(Value::to_string))
    .bind(payload.icon.as_deref())
    .fetch_one(&state.db)
    .await
    .map_err(|error| AppError::internal(format!("Failed to create program: {error}")))?;

    let program_id = row.try_get::<i32, _>("id").map_err(read_program_error)?;
    Ok(Json(load_program_by_id(&state, program_id).await?))
}

pub async fn update_program(
    State(state): State<AppState>,
    Path(program_id): Path<i32>,
    Json(payload): Json<ProgramUpdateRequest>,
) -> Result<Json<ProgramResponse>, AppError> {
    let current = load_program_row_by_id(&state, program_id)
        .await?
        .ok_or_else(|| AppError::not_found("Program not found"))?;

    if let Some(code) = payload.code.as_deref() {
        ensure_program_code_valid(code)?;
    }

    let name = payload
        .name
        .unwrap_or_else(|| current.try_get::<String, _>("name").unwrap_or_default());
    let description = if payload.description.is_some() {
        payload.description
    } else {
        current
            .try_get::<Option<String>, _>("description")
            .ok()
            .flatten()
    };
    let code = payload
        .code
        .unwrap_or_else(|| current.try_get::<String, _>("code").unwrap_or_default());
    let params = if payload.params.is_some() {
        payload.params
    } else {
        parse_optional_json(
            current
                .try_get::<Option<String>, _>("params")
                .ok()
                .flatten(),
        )
    };
    let icon = if payload.icon.is_some() {
        payload.icon
    } else {
        current.try_get::<Option<String>, _>("icon").ok().flatten()
    };

    let result = sqlx::query(
        r#"
        UPDATE trading_programs
        SET name = $2,
            description = $3,
            code = $4,
            params = $5,
            icon = $6,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = $1
          AND is_deleted IS DISTINCT FROM true
        "#,
    )
    .bind(program_id)
    .bind(&name)
    .bind(description.as_deref())
    .bind(&code)
    .bind(params.as_ref().map(Value::to_string))
    .bind(icon.as_deref())
    .execute(&state.db)
    .await
    .map_err(|error| AppError::internal(format!("Failed to update program: {error}")))?;

    if result.rows_affected() == 0 {
        return Err(AppError::not_found("Program not found"));
    }

    Ok(Json(load_program_by_id(&state, program_id).await?))
}

pub async fn validate_program_code(
    Json(payload): Json<ProgramValidationRequest>,
) -> Result<Json<ProgramValidationResponse>, AppError> {
    if payload.code.trim().is_empty() {
        return Err(AppError::bad_request("Code is required"));
    }

    let validation = run_program_code_validation(&payload.code);
    Ok(Json(ProgramValidationResponse {
        is_valid: validation.is_valid,
        errors: validation.errors,
        warnings: validation.warnings,
    }))
}

pub async fn chat_with_program_ai(
    State(state): State<AppState>,
    headers: HeaderMap,
    Json(payload): Json<AiProgramChatRequest>,
) -> Result<Response, AppError> {
    let request_body = serde_json::to_vec(&payload).map_err(|error| {
        AppError::internal(format!("Failed to encode ai-chat request: {error}"))
    })?;
    let target_url = state.config.legacy_http_target("/api/programs/ai-chat");
    let upstream_request = build_upstream_request(
        &state.client,
        Method::POST,
        &headers,
        target_url,
        request_body.into(),
    )?;
    let upstream_response = upstream_request.send().await.map_err(|error| {
        AppError::bad_gateway(format!("legacy program ai-chat request failed: {error}"))
    })?;

    build_downstream_streaming_response(upstream_response)
}

pub async fn test_run_program(
    Json(payload): Json<TestRunRequest>,
) -> Result<Json<TestRunResponse>, AppError> {
    let started_at = Instant::now();
    let validation = run_program_code_validation(&payload.code);
    if !validation.is_valid {
        return Ok(Json(build_validation_failure_response(
            &validation.errors,
            started_at.elapsed().as_secs_f64() * 1000.0,
        )));
    }

    let execution = match execute_test_run_sandbox(&payload).await {
        Ok(execution) => execution,
        Err(error) => {
            return Ok(Json(build_environment_failure_response(
                &error,
                started_at.elapsed().as_secs_f64() * 1000.0,
            )));
        }
    };

    let response = if execution.success {
        build_test_run_success_response(execution)
    } else {
        build_test_run_error_response(
            &execution
                .error
                .unwrap_or_else(|| "Unknown error".to_owned()),
            &payload.code,
            execution.execution_time_ms.unwrap_or_default(),
        )
    };

    Ok(Json(response))
}

pub async fn preview_run_binding(
    State(state): State<AppState>,
    Path(binding_id): Path<i32>,
) -> Result<Json<PreviewRunResponse>, AppError> {
    let started_at = Instant::now();
    let binding = load_preview_binding(&state, binding_id)
        .await?
        .ok_or_else(|| AppError::not_found("Binding not found"))?;
    let program = load_preview_program(&state, binding.program_id)
        .await?
        .ok_or_else(|| AppError::not_found("Program not found"))?;

    let validation = run_program_code_validation(&program.code);
    if !validation.is_valid {
        return Ok(Json(build_preview_failure_response(
            format!("Code validation failed: {}", validation.errors.join("; ")),
            None,
            Vec::new(),
            Vec::new(),
            started_at.elapsed().as_secs_f64() * 1000.0,
        )));
    }

    let environment = get_global_trading_mode(&state).await?;
    let Some(wallet) =
        load_preview_wallet(&state, binding.account_id, &binding.exchange, &environment).await?
    else {
        let error = if binding.exchange == "binance" {
            format!("Binance {environment} wallet not configured for this AI Trader")
        } else {
            format!("No active {environment} wallet found for this AI Trader")
        };
        return Ok(Json(build_preview_failure_response(
            error,
            None,
            Vec::new(),
            Vec::new(),
            started_at.elapsed().as_secs_f64() * 1000.0,
        )));
    };

    let signal_context = load_preview_signal_context(&state, &binding.signal_pool_ids).await?;
    let trigger_type = if binding.scheduled_trigger_enabled {
        "scheduled"
    } else {
        "signal"
    };
    let account_state = load_preview_account_state(
        &state,
        &binding,
        &wallet,
        &environment,
        &signal_context.trigger_symbol,
    )
    .await?;
    let input_data = build_preview_input_data(
        &binding,
        &wallet,
        &account_state,
        &signal_context,
        trigger_type,
        &environment,
    );

    let execution = match execute_preview_run_sandbox(&PreviewRunSandboxInput {
        mode: "preview_run",
        code: &program.code,
        symbol: &signal_context.trigger_symbol,
        params: binding.params_override.as_ref().unwrap_or(&Value::Null),
        input_data: &input_data,
    })
    .await
    {
        Ok(execution) => execution,
        Err(error) => {
            return Ok(Json(build_preview_failure_response(
                format!("Execution failed: {error}"),
                Some(input_data),
                Vec::new(),
                Vec::new(),
                started_at.elapsed().as_secs_f64() * 1000.0,
            )));
        }
    };

    let execution_time_ms = started_at.elapsed().as_secs_f64() * 1000.0;
    if execution.success {
        Ok(Json(PreviewRunResponse {
            success: true,
            error: None,
            input_data: Some(input_data),
            data_queries: execution.data_queries,
            execution_logs: execution.execution_logs,
            decision: execution.decision,
            execution_time_ms,
        }))
    } else {
        Ok(Json(build_preview_failure_response(
            execution
                .error
                .unwrap_or_else(|| "Unknown execution error".to_owned()),
            Some(input_data),
            execution.data_queries,
            execution.execution_logs,
            execution_time_ms,
        )))
    }
}

pub async fn run_program_backtest(
    State(state): State<AppState>,
    Json(mut payload): Json<ProgramBacktestRequest>,
) -> Result<Response, AppError> {
    let now_ms = chrono::Utc::now().timestamp_millis();
    if payload.end_time_ms > now_ms {
        payload.end_time_ms = now_ms;
    }

    if payload.end_time_ms <= payload.start_time_ms {
        return Err(AppError::bad_request("End time must be after start time"));
    }

    let binding_row = sqlx::query(
        r#"
        SELECT program_id
        FROM account_program_bindings
        WHERE id = $1
          AND is_deleted IS DISTINCT FROM true
        "#,
    )
    .bind(payload.binding_id)
    .fetch_optional(&state.db)
    .await
    .map_err(|error| AppError::internal(format!("Failed to load backtest binding: {error}")))?;

    let Some(binding_row) = binding_row else {
        return Err(AppError::not_found("Binding not found"));
    };

    let program_id = binding_row
        .try_get::<i32, _>("program_id")
        .map_err(read_program_error)?;

    let program_exists = sqlx::query(
        r#"
        SELECT id
        FROM trading_programs
        WHERE id = $1
          AND is_deleted IS DISTINCT FROM true
        "#,
    )
    .bind(program_id)
    .fetch_optional(&state.db)
    .await
    .map_err(|error| AppError::internal(format!("Failed to load backtest program: {error}")))?;

    if program_exists.is_none() {
        return Err(AppError::not_found("Program not found"));
    }

    let child = spawn_program_backtest_process(&state, &payload).await?;
    Ok(build_program_backtest_stream_response(child))
}

pub async fn delete_program(
    State(state): State<AppState>,
    Path(program_id): Path<i32>,
) -> Result<Json<DeleteResult>, AppError> {
    let program = load_program_row_by_id(&state, program_id)
        .await?
        .ok_or_else(|| AppError::not_found("Program not found"))?;

    let deps = load_program_dependencies(&state, program_id).await?;
    if !deps.is_empty() {
        return Ok(Json(DeleteResult {
            success: true,
            deleted: false,
            dependencies: Some(deps),
            message: Some("Cannot delete: program has bindings. Remove bindings first.".to_owned()),
            entity: None,
            error: None,
        }));
    }

    sqlx::query(
        r#"
        UPDATE trading_programs
        SET is_deleted = true,
            deleted_at = CURRENT_TIMESTAMP
        WHERE id = $1
        "#,
    )
    .bind(program_id)
    .execute(&state.db)
    .await
    .map_err(|error| AppError::internal(format!("Failed to delete program: {error}")))?;

    Ok(Json(DeleteResult {
        success: true,
        deleted: true,
        dependencies: None,
        message: None,
        entity: Some(serde_json::json!({
            "id": program_id,
            "name": program.try_get::<String, _>("name").map_err(read_program_error)?,
        })),
        error: None,
    }))
}

pub async fn get_program_dev_guide(
    Query(query): Query<DevGuideQuery>,
) -> Result<Json<DevGuideResponse>, AppError> {
    let filename = if query.lang == "zh" {
        "PROGRAM_DEV_GUIDE_ZH.md"
    } else {
        "PROGRAM_DEV_GUIDE.md"
    };
    let path = PathBuf::from("backend").join("config").join(filename);
    let content = std::fs::read_to_string(&path)
        .map_err(|_| AppError::not_found(format!("Documentation file not found: {filename}")))?;

    Ok(Json(DevGuideResponse { content }))
}

pub async fn list_signal_pools(
    State(state): State<AppState>,
) -> Result<Json<Vec<SignalPoolInfo>>, AppError> {
    let rows = sqlx::query(
        r#"
        SELECT id, pool_name, symbols, enabled, exchange, source_type
        FROM signal_pools
        WHERE enabled = true
          AND is_deleted IS DISTINCT FROM true
        ORDER BY pool_name
        "#,
    )
    .fetch_all(&state.db)
    .await
    .map_err(|error| AppError::internal(format!("Failed to list signal pools: {error}")))?;

    let pools = rows
        .into_iter()
        .map(|row| {
            Ok(SignalPoolInfo {
                id: row.try_get("id").map_err(read_program_error)?,
                pool_name: row.try_get("pool_name").map_err(read_program_error)?,
                symbols: parse_string_list(
                    row.try_get::<Option<String>, _>("symbols")
                        .map_err(read_program_error)?
                        .as_deref(),
                ),
                enabled: row
                    .try_get::<Option<bool>, _>("enabled")
                    .map_err(read_program_error)?
                    .unwrap_or(true),
                exchange: row
                    .try_get::<Option<String>, _>("exchange")
                    .map_err(read_program_error)?
                    .unwrap_or_else(|| "hyperliquid".to_owned()),
                source_type: row
                    .try_get::<Option<String>, _>("source_type")
                    .map_err(read_program_error)?
                    .unwrap_or_else(|| "market_signals".to_owned()),
            })
        })
        .collect::<Result<Vec<_>, AppError>>()?;

    Ok(Json(pools))
}

pub async fn list_program_accounts(
    State(state): State<AppState>,
) -> Result<Json<Vec<AccountInfo>>, AppError> {
    let rows = sqlx::query(
        r#"
        SELECT id, name, model
        FROM accounts
        WHERE is_active = 'true'
          AND account_type = 'AI'
          AND is_deleted IS DISTINCT FROM true
        ORDER BY name
        "#,
    )
    .fetch_all(&state.db)
    .await
    .map_err(|error| AppError::internal(format!("Failed to list program accounts: {error}")))?;

    let accounts = rows
        .into_iter()
        .map(|row| {
            Ok(AccountInfo {
                id: row.try_get("id").map_err(read_program_error)?,
                name: row.try_get("name").map_err(read_program_error)?,
                model: row.try_get("model").map_err(read_program_error)?,
            })
        })
        .collect::<Result<Vec<_>, AppError>>()?;

    Ok(Json(accounts))
}

pub async fn list_bindings(
    State(state): State<AppState>,
    Query(query): Query<BindingListQuery>,
) -> Result<Json<Vec<BindingResponse>>, AppError> {
    let rows = sqlx::query(
        r#"
        SELECT
            b.id,
            b.account_id,
            a.name AS account_name,
            b.program_id,
            p.name AS program_name,
            b.signal_pool_ids,
            b.trigger_interval,
            b.scheduled_trigger_enabled,
            b.is_active,
            b.last_trigger_at,
            b.params_override,
            b.exchange,
            b.created_at,
            b.updated_at
        FROM account_program_bindings b
        JOIN accounts a ON b.account_id = a.id
        JOIN trading_programs p ON b.program_id = p.id
        WHERE b.is_deleted IS DISTINCT FROM true
          AND ($1::int4 IS NULL OR b.program_id = $1)
          AND ($2::int4 IS NULL OR b.account_id = $2)
        ORDER BY b.created_at DESC
        "#,
    )
    .bind(query.program_id)
    .bind(query.account_id)
    .fetch_all(&state.db)
    .await
    .map_err(|error| AppError::internal(format!("Failed to list program bindings: {error}")))?;

    let environment = get_global_trading_mode(&state).await?;
    let mut bindings = Vec::new();
    for row in rows {
        bindings.push(row_to_binding(&state, row, &environment).await?);
    }

    Ok(Json(bindings))
}

pub async fn create_binding(
    State(state): State<AppState>,
    Query(query): Query<BindingListQuery>,
    Json(payload): Json<BindingCreateRequest>,
) -> Result<Json<BindingResponse>, AppError> {
    let account_id = query
        .account_id
        .ok_or_else(|| AppError::bad_request("account_id is required"))?;

    ensure_account_exists(&state, account_id).await?;
    ensure_program_exists(&state, payload.program_id).await?;
    ensure_binding_not_exists(&state, account_id, payload.program_id).await?;

    let row = sqlx::query(
        r#"
        INSERT INTO account_program_bindings (
            account_id, program_id, signal_pool_ids, trigger_interval,
            scheduled_trigger_enabled, is_active, params_override, exchange,
            created_at, updated_at
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        RETURNING id
        "#,
    )
    .bind(account_id)
    .bind(payload.program_id)
    .bind(if payload.signal_pool_ids.is_empty() {
        None
    } else {
        Some(serde_json::to_string(&payload.signal_pool_ids).map_err(json_program_err)?)
    })
    .bind(payload.trigger_interval)
    .bind(payload.scheduled_trigger_enabled)
    .bind(payload.is_active)
    .bind(payload.params_override.as_ref().map(Value::to_string))
    .bind(&payload.exchange)
    .fetch_one(&state.db)
    .await
    .map_err(|error| AppError::internal(format!("Failed to create binding: {error}")))?;

    let binding_id = row.try_get::<i32, _>("id").map_err(read_program_error)?;
    Ok(Json(load_binding_by_id(&state, binding_id).await?))
}

pub async fn update_binding(
    State(state): State<AppState>,
    Path(binding_id): Path<i32>,
    Json(payload): Json<BindingUpdateRequest>,
) -> Result<Json<BindingResponse>, AppError> {
    let current = load_binding_row(&state, binding_id)
        .await?
        .ok_or_else(|| AppError::not_found("Binding not found"))?;

    let signal_pool_ids = if payload.signal_pool_ids.is_some() {
        payload.signal_pool_ids
    } else {
        Some(parse_i32_list(
            current
                .try_get::<Option<String>, _>("signal_pool_ids")
                .ok()
                .flatten()
                .as_deref(),
        ))
    };
    let trigger_interval = payload
        .trigger_interval
        .unwrap_or_else(|| current.try_get::<i32, _>("trigger_interval").unwrap_or(300));
    let scheduled_trigger_enabled = payload.scheduled_trigger_enabled.unwrap_or_else(|| {
        current
            .try_get::<bool, _>("scheduled_trigger_enabled")
            .unwrap_or(false)
    });
    let is_active = payload
        .is_active
        .unwrap_or_else(|| current.try_get::<bool, _>("is_active").unwrap_or(true));
    let params_override = if payload.params_override.is_some() {
        payload.params_override
    } else {
        parse_optional_json(
            current
                .try_get::<Option<String>, _>("params_override")
                .ok()
                .flatten(),
        )
    };
    let exchange = payload.exchange.unwrap_or_else(|| {
        current
            .try_get::<String, _>("exchange")
            .unwrap_or_else(|_| "hyperliquid".to_owned())
    });

    let result = sqlx::query(
        r#"
        UPDATE account_program_bindings
        SET signal_pool_ids = $2,
            trigger_interval = $3,
            scheduled_trigger_enabled = $4,
            is_active = $5,
            params_override = $6,
            exchange = $7,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = $1
          AND is_deleted IS DISTINCT FROM true
        "#,
    )
    .bind(binding_id)
    .bind(
        signal_pool_ids
            .as_ref()
            .filter(|ids| !ids.is_empty())
            .map(|ids| serde_json::to_string(ids).unwrap_or_else(|_| "[]".to_owned())),
    )
    .bind(trigger_interval)
    .bind(scheduled_trigger_enabled)
    .bind(is_active)
    .bind(params_override.as_ref().map(Value::to_string))
    .bind(&exchange)
    .execute(&state.db)
    .await
    .map_err(|error| AppError::internal(format!("Failed to update binding: {error}")))?;

    if result.rows_affected() == 0 {
        return Err(AppError::not_found("Binding not found"));
    }

    Ok(Json(load_binding_by_id(&state, binding_id).await?))
}

pub async fn delete_binding(
    State(state): State<AppState>,
    Path(binding_id): Path<i32>,
) -> Result<Json<DeleteResult>, AppError> {
    let binding = load_binding_row(&state, binding_id)
        .await?
        .ok_or_else(|| AppError::not_found("Binding not found"))?;

    if binding
        .try_get::<bool, _>("is_active")
        .map_err(read_program_error)?
    {
        return Ok(Json(DeleteResult {
            success: true,
            deleted: false,
            dependencies: Some(vec![
                "Binding is currently active (is_active=True)".to_owned(),
            ]),
            message: Some("Cannot delete: binding is active. Deactivate it first.".to_owned()),
            entity: None,
            error: None,
        }));
    }

    sqlx::query(
        r#"
        UPDATE account_program_bindings
        SET is_deleted = true,
            deleted_at = CURRENT_TIMESTAMP
        WHERE id = $1
        "#,
    )
    .bind(binding_id)
    .execute(&state.db)
    .await
    .map_err(|error| AppError::internal(format!("Failed to delete binding: {error}")))?;

    Ok(Json(DeleteResult {
        success: true,
        deleted: true,
        dependencies: None,
        message: None,
        entity: Some(serde_json::json!({
            "id": binding_id,
            "account_id": binding.try_get::<i32, _>("account_id").map_err(read_program_error)?,
            "program_id": binding.try_get::<i32, _>("program_id").map_err(read_program_error)?,
        })),
        error: None,
    }))
}

struct PreviewBinding {
    id: i32,
    account_id: i32,
    program_id: i32,
    signal_pool_ids: Vec<i32>,
    scheduled_trigger_enabled: bool,
    params_override: Option<Value>,
    exchange: String,
    account_current_cash: f64,
    account_frozen_cash: f64,
}

struct PreviewProgram {
    code: String,
}

struct PreviewWallet {
    wallet_address: Option<String>,
    max_leverage: i32,
    default_leverage: i32,
}

struct PreviewAccountState {
    available_balance: f64,
    total_equity: f64,
    used_margin: f64,
    margin_usage_percent: f64,
    maintenance_margin: f64,
    positions: Value,
    open_orders: Vec<Value>,
    recent_trades: Vec<Value>,
    recent_trades_count: usize,
    current_price: Option<f64>,
}

struct PreviewSignalContext {
    trigger_symbol: String,
    signal_pool_name: String,
    pool_logic: String,
    signal_source_type: Option<String>,
}

async fn load_preview_binding(
    state: &AppState,
    binding_id: i32,
) -> Result<Option<PreviewBinding>, AppError> {
    let row = sqlx::query(
        r#"
        SELECT
            b.id,
            b.account_id,
            b.program_id,
            b.signal_pool_ids,
            b.scheduled_trigger_enabled,
            b.params_override,
            b.exchange,
            a.current_cash::float8 AS account_current_cash,
            a.frozen_cash::float8 AS account_frozen_cash
        FROM account_program_bindings b
        JOIN accounts a ON b.account_id = a.id
        WHERE b.id = $1
          AND b.is_deleted IS DISTINCT FROM true
        "#,
    )
    .bind(binding_id)
    .fetch_optional(&state.db)
    .await
    .map_err(|error| AppError::internal(format!("Failed to load binding: {error}")))?;

    row.map(|row| {
        Ok(PreviewBinding {
            id: row.try_get("id").map_err(read_program_error)?,
            account_id: row.try_get("account_id").map_err(read_program_error)?,
            program_id: row.try_get("program_id").map_err(read_program_error)?,
            signal_pool_ids: parse_i32_list(
                row.try_get::<Option<String>, _>("signal_pool_ids")
                    .map_err(read_program_error)?
                    .as_deref(),
            ),
            scheduled_trigger_enabled: row
                .try_get("scheduled_trigger_enabled")
                .map_err(read_program_error)?,
            params_override: parse_optional_json(
                row.try_get::<Option<String>, _>("params_override")
                    .map_err(read_program_error)?,
            ),
            exchange: row
                .try_get::<Option<String>, _>("exchange")
                .map_err(read_program_error)?
                .unwrap_or_else(|| "hyperliquid".to_owned()),
            account_current_cash: row
                .try_get("account_current_cash")
                .map_err(read_program_error)?,
            account_frozen_cash: row
                .try_get("account_frozen_cash")
                .map_err(read_program_error)?,
        })
    })
    .transpose()
}

async fn load_preview_program(
    state: &AppState,
    program_id: i32,
) -> Result<Option<PreviewProgram>, AppError> {
    let row = sqlx::query(
        r#"
        SELECT code
        FROM trading_programs
        WHERE id = $1
          AND is_deleted IS DISTINCT FROM true
        "#,
    )
    .bind(program_id)
    .fetch_optional(&state.db)
    .await
    .map_err(|error| AppError::internal(format!("Failed to load program: {error}")))?;

    row.map(|row| {
        Ok(PreviewProgram {
            code: row.try_get("code").map_err(read_program_error)?,
        })
    })
    .transpose()
}

async fn load_preview_wallet(
    state: &AppState,
    account_id: i32,
    exchange: &str,
    environment: &str,
) -> Result<Option<PreviewWallet>, AppError> {
    if exchange == "binance" {
        let row = sqlx::query(
            r#"
            SELECT max_leverage, default_leverage
            FROM binance_wallets
            WHERE account_id = $1
              AND environment = $2
              AND is_active = 'true'
              AND api_key_encrypted IS NOT NULL
            LIMIT 1
            "#,
        )
        .bind(account_id)
        .bind(environment)
        .fetch_optional(&state.db)
        .await
        .map_err(|error| AppError::internal(format!("Failed to load Binance wallet: {error}")))?;

        return row
            .map(|row| {
                Ok(PreviewWallet {
                    wallet_address: None,
                    max_leverage: row.try_get("max_leverage").map_err(read_program_error)?,
                    default_leverage: row
                        .try_get("default_leverage")
                        .map_err(read_program_error)?,
                })
            })
            .transpose();
    }

    let row = sqlx::query(
        r#"
        SELECT wallet_address, max_leverage, default_leverage
        FROM hyperliquid_wallets
        WHERE account_id = $1
          AND environment = $2
          AND is_active = 'true'
        LIMIT 1
        "#,
    )
    .bind(account_id)
    .bind(environment)
    .fetch_optional(&state.db)
    .await
    .map_err(|error| AppError::internal(format!("Failed to load Hyperliquid wallet: {error}")))?;

    row.map(|row| {
        Ok(PreviewWallet {
            wallet_address: row.try_get("wallet_address").map_err(read_program_error)?,
            max_leverage: row.try_get("max_leverage").map_err(read_program_error)?,
            default_leverage: row
                .try_get("default_leverage")
                .map_err(read_program_error)?,
        })
    })
    .transpose()
}

async fn load_preview_signal_context(
    state: &AppState,
    signal_pool_ids: &[i32],
) -> Result<PreviewSignalContext, AppError> {
    let Some(first_pool_id) = signal_pool_ids.first().copied() else {
        return Ok(PreviewSignalContext {
            trigger_symbol: "BTC".to_owned(),
            signal_pool_name: String::new(),
            pool_logic: "OR".to_owned(),
            signal_source_type: None,
        });
    };

    let row = sqlx::query(
        r#"
        SELECT pool_name, symbols, logic, source_type
        FROM signal_pools
        WHERE id = $1
          AND is_deleted IS DISTINCT FROM true
        "#,
    )
    .bind(first_pool_id)
    .fetch_optional(&state.db)
    .await
    .map_err(|error| AppError::internal(format!("Failed to load signal pool: {error}")))?;

    let Some(row) = row else {
        return Ok(PreviewSignalContext {
            trigger_symbol: "BTC".to_owned(),
            signal_pool_name: String::new(),
            pool_logic: "OR".to_owned(),
            signal_source_type: None,
        });
    };
    let symbols = parse_string_list(
        row.try_get::<Option<String>, _>("symbols")
            .map_err(read_program_error)?
            .as_deref(),
    );
    Ok(PreviewSignalContext {
        trigger_symbol: symbols
            .into_iter()
            .next()
            .unwrap_or_else(|| "BTC".to_owned()),
        signal_pool_name: row
            .try_get::<String, _>("pool_name")
            .map_err(read_program_error)?,
        pool_logic: row
            .try_get::<Option<String>, _>("logic")
            .map_err(read_program_error)?
            .unwrap_or_else(|| "OR".to_owned()),
        signal_source_type: row
            .try_get::<Option<String>, _>("source_type")
            .map_err(read_program_error)?,
    })
}

async fn load_preview_account_state(
    state: &AppState,
    binding: &PreviewBinding,
    wallet: &PreviewWallet,
    environment: &str,
    trigger_symbol: &str,
) -> Result<PreviewAccountState, AppError> {
    let (available_balance, total_equity, used_margin, maintenance_margin, positions) =
        if binding.exchange == "binance" {
            load_preview_binance_account_state(state, binding, environment).await?
        } else {
            load_preview_hyperliquid_account_state(state, binding, wallet, environment).await?
        };

    let open_orders = load_preview_open_orders(state, binding.account_id, environment).await?;
    let recent_trades = load_preview_recent_trades(state, binding.account_id, environment).await?;
    let margin_usage_percent = if total_equity > 0.0 {
        used_margin / total_equity * 100.0
    } else {
        0.0
    };
    let current_price =
        load_preview_current_price(state, &binding.exchange, environment, Some(trigger_symbol))
            .await?;

    Ok(PreviewAccountState {
        available_balance,
        total_equity,
        used_margin,
        margin_usage_percent,
        maintenance_margin,
        positions,
        open_orders,
        recent_trades_count: recent_trades.len(),
        recent_trades,
        current_price,
    })
}

async fn load_preview_hyperliquid_account_state(
    state: &AppState,
    binding: &PreviewBinding,
    wallet: &PreviewWallet,
    environment: &str,
) -> Result<(f64, f64, f64, f64, Value), AppError> {
    let snapshot = sqlx::query(
        r#"
        SELECT
            total_equity::float8 AS total_equity,
            available_balance::float8 AS available_balance,
            used_margin::float8 AS used_margin,
            maintenance_margin::float8 AS maintenance_margin
        FROM hyperliquid_account_snapshots
        WHERE account_id = $1
          AND environment = $2
        ORDER BY snapshot_time DESC, id DESC
        LIMIT 1
        "#,
    )
    .bind(binding.account_id)
    .bind(environment)
    .fetch_optional(&state.db)
    .await
    .map_err(|error| AppError::internal(format!("Failed to load account data: {error}")))?;

    let (available_balance, total_equity, used_margin, maintenance_margin) =
        if let Some(snapshot) = snapshot {
            (
                snapshot
                    .try_get("available_balance")
                    .map_err(read_program_error)?,
                snapshot
                    .try_get("total_equity")
                    .map_err(read_program_error)?,
                snapshot
                    .try_get("used_margin")
                    .map_err(read_program_error)?,
                snapshot
                    .try_get("maintenance_margin")
                    .map_err(read_program_error)?,
            )
        } else {
            (
                binding.account_current_cash,
                binding.account_current_cash,
                binding.account_frozen_cash,
                0.0,
            )
        };

    let positions = load_preview_hyperliquid_positions(
        state,
        binding.account_id,
        environment,
        wallet.wallet_address.as_deref(),
    )
    .await?;

    Ok((
        available_balance,
        total_equity,
        used_margin,
        maintenance_margin,
        positions,
    ))
}

async fn load_preview_binance_account_state(
    state: &AppState,
    binding: &PreviewBinding,
    environment: &str,
) -> Result<(f64, f64, f64, f64, Value), AppError> {
    let snapshot = sqlx::query(
        r#"
        SELECT
            total_margin_balance::float8 AS total_margin_balance,
            available_balance::float8 AS available_balance,
            total_initial_margin::float8 AS total_initial_margin,
            total_maint_margin::float8 AS total_maint_margin,
            snapshot_data
        FROM binance_account_snapshots
        WHERE account_id = $1
          AND environment = $2
        ORDER BY snapshot_time DESC, id DESC
        LIMIT 1
        "#,
    )
    .bind(binding.account_id)
    .bind(environment)
    .fetch_optional(&state.db)
    .await
    .map_err(|error| AppError::internal(format!("Failed to load account data: {error}")))?;

    let Some(snapshot) = snapshot else {
        return Ok((
            binding.account_current_cash,
            binding.account_current_cash,
            binding.account_frozen_cash,
            0.0,
            json!({}),
        ));
    };

    let snapshot_data = snapshot
        .try_get::<Option<String>, _>("snapshot_data")
        .map_err(read_program_error)?
        .unwrap_or_default();
    Ok((
        snapshot
            .try_get("available_balance")
            .map_err(read_program_error)?,
        snapshot
            .try_get("total_margin_balance")
            .map_err(read_program_error)?,
        snapshot
            .try_get::<Option<f64>, _>("total_initial_margin")
            .map_err(read_program_error)?
            .unwrap_or(0.0),
        snapshot
            .try_get::<Option<f64>, _>("total_maint_margin")
            .map_err(read_program_error)?
            .unwrap_or(0.0),
        extract_binance_positions_for_preview(&snapshot_data),
    ))
}

async fn load_preview_hyperliquid_positions(
    state: &AppState,
    account_id: i32,
    environment: &str,
    wallet_address: Option<&str>,
) -> Result<Value, AppError> {
    let latest_snapshot_time = sqlx::query_scalar::<_, Option<NaiveDateTime>>(
        r#"
        SELECT MAX(snapshot_time)
        FROM hyperliquid_positions
        WHERE account_id = $1
          AND environment = $2
          AND ($3::text IS NULL OR wallet_address = $3)
        "#,
    )
    .bind(account_id)
    .bind(environment)
    .bind(wallet_address)
    .fetch_one(&state.db)
    .await
    .map_err(|error| AppError::internal(format!("Failed to load positions: {error}")))?;

    let Some(snapshot_time) = latest_snapshot_time else {
        return Ok(json!({}));
    };

    let rows = sqlx::query(
        r#"
        SELECT
            symbol,
            position_size::float8 AS position_size,
            entry_price::float8 AS entry_price,
            unrealized_pnl::float8 AS unrealized_pnl,
            liquidation_price::float8 AS liquidation_price,
            leverage
        FROM hyperliquid_positions
        WHERE account_id = $1
          AND environment = $2
          AND snapshot_time = $3
          AND ($4::text IS NULL OR wallet_address = $4)
          AND position_size != 0
        ORDER BY symbol ASC
        "#,
    )
    .bind(account_id)
    .bind(environment)
    .bind(snapshot_time)
    .bind(wallet_address)
    .fetch_all(&state.db)
    .await
    .map_err(|error| AppError::internal(format!("Failed to load positions: {error}")))?;

    let mut positions = serde_json::Map::new();
    for row in rows {
        let symbol = row
            .try_get::<String, _>("symbol")
            .map_err(read_program_error)?;
        let size = row
            .try_get::<f64, _>("position_size")
            .map_err(read_program_error)?;
        positions.insert(
            symbol.clone(),
            json!({
                "symbol": symbol,
                "side": if size >= 0.0 { "long" } else { "short" },
                "size": size.abs(),
                "entry_price": row.try_get::<f64,_>("entry_price").map_err(read_program_error)?,
                "unrealized_pnl": row.try_get::<f64,_>("unrealized_pnl").map_err(read_program_error)?,
                "leverage": row.try_get::<i32,_>("leverage").map_err(read_program_error)?,
                "liquidation_price": row.try_get::<Option<f64>,_>("liquidation_price").map_err(read_program_error)?,
            }),
        );
    }

    Ok(Value::Object(positions))
}

async fn load_preview_open_orders(
    state: &AppState,
    account_id: i32,
    environment: &str,
) -> Result<Vec<Value>, AppError> {
    let rows = sqlx::query(
        r#"
        SELECT
            id,
            hyperliquid_order_id,
            symbol,
            side,
            order_type,
            quantity::float8 AS quantity,
            price::float8 AS price,
            reduce_only,
            created_at
        FROM orders
        WHERE account_id = $1
          AND COALESCE(hyperliquid_environment, $2) = $2
          AND lower(status) IN ('open', 'new', 'pending')
        ORDER BY created_at DESC
        LIMIT 20
        "#,
    )
    .bind(account_id)
    .bind(environment)
    .fetch_all(&state.db)
    .await
    .map_err(|error| AppError::internal(format!("Failed to load open orders: {error}")))?;

    rows.into_iter()
        .map(|row| {
            let order_id = row
                .try_get::<Option<String>, _>("hyperliquid_order_id")
                .map_err(read_program_error)?
                .and_then(|value| value.parse::<i64>().ok())
                .unwrap_or_else(|| row.try_get::<i32, _>("id").unwrap_or_default() as i64);
            let created_at = row
                .try_get::<Option<NaiveDateTime>, _>("created_at")
                .map_err(read_program_error)?;
            let side = row.try_get::<String, _>("side").map_err(read_program_error)?;
            Ok(json!({
                "order_id": order_id,
                "symbol": row.try_get::<String,_>("symbol").map_err(read_program_error)?,
                "side": side,
                "direction": side,
                "order_type": row.try_get::<String,_>("order_type").map_err(read_program_error)?,
                "size": row.try_get::<f64,_>("quantity").map_err(read_program_error)?,
                "price": row.try_get::<Option<f64>,_>("price").map_err(read_program_error)?.unwrap_or(0.0),
                "trigger_price": Value::Null,
                "reduce_only": row.try_get::<Option<String>,_>("reduce_only").map_err(read_program_error)?.as_deref() == Some("true"),
                "timestamp": created_at
                    .map(|value| value.and_utc().timestamp_millis())
                    .unwrap_or_default(),
            }))
        })
        .collect()
}

async fn load_preview_recent_trades(
    state: &AppState,
    account_id: i32,
    environment: &str,
) -> Result<Vec<Value>, AppError> {
    let rows = sqlx::query(
        r#"
        SELECT symbol, side, quantity::float8 AS quantity, price::float8 AS price, trade_time
        FROM trades
        WHERE account_id = $1
          AND COALESCE(hyperliquid_environment, $2) = $2
        ORDER BY trade_time DESC, id DESC
        LIMIT 5
        "#,
    )
    .bind(account_id)
    .bind(environment)
    .fetch_all(&state.db)
    .await
    .map_err(|error| AppError::internal(format!("Failed to load recent trades: {error}")))?;

    rows.into_iter()
        .map(|row| {
            let trade_time = row
                .try_get::<Option<NaiveDateTime>, _>("trade_time")
                .map_err(read_program_error)?;
            Ok(json!({
                "symbol": row.try_get::<String,_>("symbol").map_err(read_program_error)?,
                "side": row.try_get::<String,_>("side").map_err(read_program_error)?.to_lowercase(),
                "size": row.try_get::<f64,_>("quantity").map_err(read_program_error)?,
                "price": row.try_get::<f64,_>("price").map_err(read_program_error)?,
                "timestamp": trade_time.map(|value| value.and_utc().timestamp_millis()).unwrap_or_default(),
                "pnl": Value::Null,
                "close_time": trade_time.map(|value| value.and_utc().to_rfc3339()).unwrap_or_default(),
            }))
        })
        .collect()
}

async fn load_preview_current_price(
    state: &AppState,
    exchange: &str,
    environment: &str,
    symbol: Option<&str>,
) -> Result<Option<f64>, AppError> {
    let Some(symbol) = symbol else {
        return Ok(None);
    };

    sqlx::query_scalar::<_, Option<f64>>(
        r#"
        SELECT close_price::float8 AS close_price
        FROM crypto_klines
        WHERE exchange = $1
          AND environment = $2
          AND symbol = $3
        ORDER BY
            CASE period
                WHEN '1m' THEN 0
                WHEN '5m' THEN 1
                WHEN '15m' THEN 2
                WHEN '1h' THEN 3
                ELSE 4
            END,
            timestamp DESC
        LIMIT 1
        "#,
    )
    .bind(exchange)
    .bind(environment)
    .bind(symbol)
    .fetch_optional(&state.db)
    .await
    .map_err(|error| AppError::internal(format!("Failed to load current price: {error}")))
    .map(|value| value.flatten())
}

fn build_preview_input_data(
    binding: &PreviewBinding,
    wallet: &PreviewWallet,
    account_state: &PreviewAccountState,
    signal_context: &PreviewSignalContext,
    trigger_type: &str,
    environment: &str,
) -> Value {
    let positions_count = account_state
        .positions
        .as_object()
        .map(|positions| positions.len())
        .unwrap_or_default();
    let open_orders_count = account_state.open_orders.len();
    json!({
        "trigger_symbol": signal_context.trigger_symbol,
        "trigger_type": trigger_type,
        "environment": environment,
        "exchange": binding.exchange,
        "signal_pool_name": signal_context.signal_pool_name,
        "pool_logic": signal_context.pool_logic,
        "triggered_signals": [],
        "signal_source_type": signal_context.signal_source_type,
        "trigger_market_regime": Value::Null,
        "max_leverage": wallet.max_leverage,
        "default_leverage": wallet.default_leverage,
        "available_balance": account_state.available_balance,
        "total_equity": account_state.total_equity,
        "used_margin": account_state.used_margin,
        "margin_usage_percent": account_state.margin_usage_percent,
        "maintenance_margin": account_state.maintenance_margin,
        "positions": account_state.positions.clone(),
        "positions_count": positions_count,
        "open_orders": account_state.open_orders.clone(),
        "open_orders_count": open_orders_count,
        "recent_trades": account_state.recent_trades.clone(),
        "recent_trades_count": account_state.recent_trades_count,
        "current_price": account_state.current_price,
        "binding_id": binding.id,
        "wallet_address": wallet.wallet_address.clone(),
    })
}

fn extract_binance_positions_for_preview(snapshot_data: &str) -> Value {
    let Ok(value) = serde_json::from_str::<Value>(snapshot_data) else {
        return json!({});
    };
    let Some(positions) = value.get("positions").and_then(Value::as_array) else {
        return json!({});
    };

    let mut mapped = serde_json::Map::new();
    for position in positions {
        let symbol = position
            .get("symbol")
            .and_then(Value::as_str)
            .unwrap_or_default()
            .trim_end_matches("USDT")
            .to_owned();
        if symbol.is_empty() {
            continue;
        }
        let size = parse_json_number(position.get("positionAmt"))
            .or_else(|| parse_json_number(position.get("size")))
            .unwrap_or(0.0);
        if size == 0.0 {
            continue;
        }
        mapped.insert(
            symbol.clone(),
            json!({
                "symbol": symbol,
                "side": if size >= 0.0 { "long" } else { "short" },
                "size": size.abs(),
                "entry_price": parse_json_number(position.get("entryPrice")).unwrap_or(0.0),
                "unrealized_pnl": parse_json_number(position.get("unRealizedProfit")).unwrap_or(0.0),
                "leverage": parse_json_number(position.get("leverage")).unwrap_or(1.0) as i32,
                "liquidation_price": parse_json_number(position.get("liquidationPrice")).unwrap_or(0.0),
            }),
        );
    }

    Value::Object(mapped)
}

fn parse_json_number(value: Option<&Value>) -> Option<f64> {
    value.and_then(|value| match value {
        Value::Number(number) => number.as_f64(),
        Value::String(text) => text.parse::<f64>().ok(),
        _ => None,
    })
}

fn build_preview_failure_response(
    error: impl Into<String>,
    input_data: Option<Value>,
    data_queries: Vec<Value>,
    execution_logs: Vec<String>,
    execution_time_ms: f64,
) -> PreviewRunResponse {
    PreviewRunResponse {
        success: false,
        error: Some(error.into()),
        input_data,
        data_queries,
        execution_logs,
        decision: None,
        execution_time_ms,
    }
}

async fn row_to_binding(
    state: &AppState,
    row: sqlx::postgres::PgRow,
    environment: &str,
) -> Result<BindingResponse, AppError> {
    let account_id = row
        .try_get::<i32, _>("account_id")
        .map_err(read_program_error)?;
    let pool_ids = parse_i32_list(
        row.try_get::<Option<String>, _>("signal_pool_ids")
            .map_err(read_program_error)?
            .as_deref(),
    );
    let exchange = row
        .try_get::<Option<String>, _>("exchange")
        .map_err(read_program_error)?
        .unwrap_or_else(|| "hyperliquid".to_owned());
    let signal_pool_names = load_signal_pool_names(&state.db, &pool_ids).await?;
    let wallets = load_binding_wallets(&state.db, account_id, &exchange, environment).await?;

    Ok(BindingResponse {
        id: row.try_get("id").map_err(read_program_error)?,
        account_id,
        account_name: row.try_get("account_name").map_err(read_program_error)?,
        program_id: row.try_get("program_id").map_err(read_program_error)?,
        program_name: row.try_get("program_name").map_err(read_program_error)?,
        signal_pool_ids: pool_ids,
        signal_pool_names,
        trigger_interval: row
            .try_get("trigger_interval")
            .map_err(read_program_error)?,
        scheduled_trigger_enabled: row
            .try_get("scheduled_trigger_enabled")
            .map_err(read_program_error)?,
        is_active: row.try_get("is_active").map_err(read_program_error)?,
        last_trigger_at: row
            .try_get::<Option<NaiveDateTime>, _>("last_trigger_at")
            .map_err(read_program_error)?
            .map(format_naive_iso),
        params_override: parse_optional_json(
            row.try_get::<Option<String>, _>("params_override")
                .map_err(read_program_error)?,
        ),
        exchange,
        wallets,
        created_at: row
            .try_get::<Option<NaiveDateTime>, _>("created_at")
            .map_err(read_program_error)?
            .map(format_naive_iso)
            .unwrap_or_default(),
        updated_at: row
            .try_get::<Option<NaiveDateTime>, _>("updated_at")
            .map_err(read_program_error)?
            .map(format_naive_iso)
            .unwrap_or_default(),
    })
}

fn row_to_program(row: sqlx::postgres::PgRow) -> Result<ProgramResponse, AppError> {
    Ok(ProgramResponse {
        id: row.try_get("id").map_err(read_program_error)?,
        name: row.try_get("name").map_err(read_program_error)?,
        description: row.try_get("description").map_err(read_program_error)?,
        code: row.try_get("code").map_err(read_program_error)?,
        params: parse_optional_json(row.try_get("params").map_err(read_program_error)?),
        icon: row.try_get("icon").map_err(read_program_error)?,
        binding_count: row.try_get("binding_count").map_err(read_program_error)?,
        created_at: row
            .try_get::<Option<NaiveDateTime>, _>("created_at")
            .map_err(read_program_error)?
            .map(format_naive_iso)
            .unwrap_or_default(),
        updated_at: row
            .try_get::<Option<NaiveDateTime>, _>("updated_at")
            .map_err(read_program_error)?
            .map(format_naive_iso)
            .unwrap_or_default(),
    })
}

async fn load_program_by_id(
    state: &AppState,
    program_id: i32,
) -> Result<ProgramResponse, AppError> {
    let row = load_program_row_by_id(state, program_id)
        .await?
        .ok_or_else(|| AppError::not_found("Program not found"))?;
    row_to_program(row)
}

async fn load_program_row_by_id(
    state: &AppState,
    program_id: i32,
) -> Result<Option<sqlx::postgres::PgRow>, AppError> {
    let user_id = ensure_default_user_id(state).await?;
    sqlx::query(
        r#"
        SELECT
            p.id,
            p.name,
            p.description,
            p.code,
            p.params,
            p.icon,
            p.created_at,
            p.updated_at,
            COUNT(b.id) FILTER (WHERE b.is_deleted IS DISTINCT FROM true)::bigint AS binding_count
        FROM trading_programs p
        LEFT JOIN account_program_bindings b ON b.program_id = p.id
        WHERE p.id = $1
          AND p.user_id = $2
          AND p.is_deleted IS DISTINCT FROM true
        GROUP BY p.id
        "#,
    )
    .bind(program_id)
    .bind(user_id)
    .fetch_optional(&state.db)
    .await
    .map_err(|error| AppError::internal(format!("Failed to load program: {error}")))
}

async fn load_signal_pool_names(pool: &sqlx::PgPool, ids: &[i32]) -> Result<Vec<String>, AppError> {
    if ids.is_empty() {
        return Ok(Vec::new());
    }

    let rows = sqlx::query(
        r#"
        SELECT id, pool_name
        FROM signal_pools
        WHERE id = ANY($1)
          AND is_deleted IS DISTINCT FROM true
        "#,
    )
    .bind(ids)
    .fetch_all(pool)
    .await
    .map_err(|error| AppError::internal(format!("Failed to load signal pool names: {error}")))?;
    let map = rows
        .into_iter()
        .map(|row| {
            Ok((
                row.try_get::<i32, _>("id").map_err(read_program_error)?,
                row.try_get::<String, _>("pool_name")
                    .map_err(read_program_error)?,
            ))
        })
        .collect::<Result<HashMap<_, _>, AppError>>()?;

    Ok(ids
        .iter()
        .map(|id| {
            map.get(id)
                .cloned()
                .unwrap_or_else(|| format!("Pool #{id}"))
        })
        .collect())
}

async fn load_binding_wallets(
    pool: &sqlx::PgPool,
    account_id: i32,
    exchange: &str,
    environment: &str,
) -> Result<Vec<WalletInfo>, AppError> {
    if exchange == "binance" {
        let rows = sqlx::query(
            r#"
            SELECT environment
            FROM binance_wallets
            WHERE account_id = $1
              AND environment = $2
              AND is_active = 'true'
              AND api_key_encrypted IS NOT NULL
            "#,
        )
        .bind(account_id)
        .bind(environment)
        .fetch_all(pool)
        .await
        .map_err(|error| AppError::internal(format!("Failed to load Binance wallets: {error}")))?;

        return rows
            .into_iter()
            .map(|row| {
                Ok(WalletInfo {
                    environment: row.try_get("environment").map_err(read_program_error)?,
                    address: "****".to_owned(),
                })
            })
            .collect();
    }

    let rows = sqlx::query(
        r#"
        SELECT environment, wallet_address
        FROM hyperliquid_wallets
        WHERE account_id = $1
          AND environment = $2
          AND is_active = 'true'
          AND wallet_address IS NOT NULL
        "#,
    )
    .bind(account_id)
    .bind(environment)
    .fetch_all(pool)
    .await
    .map_err(|error| AppError::internal(format!("Failed to load Hyperliquid wallets: {error}")))?;

    rows.into_iter()
        .map(|row| {
            Ok(WalletInfo {
                environment: row.try_get("environment").map_err(read_program_error)?,
                address: row.try_get("wallet_address").map_err(read_program_error)?,
            })
        })
        .collect()
}

async fn get_global_trading_mode(state: &AppState) -> Result<String, AppError> {
    let value = sqlx::query_scalar::<_, Option<String>>(
        "SELECT value FROM system_configs WHERE key = 'hyperliquid_trading_mode' LIMIT 1",
    )
    .fetch_optional(&state.db)
    .await
    .map_err(|error| AppError::internal(format!("Failed to get trading mode: {error}")))?;

    Ok(match value.flatten().as_deref() {
        Some("mainnet") => "mainnet".to_owned(),
        _ => "testnet".to_owned(),
    })
}

async fn ensure_default_user_id(state: &AppState) -> Result<i32, AppError> {
    sqlx::query_scalar::<_, i32>(
        r#"
        INSERT INTO users (username, email, is_active, created_at, updated_at)
        VALUES ('default', 'default@local', 'true', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        ON CONFLICT (username)
        DO UPDATE SET updated_at = CURRENT_TIMESTAMP
        RETURNING id
        "#,
    )
    .fetch_one(&state.db)
    .await
    .map_err(|error| AppError::internal(format!("Failed to ensure default user: {error}")))
}

async fn ensure_account_exists(state: &AppState, account_id: i32) -> Result<(), AppError> {
    let exists = sqlx::query_scalar::<_, i64>(
        r#"
        SELECT COUNT(*)::bigint
        FROM accounts
        WHERE id = $1
          AND is_deleted IS DISTINCT FROM true
        "#,
    )
    .bind(account_id)
    .fetch_one(&state.db)
    .await
    .map_err(|error| AppError::internal(format!("Failed to load account: {error}")))?;

    if exists == 0 {
        Err(AppError::not_found("AI Trader not found"))
    } else {
        Ok(())
    }
}

async fn ensure_program_exists(state: &AppState, program_id: i32) -> Result<(), AppError> {
    if load_program_row_by_id(state, program_id).await?.is_none() {
        Err(AppError::not_found("Program not found"))
    } else {
        Ok(())
    }
}

async fn ensure_binding_not_exists(
    state: &AppState,
    account_id: i32,
    program_id: i32,
) -> Result<(), AppError> {
    let exists = sqlx::query_scalar::<_, i64>(
        r#"
        SELECT COUNT(*)::bigint
        FROM account_program_bindings
        WHERE account_id = $1
          AND program_id = $2
          AND is_deleted IS DISTINCT FROM true
        "#,
    )
    .bind(account_id)
    .bind(program_id)
    .fetch_one(&state.db)
    .await
    .map_err(|error| AppError::internal(format!("Failed to check binding: {error}")))?;

    if exists > 0 {
        Err(AppError::bad_request("Binding already exists"))
    } else {
        Ok(())
    }
}

async fn load_binding_by_id(
    state: &AppState,
    binding_id: i32,
) -> Result<BindingResponse, AppError> {
    let environment = get_global_trading_mode(state).await?;
    let row = load_binding_row(state, binding_id)
        .await?
        .ok_or_else(|| AppError::not_found("Binding not found"))?;
    row_to_binding(state, row, &environment).await
}

async fn load_binding_row(
    state: &AppState,
    binding_id: i32,
) -> Result<Option<sqlx::postgres::PgRow>, AppError> {
    sqlx::query(
        r#"
        SELECT
            b.id,
            b.account_id,
            a.name AS account_name,
            b.program_id,
            p.name AS program_name,
            b.signal_pool_ids,
            b.trigger_interval,
            b.scheduled_trigger_enabled,
            b.is_active,
            b.last_trigger_at,
            b.params_override,
            b.exchange,
            b.created_at,
            b.updated_at
        FROM account_program_bindings b
        JOIN accounts a ON b.account_id = a.id
        JOIN trading_programs p ON b.program_id = p.id
        WHERE b.id = $1
          AND b.is_deleted IS DISTINCT FROM true
        "#,
    )
    .bind(binding_id)
    .fetch_optional(&state.db)
    .await
    .map_err(|error| AppError::internal(format!("Failed to load binding: {error}")))
}

async fn load_program_dependencies(
    state: &AppState,
    program_id: i32,
) -> Result<Vec<String>, AppError> {
    let rows = sqlx::query(
        r#"
        SELECT b.id, b.is_active, a.name
        FROM account_program_bindings b
        LEFT JOIN accounts a ON a.id = b.account_id
        WHERE b.program_id = $1
          AND b.is_deleted IS DISTINCT FROM true
        "#,
    )
    .bind(program_id)
    .fetch_all(&state.db)
    .await
    .map_err(|error| AppError::internal(format!("Failed to load program dependencies: {error}")))?;

    rows.into_iter()
        .map(|row| {
            let name = row
                .try_get::<Option<String>, _>("name")
                .map_err(read_program_error)?
                .unwrap_or_else(|| "unknown".to_owned());
            let status = if row
                .try_get::<bool, _>("is_active")
                .map_err(read_program_error)?
            {
                "active"
            } else {
                "inactive"
            };
            Ok(format!(
                "Bound to Trader: {} (binding #{}, {})",
                name,
                row.try_get::<i32, _>("id").map_err(read_program_error)?,
                status
            ))
        })
        .collect()
}

const TEST_RUN_TIMEOUT_SECS: u64 = 5;
const TEST_RUN_SANDBOX_SCRIPT: &str = r#"
import json
import math
import sys
import time as pytime
import traceback
import types

SAFE_BUILTINS = {
    "__build_class__": __builtins__["__build_class__"] if isinstance(__builtins__, dict) else getattr(__builtins__, "__build_class__"),
    "__name__": "__main__",
    "abs": abs,
    "min": min,
    "max": max,
    "sum": sum,
    "len": len,
    "round": round,
    "int": int,
    "float": float,
    "str": str,
    "bool": bool,
    "list": list,
    "dict": dict,
    "tuple": tuple,
    "set": set,
    "range": range,
    "enumerate": enumerate,
    "zip": zip,
    "sorted": sorted,
    "reversed": reversed,
    "any": any,
    "all": all,
    "isinstance": isinstance,
    "type": type,
    "True": True,
    "False": False,
    "None": None,
}


class ActionType:
    BUY = "buy"
    SELL = "sell"
    CLOSE = "close"
    HOLD = "hold"


class RegimeInfo:
    def __init__(self, regime="noise", conf=0.0, direction="neutral", reason="", indicators=None):
        self.regime = regime
        self.conf = conf
        self.direction = direction
        self.reason = reason
        self.indicators = indicators or {}


class Position:
    def __init__(
        self,
        symbol,
        side="long",
        size=0.0,
        entry_price=0.0,
        unrealized_pnl=0.0,
        leverage=1,
        liquidation_price=0.0,
        opened_at=None,
        opened_at_str=None,
        holding_duration_seconds=None,
        holding_duration_str=None,
    ):
        self.symbol = symbol
        self.side = side
        self.size = size
        self.entry_price = entry_price
        self.unrealized_pnl = unrealized_pnl
        self.leverage = leverage
        self.liquidation_price = liquidation_price
        self.opened_at = opened_at
        self.opened_at_str = opened_at_str
        self.holding_duration_seconds = holding_duration_seconds
        self.holding_duration_str = holding_duration_str


class Trade:
    def __init__(
        self,
        symbol="",
        side="",
        size=0.0,
        price=0.0,
        timestamp=0,
        pnl=None,
        close_time="",
    ):
        self.symbol = symbol
        self.side = side
        self.size = size
        self.price = price
        self.timestamp = timestamp
        self.pnl = pnl
        self.close_time = close_time


class Order:
    def __init__(
        self,
        order_id=0,
        symbol="",
        side="",
        direction="",
        order_type="",
        size=0.0,
        price=0.0,
        trigger_price=None,
        reduce_only=False,
        timestamp=0,
    ):
        self.order_id = order_id
        self.symbol = symbol
        self.side = side
        self.direction = direction
        self.order_type = order_type
        self.size = size
        self.price = price
        self.trigger_price = trigger_price
        self.reduce_only = reduce_only
        self.timestamp = timestamp


class Decision:
    def __init__(
        self,
        operation,
        symbol,
        reason="",
        trading_strategy="",
        target_portion_of_balance=0.0,
        leverage=10,
        max_price=None,
        min_price=None,
        time_in_force="Ioc",
        take_profit_price=None,
        stop_loss_price=None,
        tp_execution="limit",
        sl_execution="limit",
    ):
        self.operation = operation
        self.symbol = symbol
        self.reason = reason
        self.trading_strategy = trading_strategy
        self.target_portion_of_balance = target_portion_of_balance
        self.leverage = leverage
        self.max_price = max_price
        self.min_price = min_price
        self.time_in_force = time_in_force
        self.take_profit_price = take_profit_price
        self.stop_loss_price = stop_loss_price
        self.tp_execution = tp_execution
        self.sl_execution = sl_execution


class MarketData:
    def __init__(
        self,
        available_balance=10000.0,
        total_equity=10000.0,
        used_margin=0.0,
        margin_usage_percent=0.0,
        maintenance_margin=0.0,
        positions=None,
        recent_trades=None,
        open_orders=None,
        trigger_symbol="BTC",
        trigger_type="manual_test",
        signal_pool_name="",
        pool_logic="OR",
        triggered_signals=None,
        signal_source_type=None,
        wallet_event=None,
        trigger_market_regime=None,
        environment="mainnet",
        max_leverage=10,
        default_leverage=3,
        current_price=None,
        _data_queries=None,
    ):
        self.available_balance = available_balance
        self.total_equity = total_equity
        self.used_margin = used_margin
        self.margin_usage_percent = margin_usage_percent
        self.maintenance_margin = maintenance_margin
        self.positions = {}
        for symbol, value in (positions or {}).items():
            if isinstance(value, Position):
                self.positions[symbol] = value
            else:
                position_data = dict(value)
                position_data.setdefault("symbol", symbol)
                self.positions[symbol] = Position(**position_data)
        self.recent_trades = [
            value if isinstance(value, Trade) else Trade(**value)
            for value in (recent_trades or [])
        ]
        self.open_orders = [
            value if isinstance(value, Order) else Order(**value)
            for value in (open_orders or [])
        ]
        self.trigger_symbol = trigger_symbol
        self.trigger_type = trigger_type
        self.signal_pool_name = signal_pool_name
        self.pool_logic = pool_logic
        self.triggered_signals = triggered_signals or []
        self.signal_source_type = signal_source_type
        self.wallet_event = wallet_event
        self.trigger_market_regime = trigger_market_regime
        self.environment = environment
        self.max_leverage = max_leverage
        self.default_leverage = default_leverage
        self.current_price = current_price
        self._data_queries = _data_queries if _data_queries is not None else []

    def _record_query(self, method, args, result):
        self._data_queries.append({"method": method, "args": args, "result": result})

    def get_price(self, symbol):
        result = self.current_price if symbol == self.trigger_symbol else 0.0
        self._record_query("get_price", {"symbol": symbol}, result)
        return result

    def get_price_change(self, symbol, period):
        result = {"change_percent": 0.0, "change_usd": 0.0}
        self._record_query("get_price_change", {"symbol": symbol, "period": period}, result)
        return result

    def get_klines(self, symbol, period, count=50):
        result = []
        self._record_query("get_klines", {"symbol": symbol, "period": period, "count": count}, {"count": 0})
        return result

    def get_indicator(self, symbol, indicator, period):
        result = {}
        self._record_query("get_indicator", {"symbol": symbol, "indicator": indicator, "period": period}, result)
        return result

    def get_flow(self, symbol, metric, period):
        result = {}
        self._record_query("get_flow", {"symbol": symbol, "metric": metric, "period": period}, result)
        return result

    def get_regime(self, symbol, period):
        result = RegimeInfo()
        self._record_query("get_regime", {"symbol": symbol, "period": period}, {
            "regime": result.regime,
            "conf": result.conf,
            "direction": result.direction,
        })
        return result

    def get_market_data(self, symbol):
        result = {
            "symbol": symbol,
            "price": self.current_price if symbol == self.trigger_symbol else None,
            "oracle_price": None,
            "change24h": None,
            "volume24h": None,
            "percentage24h": None,
            "open_interest": None,
            "funding_rate": None,
        }
        self._record_query("get_market_data", {"symbol": symbol}, result)
        return result

    def get_factor(self, symbol, factor_name, period="5m"):
        result = {"factor_name": factor_name, "symbol": symbol, "period": period, "value": None}
        self._record_query("get_factor", {"symbol": symbol, "factor_name": factor_name, "period": period}, result)
        return result

    def get_factor_ranking(self, symbol, top_n=10):
        result = []
        self._record_query("get_factor_ranking", {"symbol": symbol, "top_n": top_n}, result)
        return result


def main():
    request = json.load(sys.stdin)
    code = request["code"]
    symbol = request.get("symbol") or "BTC"
    mode = request.get("mode") or "test_run"
    params = request.get("params") or {}
    input_data = request.get("input_data") or {}
    sandbox_logs = []
    data_queries = []

    def sandbox_log(message):
        sandbox_logs.append(str(message))

    def sandbox_print(*args, **kwargs):
        sandbox_logs.append(" ".join(str(arg) for arg in args))

    restricted_globals = {
        "__builtins__": dict(SAFE_BUILTINS, print=sandbox_print),
        "math": types.SimpleNamespace(
            sqrt=math.sqrt,
            log=math.log,
            log10=math.log10,
            exp=math.exp,
            pow=math.pow,
            floor=math.floor,
            ceil=math.ceil,
            fabs=math.fabs,
        ),
        "time": types.SimpleNamespace(time=pytime.time),
        "MarketData": MarketData,
        "Decision": Decision,
        "ActionType": ActionType,
        "log": sandbox_log,
    }

    def find_strategy_class():
        for name, obj in restricted_globals.items():
            if isinstance(obj, type) and name not in ("MarketData", "Decision", "ActionType", "RegimeInfo", "Position", "Trade", "Order"):
                if hasattr(obj, "should_trade"):
                    return obj
        return None

    def preview_decision_to_dict(decision):
        return {
            "operation": getattr(decision, "operation", None),
            "symbol": getattr(decision, "symbol", None),
            "target_portion_of_balance": getattr(decision, "target_portion_of_balance", 0.0),
            "leverage": getattr(decision, "leverage", None),
            "max_price": getattr(decision, "max_price", None),
            "min_price": getattr(decision, "min_price", None),
            "time_in_force": getattr(decision, "time_in_force", "Ioc"),
            "take_profit_price": getattr(decision, "take_profit_price", None),
            "stop_loss_price": getattr(decision, "stop_loss_price", None),
            "tp_execution": getattr(decision, "tp_execution", "limit"),
            "sl_execution": getattr(decision, "sl_execution", "limit"),
            "reason": getattr(decision, "reason", None),
            "trading_strategy": getattr(decision, "trading_strategy", None),
        }

    started_at = pytime.time()
    try:
        exec(code, restricted_globals)

        strategy_class = find_strategy_class()
        if strategy_class is None:
            raise ValueError("No valid strategy class found in code")

        strategy = strategy_class()
        if hasattr(strategy, "init"):
            strategy.init(params if mode == "preview_run" else {})

        if mode == "preview_run":
            market_data = MarketData(
                available_balance=input_data.get("available_balance", 0.0),
                total_equity=input_data.get("total_equity", 0.0),
                used_margin=input_data.get("used_margin", 0.0),
                margin_usage_percent=input_data.get("margin_usage_percent", 0.0),
                maintenance_margin=input_data.get("maintenance_margin", 0.0),
                positions=input_data.get("positions") or {},
                recent_trades=input_data.get("recent_trades") or [],
                open_orders=input_data.get("open_orders") or [],
                trigger_symbol=input_data.get("trigger_symbol") or symbol,
                trigger_type=input_data.get("trigger_type") or "signal",
                signal_pool_name=input_data.get("signal_pool_name") or "",
                pool_logic=input_data.get("pool_logic") or "OR",
                triggered_signals=input_data.get("triggered_signals") or [],
                trigger_market_regime=input_data.get("trigger_market_regime"),
                environment=input_data.get("environment") or "mainnet",
                max_leverage=input_data.get("max_leverage") or 20,
                default_leverage=input_data.get("default_leverage") or 3,
                current_price=input_data.get("current_price"),
                _data_queries=data_queries,
            )
        else:
            market_data = MarketData(
                    available_balance=10000.0,
                    total_equity=10000.0,
                    trigger_symbol=symbol,
                    trigger_type="manual_test",
                    environment="mainnet",
            )

        decision = strategy.should_trade(market_data)

        if not isinstance(decision, Decision):
            raise ValueError(f"should_trade must return Decision, got {type(decision)}")

        if mode == "preview_run":
            print(
                json.dumps(
                    {
                        "success": True,
                        "decision": preview_decision_to_dict(decision),
                        "execution_time_ms": (pytime.time() - started_at) * 1000.0,
                        "execution_logs": sandbox_logs,
                        "data_queries": data_queries,
                    }
                )
            )
            return

        print(
            json.dumps(
                {
                    "success": True,
                    "decision": {
                        "action": decision.operation,
                        "symbol": getattr(decision, "symbol", None),
                        "size_usd": getattr(decision, "size_usd", None),
                        "leverage": getattr(decision, "leverage", None),
                        "reason": getattr(decision, "reason", None),
                    },
                    "execution_time_ms": (pytime.time() - started_at) * 1000.0,
                }
            )
        )
    except Exception as exc:
        if mode == "preview_run":
            print(
                json.dumps(
                    {
                        "success": False,
                        "error": f"Execution error: {exc}\n{traceback.format_exc()}",
                        "execution_time_ms": (pytime.time() - started_at) * 1000.0,
                        "execution_logs": sandbox_logs,
                        "data_queries": data_queries,
                    }
                )
            )
            return

        print(
            json.dumps(
                {
                    "success": False,
                    "error": f"Execution error: {exc}\n{traceback.format_exc()}",
                    "execution_time_ms": (pytime.time() - started_at) * 1000.0,
                }
            )
        )


if __name__ == "__main__":
    main()
"#;

const PROGRAM_BACKTEST_STREAM_SCRIPT: &str = r#"
import asyncio
import json
import os
import sys
import time
from pathlib import Path

repo_root = Path(os.environ.get("PROGRAM_BACKTEST_REPO_ROOT", ".")).resolve()
backend_path = repo_root / "backend"
if str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))

from backtest import BacktestConfig, ProgramBacktestEngine
from database.connection import SessionLocal
from database.models import AccountProgramBinding, BacktestResult, SignalPool, TradingProgram
from routes.program_routes import _run_backtest_with_progress


def emit(event):
    sys.stdout.write(f"data: {json.dumps(event)}\n\n")
    sys.stdout.flush()


async def main():
    request = json.load(sys.stdin)
    db = SessionLocal()
    backtest_record = None

    try:
        now_ms = int(time.time() * 1000)
        end_time_ms = min(request["end_time_ms"], now_ms)
        if end_time_ms <= request["start_time_ms"]:
            emit({"type": "error", "message": "End time must be after start time"})
            return

        binding = db.query(AccountProgramBinding).filter(
            AccountProgramBinding.id == request["binding_id"],
            AccountProgramBinding.is_deleted != True,
        ).first()
        if not binding:
            emit({"type": "error", "message": "Binding not found"})
            return

        program = db.query(TradingProgram).filter(
            TradingProgram.id == binding.program_id,
            TradingProgram.is_deleted != True,
        ).first()
        if not program:
            emit({"type": "error", "message": "Program not found"})
            return

        exchange = getattr(binding, "exchange", None) or "hyperliquid"
        signal_pool_ids = []
        symbols = set()

        if binding.signal_pool_ids:
            pool_ids = binding.signal_pool_ids
            if isinstance(pool_ids, str):
                pool_ids = json.loads(pool_ids)
            signal_pool_ids = pool_ids

            for pool_id in pool_ids:
                pool = db.query(SignalPool).filter(
                    SignalPool.id == pool_id,
                    SignalPool.is_deleted != True,
                ).first()
                if pool and pool.symbols:
                    pool_symbols = pool.symbols
                    if isinstance(pool_symbols, str):
                        pool_symbols = json.loads(pool_symbols)
                    for symbol in pool_symbols:
                        symbols.add(symbol)

        if not symbols:
            symbols = {"BTC"}

        scheduled_interval_sec = None
        if binding.scheduled_trigger_enabled and binding.trigger_interval:
            scheduled_interval_sec = binding.trigger_interval

        config = BacktestConfig(
            code=program.code,
            signal_pool_ids=signal_pool_ids,
            symbols=list(symbols),
            start_time_ms=request["start_time_ms"],
            end_time_ms=end_time_ms,
            scheduled_interval_sec=scheduled_interval_sec,
            initial_balance=request["initial_balance"],
            slippage_percent=request["slippage_percent"],
            fee_rate=request["fee_rate"],
            exchange=exchange,
        )

        engine = ProgramBacktestEngine(db)

        emit({"type": "calculating", "message": "Calculating trigger points..."})
        await asyncio.sleep(0.01)

        triggers = engine._generate_trigger_events(config)
        if not triggers and not config.scheduled_interval_sec:
            emit({
                "type": "error",
                "message": "No triggers generated. Add signal pools or enable scheduled trigger.",
            })
            return

        backtest_record = BacktestResult(
            backtest_type="program",
            binding_id=request["binding_id"],
            user_id=binding.account.user_id if binding.account else None,
            config=json.dumps({
                "signal_pool_ids": signal_pool_ids,
                "symbols": list(symbols),
                "scheduled_interval_sec": scheduled_interval_sec,
                "slippage_percent": request["slippage_percent"],
                "fee_rate": request["fee_rate"],
            }),
            start_time=config.start_time,
            end_time=config.end_time,
            initial_balance=config.initial_balance,
            total_triggers=len(triggers),
            status="running",
            exchange=exchange,
        )
        db.add(backtest_record)
        db.commit()
        db.refresh(backtest_record)

        emit({
            "type": "init",
            "total_triggers": engine.estimate_total_triggers(config, triggers),
            "backtest_id": backtest_record.id,
        })
        await asyncio.sleep(0.01)

        async for event in _run_backtest_with_progress(
            engine, config, triggers, db, backtest_record.id
        ):
            sys.stdout.write(event)
            sys.stdout.flush()

    except Exception as exc:
        if backtest_record:
            backtest_record.status = "error"
            backtest_record.error_message = str(exc)
            db.commit()
        emit({"type": "error", "message": str(exc)})
    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(main())
"#;

#[derive(Serialize)]
struct TestRunSandboxInput<'a> {
    code: &'a str,
    symbol: &'a str,
    period: &'a str,
}

#[derive(Serialize)]
struct PreviewRunSandboxInput<'a> {
    mode: &'a str,
    code: &'a str,
    symbol: &'a str,
    params: &'a Value,
    input_data: &'a Value,
}

#[derive(Deserialize)]
struct TestRunSandboxOutput {
    success: bool,
    #[serde(default)]
    decision: Option<DecisionResult>,
    #[serde(default)]
    error: Option<String>,
    #[serde(default)]
    execution_time_ms: Option<f64>,
}

#[derive(Deserialize)]
struct PreviewRunSandboxOutput {
    success: bool,
    #[serde(default)]
    decision: Option<Value>,
    #[serde(default)]
    error: Option<String>,
    #[serde(default)]
    execution_logs: Vec<String>,
    #[serde(default)]
    data_queries: Vec<Value>,
}

async fn execute_test_run_sandbox(
    request: &TestRunRequest,
) -> Result<TestRunSandboxOutput, String> {
    execute_program_sandbox(
        &TestRunSandboxInput {
            code: &request.code,
            symbol: &request.symbol,
            period: &request.period,
        },
        "test-run",
    )
    .await
}

async fn execute_preview_run_sandbox(
    request: &PreviewRunSandboxInput<'_>,
) -> Result<PreviewRunSandboxOutput, String> {
    execute_program_sandbox(request, "preview-run").await
}

async fn execute_program_sandbox<TInput, TOutput>(
    request: &TInput,
    operation_name: &str,
) -> Result<TOutput, String>
where
    TInput: Serialize + ?Sized,
    TOutput: DeserializeOwned,
{
    let python_command = std::env::var("PYTHON").unwrap_or_else(|_| "python".to_owned());
    let mut child = Command::new(&python_command)
        .arg("-c")
        .arg(TEST_RUN_SANDBOX_SCRIPT)
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .kill_on_drop(true)
        .spawn()
        .map_err(|error| format!("Failed to start {operation_name} sandbox: {error}"))?;

    let stdin_payload = serde_json::to_vec(request)
        .map_err(|error| format!("Failed to serialize {operation_name} request: {error}"))?;

    if let Some(mut stdin) = child.stdin.take() {
        stdin
            .write_all(&stdin_payload)
            .await
            .map_err(|error| format!("Failed to send {operation_name} payload: {error}"))?;
        stdin
            .shutdown()
            .await
            .map_err(|error| format!("Failed to finalize {operation_name} payload: {error}"))?;
    }

    let output = match timeout(
        Duration::from_secs(TEST_RUN_TIMEOUT_SECS),
        child.wait_with_output(),
    )
    .await
    {
        Ok(result) => result
            .map_err(|error| format!("Failed waiting for {operation_name} sandbox: {error}"))?,
        Err(_) => {
            return serde_json::from_value(json!({
                "success": false,
                "error": format!("Execution timed out after {TEST_RUN_TIMEOUT_SECS}s"),
                "execution_time_ms": (TEST_RUN_TIMEOUT_SECS as f64) * 1000.0,
            }))
            .map_err(|error| {
                format!("Failed to build {operation_name} timeout response: {error}")
            });
        }
    };

    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr).trim().to_owned();
        let message = if stderr.is_empty() {
            format!("{operation_name} sandbox exited unexpectedly")
        } else {
            format!("{operation_name} sandbox exited unexpectedly: {stderr}")
        };
        return Err(message);
    }

    let stdout = String::from_utf8_lossy(&output.stdout).trim().to_owned();
    serde_json::from_str::<TOutput>(&stdout).map_err(|error| {
        format!("Failed to decode {operation_name} sandbox response: {error}; stdout: {stdout}")
    })
}

async fn spawn_program_backtest_process(
    state: &AppState,
    request: &ProgramBacktestRequest,
) -> Result<tokio::process::Child, AppError> {
    spawn_program_backtest_process_with_script(state, request, PROGRAM_BACKTEST_STREAM_SCRIPT).await
}

async fn spawn_program_backtest_process_with_script(
    state: &AppState,
    request: &ProgramBacktestRequest,
    script: &str,
) -> Result<tokio::process::Child, AppError> {
    let python_command = std::env::var("PYTHON").unwrap_or_else(|_| "python".to_owned());
    let repo_root = workspace_root();
    let repo_root_string = repo_root.to_string_lossy().to_string();

    let mut child = Command::new(&python_command)
        .current_dir(&repo_root)
        .env("PROGRAM_BACKTEST_REPO_ROOT", &repo_root_string)
        .env("DATABASE_URL", &state.config.database_url)
        .env("SNAPSHOT_DATABASE_URL", &state.config.snapshot_database_url)
        .arg("-u")
        .arg("-c")
        .arg(script)
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .kill_on_drop(true)
        .spawn()
        .map_err(|error| {
            AppError::bad_gateway(format!("Failed to start backtest subprocess: {error}"))
        })?;

    let stdin_payload = serde_json::to_vec(request).map_err(|error| {
        AppError::internal(format!("Failed to encode backtest request: {error}"))
    })?;

    if let Some(mut stdin) = child.stdin.take() {
        stdin.write_all(&stdin_payload).await.map_err(|error| {
            AppError::bad_gateway(format!(
                "Failed to send backtest request to subprocess: {error}"
            ))
        })?;
        stdin.shutdown().await.map_err(|error| {
            AppError::bad_gateway(format!(
                "Failed to finalize backtest request payload: {error}"
            ))
        })?;
    }

    Ok(child)
}

fn build_program_backtest_stream_response(mut child: tokio::process::Child) -> Response {
    let stdout = child.stdout.take();
    let stderr = child.stderr.take();

    let (tx, rx) = mpsc::channel::<Result<Event, Infallible>>(32);

    tokio::spawn(async move {
        let Some(stdout) = stdout else {
            let _ = tx
                .send(Ok(Event::default().data(backtest_stream_error_payload(
                    "Backtest subprocess did not expose stdout",
                ))))
                .await;
            return;
        };

        let stderr_task = stderr.map(|stderr| {
            tokio::spawn(async move {
                let mut stderr_text = String::new();
                let mut stderr_reader = BufReader::new(stderr);
                let _ = stderr_reader.read_to_string(&mut stderr_text).await;
                stderr_text
            })
        });

        let mut emitted_payload = false;
        let mut stdout_lines = BufReader::new(stdout).lines();
        loop {
            match stdout_lines.next_line().await {
                Ok(Some(line)) => {
                    if let Some(data) = parse_backtest_stream_data_line(&line) {
                        emitted_payload = true;
                        if tx.send(Ok(Event::default().data(data))).await.is_err() {
                            return;
                        }
                    }
                }
                Ok(None) => break,
                Err(error) => {
                    let _ = tx
                        .send(Ok(Event::default().data(backtest_stream_error_payload(
                            &format!("Failed to read backtest stream: {error}"),
                        ))))
                        .await;
                    return;
                }
            }
        }

        let wait_result = child.wait().await;
        let stderr_output = match stderr_task {
            Some(task) => task.await.unwrap_or_default(),
            None => String::new(),
        };

        match wait_result {
            Ok(status) if status.success() => {
                if !emitted_payload {
                    let _ = tx
                        .send(Ok(Event::default().data(backtest_stream_error_payload(
                            "Backtest subprocess exited without emitting any events",
                        ))))
                        .await;
                }
            }
            Ok(_) => {
                let detail = stderr_output.trim();
                let message = if detail.is_empty() {
                    "Backtest subprocess exited unexpectedly".to_owned()
                } else {
                    format!("Backtest subprocess exited unexpectedly: {detail}")
                };
                let _ = tx
                    .send(Ok(
                        Event::default().data(backtest_stream_error_payload(&message))
                    ))
                    .await;
            }
            Err(error) => {
                let _ = tx
                    .send(Ok(Event::default().data(backtest_stream_error_payload(
                        &format!("Failed waiting for backtest subprocess: {error}"),
                    ))))
                    .await;
            }
        }
    });

    let stream = stream::unfold(rx, |mut rx| async {
        rx.recv().await.map(|item| (item, rx))
    });
    let sse = Sse::new(stream).keep_alive(KeepAlive::default());
    let mut response = sse.into_response();
    response
        .headers_mut()
        .insert(header::CACHE_CONTROL, HeaderValue::from_static("no-cache"));
    response.headers_mut().insert(
        header::HeaderName::from_static("x-accel-buffering"),
        HeaderValue::from_static("no"),
    );
    response
        .headers_mut()
        .insert(header::CONNECTION, HeaderValue::from_static("keep-alive"));
    response
}

fn parse_backtest_stream_data_line(line: &str) -> Option<String> {
    line.strip_prefix("data: ")
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .map(ToOwned::to_owned)
}

fn backtest_stream_error_payload(message: &str) -> String {
    json!({
        "type": "error",
        "message": message,
    })
    .to_string()
}

fn workspace_root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .unwrap_or_else(|| std::path::Path::new(env!("CARGO_MANIFEST_DIR")))
        .to_path_buf()
}

fn build_validation_failure_response(errors: &[String], execution_time_ms: f64) -> TestRunResponse {
    TestRunResponse {
        success: false,
        decision: None,
        execution_time_ms,
        market_data: None,
        error_type: Some("ValidationError".to_owned()),
        error_message: Some(format!("Code validation failed: {}", errors.join("; "))),
        error_traceback: None,
        error_location: None,
        suggestions: vec![
            "Ensure your code defines a class with should_trade(self, data: MarketData) method"
                .to_owned(),
            "The method must return a Decision object".to_owned(),
        ],
        available_apis: Some(get_test_run_available_apis()),
    }
}

fn build_environment_failure_response(error: &str, execution_time_ms: f64) -> TestRunResponse {
    TestRunResponse {
        success: false,
        decision: None,
        execution_time_ms,
        market_data: None,
        error_type: Some("DataError".to_owned()),
        error_message: Some(format!(
            "Failed to initialize execution environment: {error}"
        )),
        error_traceback: Some(error.to_owned()),
        error_location: None,
        suggestions: vec!["Check Python runtime availability".to_owned()],
        available_apis: Some(get_test_run_available_apis()),
    }
}

fn build_test_run_success_response(execution: TestRunSandboxOutput) -> TestRunResponse {
    TestRunResponse {
        success: true,
        decision: execution.decision,
        execution_time_ms: execution.execution_time_ms.unwrap_or_default(),
        market_data: None,
        error_type: None,
        error_message: None,
        error_traceback: None,
        error_location: None,
        suggestions: Vec::new(),
        available_apis: None,
    }
}

fn build_test_run_error_response(
    error: &str,
    code: &str,
    execution_time_ms: f64,
) -> TestRunResponse {
    let error_type = classify_test_run_error(error);
    let error_message = first_test_run_error_message(error);

    TestRunResponse {
        success: false,
        decision: None,
        execution_time_ms,
        market_data: None,
        error_type: Some(error_type.clone()),
        error_message: Some(error_message.clone()),
        error_traceback: Some(error.to_owned()),
        error_location: parse_test_run_error_location(error, code),
        suggestions: generate_test_run_suggestions(&error_type, &error_message),
        available_apis: Some(get_test_run_available_apis()),
    }
}

fn classify_test_run_error(error: &str) -> String {
    if error.contains("ImportError") {
        "ImportError".to_owned()
    } else if error.contains("SyntaxError") {
        "SyntaxError".to_owned()
    } else if error.contains("NameError") {
        "NameError".to_owned()
    } else if error.contains("AttributeError") {
        "AttributeError".to_owned()
    } else if error.contains("TypeError") {
        "TypeError".to_owned()
    } else if error.contains("KeyError") {
        "KeyError".to_owned()
    } else if error.to_lowercase().contains("timed out") {
        "TimeoutError".to_owned()
    } else if error.contains("Validation failed") {
        "ValidationError".to_owned()
    } else {
        "RuntimeError".to_owned()
    }
}

fn first_test_run_error_message(error: &str) -> String {
    let first_line = error.lines().next().unwrap_or(error).trim();
    if let Some((_, message)) = first_line.split_once(": ") {
        message.to_owned()
    } else {
        first_line.to_owned()
    }
}

fn parse_test_run_error_location(traceback_str: &str, code: &str) -> Option<ErrorLocation> {
    let line_regex =
        Regex::new(r#"File "<string>", line (\d+)"#).expect("test-run line regex should compile");
    let function_regex = Regex::new(r"in (\w+)\n").expect("test-run function regex should compile");

    let mut location = ErrorLocation::default();

    if let Some(line) = line_regex
        .captures_iter(traceback_str)
        .filter_map(|captures| {
            captures
                .get(1)
                .and_then(|value| value.as_str().parse::<i32>().ok())
        })
        .filter(|line| *line > 0 && (*line as usize) <= code.lines().count())
        .last()
    {
        location.file = Some("<string>".to_owned());
        location.line = Some(line);
        if let Some(context_line) = code.lines().nth((line - 1).max(0) as usize) {
            location.code_context = Some(context_line.trim().to_owned());
        }
    }

    if let Some(function_name) = function_regex
        .captures_iter(traceback_str)
        .filter_map(|captures| captures.get(1).map(|value| value.as_str().to_owned()))
        .last()
    {
        location.function = Some(function_name);
    }

    if location == ErrorLocation::default() {
        None
    } else {
        Some(location)
    }
}

fn generate_test_run_suggestions(error_type: &str, error_message: &str) -> Vec<String> {
    let mut suggestions = Vec::new();

    match error_type {
        "ImportError" => {
            suggestions.push("Check if the module/function name is spelled correctly".to_owned());
            if error_message.contains("calculate_indicator") {
                suggestions.push(
                    "Available indicator functions: get_indicator(symbol, indicator, period)"
                        .to_owned(),
                );
            }
            if error_message.contains("services") {
                suggestions
                    .push("Use MarketData methods instead of direct service imports".to_owned());
            }
        }
        "SyntaxError" => {
            suggestions
                .push("Check for missing colons, parentheses, or indentation errors".to_owned());
            suggestions.push("Ensure proper Python 3 syntax".to_owned());
        }
        "NameError" => {
            suggestions.push("Check if the variable/function is defined before use".to_owned());
            suggestions.push(
                "Available in sandbox: MarketData, Decision, ActionType, math functions".to_owned(),
            );
        }
        "AttributeError" => {
            suggestions.push("Check if the method/attribute exists on the object".to_owned());
            suggestions.push(
                "MarketData methods: get_price(), get_indicator(), get_klines(), get_flow()"
                    .to_owned(),
            );
        }
        "TypeError" => {
            suggestions
                .push("Check function arguments - wrong number or type of arguments".to_owned());
        }
        "KeyError" => {
            suggestions.push("Check if the dictionary key exists before accessing".to_owned());
            suggestions.push("Use .get(key, default) for safe dictionary access".to_owned());
        }
        "ValidationError" => {
            suggestions.push(
                "Ensure your class has a should_trade(self, data: MarketData) method".to_owned(),
            );
            suggestions.push("should_trade must return a Decision object".to_owned());
        }
        "TimeoutError" => {
            suggestions.push("Strategy execution took too long (>5 seconds)".to_owned());
            suggestions.push("Avoid infinite loops or expensive computations".to_owned());
        }
        _ => {}
    }

    suggestions
}

fn get_test_run_available_apis() -> Value {
    json!({
        "MarketData_properties": {
            "data.trigger_symbol": "Symbol that triggered this evaluation",
            "data.trigger_type": "Trigger type: 'signal' or 'scheduled'",
            "data.signal_source_type": "Optional signal source subtype: 'wallet_tracking' for Hyper Insight wallet signals, None for market signals",
            "data.wallet_event": "Optional wallet signal payload (dict). Present when signal_source_type='wallet_tracking'. Structure: {source, source_type, address, event_type, event_level, tier, summary, detail, event_timestamp}",
            "data.wallet_event.detail (position_change common)": "{action, direction, start_position, end_position, old_value, new_value, notional_value, entry_price, leverage, unrealized_pnl, liquidation_price}",
            "data.wallet_event.detail (realtime extras)": "{fills_count, total_size, average_price, closed_pnl, fills[]}",
            "data.wallet_event.detail (polling extras)": "{absolute_change, relative_change, current_position, previous_position, source_event_type}",
            "data.wallet_event.detail.action": "open, close, add, reduce, flip, update",
            "data.wallet_event.detail.direction": "long, short, flat",
            "data.available_balance": "Available balance in USD",
            "data.total_equity": "Total account equity",
            "data.positions": "Dict[str, Position] of current open positions",
        },
        "Position_fields": {
            "symbol": "Trading symbol",
            "side": "'long' or 'short'",
            "size": "Position size",
            "entry_price": "Entry price",
            "unrealized_pnl": "Unrealized PnL",
            "leverage": "Leverage used",
            "liquidation_price": "Liquidation price",
        },
        "MarketData_methods": {
            "get_market_data(symbol)": "Returns {symbol, price, oracle_price, change24h, volume24h, percentage24h, open_interest, funding_rate}",
            "get_indicator(symbol, indicator, period)": "Indicators: RSI14, RSI7, MA5, MA10, MA20, EMA20, EMA50, EMA100, MACD, BOLL, ATR14, VWAP, STOCH, OBV",
            "get_klines(symbol, period, count=50)": "Returns list of Kline(timestamp, open, high, low, close, volume)",
            "get_flow(symbol, metric, period)": "Metrics: CVD, OI, OI_DELTA, TAKER, FUNDING, DEPTH, IMBALANCE",
            "get_regime(symbol, period)": "Returns RegimeInfo(regime, conf, direction, reason, indicators)",
            "get_price_change(symbol, period)": "Returns {change_percent, change_usd}",
        },
        "Decision_fields": {
            "operation": "Required: 'buy', 'sell', 'hold', 'close'",
            "symbol": "Required: Trading symbol string",
            "target_portion_of_balance": "Required for buy/sell/close: 0.1-1.0",
            "leverage": "Required for buy/sell/close: 1-50 (default: 10)",
            "max_price": "Required for buy or close short: maximum entry price",
            "min_price": "Required for sell or close long: minimum entry price",
            "time_in_force": "Optional: 'Ioc', 'Gtc', 'Alo' (default: 'Ioc')",
            "take_profit_price": "Optional: TP trigger price",
            "stop_loss_price": "Optional: SL trigger price",
            "tp_execution": "Optional: 'market' or 'limit' (default: 'limit')",
            "sl_execution": "Optional: 'market' or 'limit' (default: 'limit')",
            "reason": "Optional: Explanation string",
            "trading_strategy": "Optional: Entry thesis, risk controls",
        },
        "operation_values": ["buy", "sell", "hold", "close"],
        "supported_periods": ["1m", "5m", "15m", "1h", "4h", "1d"],
        "math_functions": {
            "usage": "Call via math.xxx (e.g., math.pow(10, 2))",
            "functions": ["sqrt", "log", "log10", "exp", "pow", "floor", "ceil", "fabs"],
        },
        "available_builtins": ["abs", "min", "max", "sum", "len", "round", "int", "float", "str", "bool", "list", "dict", "range", "enumerate", "zip", "sorted", "any", "all"],
        "debug_function": "log(message) - Print debug output",
    })
}

const FORBIDDEN_IMPORTS: &[&str] = &[
    "os",
    "sys",
    "subprocess",
    "shutil",
    "pathlib",
    "socket",
    "requests",
    "urllib",
    "http",
    "pickle",
    "marshal",
    "shelve",
    "ctypes",
    "multiprocessing",
    "threading",
    "importlib",
    "builtins",
    "__builtins__",
];

const FORBIDDEN_FUNCTIONS: &[&str] = &[
    "eval",
    "exec",
    "compile",
    "open",
    "input",
    "__import__",
    "globals",
    "locals",
    "vars",
    "getattr",
    "setattr",
    "delattr",
    "hasattr",
    "breakpoint",
    "exit",
    "quit",
];

const MATH_IMPORT_GUIDANCE: &str =
    "Do not use import math. Use injected math.sqrt()/math.log()/math.exp() directly.";
const TIME_IMPORT_GUIDANCE: &str = "Do not use import time. Use injected time.time() directly.";

#[derive(Default)]
struct ProgramCodeValidation {
    is_valid: bool,
    errors: Vec<String>,
    warnings: Vec<String>,
}

#[derive(Default)]
struct StrategyTemplateSummary {
    has_should_trade: bool,
    should_trade_arg_count: Option<usize>,
    has_init: bool,
}

fn ensure_program_code_valid(code: &str) -> Result<(), AppError> {
    let validation = run_program_code_validation(code);
    if validation.is_valid {
        Ok(())
    } else {
        Err(AppError::bad_request(format!(
            "Invalid code: {}",
            validation.errors.join("; ")
        )))
    }
}

fn run_program_code_validation(code: &str) -> ProgramCodeValidation {
    if code.trim().is_empty() {
        return ProgramCodeValidation {
            is_valid: false,
            errors: vec!["Code is required".to_owned()],
            warnings: Vec::new(),
        };
    }

    let suite = match ast::Suite::parse(code, "<program>") {
        Ok(suite) => suite,
        Err(error) => {
            return ProgramCodeValidation {
                is_valid: false,
                errors: vec![normalize_parse_error(&error.to_string())],
                warnings: Vec::new(),
            };
        }
    };

    let mut errors = Vec::new();
    let mut warnings = Vec::new();

    for stmt in &suite {
        walk_stmt_for_security(stmt, &mut errors);
    }

    let mut strategy_classes = Vec::new();
    collect_strategy_templates(&suite, &mut strategy_classes);

    if strategy_classes.is_empty() {
        errors.push("No class definition found. Strategy must define a class.".to_owned());
    } else if let Some(strategy_class) = strategy_classes
        .into_iter()
        .find(|item| item.has_should_trade)
    {
        if strategy_class.should_trade_arg_count.unwrap_or_default() < 2 {
            errors.push("should_trade must accept 'data' parameter.".to_owned());
        }
        if !strategy_class.has_init {
            warnings.push("Consider adding 'init' method for parameter initialization.".to_owned());
        }
    } else {
        errors.push("Strategy class must have 'should_trade' method.".to_owned());
    }

    ProgramCodeValidation {
        is_valid: errors.is_empty(),
        errors,
        warnings,
    }
}

fn normalize_parse_error(raw: &str) -> String {
    raw.lines()
        .next()
        .map(str::trim)
        .filter(|line| !line.is_empty())
        .unwrap_or("Syntax error")
        .to_owned()
}

fn walk_stmt_for_security(stmt: &ast::Stmt, errors: &mut Vec<String>) {
    match stmt {
        ast::Stmt::Import(node) => {
            for alias in &node.names {
                record_import_error(&alias.name.to_string(), errors);
            }
        }
        ast::Stmt::ImportFrom(node) => {
            if let Some(module) = &node.module {
                record_import_error(&module.to_string(), errors);
            }
        }
        ast::Stmt::FunctionDef(node) => {
            for decorator in &node.decorator_list {
                walk_expr_for_security(decorator, errors);
            }
            for stmt in &node.body {
                walk_stmt_for_security(stmt, errors);
            }
        }
        ast::Stmt::AsyncFunctionDef(node) => {
            for decorator in &node.decorator_list {
                walk_expr_for_security(decorator, errors);
            }
            for stmt in &node.body {
                walk_stmt_for_security(stmt, errors);
            }
        }
        ast::Stmt::ClassDef(node) => {
            for base in &node.bases {
                walk_expr_for_security(base, errors);
            }
            for keyword in &node.keywords {
                walk_expr_for_security(&keyword.value, errors);
            }
            for decorator in &node.decorator_list {
                walk_expr_for_security(decorator, errors);
            }
            for stmt in &node.body {
                walk_stmt_for_security(stmt, errors);
            }
        }
        ast::Stmt::Return(node) => {
            if let Some(value) = &node.value {
                walk_expr_for_security(value, errors);
            }
        }
        ast::Stmt::Delete(node) => {
            for target in &node.targets {
                walk_expr_for_security(target, errors);
            }
        }
        ast::Stmt::Assign(node) => {
            for target in &node.targets {
                walk_expr_for_security(target, errors);
            }
            walk_expr_for_security(&node.value, errors);
        }
        ast::Stmt::AugAssign(node) => {
            walk_expr_for_security(&node.target, errors);
            walk_expr_for_security(&node.value, errors);
        }
        ast::Stmt::AnnAssign(node) => {
            walk_expr_for_security(&node.target, errors);
            walk_expr_for_security(&node.annotation, errors);
            if let Some(value) = &node.value {
                walk_expr_for_security(value, errors);
            }
        }
        ast::Stmt::For(node) => {
            walk_expr_for_security(&node.target, errors);
            walk_expr_for_security(&node.iter, errors);
            for stmt in &node.body {
                walk_stmt_for_security(stmt, errors);
            }
            for stmt in &node.orelse {
                walk_stmt_for_security(stmt, errors);
            }
        }
        ast::Stmt::AsyncFor(node) => {
            walk_expr_for_security(&node.target, errors);
            walk_expr_for_security(&node.iter, errors);
            for stmt in &node.body {
                walk_stmt_for_security(stmt, errors);
            }
            for stmt in &node.orelse {
                walk_stmt_for_security(stmt, errors);
            }
        }
        ast::Stmt::While(node) => {
            walk_expr_for_security(&node.test, errors);
            for stmt in &node.body {
                walk_stmt_for_security(stmt, errors);
            }
            for stmt in &node.orelse {
                walk_stmt_for_security(stmt, errors);
            }
        }
        ast::Stmt::If(node) => {
            walk_expr_for_security(&node.test, errors);
            for stmt in &node.body {
                walk_stmt_for_security(stmt, errors);
            }
            for stmt in &node.orelse {
                walk_stmt_for_security(stmt, errors);
            }
        }
        ast::Stmt::With(node) => {
            for item in &node.items {
                walk_expr_for_security(&item.context_expr, errors);
                if let Some(optional_vars) = &item.optional_vars {
                    walk_expr_for_security(optional_vars, errors);
                }
            }
            for stmt in &node.body {
                walk_stmt_for_security(stmt, errors);
            }
        }
        ast::Stmt::AsyncWith(node) => {
            for item in &node.items {
                walk_expr_for_security(&item.context_expr, errors);
                if let Some(optional_vars) = &item.optional_vars {
                    walk_expr_for_security(optional_vars, errors);
                }
            }
            for stmt in &node.body {
                walk_stmt_for_security(stmt, errors);
            }
        }
        ast::Stmt::Match(node) => {
            walk_expr_for_security(&node.subject, errors);
            for case in &node.cases {
                if let Some(guard) = &case.guard {
                    walk_expr_for_security(guard, errors);
                }
                for stmt in &case.body {
                    walk_stmt_for_security(stmt, errors);
                }
            }
        }
        ast::Stmt::Raise(node) => {
            if let Some(exc) = &node.exc {
                walk_expr_for_security(exc, errors);
            }
            if let Some(cause) = &node.cause {
                walk_expr_for_security(cause, errors);
            }
        }
        ast::Stmt::Try(node) => {
            for stmt in &node.body {
                walk_stmt_for_security(stmt, errors);
            }
            for handler in &node.handlers {
                let ast::ExceptHandler::ExceptHandler(handler) = handler;
                if let Some(typ) = &handler.type_ {
                    walk_expr_for_security(typ, errors);
                }
                for stmt in &handler.body {
                    walk_stmt_for_security(stmt, errors);
                }
            }
            for stmt in &node.orelse {
                walk_stmt_for_security(stmt, errors);
            }
            for stmt in &node.finalbody {
                walk_stmt_for_security(stmt, errors);
            }
        }
        ast::Stmt::TryStar(node) => {
            for stmt in &node.body {
                walk_stmt_for_security(stmt, errors);
            }
            for handler in &node.handlers {
                let ast::ExceptHandler::ExceptHandler(handler) = handler;
                if let Some(typ) = &handler.type_ {
                    walk_expr_for_security(typ, errors);
                }
                for stmt in &handler.body {
                    walk_stmt_for_security(stmt, errors);
                }
            }
            for stmt in &node.orelse {
                walk_stmt_for_security(stmt, errors);
            }
            for stmt in &node.finalbody {
                walk_stmt_for_security(stmt, errors);
            }
        }
        ast::Stmt::Assert(node) => {
            walk_expr_for_security(&node.test, errors);
            if let Some(msg) = &node.msg {
                walk_expr_for_security(msg, errors);
            }
        }
        ast::Stmt::Expr(node) => walk_expr_for_security(&node.value, errors),
        _ => {}
    }
}

fn walk_expr_for_security(expr: &ast::Expr, errors: &mut Vec<String>) {
    match expr {
        ast::Expr::BoolOp(node) => {
            for value in &node.values {
                walk_expr_for_security(value, errors);
            }
        }
        ast::Expr::NamedExpr(node) => {
            walk_expr_for_security(&node.target, errors);
            walk_expr_for_security(&node.value, errors);
        }
        ast::Expr::BinOp(node) => {
            walk_expr_for_security(&node.left, errors);
            walk_expr_for_security(&node.right, errors);
        }
        ast::Expr::UnaryOp(node) => walk_expr_for_security(&node.operand, errors),
        ast::Expr::Lambda(node) => walk_expr_for_security(&node.body, errors),
        ast::Expr::IfExp(node) => {
            walk_expr_for_security(&node.test, errors);
            walk_expr_for_security(&node.body, errors);
            walk_expr_for_security(&node.orelse, errors);
        }
        ast::Expr::Dict(node) => {
            for key in node.keys.iter().flatten() {
                walk_expr_for_security(key, errors);
            }
            for value in &node.values {
                walk_expr_for_security(value, errors);
            }
        }
        ast::Expr::Set(node) => {
            for value in &node.elts {
                walk_expr_for_security(value, errors);
            }
        }
        ast::Expr::ListComp(node) => {
            walk_expr_for_security(&node.elt, errors);
            walk_comprehensions_for_security(&node.generators, errors);
        }
        ast::Expr::SetComp(node) => {
            walk_expr_for_security(&node.elt, errors);
            walk_comprehensions_for_security(&node.generators, errors);
        }
        ast::Expr::DictComp(node) => {
            walk_expr_for_security(&node.key, errors);
            walk_expr_for_security(&node.value, errors);
            walk_comprehensions_for_security(&node.generators, errors);
        }
        ast::Expr::GeneratorExp(node) => {
            walk_expr_for_security(&node.elt, errors);
            walk_comprehensions_for_security(&node.generators, errors);
        }
        ast::Expr::Await(node) => walk_expr_for_security(&node.value, errors),
        ast::Expr::Yield(node) => {
            if let Some(value) = &node.value {
                walk_expr_for_security(value, errors);
            }
        }
        ast::Expr::YieldFrom(node) => walk_expr_for_security(&node.value, errors),
        ast::Expr::Compare(node) => {
            walk_expr_for_security(&node.left, errors);
            for comparator in &node.comparators {
                walk_expr_for_security(comparator, errors);
            }
        }
        ast::Expr::Call(node) => {
            if let Some(name) = extract_call_name(&node.func)
                && FORBIDDEN_FUNCTIONS.contains(&name.as_str())
            {
                errors.push(format!("Forbidden function: {name}()"));
            }
            walk_expr_for_security(&node.func, errors);
            for arg in &node.args {
                walk_expr_for_security(arg, errors);
            }
            for keyword in &node.keywords {
                walk_expr_for_security(&keyword.value, errors);
            }
        }
        ast::Expr::FormattedValue(node) => {
            walk_expr_for_security(&node.value, errors);
            if let Some(spec) = &node.format_spec {
                walk_expr_for_security(spec, errors);
            }
        }
        ast::Expr::JoinedStr(node) => {
            for value in &node.values {
                walk_expr_for_security(value, errors);
            }
        }
        ast::Expr::Attribute(node) => walk_expr_for_security(&node.value, errors),
        ast::Expr::Subscript(node) => {
            walk_expr_for_security(&node.value, errors);
            walk_expr_for_security(&node.slice, errors);
        }
        ast::Expr::Starred(node) => walk_expr_for_security(&node.value, errors),
        ast::Expr::List(node) => {
            for value in &node.elts {
                walk_expr_for_security(value, errors);
            }
        }
        ast::Expr::Tuple(node) => {
            for value in &node.elts {
                walk_expr_for_security(value, errors);
            }
        }
        ast::Expr::Slice(node) => {
            if let Some(lower) = &node.lower {
                walk_expr_for_security(lower, errors);
            }
            if let Some(upper) = &node.upper {
                walk_expr_for_security(upper, errors);
            }
            if let Some(step) = &node.step {
                walk_expr_for_security(step, errors);
            }
        }
        _ => {}
    }
}

fn walk_comprehensions_for_security(
    comprehensions: &[ast::Comprehension],
    errors: &mut Vec<String>,
) {
    for comprehension in comprehensions {
        walk_expr_for_security(&comprehension.target, errors);
        walk_expr_for_security(&comprehension.iter, errors);
        for condition in &comprehension.ifs {
            walk_expr_for_security(condition, errors);
        }
    }
}

fn extract_call_name(expr: &ast::Expr) -> Option<String> {
    match expr {
        ast::Expr::Name(node) => Some(node.id.to_string()),
        ast::Expr::Attribute(node) => Some(node.attr.to_string()),
        _ => None,
    }
}

fn record_import_error(module_name: &str, errors: &mut Vec<String>) {
    let root_module = module_name.split('.').next().unwrap_or(module_name);

    match root_module {
        "math" => errors.push(MATH_IMPORT_GUIDANCE.to_owned()),
        "time" => errors.push(TIME_IMPORT_GUIDANCE.to_owned()),
        _ if FORBIDDEN_IMPORTS.contains(&root_module) => {
            errors.push(format!("Forbidden import: {module_name}"));
        }
        _ => {}
    }
}

fn collect_strategy_templates(stmts: &[ast::Stmt], classes: &mut Vec<StrategyTemplateSummary>) {
    for stmt in stmts {
        match stmt {
            ast::Stmt::ClassDef(node) => {
                let mut summary = StrategyTemplateSummary::default();
                for body_stmt in &node.body {
                    match body_stmt {
                        ast::Stmt::FunctionDef(method) => {
                            update_strategy_template_summary(
                                &mut summary,
                                &method.name.to_string(),
                                method.args.args.len(),
                            );
                        }
                        ast::Stmt::AsyncFunctionDef(method) => {
                            update_strategy_template_summary(
                                &mut summary,
                                &method.name.to_string(),
                                method.args.args.len(),
                            );
                        }
                        _ => {}
                    }
                }
                classes.push(summary);
                collect_strategy_templates(&node.body, classes);
            }
            ast::Stmt::FunctionDef(node) => collect_strategy_templates(&node.body, classes),
            ast::Stmt::AsyncFunctionDef(node) => collect_strategy_templates(&node.body, classes),
            ast::Stmt::For(node) => {
                collect_strategy_templates(&node.body, classes);
                collect_strategy_templates(&node.orelse, classes);
            }
            ast::Stmt::AsyncFor(node) => {
                collect_strategy_templates(&node.body, classes);
                collect_strategy_templates(&node.orelse, classes);
            }
            ast::Stmt::While(node) => {
                collect_strategy_templates(&node.body, classes);
                collect_strategy_templates(&node.orelse, classes);
            }
            ast::Stmt::If(node) => {
                collect_strategy_templates(&node.body, classes);
                collect_strategy_templates(&node.orelse, classes);
            }
            ast::Stmt::With(node) => collect_strategy_templates(&node.body, classes),
            ast::Stmt::AsyncWith(node) => collect_strategy_templates(&node.body, classes),
            ast::Stmt::Try(node) => {
                collect_strategy_templates(&node.body, classes);
                collect_strategy_templates(&node.orelse, classes);
                collect_strategy_templates(&node.finalbody, classes);
                for handler in &node.handlers {
                    let ast::ExceptHandler::ExceptHandler(handler) = handler;
                    collect_strategy_templates(&handler.body, classes);
                }
            }
            ast::Stmt::TryStar(node) => {
                collect_strategy_templates(&node.body, classes);
                collect_strategy_templates(&node.orelse, classes);
                collect_strategy_templates(&node.finalbody, classes);
                for handler in &node.handlers {
                    let ast::ExceptHandler::ExceptHandler(handler) = handler;
                    collect_strategy_templates(&handler.body, classes);
                }
            }
            ast::Stmt::Match(node) => {
                for case in &node.cases {
                    collect_strategy_templates(&case.body, classes);
                }
            }
            _ => {}
        }
    }
}

fn update_strategy_template_summary(
    summary: &mut StrategyTemplateSummary,
    name: &str,
    arg_count: usize,
) {
    if name == "should_trade" {
        summary.has_should_trade = true;
        summary.should_trade_arg_count = Some(arg_count);
    }

    if name == "init" || name == "__init__" {
        summary.has_init = true;
    }
}

fn parse_optional_json(raw: Option<String>) -> Option<Value> {
    raw.and_then(|raw| serde_json::from_str::<Value>(&raw).ok())
}

fn parse_i32_list(raw: Option<&str>) -> Vec<i32> {
    let Some(raw) = raw else {
        return Vec::new();
    };
    serde_json::from_str::<Vec<i32>>(raw).unwrap_or_default()
}

fn parse_string_list(raw: Option<&str>) -> Vec<String> {
    let Some(raw) = raw else {
        return Vec::new();
    };
    serde_json::from_str::<Vec<String>>(raw).unwrap_or_default()
}

fn json_program_err(error: serde_json::Error) -> AppError {
    AppError::internal(format!("Failed to serialize program payload: {error}"))
}

fn read_program_error(error: sqlx::Error) -> AppError {
    AppError::internal(format!("Failed to read program data: {error}"))
}

fn format_naive_iso(value: NaiveDateTime) -> String {
    value.format("%Y-%m-%dT%H:%M:%S%.f").to_string()
}

fn default_lang() -> String {
    "en".to_owned()
}

fn default_test_symbol() -> String {
    "BTC".to_owned()
}

fn default_test_period() -> String {
    "1h".to_owned()
}

fn default_backtest_initial_balance() -> f64 {
    10000.0
}

fn default_backtest_slippage_percent() -> f64 {
    0.05
}

fn default_backtest_fee_rate() -> f64 {
    0.035
}

fn default_trigger_interval() -> i32 {
    300
}

fn default_true() -> bool {
    true
}

fn default_exchange() -> String {
    "hyperliquid".to_owned()
}

#[cfg(test)]
mod tests {
    use axum::{body::to_bytes, http::header};
    use serde_json::json;

    use super::{
        MATH_IMPORT_GUIDANCE, PreviewRunSandboxInput, ProgramBacktestRequest, TIME_IMPORT_GUIDANCE,
        build_preview_failure_response, build_program_backtest_stream_response,
        build_test_run_error_response, build_validation_failure_response,
        default_backtest_fee_rate, default_backtest_initial_balance,
        default_backtest_slippage_percent, default_exchange, default_trigger_interval,
        ensure_program_code_valid, execute_preview_run_sandbox,
        extract_binance_positions_for_preview, parse_backtest_stream_data_line, parse_i32_list,
        parse_json_number, parse_optional_json, parse_string_list, run_program_code_validation,
        spawn_program_backtest_process_with_script,
    };
    use crate::{config::AppConfig, state::AppState};

    const VALID_STRATEGY_CODE: &str = r#"
class MomentumStrategy:
    def __init__(self):
        self.window = 14

    def should_trade(self, data):
        return "hold"
"#;

    #[test]
    fn parses_program_json_fields() {
        assert_eq!(parse_i32_list(Some("[1,2]")), vec![1, 2]);
        assert_eq!(
            parse_string_list(Some(r#"["BTC","ETH"]"#)),
            vec!["BTC", "ETH"]
        );
        assert_eq!(
            parse_optional_json(Some("{\"x\":1}".to_owned())),
            Some(json!({"x": 1}))
        );
    }

    #[test]
    fn default_binding_values_match_legacy_routes() {
        assert_eq!(default_trigger_interval(), 300);
        assert_eq!(default_exchange(), "hyperliquid");
        assert_eq!(default_backtest_initial_balance(), 10000.0);
        assert_eq!(default_backtest_slippage_percent(), 0.05);
        assert_eq!(default_backtest_fee_rate(), 0.035);
    }

    #[test]
    fn valid_code_passes_program_validation() {
        let validation = run_program_code_validation(VALID_STRATEGY_CODE);

        assert!(validation.is_valid);
        assert!(validation.errors.is_empty());
        assert!(validation.warnings.is_empty());
    }

    #[test]
    fn syntax_error_fails_program_validation() {
        let validation = run_program_code_validation(
            r#"
class BrokenStrategy:
    def should_trade(self, data)
        return "hold"
"#,
        );

        assert!(!validation.is_valid);
        assert!(!validation.errors.is_empty());
    }

    #[test]
    fn forbidden_import_fails_program_validation() {
        let validation = run_program_code_validation(&format!("import os\n{VALID_STRATEGY_CODE}"));

        assert!(!validation.is_valid);
        assert!(
            validation
                .errors
                .iter()
                .any(|error| error == "Forbidden import: os")
        );
    }

    #[test]
    fn math_import_returns_guidance_error() {
        let validation =
            run_program_code_validation(&format!("import math\n{VALID_STRATEGY_CODE}"));

        assert!(!validation.is_valid);
        assert!(
            validation
                .errors
                .iter()
                .any(|error| error == MATH_IMPORT_GUIDANCE)
        );
    }

    #[test]
    fn time_import_returns_guidance_error() {
        let validation =
            run_program_code_validation(&format!("import time\n{VALID_STRATEGY_CODE}"));

        assert!(!validation.is_valid);
        assert!(
            validation
                .errors
                .iter()
                .any(|error| error == TIME_IMPORT_GUIDANCE)
        );
    }

    #[test]
    fn missing_should_trade_fails_program_validation() {
        let validation = run_program_code_validation(
            r#"
class MissingShouldTrade:
    def __init__(self):
        self.enabled = True
"#,
        );

        assert!(!validation.is_valid);
        assert!(
            validation
                .errors
                .iter()
                .any(|error| error == "Strategy class must have 'should_trade' method.")
        );
    }

    #[test]
    fn invalid_code_helper_keeps_create_update_error_message_clear() {
        let error = ensure_program_code_valid(&format!("import os\n{VALID_STRATEGY_CODE}"))
            .expect_err("invalid program code should be rejected");

        assert_eq!(error.status.as_u16(), 400);
        assert_eq!(error.message, "Invalid code: Forbidden import: os");
    }

    #[test]
    fn validation_failure_response_matches_legacy_contract_shape() {
        let response =
            build_validation_failure_response(&["Forbidden import: os".to_owned()], 12.5);

        assert!(!response.success);
        assert_eq!(response.error_type.as_deref(), Some("ValidationError"));
        assert_eq!(
            response.error_message.as_deref(),
            Some("Code validation failed: Forbidden import: os")
        );
        assert_eq!(response.suggestions.len(), 2);
        assert!(response.available_apis.is_some());
    }

    #[test]
    fn execution_failure_response_extracts_location_and_suggestions() {
        let code = "class BrokenStrategy:\n    def should_trade(self, data):\n        return missing_name\n";
        let traceback = "Execution error: name 'missing_name' is not defined\nTraceback (most recent call last):\n  File \"<string>\", line 3, in should_trade\nNameError: name 'missing_name' is not defined\n";
        let response = build_test_run_error_response(traceback, code, 7.0);

        assert!(!response.success);
        assert_eq!(response.error_type.as_deref(), Some("NameError"));
        assert_eq!(
            response.error_message.as_deref(),
            Some("name 'missing_name' is not defined")
        );
        assert_eq!(
            response.error_location.as_ref().and_then(|item| item.line),
            Some(3)
        );
        assert_eq!(
            response
                .error_location
                .as_ref()
                .and_then(|item| item.code_context.as_deref()),
            Some("return missing_name")
        );
        assert!(
            response
                .suggestions
                .iter()
                .any(|item| item == "Check if the variable/function is defined before use")
        );
    }

    #[test]
    fn preview_failure_response_matches_legacy_contract_shape() {
        let response = build_preview_failure_response(
            "No active testnet wallet found for this AI Trader",
            None,
            Vec::new(),
            Vec::new(),
            3.5,
        );

        assert!(!response.success);
        assert_eq!(
            response.error.as_deref(),
            Some("No active testnet wallet found for this AI Trader")
        );
        assert!(response.input_data.is_none());
        assert!(response.data_queries.is_empty());
        assert!(response.execution_logs.is_empty());
        assert!(response.decision.is_none());
        assert_eq!(response.execution_time_ms, 3.5);
    }

    #[test]
    fn parses_binance_positions_for_preview_input_snapshot() {
        let positions = extract_binance_positions_for_preview(
            r#"{"positions":[{"symbol":"BTCUSDT","positionAmt":"0.0100","entryPrice":"50000","unRealizedProfit":"5","liquidationPrice":"45000","leverage":"10"}]}"#,
        );

        assert_eq!(positions["BTC"]["side"], json!("long"));
        assert_eq!(positions["BTC"]["size"], json!(0.01));
        assert_eq!(positions["BTC"]["entry_price"], json!(50000.0));
        assert_eq!(positions["BTC"]["unrealized_pnl"], json!(5.0));
        assert_eq!(positions["BTC"]["leverage"], json!(10));
        assert_eq!(parse_json_number(Some(&json!("42.25"))), Some(42.25));
    }

    #[tokio::test]
    async fn preview_run_sandbox_returns_execution_details_and_query_log() {
        let input_data = json!({
            "trigger_symbol": "ETH",
            "trigger_type": "scheduled",
            "environment": "testnet",
            "exchange": "hyperliquid",
            "available_balance": 1234.0,
            "total_equity": 1250.0,
            "used_margin": 16.0,
            "margin_usage_percent": 1.28,
            "maintenance_margin": 0.0,
            "positions": {
                "ETH": {
                    "symbol": "ETH",
                    "side": "long",
                    "size": 0.5,
                    "entry_price": 2000.0,
                    "unrealized_pnl": 12.0,
                    "leverage": 3,
                    "liquidation_price": 1500.0
                }
            },
            "open_orders": [],
            "max_leverage": 20,
            "default_leverage": 3
        });
        let params = json!({"reason": "preview ok"});
        let output = execute_preview_run_sandbox(&PreviewRunSandboxInput {
            mode: "preview_run",
            code: "class PreviewStrategy:\n    def init(self, params):\n        self.params = params\n    def should_trade(self, data):\n        log('balance=' + str(data.available_balance))\n        data.get_indicator(data.trigger_symbol, 'RSI14', '1h')\n        return Decision(operation='hold', symbol=data.trigger_symbol, reason=self.params.get('reason'))\n",
            symbol: "ETH",
            params: &params,
            input_data: &input_data,
        })
        .await
        .expect("preview-run sandbox should execute");

        assert!(output.success);
        assert_eq!(
            output.decision.as_ref().unwrap()["operation"],
            json!("hold")
        );
        assert_eq!(output.decision.as_ref().unwrap()["symbol"], json!("ETH"));
        assert_eq!(
            output.decision.as_ref().unwrap()["reason"],
            json!("preview ok")
        );
        assert_eq!(output.execution_logs, vec!["balance=1234.0"]);
        assert_eq!(output.data_queries.len(), 1);
        assert_eq!(output.data_queries[0]["method"], json!("get_indicator"));
        assert_eq!(output.data_queries[0]["args"]["symbol"], json!("ETH"));
    }

    #[tokio::test]
    async fn preview_run_sandbox_returns_structured_runtime_failures() {
        let input_data = json!({
            "trigger_symbol": "BTC",
            "trigger_type": "signal",
            "environment": "testnet",
            "exchange": "hyperliquid",
            "available_balance": 2000.0,
            "total_equity": 2100.0,
            "used_margin": 100.0,
            "margin_usage_percent": 4.76,
            "maintenance_margin": 10.0,
            "positions": {},
            "open_orders": []
        });
        let params = json!({});
        let output = execute_preview_run_sandbox(&PreviewRunSandboxInput {
            mode: "preview_run",
            code: "class BrokenPreviewStrategy:\n    def should_trade(self, data):\n        log('before crash')\n        data.get_flow(data.trigger_symbol, 'CVD', '1h')\n        return missing_name\n",
            symbol: "BTC",
            params: &params,
            input_data: &input_data,
        })
        .await
        .expect("preview-run sandbox should return structured runtime failures");

        assert!(!output.success);
        assert!(output.decision.is_none());
        assert!(
            output
                .error
                .as_deref()
                .unwrap_or_default()
                .contains("missing_name")
        );
        assert_eq!(output.execution_logs, vec!["before crash"]);
        assert_eq!(output.data_queries.len(), 1);
        assert_eq!(output.data_queries[0]["method"], json!("get_flow"));
        assert_eq!(output.data_queries[0]["args"]["symbol"], json!("BTC"));
    }

    #[test]
    fn backtest_stream_parser_only_keeps_data_payload_lines() {
        assert_eq!(
            parse_backtest_stream_data_line(r#"data: {"type":"init"}"#),
            Some(r#"{"type":"init"}"#.to_owned())
        );
        assert_eq!(parse_backtest_stream_data_line("event: progress"), None);
        assert_eq!(parse_backtest_stream_data_line(""), None);
    }

    #[tokio::test]
    async fn backtest_stream_response_preserves_sse_contract() {
        const FAKE_BACKTEST_SCRIPT: &str = r#"
import json
import sys

request = json.load(sys.stdin)

def emit(event):
    print(f"data: {json.dumps(event)}")
    print()

emit({"type": "calculating", "message": "Calculating trigger points..."})
emit({"type": "init", "total_triggers": 1, "backtest_id": request["binding_id"]})
emit({
    "type": "complete",
    "backtest_id": request["binding_id"],
    "success": True,
    "total_pnl": 12.5,
    "equity_curve": [],
    "trades": []
})
"#;

        let state = AppState::from_config(AppConfig::for_tests());
        let request = ProgramBacktestRequest {
            binding_id: 42,
            start_time_ms: 1_700_000_000_000,
            end_time_ms: 1_700_003_600_000,
            initial_balance: 10000.0,
            slippage_percent: 0.05,
            fee_rate: 0.035,
        };

        let child =
            spawn_program_backtest_process_with_script(&state, &request, FAKE_BACKTEST_SCRIPT)
                .await
                .expect("fake backtest subprocess should start");
        let response = build_program_backtest_stream_response(child);

        assert_eq!(
            response.headers().get(header::CONTENT_TYPE).unwrap(),
            "text/event-stream"
        );
        assert_eq!(
            response.headers().get(header::CACHE_CONTROL).unwrap(),
            "no-cache"
        );

        let body = to_bytes(response.into_body(), usize::MAX)
            .await
            .expect("sse body should be readable");
        let text = String::from_utf8(body.to_vec()).expect("sse body should be utf-8");

        assert!(text.contains(
            r#"data: {"type": "calculating", "message": "Calculating trigger points..."}"#
        ));
        assert!(text.contains(r#"data: {"type": "init", "total_triggers": 1, "backtest_id": 42}"#));
        assert!(text.contains(r#"data: {"type": "complete", "backtest_id": 42, "success": true, "total_pnl": 12.5, "equity_curve": [], "trades": []}"#));
    }
}
