use axum::{
    Json,
    extract::{Path, Query, State},
};
use chrono::{NaiveDate, NaiveDateTime, Utc};
use regex::Regex;
use rhai::Engine;
use serde::{Deserialize, Serialize};
use sqlx::Row;
use std::{
    collections::{BTreeMap, BTreeSet},
    sync::OnceLock,
};

use crate::{error::AppError, state::AppState};

const REGISTERED_BUILTIN_FACTORS: usize = 22;
const COMPUTE_INTERVAL_SECONDS: i64 = 3600;
const FACTOR_EXPRESSION_ENGINE_SOURCE: &str =
    include_str!("../../backend/services/factor_expression_engine.py");

#[derive(Clone, Copy, Serialize)]
pub struct CategoryLabel {
    en: &'static str,
    zh: &'static str,
}

#[derive(Clone, Serialize)]
pub struct FactorLibraryItem {
    name: String,
    category: String,
    display_name: String,
    display_name_zh: String,
    description: String,
    description_zh: String,
    value_range: Option<String>,
    unit: Option<String>,
    source: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    expression: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    custom_id: Option<i32>,
}

#[derive(Serialize)]
pub struct FactorLibraryResponse {
    factors: Vec<FactorLibraryItem>,
    categories: Vec<String>,
    category_labels: BTreeMap<String, CategoryLabel>,
}

#[derive(Clone, Debug, Serialize)]
pub struct ExpressionFunctionMeta {
    name: String,
    category: String,
    signature: String,
    description: String,
    description_zh: String,
    example: String,
    params: Vec<String>,
}

#[derive(Clone, Serialize)]
pub struct ExpressionFunctionGroup {
    label: String,
    label_zh: String,
    functions: Vec<ExpressionFunctionMeta>,
}

#[derive(Serialize)]
pub struct ExpressionFunctionsResponse {
    functions: BTreeMap<String, String>,
    grouped: BTreeMap<String, ExpressionFunctionGroup>,
    total: usize,
}

#[derive(Deserialize)]
pub struct ValidateExpressionRequest {
    expression: String,
}

#[derive(Serialize)]
pub struct ValidateExpressionResponse {
    valid: bool,
    error: Option<String>,
}

#[derive(Deserialize)]
pub struct FactorValuesQuery {
    symbol: String,
    #[serde(default = "default_period")]
    period: String,
    #[serde(default = "default_exchange")]
    exchange: String,
}

#[derive(Serialize)]
pub struct FactorValuesResponse {
    symbol: String,
    period: String,
    exchange: String,
    values: Vec<FactorValueItem>,
}

#[derive(Serialize)]
pub struct FactorValueItem {
    factor_name: String,
    category: String,
    value: Option<f64>,
    timestamp: i32,
}

#[derive(Deserialize)]
pub struct FactorEffectivenessQuery {
    symbol: String,
    #[serde(default = "default_period")]
    period: String,
    #[serde(default = "default_forward_period")]
    forward_period: String,
    #[serde(default = "default_exchange")]
    exchange: String,
    #[serde(default = "default_sort_by")]
    sort_by: String,
}

#[derive(Serialize)]
pub struct FactorEffectivenessResponse {
    symbol: String,
    period: String,
    forward_period: String,
    exchange: String,
    items: Vec<FactorEffectivenessItem>,
}

#[derive(Debug, Serialize)]
pub struct FactorEffectivenessItem {
    factor_name: String,
    category: String,
    ic_mean: Option<f64>,
    ic_std: Option<f64>,
    icir: Option<f64>,
    win_rate: Option<f64>,
    decay_half_life: Option<i32>,
    sample_count: Option<i32>,
    calc_date: String,
    ic_7d: Option<f64>,
    ic_trend: Option<f64>,
}

#[derive(Deserialize)]
pub struct FactorHistoryQuery {
    symbol: String,
    #[serde(default = "default_period")]
    period: String,
    #[serde(default = "default_forward_period")]
    forward_period: String,
    #[serde(default = "default_exchange")]
    exchange: String,
    #[serde(default = "default_history_days")]
    days: i64,
}

#[derive(Serialize)]
pub struct FactorHistoryResponse {
    factor_name: String,
    history: Vec<FactorHistoryItem>,
}

#[derive(Serialize)]
pub struct FactorHistoryItem {
    date: String,
    ic_mean: Option<f64>,
    icir: Option<f64>,
    win_rate: Option<f64>,
    sample_count: Option<i32>,
}

#[derive(Deserialize)]
pub struct FactorByWindowQuery {
    symbol: String,
    #[serde(default = "default_period")]
    period: String,
    #[serde(default = "default_exchange")]
    exchange: String,
}

