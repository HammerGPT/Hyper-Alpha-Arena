use axum::{
    Json,
    extract::{Query, State},
};
use chrono::{Duration, FixedOffset, NaiveDateTime, Utc};
use serde::{Deserialize, Serialize};
use sqlx::Row;
use std::collections::HashMap;

use crate::{error::AppError, state::AppState};

const HYPERLIQUID_RETENTION_KEY: &str = "hyperliquid_retention_days";
const BINANCE_RETENTION_KEY: &str = "binance_retention_days";
const DEFAULT_RETENTION_DAYS: i32 = 365;

#[derive(Deserialize)]
pub struct ExchangeQuery {
    #[serde(default = "default_exchange")]
    exchange: String,
}

#[derive(Deserialize)]
pub struct RetentionDaysRequest {
    days: i32,
    #[serde(default = "default_exchange")]
    exchange: String,
}

#[derive(Serialize)]
pub struct RetentionDaysResponse {
    days: i32,
    exchange: String,
}

#[derive(Serialize)]
pub struct CollectionDaysResponse {
    days: f64,
    exchange: String,
}

#[derive(Serialize)]
pub struct BackfillStatusResponse {
    status: String,
    progress: i32,
    #[serde(skip_serializing_if = "Option::is_none")]
    task_id: Option<i32>,
    #[serde(skip_serializing_if = "Vec::is_empty")]
    symbols: Vec<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    error_message: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    created_at: Option<String>,
}

#[derive(Deserialize)]
pub struct StorageStatsQuery {
    #[serde(default = "default_exchange")]
    exchange: String,
}

#[derive(Serialize)]
pub struct StorageStatsResponse {
    exchange: String,
    total_size_mb: f64,
    tables: HashMap<String, f64>,
    retention_days: i32,
    symbol_count: i64,
    estimated_per_symbol_per_day_mb: f64,
}

#[derive(Deserialize)]
pub struct DataCoverageQuery {
    #[serde(default = "default_coverage_days")]
    days: i64,
    symbol: Option<String>,
    #[serde(default)]
    tz_offset: i32,
    #[serde(default = "default_exchange")]
    exchange: String,
    #[serde(default = "default_data_type")]
    data_type: String,
}

#[derive(Serialize)]
#[serde(untagged)]
pub enum DataCoverageResponse {
    Symbols {
        symbols: Vec<String>,
        exchange: String,
        data_type: String,
    },
    Coverage {
        symbol: String,
        days: i64,
        coverage: Vec<CoverageItem>,
        exchange: String,
        data_type: String,
    },
}

#[derive(Serialize)]
pub struct CoverageItem {
    date: String,
    pct: i32,
}

pub async fn get_storage_stats(
    State(state): State<AppState>,
    Query(query): Query<StorageStatsQuery>,
) -> Result<Json<StorageStatsResponse>, AppError> {
    let exchange = query.exchange;
    let mut tables = HashMap::new();
    let mut total_bytes = 0_i64;

    for table_name in storage_tables_for_exchange(&exchange) {
        match exchange_table_size_bytes(&state.db, table_name, &exchange).await {
            Ok(bytes) => {
                tables.insert(
                    table_name.to_owned(),
                    round_one_decimal(bytes as f64 / bytes_per_mb()),
                );
                total_bytes += bytes;
            }
            Err(error) => {
                tracing::warn!(
                    target = "backend_rust::system_routes",
                    %error,
                    table_name,
                    exchange,
                    "failed to get per-table storage stats"
                );
                tables.insert(table_name.to_owned(), 0.0);
            }
        }
    }

    let total_size_mb = round_one_decimal(total_bytes as f64 / bytes_per_mb());
    let retention_days = get_retention_days(&state.db, &exchange).await?;
    let (symbol_count, min_ts, max_ts) =
        market_trades_collection_range(&state.db, &exchange).await?;
    let symbol_count_for_math = symbol_count.max(1);

    let estimated_per_symbol_per_day_mb = if let (Some(min_ts), Some(max_ts)) = (min_ts, max_ts) {
        if total_size_mb > 0.0 {
            let days_of_data = ((max_ts - min_ts) as f64 / (1000.0 * 86400.0)).max(1.0);
            round_two_decimals(total_size_mb / (symbol_count_for_math as f64 * days_of_data))
        } else {
            6.7
        }
    } else {
        6.7
    };

    Ok(Json(StorageStatsResponse {
        exchange,
        total_size_mb,
        tables,
        retention_days,
        symbol_count: symbol_count_for_math,
        estimated_per_symbol_per_day_mb,
    }))
}

