use axum::{
    Json,
    extract::{Query, State},
};
use chrono::NaiveDateTime;
use serde::{Deserialize, Serialize};
use sqlx::Row;

use crate::{error::AppError, state::AppState};

#[derive(Deserialize)]
pub struct ActionListQuery {
    #[serde(default = "default_limit")]
    limit: i64,
    account_id: Option<i32>,
    environment: Option<String>,
    wallet_address: Option<String>,
}

#[derive(Serialize)]
pub struct ActionListResponse {
    entries: Vec<ExchangeActionEntry>,
    stats: ExchangeActionStats,
}

#[derive(Serialize)]
pub struct ExchangeActionEntry {
    id: i32,
    timestamp: Option<String>,
    account_id: i32,
    environment: String,
    wallet_address: String,
    action_type: String,
    status: String,
    symbol: Option<String>,
    side: Option<String>,
    leverage: Option<i32>,
    size: Option<f64>,
    price: Option<f64>,
    notional: Option<f64>,
    request_weight: i32,
    error_message: Option<String>,
    request_payload: Option<String>,
    response_payload: Option<String>,
}

#[derive(Serialize)]
pub struct ExchangeActionStats {
    total: i64,
    success: i64,
    error: i64,
    last24h: i64,
    request_weight_sum: i64,
}

pub async fn list_exchange_actions(
    State(state): State<AppState>,
    Query(query): Query<ActionListQuery>,
) -> Result<Json<ActionListResponse>, AppError> {
    validate_action_query(&query)?;

    let entries = load_action_entries(&state.db, &query).await?;
    let stats = load_action_stats(&state.db, &query).await?;

    Ok(Json(ActionListResponse { entries, stats }))
}

async fn load_action_entries(
    pool: &sqlx::PgPool,
    query: &ActionListQuery,
) -> Result<Vec<ExchangeActionEntry>, AppError> {
    let rows = sqlx::query(
        r#"
        SELECT
            id,
            created_at,
            account_id,
            environment,
            wallet_address,
            action_type,
            status,
            symbol,
            side,
            leverage,
            size::float8 AS size,
            price::float8 AS price,
            notional::float8 AS notional,
            request_weight,
            error_message,
            request_payload,
            response_payload
        FROM hyperliquid_exchange_actions
        WHERE ($1::int4 IS NULL OR account_id = $1)
          AND ($2::text IS NULL OR environment = $2)
          AND ($3::text IS NULL OR wallet_address = $3)
        ORDER BY created_at DESC
        LIMIT $4
        "#,
    )
    .bind(query.account_id)
    .bind(query.environment.as_deref())
    .bind(query.wallet_address.as_deref())
    .bind(query.limit)
    .fetch_all(pool)
    .await
    .map_err(|error| AppError::internal(format!("Failed to list Hyperliquid actions: {error}")))?;

    rows.into_iter()
        .map(row_to_action_entry)
        .collect::<Result<Vec<_>, _>>()
}

async fn load_action_stats(
    pool: &sqlx::PgPool,
    query: &ActionListQuery,
) -> Result<ExchangeActionStats, AppError> {
    let row = sqlx::query(
        r#"
        SELECT
            COUNT(*)::bigint AS total,
            COUNT(*) FILTER (WHERE status = 'success')::bigint AS success,
            COUNT(*) FILTER (WHERE status = 'error')::bigint AS error,
            COUNT(*) FILTER (WHERE created_at >= CURRENT_TIMESTAMP - INTERVAL '24 hours')::bigint AS last24h,
            COALESCE(SUM(request_weight), 0)::bigint AS request_weight_sum
        FROM hyperliquid_exchange_actions
        WHERE ($1::int4 IS NULL OR account_id = $1)
          AND ($2::text IS NULL OR environment = $2)
          AND ($3::text IS NULL OR wallet_address = $3)
        "#,
    )
    .bind(query.account_id)
    .bind(query.environment.as_deref())
    .bind(query.wallet_address.as_deref())
    .fetch_one(pool)
    .await
    .map_err(|error| AppError::internal(format!("Failed to load Hyperliquid action stats: {error}")))?;

    Ok(ExchangeActionStats {
        total: row.try_get("total").map_err(|error| {
            AppError::internal(format!("Failed to read Hyperliquid action stats: {error}"))
        })?,
        success: row.try_get("success").map_err(|error| {
            AppError::internal(format!("Failed to read Hyperliquid action stats: {error}"))
        })?,
        error: row.try_get("error").map_err(|error| {
            AppError::internal(format!("Failed to read Hyperliquid action stats: {error}"))
        })?,
        last24h: row.try_get("last24h").map_err(|error| {
            AppError::internal(format!("Failed to read Hyperliquid action stats: {error}"))
        })?,
        request_weight_sum: row.try_get("request_weight_sum").map_err(|error| {
            AppError::internal(format!("Failed to read Hyperliquid action stats: {error}"))
        })?,
    })
}