#[derive(Serialize)]
pub struct FactorByWindowResponse {
    factor_name: String,
    windows: Vec<FactorWindowItem>,
}

#[derive(Serialize)]
pub struct FactorWindowItem {
    forward_period: String,
    ic_mean: Option<f64>,
    icir: Option<f64>,
    win_rate: Option<f64>,
    sample_count: Option<i32>,
}

#[derive(Serialize)]
pub struct FactorStatusResponse {
    enabled: bool,
    total_factor_values: i64,
    symbols_covered: i64,
    latest_computation_ts: Option<i32>,
    total_effectiveness_records: i64,
    latest_effectiveness_date: Option<String>,
    registered_factors: usize,
    last_compute_time: LastComputeTime,
    compute_interval_seconds: i64,
}

#[derive(Serialize)]
pub struct LastComputeTime {
    hyperliquid: Option<f64>,
    binance: Option<f64>,
}

#[derive(Serialize)]
pub struct CustomFactorsResponse {
    items: Vec<CustomFactorItem>,
}

#[derive(Serialize)]
pub struct CustomFactorItem {
    id: i32,
    name: String,
    expression: String,
    description: Option<String>,
    category: String,
    source: String,
    is_active: bool,
    created_at: Option<String>,
}

pub async fn get_factor_library(
    State(state): State<AppState>,
) -> Result<Json<FactorLibraryResponse>, AppError> {
    let builtin = builtin_factor_library();
    let rows = sqlx::query(
        r#"
        SELECT id, name, expression, description, category, source
        FROM custom_factors
        WHERE is_active = true
        ORDER BY created_at DESC
        "#,
    )
    .fetch_all(&state.db)
    .await
    .map_err(|error| AppError::internal(format!("Failed to get factor library: {error}")))?;

    let custom = rows
        .into_iter()
        .map(|row| {
            let name = row
                .try_get::<String, _>("name")
                .map_err(read_factor_error)?;
            let expression = row
                .try_get::<String, _>("expression")
                .map_err(read_factor_error)?;
            let description = row
                .try_get::<Option<String>, _>("description")
                .map_err(read_factor_error)?
                .unwrap_or_else(|| expression.clone());
            let category = row
                .try_get::<Option<String>, _>("category")
                .map_err(read_factor_error)?
                .unwrap_or_else(|| "custom".to_owned());
            let source = row
                .try_get::<Option<String>, _>("source")
                .map_err(read_factor_error)?
                .unwrap_or_else(|| "custom".to_owned());

            Ok(FactorLibraryItem {
                name: name.clone(),
                category: if category == "custom" {
                    "custom".to_owned()
                } else {
                    category
                },
                display_name: name.clone(),
                display_name_zh: name.clone(),
                description: description.clone(),
                description_zh: description,
                value_range: None,
                unit: None,
                source,
                expression: Some(expression),
                custom_id: Some(row.try_get("id").map_err(read_factor_error)?),
            })
        })
        .collect::<Result<Vec<_>, AppError>>()?;

    let mut factors = builtin.clone();
    factors.extend(custom.clone());

    let mut categories = factors
        .iter()
        .map(|factor| factor.category.clone())
        .collect::<BTreeSet<_>>()
        .into_iter()
        .collect::<Vec<_>>();
    categories.sort();

    let mut category_labels = category_labels();
    for category in &categories {
        category_labels
            .entry(category.clone())
            .or_insert(CategoryLabel {
                en: "Custom",
                zh: "Custom",
            });
    }

    Ok(Json(FactorLibraryResponse {
        factors,
        categories,
        category_labels,
    }))
}

pub async fn list_expression_functions() -> Result<Json<ExpressionFunctionsResponse>, AppError> {
    let registry = expression_function_registry()?;
    let functions = registry
        .iter()
        .map(|function| {
            (
                function.name.clone(),
                format!("{} - {}", function.signature, function.description),
            )
        })
        .collect::<BTreeMap<_, _>>();

    let mut grouped = BTreeMap::new();
    let labels = expression_category_labels();
    for function in registry.iter() {
        let label = labels
            .get(&function.category)
            .copied()
            .unwrap_or(CategoryLabel {
                en: "Other",
                zh: "Other",
            });
        grouped
            .entry(function.category.clone())
            .or_insert_with(|| ExpressionFunctionGroup {
                label: label.en.to_owned(),
                label_zh: label.zh.to_owned(),
                functions: Vec::new(),
            })
            .functions
            .push(function.clone());
    }

    Ok(Json(ExpressionFunctionsResponse {
        total: registry.len(),
        functions,
        grouped,
    }))
}