pub async fn get_data_coverage(
    State(state): State<AppState>,
    Query(query): Query<DataCoverageQuery>,
) -> Result<Json<DataCoverageResponse>, AppError> {
    let days = query.days.max(1);
    let table = coverage_table(&query.data_type);
    let now_seconds = Utc::now().timestamp();
    let (start_ts, ts_divisor) = if query.data_type == "klines" {
        (now_seconds - days * 24 * 60 * 60, 1.0)
    } else {
        (now_seconds * 1000 - days * 24 * 60 * 60 * 1000, 1000.0)
    };

    let Some(symbol) = query.symbol else {
        let symbols = data_coverage_symbols(&state.db, table, start_ts, &query.exchange).await?;
        return Ok(Json(DataCoverageResponse::Symbols {
            symbols,
            exchange: query.exchange,
            data_type: query.data_type,
        }));
    };

    let symbol = symbol.to_uppercase();
    let offset_minutes = -query.tz_offset;
    let offset_interval = format!("{offset_minutes} minutes");
    let rows = data_coverage_rows(
        &state.db,
        table,
        ts_divisor,
        start_ts,
        &symbol,
        &query.exchange,
        &offset_interval,
    )
    .await?;

    let mut coverage_map = HashMap::new();
    for (date, hours) in rows {
        let pct = ((hours as f64 / 24.0 * 100.0).round() as i32).min(100);
        coverage_map.insert(date, pct);
    }

    let offset = FixedOffset::east_opt(offset_minutes * 60)
        .unwrap_or_else(|| FixedOffset::east_opt(0).expect("zero offset is valid"));
    let end_date = Utc::now().with_timezone(&offset).date_naive();
    let start_date = end_date - Duration::days(days - 1);
    let coverage = (0..days)
        .map(|index| {
            let date = start_date + Duration::days(index);
            let date = date.format("%Y-%m-%d").to_string();
            CoverageItem {
                pct: coverage_map.get(&date).copied().unwrap_or(0),
                date,
            }
        })
        .collect();

    Ok(Json(DataCoverageResponse::Coverage {
        symbol,
        days,
        coverage,
        exchange: query.exchange,
        data_type: query.data_type,
    }))
}

pub async fn get_retention_days_api(
    State(state): State<AppState>,
    Query(query): Query<ExchangeQuery>,
) -> Result<Json<RetentionDaysResponse>, AppError> {
    let days = get_retention_days(&state.db, &query.exchange).await?;
    Ok(Json(RetentionDaysResponse {
        days,
        exchange: query.exchange,
    }))
}

pub async fn update_retention_days(
    State(state): State<AppState>,
    Json(payload): Json<RetentionDaysRequest>,
) -> Result<Json<RetentionDaysResponse>, AppError> {
    validate_retention_days(payload.days)?;
    set_retention_days(&state.db, payload.days, &payload.exchange).await?;

    Ok(Json(RetentionDaysResponse {
        days: payload.days,
        exchange: payload.exchange,
    }))
}

pub async fn get_collection_days(
    State(state): State<AppState>,
    Query(query): Query<ExchangeQuery>,
) -> Json<CollectionDaysResponse> {
    let days = match sqlx::query_scalar::<_, Option<i64>>(
        "SELECT MIN(timestamp) FROM market_trades_aggregated WHERE exchange = $1",
    )
    .bind(&query.exchange)
    .fetch_one(&state.db)
    .await
    {
        Ok(Some(min_timestamp)) => {
            let now_ms = Utc::now().timestamp_millis();
            round_one_decimal((now_ms - min_timestamp) as f64 / (24.0 * 60.0 * 60.0 * 1000.0))
        }
        Ok(None) | Err(_) => 0.0,
    };

    Json(CollectionDaysResponse {
        days,
        exchange: query.exchange,
    })
}

pub async fn get_binance_backfill_status(
    State(state): State<AppState>,
) -> Result<Json<BackfillStatusResponse>, AppError> {
    get_backfill_status(&state.db, "binance_backfill_tasks")
        .await
        .map(Json)
}

