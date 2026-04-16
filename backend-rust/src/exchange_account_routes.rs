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
use url::form_urlencoded;

use crate::{
    error::AppError,
    proxy::{build_downstream_streaming_response, build_upstream_request},
    state::AppState,
};

const DEFAULT_HYPERLIQUID_MAX_LEVERAGE: i32 = 3;
const DEFAULT_HYPERLIQUID_DEFAULT_LEVERAGE: i32 = 1;

#[derive(Deserialize)]
pub struct ExchangeEnvironmentQuery {
    environment: Option<String>,
    force_refresh: Option<bool>,
}

#[derive(Serialize)]
pub struct HyperliquidHealthResponse {
    status: String,
    service: String,
    encryption_configured: bool,
    endpoints: Value,
}

#[derive(Serialize)]
pub struct BinanceConfigInfo {
    configured: bool,
    api_key_masked: String,
    max_leverage: i32,
    default_leverage: i32,
}

#[derive(Serialize)]
pub struct TradingModeResponse {
    success: bool,
    mode: String,
    description: String,
}

#[derive(Deserialize)]
pub struct WalletTestRequest {
    environment: Option<String>,
}

#[derive(Deserialize)]
pub struct SnapshotQuery {
    #[serde(default = "default_snapshot_limit")]
    limit: i64,
}

#[derive(Deserialize)]
pub struct HyperliquidWalletDeleteQuery {
    environment: Option<String>,
}

#[derive(Deserialize)]
pub struct PendingOrdersQuery {
    user_id: Option<String>,
}

#[derive(Deserialize)]
pub struct UserOrdersQuery {
    status: Option<String>,
}