pub async fn validate_expression(
    Json(payload): Json<ValidateExpressionRequest>,
) -> Json<ValidateExpressionResponse> {
    match validate_expression_syntax(&payload.expression) {
        Ok(()) => Json(ValidateExpressionResponse {
            valid: true,
            error: None,
        }),
        Err(error) => Json(ValidateExpressionResponse {
            valid: false,
            error: Some(error),
        }),
    }
}

pub async fn get_factor_values(
    State(state): State<AppState>,
    Query(query): Query<FactorValuesQuery>,
) -> Result<Json<FactorValuesResponse>, AppError> {
    let rows = sqlx::query(
        r#"
        SELECT DISTINCT ON (factor_name)
            factor_name, factor_category, value, timestamp
        FROM factor_values
        WHERE symbol = $1 AND period = $2 AND exchange = $3
        ORDER BY factor_name, timestamp DESC
        "#,
    )
    .bind(&query.symbol)
    .bind(&query.period)
    .bind(&query.exchange)
    .fetch_all(&state.db)
    .await
    .map_err(|error| AppError::internal(format!("Failed to get factor values: {error}")))?;

    let values = rows
        .into_iter()
        .map(|row| {
            Ok(FactorValueItem {
                factor_name: row.try_get("factor_name").map_err(read_factor_error)?,
                category: row.try_get("factor_category").map_err(read_factor_error)?,
                value: row.try_get("value").map_err(read_factor_error)?,
                timestamp: row.try_get("timestamp").map_err(read_factor_error)?,
            })
        })
        .collect::<Result<Vec<_>, AppError>>()?;

    Ok(Json(FactorValuesResponse {
        symbol: query.symbol,
        period: query.period,
        exchange: query.exchange,
        values,
    }))
}

pub async fn get_factor_effectiveness(
    State(state): State<AppState>,
    Query(query): Query<FactorEffectivenessQuery>,
) -> Result<Json<FactorEffectivenessResponse>, AppError> {
    let rows = sqlx::query(
        r#"
        SELECT DISTINCT ON (factor_name)
            factor_name, factor_category, ic_mean, ic_std, icir,
            win_rate, decay_half_life, sample_count, calc_date
        FROM factor_effectiveness
        WHERE symbol = $1 AND period = $2 AND forward_period = $3 AND exchange = $4
        ORDER BY factor_name, calc_date DESC
        "#,
    )
    .bind(&query.symbol)
    .bind(&query.period)
    .bind(&query.forward_period)
    .bind(&query.exchange)
    .fetch_all(&state.db)
    .await
    .map_err(|error| AppError::internal(format!("Failed to get factor effectiveness: {error}")))?;

    let cutoff_7d = Utc::now().date_naive() - chrono::Duration::days(7);
    let ic_7d = load_ic_7d_map(&state, &query, cutoff_7d).await?;

    let mut items = rows
        .into_iter()
        .map(|row| row_to_effectiveness_item(row, &ic_7d))
        .collect::<Result<Vec<_>, AppError>>()?;

    sort_effectiveness_items(&mut items, &query.sort_by);

    Ok(Json(FactorEffectivenessResponse {
        symbol: query.symbol,
        period: query.period,
        forward_period: query.forward_period,
        exchange: query.exchange,
        items,
    }))
}

pub async fn get_effectiveness_history(
    State(state): State<AppState>,
    Path(factor_name): Path<String>,
    Query(query): Query<FactorHistoryQuery>,
) -> Result<Json<FactorHistoryResponse>, AppError> {
    let cutoff = Utc::now().date_naive() - chrono::Duration::days(query.days.max(0));
    let rows = sqlx::query(
        r#"
        SELECT calc_date, ic_mean, icir, win_rate, sample_count
        FROM factor_effectiveness
        WHERE exchange = $1 AND factor_name = $2 AND symbol = $3 AND period = $4
            AND forward_period = $5 AND calc_date >= $6
        ORDER BY calc_date
        "#,
    )
    .bind(&query.exchange)
    .bind(&factor_name)
    .bind(&query.symbol)
    .bind(&query.period)
    .bind(&query.forward_period)
    .bind(cutoff)
    .fetch_all(&state.db)
    .await
    .map_err(|error| AppError::internal(format!("Failed to get factor history: {error}")))?;

    let history = rows
        .into_iter()
        .map(|row| {
            let date = row
                .try_get::<NaiveDate, _>("calc_date")
                .map_err(read_factor_error)?;
            Ok(FactorHistoryItem {
                date: date.to_string(),
                ic_mean: row.try_get("ic_mean").map_err(read_factor_error)?,
                icir: row.try_get("icir").map_err(read_factor_error)?,
                win_rate: row.try_get("win_rate").map_err(read_factor_error)?,
                sample_count: row.try_get("sample_count").map_err(read_factor_error)?,
            })
        })
        .collect::<Result<Vec<_>, AppError>>()?;

    Ok(Json(FactorHistoryResponse {
        factor_name,
        history,
    }))
}