pub async fn get_hyperliquid_backfill_status(
    State(state): State<AppState>,
) -> Result<Json<BackfillStatusResponse>, AppError> {
    get_backfill_status(&state.db, "hyperliquid_backfill_tasks")
        .await
        .map(Json)
}

async fn get_retention_days(pool: &sqlx::PgPool, exchange: &str) -> Result<i32, AppError> {
    let key = retention_key(exchange);
    let value = sqlx::query_scalar::<_, Option<String>>(
        "SELECT value FROM system_configs WHERE key = $1 LIMIT 1",
    )
    .bind(key)
    .fetch_optional(pool)
    .await
    .map_err(|error| AppError::internal(format!("Failed to get retention days: {error}")))?;

    Ok(value
        .flatten()
        .and_then(|raw| raw.parse::<i32>().ok())
        .unwrap_or(DEFAULT_RETENTION_DAYS))
}

async fn set_retention_days(
    pool: &sqlx::PgPool,
    days: i32,
    exchange: &str,
) -> Result<(), AppError> {
    let key = retention_key(exchange);
    let description = format!(
        "{} market data retention period in days",
        capitalize(exchange)
    );

    sqlx::query(
        r#"
        INSERT INTO system_configs (key, value, description, created_at, updated_at)
        VALUES ($1, $2, $3, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        ON CONFLICT (key)
        DO UPDATE SET value = EXCLUDED.value, description = EXCLUDED.description, updated_at = CURRENT_TIMESTAMP
        "#,
    )
    .bind(key)
    .bind(days.to_string())
    .bind(description)
    .execute(pool)
    .await
    .map_err(|error| AppError::internal(format!("Failed to update retention days: {error}")))?;

    Ok(())
}

async fn exchange_table_size_bytes(
    pool: &sqlx::PgPool,
    table_name: &str,
    exchange: &str,
) -> Result<i64, sqlx::Error> {
    let table_size = sqlx::query_scalar::<_, i64>(
        r#"
        SELECT pg_total_relation_size(relid)::bigint
        FROM pg_catalog.pg_statio_user_tables
        WHERE relname = $1
        "#,
    )
    .bind(table_name)
    .fetch_optional(pool)
    .await?
    .unwrap_or(0);

    let ratio_query = format!(
        r#"
        SELECT
            COALESCE(
                (SELECT COUNT(*)::float8 FROM {table_name} WHERE exchange = $1) /
                NULLIF((SELECT COUNT(*)::float8 FROM {table_name}), 0),
                0
            )
        "#
    );
    let ratio = sqlx::query_scalar::<_, f64>(&ratio_query)
        .bind(exchange)
        .fetch_one(pool)
        .await?;

    Ok((table_size as f64 * ratio) as i64)
}

async fn market_trades_collection_range(
    pool: &sqlx::PgPool,
    exchange: &str,
) -> Result<(i64, Option<i64>, Option<i64>), AppError> {
    let row = sqlx::query(
        r#"
        SELECT
            COUNT(DISTINCT symbol)::bigint AS symbol_count,
            MIN(timestamp)::bigint AS min_ts,
            MAX(timestamp)::bigint AS max_ts
        FROM market_trades_aggregated
        WHERE exchange = $1
        "#,
    )
    .bind(exchange)
    .fetch_one(pool)
    .await
    .map_err(|error| AppError::internal(format!("Failed to get storage stats: {error}")))?;

    let symbol_count = row
        .try_get::<i64, _>("symbol_count")
        .map_err(|error| AppError::internal(format!("Failed to read storage stats: {error}")))?;
    let min_ts = row
        .try_get::<Option<i64>, _>("min_ts")
        .map_err(|error| AppError::internal(format!("Failed to read storage stats: {error}")))?;
    let max_ts = row
        .try_get::<Option<i64>, _>("max_ts")
        .map_err(|error| AppError::internal(format!("Failed to read storage stats: {error}")))?;

    Ok((symbol_count, min_ts, max_ts))
}

async fn data_coverage_symbols(
    pool: &sqlx::PgPool,
    table_name: &str,
    start_ts: i64,
    exchange: &str,
) -> Result<Vec<String>, AppError> {
    let query = format!(
        r#"
        SELECT DISTINCT symbol
        FROM {table_name}
        WHERE timestamp >= $1 AND exchange = $2
        ORDER BY symbol
        "#
    );

    sqlx::query_scalar::<_, String>(&query)
        .bind(start_ts)
        .bind(exchange)
        .fetch_all(pool)
        .await
        .map_err(|error| {
            AppError::internal(format!("Failed to get data coverage symbols: {error}"))
        })
}

async fn data_coverage_rows(
    pool: &sqlx::PgPool,
    table_name: &str,
    ts_divisor: f64,
    start_ts: i64,
    symbol: &str,
    exchange: &str,
    offset_interval: &str,
) -> Result<Vec<(String, i64)>, AppError> {
    let query = format!(
        r#"
        SELECT
            to_char(to_timestamp(timestamp::double precision / {ts_divisor}) + ($3::interval), 'YYYY-MM-DD') AS date,
            COUNT(DISTINCT to_char(to_timestamp(timestamp::double precision / {ts_divisor}) + ($3::interval), 'HH24'))::bigint AS hours_with_data
        FROM {table_name}
        WHERE timestamp >= $1 AND symbol = $2 AND exchange = $4
        GROUP BY date
        ORDER BY date
        "#
    );

    let rows = sqlx::query(&query)
        .bind(start_ts)
        .bind(symbol)
        .bind(offset_interval)
        .bind(exchange)
        .fetch_all(pool)
        .await
        .map_err(|error| AppError::internal(format!("Failed to get data coverage: {error}")))?;

    rows.into_iter()
        .map(|row| {
            let date = row.try_get::<String, _>("date").map_err(|error| {
                AppError::internal(format!("Failed to read data coverage: {error}"))
            })?;
            let hours = row.try_get::<i64, _>("hours_with_data").map_err(|error| {
                AppError::internal(format!("Failed to read data coverage: {error}"))
            })?;
            Ok((date, hours))
        })
        .collect()
}

async fn get_backfill_status(
    pool: &sqlx::PgPool,
    table_name: &str,
) -> Result<BackfillStatusResponse, AppError> {
    let query = format!(
        r#"
        SELECT id, symbols, status, progress, error_message, created_at
        FROM {table_name}
        ORDER BY created_at DESC
        LIMIT 1
        "#
    );

    let Some(row) = sqlx::query(&query)
        .fetch_optional(pool)
        .await
        .map_err(|error| AppError::internal(format!("Failed to get backfill status: {error}")))?
    else {
        return Ok(BackfillStatusResponse {
            status: "none".to_owned(),
            progress: 0,
            task_id: None,
            symbols: Vec::new(),
            error_message: None,
            created_at: None,
        });
    };

    let raw_symbols = row
        .try_get::<Option<String>, _>("symbols")
        .map_err(|error| AppError::internal(format!("Failed to read backfill status: {error}")))?
        .unwrap_or_default();
    let created_at = row
        .try_get::<Option<NaiveDateTime>, _>("created_at")
        .map_err(|error| AppError::internal(format!("Failed to read backfill status: {error}")))?
        .map(format_naive_iso);

    Ok(BackfillStatusResponse {
        task_id: Some(row.try_get::<i32, _>("id").map_err(|error| {
            AppError::internal(format!("Failed to read backfill status: {error}"))
        })?),
        symbols: split_symbols(&raw_symbols),
        status: row.try_get::<String, _>("status").map_err(|error| {
            AppError::internal(format!("Failed to read backfill status: {error}"))
        })?,
        progress: row.try_get::<i32, _>("progress").map_err(|error| {
            AppError::internal(format!("Failed to read backfill status: {error}"))
        })?,
        error_message: row
            .try_get::<Option<String>, _>("error_message")
            .map_err(|error| {
                AppError::internal(format!("Failed to read backfill status: {error}"))
            })?,
        created_at,
    })
}

fn validate_retention_days(days: i32) -> Result<(), AppError> {
    if !(7..=730).contains(&days) {
        return Err(AppError::bad_request(
            "Retention days must be between 7 and 730",
        ));
    }
    Ok(())
}

fn storage_tables_for_exchange(exchange: &str) -> Vec<&'static str> {
    let mut tables = vec![
        "market_trades_aggregated",
        "market_asset_metrics",
        "market_orderbook_snapshots",
        "crypto_klines",
    ];
    if exchange == "binance" {
        tables.push("market_sentiment_metrics");
    }
    tables
}

