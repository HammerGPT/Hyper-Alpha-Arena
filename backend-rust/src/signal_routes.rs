use axum::{
    Json,
    body::Bytes,
    extract::{Path, Query, State},
    http::{HeaderMap, Method, StatusCode},
    response::Response,
};
use chrono::{NaiveDateTime, Utc};
use serde::{Deserialize, Serialize};
use serde_json::{Map, Value};
use sqlx::Row;
use std::{
    collections::{BTreeMap, HashMap},
    sync::{LazyLock, RwLock},
};

use crate::{
    error::AppError,
    proxy::{build_downstream_streaming_response, build_upstream_request},
    state::AppState,
    wallet_tracking_runtime,
};

const MARKET_SIGNAL_SOURCE: &str = "market_signals";
const WALLET_TRACKING_SOURCE: &str = "wallet_tracking";
const WALLET_TRACKING_ENABLED_KEY: &str = "hyper_insight_wallet_enabled";
const WALLET_TRACKING_ACCESS_TOKEN_KEY: &str = "hyper_insight_wallet_access_token";
const WALLET_TRACKING_TOKEN_SYNCED_AT_KEY: &str = "hyper_insight_wallet_token_synced_at";
const WALLET_TRACKING_ENABLED_DESCRIPTION: &str =
    "Whether Hyper Insight wallet tracking integration is enabled";
const WALLET_TRACKING_ACCESS_TOKEN_DESCRIPTION: &str =
    "Latest Hyper Insight access token for runtime sync";
const WALLET_TRACKING_TOKEN_SYNCED_AT_DESCRIPTION: &str = "Last Hyper Insight token sync time";
const MIN_SIGNAL_ANALYSIS_SAMPLES: usize = 3;
const LIMITED_SIGNAL_ANALYSIS_DATA_THRESHOLD: usize = 10;
const MAX_SIGNAL_POOL_CONFIG_SIGNALS: usize = 10;
const DAY_MS: i64 = 24 * 60 * 60 * 1000;

#[derive(Serialize)]
pub struct SignalListResponse {
    signals: Vec<SignalDefinitionResponse>,
    pools: Vec<SignalPoolResponse>,
}

#[derive(Clone, Debug, Deserialize)]
pub struct SignalDefinitionCreate {
    signal_name: String,
    description: Option<String>,
    trigger_condition: Value,
    #[serde(default = "default_true")]
    enabled: bool,
    #[serde(default = "default_exchange")]
    exchange: String,
}

#[derive(Clone, Debug, Deserialize)]
pub struct SignalDefinitionUpdate {
    signal_name: Option<String>,
    description: Option<String>,
    trigger_condition: Option<Value>,
    enabled: Option<bool>,
    exchange: Option<String>,
}

#[derive(Serialize)]
pub struct SignalDefinitionResponse {
    id: i32,
    signal_name: String,
    description: Option<String>,
    trigger_condition: Value,
    enabled: bool,
    exchange: String,
    created_at: String,
    updated_at: String,
}

#[derive(Clone, Debug, Deserialize)]
pub struct SignalPoolCreate {
    pool_name: String,
    #[serde(default)]
    signal_ids: Vec<i32>,
    #[serde(default)]
    symbols: Vec<String>,
    #[serde(default = "default_true")]
    enabled: bool,
    #[serde(default = "default_logic")]
    logic: String,
    #[serde(default = "default_exchange")]
    exchange: String,
    #[serde(default = "default_market_source")]
    source_type: String,
    #[serde(default)]
    source_config: Value,
}

#[derive(Clone, Debug, Deserialize)]
pub struct SignalPoolUpdate {
    pool_name: Option<String>,
    signal_ids: Option<Vec<i32>>,
    symbols: Option<Vec<String>>,
    enabled: Option<bool>,
    logic: Option<String>,
    exchange: Option<String>,
    source_type: Option<String>,
    source_config: Option<Value>,
}

#[derive(Serialize)]
pub struct SignalPoolResponse {
    id: i32,
    pool_name: String,
    signal_ids: Vec<i32>,
    symbols: Vec<String>,
    enabled: bool,
    logic: String,
    exchange: String,
    source_type: String,
    source_config: Value,
    created_at: String,
}

#[derive(Serialize)]
pub struct SignalTriggerLogResponse {
    id: i32,
    signal_id: Option<i32>,
    pool_id: Option<i32>,
    symbol: String,
    trigger_value: Option<Value>,
    triggered_at: String,
    market_regime: Option<Value>,
}

#[derive(Serialize)]
pub struct SignalTriggerLogsResponse {
    logs: Vec<SignalTriggerLogResponse>,
    total: i64,
}

#[derive(Deserialize)]
pub struct TriggerLogsQuery {
    pool_id: Option<i32>,
    signal_id: Option<i32>,
    symbol: Option<String>,
    #[serde(default = "default_logs_limit")]
    limit: i64,
    #[serde(default)]
    offset: i64,
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
}

#[derive(Serialize)]
pub struct WalletTrackingStatusResponse {
    enabled: bool,
    status: String,
    tier: Option<String>,
    synced_addresses: Vec<String>,
    last_connected_at: Option<String>,
    last_message_at: Option<String>,
    last_event_at: Option<String>,
    last_error: Option<String>,
    active_wallet_pool_count: i64,
    token_synced_at: Option<String>,
}

#[derive(Deserialize)]
pub struct WalletTrackingRuntimeRequest {
    enabled: bool,
    access_token: Option<String>,
}

#[derive(Deserialize)]
pub struct WalletTrackingTokenRequest {
    access_token: String,
}

#[derive(Serialize)]
pub struct WalletTrackingTokenResponse {
    success: bool,
}

#[derive(Default)]
struct SignalRuntimeStateStore {
    signal_states: HashMap<(i32, String), RuntimeSignalState>,
    pool_states: HashMap<(i32, String), RuntimePoolState>,
}

#[derive(Clone, Debug)]
struct RuntimeSignalState {
    is_active: bool,
    last_value: Option<f64>,
    last_check_time: f64,
}

#[derive(Clone, Debug)]
struct RuntimePoolState {
    is_active: bool,
    signal_conditions_met: BTreeMap<String, bool>,
    last_check_time: f64,
}

static SIGNAL_RUNTIME_STATE_STORE: LazyLock<RwLock<SignalRuntimeStateStore>> =
    LazyLock::new(|| RwLock::new(SignalRuntimeStateStore::default()));

#[derive(Serialize)]
pub struct SignalStatesResponse {
    states: SignalStatesPayload,
    cache_info: SignalStatesCacheInfo,
}

#[derive(Serialize)]
pub struct SignalStatesPayload {
    signal_states: BTreeMap<String, SignalStateEntry>,
    pool_states: BTreeMap<String, PoolStateEntry>,
}

#[derive(Serialize)]
pub struct SignalStateEntry {
    is_active: bool,
    last_value: Option<f64>,
    last_check_time: f64,
}

#[derive(Serialize)]
pub struct PoolStateEntry {
    is_active: bool,
    signal_conditions_met: BTreeMap<String, bool>,
    last_check_time: f64,
}

#[derive(Serialize)]
pub struct SignalStatesCacheInfo {
    pools_count: i64,
    signals_count: i64,
}

#[derive(Clone, Debug, Default, Deserialize)]
pub struct ResetSignalStatesQuery {
    signal_id: Option<i32>,
    pool_id: Option<i32>,
    symbol: Option<String>,
}

#[derive(Serialize)]
pub struct ResetSignalStatesResponse {
    message: String,
}

#[derive(Clone, Debug, Deserialize)]
pub struct SignalAnalyzeQuery {
    symbol: String,
    metric: String,
    #[serde(default = "default_analyze_period")]
    period: String,
    #[serde(default = "default_analyze_days")]
    days: i64,
    #[serde(default = "default_exchange")]
    exchange: String,
}