pub async fn get_effectiveness_by_window(
    State(state): State<AppState>,
    Path(factor_name): Path<String>,
    Query(query): Query<FactorByWindowQuery>,
) -> Result<Json<FactorByWindowResponse>, AppError> {
    let rows = sqlx::query(
        r#"
        SELECT DISTINCT ON (forward_period)
            forward_period, ic_mean, icir, win_rate, sample_count
        FROM factor_effectiveness
        WHERE factor_name = $1 AND symbol = $2 AND period = $3 AND exchange = $4
        ORDER BY forward_period, calc_date DESC
        "#,
    )
    .bind(&factor_name)
    .bind(&query.symbol)
    .bind(&query.period)
    .bind(&query.exchange)
    .fetch_all(&state.db)
    .await
    .map_err(|error| AppError::internal(format!("Failed to get factor windows: {error}")))?;

    let windows = rows
        .into_iter()
        .map(|row| {
            Ok(FactorWindowItem {
                forward_period: row.try_get("forward_period").map_err(read_factor_error)?,
                ic_mean: row.try_get("ic_mean").map_err(read_factor_error)?,
                icir: row.try_get("icir").map_err(read_factor_error)?,
                win_rate: row.try_get("win_rate").map_err(read_factor_error)?,
                sample_count: row.try_get("sample_count").map_err(read_factor_error)?,
            })
        })
        .collect::<Result<Vec<_>, AppError>>()?;

    Ok(Json(FactorByWindowResponse {
        factor_name,
        windows,
    }))
}

pub async fn get_factor_status(
    State(state): State<AppState>,
) -> Result<Json<FactorStatusResponse>, AppError> {
    let stats = sqlx::query(
        r#"
        SELECT
            COUNT(*)::bigint AS total_factor_values,
            COUNT(DISTINCT symbol)::bigint AS symbols_covered,
            MAX(timestamp)::int4 AS latest_computation_ts,
            MAX(created_at) AS latest_created_at
        FROM factor_values
        "#,
    )
    .fetch_one(&state.db)
    .await
    .map_err(|error| AppError::internal(format!("Failed to get factor status: {error}")))?;

    let eff_stats = sqlx::query(
        r#"
        SELECT COUNT(*)::bigint AS total_effectiveness_records, MAX(calc_date) AS latest_effectiveness_date
        FROM factor_effectiveness
        "#,
    )
    .fetch_one(&state.db)
    .await
    .map_err(|error| AppError::internal(format!("Failed to get factor status: {error}")))?;

    let db_last_compute = stats
        .try_get::<Option<NaiveDateTime>, _>("latest_created_at")
        .map_err(read_factor_error)?
        .map(|value| value.and_utc().timestamp() as f64);

    Ok(Json(FactorStatusResponse {
        enabled: std::env::var("FACTOR_ENGINE_ENABLED")
            .map(|value| value.eq_ignore_ascii_case("true"))
            .unwrap_or(false),
        total_factor_values: stats
            .try_get("total_factor_values")
            .map_err(read_factor_error)?,
        symbols_covered: stats
            .try_get("symbols_covered")
            .map_err(read_factor_error)?,
        latest_computation_ts: stats
            .try_get("latest_computation_ts")
            .map_err(read_factor_error)?,
        total_effectiveness_records: eff_stats
            .try_get("total_effectiveness_records")
            .map_err(read_factor_error)?,
        latest_effectiveness_date: eff_stats
            .try_get::<Option<NaiveDate>, _>("latest_effectiveness_date")
            .map_err(read_factor_error)?
            .map(|date| date.to_string()),
        registered_factors: REGISTERED_BUILTIN_FACTORS,
        last_compute_time: LastComputeTime {
            hyperliquid: db_last_compute,
            binance: db_last_compute,
        },
        compute_interval_seconds: COMPUTE_INTERVAL_SECONDS,
    }))
}

pub async fn list_custom_factors(
    State(state): State<AppState>,
) -> Result<Json<CustomFactorsResponse>, AppError> {
    let rows = sqlx::query(
        r#"
        SELECT id, name, expression, description, category, source, is_active, created_at
        FROM custom_factors
        WHERE source != 'builtin_expression'
        ORDER BY created_at DESC
        "#,
    )
    .fetch_all(&state.db)
    .await
    .map_err(|error| AppError::internal(format!("Failed to list custom factors: {error}")))?;

    let items = rows
        .into_iter()
        .map(|row| {
            Ok(CustomFactorItem {
                id: row.try_get("id").map_err(read_factor_error)?,
                name: row.try_get("name").map_err(read_factor_error)?,
                expression: row.try_get("expression").map_err(read_factor_error)?,
                description: row.try_get("description").map_err(read_factor_error)?,
                category: row.try_get("category").map_err(read_factor_error)?,
                source: row.try_get("source").map_err(read_factor_error)?,
                is_active: row.try_get("is_active").map_err(read_factor_error)?,
                created_at: row
                    .try_get::<Option<NaiveDateTime>, _>("created_at")
                    .map_err(read_factor_error)?
                    .map(|value| value.to_string()),
            })
        })
        .collect::<Result<Vec<_>, AppError>>()?;

    Ok(Json(CustomFactorsResponse { items }))
}