fn coverage_table(data_type: &str) -> &'static str {
    if data_type == "klines" {
        "crypto_klines"
    } else {
        "market_trades_aggregated"
    }
}

fn default_coverage_days() -> i64 {
    30
}

fn default_data_type() -> String {
    "market_flow".to_owned()
}

fn retention_key(exchange: &str) -> &'static str {
    if exchange == "binance" {
        BINANCE_RETENTION_KEY
    } else {
        HYPERLIQUID_RETENTION_KEY
    }
}

fn default_exchange() -> String {
    "hyperliquid".to_owned()
}

fn capitalize(value: &str) -> String {
    let mut chars = value.chars();
    match chars.next() {
        Some(first) => first.to_uppercase().collect::<String>() + chars.as_str(),
        None => String::new(),
    }
}

fn round_one_decimal(value: f64) -> f64 {
    (value * 10.0).round() / 10.0
}

fn round_two_decimals(value: f64) -> f64 {
    (value * 100.0).round() / 100.0
}

fn bytes_per_mb() -> f64 {
    (1024 * 1024) as f64
}

fn split_symbols(raw: &str) -> Vec<String> {
    raw.split(',')
        .filter_map(|symbol| {
            let symbol = symbol.trim();
            if symbol.is_empty() {
                None
            } else {
                Some(symbol.to_owned())
            }
        })
        .collect()
}