#[derive(Deserialize)]
pub struct CancelOrderQuery {
    reason: Option<String>,
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

async fn resolve_live_environment(
    state: &AppState,
    environment: Option<&str>,
) -> Result<String, AppError> {
    match environment {
        Some("testnet" | "mainnet") => Ok(environment.unwrap().to_owned()),
        Some(other) => Err(AppError::bad_request(format!(
            "Invalid environment `{other}`"
        ))),
        None => get_global_trading_mode(state).await,
    }
}

async fn ensure_account_exists(state: &AppState, account_id: i32) -> Result<(), AppError> {
    let exists = sqlx::query_scalar::<_, Option<i32>>(
        "SELECT 1 FROM accounts WHERE id = $1 AND COALESCE(is_deleted, false) = false LIMIT 1",
    )
    .bind(account_id)
    .fetch_optional(&state.db)
    .await
    .map_err(|error| AppError::internal(format!("Failed to check account: {error}")))?;

    if exists.flatten().is_some() {
        Ok(())
    } else {
        Err(AppError::not_found("Account not found"))
    }
}

async fn ensure_hyperliquid_wallet(
    state: &AppState,
    account_id: i32,
    environment: &str,
) -> Result<sqlx::postgres::PgRow, AppError> {
    sqlx::query(
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
    .map_err(|error| AppError::internal(format!("Failed to load Hyperliquid wallet: {error}")))?
    .ok_or_else(|| AppError::not_found(format!("No {environment} wallet configured")))
}

async fn ensure_binance_wallet(
    state: &AppState,
    account_id: i32,
    environment: &str,
) -> Result<(), AppError> {
    let exists = sqlx::query_scalar::<_, Option<i32>>(
        r#"
        SELECT 1
        FROM binance_wallets
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
    .map_err(|error| AppError::internal(format!("Failed to load Binance wallet: {error}")))?;

    if exists.flatten().is_some() {
        Ok(())
    } else {
        Err(AppError::not_found(format!(
            "No {environment} wallet configured"
        )))
    }
}

async fn latest_binance_snapshot(
    state: &AppState,
    account_id: i32,
    environment: &str,
) -> Result<Option<sqlx::postgres::PgRow>, AppError> {
    sqlx::query(
        r#"
        SELECT
            total_wallet_balance::float8 AS total_wallet_balance,
            available_balance::float8 AS available_balance,
            total_unrealized_profit::float8 AS total_unrealized_profit,
            total_margin_balance::float8 AS total_margin_balance,
            total_initial_margin::float8 AS total_initial_margin,
            total_maint_margin::float8 AS total_maint_margin,
            snapshot_time,
            snapshot_data
        FROM binance_account_snapshots
        WHERE account_id = $1
          AND environment = $2
        ORDER BY snapshot_time DESC, id DESC
        LIMIT 1
        "#,
    )
    .bind(account_id)
    .bind(environment)
    .fetch_optional(&state.db)
    .await
    .map_err(|error| AppError::internal(format!("Failed to load Binance snapshot: {error}")))
}

async fn latest_hyperliquid_snapshot(
    state: &AppState,
    account_id: i32,
    environment: &str,
) -> Result<Option<sqlx::postgres::PgRow>, AppError> {
    sqlx::query(
        r#"
        SELECT
            wallet_address,
            total_equity::float8 AS total_equity,
            available_balance::float8 AS available_balance,
            used_margin::float8 AS used_margin,
            maintenance_margin::float8 AS maintenance_margin,
            snapshot_time
        FROM hyperliquid_account_snapshots
        WHERE account_id = $1
          AND environment = $2
        ORDER BY snapshot_time DESC, id DESC
        LIMIT 1
        "#,
    )
    .bind(account_id)
    .bind(environment)
    .fetch_optional(&state.db)
    .await
    .map_err(|error| AppError::internal(format!("Failed to load Hyperliquid snapshot: {error}")))
}

fn default_snapshot_limit() -> i64 {
    100
}

fn parse_hyperliquid_wallet_config_request(payload: Value) -> Result<Value, AppError> {
    let object = payload
        .as_object()
        .ok_or_else(|| wallet_config_validation_error("request body must be a JSON object"))?;
    let private_key = parse_private_key_field(object)?;
    let environment = parse_wallet_environment(object)?;
    let max_leverage = parse_wallet_leverage_field(
        object,
        "max_leverage",
        "maxLeverage",
        DEFAULT_HYPERLIQUID_MAX_LEVERAGE,
    )?;
    let default_leverage = parse_wallet_leverage_field(
        object,
        "default_leverage",
        "defaultLeverage",
        DEFAULT_HYPERLIQUID_DEFAULT_LEVERAGE,
    )?;

    Ok(serde_json::json!({
        "private_key": private_key,
        "environment": environment,
        "max_leverage": max_leverage,
        "default_leverage": default_leverage
    }))
}

fn parse_hyperliquid_setup_request(payload: Value) -> Result<Value, AppError> {
    let object = payload
        .as_object()
        .ok_or_else(|| wallet_config_validation_error("request body must be a JSON object"))?;
    let private_key = parse_private_key_field(object)?;
    let environment = parse_required_wallet_environment(object)?;
    let max_leverage = parse_wallet_leverage_field(
        object,
        "max_leverage",
        "maxLeverage",
        DEFAULT_HYPERLIQUID_MAX_LEVERAGE,
    )?;
    let default_leverage = parse_wallet_leverage_field(
        object,
        "default_leverage",
        "defaultLeverage",
        DEFAULT_HYPERLIQUID_DEFAULT_LEVERAGE,
    )?;

    Ok(serde_json::json!({
        "private_key": private_key,
        "environment": environment,
        "max_leverage": max_leverage,
        "default_leverage": default_leverage
    }))
}

fn parse_private_key_field(payload: &Map<String, Value>) -> Result<String, AppError> {
    let key_value = payload
        .get("private_key")
        .or_else(|| payload.get("privateKey"))
        .ok_or_else(|| wallet_config_validation_error("privateKey (or private_key) is required"))?;
    let private_key = key_value.as_str().ok_or_else(|| {
        wallet_config_validation_error("privateKey (or private_key) must be a string")
    })?;
    normalize_private_key(private_key)
}

fn normalize_private_key(private_key: &str) -> Result<String, AppError> {
    let trimmed = private_key.trim();
    if trimmed.is_empty() {
        return Err(wallet_config_validation_error(
            "privateKey (or private_key) is required",
        ));
    }
    let normalized = trimmed
        .strip_prefix("0x")
        .or_else(|| trimmed.strip_prefix("0X"))
        .unwrap_or(trimmed);
    if normalized.len() != 64 || !normalized.chars().all(|ch| ch.is_ascii_hexdigit()) {
        return Err(wallet_config_validation_error(
            "Invalid private key format. Must be 64 hex characters (with or without 0x prefix)",
        ));
    }

    Ok(format!("0x{normalized}"))
}

fn parse_wallet_environment(payload: &Map<String, Value>) -> Result<String, AppError> {
    let Some(environment) = payload.get("environment") else {
        return Ok("testnet".to_owned());
    };
    let environment = environment
        .as_str()
        .ok_or_else(|| wallet_config_validation_error("environment must be a string"))?;
    match environment {
        "testnet" | "mainnet" => Ok(environment.to_owned()),
        _ => Err(wallet_config_validation_error(
            "Environment must be 'testnet' or 'mainnet'",
        )),
    }
}

fn parse_required_wallet_environment(payload: &Map<String, Value>) -> Result<String, AppError> {
    let environment = payload
        .get("environment")
        .ok_or_else(|| wallet_config_validation_error("environment is required"))?;
    let environment = environment
        .as_str()
        .ok_or_else(|| wallet_config_validation_error("environment must be a string"))?;
    match environment {
        "testnet" | "mainnet" => Ok(environment.to_owned()),
        _ => Err(wallet_config_validation_error(
            "environment must be 'testnet' or 'mainnet'",
        )),
    }
}

fn parse_wallet_delete_environment(environment: Option<&str>) -> Result<String, AppError> {
    let environment = environment
        .map(str::trim)
        .filter(|environment| !environment.is_empty())
        .ok_or_else(|| wallet_config_validation_error("environment query parameter is required"))?;

    match environment {
        "testnet" | "mainnet" => Ok(environment.to_owned()),
        _ => Err(wallet_config_validation_error(
            "environment query parameter must be 'testnet' or 'mainnet'",
        )),
    }
}

fn parse_trading_mode_update_request(payload: Value) -> Result<Value, AppError> {
    let object = payload
        .as_object()
        .ok_or_else(|| wallet_config_validation_error("request body must be a JSON object"))?;
    let mode = object
        .get("mode")
        .ok_or_else(|| wallet_config_validation_error("mode is required"))?
        .as_str()
        .ok_or_else(|| wallet_config_validation_error("mode must be a string"))?
        .trim()
        .to_owned();

    match mode.as_str() {
        "testnet" | "mainnet" => Ok(serde_json::json!({ "mode": mode })),
        _ => Err(wallet_config_validation_error(
            "mode must be 'testnet' or 'mainnet'",
        )),
    }
}

fn parse_switch_environment_request(payload: Value) -> Result<Value, AppError> {
    let object = payload
        .as_object()
        .ok_or_else(|| wallet_config_validation_error("request body must be a JSON object"))?;
    let target_environment = object
        .get("target_environment")
        .or_else(|| object.get("targetEnvironment"))
        .ok_or_else(|| {
            wallet_config_validation_error("target_environment (or targetEnvironment) is required")
        })?
        .as_str()
        .ok_or_else(|| {
            wallet_config_validation_error(
                "target_environment (or targetEnvironment) must be a string",
            )
        })?
        .trim()
        .to_owned();
    let target_environment = match target_environment.as_str() {
        "testnet" | "mainnet" => target_environment,
        _ => {
            return Err(wallet_config_validation_error(
                "target_environment must be 'testnet' or 'mainnet'",
            ));
        }
    };
    let confirm_switch = object
        .get("confirm_switch")
        .or_else(|| object.get("confirmSwitch"))
        .or_else(|| object.get("confirm"))
        .map(|value| {
            value.as_bool().ok_or_else(|| {
                wallet_config_validation_error(
                    "confirm_switch (or confirmSwitch/confirm) must be a boolean",
                )
            })
        })
        .transpose()?
        .unwrap_or(false);

    Ok(serde_json::json!({
        "target_environment": target_environment,
        "confirm_switch": confirm_switch
    }))
}

fn parse_manual_order_request(payload: Value) -> Result<Value, AppError> {
    let object = payload
        .as_object()
        .ok_or_else(|| wallet_config_validation_error("request body must be a JSON object"))?;
    let symbol = object
        .get("symbol")
        .ok_or_else(|| wallet_config_validation_error("symbol is required"))?
        .as_str()
        .ok_or_else(|| wallet_config_validation_error("symbol must be a string"))?
        .trim()
        .to_owned();
    if symbol.is_empty() {
        return Err(wallet_config_validation_error("symbol is required"));
    }
    let is_buy = object
        .get("is_buy")
        .or_else(|| object.get("isBuy"))
        .ok_or_else(|| wallet_config_validation_error("is_buy (or isBuy) is required"))?
        .as_bool()
        .ok_or_else(|| wallet_config_validation_error("is_buy (or isBuy) must be a boolean"))?;
    let size = object
        .get("size")
        .ok_or_else(|| wallet_config_validation_error("size is required"))?
        .as_f64()
        .ok_or_else(|| wallet_config_validation_error("size must be a number greater than 0"))?;
    if size <= 0.0 {
        return Err(wallet_config_validation_error(
            "size must be a number greater than 0",
        ));
    }
    let price = object
        .get("price")
        .ok_or_else(|| wallet_config_validation_error("price is required"))?
        .as_f64()
        .ok_or_else(|| wallet_config_validation_error("price must be a number greater than 0"))?;
    if price <= 0.0 {
        return Err(wallet_config_validation_error(
            "price must be a number greater than 0",
        ));
    }
    let time_in_force = object
        .get("time_in_force")
        .or_else(|| object.get("timeInForce"))
        .map(|value| {
            value
                .as_str()
                .ok_or_else(|| {
                    wallet_config_validation_error(
                        "time_in_force (or timeInForce) must be a string",
                    )
                })
                .map(str::trim)
                .map(str::to_owned)
        })
        .transpose()?
        .unwrap_or_else(|| "Ioc".to_owned());
    if !matches!(time_in_force.as_str(), "Ioc" | "Gtc" | "Alo") {
        return Err(wallet_config_validation_error(
            "time_in_force must be one of 'Ioc', 'Gtc', or 'Alo'",
        ));
    }
    let leverage = object
        .get("leverage")
        .map(|value| {
            value
                .as_i64()
                .ok_or_else(|| wallet_config_validation_error("leverage must be an integer"))
        })
        .transpose()?
        .unwrap_or(1);
    if !(1..=50).contains(&leverage) {
        return Err(wallet_config_validation_error(
            "leverage must be between 1 and 50",
        ));
    }
    let reduce_only = object
        .get("reduce_only")
        .or_else(|| object.get("reduceOnly"))
        .map(|value| {
            value.as_bool().ok_or_else(|| {
                wallet_config_validation_error("reduce_only (or reduceOnly) must be a boolean")
            })
        })
        .transpose()?
        .unwrap_or(false);
    let take_profit_price = object
        .get("take_profit_price")
        .or_else(|| object.get("takeProfitPrice"))
        .map(|value| {
            value.as_f64().ok_or_else(|| {
                wallet_config_validation_error(
                    "take_profit_price (or takeProfitPrice) must be a positive number",
                )
            })
        })
        .transpose()?;
    if take_profit_price.is_some_and(|value| value <= 0.0) {
        return Err(wallet_config_validation_error(
            "take_profit_price (or takeProfitPrice) must be a positive number",
        ));
    }
    let stop_loss_price = object
        .get("stop_loss_price")
        .or_else(|| object.get("stopLossPrice"))
        .map(|value| {
            value.as_f64().ok_or_else(|| {
                wallet_config_validation_error(
                    "stop_loss_price (or stopLossPrice) must be a positive number",
                )
            })
        })
        .transpose()?;
    if stop_loss_price.is_some_and(|value| value <= 0.0) {
        return Err(wallet_config_validation_error(
            "stop_loss_price (or stopLossPrice) must be a positive number",
        ));
    }
    let environment = object
        .get("environment")
        .map(|value| {
            value
                .as_str()
                .ok_or_else(|| wallet_config_validation_error("environment must be a string"))
        })
        .transpose()?
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .map(str::to_owned);

    let mut normalized = Map::new();
    normalized.insert("symbol".to_owned(), Value::String(symbol));
    normalized.insert("is_buy".to_owned(), Value::Bool(is_buy));
    normalized.insert("size".to_owned(), Value::from(size));
    normalized.insert("price".to_owned(), Value::from(price));
    normalized.insert("time_in_force".to_owned(), Value::String(time_in_force));
    normalized.insert("leverage".to_owned(), Value::from(leverage));
    normalized.insert("reduce_only".to_owned(), Value::Bool(reduce_only));
    if let Some(take_profit_price) = take_profit_price {
        normalized.insert(
            "take_profit_price".to_owned(),
            Value::from(take_profit_price),
        );
    }
    if let Some(stop_loss_price) = stop_loss_price {
        normalized.insert("stop_loss_price".to_owned(), Value::from(stop_loss_price));
    }
    if let Some(environment) = environment {
        normalized.insert("environment".to_owned(), Value::String(environment));
    }

    Ok(Value::Object(normalized))
}

fn parse_order_create_request(payload: Value) -> Result<Value, AppError> {
    let object = payload
        .as_object()
        .ok_or_else(|| orders_route_validation_error("request body must be a JSON object"))?;

    let user_id = object
        .get("user_id")
        .or_else(|| object.get("userId"))
        .ok_or_else(|| orders_route_validation_error("user_id (or userId) is required"))?
        .as_i64()
        .ok_or_else(|| orders_route_validation_error("user_id (or userId) must be an integer"))
        .and_then(|value| {
            i32::try_from(value).map_err(|_| {
                orders_route_validation_error("user_id (or userId) must be an integer")
            })
        })?;
    let symbol = object
        .get("symbol")
        .ok_or_else(|| orders_route_validation_error("symbol is required"))?
        .as_str()
        .ok_or_else(|| orders_route_validation_error("symbol must be a string"))?;
    let name = object
        .get("name")
        .ok_or_else(|| orders_route_validation_error("name is required"))?
        .as_str()
        .ok_or_else(|| orders_route_validation_error("name must be a string"))?;
    let side = object
        .get("side")
        .ok_or_else(|| orders_route_validation_error("side is required"))?
        .as_str()
        .ok_or_else(|| orders_route_validation_error("side must be a string"))?;
    let order_type = object
        .get("order_type")
        .or_else(|| object.get("orderType"))
        .ok_or_else(|| orders_route_validation_error("order_type (or orderType) is required"))?
        .as_str()
        .ok_or_else(|| {
            orders_route_validation_error("order_type (or orderType) must be a string")
        })?;
    let quantity = object
        .get("quantity")
        .ok_or_else(|| orders_route_validation_error("quantity is required"))?
        .as_f64()
        .ok_or_else(|| orders_route_validation_error("quantity must be a number"))?;
    let price = object
        .get("price")
        .and_then(|value| (!value.is_null()).then_some(value))
        .map(|value| {
            value
                .as_f64()
                .ok_or_else(|| orders_route_validation_error("price must be a number"))
        })
        .transpose()?;
    let username = object
        .get("username")
        .and_then(|value| (!value.is_null()).then_some(value))
        .map(|value| {
            value
                .as_str()
                .ok_or_else(|| orders_route_validation_error("username must be a string"))
        })
        .transpose()?;
    let password = object
        .get("password")
        .and_then(|value| (!value.is_null()).then_some(value))
        .map(|value| {
            value
                .as_str()
                .ok_or_else(|| orders_route_validation_error("password must be a string"))
        })
        .transpose()?;
    let session_token = object
        .get("session_token")
        .or_else(|| object.get("sessionToken"))
        .and_then(|value| (!value.is_null()).then_some(value))
        .map(|value| {
            value.as_str().ok_or_else(|| {
                orders_route_validation_error("session_token (or sessionToken) must be a string")
            })
        })
        .transpose()?;

    let mut normalized = Map::new();
    normalized.insert("user_id".to_owned(), Value::from(user_id));
    normalized.insert("symbol".to_owned(), Value::String(symbol.to_owned()));
    normalized.insert("name".to_owned(), Value::String(name.to_owned()));
    normalized.insert("side".to_owned(), Value::String(side.to_owned()));
    normalized.insert(
        "order_type".to_owned(),
        Value::String(order_type.to_owned()),
    );
    normalized.insert("quantity".to_owned(), Value::from(quantity));
    if let Some(price) = price {
        normalized.insert("price".to_owned(), Value::from(price));
    }
    if let Some(username) = username {
        normalized.insert("username".to_owned(), Value::String(username.to_owned()));
    }
    if let Some(password) = password {
        normalized.insert("password".to_owned(), Value::String(password.to_owned()));
    }
    if let Some(session_token) = session_token {
        normalized.insert(
            "session_token".to_owned(),
            Value::String(session_token.to_owned()),
        );
    }

    Ok(Value::Object(normalized))
}

fn parse_pending_orders_user_id(user_id: Option<&str>) -> Result<Option<i32>, AppError> {
    let Some(raw_user_id) = user_id else {
        return Ok(None);
    };
    let normalized = raw_user_id.trim();
    if normalized.is_empty() {
        return Err(orders_route_validation_error(
            "user_id query parameter must be a valid integer",
        ));
    }

    normalized.parse::<i32>().map(Some).map_err(|_| {
        orders_route_validation_error("user_id query parameter must be a valid integer")
    })
}

fn parse_user_orders_path_user_id(user_id: &str) -> Result<i32, AppError> {
    user_id.parse::<i32>().map_err(|_| {
        orders_route_validation_error("user_id path parameter must be a valid integer")
    })
}

fn parse_execute_order_path_order_id(order_id: &str) -> Result<i32, AppError> {
    order_id.parse::<i32>().map_err(|_| {
        orders_route_validation_error("order_id path parameter must be a valid integer")
    })
}

fn parse_cancel_order_reason(reason: Option<&str>) -> String {
    reason
        .map(str::to_owned)
        .unwrap_or_else(|| "User cancelled".to_owned())
}

fn parse_user_orders_status(status: Option<&str>) -> Option<String> {
    status
        .map(str::trim)
        .filter(|status| !status.is_empty())
        .map(str::to_owned)
}

fn parse_wallet_leverage_field(
    payload: &Map<String, Value>,
    snake_case_key: &str,
    camel_case_key: &str,
    default_value: i32,
) -> Result<i32, AppError> {
    let Some(raw_value) = payload
        .get(snake_case_key)
        .or_else(|| payload.get(camel_case_key))
    else {
        return Ok(default_value);
    };
    let leverage = raw_value.as_i64().ok_or_else(|| {
        wallet_config_validation_error(format!(
            "{camel_case_key} (or {snake_case_key}) must be an integer"
        ))
    })?;
    if !(1..=50).contains(&leverage) {
        return Err(wallet_config_validation_error(format!(
            "{camel_case_key} (or {snake_case_key}) must be between 1 and 50"
        )));
    }
    i32::try_from(leverage).map_err(|_| {
        wallet_config_validation_error(format!(
            "{camel_case_key} (or {snake_case_key}) must be between 1 and 50"
        ))
    })
}

fn wallet_config_validation_error(message: impl Into<String>) -> AppError {
    AppError {
        status: StatusCode::UNPROCESSABLE_ENTITY,
        message: message.into(),
    }
}

fn orders_route_validation_error(message: impl Into<String>) -> AppError {
    AppError {
        status: StatusCode::UNPROCESSABLE_ENTITY,
        message: message.into(),
    }
}

fn read_exchange_error(error: sqlx::Error) -> AppError {
    AppError::internal(format!("Failed to read exchange data: {error}"))
}

pub async fn get_hyperliquid_health() -> Json<HyperliquidHealthResponse> {
    Json(HyperliquidHealthResponse {
        status: "healthy".to_owned(),
        service: "hyperliquid".to_owned(),
        encryption_configured: std::env::var("HYPERLIQUID_ENCRYPTION_KEY")
            .ok()
            .filter(|value| !value.is_empty())
            .is_some(),
        endpoints: serde_json::json!({
            "setup": "/api/hyperliquid/accounts/{id}/setup",
            "balance": "/api/hyperliquid/accounts/{id}/balance",
            "positions": "/api/hyperliquid/accounts/{id}/positions",
            "snapshots": "/api/hyperliquid/accounts/{id}/snapshots",
            "test": "/api/hyperliquid/accounts/{id}/test-connection",
            "wallet": "/api/hyperliquid/accounts/{id}/wallet"
        }),
    })
}

pub async fn get_hyperliquid_trading_mode(
    State(state): State<AppState>,
) -> Result<Json<TradingModeResponse>, AppError> {
    let mode = get_global_trading_mode(&state).await?;
    Ok(Json(TradingModeResponse {
        success: true,
        description: if mode == "testnet" {
            "Testnet (paper trading)".to_owned()
        } else {
            "Mainnet (real funds)".to_owned()
        },
        mode,
    }))
}

pub async fn set_hyperliquid_trading_mode(
    State(state): State<AppState>,
    headers: HeaderMap,
    Json(payload): Json<Value>,
) -> Result<Response, AppError> {
    let request_payload = parse_trading_mode_update_request(payload)?;
    let request_body = serde_json::to_vec(&request_payload).map_err(|error| {
        AppError::internal(format!(
            "Failed to encode Hyperliquid trading mode request: {error}"
        ))
    })?;
    let target_url = state
        .config
        .legacy_http_target("/api/hyperliquid/trading-mode");
    let upstream_request = build_upstream_request(
        &state.client,
        Method::POST,
        &headers,
        target_url,
        request_body.into(),
    )?;
    let upstream_response = upstream_request.send().await.map_err(|error| {
        AppError::bad_gateway(format!(
            "legacy Hyperliquid trading mode request failed: {error}"
        ))
    })?;

    build_downstream_streaming_response(upstream_response)
}

pub async fn setup_hyperliquid_account(
    State(state): State<AppState>,
    Path(account_id): Path<String>,
    headers: HeaderMap,
    Json(payload): Json<Value>,
) -> Result<Response, AppError> {
    let account_id = account_id
        .parse::<i32>()
        .map_err(|_| wallet_config_validation_error("account_id must be a valid integer"))?;
    let request_payload = parse_hyperliquid_setup_request(payload)?;
    let request_body = serde_json::to_vec(&request_payload).map_err(|error| {
        AppError::internal(format!(
            "Failed to encode Hyperliquid setup request: {error}"
        ))
    })?;
    let target_url = state
        .config
        .legacy_http_target(&format!("/api/hyperliquid/accounts/{account_id}/setup"));
    let upstream_request = build_upstream_request(
        &state.client,
        Method::POST,
        &headers,
        target_url,
        request_body.into(),
    )?;
    let upstream_response = upstream_request.send().await.map_err(|error| {
        AppError::bad_gateway(format!("legacy Hyperliquid setup request failed: {error}"))
    })?;

    build_downstream_streaming_response(upstream_response)
}

pub async fn switch_hyperliquid_account_environment(
    State(state): State<AppState>,
    Path(account_id): Path<String>,
    headers: HeaderMap,
    Json(payload): Json<Value>,
) -> Result<Response, AppError> {
    let account_id = account_id
        .parse::<i32>()
        .map_err(|_| wallet_config_validation_error("account_id must be a valid integer"))?;
    let request_payload = parse_switch_environment_request(payload)?;
    let request_body = serde_json::to_vec(&request_payload).map_err(|error| {
        AppError::internal(format!(
            "Failed to encode Hyperliquid switch-environment request: {error}"
        ))
    })?;
    let target_url = state.config.legacy_http_target(&format!(
        "/api/hyperliquid/accounts/{account_id}/switch-environment"
    ));
    let upstream_request = build_upstream_request(
        &state.client,
        Method::POST,
        &headers,
        target_url,
        request_body.into(),
    )?;
    let upstream_response = upstream_request.send().await.map_err(|error| {
        AppError::bad_gateway(format!(
            "legacy Hyperliquid switch-environment request failed: {error}"
        ))
    })?;

    build_downstream_streaming_response(upstream_response)
}

pub async fn place_hyperliquid_manual_order(
    State(state): State<AppState>,
    Path(account_id): Path<String>,
    headers: HeaderMap,
    Json(payload): Json<Value>,
) -> Result<Response, AppError> {
    let account_id = account_id
        .parse::<i32>()
        .map_err(|_| wallet_config_validation_error("account_id must be a valid integer"))?;
    let request_payload = parse_manual_order_request(payload)?;
    let request_body = serde_json::to_vec(&request_payload).map_err(|error| {
        AppError::internal(format!(
            "Failed to encode Hyperliquid manual-order request: {error}"
        ))
    })?;
    let target_url = state.config.legacy_http_target(&format!(
        "/api/hyperliquid/accounts/{account_id}/orders/manual"
    ));
    let upstream_request = build_upstream_request(
        &state.client,
        Method::POST,
        &headers,
        target_url,
        request_body.into(),
    )?;
    let upstream_response = upstream_request.send().await.map_err(|error| {
        AppError::bad_gateway(format!(
            "legacy Hyperliquid manual-order request failed: {error}"
        ))
    })?;

    build_downstream_streaming_response(upstream_response)
}

pub async fn get_pending_orders(
    State(state): State<AppState>,
    headers: HeaderMap,
    Query(query): Query<PendingOrdersQuery>,
) -> Result<Response, AppError> {
    let normalized_user_id = parse_pending_orders_user_id(query.user_id.as_deref())?;
    let target_path = match normalized_user_id {
        Some(user_id) => format!("/api/orders/pending?user_id={user_id}"),
        None => "/api/orders/pending".to_owned(),
    };
    let target_url = state.config.legacy_http_target(&target_path);
    let upstream_request = build_upstream_request(
        &state.client,
        Method::GET,
        &headers,
        target_url,
        Bytes::new(),
    )?;
    let upstream_response = upstream_request.send().await.map_err(|error| {
        AppError::bad_gateway(format!("legacy pending orders request failed: {error}"))
    })?;

    build_downstream_streaming_response(upstream_response)
}

pub async fn create_user_order(
    State(state): State<AppState>,
    headers: HeaderMap,
    Json(payload): Json<Value>,
) -> Result<Response, AppError> {
    let request_payload = parse_order_create_request(payload)?;
    let request_body = serde_json::to_vec(&request_payload).map_err(|error| {
        AppError::internal(format!("Failed to encode order create request: {error}"))
    })?;
    let target_url = state.config.legacy_http_target("/api/orders/create");
    let upstream_request = build_upstream_request(
        &state.client,
        Method::POST,
        &headers,
        target_url,
        request_body.into(),
    )?;
    let upstream_response = upstream_request.send().await.map_err(|error| {
        AppError::bad_gateway(format!("legacy order create request failed: {error}"))
    })?;

    build_downstream_streaming_response(upstream_response)
}

pub async fn get_user_orders(
    State(state): State<AppState>,
    Path(user_id): Path<String>,
    headers: HeaderMap,
    Query(query): Query<UserOrdersQuery>,
) -> Result<Response, AppError> {
    let user_id = parse_user_orders_path_user_id(&user_id)?;
    let target_path = if let Some(status) = parse_user_orders_status(query.status.as_deref()) {
        let query = form_urlencoded::Serializer::new(String::new())
            .append_pair("status", &status)
            .finish();
        format!("/api/orders/user/{user_id}?{query}")
    } else {
        format!("/api/orders/user/{user_id}")
    };
    let target_url = state.config.legacy_http_target(&target_path);
    let upstream_request = build_upstream_request(
        &state.client,
        Method::GET,
        &headers,
        target_url,
        Bytes::new(),
    )?;
    let upstream_response = upstream_request.send().await.map_err(|error| {
        AppError::bad_gateway(format!("legacy user orders request failed: {error}"))
    })?;

    build_downstream_streaming_response(upstream_response)
}

pub async fn get_order_details(
    State(state): State<AppState>,
    Path(order_id): Path<String>,
    headers: HeaderMap,
) -> Result<Response, AppError> {
    let order_id = parse_execute_order_path_order_id(&order_id)?;
    let target_url = state
        .config
        .legacy_http_target(&format!("/api/orders/order/{order_id}"));
    let upstream_request = build_upstream_request(
        &state.client,
        Method::GET,
        &headers,
        target_url,
        Bytes::new(),
    )?;
    let upstream_response = upstream_request.send().await.map_err(|error| {
        AppError::bad_gateway(format!("legacy order details request failed: {error}"))
    })?;

    build_downstream_streaming_response(upstream_response)
}

pub async fn get_orders_health(
    State(state): State<AppState>,
    headers: HeaderMap,
) -> Result<Response, AppError> {
    let target_url = state.config.legacy_http_target("/api/orders/health");
    let upstream_request = build_upstream_request(
        &state.client,
        Method::GET,
        &headers,
        target_url,
        Bytes::new(),
    )?;
    let upstream_response = upstream_request.send().await.map_err(|error| {
        AppError::bad_gateway(format!("legacy orders health request failed: {error}"))
    })?;

    build_downstream_streaming_response(upstream_response)
}

pub async fn execute_order_manually(
    State(state): State<AppState>,
    Path(order_id): Path<String>,
    headers: HeaderMap,
) -> Result<Response, AppError> {
    let order_id = parse_execute_order_path_order_id(&order_id)?;
    let target_url = state
        .config
        .legacy_http_target(&format!("/api/orders/execute/{order_id}"));
    let upstream_request = build_upstream_request(
        &state.client,
        Method::POST,
        &headers,
        target_url,
        Bytes::new(),
    )?;
    let upstream_response = upstream_request.send().await.map_err(|error| {
        AppError::bad_gateway(format!("legacy order execute request failed: {error}"))
    })?;

    build_downstream_streaming_response(upstream_response)
}

pub async fn cancel_user_order(
    State(state): State<AppState>,
    Path(order_id): Path<String>,
    headers: HeaderMap,
    Query(query): Query<CancelOrderQuery>,
) -> Result<Response, AppError> {
    let order_id = parse_execute_order_path_order_id(&order_id)?;
    let reason = parse_cancel_order_reason(query.reason.as_deref());
    let encoded_query = form_urlencoded::Serializer::new(String::new())
        .append_pair("reason", &reason)
        .finish();
    let target_url = state
        .config
        .legacy_http_target(&format!("/api/orders/cancel/{order_id}?{encoded_query}"));
    let upstream_request = build_upstream_request(
        &state.client,
        Method::POST,
        &headers,
        target_url,
        Bytes::new(),
    )?;
    let upstream_response = upstream_request.send().await.map_err(|error| {
        AppError::bad_gateway(format!("legacy order cancel request failed: {error}"))
    })?;

    build_downstream_streaming_response(upstream_response)
}

pub async fn process_all_orders(
    State(state): State<AppState>,
    headers: HeaderMap,
) -> Result<Response, AppError> {
    let target_url = state.config.legacy_http_target("/api/orders/process-all");
    let upstream_request = build_upstream_request(
        &state.client,
        Method::POST,
        &headers,
        target_url,
        Bytes::new(),
    )?;
    let upstream_response = upstream_request.send().await.map_err(|error| {
        AppError::bad_gateway(format!("legacy process-all orders request failed: {error}"))
    })?;

    build_downstream_streaming_response(upstream_response)
}

pub async fn disable_hyperliquid_account_trading(
    State(state): State<AppState>,
    Path(account_id): Path<String>,
    headers: HeaderMap,
) -> Result<Response, AppError> {
    let account_id = account_id
        .parse::<i32>()
        .map_err(|_| wallet_config_validation_error("account_id must be a valid integer"))?;
    let target_url = state
        .config
        .legacy_http_target(&format!("/api/hyperliquid/accounts/{account_id}/disable"));
    let upstream_request = build_upstream_request(
        &state.client,
        Method::POST,
        &headers,
        target_url,
        Bytes::new(),
    )?;
    let upstream_response = upstream_request.send().await.map_err(|error| {
        AppError::bad_gateway(format!(
            "legacy Hyperliquid disable request failed: {error}"
        ))
    })?;

    build_downstream_streaming_response(upstream_response)
}

pub async fn enable_hyperliquid_account_trading(
    State(state): State<AppState>,
    Path(account_id): Path<String>,
    headers: HeaderMap,
) -> Result<Response, AppError> {
    let account_id = account_id
        .parse::<i32>()
        .map_err(|_| wallet_config_validation_error("account_id must be a valid integer"))?;
    let target_url = state
        .config
        .legacy_http_target(&format!("/api/hyperliquid/accounts/{account_id}/enable"));
    let upstream_request = build_upstream_request(
        &state.client,
        Method::POST,
        &headers,
        target_url,
        Bytes::new(),
    )?;
    let upstream_response = upstream_request.send().await.map_err(|error| {
        AppError::bad_gateway(format!("legacy Hyperliquid enable request failed: {error}"))
    })?;

    build_downstream_streaming_response(upstream_response)
}

pub async fn get_hyperliquid_wallets_all(
    State(state): State<AppState>,
) -> Result<Json<Vec<Value>>, AppError> {
    let rows = sqlx::query(
        r#"
        SELECT
            w.id AS wallet_id,
            w.account_id,
            a.name AS account_name,
            a.model,
            w.wallet_address,
            w.master_wallet_address,
            w.environment,
            w.is_active,
            w.max_leverage,
            w.default_leverage,
            w.key_type
        FROM hyperliquid_wallets w
        JOIN accounts a ON a.id = w.account_id
        WHERE a.is_active = 'true'
          AND COALESCE(a.is_deleted, false) = false
        ORDER BY a.name ASC, w.environment ASC
        "#,
    )
    .fetch_all(&state.db)
    .await
    .map_err(|error| AppError::internal(format!("Failed to list Hyperliquid wallets: {error}")))?;

    let wallets = rows
        .into_iter()
        .map(|row| {
            let key_type = row
                .try_get::<Option<String>, _>("key_type")
                .map_err(read_exchange_error)?
                .unwrap_or_else(|| "private_key".to_owned());
            let wallet_address = if key_type == "agent_key" {
                row.try_get::<Option<String>, _>("master_wallet_address")
                    .map_err(read_exchange_error)?
                    .or_else(|| row.try_get::<Option<String>, _>("wallet_address").ok().flatten())
            } else {
                row.try_get::<Option<String>, _>("wallet_address")
                    .map_err(read_exchange_error)?
            };
            Ok(serde_json::json!({
                "wallet_id": row.try_get::<i32,_>("wallet_id").map_err(read_exchange_error)?,
                "account_id": row.try_get::<i32,_>("account_id").map_err(read_exchange_error)?,
                "account_name": row.try_get::<String,_>("account_name").map_err(read_exchange_error)?,
                "model": row.try_get::<Option<String>,_>("model").map_err(read_exchange_error)?,
                "wallet_address": wallet_address,
                "environment": row.try_get::<String,_>("environment").map_err(read_exchange_error)?,
                "is_active": row.try_get::<String,_>("is_active").map_err(read_exchange_error)? == "true",
                "max_leverage": row.try_get::<i32,_>("max_leverage").map_err(read_exchange_error)?,
                "default_leverage": row.try_get::<i32,_>("default_leverage").map_err(read_exchange_error)?,
            }))
        })
        .collect::<Result<Vec<_>, AppError>>()?;

    Ok(Json(wallets))
}

pub async fn get_hyperliquid_agent_wallet_status(
    State(state): State<AppState>,
    Path(account_id): Path<i32>,
    Query(query): Query<ExchangeEnvironmentQuery>,
) -> Result<Json<Value>, AppError> {
    let environment = resolve_live_environment(&state, query.environment.as_deref()).await?;
    ensure_account_exists(&state, account_id).await?;
    let wallet = sqlx::query(
        r#"
        SELECT wallet_address, master_wallet_address, key_type, agent_valid_until
        FROM hyperliquid_wallets
        WHERE account_id = $1
          AND environment = $2
        LIMIT 1
        "#,
    )
    .bind(account_id)
    .bind(&environment)
    .fetch_optional(&state.db)
    .await
    .map_err(|error| AppError::internal(format!("Failed to load agent wallet status: {error}")))?
    .ok_or_else(|| AppError::not_found(format!("No {environment} wallet found")))?;

    let key_type = wallet
        .try_get::<Option<String>, _>("key_type")
        .map_err(read_exchange_error)?
        .unwrap_or_else(|| "private_key".to_owned());
    if key_type != "agent_key" {
        return Ok(Json(serde_json::json!({
            "success": true,
            "keyType": "private_key",
            "message": "Wallet is using legacy private key mode"
        })));
    }

    let valid_until = wallet
        .try_get::<Option<NaiveDateTime>, _>("agent_valid_until")
        .map_err(read_exchange_error)?;
    let now = Utc::now().naive_utc();
    let is_expired = valid_until.map(|value| value < now).unwrap_or(true);
    let days_remaining = valid_until
        .map(|value| (value - now).num_days().max(0))
        .unwrap_or(0);

    Ok(Json(serde_json::json!({
        "success": true,
        "keyType": "agent_key",
        "agentAddress": wallet.try_get::<Option<String>,_>("wallet_address").map_err(read_exchange_error)?,
        "masterWalletAddress": wallet.try_get::<Option<String>,_>("master_wallet_address").map_err(read_exchange_error)?,
        "agentName": Value::Null,
        "validUntil": valid_until.map(|value| value.and_utc().to_rfc3339()),
        "isExpired": is_expired,
        "daysRemaining": days_remaining,
        "found": true
    })))
}

pub async fn check_hyperliquid_wallet_upgrade_needed(
    State(state): State<AppState>,
) -> Result<Json<Value>, AppError> {
    let rows = sqlx::query(
        r#"
        SELECT
            a.id AS account_id,
            a.name AS account_name,
            w.environment,
            w.wallet_address,
            w.key_type
        FROM hyperliquid_wallets w
        JOIN accounts a ON a.id = w.account_id
        WHERE w.is_active = 'true'
          AND COALESCE(a.is_deleted, false) = false
        ORDER BY a.id, w.environment
        "#,
    )
    .fetch_all(&state.db)
    .await
    .map_err(|error| AppError::internal(format!("Failed to check wallet upgrades: {error}")))?;

    let needs_upgrade = rows
        .into_iter()
        .filter_map(|row| {
            let key_type = row.try_get::<Option<String>, _>("key_type").ok().flatten();
            if key_type.as_deref().unwrap_or("private_key") == "private_key" {
                Some(serde_json::json!({
                    "accountId": row.try_get::<i32,_>("account_id").ok(),
                    "accountName": row.try_get::<String,_>("account_name").ok(),
                    "environment": row.try_get::<String,_>("environment").ok(),
                    "walletAddress": row.try_get::<Option<String>,_>("wallet_address").ok().flatten(),
                }))
            } else {
                None
            }
        })
        .collect::<Vec<_>>();

    Ok(Json(serde_json::json!({
        "success": true,
        "needsUpgrade": needs_upgrade,
        "count": needs_upgrade.len()
    })))
}

pub async fn get_hyperliquid_account_wallet(
    State(state): State<AppState>,
    Path(account_id): Path<i32>,
) -> Result<Json<Value>, AppError> {
    let account = sqlx::query(
        r#"
        SELECT id, name
        FROM accounts
        WHERE id = $1
          AND COALESCE(is_deleted, false) = false
        LIMIT 1
        "#,
    )
    .bind(account_id)
    .fetch_optional(&state.db)
    .await
    .map_err(|error| AppError::internal(format!("Failed to load account wallet info: {error}")))?
    .ok_or_else(|| AppError::not_found(format!("Account {account_id} not found")))?;

    let wallets = sqlx::query(
        r#"
        SELECT
            id,
            wallet_address,
            master_wallet_address,
            max_leverage,
            default_leverage,
            is_active,
            created_at,
            updated_at,
            environment,
            key_type,
            agent_valid_until
        FROM hyperliquid_wallets
        WHERE account_id = $1
        ORDER BY environment ASC
        "#,
    )
    .bind(account_id)
    .fetch_all(&state.db)
    .await
    .map_err(|error| AppError::internal(format!("Failed to load account wallets: {error}")))?;

    let mut testnet_wallet = Value::Null;
    let mut mainnet_wallet = Value::Null;
    for row in wallets {
        let environment = row
            .try_get::<String, _>("environment")
            .map_err(read_exchange_error)?;
        let key_type = row
            .try_get::<Option<String>, _>("key_type")
            .map_err(read_exchange_error)?
            .unwrap_or_else(|| "private_key".to_owned());
        let balance = latest_hyperliquid_snapshot(&state, account_id, &environment).await?;
        let balance_json = if let Some(snapshot) = balance {
            let total = snapshot
                .try_get::<f64, _>("total_equity")
                .ok()
                .unwrap_or(0.0);
            let used = snapshot
                .try_get::<f64, _>("used_margin")
                .ok()
                .unwrap_or(0.0);
            serde_json::json!({
                "totalEquity": total,
                "availableBalance": snapshot.try_get::<f64,_>("available_balance").ok().unwrap_or(0.0),
                "marginUsagePercent": if total > 0.0 { used / total * 100.0 } else { 0.0 }
            })
        } else {
            Value::Null
        };
        let wallet_json = serde_json::json!({
            "id": row.try_get::<i32,_>("id").map_err(read_exchange_error)?,
            "walletAddress": if key_type == "agent_key" {
                row.try_get::<Option<String>,_>("master_wallet_address").map_err(read_exchange_error)?
                    .or_else(|| row.try_get::<Option<String>,_>("wallet_address").ok().flatten())
            } else {
                row.try_get::<Option<String>,_>("wallet_address").map_err(read_exchange_error)?
            },
            "maxLeverage": row.try_get::<i32,_>("max_leverage").map_err(read_exchange_error)?,
            "defaultLeverage": row.try_get::<i32,_>("default_leverage").map_err(read_exchange_error)?,
            "isActive": row.try_get::<String,_>("is_active").map_err(read_exchange_error)? == "true",
            "createdAt": row.try_get::<Option<NaiveDateTime>,_>("created_at").map_err(read_exchange_error)?.map(|v| v.and_utc().to_rfc3339()),
            "updatedAt": row.try_get::<Option<NaiveDateTime>,_>("updated_at").map_err(read_exchange_error)?.map(|v| v.and_utc().to_rfc3339()),
            "environment": environment,
            "keyType": key_type,
            "masterWalletAddress": row.try_get::<Option<String>,_>("master_wallet_address").map_err(read_exchange_error)?,
            "agentValidUntil": row.try_get::<Option<NaiveDateTime>,_>("agent_valid_until").map_err(read_exchange_error)?.map(|v| v.and_utc().to_rfc3339()),
            "balance": balance_json
        });
        match wallet_json["environment"].as_str() {
            Some("testnet") => testnet_wallet = wallet_json,
            Some("mainnet") => mainnet_wallet = wallet_json,
            _ => {}
        }
    }

    let trading_mode = get_global_trading_mode(&state).await?;
    Ok(Json(serde_json::json!({
        "success": true,
        "configured": !testnet_wallet.is_null() || !mainnet_wallet.is_null(),
        "accountId": account_id,
        "accountName": account.try_get::<String,_>("name").map_err(read_exchange_error)?,
        "testnetWallet": testnet_wallet,
        "mainnetWallet": mainnet_wallet,
        "globalTradingMode": trading_mode
    })))
}

pub async fn configure_hyperliquid_account_wallet(
    State(state): State<AppState>,
    Path(account_id): Path<String>,
    headers: HeaderMap,
    Json(payload): Json<Value>,
) -> Result<Response, AppError> {
    let account_id = account_id
        .parse::<i32>()
        .map_err(|_| wallet_config_validation_error("account_id must be a valid integer"))?;
    let request_payload = parse_hyperliquid_wallet_config_request(payload)?;
    let request_body = serde_json::to_vec(&request_payload).map_err(|error| {
        AppError::internal(format!(
            "Failed to encode Hyperliquid wallet config request: {error}"
        ))
    })?;
    let target_url = state
        .config
        .legacy_http_target(&format!("/api/hyperliquid/accounts/{account_id}/wallet"));
    let upstream_request = build_upstream_request(
        &state.client,
        Method::POST,
        &headers,
        target_url,
        request_body.into(),
    )?;
    let upstream_response = upstream_request.send().await.map_err(|error| {
        AppError::bad_gateway(format!(
            "legacy Hyperliquid wallet config request failed: {error}"
        ))
    })?;

    build_downstream_streaming_response(upstream_response)
}

pub async fn delete_hyperliquid_account_wallet(
    State(state): State<AppState>,
    Path(account_id): Path<String>,
    Query(query): Query<HyperliquidWalletDeleteQuery>,
    headers: HeaderMap,
) -> Result<Response, AppError> {
    let account_id = account_id
        .parse::<i32>()
        .map_err(|_| wallet_config_validation_error("account_id must be a valid integer"))?;
    let environment = parse_wallet_delete_environment(query.environment.as_deref())?;

    let mut target_url = state
        .config
        .legacy_http_target(&format!("/api/hyperliquid/accounts/{account_id}/wallet"));
    target_url
        .query_pairs_mut()
        .append_pair("environment", &environment);

    let upstream_request = build_upstream_request(
        &state.client,
        Method::DELETE,
        &headers,
        target_url,
        Bytes::new(),
    )?;
    let upstream_response = upstream_request.send().await.map_err(|error| {
        AppError::bad_gateway(format!(
            "legacy Hyperliquid wallet delete request failed: {error}"
        ))
    })?;

    build_downstream_streaming_response(upstream_response)
}

pub async fn get_hyperliquid_config(
    State(state): State<AppState>,
    Path(account_id): Path<i32>,
) -> Result<Json<Value>, AppError> {
    let account = sqlx::query(
        r#"
        SELECT
            id, name, hyperliquid_enabled,
            hyperliquid_testnet_private_key, hyperliquid_mainnet_private_key,
            max_leverage, default_leverage
        FROM accounts
        WHERE id = $1
          AND COALESCE(is_deleted, false) = false
        LIMIT 1
        "#,
    )
    .bind(account_id)
    .fetch_optional(&state.db)
    .await
    .map_err(|error| AppError::internal(format!("Failed to load Hyperliquid config: {error}")))?
    .ok_or_else(|| AppError::not_found("Account not found"))?;

    let trading_mode = get_global_trading_mode(&state).await?;
    let wallets = sqlx::query(
        r#"
        SELECT environment, max_leverage, default_leverage
        FROM hyperliquid_wallets
        WHERE account_id = $1
          AND is_active = 'true'
        "#,
    )
    .bind(account_id)
    .fetch_all(&state.db)
    .await
    .map_err(|error| AppError::internal(format!("Failed to load Hyperliquid wallets: {error}")))?;

    let mut testnet = None;
    let mut mainnet = None;
    for row in wallets {
        let pair = (
            row.try_get::<i32, _>("max_leverage")
                .map_err(read_exchange_error)?,
            row.try_get::<i32, _>("default_leverage")
                .map_err(read_exchange_error)?,
        );
        match row
            .try_get::<String, _>("environment")
            .map_err(read_exchange_error)?
            .as_str()
        {
            "testnet" => testnet = Some(pair),
            "mainnet" => mainnet = Some(pair),
            _ => {}
        }
    }

    let has_testnet = testnet.is_some()
        || account
            .try_get::<Option<String>, _>("hyperliquid_testnet_private_key")
            .map_err(read_exchange_error)?
            .is_some();
    let has_mainnet = mainnet.is_some()
        || account
            .try_get::<Option<String>, _>("hyperliquid_mainnet_private_key")
            .map_err(read_exchange_error)?
            .is_some();
    let enabled = has_testnet
        || has_mainnet
        || account
            .try_get::<String, _>("hyperliquid_enabled")
            .map_err(read_exchange_error)?
            == "true";
    let active_leverage = match trading_mode.as_str() {
        "mainnet" => mainnet,
        _ => testnet,
    };

    Ok(Json(serde_json::json!({
        "account_id": account_id,
        "account_name": account.try_get::<String,_>("name").map_err(read_exchange_error)?,
        "hyperliquid_enabled": enabled,
        "enabled": enabled,
        "environment": trading_mode,
        "max_leverage": active_leverage
            .map(|v| v.0)
            .or_else(|| account.try_get::<Option<i32>,_>("max_leverage").ok().flatten())
            .unwrap_or(3),
        "default_leverage": active_leverage
            .map(|v| v.1)
            .or_else(|| account.try_get::<Option<i32>,_>("default_leverage").ok().flatten())
            .unwrap_or(1),
        "testnet_configured": has_testnet,
        "mainnet_configured": has_mainnet,
        "hasTestnetKey": has_testnet,
        "hasMainnetKey": has_mainnet
    })))
}

pub async fn get_hyperliquid_balance(
    State(state): State<AppState>,
    Path(account_id): Path<i32>,
    Query(query): Query<ExchangeEnvironmentQuery>,
) -> Result<Json<Value>, AppError> {
    let environment = resolve_live_environment(&state, query.environment.as_deref()).await?;
    let _force_refresh = query.force_refresh.unwrap_or(false);
    let wallet = ensure_hyperliquid_wallet(&state, account_id, &environment).await?;
    let account = sqlx::query(
        "SELECT current_cash::float8 AS current_cash, frozen_cash::float8 AS frozen_cash FROM accounts WHERE id = $1",
    )
    .bind(account_id)
    .fetch_one(&state.db)
    .await
    .map_err(|error| AppError::internal(format!("Failed to load account fallback balance: {error}")))?;

    let snapshot = sqlx::query(
        r#"
        SELECT
            wallet_address,
            total_equity::float8 AS total_equity,
            available_balance::float8 AS available_balance,
            used_margin::float8 AS used_margin,
            maintenance_margin::float8 AS maintenance_margin,
            snapshot_time
        FROM hyperliquid_account_snapshots
        WHERE account_id = $1
          AND environment = $2
        ORDER BY snapshot_time DESC, id DESC
        LIMIT 1
        "#,
    )
    .bind(account_id)
    .bind(&environment)
    .fetch_optional(&state.db)
    .await
    .map_err(|error| {
        AppError::internal(format!(
            "Failed to load Hyperliquid balance snapshot: {error}"
        ))
    })?;

    let (
        total_equity,
        available_balance,
        used_margin,
        maintenance_margin,
        timestamp,
        wallet_address,
    ) = if let Some(snapshot) = snapshot {
        (
            snapshot
                .try_get::<f64, _>("total_equity")
                .map_err(read_exchange_error)?,
            snapshot
                .try_get::<f64, _>("available_balance")
                .map_err(read_exchange_error)?,
            snapshot
                .try_get::<f64, _>("used_margin")
                .map_err(read_exchange_error)?,
            snapshot
                .try_get::<f64, _>("maintenance_margin")
                .map_err(read_exchange_error)?,
            snapshot
                .try_get::<NaiveDateTime, _>("snapshot_time")
                .map_err(read_exchange_error)?,
            snapshot
                .try_get::<Option<String>, _>("wallet_address")
                .map_err(read_exchange_error)?,
        )
    } else {
        (
            account
                .try_get::<f64, _>("current_cash")
                .map_err(read_exchange_error)?,
            account
                .try_get::<f64, _>("current_cash")
                .map_err(read_exchange_error)?,
            account
                .try_get::<f64, _>("frozen_cash")
                .map_err(read_exchange_error)?,
            0.0,
            Utc::now().naive_utc(),
            wallet
                .try_get::<Option<String>, _>("wallet_address")
                .map_err(read_exchange_error)?,
        )
    };

    Ok(Json(serde_json::json!({
        "environment": environment,
        "total_equity": total_equity,
        "available_balance": available_balance,
        "used_margin": used_margin,
        "maintenance_margin": maintenance_margin,
        "margin_usage_percent": if total_equity > 0.0 { used_margin / total_equity * 100.0 } else { 0.0 },
        "withdrawal_available": available_balance,
        "wallet_address": wallet_address,
        "source": "cache",
        "timestamp": timestamp.and_utc().timestamp_millis(),
        "cached_at": timestamp.and_utc().to_rfc3339()
    })))
}

pub async fn get_hyperliquid_positions(
    State(state): State<AppState>,
    Path(account_id): Path<i32>,
    Query(query): Query<ExchangeEnvironmentQuery>,
) -> Result<Json<Value>, AppError> {
    let environment = resolve_live_environment(&state, query.environment.as_deref()).await?;
    let _force_refresh = query.force_refresh.unwrap_or(false);
    ensure_hyperliquid_wallet(&state, account_id, &environment).await?;

    let snapshot_time = sqlx::query_scalar::<_, Option<NaiveDateTime>>(
        r#"
        SELECT MAX(snapshot_time)
        FROM hyperliquid_positions
        WHERE account_id = $1
          AND environment = $2
        "#,
    )
    .bind(account_id)
    .bind(&environment)
    .fetch_one(&state.db)
    .await
    .map_err(|error| {
        AppError::internal(format!(
            "Failed to load Hyperliquid position snapshot time: {error}"
        ))
    })?;

    let cached_at = snapshot_time.unwrap_or_else(|| Utc::now().naive_utc());
    let positions = if let Some(snapshot_time) = snapshot_time {
        let rows = sqlx::query(
            r#"
            SELECT
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
        .bind(account_id)
        .bind(&environment)
        .bind(snapshot_time)
        .fetch_all(&state.db)
        .await
        .map_err(|error| {
            AppError::internal(format!("Failed to load Hyperliquid positions: {error}"))
        })?;

        rows.into_iter()
            .map(|row| {
                let szi = row.try_get::<f64,_>("position_size").map_err(read_exchange_error)?;
                let entry_px = row.try_get::<f64,_>("entry_price").map_err(read_exchange_error)?;
                let margin_used = row.try_get::<f64,_>("margin_used").map_err(read_exchange_error)?;
                let unrealized_pnl = row.try_get::<f64,_>("unrealized_pnl").map_err(read_exchange_error)?;
                Ok(serde_json::json!({
                    "coin": row.try_get::<String,_>("symbol").map_err(read_exchange_error)?,
                    "szi": szi,
                    "entry_px": entry_px,
                    "position_value": row.try_get::<f64,_>("position_value").map_err(read_exchange_error)?,
                    "unrealized_pnl": unrealized_pnl,
                    "margin_used": margin_used,
                    "liquidation_px": row.try_get::<Option<f64>,_>("liquidation_price").map_err(read_exchange_error)?.unwrap_or(0.0),
                    "leverage": row.try_get::<i32,_>("leverage").map_err(read_exchange_error)?,
                    "side": if szi >= 0.0 { "Long" } else { "Short" },
                    "return_on_equity": if margin_used > 0.0 { unrealized_pnl / margin_used } else { 0.0 },
                    "max_leverage": Value::Null,
                    "leverage_type": "cross",
                    "notional": szi.abs() * entry_px,
                    "percentage": 0.0,
                    "margin_mode": "cross"
                }))
            })
            .collect::<Result<Vec<_>, AppError>>()?
    } else {
        Vec::new()
    };

    Ok(Json(serde_json::json!({
        "account_id": account_id,
        "environment": environment,
        "positions": positions,
        "count": positions.len(),
        "source": "cache",
        "cached_at": cached_at.and_utc().to_rfc3339()
    })))
}

pub async fn get_hyperliquid_account_state(
    State(state): State<AppState>,
    Path(account_id): Path<i32>,
    Query(query): Query<ExchangeEnvironmentQuery>,
) -> Result<Json<Value>, AppError> {
    let environment = resolve_live_environment(&state, query.environment.as_deref()).await?;
    let balance = get_hyperliquid_balance(
        State(state.clone()),
        Path(account_id),
        Query(ExchangeEnvironmentQuery {
            environment: Some(environment.clone()),
            force_refresh: query.force_refresh,
        }),
    )
    .await?
    .0;
    let positions = get_hyperliquid_positions(
        State(state),
        Path(account_id),
        Query(ExchangeEnvironmentQuery {
            environment: Some(environment.clone()),
            force_refresh: query.force_refresh,
        }),
    )
    .await?
    .0;

    let account_value = balance
        .get("total_equity")
        .and_then(Value::as_f64)
        .unwrap_or(0.0);
    let margin_used = balance
        .get("used_margin")
        .and_then(Value::as_f64)
        .unwrap_or(0.0);
    let available = balance
        .get("available_balance")
        .and_then(Value::as_f64)
        .unwrap_or(0.0);
    let maintenance = balance
        .get("maintenance_margin")
        .and_then(Value::as_f64)
        .unwrap_or(0.0);
    let positions_array = positions
        .get("positions")
        .cloned()
        .unwrap_or_else(|| Value::Array(Vec::new()));
    let total_ntl = positions_array
        .as_array()
        .map(|items| {
            items
                .iter()
                .filter_map(|item| item.get("position_value").and_then(Value::as_f64))
                .sum::<f64>()
        })
        .unwrap_or(0.0);

    Ok(Json(serde_json::json!({
        "marginSummary": {
            "accountValue": account_value,
            "totalMarginUsed": margin_used,
            "totalNtlPos": total_ntl,
            "totalRawUsd": available
        },
        "crossMaintenanceMarginUsed": maintenance,
        "crossMarginSummary": {
            "accountValue": account_value,
            "totalMarginUsed": margin_used,
            "totalNtlPos": total_ntl,
            "totalRawUsd": available
        },
        "positions": positions_array
    })))
}

pub async fn test_hyperliquid_connection(
    State(state): State<AppState>,
    Path(account_id): Path<i32>,
) -> Result<Json<Value>, AppError> {
    let environment = get_global_trading_mode(&state).await?;
    let account = sqlx::query("SELECT name FROM accounts WHERE id = $1 LIMIT 1")
        .bind(account_id)
        .fetch_optional(&state.db)
        .await
        .map_err(|error| AppError::internal(format!("Failed to load account: {error}")))?
        .ok_or_else(|| AppError::not_found("Account not found"))?;
    let wallet = ensure_hyperliquid_wallet(&state, account_id, &environment).await?;
    let balance = latest_hyperliquid_snapshot(&state, account_id, &environment).await?;

    Ok(Json(serde_json::json!({
        "success": true,
        "environment": environment,
        "address": wallet.try_get::<String,_>("wallet_address").map_err(read_exchange_error)?,
        "balance": balance.as_ref().and_then(|row| row.try_get::<f64,_>("total_equity").ok()),
        "accountId": account_id,
        "accountName": account.try_get::<String,_>("name").map_err(read_exchange_error)?
    })))
}

pub async fn test_hyperliquid_wallet_connection(
    State(state): State<AppState>,
    Path(account_id): Path<i32>,
    Json(body): Json<WalletTestRequest>,
) -> Result<Json<Value>, AppError> {
    let environment = resolve_live_environment(&state, body.environment.as_deref()).await?;
    let account = sqlx::query("SELECT name FROM accounts WHERE id = $1 LIMIT 1")
        .bind(account_id)
        .fetch_optional(&state.db)
        .await
        .map_err(|error| AppError::internal(format!("Failed to load account: {error}")))?
        .ok_or_else(|| AppError::not_found(format!("Account {account_id} not found")))?;
    let wallet = ensure_hyperliquid_wallet(&state, account_id, &environment).await?;
    let balance = latest_hyperliquid_snapshot(&state, account_id, &environment).await?;
    let account_state = if let Some(snapshot) = balance {
        let total = snapshot
            .try_get::<f64, _>("total_equity")
            .map_err(read_exchange_error)?;
        let used = snapshot
            .try_get::<f64, _>("used_margin")
            .map_err(read_exchange_error)?;
        serde_json::json!({
            "totalEquity": total,
            "availableBalance": snapshot.try_get::<f64,_>("available_balance").map_err(read_exchange_error)?,
            "marginUsage": if total > 0.0 { used / total * 100.0 } else { 0.0 }
        })
    } else {
        serde_json::json!({
            "totalEquity": 0.0,
            "availableBalance": 0.0,
            "marginUsage": 0.0
        })
    };

    Ok(Json(serde_json::json!({
        "success": true,
        "accountId": account_id,
        "accountName": account.try_get::<String,_>("name").map_err(read_exchange_error)?,
        "environment": environment,
        "walletAddress": wallet.try_get::<String,_>("wallet_address").map_err(read_exchange_error)?,
        "connection": "successful",
        "accountState": account_state
    })))
}

pub async fn get_hyperliquid_account_snapshots(
    State(state): State<AppState>,
    Path(account_id): Path<i32>,
    Query(query): Query<SnapshotQuery>,
) -> Result<Json<Value>, AppError> {
    let limit = query.limit.clamp(1, 1000);
    let account = sqlx::query(
        r#"
        SELECT id, name, hyperliquid_environment
        FROM accounts
        WHERE id = $1
          AND COALESCE(is_deleted, false) = false
        LIMIT 1
        "#,
    )
    .bind(account_id)
    .fetch_optional(&state.db)
    .await
    .map_err(|error| {
        AppError::internal(format!(
            "Failed to load account snapshots metadata: {error}"
        ))
    })?
    .ok_or_else(|| AppError::not_found("Account not found"))?;
    let environment = account
        .try_get::<Option<String>, _>("hyperliquid_environment")
        .map_err(read_exchange_error)?
        .unwrap_or_else(|| "testnet".to_owned());
    let rows = sqlx::query(
        r#"
        SELECT environment, snapshot_time, total_equity::float8 AS total_equity,
               available_balance::float8 AS available_balance,
               used_margin::float8 AS used_margin,
               maintenance_margin::float8 AS maintenance_margin,
               trigger_event
        FROM hyperliquid_account_snapshots
        WHERE account_id = $1
        ORDER BY snapshot_time DESC
        LIMIT $2
        "#,
    )
    .bind(account_id)
    .bind(limit)
    .fetch_all(&state.db)
    .await
    .map_err(|error| AppError::internal(format!("Failed to load account snapshots: {error}")))?;

    let snapshots = rows
        .into_iter()
        .rev()
        .map(|row| {
            Ok(serde_json::json!({
                "account_id": account_id,
                "environment": row.try_get::<String,_>("environment").map_err(read_exchange_error)?,
                "snapshot_time": row.try_get::<NaiveDateTime,_>("snapshot_time").map_err(read_exchange_error)?.and_utc().to_rfc3339(),
                "total_equity": row.try_get::<f64,_>("total_equity").map_err(read_exchange_error)?,
                "available_balance": row.try_get::<f64,_>("available_balance").map_err(read_exchange_error)?,
                "used_margin": row.try_get::<f64,_>("used_margin").map_err(read_exchange_error)?,
                "maintenance_margin": row.try_get::<f64,_>("maintenance_margin").map_err(read_exchange_error)?,
                "trigger_event": row.try_get::<Option<String>,_>("trigger_event").map_err(read_exchange_error)?,
            }))
        })
        .collect::<Result<Vec<_>, AppError>>()?;

    Ok(Json(serde_json::json!({
        "account_id": account_id,
        "account_name": account.try_get::<String,_>("name").map_err(read_exchange_error)?,
        "environment": environment,
        "snapshot_count": snapshots.len(),
        "snapshots": snapshots
    })))
}

pub async fn get_binance_price(
    State(state): State<AppState>,
    Path(symbol): Path<String>,
) -> Result<Json<Value>, AppError> {
    let upper = symbol.to_uppercase();
    let price = sqlx::query_scalar::<_, Option<f64>>(
        r#"
        SELECT close_price::float8
        FROM crypto_klines
        WHERE symbol = $1
          AND exchange = 'binance'
          AND period = '1m'
          AND environment = 'mainnet'
        ORDER BY timestamp DESC
        LIMIT 1
        "#,
    )
    .bind(&upper)
    .fetch_optional(&state.db)
    .await
    .map_err(|error| AppError::internal(format!("Failed to load Binance price: {error}")))?;

    Ok(Json(serde_json::json!({
        "symbol": upper,
        "price": price.flatten().unwrap_or(0.0),
        "binance_symbol": format!("{}USDT", symbol.to_uppercase())
    })))
}

pub async fn get_binance_config(
    State(state): State<AppState>,
    Path(account_id): Path<i32>,
) -> Result<Json<Value>, AppError> {
    ensure_account_exists(&state, account_id).await?;
    let trading_mode = get_global_trading_mode(&state).await?;
    let wallets = sqlx::query(
        r#"
        SELECT environment, max_leverage, default_leverage
        FROM binance_wallets
        WHERE account_id = $1
          AND is_active = 'true'
        "#,
    )
    .bind(account_id)
    .fetch_all(&state.db)
    .await
    .map_err(|error| AppError::internal(format!("Failed to load Binance config: {error}")))?;

    let mut testnet: Option<BinanceConfigInfo> = None;
    let mut mainnet: Option<BinanceConfigInfo> = None;
    for row in wallets {
        let info = BinanceConfigInfo {
            configured: true,
            api_key_masked: "****".to_owned(),
            max_leverage: row.try_get("max_leverage").map_err(read_exchange_error)?,
            default_leverage: row
                .try_get("default_leverage")
                .map_err(read_exchange_error)?,
        };
        match row
            .try_get::<String, _>("environment")
            .map_err(read_exchange_error)?
            .as_str()
        {
            "testnet" => testnet = Some(info),
            "mainnet" => mainnet = Some(info),
            _ => {}
        }
    }

    Ok(Json(serde_json::json!({
        "testnet_configured": testnet.is_some(),
        "mainnet_configured": mainnet.is_some(),
        "testnet": testnet,
        "mainnet": mainnet,
        "current_environment": trading_mode
    })))
}

pub async fn get_binance_balance(
    State(state): State<AppState>,
    Path(account_id): Path<i32>,
    Query(query): Query<ExchangeEnvironmentQuery>,
) -> Result<Json<Value>, AppError> {
    let environment = resolve_live_environment(&state, query.environment.as_deref()).await?;
    let _force_refresh = query.force_refresh.unwrap_or(false);
    ensure_binance_wallet(&state, account_id, &environment).await?;
    let snapshot = latest_binance_snapshot(&state, account_id, &environment)
        .await?
        .ok_or_else(|| AppError::not_found(format!("No {environment} snapshot available")))?;
    let snapshot_time = snapshot
        .try_get::<NaiveDateTime, _>("snapshot_time")
        .map_err(read_exchange_error)?;
    let total_equity = snapshot
        .try_get::<f64, _>("total_margin_balance")
        .map_err(read_exchange_error)?;
    let used_margin = snapshot
        .try_get::<Option<f64>, _>("total_initial_margin")
        .map_err(read_exchange_error)?
        .unwrap_or(0.0);

    Ok(Json(serde_json::json!({
        "environment": environment,
        "total_equity": total_equity,
        "available_balance": snapshot.try_get::<f64,_>("available_balance").map_err(read_exchange_error)?,
        "used_margin": used_margin,
        "maintenance_margin": snapshot.try_get::<Option<f64>,_>("total_maint_margin").map_err(read_exchange_error)?.unwrap_or(0.0),
        "unrealized_pnl": snapshot.try_get::<f64,_>("total_unrealized_profit").map_err(read_exchange_error)?,
        "total_wallet_balance": snapshot.try_get::<f64,_>("total_wallet_balance").map_err(read_exchange_error)?,
        "margin_usage_percent": if total_equity > 0.0 { used_margin / total_equity * 100.0 } else { 0.0 },
        "source": "snapshot",
        "timestamp": snapshot_time.and_utc().timestamp_millis(),
        "cached_at": snapshot_time.and_utc().to_rfc3339()
    })))
}

pub async fn get_binance_positions(
    State(state): State<AppState>,
    Path(account_id): Path<i32>,
    Query(query): Query<ExchangeEnvironmentQuery>,
) -> Result<Json<Value>, AppError> {
    let environment = resolve_live_environment(&state, query.environment.as_deref()).await?;
    let _force_refresh = query.force_refresh.unwrap_or(false);
    ensure_binance_wallet(&state, account_id, &environment).await?;
    let snapshot = latest_binance_snapshot(&state, account_id, &environment).await?;
    let (positions, cached_at) = if let Some(snapshot) = snapshot {
        let snapshot_time = snapshot
            .try_get::<NaiveDateTime, _>("snapshot_time")
            .map_err(read_exchange_error)?;
        let snapshot_data = snapshot
            .try_get::<Option<String>, _>("snapshot_data")
            .map_err(read_exchange_error)?
            .unwrap_or_default();
        (
            extract_binance_positions_from_snapshot(&snapshot_data),
            snapshot_time,
        )
    } else {
        (Vec::new(), Utc::now().naive_utc())
    };

    Ok(Json(serde_json::json!({
        "environment": environment,
        "positions": positions,
        "count": positions.len(),
        "source": "snapshot",
        "cached_at": cached_at.and_utc().to_rfc3339()
    })))
}

pub async fn get_binance_summary(
    State(state): State<AppState>,
    Path(account_id): Path<i32>,
    Query(query): Query<ExchangeEnvironmentQuery>,
) -> Result<Json<Value>, AppError> {
    let environment = resolve_live_environment(&state, query.environment.as_deref()).await?;
    ensure_binance_wallet(&state, account_id, &environment).await?;
    let snapshot = latest_binance_snapshot(&state, account_id, &environment)
        .await?
        .ok_or_else(|| AppError::not_found(format!("No {environment} snapshot available")))?;
    let snapshot_time = snapshot
        .try_get::<NaiveDateTime, _>("snapshot_time")
        .map_err(read_exchange_error)?;
    let equity = snapshot
        .try_get::<f64, _>("total_margin_balance")
        .map_err(read_exchange_error)?;
    let used_margin = snapshot
        .try_get::<Option<f64>, _>("total_initial_margin")
        .map_err(read_exchange_error)?
        .unwrap_or(0.0);

    Ok(Json(serde_json::json!({
        "account_id": account_id,
        "environment": environment,
        "exchange": "binance",
        "equity": equity,
        "available_balance": snapshot.try_get::<f64,_>("available_balance").map_err(read_exchange_error)?,
        "used_margin": used_margin,
        "margin_usage": if equity > 0.0 { used_margin / equity * 100.0 } else { 0.0 },
        "unrealized_pnl": snapshot.try_get::<f64,_>("total_unrealized_profit").map_err(read_exchange_error)?,
        "rate_limit": Value::Null,
        "last_updated": snapshot_time.and_utc().to_rfc3339()
    })))
}

pub async fn get_binance_daily_quota(
    State(state): State<AppState>,
    Path(account_id): Path<i32>,
) -> Result<Json<Value>, AppError> {
    const DAILY_QUOTA_LIMIT: i64 = 20;
    let wallet = sqlx::query(
        r#"
        SELECT rebate_working
        FROM binance_wallets
        WHERE account_id = $1
          AND environment = 'mainnet'
          AND is_active = 'true'
        LIMIT 1
        "#,
    )
    .bind(account_id)
    .fetch_optional(&state.db)
    .await
    .map_err(|error| AppError::internal(format!("Failed to load Binance quota wallet: {error}")))?;

    let Some(wallet) = wallet else {
        return Ok(Json(
            serde_json::json!({"limited": false, "used": 0, "limit": DAILY_QUOTA_LIMIT, "remaining": DAILY_QUOTA_LIMIT}),
        ));
    };
    let rebate = wallet
        .try_get::<Option<bool>, _>("rebate_working")
        .map_err(read_exchange_error)?
        .unwrap_or(false);
    let premium_count = sqlx::query_scalar::<_, i64>(
        "SELECT COUNT(*)::bigint FROM user_subscriptions WHERE subscription_type = 'premium'",
    )
    .fetch_one(&state.db)
    .await
    .map_err(|error| AppError::internal(format!("Failed to load premium status: {error}")))?;
    if rebate || premium_count > 0 {
        return Ok(Json(
            serde_json::json!({"limited": false, "used": 0, "limit": DAILY_QUOTA_LIMIT, "remaining": DAILY_QUOTA_LIMIT}),
        ));
    }

    let today_start = Utc::now()
        .date_naive()
        .and_hms_opt(0, 0, 0)
        .expect("valid midnight");
    let ai_count = sqlx::query_scalar::<_, i64>(
        r#"
        SELECT COUNT(*)::bigint
        FROM ai_decision_logs
        WHERE account_id = $1
          AND exchange = 'binance'
          AND hyperliquid_environment = 'mainnet'
          AND created_at >= $2
          AND operation = ANY($3)
        "#,
    )
    .bind(account_id)
    .bind(today_start)
    .bind(vec!["buy", "sell", "close"])
    .fetch_one(&state.db)
    .await
    .map_err(|error| {
        AppError::internal(format!("Failed to count Binance AI quota usage: {error}"))
    })?;
    let program_count = sqlx::query_scalar::<_, i64>(
        r#"
        SELECT COUNT(*)::bigint
        FROM program_execution_logs
        WHERE account_id = $1
          AND exchange = 'binance'
          AND environment = 'mainnet'
          AND created_at >= $2
          AND decision_action = ANY($3)
        "#,
    )
    .bind(account_id)
    .bind(today_start)
    .bind(vec!["buy", "sell", "close"])
    .fetch_one(&state.db)
    .await
    .map_err(|error| {
        AppError::internal(format!(
            "Failed to count Binance program quota usage: {error}"
        ))
    })?;
    let tomorrow = today_start + chrono::Duration::days(1);
    let used = ai_count + program_count;

    Ok(Json(serde_json::json!({
        "limited": true,
        "used": used,
        "limit": DAILY_QUOTA_LIMIT,
        "remaining": (DAILY_QUOTA_LIMIT - used).max(0),
        "reset_at": tomorrow.and_utc().timestamp()
    })))
}

pub async fn get_binance_wallets_all(
    State(state): State<AppState>,
) -> Result<Json<Vec<Value>>, AppError> {
    let rows = sqlx::query(
        r#"
        SELECT
            w.id AS wallet_id,
            w.account_id,
            a.name AS account_name,
            a.model,
            w.environment,
            w.is_active,
            w.max_leverage,
            w.default_leverage
        FROM binance_wallets w
        JOIN accounts a ON a.id = w.account_id
        WHERE w.is_active = 'true'
          AND a.is_active = 'true'
          AND COALESCE(a.is_deleted, false) = false
        ORDER BY a.name ASC, w.environment ASC
        "#,
    )
    .fetch_all(&state.db)
    .await
    .map_err(|error| AppError::internal(format!("Failed to list Binance wallets: {error}")))?;

    let wallets = rows
        .into_iter()
        .map(|row| {
            Ok(serde_json::json!({
                "wallet_id": row.try_get::<i32,_>("wallet_id").map_err(read_exchange_error)?,
                "account_id": row.try_get::<i32,_>("account_id").map_err(read_exchange_error)?,
                "account_name": row.try_get::<String,_>("account_name").map_err(read_exchange_error)?,
                "model": row.try_get::<Option<String>,_>("model").map_err(read_exchange_error)?,
                "api_key_masked": "****",
                "environment": row.try_get::<String,_>("environment").map_err(read_exchange_error)?,
                "is_active": row.try_get::<String,_>("is_active").map_err(read_exchange_error)? == "true",
                "max_leverage": row.try_get::<i32,_>("max_leverage").map_err(read_exchange_error)?,
                "default_leverage": row.try_get::<i32,_>("default_leverage").map_err(read_exchange_error)?,
            }))
        })
        .collect::<Result<Vec<_>, AppError>>()?;

    Ok(Json(wallets))
}

fn extract_binance_positions_from_snapshot(snapshot_data: &str) -> Vec<Value> {
    let Ok(value) = serde_json::from_str::<Value>(snapshot_data) else {
        return Vec::new();
    };
    let Some(positions) = value.get("positions").and_then(Value::as_array) else {
        return Vec::new();
    };

    positions
        .iter()
        .filter_map(|position| {
            let amount = position
                .get("positionAmt")
                .and_then(Value::as_str)
                .and_then(|value| value.parse::<f64>().ok())
                .unwrap_or(0.0);
            if amount == 0.0 {
                return None;
            }
            let symbol = position
                .get("symbol")
                .and_then(Value::as_str)
                .unwrap_or("")
                .trim_end_matches("USDT")
                .to_owned();
            let entry_px = position
                .get("entryPrice")
                .and_then(Value::as_str)
                .and_then(|value| value.parse::<f64>().ok())
                .unwrap_or(0.0);
            let position_value = position
                .get("notional")
                .and_then(Value::as_str)
                .and_then(|value| value.parse::<f64>().ok())
                .unwrap_or(0.0)
                .abs();
            let margin_used = position
                .get("initialMargin")
                .and_then(Value::as_str)
                .and_then(|value| value.parse::<f64>().ok())
                .unwrap_or(0.0);
            let leverage = if margin_used > 0.0 {
                (position_value / margin_used).round() as i32
            } else {
                1
            };
            Some(serde_json::json!({
                "coin": symbol,
                "szi": amount,
                "entry_px": entry_px,
                "position_value": position_value,
                "unrealized_pnl": position
                    .get("unRealizedProfit")
                    .and_then(Value::as_str)
                    .and_then(|value| value.parse::<f64>().ok())
                    .unwrap_or(0.0),
                "leverage": leverage,
                "liquidation_px": position
                    .get("liquidationPrice")
                    .and_then(Value::as_str)
                    .and_then(|value| value.parse::<f64>().ok())
                    .unwrap_or(0.0),
                "margin_used": margin_used,
                "leverage_type": if position
                    .get("isolatedMargin")
                    .and_then(Value::as_str)
                    .and_then(|value| value.parse::<f64>().ok())
                    .unwrap_or(0.0) > 0.0 { "isolated" } else { "cross" }
            }))
        })
        .collect()
}

#[cfg(test)]
mod tests {
    use super::extract_binance_positions_from_snapshot;

    #[test]
    fn parses_binance_positions_from_snapshot_json() {
        let positions = extract_binance_positions_from_snapshot(
            r#"{"positions":[{"symbol":"BTCUSDT","positionAmt":"0.0100","entryPrice":"50000","notional":"505.0","unRealizedProfit":"5","liquidationPrice":"45000","initialMargin":"50.5","isolatedMargin":"0"}]}"#,
        );
        assert_eq!(positions.len(), 1);
        assert_eq!(positions[0]["coin"], "BTC");
        assert_eq!(positions[0]["leverage"], 10);
        assert_eq!(positions[0]["leverage_type"], "cross");
    }
}