async fn load_ic_7d_map(
    state: &AppState,
    query: &FactorEffectivenessQuery,
    cutoff: NaiveDate,
) -> Result<std::collections::HashMap<String, Option<f64>>, AppError> {
    let rows = sqlx::query(
        r#"
        SELECT factor_name, AVG(ic_mean) AS ic_7d
        FROM factor_effectiveness
        WHERE symbol = $1 AND period = $2 AND forward_period = $3
            AND exchange = $4 AND calc_date >= $5
        GROUP BY factor_name
        "#,
    )
    .bind(&query.symbol)
    .bind(&query.period)
    .bind(&query.forward_period)
    .bind(&query.exchange)
    .bind(cutoff)
    .fetch_all(&state.db)
    .await
    .map_err(|error| AppError::internal(format!("Failed to get factor effectiveness: {error}")))?;

    rows.into_iter()
        .map(|row| {
            let name = row
                .try_get::<String, _>("factor_name")
                .map_err(read_factor_error)?;
            let value = row
                .try_get::<Option<f64>, _>("ic_7d")
                .map_err(read_factor_error)?
                .map(round_six);
            Ok((name, value))
        })
        .collect()
}

fn row_to_effectiveness_item(
    row: sqlx::postgres::PgRow,
    ic_7d_map: &std::collections::HashMap<String, Option<f64>>,
) -> Result<FactorEffectivenessItem, AppError> {
    let factor_name = row
        .try_get::<String, _>("factor_name")
        .map_err(read_factor_error)?;
    let ic_mean = row
        .try_get::<Option<f64>, _>("ic_mean")
        .map_err(read_factor_error)?;
    let ic_7d = ic_7d_map.get(&factor_name).copied().flatten();
    let ic_trend = calculate_ic_trend(ic_7d, ic_mean);
    let calc_date = row
        .try_get::<NaiveDate, _>("calc_date")
        .map_err(read_factor_error)?
        .to_string();

    Ok(FactorEffectivenessItem {
        factor_name,
        category: row.try_get("factor_category").map_err(read_factor_error)?,
        ic_mean,
        ic_std: row.try_get("ic_std").map_err(read_factor_error)?,
        icir: row.try_get("icir").map_err(read_factor_error)?,
        win_rate: row.try_get("win_rate").map_err(read_factor_error)?,
        decay_half_life: row.try_get("decay_half_life").map_err(read_factor_error)?,
        sample_count: row.try_get("sample_count").map_err(read_factor_error)?,
        calc_date,
        ic_7d,
        ic_trend,
    })
}

fn sort_effectiveness_items(items: &mut [FactorEffectivenessItem], sort_by: &str) {
    let sort_by = if matches!(sort_by, "icir" | "ic_mean" | "win_rate" | "sample_count") {
        sort_by
    } else {
        "icir"
    };

    items.sort_by(|left, right| {
        let left_value = effectiveness_sort_value(left, sort_by).abs();
        let right_value = effectiveness_sort_value(right, sort_by).abs();
        right_value
            .partial_cmp(&left_value)
            .unwrap_or(std::cmp::Ordering::Equal)
    });
}

fn effectiveness_sort_value(item: &FactorEffectivenessItem, sort_by: &str) -> f64 {
    match sort_by {
        "ic_mean" => item.ic_mean.unwrap_or(0.0),
        "win_rate" => item.win_rate.unwrap_or(0.0),
        "sample_count" => item.sample_count.unwrap_or(0) as f64,
        _ => item.icir.unwrap_or(0.0),
    }
}

fn calculate_ic_trend(ic_7d: Option<f64>, ic_30d: Option<f64>) -> Option<f64> {
    let (Some(ic_7d), Some(ic_30d)) = (ic_7d, ic_30d) else {
        return None;
    };
    if ic_30d.abs() <= 1e-6 {
        return None;
    }
    Some(round_two(ic_7d / ic_30d))
}

fn read_factor_error(error: sqlx::Error) -> AppError {
    AppError::internal(format!("Failed to read factor data: {error}"))
}