fn format_naive_iso(value: NaiveDateTime) -> String {
    value.format("%Y-%m-%dT%H:%M:%S%.f").to_string()
}

#[cfg(test)]
mod tests {
    use axum::http::StatusCode;

    use super::{
        coverage_table, format_naive_iso, retention_key, round_one_decimal, round_two_decimals,
        split_symbols, storage_tables_for_exchange, validate_retention_days,
    };

    #[test]
    fn retention_key_matches_legacy_exchange_rules() {
        assert_eq!(retention_key("binance"), "binance_retention_days");
        assert_eq!(retention_key("hyperliquid"), "hyperliquid_retention_days");
        assert_eq!(retention_key("unknown"), "hyperliquid_retention_days");
    }

    #[test]
    fn validates_retention_range() {
        assert!(validate_retention_days(7).is_ok());
        assert!(validate_retention_days(730).is_ok());

        let error = validate_retention_days(6).expect_err("too-low value should fail");
        assert_eq!(error.status, StatusCode::BAD_REQUEST);
        assert_eq!(error.message, "Retention days must be between 7 and 730");
    }

    #[test]
    fn rounds_collection_days_like_legacy_route() {
        assert_eq!(round_one_decimal(12.34), 12.3);
        assert_eq!(round_one_decimal(12.35), 12.4);
    }

    #[test]
    fn storage_tables_match_legacy_exchange_rules() {
        assert_eq!(
            storage_tables_for_exchange("hyperliquid"),
            vec![
                "market_trades_aggregated",
                "market_asset_metrics",
                "market_orderbook_snapshots",
                "crypto_klines"
            ]
        );
        assert!(storage_tables_for_exchange("binance").contains(&"market_sentiment_metrics"));
    }

    #[test]
    fn coverage_table_is_whitelisted_by_data_type() {
        assert_eq!(coverage_table("klines"), "crypto_klines");
        assert_eq!(coverage_table("market_flow"), "market_trades_aggregated");
        assert_eq!(coverage_table("anything_else"), "market_trades_aggregated");
    }

    #[test]
    fn rounds_storage_estimates_like_legacy_route() {
        assert_eq!(round_two_decimals(6.666), 6.67);
        assert_eq!(round_two_decimals(6.664), 6.66);
    }

    #[test]
    fn splits_backfill_symbols_like_legacy_route() {
        assert_eq!(split_symbols("BTC,ETH, SOL"), vec!["BTC", "ETH", "SOL"]);
        assert!(split_symbols("").is_empty());
    }

    #[test]
    fn formats_backfill_created_at_as_iso_string() {
        let value = chrono::NaiveDate::from_ymd_opt(2026, 4, 14)
            .expect("date should be valid")
            .and_hms_opt(5, 6, 7)
            .expect("time should be valid");
        assert_eq!(format_naive_iso(value), "2026-04-14T05:06:07");
    }
}