#[derive(Clone, Debug, Deserialize)]
pub struct SignalBacktestQuery {
    symbol: Option<String>,
    kline_min_ts: Option<String>,
    kline_max_ts: Option<String>,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct AiSignalChatStreamRequest {
    #[serde(alias = "accountId")]
    account_id: i32,
    #[serde(alias = "userMessage")]
    user_message: String,
    #[serde(alias = "conversationId")]
    conversation_id: Option<i32>,
    #[serde(default = "default_true", alias = "useBackgroundTask")]
    use_background_task: bool,
}

#[derive(Clone, Debug, Deserialize)]
pub struct SignalTestQuery {
    symbol: Option<String>,
}

#[derive(Debug)]
struct ParsedSignalBacktestQuery {
    symbol: String,
    kline_min_ts: Option<i64>,
    kline_max_ts: Option<i64>,
}

#[derive(Debug)]
struct ParsedSignalTestQuery {
    symbol: String,
}

#[derive(Debug)]
struct ParsedSignalBacktestPreviewRequest {
    symbol: String,
    trigger_condition: Value,
    kline_min_ts: Option<i64>,
    kline_max_ts: Option<i64>,
    exchange: String,
}

#[derive(Clone, Debug, Serialize)]
struct SignalThresholdSuggestion {
    threshold: f64,
    description: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    recommended: Option<bool>,
    #[serde(skip_serializing_if = "Option::is_none")]
    multiplier: Option<f64>,
}

#[derive(Clone, Debug, Serialize)]
struct SignalThresholdSuggestions {
    aggressive: SignalThresholdSuggestion,
    moderate: SignalThresholdSuggestion,
    conservative: SignalThresholdSuggestion,
}

#[derive(Clone, Debug, Serialize)]
struct MetricStatistics {
    mean: f64,
    std: f64,
    min: f64,
    max: f64,
    abs_percentiles: MetricAbsPercentiles,
}

#[derive(Clone, Debug, Serialize)]
struct MetricAbsPercentiles {
    p75: f64,
    p90: f64,
    p95: f64,
    p99: f64,
}

pub async fn list_signals(
    State(state): State<AppState>,
) -> Result<Json<SignalListResponse>, AppError> {
    let signals = load_signal_definitions(&state.db).await?;
    let pools = load_signal_pools(&state.db).await?;
    Ok(Json(SignalListResponse { signals, pools }))
}

pub async fn get_wallet_tracking_status(
    State(state): State<AppState>,
) -> Result<Json<WalletTrackingStatusResponse>, AppError> {
    Ok(Json(get_wallet_tracking_status_snapshot(&state).await?))
}

pub async fn update_wallet_tracking_runtime(
    State(state): State<AppState>,
    Json(payload): Json<WalletTrackingRuntimeRequest>,
) -> Result<Json<WalletTrackingStatusResponse>, AppError> {
    Ok(Json(
        apply_wallet_tracking_runtime_update(&state, payload).await?,
    ))
}

pub async fn sync_wallet_tracking_token(
    State(state): State<AppState>,
    Json(payload): Json<WalletTrackingTokenRequest>,
) -> Result<Json<WalletTrackingTokenResponse>, AppError> {
    sync_wallet_tracking_access_token(&state, &payload.access_token).await?;
    Ok(Json(WalletTrackingTokenResponse { success: true }))
}

pub async fn clear_wallet_tracking_token(
    State(state): State<AppState>,
) -> Result<Json<WalletTrackingTokenResponse>, AppError> {
    clear_wallet_tracking_access_token(&state).await?;
    Ok(Json(WalletTrackingTokenResponse { success: true }))
}

pub async fn get_signal_states(
    State(state): State<AppState>,
) -> Result<Json<SignalStatesResponse>, AppError> {
    Ok(Json(SignalStatesResponse {
        states: snapshot_signal_runtime_states(),
        cache_info: load_signal_states_cache_info(&state.db).await?,
    }))
}

pub async fn reset_signal_states(
    Query(query): Query<ResetSignalStatesQuery>,
) -> Result<Json<ResetSignalStatesResponse>, AppError> {
    reset_signal_runtime_states(query);
    Ok(Json(ResetSignalStatesResponse {
        message: "Signal and pool states reset successfully".to_owned(),
    }))
}

pub async fn get_signal_metric_analysis(
    State(state): State<AppState>,
    Query(query): Query<SignalAnalyzeQuery>,
) -> Result<Json<Value>, AppError> {
    if query.days > 30 {
        return Err(AppError::bad_request(
            "days must be less than or equal to 30",
        ));
    }

    Ok(Json(analyze_signal_metric(&state.db, query).await))
}

pub async fn get_signal_backtest(
    State(state): State<AppState>,
    Path(signal_id): Path<String>,
    Query(query): Query<SignalBacktestQuery>,
    headers: HeaderMap,
) -> Result<Response, AppError> {
    let signal_id = parse_signal_backtest_signal_id(&signal_id)?;
    let query = parse_signal_backtest_query(query)?;
    let mut target_url = state
        .config
        .legacy_http_target(&format!("/api/signals/backtest/{signal_id}"));
    {
        let mut query_pairs = target_url.query_pairs_mut();
        query_pairs.append_pair("symbol", &query.symbol);
        if let Some(kline_min_ts) = query.kline_min_ts {
            query_pairs.append_pair("kline_min_ts", &kline_min_ts.to_string());
        }
        if let Some(kline_max_ts) = query.kline_max_ts {
            query_pairs.append_pair("kline_max_ts", &kline_max_ts.to_string());
        }
    }

    let upstream_request = build_upstream_request(
        &state.client,
        Method::GET,
        &headers,
        target_url,
        Bytes::new(),
    )?;
    let upstream_response = upstream_request.send().await.map_err(|error| {
        AppError::bad_gateway(format!("legacy signal backtest request failed: {error}"))
    })?;

    build_downstream_streaming_response(upstream_response)
}

pub async fn get_signal_pool_backtest(
    State(state): State<AppState>,
    Path(pool_id): Path<String>,
    Query(query): Query<SignalBacktestQuery>,
    headers: HeaderMap,
) -> Result<Response, AppError> {
    let pool_id = parse_signal_backtest_pool_id(&pool_id)?;
    let query = parse_signal_backtest_query(query)?;
    let mut target_url = state
        .config
        .legacy_http_target(&format!("/api/signals/pool-backtest/{pool_id}"));
    {
        let mut query_pairs = target_url.query_pairs_mut();
        query_pairs.append_pair("symbol", &query.symbol);
        if let Some(kline_min_ts) = query.kline_min_ts {
            query_pairs.append_pair("kline_min_ts", &kline_min_ts.to_string());
        }
        if let Some(kline_max_ts) = query.kline_max_ts {
            query_pairs.append_pair("kline_max_ts", &kline_max_ts.to_string());
        }
    }

    let upstream_request = build_upstream_request(
        &state.client,
        Method::GET,
        &headers,
        target_url,
        Bytes::new(),
    )?;
    let upstream_response = upstream_request.send().await.map_err(|error| {
        AppError::bad_gateway(format!(
            "legacy signal pool-backtest request failed: {error}"
        ))
    })?;

    build_downstream_streaming_response(upstream_response)
}

pub async fn get_signal_test(
    State(state): State<AppState>,
    Path(signal_id): Path<String>,
    Query(query): Query<SignalTestQuery>,
    headers: HeaderMap,
) -> Result<Response, AppError> {
    let signal_id = parse_signal_backtest_signal_id(&signal_id)?;
    let query = parse_signal_test_query(query)?;
    let mut target_url = state
        .config
        .legacy_http_target(&format!("/api/signals/test/{signal_id}"));
    target_url
        .query_pairs_mut()
        .append_pair("symbol", &query.symbol);

    let upstream_request = build_upstream_request(
        &state.client,
        Method::GET,
        &headers,
        target_url,
        Bytes::new(),
    )?;
    let upstream_response = upstream_request.send().await.map_err(|error| {
        AppError::bad_gateway(format!("legacy signal test request failed: {error}"))
    })?;

    build_downstream_streaming_response(upstream_response)
}

pub async fn get_signal_backtest_preview(
    State(state): State<AppState>,
    headers: HeaderMap,
    Json(payload): Json<Value>,
) -> Result<Response, AppError> {
    let parsed = parse_signal_backtest_preview_request(payload)?;
    let mut request_payload = Map::new();
    request_payload.insert("symbol".to_owned(), Value::String(parsed.symbol));
    request_payload.insert("trigger_condition".to_owned(), parsed.trigger_condition);
    request_payload.insert("exchange".to_owned(), Value::String(parsed.exchange));
    if let Some(kline_min_ts) = parsed.kline_min_ts {
        request_payload.insert(
            "kline_min_ts".to_owned(),
            Value::Number(kline_min_ts.into()),
        );
    }
    if let Some(kline_max_ts) = parsed.kline_max_ts {
        request_payload.insert(
            "kline_max_ts".to_owned(),
            Value::Number(kline_max_ts.into()),
        );
    }

    let request_body = serde_json::to_vec(&Value::Object(request_payload)).map_err(|error| {
        AppError::internal(format!("Failed to encode signal preview request: {error}"))
    })?;

    let target_url = state
        .config
        .legacy_http_target("/api/signals/backtest-preview");
    let upstream_request = build_upstream_request(
        &state.client,
        Method::POST,
        &headers,
        target_url,
        request_body.into(),
    )?;
    let upstream_response = upstream_request.send().await.map_err(|error| {
        AppError::bad_gateway(format!(
            "legacy signal backtest-preview request failed: {error}"
        ))
    })?;

    build_downstream_streaming_response(upstream_response)
}

pub async fn create_pool_from_config(
    State(state): State<AppState>,
    headers: HeaderMap,
    Json(payload): Json<Value>,
) -> Result<Response, AppError> {
    let request_payload = parse_signal_pool_from_config_request(payload)?;
    let request_body = serde_json::to_vec(&request_payload).map_err(|error| {
        AppError::internal(format!(
            "Failed to encode signal pool config request: {error}"
        ))
    })?;

    let target_url = state
        .config
        .legacy_http_target("/api/signals/create-pool-from-config");
    let upstream_request = build_upstream_request(
        &state.client,
        Method::POST,
        &headers,
        target_url,
        request_body.into(),
    )?;
    let upstream_response = upstream_request.send().await.map_err(|error| {
        AppError::bad_gateway(format!(
            "legacy create-pool-from-config request failed: {error}"
        ))
    })?;

    build_downstream_streaming_response(upstream_response)
}

pub async fn chat_with_signal_ai_stream(
    State(state): State<AppState>,
    headers: HeaderMap,
    Json(payload): Json<AiSignalChatStreamRequest>,
) -> Result<Response, AppError> {
    let request_body = serde_json::to_vec(&payload).map_err(|error| {
        AppError::internal(format!(
            "Failed to encode signal ai-chat-stream request: {error}"
        ))
    })?;

    let target_url = state
        .config
        .legacy_http_target("/api/signals/ai-chat-stream");
    let upstream_request = build_upstream_request(
        &state.client,
        Method::POST,
        &headers,
        target_url,
        request_body.into(),
    )?;
    let upstream_response = upstream_request.send().await.map_err(|error| {
        AppError::bad_gateway(format!(
            "legacy signal ai-chat-stream request failed: {error}"
        ))
    })?;

    build_downstream_streaming_response(upstream_response)
}

pub async fn create_signal(
    State(state): State<AppState>,
    Json(payload): Json<SignalDefinitionCreate>,
) -> Result<Json<SignalDefinitionResponse>, AppError> {
    let row = sqlx::query(
        r#"
        INSERT INTO signal_definitions (signal_name, description, trigger_condition, enabled, exchange, created_at, updated_at)
        VALUES ($1, $2, $3, $4, $5, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        RETURNING id
        "#,
    )
    .bind(&payload.signal_name)
    .bind(payload.description.as_deref())
    .bind(payload.trigger_condition.to_string())
    .bind(payload.enabled)
    .bind(&payload.exchange)
    .fetch_one(&state.db)
    .await
    .map_err(|error| AppError::internal(format!("Failed to create signal: {error}")))?;

    let id = row.try_get::<i32, _>("id").map_err(read_signal_error)?;
    Ok(Json(load_signal_definition_by_id(&state, id).await?))
}

pub async fn get_signal(
    State(state): State<AppState>,
    Path(signal_id): Path<i32>,
) -> Result<Json<SignalDefinitionResponse>, AppError> {
    Ok(Json(load_signal_definition_by_id(&state, signal_id).await?))
}

pub async fn update_signal(
    State(state): State<AppState>,
    Path(signal_id): Path<i32>,
    Json(payload): Json<SignalDefinitionUpdate>,
) -> Result<Json<SignalDefinitionResponse>, AppError> {
    let current = load_signal_definition_row(&state, signal_id)
        .await?
        .ok_or_else(|| AppError::not_found("Signal not found"))?;

    let signal_name = payload.signal_name.unwrap_or_else(|| {
        current
            .try_get::<String, _>("signal_name")
            .unwrap_or_default()
    });
    let description = if payload.description.is_some() {
        payload.description
    } else {
        current
            .try_get::<Option<String>, _>("description")
            .ok()
            .flatten()
    };
    let trigger_condition = payload.trigger_condition.unwrap_or_else(|| {
        parse_json_or_default(
            current
                .try_get::<Option<String>, _>("trigger_condition")
                .ok()
                .flatten(),
            Value::Object(Default::default()),
        )
    });
    let enabled = payload.enabled.unwrap_or_else(|| {
        current
            .try_get::<Option<bool>, _>("enabled")
            .ok()
            .flatten()
            .unwrap_or(true)
    });
    let exchange = payload.exchange.unwrap_or_else(|| {
        current
            .try_get::<Option<String>, _>("exchange")
            .ok()
            .flatten()
            .unwrap_or_else(default_exchange)
    });

    let result = sqlx::query(
        r#"
        UPDATE signal_definitions
        SET signal_name = $2,
            description = $3,
            trigger_condition = $4,
            enabled = $5,
            exchange = $6,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = $1
          AND (is_deleted IS NULL OR is_deleted = false)
        "#,
    )
    .bind(signal_id)
    .bind(signal_name)
    .bind(description.as_deref())
    .bind(trigger_condition.to_string())
    .bind(enabled)
    .bind(exchange)
    .execute(&state.db)
    .await
    .map_err(|error| AppError::internal(format!("Failed to update signal: {error}")))?;

    if result.rows_affected() == 0 {
        return Err(AppError::not_found("Signal not found"));
    }

    Ok(Json(load_signal_definition_by_id(&state, signal_id).await?))
}

pub async fn delete_signal(
    State(state): State<AppState>,
    Path(signal_id): Path<i32>,
) -> Result<Json<DeleteResult>, AppError> {
    let row = load_signal_definition_row(&state, signal_id)
        .await?
        .ok_or_else(|| AppError::not_found("Signal not found"))?;

    let deps = load_signal_definition_dependencies(&state, signal_id).await?;
    if !deps.is_empty() {
        return Ok(Json(DeleteResult {
            success: true,
            deleted: false,
            dependencies: Some(deps),
            message: Some(
                "Cannot delete: signal is used in pools. Remove from pools first.".to_owned(),
            ),
            entity: None,
        }));
    }

    sqlx::query(
        r#"
        UPDATE signal_definitions
        SET is_deleted = true,
            deleted_at = CURRENT_TIMESTAMP
        WHERE id = $1
        "#,
    )
    .bind(signal_id)
    .execute(&state.db)
    .await
    .map_err(|error| AppError::internal(format!("Failed to delete signal: {error}")))?;

    Ok(Json(DeleteResult {
        success: true,
        deleted: true,
        dependencies: None,
        message: None,
        entity: Some(serde_json::json!({
            "id": signal_id,
            "name": row.try_get::<String, _>("signal_name").map_err(read_signal_error)?,
        })),
    }))
}

async fn load_signal_definitions(
    pool: &sqlx::PgPool,
) -> Result<Vec<SignalDefinitionResponse>, AppError> {
    let rows = sqlx::query(
        r#"
        SELECT id, signal_name, description, trigger_condition, enabled, created_at, updated_at, exchange
        FROM signal_definitions
        WHERE (is_deleted IS NULL OR is_deleted = false)
        ORDER BY id
        "#,
    )
    .fetch_all(pool)
    .await
    .map_err(|error| AppError::internal(format!("Failed to load signals: {error}")))?;

    rows.into_iter()
        .map(row_to_signal_definition)
        .collect::<Result<Vec<_>, _>>()
}

async fn load_signal_definition_by_id(
    state: &AppState,
    signal_id: i32,
) -> Result<SignalDefinitionResponse, AppError> {
    let row = load_signal_definition_row(state, signal_id)
        .await?
        .ok_or_else(|| AppError::not_found("Signal not found"))?;
    row_to_signal_definition(row)
}

async fn load_signal_definition_row(
    state: &AppState,
    signal_id: i32,
) -> Result<Option<sqlx::postgres::PgRow>, AppError> {
    sqlx::query(
        r#"
        SELECT id, signal_name, description, trigger_condition, enabled, created_at, updated_at, exchange
        FROM signal_definitions
        WHERE id = $1 AND (is_deleted IS NULL OR is_deleted = false)
        "#,
    )
    .bind(signal_id)
    .fetch_optional(&state.db)
    .await
    .map_err(|error| AppError::internal(format!("Failed to load signal: {error}")))
}

async fn load_signal_definition_dependencies(
    state: &AppState,
    signal_id: i32,
) -> Result<Vec<String>, AppError> {
    let rows = sqlx::query(
        r#"
        SELECT id, pool_name, signal_ids
        FROM signal_pools
        WHERE is_deleted IS DISTINCT FROM true
        "#,
    )
    .fetch_all(&state.db)
    .await
    .map_err(|error| AppError::internal(format!("Failed to load signal dependencies: {error}")))?;

    let mut dependencies = Vec::new();
    for row in rows {
        let ids = parse_i32_list(
            row.try_get::<Option<String>, _>("signal_ids")
                .ok()
                .flatten()
                .as_deref(),
        );
        if ids.contains(&signal_id) {
            dependencies.push(format!(
                "Referenced by Signal Pool: {} (#{})",
                row.try_get::<String, _>("pool_name")
                    .map_err(read_signal_error)?,
                row.try_get::<i32, _>("id").map_err(read_signal_error)?,
            ));
        }
    }
    Ok(dependencies)
}

pub async fn create_pool(
    State(state): State<AppState>,
    Json(payload): Json<SignalPoolCreate>,
) -> Result<Json<SignalPoolResponse>, AppError> {
    let source_type = normalize_source_type(&payload.source_type)?;
    let source_config = normalize_source_config(&source_type, payload.source_config)?;
    let exchange = payload.exchange;

    if source_type == MARKET_SIGNAL_SOURCE {
        validate_signal_exchange(&state, &payload.signal_ids, &exchange).await?;
    }

    let signal_ids = if source_type == MARKET_SIGNAL_SOURCE {
        payload.signal_ids
    } else {
        Vec::new()
    };
    let symbols = if source_type == MARKET_SIGNAL_SOURCE {
        payload.symbols
    } else {
        Vec::new()
    };

    let row = sqlx::query(
        r#"
        INSERT INTO signal_pools (
            pool_name, signal_ids, symbols, enabled, logic, exchange, source_type, source_config, created_at
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, CURRENT_TIMESTAMP)
        RETURNING id
        "#,
    )
    .bind(&payload.pool_name)
    .bind(serde_json::to_string(&signal_ids).map_err(json_err)?)
    .bind(serde_json::to_string(&symbols).map_err(json_err)?)
    .bind(payload.enabled)
    .bind(&payload.logic)
    .bind(&exchange)
    .bind(&source_type)
    .bind(source_config.to_string())
    .fetch_one(&state.db)
    .await
    .map_err(|error| AppError::internal(format!("Failed to create pool: {error}")))?;

    sync_wallet_runtime_refresh(&state).await;

    let id = row.try_get::<i32, _>("id").map_err(read_signal_error)?;
    Ok(Json(load_signal_pool_by_id(&state, id).await?))
}

pub async fn get_pool(
    State(state): State<AppState>,
    Path(pool_id): Path<i32>,
) -> Result<Json<SignalPoolResponse>, AppError> {
    Ok(Json(load_signal_pool_by_id(&state, pool_id).await?))
}

pub async fn update_pool(
    State(state): State<AppState>,
    Path(pool_id): Path<i32>,
    Json(payload): Json<SignalPoolUpdate>,
) -> Result<Json<SignalPoolResponse>, AppError> {
    let current = load_signal_pool_row(&state, pool_id)
        .await?
        .ok_or_else(|| AppError::not_found("Pool not found"))?;

    let exchange = payload
        .exchange
        .clone()
        .or_else(|| {
            current
                .try_get::<Option<String>, _>("exchange")
                .ok()
                .flatten()
        })
        .unwrap_or_else(default_exchange);
    let current_source_type = current
        .try_get::<Option<String>, _>("source_type")
        .ok()
        .flatten();
    let source_type = normalize_source_type(
        payload
            .source_type
            .as_deref()
            .or(current_source_type.as_deref())
            .unwrap_or(MARKET_SIGNAL_SOURCE),
    )?;
    let source_config = normalize_source_config(
        &source_type,
        payload.source_config.clone().unwrap_or_else(|| {
            parse_json_or_default(
                current
                    .try_get::<Option<String>, _>("source_config")
                    .ok()
                    .flatten(),
                Value::Object(Default::default()),
            )
        }),
    )?;

    let signal_ids = match payload.signal_ids {
        Some(ids) if source_type == MARKET_SIGNAL_SOURCE => ids,
        Some(_) => Vec::new(),
        None if source_type == MARKET_SIGNAL_SOURCE => parse_i32_list(
            current
                .try_get::<Option<String>, _>("signal_ids")
                .ok()
                .flatten()
                .as_deref(),
        ),
        None => Vec::new(),
    };
    if source_type == MARKET_SIGNAL_SOURCE {
        validate_signal_exchange(&state, &signal_ids, &exchange).await?;
    }

    let symbols = match payload.symbols {
        Some(symbols) if source_type == MARKET_SIGNAL_SOURCE => symbols,
        Some(_) => Vec::new(),
        None if source_type == MARKET_SIGNAL_SOURCE => parse_string_list(
            current
                .try_get::<Option<String>, _>("symbols")
                .ok()
                .flatten()
                .as_deref(),
        ),
        None => Vec::new(),
    };

    let result = sqlx::query(
        r#"
        UPDATE signal_pools
        SET pool_name = COALESCE($2, pool_name),
            signal_ids = $3,
            symbols = $4,
            enabled = COALESCE($5, enabled),
            logic = COALESCE($6, logic),
            exchange = $7,
            source_type = $8,
            source_config = $9
        WHERE id = $1
          AND (is_deleted IS NULL OR is_deleted = false)
        "#,
    )
    .bind(pool_id)
    .bind(payload.pool_name.as_deref())
    .bind(serde_json::to_string(&signal_ids).map_err(json_err)?)
    .bind(serde_json::to_string(&symbols).map_err(json_err)?)
    .bind(payload.enabled)
    .bind(payload.logic.as_deref())
    .bind(&exchange)
    .bind(&source_type)
    .bind(source_config.to_string())
    .execute(&state.db)
    .await
    .map_err(|error| AppError::internal(format!("Failed to update pool: {error}")))?;

    if result.rows_affected() == 0 {
        return Err(AppError::not_found("Pool not found"));
    }

    sync_wallet_runtime_refresh(&state).await;
    Ok(Json(load_signal_pool_by_id(&state, pool_id).await?))
}

pub async fn delete_pool(
    State(state): State<AppState>,
    Path(pool_id): Path<i32>,
) -> Result<Json<DeleteResult>, AppError> {
    let pool = load_signal_pool_row(&state, pool_id)
        .await?
        .ok_or_else(|| AppError::not_found("Pool not found"))?;

    let deps = load_signal_pool_dependencies(&state, pool_id).await?;
    if !deps.is_empty() {
        return Ok(Json(DeleteResult {
            success: true,
            deleted: false,
            dependencies: Some(deps),
            message: Some(
                "Cannot delete: pool is referenced by strategies. Remove references first."
                    .to_owned(),
            ),
            entity: None,
        }));
    }

    sqlx::query(
        r#"
        UPDATE signal_pools
        SET is_deleted = true,
            deleted_at = CURRENT_TIMESTAMP,
            enabled = false
        WHERE id = $1
        "#,
    )
    .bind(pool_id)
    .execute(&state.db)
    .await
    .map_err(|error| AppError::internal(format!("Failed to delete pool: {error}")))?;

    sync_wallet_runtime_refresh(&state).await;
    Ok(Json(DeleteResult {
        success: true,
        deleted: true,
        dependencies: None,
        message: None,
        entity: Some(serde_json::json!({
            "id": pool_id,
            "name": pool.try_get::<String, _>("pool_name").map_err(read_signal_error)?,
        })),
    }))
}

pub async fn get_trigger_logs(
    State(state): State<AppState>,
    Query(query): Query<TriggerLogsQuery>,
) -> Result<Json<SignalTriggerLogsResponse>, AppError> {
    let rows = sqlx::query(
        r#"
        SELECT id, signal_id, pool_id, symbol, trigger_value, triggered_at, market_regime
        FROM signal_trigger_logs
        WHERE ($1::int4 IS NULL OR pool_id = $1)
          AND ($2::int4 IS NULL OR signal_id = $2)
          AND ($3::text IS NULL OR symbol = $3)
        ORDER BY triggered_at DESC
        LIMIT $4 OFFSET $5
        "#,
    )
    .bind(query.pool_id)
    .bind(query.signal_id)
    .bind(query.symbol.as_deref())
    .bind(query.limit)
    .bind(query.offset)
    .fetch_all(&state.db)
    .await
    .map_err(|error| AppError::internal(format!("Failed to get trigger logs: {error}")))?;

    let logs = rows
        .into_iter()
        .map(|row| {
            Ok(SignalTriggerLogResponse {
                id: row.try_get("id").map_err(read_signal_error)?,
                signal_id: row.try_get("signal_id").map_err(read_signal_error)?,
                pool_id: row.try_get("pool_id").map_err(read_signal_error)?,
                symbol: row.try_get("symbol").map_err(read_signal_error)?,
                trigger_value: parse_optional_json(
                    row.try_get::<Option<String>, _>("trigger_value")
                        .map_err(read_signal_error)?,
                ),
                triggered_at: row
                    .try_get::<NaiveDateTime, _>("triggered_at")
                    .map_err(read_signal_error)?
                    .format("%Y-%m-%dT%H:%M:%S%.f")
                    .to_string(),
                market_regime: parse_optional_json(
                    row.try_get::<Option<String>, _>("market_regime")
                        .map_err(read_signal_error)?,
                ),
            })
        })
        .collect::<Result<Vec<_>, AppError>>()?;

    let total = sqlx::query_scalar::<_, i64>(
        r#"
        SELECT COUNT(*)::bigint
        FROM signal_trigger_logs
        WHERE ($1::int4 IS NULL OR pool_id = $1)
          AND ($2::int4 IS NULL OR signal_id = $2)
          AND ($3::text IS NULL OR symbol = $3)
        "#,
    )
    .bind(query.pool_id)
    .bind(query.signal_id)
    .bind(query.symbol.as_deref())
    .fetch_one(&state.db)
    .await
    .map_err(|error| AppError::internal(format!("Failed to count trigger logs: {error}")))?;

    Ok(Json(SignalTriggerLogsResponse { logs, total }))
}

fn row_to_signal_definition(
    row: sqlx::postgres::PgRow,
) -> Result<SignalDefinitionResponse, AppError> {
    Ok(SignalDefinitionResponse {
        id: row.try_get("id").map_err(read_signal_error)?,
        signal_name: row.try_get("signal_name").map_err(read_signal_error)?,
        description: row.try_get("description").map_err(read_signal_error)?,
        trigger_condition: parse_json_or_default(
            row.try_get::<Option<String>, _>("trigger_condition")
                .map_err(read_signal_error)?,
            Value::Object(Default::default()),
        ),
        enabled: row
            .try_get::<Option<bool>, _>("enabled")
            .map_err(read_signal_error)?
            .unwrap_or(true),
        exchange: row
            .try_get::<Option<String>, _>("exchange")
            .map_err(read_signal_error)?
            .unwrap_or_else(default_exchange),
        created_at: row
            .try_get::<NaiveDateTime, _>("created_at")
            .map_err(read_signal_error)?
            .format("%Y-%m-%dT%H:%M:%S%.f")
            .to_string(),
        updated_at: row
            .try_get::<NaiveDateTime, _>("updated_at")
            .map_err(read_signal_error)?
            .format("%Y-%m-%dT%H:%M:%S%.f")
            .to_string(),
    })
}

fn row_to_signal_pool(row: sqlx::postgres::PgRow) -> Result<SignalPoolResponse, AppError> {
    let source_type = row
        .try_get::<Option<String>, _>("source_type")
        .map_err(read_signal_error)?
        .unwrap_or_else(default_market_source);
    Ok(SignalPoolResponse {
        id: row.try_get("id").map_err(read_signal_error)?,
        pool_name: row.try_get("pool_name").map_err(read_signal_error)?,
        signal_ids: parse_i32_list(
            row.try_get::<Option<String>, _>("signal_ids")
                .map_err(read_signal_error)?
                .as_deref(),
        ),
        symbols: parse_string_list(
            row.try_get::<Option<String>, _>("symbols")
                .map_err(read_signal_error)?
                .as_deref(),
        ),
        enabled: row
            .try_get::<Option<bool>, _>("enabled")
            .map_err(read_signal_error)?
            .unwrap_or(true),
        created_at: row
            .try_get::<NaiveDateTime, _>("created_at")
            .map_err(read_signal_error)?
            .format("%Y-%m-%dT%H:%M:%S%.f")
            .to_string(),
        logic: row
            .try_get::<Option<String>, _>("logic")
            .map_err(read_signal_error)?
            .unwrap_or_else(default_logic),
        exchange: row
            .try_get::<Option<String>, _>("exchange")
            .map_err(read_signal_error)?
            .unwrap_or_else(default_exchange),
        source_type: source_type.clone(),
        source_config: parse_source_config_response(
            &source_type,
            row.try_get::<Option<String>, _>("source_config")
                .map_err(read_signal_error)?,
        ),
    })
}

async fn load_signal_pools(pool: &sqlx::PgPool) -> Result<Vec<SignalPoolResponse>, AppError> {
    let rows = sqlx::query(
        r#"
        SELECT id, pool_name, signal_ids, symbols, enabled, created_at, logic, exchange, source_type, source_config
        FROM signal_pools
        WHERE (is_deleted IS NULL OR is_deleted = false)
        ORDER BY id
        "#,
    )
    .fetch_all(pool)
    .await
    .map_err(|error| AppError::internal(format!("Failed to load signal pools: {error}")))?;

    rows.into_iter()
        .map(row_to_signal_pool)
        .collect::<Result<Vec<_>, _>>()
}

async fn load_signal_pool_by_id(
    state: &AppState,
    pool_id: i32,
) -> Result<SignalPoolResponse, AppError> {
    let row = load_signal_pool_row(state, pool_id)
        .await?
        .ok_or_else(|| AppError::not_found("Pool not found"))?;
    row_to_signal_pool(row)
}

async fn load_signal_pool_row(
    state: &AppState,
    pool_id: i32,
) -> Result<Option<sqlx::postgres::PgRow>, AppError> {
    sqlx::query(
        r#"
        SELECT id, pool_name, signal_ids, symbols, enabled, created_at, logic, exchange, source_type, source_config
        FROM signal_pools
        WHERE id = $1 AND (is_deleted IS NULL OR is_deleted = false)
        "#,
    )
    .bind(pool_id)
    .fetch_optional(&state.db)
    .await
    .map_err(|error| AppError::internal(format!("Failed to load signal pool: {error}")))
}

async fn validate_signal_exchange(
    state: &AppState,
    signal_ids: &[i32],
    pool_exchange: &str,
) -> Result<(), AppError> {
    if signal_ids.is_empty() {
        return Ok(());
    }

    let rows = sqlx::query(
        r#"
        SELECT id, exchange
        FROM signal_definitions
        WHERE id = ANY($1)
          AND (is_deleted IS NULL OR is_deleted = false)
        "#,
    )
    .bind(signal_ids)
    .fetch_all(&state.db)
    .await
    .map_err(|error| AppError::internal(format!("Failed to validate signals: {error}")))?;

    for row in rows {
        let signal_exchange = row
            .try_get::<Option<String>, _>("exchange")
            .map_err(read_signal_error)?
            .unwrap_or_else(default_exchange);
        if signal_exchange != pool_exchange {
            return Err(AppError::bad_request(format!(
                "Signal {} belongs to {}, but pool is for {}",
                row.try_get::<i32, _>("id").map_err(read_signal_error)?,
                signal_exchange,
                pool_exchange
            )));
        }
    }
    Ok(())
}

async fn load_signal_pool_dependencies(
    state: &AppState,
    pool_id: i32,
) -> Result<Vec<String>, AppError> {
    let mut deps = Vec::new();

    let strategy_rows = sqlx::query(
        r#"
        SELECT s.signal_pool_ids, a.name
        FROM account_strategy_configs s
        LEFT JOIN accounts a ON a.id = s.account_id
        "#,
    )
    .fetch_all(&state.db)
    .await
    .map_err(|error| {
        AppError::internal(format!("Failed to load strategy dependencies: {error}"))
    })?;
    for row in strategy_rows {
        let ids = parse_i32_list(
            row.try_get::<Option<String>, _>("signal_pool_ids")
                .ok()
                .flatten()
                .as_deref(),
        );
        if ids.contains(&pool_id) {
            let name = row
                .try_get::<Option<String>, _>("name")
                .map_err(read_signal_error)?
                .unwrap_or_else(|| "unknown".to_owned());
            deps.push(format!("Used by AI Strategy of Trader: {name}"));
        }
    }

    let binding_rows = sqlx::query(
        r#"
        SELECT id, program_id, signal_pool_ids
        FROM account_program_bindings
        WHERE is_deleted IS DISTINCT FROM true
        "#,
    )
    .fetch_all(&state.db)
    .await
    .map_err(|error| {
        AppError::internal(format!(
            "Failed to load program binding dependencies: {error}"
        ))
    })?;
    for row in binding_rows {
        let ids = parse_i32_list(
            row.try_get::<Option<String>, _>("signal_pool_ids")
                .ok()
                .flatten()
                .as_deref(),
        );
        if ids.contains(&pool_id) {
            deps.push(format!(
                "Used by Program Binding #{} (program #{})",
                row.try_get::<i32, _>("id").map_err(read_signal_error)?,
                row.try_get::<i32, _>("program_id")
                    .map_err(read_signal_error)?,
            ));
        }
    }

    let trigger_rows = sqlx::query(
        r#"
        SELECT trader_id, signal_pool_ids
        FROM trader_trigger_config
        "#,
    )
    .fetch_all(&state.db)
    .await
    .map_err(|error| AppError::internal(format!("Failed to load trigger dependencies: {error}")))?;
    for row in trigger_rows {
        let ids = parse_i32_list(
            row.try_get::<Option<String>, _>("signal_pool_ids")
                .ok()
                .flatten()
                .as_deref(),
        );
        if ids.contains(&pool_id) {
            deps.push(format!(
                "Used by TraderTriggerConfig: {}",
                row.try_get::<String, _>("trader_id")
                    .map_err(read_signal_error)?,
            ));
        }
    }

    Ok(deps)
}

async fn sync_wallet_runtime_refresh(_state: &AppState) {
    wallet_tracking_runtime::request_refresh();
}

async fn apply_wallet_tracking_runtime_update(
    state: &AppState,
    payload: WalletTrackingRuntimeRequest,
) -> Result<WalletTrackingStatusResponse, AppError> {
    set_system_config_value(
        &state.db,
        WALLET_TRACKING_ENABLED_KEY,
        if payload.enabled { "true" } else { "false" },
        Some(WALLET_TRACKING_ENABLED_DESCRIPTION),
    )
    .await?;

    if let Some(access_token) = payload.access_token.filter(|value| !value.is_empty()) {
        sync_wallet_tracking_access_token(state, &access_token).await?;
    }

    wallet_tracking_runtime::request_refresh();
    get_wallet_tracking_status_snapshot(state).await
}

async fn sync_wallet_tracking_access_token(
    state: &AppState,
    access_token: &str,
) -> Result<(), AppError> {
    set_system_config_value(
        &state.db,
        WALLET_TRACKING_ACCESS_TOKEN_KEY,
        access_token,
        Some(WALLET_TRACKING_ACCESS_TOKEN_DESCRIPTION),
    )
    .await?;
    let timestamp = chrono::Utc::now()
        .naive_utc()
        .format("%Y-%m-%dT%H:%M:%S%.f")
        .to_string();
    set_system_config_value(
        &state.db,
        WALLET_TRACKING_TOKEN_SYNCED_AT_KEY,
        &timestamp,
        Some(WALLET_TRACKING_TOKEN_SYNCED_AT_DESCRIPTION),
    )
    .await?;
    wallet_tracking_runtime::request_refresh();
    Ok(())
}

async fn clear_wallet_tracking_access_token(state: &AppState) -> Result<(), AppError> {
    set_system_config_value(
        &state.db,
        WALLET_TRACKING_ACCESS_TOKEN_KEY,
        "",
        Some(WALLET_TRACKING_ACCESS_TOKEN_DESCRIPTION),
    )
    .await?;
    wallet_tracking_runtime::request_refresh();
    Ok(())
}

async fn get_wallet_tracking_status_snapshot(
    state: &AppState,
) -> Result<WalletTrackingStatusResponse, AppError> {
    let enabled = load_system_config_value(&state.db, WALLET_TRACKING_ENABLED_KEY)
        .await?
        .as_deref()
        == Some("true");
    let has_access_token = load_system_config_value(&state.db, WALLET_TRACKING_ACCESS_TOKEN_KEY)
        .await?
        .as_deref()
        .map(str::trim)
        .is_some_and(|value| !value.is_empty());
    let token_synced_at = load_system_config_value(&state.db, WALLET_TRACKING_TOKEN_SYNCED_AT_KEY)
        .await?
        .filter(|value| !value.trim().is_empty());
    let active_wallet_pool_count = count_enabled_wallet_tracking_pools(&state.db).await?;

    let runtime_snapshot = wallet_tracking_runtime::snapshot().await;
    let status = wallet_tracking_status(enabled, has_access_token, &runtime_snapshot.status);
    let has_runtime_connection = has_access_token && status == "connected";

    Ok(WalletTrackingStatusResponse {
        enabled,
        status,
        tier: if has_runtime_connection {
            runtime_snapshot.tier
        } else {
            None
        },
        synced_addresses: if has_runtime_connection {
            runtime_snapshot.synced_addresses
        } else {
            Vec::new()
        },
        last_connected_at: if has_access_token {
            runtime_snapshot.last_connected_at
        } else {
            None
        },
        last_message_at: if has_access_token {
            runtime_snapshot.last_message_at
        } else {
            None
        },
        last_event_at: if has_access_token {
            runtime_snapshot.last_event_at
        } else {
            None
        },
        last_error: if has_access_token {
            runtime_snapshot.last_error
        } else {
            None
        },
        active_wallet_pool_count,
        token_synced_at,
    })
}

async fn set_system_config_value(
    pool: &sqlx::PgPool,
    key: &str,
    value: &str,
    description: Option<&str>,
) -> Result<(), AppError> {
    sqlx::query(
        r#"
        INSERT INTO system_configs (key, value, description, created_at, updated_at)
        VALUES ($1, $2, $3, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        ON CONFLICT (key)
        DO UPDATE SET
            value = EXCLUDED.value,
            description = COALESCE(system_configs.description, EXCLUDED.description),
            updated_at = CURRENT_TIMESTAMP
        "#,
    )
    .bind(key)
    .bind(value)
    .bind(description)
    .execute(pool)
    .await
    .map(|_| ())
    .map_err(|error| AppError::internal(format!("Failed to set system config {key}: {error}")))
}

async fn load_system_config_value(
    pool: &sqlx::PgPool,
    key: &str,
) -> Result<Option<String>, AppError> {
    sqlx::query_scalar::<_, Option<String>>(
        "SELECT value FROM system_configs WHERE key = $1 LIMIT 1",
    )
    .bind(key)
    .fetch_optional(pool)
    .await
    .map(|value| value.flatten())
    .map_err(|error| AppError::internal(format!("Failed to load system config {key}: {error}")))
}

async fn count_enabled_wallet_tracking_pools(pool: &sqlx::PgPool) -> Result<i64, AppError> {
    sqlx::query_scalar::<_, i64>(
        r#"
        SELECT COUNT(*)::bigint
        FROM signal_pools
        WHERE enabled = true
          AND (is_deleted IS NULL OR is_deleted = false)
          AND source_type = $1
        "#,
    )
    .bind(WALLET_TRACKING_SOURCE)
    .fetch_one(pool)
    .await
    .map_err(|error| AppError::internal(format!("Failed to count wallet tracking pools: {error}")))
}

async fn load_signal_states_cache_info(
    pool: &sqlx::PgPool,
) -> Result<SignalStatesCacheInfo, AppError> {
    let pools_count = count_enabled_market_signal_pools(pool).await?;
    let signals_count = count_enabled_signal_definitions(pool).await?;

    Ok(SignalStatesCacheInfo {
        pools_count,
        signals_count,
    })
}

fn snapshot_signal_runtime_states() -> SignalStatesPayload {
    let store = SIGNAL_RUNTIME_STATE_STORE
        .read()
        .unwrap_or_else(|poisoned| poisoned.into_inner());
    let signal_states = store
        .signal_states
        .iter()
        .map(|((signal_id, symbol), state)| {
            (
                format!("{signal_id}:{symbol}"),
                SignalStateEntry {
                    is_active: state.is_active,
                    last_value: state.last_value,
                    last_check_time: state.last_check_time,
                },
            )
        })
        .collect::<BTreeMap<_, _>>();
    let pool_states = store
        .pool_states
        .iter()
        .map(|((pool_id, symbol), state)| {
            (
                format!("{pool_id}:{symbol}"),
                PoolStateEntry {
                    is_active: state.is_active,
                    signal_conditions_met: state.signal_conditions_met.clone(),
                    last_check_time: state.last_check_time,
                },
            )
        })
        .collect::<BTreeMap<_, _>>();

    SignalStatesPayload {
        signal_states,
        pool_states,
    }
}

fn reset_signal_runtime_states(query: ResetSignalStatesQuery) {
    let mut store = SIGNAL_RUNTIME_STATE_STORE
        .write()
        .unwrap_or_else(|poisoned| poisoned.into_inner());
    apply_signal_state_reset(&mut store, &query);
}

pub(crate) fn project_wallet_trigger_into_runtime_states(
    pool_id: i32,
    symbol: &str,
    signal_ids: &[i32],
    event_type: &str,
    triggered_at: NaiveDateTime,
) {
    let mut store = SIGNAL_RUNTIME_STATE_STORE
        .write()
        .unwrap_or_else(|poisoned| poisoned.into_inner());
    apply_wallet_runtime_state_projection(
        &mut store,
        pool_id,
        symbol,
        signal_ids,
        event_type,
        triggered_at,
    );
}

fn apply_signal_state_reset(store: &mut SignalRuntimeStateStore, query: &ResetSignalStatesQuery) {
    if query.signal_id.is_none() && query.pool_id.is_none() && query.symbol.is_none() {
        store.signal_states.clear();
        store.pool_states.clear();
        return;
    }

    if query.signal_id.is_some() || query.symbol.is_some() {
        store.signal_states.retain(|(signal_id, symbol), _| {
            let signal_match = query
                .signal_id
                .as_ref()
                .map(|id| *id == *signal_id)
                .unwrap_or(true);
            let symbol_match = query
                .symbol
                .as_ref()
                .map(|value| value == symbol)
                .unwrap_or(true);
            !(signal_match && symbol_match)
        });
    }

    if query.pool_id.is_some() || query.symbol.is_some() {
        store.pool_states.retain(|(pool_id, symbol), _| {
            let pool_match = query
                .pool_id
                .as_ref()
                .map(|id| *id == *pool_id)
                .unwrap_or(true);
            let symbol_match = query
                .symbol
                .as_ref()
                .map(|value| value == symbol)
                .unwrap_or(true);
            !(pool_match && symbol_match)
        });
    }
}

fn apply_wallet_runtime_state_projection(
    store: &mut SignalRuntimeStateStore,
    pool_id: i32,
    symbol: &str,
    signal_ids: &[i32],
    event_type: &str,
    triggered_at: NaiveDateTime,
) {
    if pool_id <= 0 {
        return;
    }

    let normalized_symbol = symbol.trim();
    if normalized_symbol.is_empty() {
        return;
    }

    let symbol_key = normalized_symbol.to_owned();
    let last_check_time = triggered_at.and_utc().timestamp_millis() as f64 / 1000.0;
    let mut signal_conditions_met = BTreeMap::new();

    for signal_id in signal_ids.iter().copied().filter(|value| *value > 0) {
        store.signal_states.insert(
            (signal_id, symbol_key.clone()),
            RuntimeSignalState {
                is_active: true,
                last_value: None,
                last_check_time,
            },
        );
        signal_conditions_met.insert(signal_id.to_string(), true);
    }

    if signal_conditions_met.is_empty() {
        signal_conditions_met.insert("wallet_event".to_owned(), true);
    }

    let normalized_event_type = event_type.trim();
    if !normalized_event_type.is_empty() {
        signal_conditions_met.insert(format!("wallet_event:{normalized_event_type}"), true);
    }

    store.pool_states.insert(
        (pool_id, symbol_key),
        RuntimePoolState {
            is_active: true,
            signal_conditions_met,
            last_check_time,
        },
    );
}

async fn count_enabled_market_signal_pools(pool: &sqlx::PgPool) -> Result<i64, AppError> {
    sqlx::query_scalar::<_, i64>(
        r#"
        SELECT COUNT(*)::bigint
        FROM signal_pools
        WHERE enabled = true
          AND (is_deleted IS NULL OR is_deleted = false)
          AND COALESCE(source_type, $1) = $1
        "#,
    )
    .bind(MARKET_SIGNAL_SOURCE)
    .fetch_one(pool)
    .await
    .map_err(|error| AppError::internal(format!("Failed to count market signal pools: {error}")))
}

async fn count_enabled_signal_definitions(pool: &sqlx::PgPool) -> Result<i64, AppError> {
    sqlx::query_scalar::<_, i64>(
        r#"
        SELECT COUNT(*)::bigint
        FROM signal_definitions
        WHERE enabled = true
          AND (is_deleted IS NULL OR is_deleted = false)
        "#,
    )
    .fetch_one(pool)
    .await
    .map_err(|error| {
        AppError::internal(format!(
            "Failed to count enabled signal definitions: {error}"
        ))
    })
}

async fn analyze_signal_metric(pool: &sqlx::PgPool, query: SignalAnalyzeQuery) -> Value {
    let metric = normalize_signal_analysis_metric(&query.metric);
    let result = if metric == "taker_volume" {
        analyze_taker_volume_metric(
            pool,
            &query.symbol,
            &query.period,
            query.days,
            &query.exchange,
        )
        .await
    } else {
        analyze_standard_signal_metric(
            pool,
            &query.symbol,
            &metric,
            &query.period,
            query.days,
            &query.exchange,
        )
        .await
    };

    match result {
        Ok(payload) => payload,
        Err(message) => serde_json::json!({
            "status": "error",
            "message": message,
        }),
    }
}

async fn analyze_standard_signal_metric(
    pool: &sqlx::PgPool,
    symbol: &str,
    metric: &str,
    period: &str,
    days: i64,
    exchange: &str,
) -> Result<Value, String> {
    let (values, time_range_hours) =
        load_signal_metric_history(pool, symbol, metric, period, days, exchange).await?;

    if values.len() < MIN_SIGNAL_ANALYSIS_SAMPLES {
        return Ok(serde_json::json!({
            "status": "insufficient_data",
            "message": format!(
                "Need at least {MIN_SIGNAL_ANALYSIS_SAMPLES} samples, found {}",
                values.len()
            ),
            "sample_count": values.len(),
            "required_samples": MIN_SIGNAL_ANALYSIS_SAMPLES,
        }));
    }

    let precision = if metric == "funding" { 2 } else { 4 };
    if metric == "funding" {
        let non_zero_values = values
            .iter()
            .copied()
            .filter(|value| value.abs() > 0.01)
            .collect::<Vec<_>>();

        let mut stats = if non_zero_values.len() < MIN_SIGNAL_ANALYSIS_SAMPLES {
            calculate_metric_statistics(&values, precision)
        } else {
            let mut active_stats = calculate_metric_statistics(&non_zero_values, precision);
            active_stats.min = round_to(
                values.iter().copied().fold(f64::INFINITY, f64::min),
                precision,
            );
            active_stats.max = round_to(
                values.iter().copied().fold(f64::NEG_INFINITY, f64::max),
                precision,
            );
            active_stats
        };

        if !stats.min.is_finite() {
            stats.min = 0.0;
        }
        if !stats.max.is_finite() {
            stats.max = 0.0;
        }

        let suggestions = generate_signal_threshold_suggestions(&stats, metric);
        let zero_pct =
            ((values.len() - non_zero_values.len()) as f64 / values.len() as f64) * 100.0;

        let mut response = Map::new();
        response.insert("status".to_owned(), Value::String("ok".to_owned()));
        response.insert("symbol".to_owned(), Value::String(symbol.to_owned()));
        response.insert("metric".to_owned(), Value::String(metric.to_owned()));
        response.insert("period".to_owned(), Value::String(period.to_owned()));
        response.insert(
            "sample_count".to_owned(),
            Value::from(i64::try_from(values.len()).unwrap_or(0)),
        );
        response.insert(
            "active_samples".to_owned(),
            Value::from(i64::try_from(non_zero_values.len()).unwrap_or(0)),
        );
        response.insert("time_range_hours".to_owned(), Value::from(time_range_hours));
        response.insert(
            "statistics".to_owned(),
            serde_json::to_value(stats).unwrap_or(Value::Null),
        );
        response.insert(
            "suggestions".to_owned(),
            serde_json::to_value(suggestions).unwrap_or(Value::Null),
        );
        if zero_pct > 50.0 {
            response.insert(
                "info".to_owned(),
                Value::String(format!(
                    "Funding rate is stable {:.0}% of the time. Thresholds based on {} active change periods.",
                    zero_pct,
                    non_zero_values.len()
                )),
            );
        }
        return Ok(Value::Object(response));
    }

    let stats = calculate_metric_statistics(&values, precision);
    let suggestions = generate_signal_threshold_suggestions(&stats, metric);
    let mut response = Map::new();
    response.insert("status".to_owned(), Value::String("ok".to_owned()));
    response.insert("symbol".to_owned(), Value::String(symbol.to_owned()));
    response.insert("metric".to_owned(), Value::String(metric.to_owned()));
    response.insert("period".to_owned(), Value::String(period.to_owned()));
    response.insert(
        "sample_count".to_owned(),
        Value::from(i64::try_from(values.len()).unwrap_or(0)),
    );
    response.insert("time_range_hours".to_owned(), Value::from(time_range_hours));
    response.insert(
        "statistics".to_owned(),
        serde_json::to_value(stats).unwrap_or(Value::Null),
    );
    response.insert(
        "suggestions".to_owned(),
        serde_json::to_value(suggestions).unwrap_or(Value::Null),
    );
    if values.len() < LIMITED_SIGNAL_ANALYSIS_DATA_THRESHOLD {
        response.insert(
            "warning".to_owned(),
            Value::String(format!(
                "Limited data ({} samples). Statistics may not be representative.",
                values.len()
            )),
        );
    }
    Ok(Value::Object(response))
}

async fn analyze_taker_volume_metric(
    pool: &sqlx::PgPool,
    symbol: &str,
    period: &str,
    days: i64,
    exchange: &str,
) -> Result<Value, String> {
    let interval_ms = signal_analysis_timeframe_ms(period)
        .ok_or_else(|| format!("Unsupported period: {period}"))?;
    let current_time_ms = Utc::now().timestamp_millis();
    let start_time_ms = current_time_ms.saturating_sub(days.saturating_mul(DAY_MS));
    let symbol_upper = symbol.to_uppercase();

    let rows = sqlx::query(
        r#"
        SELECT timestamp,
               taker_buy_notional::float8 AS taker_buy_notional,
               taker_sell_notional::float8 AS taker_sell_notional
        FROM market_trades_aggregated
        WHERE exchange = $1
          AND symbol = $2
          AND timestamp >= $3
          AND timestamp <= $4
        ORDER BY timestamp
        "#,
    )
    .bind(exchange)
    .bind(&symbol_upper)
    .bind(start_time_ms)
    .bind(current_time_ms)
    .fetch_all(pool)
    .await
    .map_err(|error| format!("Failed to load taker volume history: {error}"))?;

    if rows.is_empty() {
        return Ok(serde_json::json!({
            "status": "insufficient_data",
            "message": "No data available",
        }));
    }

    let mut buckets = BTreeMap::<i64, (f64, f64)>::new();
    for row in rows {
        let timestamp = row
            .try_get::<i64, _>("timestamp")
            .map_err(read_signal_metric_error)?;
        let buy = row
            .try_get::<Option<f64>, _>("taker_buy_notional")
            .map_err(read_signal_metric_error)?
            .unwrap_or(0.0);
        let sell = row
            .try_get::<Option<f64>, _>("taker_sell_notional")
            .map_err(read_signal_metric_error)?
            .unwrap_or(0.0);
        let bucket = floor_timestamp(timestamp, interval_ms);
        let entry = buckets.entry(bucket).or_insert((0.0, 0.0));
        entry.0 += buy;
        entry.1 += sell;
    }

    let sorted_times = buckets.keys().copied().collect::<Vec<_>>();
    if sorted_times.len() < MIN_SIGNAL_ANALYSIS_SAMPLES {
        return Ok(serde_json::json!({
            "status": "insufficient_data",
            "message": format!(
                "Need at least {MIN_SIGNAL_ANALYSIS_SAMPLES} samples, found {}",
                sorted_times.len()
            ),
        }));
    }

    let mut ratios = Vec::new();
    let mut volumes = Vec::new();
    for timestamp in &sorted_times {
        let (buy, sell) = buckets.get(timestamp).copied().unwrap_or((0.0, 0.0));
        let total = buy + sell;
        if total > 0.0 && buy > 0.0 && sell > 0.0 {
            ratios.push((buy / sell).ln());
            volumes.push(total);
        }
    }

    if ratios.len() < MIN_SIGNAL_ANALYSIS_SAMPLES {
        return Ok(serde_json::json!({
            "status": "insufficient_data",
            "message": format!("Need at least {MIN_SIGNAL_ANALYSIS_SAMPLES} valid samples"),
        }));
    }

    let ratio_p75 = round_to(percentile_linear(&ratios, 75.0), 2);
    let ratio_p90 = round_to(percentile_linear(&ratios, 90.0), 2);
    let ratio_p95 = round_to(percentile_linear(&ratios, 95.0), 2);
    let ratio_stats = serde_json::json!({
        "mean": round_to(mean(&ratios), 2),
        "min": round_to(ratios.iter().copied().fold(f64::INFINITY, f64::min), 2),
        "max": round_to(ratios.iter().copied().fold(f64::NEG_INFINITY, f64::max), 2),
        "p75": ratio_p75,
        "p90": ratio_p90,
        "p95": ratio_p95,
    });

    let volume_p25 = round_to(percentile_linear(&volumes, 25.0), 0);
    let volume_p50 = round_to(percentile_linear(&volumes, 50.0), 0);
    let volume_p75 = round_to(percentile_linear(&volumes, 75.0), 0);
    let volume_stats = serde_json::json!({
        "mean": round_to(mean(&volumes), 0),
        "min": round_to(volumes.iter().copied().fold(f64::INFINITY, f64::min), 0),
        "max": round_to(volumes.iter().copied().fold(f64::NEG_INFINITY, f64::max), 0),
        "p25": volume_p25,
        "p50": volume_p50,
        "p75": volume_p75,
    });

    let time_range_hours =
        if let (Some(first), Some(last)) = (sorted_times.first(), sorted_times.last()) {
            (*last - *first) as f64 / (60.0 * 60.0 * 1000.0)
        } else {
            0.0
        };

    Ok(serde_json::json!({
        "status": "ok",
        "symbol": symbol,
        "metric": "taker_volume",
        "period": format!("{}m", interval_ms / 60_000),
        "sample_count": ratios.len(),
        "time_range_hours": round_to(time_range_hours, 1),
        "ratio_statistics": ratio_stats,
        "volume_statistics": volume_stats,
        "suggestions": {
            "ratio": {
                "aggressive": round_to(ratio_p75.abs().exp(), 2),
                "moderate": round_to(ratio_p90.abs().exp(), 2),
                "conservative": round_to(ratio_p95.abs().exp(), 2)
            },
            "volume": {
                "low": volume_p25,
                "medium": volume_p50,
                "high": volume_p75
            }
        }
    }))
}

async fn load_signal_metric_history(
    pool: &sqlx::PgPool,
    symbol: &str,
    metric: &str,
    period: &str,
    days: i64,
    exchange: &str,
) -> Result<(Vec<f64>, f64), String> {
    let interval_ms = signal_analysis_timeframe_ms(period)
        .ok_or_else(|| format!("Unsupported period: {period}"))?;
    let current_time_ms = Utc::now().timestamp_millis();
    let start_time_ms = current_time_ms.saturating_sub(days.saturating_mul(DAY_MS));
    let symbol_upper = symbol.to_uppercase();

    let (values, min_ts, max_ts) = match metric {
        "oi_delta" => {
            load_oi_delta_history(
                pool,
                &symbol_upper,
                interval_ms,
                start_time_ms,
                current_time_ms,
                exchange,
            )
            .await?
        }
        "cvd" => {
            load_cvd_history(
                pool,
                &symbol_upper,
                interval_ms,
                start_time_ms,
                current_time_ms,
                exchange,
            )
            .await?
        }
        "depth_ratio" => {
            load_depth_ratio_history(
                pool,
                &symbol_upper,
                interval_ms,
                start_time_ms,
                current_time_ms,
                exchange,
            )
            .await?
        }
        "order_imbalance" => {
            load_order_imbalance_history(
                pool,
                &symbol_upper,
                interval_ms,
                start_time_ms,
                current_time_ms,
                exchange,
            )
            .await?
        }
        "taker_ratio" => {
            load_taker_ratio_history(
                pool,
                &symbol_upper,
                interval_ms,
                start_time_ms,
                current_time_ms,
                exchange,
            )
            .await?
        }
        "funding" => {
            load_funding_history(
                pool,
                &symbol_upper,
                interval_ms,
                start_time_ms,
                current_time_ms,
                exchange,
            )
            .await?
        }
        "oi" => {
            load_oi_history(
                pool,
                &symbol_upper,
                interval_ms,
                start_time_ms,
                current_time_ms,
                exchange,
            )
            .await?
        }
        "price_change" => {
            load_price_change_history(
                pool,
                &symbol_upper,
                interval_ms,
                start_time_ms,
                current_time_ms,
                exchange,
            )
            .await?
        }
        "volatility" => {
            load_volatility_history(
                pool,
                &symbol_upper,
                interval_ms,
                start_time_ms,
                current_time_ms,
                exchange,
            )
            .await?
        }
        _ => return Err(format!("Unsupported metric: {metric}")),
    };

    let time_range_hours = match (min_ts, max_ts) {
        (Some(min_ts), Some(max_ts)) => (max_ts - min_ts) as f64 / (60.0 * 60.0 * 1000.0),
        _ => 0.0,
    };

    Ok((values, time_range_hours))
}

async fn load_oi_delta_history(
    pool: &sqlx::PgPool,
    symbol: &str,
    interval_ms: i64,
    start_time_ms: i64,
    current_time_ms: i64,
    exchange: &str,
) -> Result<(Vec<f64>, Option<i64>, Option<i64>), String> {
    let rows = sqlx::query(
        r#"
        SELECT timestamp, open_interest::float8 AS open_interest
        FROM market_asset_metrics
        WHERE exchange = $1
          AND symbol = $2
          AND timestamp >= $3
          AND timestamp <= $4
        ORDER BY timestamp
        "#,
    )
    .bind(exchange)
    .bind(symbol)
    .bind(start_time_ms)
    .bind(current_time_ms)
    .fetch_all(pool)
    .await
    .map_err(|error| format!("Failed to load oi_delta history: {error}"))?;

    if rows.is_empty() {
        return Ok((Vec::new(), None, None));
    }

    let mut buckets = BTreeMap::<i64, Option<f64>>::new();
    for row in rows {
        let timestamp = row
            .try_get::<i64, _>("timestamp")
            .map_err(read_signal_metric_error)?;
        let open_interest = row
            .try_get::<Option<f64>, _>("open_interest")
            .map_err(read_signal_metric_error)?;
        buckets.insert(floor_timestamp(timestamp, interval_ms), open_interest);
    }

    let times = buckets.keys().copied().collect::<Vec<_>>();
    let mut values = Vec::new();
    for pair in times.windows(2) {
        let prev = buckets.get(&pair[0]).and_then(|value| *value);
        let curr = buckets.get(&pair[1]).and_then(|value| *value);
        if let (Some(prev_oi), Some(curr_oi)) = (prev, curr)
            && prev_oi != 0.0
        {
            values.push(((curr_oi - prev_oi) / prev_oi) * 100.0);
        }
    }

    Ok((values, times.first().copied(), times.last().copied()))
}

async fn load_cvd_history(
    pool: &sqlx::PgPool,
    symbol: &str,
    interval_ms: i64,
    start_time_ms: i64,
    current_time_ms: i64,
    exchange: &str,
) -> Result<(Vec<f64>, Option<i64>, Option<i64>), String> {
    let rows = sqlx::query(
        r#"
        SELECT timestamp,
               taker_buy_notional::float8 AS taker_buy_notional,
               taker_sell_notional::float8 AS taker_sell_notional
        FROM market_trades_aggregated
        WHERE exchange = $1
          AND symbol = $2
          AND timestamp >= $3
          AND timestamp <= $4
        ORDER BY timestamp
        "#,
    )
    .bind(exchange)
    .bind(symbol)
    .bind(start_time_ms)
    .bind(current_time_ms)
    .fetch_all(pool)
    .await
    .map_err(|error| format!("Failed to load cvd history: {error}"))?;

    if rows.is_empty() {
        return Ok((Vec::new(), None, None));
    }

    let mut buckets = BTreeMap::<i64, (f64, f64)>::new();
    for row in rows {
        let timestamp = row
            .try_get::<i64, _>("timestamp")
            .map_err(read_signal_metric_error)?;
        let buy = row
            .try_get::<Option<f64>, _>("taker_buy_notional")
            .map_err(read_signal_metric_error)?
            .unwrap_or(0.0);
        let sell = row
            .try_get::<Option<f64>, _>("taker_sell_notional")
            .map_err(read_signal_metric_error)?
            .unwrap_or(0.0);
        let bucket = floor_timestamp(timestamp, interval_ms);
        let entry = buckets.entry(bucket).or_insert((0.0, 0.0));
        entry.0 += buy;
        entry.1 += sell;
    }

    let times = buckets.keys().copied().collect::<Vec<_>>();
    let values = times
        .iter()
        .map(|timestamp| {
            let (buy, sell) = buckets.get(timestamp).copied().unwrap_or((0.0, 0.0));
            buy - sell
        })
        .collect::<Vec<_>>();

    Ok((values, times.first().copied(), times.last().copied()))
}

async fn load_depth_ratio_history(
    pool: &sqlx::PgPool,
    symbol: &str,
    interval_ms: i64,
    start_time_ms: i64,
    current_time_ms: i64,
    exchange: &str,
) -> Result<(Vec<f64>, Option<i64>, Option<i64>), String> {
    let rows = sqlx::query(
        r#"
        SELECT timestamp,
               bid_depth_5::float8 AS bid_depth_5,
               ask_depth_5::float8 AS ask_depth_5
        FROM market_orderbook_snapshots
        WHERE exchange = $1
          AND symbol = $2
          AND timestamp >= $3
          AND timestamp <= $4
        ORDER BY timestamp
        "#,
    )
    .bind(exchange)
    .bind(symbol)
    .bind(start_time_ms)
    .bind(current_time_ms)
    .fetch_all(pool)
    .await
    .map_err(|error| format!("Failed to load depth ratio history: {error}"))?;

    if rows.is_empty() {
        return Ok((Vec::new(), None, None));
    }

    let mut buckets = BTreeMap::<i64, (f64, f64)>::new();
    for row in rows {
        let timestamp = row
            .try_get::<i64, _>("timestamp")
            .map_err(read_signal_metric_error)?;
        let bid = row
            .try_get::<Option<f64>, _>("bid_depth_5")
            .map_err(read_signal_metric_error)?
            .unwrap_or(0.0);
        let ask = row
            .try_get::<Option<f64>, _>("ask_depth_5")
            .map_err(read_signal_metric_error)?
            .unwrap_or(0.0);
        buckets.insert(floor_timestamp(timestamp, interval_ms), (bid, ask));
    }

    let times = buckets.keys().copied().collect::<Vec<_>>();
    let mut values = Vec::new();
    for timestamp in &times {
        let (bid, ask) = buckets.get(timestamp).copied().unwrap_or((0.0, 0.0));
        if ask > 0.0 {
            values.push(bid / ask);
        }
    }

    Ok((values, times.first().copied(), times.last().copied()))
}

async fn load_order_imbalance_history(
    pool: &sqlx::PgPool,
    symbol: &str,
    interval_ms: i64,
    start_time_ms: i64,
    current_time_ms: i64,
    exchange: &str,
) -> Result<(Vec<f64>, Option<i64>, Option<i64>), String> {
    let rows = sqlx::query(
        r#"
        SELECT timestamp,
               bid_depth_5::float8 AS bid_depth_5,
               ask_depth_5::float8 AS ask_depth_5
        FROM market_orderbook_snapshots
        WHERE exchange = $1
          AND symbol = $2
          AND timestamp >= $3
          AND timestamp <= $4
        ORDER BY timestamp
        "#,
    )
    .bind(exchange)
    .bind(symbol)
    .bind(start_time_ms)
    .bind(current_time_ms)
    .fetch_all(pool)
    .await
    .map_err(|error| format!("Failed to load order imbalance history: {error}"))?;

    if rows.is_empty() {
        return Ok((Vec::new(), None, None));
    }

    let mut buckets = BTreeMap::<i64, (f64, f64)>::new();
    for row in rows {
        let timestamp = row
            .try_get::<i64, _>("timestamp")
            .map_err(read_signal_metric_error)?;
        let bid = row
            .try_get::<Option<f64>, _>("bid_depth_5")
            .map_err(read_signal_metric_error)?
            .unwrap_or(0.0);
        let ask = row
            .try_get::<Option<f64>, _>("ask_depth_5")
            .map_err(read_signal_metric_error)?
            .unwrap_or(0.0);
        buckets.insert(floor_timestamp(timestamp, interval_ms), (bid, ask));
    }

    let times = buckets.keys().copied().collect::<Vec<_>>();
    let mut values = Vec::new();
    for timestamp in &times {
        let (bid, ask) = buckets.get(timestamp).copied().unwrap_or((0.0, 0.0));
        let total = bid + ask;
        if total > 0.0 {
            values.push((bid - ask) / total);
        }
    }

    Ok((values, times.first().copied(), times.last().copied()))
}

async fn load_taker_ratio_history(
    pool: &sqlx::PgPool,
    symbol: &str,
    interval_ms: i64,
    start_time_ms: i64,
    current_time_ms: i64,
    exchange: &str,
) -> Result<(Vec<f64>, Option<i64>, Option<i64>), String> {
    let rows = sqlx::query(
        r#"
        SELECT timestamp,
               taker_buy_notional::float8 AS taker_buy_notional,
               taker_sell_notional::float8 AS taker_sell_notional
        FROM market_trades_aggregated
        WHERE exchange = $1
          AND symbol = $2
          AND timestamp >= $3
          AND timestamp <= $4
        ORDER BY timestamp
        "#,
    )
    .bind(exchange)
    .bind(symbol)
    .bind(start_time_ms)
    .bind(current_time_ms)
    .fetch_all(pool)
    .await
    .map_err(|error| format!("Failed to load taker ratio history: {error}"))?;

    if rows.is_empty() {
        return Ok((Vec::new(), None, None));
    }

    let mut buckets = BTreeMap::<i64, (f64, f64)>::new();
    for row in rows {
        let timestamp = row
            .try_get::<i64, _>("timestamp")
            .map_err(read_signal_metric_error)?;
        let buy = row
            .try_get::<Option<f64>, _>("taker_buy_notional")
            .map_err(read_signal_metric_error)?
            .unwrap_or(0.0);
        let sell = row
            .try_get::<Option<f64>, _>("taker_sell_notional")
            .map_err(read_signal_metric_error)?
            .unwrap_or(0.0);
        let bucket = floor_timestamp(timestamp, interval_ms);
        let entry = buckets.entry(bucket).or_insert((0.0, 0.0));
        entry.0 += buy;
        entry.1 += sell;
    }

    let times = buckets.keys().copied().collect::<Vec<_>>();
    let mut values = Vec::new();
    for timestamp in &times {
        let (buy, sell) = buckets.get(timestamp).copied().unwrap_or((0.0, 0.0));
        if buy > 0.0 && sell > 0.0 {
            values.push((buy / sell).ln());
        }
    }

    Ok((values, times.first().copied(), times.last().copied()))
}

async fn load_funding_history(
    pool: &sqlx::PgPool,
    symbol: &str,
    interval_ms: i64,
    start_time_ms: i64,
    current_time_ms: i64,
    exchange: &str,
) -> Result<(Vec<f64>, Option<i64>, Option<i64>), String> {
    let query_start_ms = start_time_ms.saturating_sub(interval_ms);
    let rows = sqlx::query(
        r#"
        SELECT timestamp, funding_rate::float8 AS funding_rate
        FROM market_asset_metrics
        WHERE exchange = $1
          AND symbol = $2
          AND timestamp >= $3
          AND timestamp <= $4
          AND funding_rate IS NOT NULL
        ORDER BY timestamp
        "#,
    )
    .bind(exchange)
    .bind(symbol)
    .bind(query_start_ms)
    .bind(current_time_ms)
    .fetch_all(pool)
    .await
    .map_err(|error| format!("Failed to load funding history: {error}"))?;

    if rows.is_empty() {
        return Ok((Vec::new(), None, None));
    }

    let mut buckets = BTreeMap::<i64, f64>::new();
    for row in rows {
        let timestamp = row
            .try_get::<i64, _>("timestamp")
            .map_err(read_signal_metric_error)?;
        let funding = row
            .try_get::<Option<f64>, _>("funding_rate")
            .map_err(read_signal_metric_error)?
            .unwrap_or(0.0);
        buckets.insert(
            floor_timestamp(timestamp, interval_ms),
            funding * 1_000_000.0,
        );
    }

    let times = buckets.keys().copied().collect::<Vec<_>>();
    if times.len() < 2 {
        return Ok((Vec::new(), None, None));
    }

    let mut values = Vec::new();
    let mut result_times = Vec::new();
    for index in 1..times.len() {
        let timestamp = times[index];
        if timestamp >= start_time_ms {
            let prev = buckets.get(&times[index - 1]).copied().unwrap_or(0.0);
            let current = buckets.get(&timestamp).copied().unwrap_or(0.0);
            values.push(current - prev);
            result_times.push(timestamp);
        }
    }

    Ok((
        values,
        result_times.first().copied(),
        result_times.last().copied(),
    ))
}

async fn load_oi_history(
    pool: &sqlx::PgPool,
    symbol: &str,
    interval_ms: i64,
    start_time_ms: i64,
    current_time_ms: i64,
    exchange: &str,
) -> Result<(Vec<f64>, Option<i64>, Option<i64>), String> {
    let query_start_ms = start_time_ms.saturating_sub(interval_ms);
    let rows = sqlx::query(
        r#"
        SELECT timestamp,
               open_interest::float8 AS open_interest,
               mark_price::float8 AS mark_price
        FROM market_asset_metrics
        WHERE exchange = $1
          AND symbol = $2
          AND timestamp >= $3
          AND timestamp <= $4
          AND open_interest IS NOT NULL
          AND mark_price IS NOT NULL
        ORDER BY timestamp
        "#,
    )
    .bind(exchange)
    .bind(symbol)
    .bind(query_start_ms)
    .bind(current_time_ms)
    .fetch_all(pool)
    .await
    .map_err(|error| format!("Failed to load oi history: {error}"))?;

    if rows.is_empty() {
        return Ok((Vec::new(), None, None));
    }

    let mut buckets = BTreeMap::<i64, (f64, f64)>::new();
    for row in rows {
        let timestamp = row
            .try_get::<i64, _>("timestamp")
            .map_err(read_signal_metric_error)?;
        let open_interest = row
            .try_get::<Option<f64>, _>("open_interest")
            .map_err(read_signal_metric_error)?
            .unwrap_or(0.0);
        let mark_price = row
            .try_get::<Option<f64>, _>("mark_price")
            .map_err(read_signal_metric_error)?
            .unwrap_or(0.0);
        buckets.insert(
            floor_timestamp(timestamp, interval_ms),
            (open_interest, mark_price),
        );
    }

    let times = buckets.keys().copied().collect::<Vec<_>>();
    if times.len() < 2 {
        return Ok((Vec::new(), None, None));
    }

    let mut values = Vec::new();
    let mut result_times = Vec::new();
    for index in 1..times.len() {
        let timestamp = times[index];
        if timestamp < start_time_ms {
            continue;
        }
        let (curr_oi, curr_price) = buckets.get(&timestamp).copied().unwrap_or((0.0, 0.0));
        let (prev_oi, _) = buckets
            .get(&times[index - 1])
            .copied()
            .unwrap_or((0.0, 0.0));
        values.push(round_to((curr_oi - prev_oi) * curr_price, 2));
        result_times.push(timestamp);
    }

    Ok((
        values,
        result_times.first().copied(),
        result_times.last().copied(),
    ))
}

async fn load_price_change_history(
    pool: &sqlx::PgPool,
    symbol: &str,
    interval_ms: i64,
    start_time_ms: i64,
    current_time_ms: i64,
    exchange: &str,
) -> Result<(Vec<f64>, Option<i64>, Option<i64>), String> {
    let rows = sqlx::query(
        r#"
        SELECT timestamp, high_price::float8 AS high_price
        FROM market_trades_aggregated
        WHERE exchange = $1
          AND symbol = $2
          AND timestamp >= $3
          AND timestamp <= $4
          AND high_price IS NOT NULL
        ORDER BY timestamp
        "#,
    )
    .bind(exchange)
    .bind(symbol)
    .bind(start_time_ms)
    .bind(current_time_ms)
    .fetch_all(pool)
    .await
    .map_err(|error| format!("Failed to load price change history: {error}"))?;

    if rows.is_empty() {
        return Ok((Vec::new(), None, None));
    }

    let mut buckets = BTreeMap::<i64, (Option<f64>, Option<f64>)>::new();
    for row in rows {
        let timestamp = row
            .try_get::<i64, _>("timestamp")
            .map_err(read_signal_metric_error)?;
        let high_price = row
            .try_get::<Option<f64>, _>("high_price")
            .map_err(read_signal_metric_error)?;
        if let Some(price) = high_price {
            let bucket = floor_timestamp(timestamp, interval_ms);
            let entry = buckets.entry(bucket).or_insert((None, None));
            if entry.0.is_none() {
                entry.0 = Some(price);
            }
            entry.1 = Some(price);
        }
    }

    let times = buckets.keys().copied().collect::<Vec<_>>();
    let mut values = Vec::new();
    for pair in times.windows(2) {
        let prev_price = buckets.get(&pair[0]).and_then(|(_, last)| *last);
        let curr_price = buckets.get(&pair[1]).and_then(|(_, last)| *last);
        if let (Some(prev_price), Some(curr_price)) = (prev_price, curr_price)
            && prev_price > 0.0
        {
            values.push(((curr_price - prev_price) / prev_price) * 100.0);
        }
    }

    Ok((values, times.first().copied(), times.last().copied()))
}

async fn load_volatility_history(
    pool: &sqlx::PgPool,
    symbol: &str,
    interval_ms: i64,
    start_time_ms: i64,
    current_time_ms: i64,
    exchange: &str,
) -> Result<(Vec<f64>, Option<i64>, Option<i64>), String> {
    let rows = sqlx::query(
        r#"
        SELECT timestamp,
               high_price::float8 AS high_price,
               low_price::float8 AS low_price
        FROM market_trades_aggregated
        WHERE exchange = $1
          AND symbol = $2
          AND timestamp >= $3
          AND timestamp <= $4
          AND high_price IS NOT NULL
          AND low_price IS NOT NULL
        ORDER BY timestamp
        "#,
    )
    .bind(exchange)
    .bind(symbol)
    .bind(start_time_ms)
    .bind(current_time_ms)
    .fetch_all(pool)
    .await
    .map_err(|error| format!("Failed to load volatility history: {error}"))?;

    if rows.is_empty() {
        return Ok((Vec::new(), None, None));
    }

    let mut buckets = BTreeMap::<i64, (Option<f64>, Option<f64>)>::new();
    for row in rows {
        let timestamp = row
            .try_get::<i64, _>("timestamp")
            .map_err(read_signal_metric_error)?;
        let high_price = row
            .try_get::<Option<f64>, _>("high_price")
            .map_err(read_signal_metric_error)?;
        let low_price = row
            .try_get::<Option<f64>, _>("low_price")
            .map_err(read_signal_metric_error)?;
        if let (Some(high), Some(low)) = (high_price, low_price) {
            let bucket = floor_timestamp(timestamp, interval_ms);
            let entry = buckets.entry(bucket).or_insert((Some(high), Some(low)));
            entry.0 = Some(entry.0.unwrap_or(high).max(high));
            entry.1 = Some(entry.1.unwrap_or(low).min(low));
        }
    }

    let times = buckets.keys().copied().collect::<Vec<_>>();
    let mut values = Vec::new();
    for timestamp in &times {
        let (high, low) = buckets.get(timestamp).copied().unwrap_or((None, None));
        if let (Some(high), Some(low)) = (high, low)
            && low > 0.0
        {
            values.push(((high - low) / low) * 100.0);
        }
    }

    Ok((values, times.first().copied(), times.last().copied()))
}

fn normalize_signal_analysis_metric(metric: &str) -> String {
    match metric {
        "oi_delta_percent" => "oi_delta".to_owned(),
        "funding_rate" => "funding".to_owned(),
        "taker_buy_ratio" => "taker_ratio".to_owned(),
        _ => metric.to_owned(),
    }
}

fn parse_signal_backtest_signal_id(signal_id: &str) -> Result<i32, AppError> {
    signal_id
        .parse::<i32>()
        .map_err(|_| signal_backtest_validation_error("signal_id must be a valid integer"))
}

fn parse_signal_backtest_pool_id(pool_id: &str) -> Result<i32, AppError> {
    pool_id
        .parse::<i32>()
        .map_err(|_| signal_backtest_validation_error("pool_id must be a valid integer"))
}

fn parse_signal_backtest_query(
    query: SignalBacktestQuery,
) -> Result<ParsedSignalBacktestQuery, AppError> {
    let symbol = query
        .symbol
        .map(|symbol| symbol.trim().to_owned())
        .filter(|symbol| !symbol.is_empty())
        .ok_or_else(|| signal_backtest_validation_error("symbol query parameter is required"))?;

    Ok(ParsedSignalBacktestQuery {
        symbol,
        kline_min_ts: parse_optional_i64_query_param("kline_min_ts", query.kline_min_ts)?,
        kline_max_ts: parse_optional_i64_query_param("kline_max_ts", query.kline_max_ts)?,
    })
}

fn parse_signal_test_query(query: SignalTestQuery) -> Result<ParsedSignalTestQuery, AppError> {
    let symbol = query
        .symbol
        .map(|symbol| symbol.trim().to_owned())
        .filter(|symbol| !symbol.is_empty())
        .ok_or_else(|| signal_backtest_validation_error("symbol query parameter is required"))?;

    Ok(ParsedSignalTestQuery { symbol })
}

fn parse_optional_i64_query_param(
    key: &str,
    value: Option<String>,
) -> Result<Option<i64>, AppError> {
    value
        .map(|value| {
            value.parse::<i64>().map_err(|_| {
                signal_backtest_validation_error(format!("{key} must be a valid integer"))
            })
        })
        .transpose()
}

fn parse_signal_backtest_preview_request(
    payload: Value,
) -> Result<ParsedSignalBacktestPreviewRequest, AppError> {
    let payload = payload
        .as_object()
        .ok_or_else(|| signal_backtest_validation_error("request body must be a JSON object"))?;

    let symbol = payload
        .get("symbol")
        .and_then(Value::as_str)
        .map(str::trim)
        .filter(|symbol| !symbol.is_empty())
        .ok_or_else(|| signal_backtest_validation_error("symbol is required"))?
        .to_owned();

    let trigger_condition = payload
        .get("triggerCondition")
        .or_else(|| payload.get("trigger_condition"))
        .and_then(Value::as_object)
        .cloned()
        .ok_or_else(|| {
            signal_backtest_validation_error(
                "triggerCondition (or trigger_condition) must be an object",
            )
        })?;

    let exchange = payload
        .get("exchange")
        .and_then(Value::as_str)
        .map(str::trim)
        .filter(|exchange| !exchange.is_empty())
        .map(str::to_owned)
        .unwrap_or_else(default_exchange);

    Ok(ParsedSignalBacktestPreviewRequest {
        symbol,
        trigger_condition: Value::Object(trigger_condition),
        kline_min_ts: parse_optional_i64_json_field(
            payload,
            "klineMinTs",
            "kline_min_ts",
            "klineMinTs (or kline_min_ts)",
        )?,
        kline_max_ts: parse_optional_i64_json_field(
            payload,
            "klineMaxTs",
            "kline_max_ts",
            "klineMaxTs (or kline_max_ts)",
        )?,
        exchange,
    })
}

fn parse_optional_i64_json_field(
    payload: &Map<String, Value>,
    primary_key: &str,
    fallback_key: &str,
    display_key: &str,
) -> Result<Option<i64>, AppError> {
    let Some(value) = payload
        .get(primary_key)
        .or_else(|| payload.get(fallback_key))
    else {
        return Ok(None);
    };

    if value.is_null() {
        return Ok(None);
    }

    if let Some(parsed) = value.as_i64() {
        return Ok(Some(parsed));
    }

    if let Some(raw) = value.as_str() {
        let parsed = raw.parse::<i64>().map_err(|_| {
            signal_backtest_validation_error(format!("{display_key} must be a valid integer"))
        })?;
        return Ok(Some(parsed));
    }

    Err(signal_backtest_validation_error(format!(
        "{display_key} must be a valid integer"
    )))
}

fn parse_signal_pool_from_config_request(payload: Value) -> Result<Value, AppError> {
    let payload = payload
        .as_object()
        .ok_or_else(|| signal_pool_config_validation_error("request body must be a JSON object"))?;

    let name = parse_required_pool_string_field(payload, "name", "name is required")?;
    let symbol = parse_required_pool_string_field(payload, "symbol", "symbol is required")?;

    let description = parse_optional_pool_string_field(payload, "description", "description")?;
    let logic = parse_optional_pool_string_field(payload, "logic", "logic")?
        .unwrap_or_else(|| "AND".to_owned());
    let exchange = parse_optional_pool_string_field(payload, "exchange", "exchange")?
        .unwrap_or_else(default_exchange);
    let signals = parse_pool_config_signals(payload)?;

    let mut normalized_payload = Map::new();
    normalized_payload.insert("name".to_owned(), Value::String(name));
    normalized_payload.insert("symbol".to_owned(), Value::String(symbol));
    if let Some(description) = description {
        normalized_payload.insert("description".to_owned(), Value::String(description));
    }
    normalized_payload.insert("logic".to_owned(), Value::String(logic));
    normalized_payload.insert("signals".to_owned(), Value::Array(signals));
    normalized_payload.insert("exchange".to_owned(), Value::String(exchange));

    Ok(Value::Object(normalized_payload))
}

fn parse_pool_config_signals(payload: &Map<String, Value>) -> Result<Vec<Value>, AppError> {
    let signals = payload
        .get("signals")
        .and_then(Value::as_array)
        .ok_or_else(|| signal_pool_config_validation_error("signals must be an array"))?;

    if signals.is_empty() {
        return Err(AppError::bad_request("No signals provided"));
    }

    if signals.len() > MAX_SIGNAL_POOL_CONFIG_SIGNALS {
        return Err(AppError::bad_request(format!(
            "Maximum {MAX_SIGNAL_POOL_CONFIG_SIGNALS} signals per pool"
        )));
    }

    let mut normalized_signals = Vec::with_capacity(signals.len());
    for (index, signal) in signals.iter().enumerate() {
        let signal = signal.as_object().ok_or_else(|| {
            signal_pool_config_validation_error(format!("Signal {} must be an object", index + 1))
        })?;

        validate_pool_config_signal(signal, index + 1)?;
        normalized_signals.push(Value::Object(signal.clone()));
    }

    Ok(normalized_signals)
}

fn validate_pool_config_signal(signal: &Map<String, Value>, index: usize) -> Result<(), AppError> {
    let metric_value = signal.get("metric").or_else(|| signal.get("indicator"));
    let metric_name = metric_value
        .and_then(Value::as_str)
        .map(str::trim)
        .unwrap_or("");

    if metric_name == "taker_volume" {
        if !is_non_empty_text(metric_value)
            || !is_non_empty_text(signal.get("direction"))
            || signal.get("ratio_threshold").is_none_or(Value::is_null)
            || signal.get("volume_threshold").is_none_or(Value::is_null)
            || !is_non_empty_text(signal.get("time_window"))
        {
            return Err(AppError::bad_request(format!(
                "Signal {index} (taker_volume) missing required fields (direction, ratio_threshold, volume_threshold, time_window)"
            )));
        }
        return Ok(());
    }

    if !is_non_empty_text(metric_value)
        || !is_non_empty_text(signal.get("operator"))
        || signal.get("threshold").is_none_or(Value::is_null)
        || !is_non_empty_text(signal.get("time_window"))
    {
        return Err(AppError::bad_request(format!(
            "Signal {index} missing required fields (metric, operator, threshold, time_window)"
        )));
    }

    Ok(())
}

fn parse_required_pool_string_field(
    payload: &Map<String, Value>,
    key: &str,
    missing_message: &str,
) -> Result<String, AppError> {
    payload
        .get(key)
        .and_then(Value::as_str)
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .map(str::to_owned)
        .ok_or_else(|| signal_pool_config_validation_error(missing_message))
}

fn parse_optional_pool_string_field(
    payload: &Map<String, Value>,
    key: &str,
    display_key: &str,
) -> Result<Option<String>, AppError> {
    let Some(value) = payload.get(key) else {
        return Ok(None);
    };
    if value.is_null() {
        return Ok(None);
    }
    let value = value.as_str().ok_or_else(|| {
        signal_pool_config_validation_error(format!("{display_key} must be a string"))
    })?;
    let value = value.trim();
    if value.is_empty() {
        return Ok(None);
    }
    Ok(Some(value.to_owned()))
}

fn is_non_empty_text(value: Option<&Value>) -> bool {
    value
        .and_then(Value::as_str)
        .map(str::trim)
        .is_some_and(|value| !value.is_empty())
}

fn signal_pool_config_validation_error(message: impl Into<String>) -> AppError {
    AppError {
        status: StatusCode::UNPROCESSABLE_ENTITY,
        message: message.into(),
    }
}

fn signal_backtest_validation_error(message: impl Into<String>) -> AppError {
    AppError {
        status: StatusCode::UNPROCESSABLE_ENTITY,
        message: message.into(),
    }
}

fn signal_analysis_timeframe_ms(period: &str) -> Option<i64> {
    match period {
        "1m" => Some(60_000),
        "3m" => Some(3 * 60_000),
        "5m" => Some(5 * 60_000),
        "15m" => Some(15 * 60_000),
        "30m" => Some(30 * 60_000),
        "1h" => Some(60 * 60_000),
        "2h" => Some(2 * 60 * 60_000),
        "4h" => Some(4 * 60 * 60_000),
        "8h" => Some(8 * 60 * 60_000),
        "12h" => Some(12 * 60 * 60_000),
        "1d" => Some(24 * 60 * 60_000),
        _ => None,
    }
}

fn floor_timestamp(timestamp_ms: i64, interval_ms: i64) -> i64 {
    (timestamp_ms / interval_ms) * interval_ms
}

fn calculate_metric_statistics(values: &[f64], precision: i32) -> MetricStatistics {
    let mean_value = mean(values);
    let variance = values
        .iter()
        .map(|value| (value - mean_value).powi(2))
        .sum::<f64>()
        / values.len() as f64;
    let std = variance.sqrt();
    let min = values.iter().copied().fold(f64::INFINITY, f64::min);
    let max = values.iter().copied().fold(f64::NEG_INFINITY, f64::max);
    let abs_values = values.iter().map(|value| value.abs()).collect::<Vec<_>>();

    MetricStatistics {
        mean: round_to(mean_value, precision),
        std: round_to(std, precision),
        min: round_to(min, precision),
        max: round_to(max, precision),
        abs_percentiles: MetricAbsPercentiles {
            p75: round_to(percentile_linear(&abs_values, 75.0), precision),
            p90: round_to(percentile_linear(&abs_values, 90.0), precision),
            p95: round_to(percentile_linear(&abs_values, 95.0), precision),
            p99: round_to(percentile_linear(&abs_values, 99.0), precision),
        },
    }
}

fn generate_signal_threshold_suggestions(
    stats: &MetricStatistics,
    metric: &str,
) -> SignalThresholdSuggestions {
    let mut aggressive = SignalThresholdSuggestion {
        threshold: stats.abs_percentiles.p75,
        description: "~25% trigger rate".to_owned(),
        recommended: None,
        multiplier: None,
    };
    let mut moderate = SignalThresholdSuggestion {
        threshold: stats.abs_percentiles.p90,
        description: "~10% trigger rate".to_owned(),
        recommended: Some(true),
        multiplier: None,
    };
    let mut conservative = SignalThresholdSuggestion {
        threshold: stats.abs_percentiles.p95,
        description: "~5% trigger rate".to_owned(),
        recommended: None,
        multiplier: None,
    };

    if metric == "taker_ratio" {
        for suggestion in [&mut aggressive, &mut moderate, &mut conservative] {
            let multiplier = round_to(suggestion.threshold.abs().exp(), 2);
            suggestion.multiplier = Some(multiplier);
            suggestion.description = format!("{} ({multiplier}x)", suggestion.description);
        }
    }

    if metric == "oi" {
        append_oi_readability_hint(&mut aggressive.description, aggressive.threshold);
        append_oi_readability_hint(&mut moderate.description, moderate.threshold);
        append_oi_readability_hint(&mut conservative.description, conservative.threshold);
    }

    SignalThresholdSuggestions {
        aggressive,
        moderate,
        conservative,
    }
}

fn append_oi_readability_hint(description: &mut String, threshold: f64) {
    if threshold.abs() >= 1_000_000_000.0 {
        description.push_str(&format!(" (${:.1}B)", threshold / 1_000_000_000.0));
    } else if threshold.abs() >= 1_000_000.0 {
        description.push_str(&format!(" (${:.1}M)", threshold / 1_000_000.0));
    }
}

fn percentile_linear(values: &[f64], percentile: f64) -> f64 {
    if values.is_empty() {
        return 0.0;
    }

    let mut sorted = values.to_vec();
    sorted.sort_by(|left, right| left.partial_cmp(right).unwrap_or(std::cmp::Ordering::Equal));

    if sorted.len() == 1 {
        return sorted[0];
    }

    let rank = (percentile / 100.0) * (sorted.len() as f64 - 1.0);
    let lower = rank.floor() as usize;
    let upper = rank.ceil() as usize;
    if lower == upper {
        sorted[lower]
    } else {
        let weight = rank - lower as f64;
        sorted[lower] + (sorted[upper] - sorted[lower]) * weight
    }
}

fn mean(values: &[f64]) -> f64 {
    values.iter().sum::<f64>() / values.len() as f64
}

fn round_to(value: f64, precision: i32) -> f64 {
    let factor = 10_f64.powi(precision);
    (value * factor).round() / factor
}

fn wallet_tracking_idle_status(enabled: bool, has_access_token: bool) -> &'static str {
    if !enabled {
        "disabled"
    } else if !has_access_token {
        "waiting_for_token"
    } else {
        "connecting"
    }
}

fn wallet_tracking_status(enabled: bool, has_access_token: bool, runtime_status: &str) -> String {
    if !enabled || !has_access_token {
        return wallet_tracking_idle_status(enabled, has_access_token).to_owned();
    }

    match runtime_status {
        "connected" | "connecting" | "error" | "auth_error" => runtime_status.to_owned(),
        _ => "connecting".to_owned(),
    }
}

fn normalize_source_type(source_type: &str) -> Result<String, AppError> {
    let normalized = source_type.trim();
    if normalized == WALLET_TRACKING_SOURCE || normalized == MARKET_SIGNAL_SOURCE {
        Ok(normalized.to_owned())
    } else {
        Err(AppError::bad_request("Invalid source_type"))
    }
}

fn normalize_source_config(source_type: &str, source_config: Value) -> Result<Value, AppError> {
    if !source_config.is_object() {
        return Err(AppError::bad_request("source_config must be an object"));
    }
    if source_type == MARKET_SIGNAL_SOURCE {
        Ok(Value::Object(Default::default()))
    } else {
        Ok(source_config)
    }
}

fn parse_source_config_response(source_type: &str, source_config: Option<String>) -> Value {
    let parsed = parse_json_or_default(source_config, Value::Object(Default::default()));
    if source_type == MARKET_SIGNAL_SOURCE {
        Value::Object(Default::default())
    } else {
        parsed
    }
}

fn parse_json_or_default(raw: Option<String>, fallback: Value) -> Value {
    raw.and_then(|raw| serde_json::from_str::<Value>(&raw).ok())
        .unwrap_or(fallback)
}

fn parse_optional_json(raw: Option<String>) -> Option<Value> {
    raw.and_then(|raw| serde_json::from_str::<Value>(&raw).ok())
}

fn parse_i32_list(raw: Option<&str>) -> Vec<i32> {
    raw.and_then(|raw| serde_json::from_str::<Vec<i32>>(raw).ok())
        .unwrap_or_default()
}

fn parse_string_list(raw: Option<&str>) -> Vec<String> {
    raw.and_then(|raw| serde_json::from_str::<Vec<String>>(raw).ok())
        .unwrap_or_default()
}

fn json_err(error: serde_json::Error) -> AppError {
    AppError::internal(format!("Failed to serialize signal payload: {error}"))
}

fn read_signal_error(error: sqlx::Error) -> AppError {
    AppError::internal(format!("Failed to read signal data: {error}"))
}

fn read_signal_metric_error(error: sqlx::Error) -> String {
    format!("Failed to read signal metric data: {error}")
}

fn default_true() -> bool {
    true
}

fn default_exchange() -> String {
    "hyperliquid".to_owned()
}

fn default_logic() -> String {
    "OR".to_owned()
}

fn default_market_source() -> String {
    MARKET_SIGNAL_SOURCE.to_owned()
}

fn default_logs_limit() -> i64 {
    100
}

fn default_analyze_period() -> String {
    "5m".to_owned()
}

fn default_analyze_days() -> i64 {
    7
}

#[cfg(test)]
mod tests {
    use std::collections::{BTreeMap, HashMap};

    use axum::http::StatusCode;
    use chrono::DateTime;
    use serde_json::json;

    use super::{
        AiSignalChatStreamRequest, ResetSignalStatesQuery, RuntimePoolState, RuntimeSignalState,
        SignalBacktestQuery, SignalRuntimeStateStore, SignalTestQuery, apply_signal_state_reset,
        apply_wallet_runtime_state_projection, default_logs_limit,
        normalize_signal_analysis_metric, normalize_source_config, normalize_source_type,
        parse_i32_list, parse_signal_backtest_pool_id, parse_signal_backtest_preview_request,
        parse_signal_backtest_query, parse_signal_backtest_signal_id,
        parse_signal_pool_from_config_request, parse_signal_test_query,
        parse_source_config_response, parse_string_list, signal_analysis_timeframe_ms,
        wallet_tracking_idle_status, wallet_tracking_status,
    };

    #[test]
    fn source_type_validation_matches_legacy_rules() {
        assert_eq!(
            normalize_source_type("market_signals").unwrap(),
            "market_signals"
        );
        assert_eq!(
            normalize_source_type("wallet_tracking").unwrap(),
            "wallet_tracking"
        );
        assert!(normalize_source_type("other").is_err());
    }

    #[test]
    fn market_signal_source_forces_empty_source_config() {
        let config =
            normalize_source_config("market_signals", json!({"addresses": ["0x1"]})).unwrap();
        assert_eq!(config, json!({}));
        assert_eq!(
            parse_source_config_response("market_signals", Some("{\"a\":1}".to_owned())),
            json!({})
        );
    }

    #[test]
    fn json_list_parsers_follow_signal_storage_format() {
        assert_eq!(parse_i32_list(Some("[1,2,3]")), vec![1, 2, 3]);
        assert_eq!(
            parse_string_list(Some("[\"BTC\",\"ETH\"]")),
            vec!["BTC", "ETH"]
        );
        assert_eq!(default_logs_limit(), 100);
    }

    #[test]
    fn wallet_tracking_idle_status_matches_legacy_runtime_defaults() {
        assert_eq!(wallet_tracking_idle_status(false, false), "disabled");
        assert_eq!(
            wallet_tracking_idle_status(true, false),
            "waiting_for_token"
        );
        assert_eq!(wallet_tracking_idle_status(true, true), "connecting");
    }

    #[test]
    fn wallet_tracking_status_prefers_live_runtime_only_when_token_present() {
        assert_eq!(
            wallet_tracking_status(false, false, "connected"),
            "disabled"
        );
        assert_eq!(
            wallet_tracking_status(true, false, "connected"),
            "waiting_for_token"
        );
        assert_eq!(wallet_tracking_status(true, true, "connected"), "connected");
        assert_eq!(
            wallet_tracking_status(true, true, "auth_error"),
            "auth_error"
        );
        assert_eq!(wallet_tracking_status(true, true, "disabled"), "connecting");
    }

    #[test]
    fn reset_signal_states_without_filters_clears_all_runtime_state() {
        let mut store = SignalRuntimeStateStore {
            signal_states: HashMap::from([(
                (1, "BTC".to_owned()),
                RuntimeSignalState {
                    is_active: true,
                    last_value: Some(1.0),
                    last_check_time: 42.0,
                },
            )]),
            pool_states: HashMap::from([(
                (9, "BTC".to_owned()),
                RuntimePoolState {
                    is_active: true,
                    signal_conditions_met: BTreeMap::from([("1".to_owned(), true)]),
                    last_check_time: 43.0,
                },
            )]),
        };

        apply_signal_state_reset(&mut store, &ResetSignalStatesQuery::default());

        assert!(store.signal_states.is_empty());
        assert!(store.pool_states.is_empty());
    }

    #[test]
    fn reset_signal_states_with_filters_matches_legacy_behavior() {
        let mut store = SignalRuntimeStateStore {
            signal_states: HashMap::from([
                (
                    (1, "BTC".to_owned()),
                    RuntimeSignalState {
                        is_active: true,
                        last_value: Some(11.0),
                        last_check_time: 10.0,
                    },
                ),
                (
                    (1, "ETH".to_owned()),
                    RuntimeSignalState {
                        is_active: false,
                        last_value: None,
                        last_check_time: 11.0,
                    },
                ),
                (
                    (2, "BTC".to_owned()),
                    RuntimeSignalState {
                        is_active: true,
                        last_value: Some(22.0),
                        last_check_time: 12.0,
                    },
                ),
            ]),
            pool_states: HashMap::from([
                (
                    (7, "BTC".to_owned()),
                    RuntimePoolState {
                        is_active: true,
                        signal_conditions_met: BTreeMap::from([("1".to_owned(), true)]),
                        last_check_time: 20.0,
                    },
                ),
                (
                    (7, "ETH".to_owned()),
                    RuntimePoolState {
                        is_active: false,
                        signal_conditions_met: BTreeMap::from([("2".to_owned(), false)]),
                        last_check_time: 21.0,
                    },
                ),
                (
                    (8, "ETH".to_owned()),
                    RuntimePoolState {
                        is_active: true,
                        signal_conditions_met: BTreeMap::from([("3".to_owned(), true)]),
                        last_check_time: 22.0,
                    },
                ),
            ]),
        };

        apply_signal_state_reset(
            &mut store,
            &ResetSignalStatesQuery {
                signal_id: Some(1),
                pool_id: None,
                symbol: Some("BTC".to_owned()),
            },
        );

        assert!(!store.signal_states.contains_key(&(1, "BTC".to_owned())));
        assert!(store.signal_states.contains_key(&(1, "ETH".to_owned())));
        assert!(store.signal_states.contains_key(&(2, "BTC".to_owned())));
        assert!(!store.pool_states.contains_key(&(7, "BTC".to_owned())));
        assert!(store.pool_states.contains_key(&(7, "ETH".to_owned())));
        assert!(store.pool_states.contains_key(&(8, "ETH".to_owned())));
    }

    #[test]
    fn wallet_runtime_projection_updates_runtime_signal_and_pool_maps() {
        let triggered_at = DateTime::from_timestamp_millis(1_700_000_000_123)
            .expect("fixture timestamp should be valid")
            .naive_utc();
        let mut store = SignalRuntimeStateStore::default();

        apply_wallet_runtime_state_projection(
            &mut store,
            9,
            "BTC",
            &[3, 5],
            "position_change",
            triggered_at,
        );

        let signal_three = store
            .signal_states
            .get(&(3, "BTC".to_owned()))
            .expect("signal state for id 3 should exist");
        assert!(signal_three.is_active);
        assert_eq!(signal_three.last_value, None);

        let signal_five = store
            .signal_states
            .get(&(5, "BTC".to_owned()))
            .expect("signal state for id 5 should exist");
        assert!(signal_five.is_active);

        let pool_state = store
            .pool_states
            .get(&(9, "BTC".to_owned()))
            .expect("pool state should exist");
        assert!(pool_state.is_active);
        assert_eq!(pool_state.signal_conditions_met.get("3"), Some(&true));
        assert_eq!(pool_state.signal_conditions_met.get("5"), Some(&true));
        assert_eq!(
            pool_state
                .signal_conditions_met
                .get("wallet_event:position_change"),
            Some(&true)
        );
        assert_eq!(
            pool_state.last_check_time,
            triggered_at.and_utc().timestamp_millis() as f64 / 1000.0
        );
    }

    #[test]
    fn wallet_runtime_projection_without_signal_ids_marks_wallet_event_condition() {
        let triggered_at = DateTime::from_timestamp_millis(1_701_111_222_333)
            .expect("fixture timestamp should be valid")
            .naive_utc();
        let mut store = SignalRuntimeStateStore::default();

        apply_wallet_runtime_state_projection(
            &mut store,
            11,
            "WALLET",
            &[],
            "funding",
            triggered_at,
        );

        assert!(store.signal_states.is_empty());
        let pool_state = store
            .pool_states
            .get(&(11, "WALLET".to_owned()))
            .expect("pool state should exist");
        assert!(pool_state.is_active);
        assert_eq!(
            pool_state.signal_conditions_met.get("wallet_event"),
            Some(&true)
        );
        assert_eq!(
            pool_state.signal_conditions_met.get("wallet_event:funding"),
            Some(&true)
        );
    }

    #[test]
    fn signal_analysis_metric_aliases_follow_legacy_mapping() {
        assert_eq!(
            normalize_signal_analysis_metric("oi_delta_percent"),
            "oi_delta"
        );
        assert_eq!(normalize_signal_analysis_metric("funding_rate"), "funding");
        assert_eq!(
            normalize_signal_analysis_metric("taker_buy_ratio"),
            "taker_ratio"
        );
        assert_eq!(normalize_signal_analysis_metric("cvd"), "cvd");
    }

    #[test]
    fn signal_analysis_period_mapping_matches_supported_timeframes() {
        assert_eq!(signal_analysis_timeframe_ms("5m"), Some(5 * 60_000));
        assert_eq!(signal_analysis_timeframe_ms("1h"), Some(60 * 60_000));
        assert_eq!(signal_analysis_timeframe_ms("1d"), Some(24 * 60 * 60_000));
        assert_eq!(signal_analysis_timeframe_ms("unknown"), None);
    }

    #[test]
    fn signal_backtest_query_parser_requires_symbol_and_valid_timestamps() {
        let parsed = parse_signal_backtest_query(SignalBacktestQuery {
            symbol: Some(" BTC ".to_owned()),
            kline_min_ts: Some("1000".to_owned()),
            kline_max_ts: Some("2000".to_owned()),
        })
        .expect("query should parse");

        assert_eq!(parsed.symbol, "BTC");
        assert_eq!(parsed.kline_min_ts, Some(1000));
        assert_eq!(parsed.kline_max_ts, Some(2000));

        let missing_symbol = parse_signal_backtest_query(SignalBacktestQuery {
            symbol: None,
            kline_min_ts: None,
            kline_max_ts: None,
        })
        .expect_err("missing symbol should fail");
        assert_eq!(missing_symbol.status, StatusCode::UNPROCESSABLE_ENTITY);

        let invalid_ts = parse_signal_backtest_query(SignalBacktestQuery {
            symbol: Some("BTC".to_owned()),
            kline_min_ts: Some("bad".to_owned()),
            kline_max_ts: None,
        })
        .expect_err("invalid timestamp should fail");
        assert_eq!(invalid_ts.status, StatusCode::UNPROCESSABLE_ENTITY);
    }

    #[test]
    fn signal_backtest_signal_id_parser_requires_integer() {
        assert_eq!(
            parse_signal_backtest_signal_id("42").expect("signal id should parse"),
            42
        );
        assert_eq!(
            parse_signal_backtest_signal_id("bad")
                .expect_err("non-integer signal id should fail")
                .status,
            StatusCode::UNPROCESSABLE_ENTITY
        );
    }

    #[test]
    fn signal_backtest_pool_id_parser_requires_integer() {
        assert_eq!(
            parse_signal_backtest_pool_id("9").expect("pool id should parse"),
            9
        );
        assert_eq!(
            parse_signal_backtest_pool_id("bad")
                .expect_err("non-integer pool id should fail")
                .status,
            StatusCode::UNPROCESSABLE_ENTITY
        );
    }

    #[test]
    fn signal_test_query_parser_requires_symbol() {
        let parsed = parse_signal_test_query(SignalTestQuery {
            symbol: Some(" BTC ".to_owned()),
        })
        .expect("test query should parse");
        assert_eq!(parsed.symbol, "BTC");

        let missing_symbol = parse_signal_test_query(SignalTestQuery { symbol: None })
            .expect_err("missing symbol should fail");
        assert_eq!(missing_symbol.status, StatusCode::UNPROCESSABLE_ENTITY);
    }

    #[test]
    fn signal_ai_chat_stream_parser_supports_alias_and_default() {
        let camel_case: AiSignalChatStreamRequest = serde_json::from_value(json!({
            "accountId": 9,
            "userMessage": "build signal",
            "conversationId": 12
        }))
        .expect("camelCase payload should parse");
        assert_eq!(camel_case.account_id, 9);
        assert_eq!(camel_case.user_message, "build signal");
        assert_eq!(camel_case.conversation_id, Some(12));
        assert!(camel_case.use_background_task);

        let snake_case: AiSignalChatStreamRequest = serde_json::from_value(json!({
            "account_id": 5,
            "user_message": "stream",
            "use_background_task": false
        }))
        .expect("snake_case payload should parse");
        assert_eq!(snake_case.account_id, 5);
        assert_eq!(snake_case.user_message, "stream");
        assert_eq!(snake_case.conversation_id, None);
        assert!(!snake_case.use_background_task);
    }

    #[test]
    fn signal_backtest_preview_parser_accepts_aliases_and_validates_fields() {
        let parsed = parse_signal_backtest_preview_request(json!({
            "symbol": " BTC ",
            "triggerCondition": {
                "metric": "cvd",
                "operator": ">",
                "threshold": 1.5
            },
            "klineMinTs": 1700000000000_i64,
            "klineMaxTs": "1700000009999",
            "exchange": "binance"
        }))
        .expect("preview payload should parse");

        assert_eq!(parsed.symbol, "BTC");
        assert_eq!(parsed.kline_min_ts, Some(1700000000000));
        assert_eq!(parsed.kline_max_ts, Some(1700000009999));
        assert_eq!(parsed.exchange, "binance");
        assert_eq!(parsed.trigger_condition["metric"], json!("cvd"));

        let missing_trigger = parse_signal_backtest_preview_request(json!({
            "symbol": "BTC"
        }))
        .expect_err("missing triggerCondition should fail");
        assert_eq!(missing_trigger.status, StatusCode::UNPROCESSABLE_ENTITY);

        let invalid_kline = parse_signal_backtest_preview_request(json!({
            "symbol": "BTC",
            "trigger_condition": {"metric": "cvd"},
            "klineMinTs": {"bad": true}
        }))
        .expect_err("invalid klineMinTs should fail");
        assert_eq!(invalid_kline.status, StatusCode::UNPROCESSABLE_ENTITY);
    }

    #[test]
    fn signal_pool_from_config_parser_validates_contract_and_defaults() {
        let parsed = parse_signal_pool_from_config_request(json!({
            "name": "Momentum Pool",
            "symbol": "BTC",
            "signals": [
                {
                    "metric": "cvd",
                    "operator": ">",
                    "threshold": 12.5,
                    "time_window": "5m"
                }
            ]
        }))
        .expect("pool config payload should parse");

        assert_eq!(parsed["name"], json!("Momentum Pool"));
        assert_eq!(parsed["symbol"], json!("BTC"));
        assert_eq!(parsed["logic"], json!("AND"));
        assert_eq!(parsed["exchange"], json!("hyperliquid"));
        assert_eq!(parsed["signals"][0]["metric"], json!("cvd"));

        let no_signals = parse_signal_pool_from_config_request(json!({
            "name": "Pool",
            "symbol": "BTC",
            "signals": []
        }))
        .expect_err("empty signals should fail");
        assert_eq!(no_signals.status, StatusCode::BAD_REQUEST);
        assert_eq!(no_signals.message, "No signals provided");

        let missing_fields = parse_signal_pool_from_config_request(json!({
            "name": "Pool",
            "symbol": "BTC",
            "signals": [
                {"metric": "cvd"}
            ]
        }))
        .expect_err("missing signal fields should fail");
        assert_eq!(missing_fields.status, StatusCode::BAD_REQUEST);
        assert_eq!(
            missing_fields.message,
            "Signal 1 missing required fields (metric, operator, threshold, time_window)"
        );

        let too_many = parse_signal_pool_from_config_request(json!({
            "name": "Pool",
            "symbol": "BTC",
            "signals": vec![json!({
                "metric": "cvd",
                "operator": ">",
                "threshold": 1,
                "time_window": "1m"
            }); 11]
        }))
        .expect_err("too many signals should fail");
        assert_eq!(too_many.status, StatusCode::BAD_REQUEST);
        assert_eq!(too_many.message, "Maximum 10 signals per pool");
    }
}