fn round_six(value: f64) -> f64 {
    (value * 1_000_000.0).round() / 1_000_000.0
}

fn round_two(value: f64) -> f64 {
    (value * 100.0).round() / 100.0
}

fn default_period() -> String {
    "1h".to_owned()
}

fn default_forward_period() -> String {
    "4h".to_owned()
}

fn default_exchange() -> String {
    "hyperliquid".to_owned()
}

fn default_sort_by() -> String {
    "icir".to_owned()
}

fn default_history_days() -> i64 {
    30
}

fn builtin_factor_library() -> Vec<FactorLibraryItem> {
    vec![
        builtin_factor(
            "RSI14",
            "momentum",
            "RSI (14)",
            "Relative Strength Index, 14-period",
            Some("0-100"),
            Some(""),
        ),
        builtin_factor(
            "RSI7",
            "momentum",
            "RSI (7)",
            "Relative Strength Index, 7-period",
            Some("0-100"),
            Some(""),
        ),
        builtin_factor(
            "STOCH_K",
            "momentum",
            "Stochastic %K",
            "Stochastic Oscillator %K value",
            Some("0-100"),
            Some(""),
        ),
        builtin_factor(
            "STOCH_D",
            "momentum",
            "Stochastic %D",
            "Stochastic Oscillator %D value",
            Some("0-100"),
            Some(""),
        ),
        builtin_factor(
            "ROC10",
            "momentum",
            "ROC (10)",
            "Rate of Change, 10-period",
            Some("%"),
            Some("%"),
        ),
        builtin_factor(
            "ROC20",
            "momentum",
            "ROC (20)",
            "Rate of Change, 20-period",
            Some("%"),
            Some("%"),
        ),
        builtin_factor(
            "EMA20",
            "trend",
            "EMA (20)",
            "Exponential Moving Average, 20-period deviation from price",
            Some("-1 to 1"),
            Some(""),
        ),
        builtin_factor(
            "EMA50",
            "trend",
            "EMA (50)",
            "Exponential Moving Average, 50-period deviation from price",
            Some("-1 to 1"),
            Some(""),
        ),
        builtin_factor(
            "SMA20",
            "trend",
            "SMA (20)",
            "Simple Moving Average, 20-period deviation from price",
            Some("-1 to 1"),
            Some(""),
        ),
        builtin_factor(
            "MACD_HIST",
            "trend",
            "MACD Histogram",
            "MACD histogram value",
            None,
            Some(""),
        ),
        builtin_factor(
            "MACD_SIGNAL",
            "trend",
            "MACD Signal",
            "MACD signal line value",
            None,
            Some(""),
        ),
        builtin_factor(
            "ATR14",
            "volatility",
            "ATR (14)",
            "Average True Range, 14-period",
            None,
            Some("price"),
        ),
        builtin_factor(
            "BOLL_WIDTH",
            "volatility",
            "Bollinger Width",
            "Bollinger Bands width (upper - lower) / middle",
            None,
            Some(""),
        ),
        builtin_factor(
            "BOLL_POSITION",
            "volatility",
            "Bollinger %B",
            "Price position within Bollinger Bands (0-1)",
            Some("0-1"),
            Some(""),
        ),
        builtin_factor("OBV", "volume", "OBV", "On-Balance Volume", None, Some("")),
        builtin_factor(
            "VWAP_DEV",
            "volume",
            "VWAP Deviation",
            "Price deviation from VWAP",
            Some("-1 to 1"),
            Some(""),
        ),
        builtin_factor(
            "VOLUME_SMA_RATIO",
            "volume",
            "Volume/SMA20 Ratio",
            "Current volume relative to 20-period SMA",
            None,
            Some("x"),
        ),
        builtin_factor(
            "CVD_RATIO",
            "microstructure",
            "CVD Ratio",
            "Cumulative Volume Delta ratio",
            Some("-1 to 1"),
            Some(""),
        ),
        builtin_factor(
            "OI_CHANGE_PCT",
            "microstructure",
            "OI Change %",
            "Open Interest change percentage",
            None,
            Some("%"),
        ),
        builtin_factor(
            "FUNDING_RATE",
            "microstructure",
            "Funding Rate",
            "Current funding rate",
            Some("-0.1% to 0.1%"),
            Some("%"),
        ),
        builtin_factor(
            "TAKER_BUY_RATIO",
            "microstructure",
            "Taker Buy Ratio",
            "Taker buy volume ratio",
            Some("0-1"),
            Some(""),
        ),
        builtin_factor(
            "DEPTH_RATIO",
            "microstructure",
            "Depth Ratio",
            "Order book bid/ask depth ratio",
            None,
            Some(""),
        ),
    ]
}