fn row_to_action_entry(row: sqlx::postgres::PgRow) -> Result<ExchangeActionEntry, AppError> {
    let timestamp = row
        .try_get::<Option<NaiveDateTime>, _>("created_at")
        .map_err(|error| AppError::internal(format!("Failed to read Hyperliquid action: {error}")))?
        .map(format_naive_iso);

    Ok(ExchangeActionEntry {
        id: row.try_get("id").map_err(|error| {
            AppError::internal(format!("Failed to read Hyperliquid action: {error}"))
        })?,
        timestamp,
        account_id: row.try_get("account_id").map_err(|error| {
            AppError::internal(format!("Failed to read Hyperliquid action: {error}"))
        })?,
        environment: row.try_get("environment").map_err(|error| {
            AppError::internal(format!("Failed to read Hyperliquid action: {error}"))
        })?,
        wallet_address: row.try_get("wallet_address").map_err(|error| {
            AppError::internal(format!("Failed to read Hyperliquid action: {error}"))
        })?,
        action_type: row.try_get("action_type").map_err(|error| {
            AppError::internal(format!("Failed to read Hyperliquid action: {error}"))
        })?,
        status: row.try_get("status").map_err(|error| {
            AppError::internal(format!("Failed to read Hyperliquid action: {error}"))
        })?,
        symbol: row.try_get("symbol").map_err(|error| {
            AppError::internal(format!("Failed to read Hyperliquid action: {error}"))
        })?,
        side: row.try_get("side").map_err(|error| {
            AppError::internal(format!("Failed to read Hyperliquid action: {error}"))
        })?,
        leverage: row.try_get("leverage").map_err(|error| {
            AppError::internal(format!("Failed to read Hyperliquid action: {error}"))
        })?,
        size: row.try_get("size").map_err(|error| {
            AppError::internal(format!("Failed to read Hyperliquid action: {error}"))
        })?,
        price: row.try_get("price").map_err(|error| {
            AppError::internal(format!("Failed to read Hyperliquid action: {error}"))
        })?,
        notional: row.try_get("notional").map_err(|error| {
            AppError::internal(format!("Failed to read Hyperliquid action: {error}"))
        })?,
        request_weight: row.try_get("request_weight").map_err(|error| {
            AppError::internal(format!("Failed to read Hyperliquid action: {error}"))
        })?,
        error_message: row.try_get("error_message").map_err(|error| {
            AppError::internal(format!("Failed to read Hyperliquid action: {error}"))
        })?,
        request_payload: row.try_get("request_payload").map_err(|error| {
            AppError::internal(format!("Failed to read Hyperliquid action: {error}"))
        })?,
        response_payload: row.try_get("response_payload").map_err(|error| {
            AppError::internal(format!("Failed to read Hyperliquid action: {error}"))
        })?,
    })
}

fn validate_action_query(query: &ActionListQuery) -> Result<(), AppError> {
    if !(1..=500).contains(&query.limit) {
        return Err(AppError::bad_request("limit must be between 1 and 500"));
    }

    if let Some(environment) = &query.environment {
        if environment != "testnet" && environment != "mainnet" {
            return Err(AppError::bad_request(
                "environment must be testnet or mainnet",
            ));
        }
    }

    Ok(())
}

fn format_naive_iso(value: NaiveDateTime) -> String {
    value.format("%Y-%m-%dT%H:%M:%S%.f").to_string()
}

fn default_limit() -> i64 {
    100
}

#[cfg(test)]
mod tests {
    use axum::http::StatusCode;

    use super::{ActionListQuery, default_limit, validate_action_query};

    #[test]
    fn default_limit_matches_legacy_route() {
        assert_eq!(default_limit(), 100);
    }

    #[test]
    fn validates_limit_range() {
        let query = ActionListQuery {
            limit: 501,
            account_id: None,
            environment: None,
            wallet_address: None,
        };
        let error = validate_action_query(&query).expect_err("limit should fail");
        assert_eq!(error.status, StatusCode::BAD_REQUEST);
    }

    #[test]
    fn validates_environment_values() {
        let query = ActionListQuery {
            limit: 100,
            account_id: None,
            environment: Some("devnet".to_owned()),
            wallet_address: None,
        };
        let error = validate_action_query(&query).expect_err("environment should fail");
        assert_eq!(error.status, StatusCode::BAD_REQUEST);
    }
}