fn builtin_factor(
    name: &str,
    category: &str,
    display_name: &str,
    description: &str,
    value_range: Option<&str>,
    unit: Option<&str>,
) -> FactorLibraryItem {
    FactorLibraryItem {
        name: name.to_owned(),
        category: category.to_owned(),
        display_name: display_name.to_owned(),
        display_name_zh: display_name.to_owned(),
        description: description.to_owned(),
        description_zh: description.to_owned(),
        value_range: value_range.map(str::to_owned),
        unit: unit.map(str::to_owned),
        source: "builtin".to_owned(),
        expression: None,
        custom_id: None,
    }
}

fn category_labels() -> BTreeMap<String, CategoryLabel> {
    BTreeMap::from([
        (
            "momentum".to_owned(),
            CategoryLabel {
                en: "Momentum",
                zh: "Momentum",
            },
        ),
        (
            "trend".to_owned(),
            CategoryLabel {
                en: "Trend",
                zh: "Trend",
            },
        ),
        (
            "volatility".to_owned(),
            CategoryLabel {
                en: "Volatility",
                zh: "Volatility",
            },
        ),
        (
            "volume".to_owned(),
            CategoryLabel {
                en: "Volume",
                zh: "Volume",
            },
        ),
        (
            "microstructure".to_owned(),
            CategoryLabel {
                en: "Microstructure",
                zh: "Microstructure",
            },
        ),
        (
            "moving_average".to_owned(),
            CategoryLabel {
                en: "Moving Average",
                zh: "Moving Average",
            },
        ),
        (
            "time_series".to_owned(),
            CategoryLabel {
                en: "Time Series Operators",
                zh: "Time Series Operators",
            },
        ),
        (
            "cross_section".to_owned(),
            CategoryLabel {
                en: "Cross-Section",
                zh: "Cross-Section",
            },
        ),
        (
            "math".to_owned(),
            CategoryLabel {
                en: "Math",
                zh: "Math",
            },
        ),
        (
            "conditional".to_owned(),
            CategoryLabel {
                en: "Conditional / Logic",
                zh: "Conditional / Logic",
            },
        ),
        (
            "custom".to_owned(),
            CategoryLabel {
                en: "Custom",
                zh: "Custom",
            },
        ),
        (
            "composite".to_owned(),
            CategoryLabel {
                en: "Composite",
                zh: "Composite",
            },
        ),
        (
            "statistical".to_owned(),
            CategoryLabel {
                en: "Statistical",
                zh: "Statistical",
            },
        ),
    ])
}

fn expression_category_labels() -> BTreeMap<String, CategoryLabel> {
    BTreeMap::from([
        (
            "moving_average".to_owned(),
            CategoryLabel {
                en: "Moving Average",
                zh: "Moving Average",
            },
        ),
        (
            "momentum".to_owned(),
            CategoryLabel {
                en: "Momentum",
                zh: "Momentum",
            },
        ),
        (
            "trend".to_owned(),
            CategoryLabel {
                en: "Trend",
                zh: "Trend",
            },
        ),
        (
            "volatility".to_owned(),
            CategoryLabel {
                en: "Volatility",
                zh: "Volatility",
            },
        ),
        (
            "volume".to_owned(),
            CategoryLabel {
                en: "Volume",
                zh: "Volume",
            },
        ),
        (
            "time_series".to_owned(),
            CategoryLabel {
                en: "Time Series Operators",
                zh: "Time Series Operators",
            },
        ),
        (
            "cross_section".to_owned(),
            CategoryLabel {
                en: "Cross-Section",
                zh: "Cross-Section",
            },
        ),
        (
            "math".to_owned(),
            CategoryLabel {
                en: "Math",
                zh: "Math",
            },
        ),
        (
            "conditional".to_owned(),
            CategoryLabel {
                en: "Conditional / Logic",
                zh: "Conditional / Logic",
            },
        ),
    ])
}

fn expression_function_registry() -> Result<&'static Vec<ExpressionFunctionMeta>, AppError> {
    static REGISTRY: OnceLock<Result<Vec<ExpressionFunctionMeta>, String>> = OnceLock::new();
    REGISTRY
        .get_or_init(parse_expression_function_registry)
        .as_ref()
        .map_err(|error| {
            AppError::internal(format!(
                "Failed to build expression function registry: {error}"
            ))
        })
}

fn parse_expression_function_registry() -> Result<Vec<ExpressionFunctionMeta>, String> {
    let regex = Regex::new(
        r#"_reg\("([^"]+)",\s*"([^"]+)",\s*"([^"]+)",\s*"([^"]*)",\s*"([^"]*)",\s*"([^"]*)""#,
    )
    .map_err(|error| error.to_string())?;

    let functions = regex
        .captures_iter(FACTOR_EXPRESSION_ENGINE_SOURCE)
        .map(|captures| ExpressionFunctionMeta {
            name: captures[1].to_owned(),
            category: captures[2].to_owned(),
            signature: captures[3].to_owned(),
            description: captures[4].to_owned(),
            description_zh: captures[5].to_owned(),
            example: captures[6].to_owned(),
            params: Vec::new(),
        })
        .collect::<Vec<_>>();

    if functions.is_empty() {
        Err("no expression functions parsed from Python registry".to_owned())
    } else {
        Ok(functions)
    }
}

fn validate_expression_syntax(expression: &str) -> Result<(), String> {
    if expression.trim().is_empty() {
        return Err("Expression is empty".to_owned());
    }
    if expression.len() > 500 {
        return Err("Expression too long (max 500 chars)".to_owned());
    }

    let registry = expression_function_registry().map_err(|error| error.message)?;
    let known_functions = registry
        .iter()
        .map(|function| function.name.as_str())
        .collect::<BTreeSet<_>>();
    let function_regex =
        Regex::new(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\(").map_err(|error| error.to_string())?;

    for captures in function_regex.captures_iter(expression) {
        let name = captures
            .get(1)
            .map(|capture| capture.as_str())
            .unwrap_or_default();
        if !known_functions.contains(name) {
            return Err(format!("Parse error: Unknown function `{name}`"));
        }
    }

    let mut depth = 0_i32;
    for ch in expression.chars() {
        match ch {
            '(' => depth += 1,
            ')' => {
                depth -= 1;
                if depth < 0 {
                    return Err("Syntax error: unmatched closing parenthesis".to_owned());
                }
            }
            _ => {}
        }
    }
    if depth != 0 {
        return Err("Syntax error: unmatched opening parenthesis".to_owned());
    }

    let engine = Engine::new();
    engine
        .compile_expression(expression)
        .map(|_| ())
        .map_err(|error| format!("Syntax error: {error}"))
}

#[cfg(test)]
mod tests {
    use super::{
        FactorEffectivenessItem, REGISTERED_BUILTIN_FACTORS, builtin_factor_library,
        calculate_ic_trend, default_forward_period, default_history_days, default_period,
        expression_function_registry, round_six, sort_effectiveness_items,
        validate_expression_syntax,
    };

    #[test]
    fn defaults_match_legacy_routes() {
        assert_eq!(default_period(), "1h");
        assert_eq!(default_forward_period(), "4h");
        assert_eq!(default_history_days(), 30);
        assert_eq!(REGISTERED_BUILTIN_FACTORS, 22);
    }

    #[test]
    fn rounds_ic_7d_like_legacy_route() {
        assert_eq!(round_six(0.1234567), 0.123457);
    }

    #[test]
    fn calculates_ic_trend_when_long_term_ic_is_nonzero() {
        assert_eq!(calculate_ic_trend(Some(0.05), Some(0.025)), Some(2.0));
        assert_eq!(calculate_ic_trend(Some(0.05), Some(0.0)), None);
    }

    #[test]
    fn sorts_effectiveness_by_absolute_metric_descending() {
        let mut items = vec![
            fake_item("a", Some(0.1)),
            fake_item("b", Some(-0.3)),
            fake_item("c", None),
        ];
        sort_effectiveness_items(&mut items, "icir");
        assert_eq!(items[0].factor_name, "b");
        assert_eq!(items[1].factor_name, "a");
    }

    #[test]
    fn builtin_factor_library_matches_expected_size() {
        assert_eq!(builtin_factor_library().len(), REGISTERED_BUILTIN_FACTORS);
    }

    #[test]
    fn expression_registry_parses_python_function_registry() {
        let registry = expression_function_registry().expect("registry should parse");
        assert!(registry.len() >= 60);
        assert!(registry.iter().any(|function| function.name == "SMA"));
        assert!(registry.iter().any(|function| function.name == "IF"));
    }

    #[test]
    fn expression_validator_accepts_known_functions_and_rejects_unknown_ones() {
        assert!(validate_expression_syntax("EMA(close, 20) / EMA(close, 50) - 1").is_ok());
        assert!(validate_expression_syntax("FOO(close, 10)").is_err());
        assert!(validate_expression_syntax("EMA(close, 20").is_err());
    }

    fn fake_item(name: &str, icir: Option<f64>) -> FactorEffectivenessItem {
        FactorEffectivenessItem {
            factor_name: name.to_owned(),
            category: "momentum".to_owned(),
            ic_mean: None,
            ic_std: None,
            icir,
            win_rate: None,
            decay_half_life: None,
            sample_count: None,
            calc_date: "2026-04-14".to_owned(),
            ic_7d: None,
            ic_trend: None,
        }
    }
}
