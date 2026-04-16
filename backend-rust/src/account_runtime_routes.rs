use axum::{
    Json,
    extract::{Path, Query, State},
};
use chrono::NaiveDateTime;
use serde::{Deserialize, Serialize};
use sqlx::Row;

use crate::{error::AppError, state::AppState};

#[derive(Deserialize)]
pub struct IncludeHiddenQuery {
    include_hidden: Option<bool>,
}

#[derive(Serialize)]
pub struct AccountListItem {
    id: i32,
    user_id: i32,
    username: String,
    name: String,
    account_type: String,
    initial_capital: f64,
    current_cash: f64,
    frozen_cash: f64,
    model: Option<String>,
    base_url: Option<String>,
    api_key: Option<String>,
    is_active: bool,
    auto_trading_enabled: bool,
    wallet_address: Option<String>,
    has_mainnet_wallet: bool,
    show_on_dashboard: bool,
    avatar_preset_id: Option<i32>,
}

#[derive(Serialize)]
pub struct AccountOverviewResponse {
    account: AccountOverviewAccount,
    #[serde(skip_serializing_if = "Option::is_none")]
    total_assets: Option<f64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    positions_value: Option<f64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    positions_count: Option<i64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pending_orders: Option<i64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    portfolio: Option<AccountOverviewPortfolio>,
}

#[derive(Serialize)]
pub struct AccountOverviewAccount {
    id: i32,
    name: String,
    account_type: String,
    current_cash: f64,
    frozen_cash: f64,
}

#[derive(Serialize)]
pub struct AccountOverviewPortfolio {
    total_assets: f64,
    positions_value: f64,
    positions_count: i64,
    pending_orders: i64,
}

#[derive(Serialize)]
pub struct StrategyConfigResponse {
    trigger_mode: String,
    interval_seconds: i32,
    tick_batch_size: i32,
    enabled: bool,
    scheduled_trigger_enabled: bool,
    exchange: String,
    last_trigger_at: Option<String>,
    price_threshold: f64,
    signal_pool_id: Option<i32>,
    signal_pool_ids: Option<Vec<i32>>,
    signal_pool_name: Option<String>,
    signal_pool_names: Option<Vec<String>>,
    warning: Option<String>,
}

#[derive(Deserialize)]
pub struct StrategyConfigUpdateRequest {
    interval_seconds: Option<i32>,
    enabled: bool,
    scheduled_trigger_enabled: bool,
    exchange: String,
    price_threshold: Option<f64>,
    signal_pool_id: Option<i32>,
    signal_pool_ids: Option<Vec<i32>>,
}

pub async fn list_all_accounts(
    State(state): State<AppState>,
    Query(query): Query<IncludeHiddenQuery>,
) -> Result<Json<Vec<AccountListItem>>, AppError> {
    let include_hidden = query.include_hidden.unwrap_or(false);
    let rows = sqlx::query(
        r#"
        SELECT a.id, a.user_id, u.username, a.name, a.account_type,
               a.initial_capital::float8 AS initial_capital,
               a.current_cash::float8 AS current_cash,
               a.frozen_cash::float8 AS frozen_cash,
               a.model, a.base_url, a.api_key, a.is_active,
               a.auto_trading_enabled, a.show_on_dashboard, a.avatar_preset_id,
               a.hyperliquid_environment
        FROM accounts a
        LEFT JOIN users u ON u.id = a.user_id
        WHERE a.is_active = 'true'
          AND a.is_deleted IS DISTINCT FROM true
          AND ($1::bool = true OR a.show_on_dashboard = true)
        ORDER BY a.id
        "#,
    )
    .bind(include_hidden)
    .fetch_all(&state.db)
    .await
    .map_err(|error| AppError::internal(format!("Failed to list accounts: {error}")))?;

    let mut accounts = Vec::new();
    for row in rows {
        let account_id = row
            .try_get::<i32, _>("id")
            .map_err(read_account_runtime_error)?;
        let environment = row
            .try_get::<Option<String>, _>("hyperliquid_environment")
            .map_err(read_account_runtime_error)?;
        let (current_cash, frozen_cash) = resolve_cached_balances(
            &state,
            account_id,
            environment.as_deref(),
            row.try_get::<f64, _>("current_cash")
                .map_err(read_account_runtime_error)?,
            row.try_get::<f64, _>("frozen_cash")
                .map_err(read_account_runtime_error)?,
        )
        .await?;
        let (wallet_address, has_mainnet_wallet) =
            load_mainnet_wallet_metadata(&state, account_id).await?;

        accounts.push(AccountListItem {
            id: account_id,
            user_id: row.try_get("user_id").map_err(read_account_runtime_error)?,
            username: row
                .try_get::<Option<String>, _>("username")
                .map_err(read_account_runtime_error)?
                .unwrap_or_else(|| "unknown".to_owned()),
            name: row.try_get("name").map_err(read_account_runtime_error)?,
            account_type: row
                .try_get("account_type")
                .map_err(read_account_runtime_error)?,
            initial_capital: row
                .try_get("initial_capital")
                .map_err(read_account_runtime_error)?,
            current_cash,
            frozen_cash,
            model: row.try_get("model").map_err(read_account_runtime_error)?,
            base_url: row
                .try_get("base_url")
                .map_err(read_account_runtime_error)?,
            api_key: row.try_get("api_key").map_err(read_account_runtime_error)?,
            is_active: row
                .try_get::<String, _>("is_active")
                .map_err(read_account_runtime_error)?
                == "true",
            auto_trading_enabled: row
                .try_get::<String, _>("auto_trading_enabled")
                .map_err(read_account_runtime_error)?
                == "true",
            wallet_address,
            has_mainnet_wallet,
            show_on_dashboard: row
                .try_get::<Option<bool>, _>("show_on_dashboard")
                .map_err(read_account_runtime_error)?
                .unwrap_or(true),
            avatar_preset_id: row
                .try_get("avatar_preset_id")
                .map_err(read_account_runtime_error)?,
        });
    }

    Ok(Json(accounts))
}

pub async fn get_specific_account_overview(
    State(state): State<AppState>,
    Path(account_id): Path<i32>,
) -> Result<Json<AccountOverviewResponse>, AppError> {
    let account = load_account_row(&state, account_id)
        .await?
        .ok_or_else(|| AppError::not_found("Account not found"))?;
    Ok(Json(build_specific_overview(&state, account).await?))
}

pub async fn get_account_overview(
    State(state): State<AppState>,
) -> Result<Json<AccountOverviewResponse>, AppError> {
    let account = sqlx::query(
        r#"
        SELECT id, name, account_type, current_cash::float8 AS current_cash,
               frozen_cash::float8 AS frozen_cash, is_active, hyperliquid_environment
        FROM accounts
        WHERE is_active = 'true'
          AND is_deleted IS DISTINCT FROM true
        ORDER BY id
        LIMIT 1
        "#,
    )
    .fetch_optional(&state.db)
    .await
    .map_err(|error| AppError::internal(format!("Failed to get overview: {error}")))?
    .ok_or_else(|| AppError::not_found("No active account found"))?;

    Ok(Json(build_default_overview(&state, account).await?))
}

pub async fn get_account_strategy(
    State(state): State<AppState>,
    Path(account_id): Path<i32>,
) -> Result<Json<StrategyConfigResponse>, AppError> {
    let account = load_account_row(&state, account_id)
        .await?
        .ok_or_else(|| AppError::not_found("Account not found"))?;
    let strategy_row = load_or_create_strategy_row(&state, &account).await?;
    Ok(Json(
        serialize_strategy(&state, &account, strategy_row).await?,
    ))
}

pub async fn update_account_strategy(
    State(state): State<AppState>,
    Path(account_id): Path<i32>,
    Json(payload): Json<StrategyConfigUpdateRequest>,
) -> Result<Json<StrategyConfigResponse>, AppError> {
    let account = load_account_row(&state, account_id)
        .await?
        .ok_or_else(|| AppError::not_found("Account not found"))?;

    if let Some(threshold) = payload.price_threshold
        && (threshold <= 0.0 || threshold > 10.0)
    {
        return Err(AppError::bad_request(
            "price_threshold must be between 0.1 and 10.0",
        ));
    }
    if let Some(interval) = payload.interval_seconds
        && interval < 30
    {
        return Err(AppError::bad_request(
            "trigger_interval must be >= 30 seconds",
        ));
    }

    let interval = payload.interval_seconds.unwrap_or(150);
    let price_threshold = payload.price_threshold.unwrap_or(1.0);
    let signal_pool_ids = if let Some(ids) = payload.signal_pool_ids.clone() {
        ids
    } else if let Some(id) = payload.signal_pool_id {
        vec![id]
    } else {
        Vec::new()
    };

    sqlx::query(
        r#"
        INSERT INTO account_strategy_configs (
            account_id, price_threshold, trigger_interval, signal_pool_id, signal_pool_ids,
            enabled, scheduled_trigger_enabled, exchange, created_at, updated_at
        )
        VALUES (
            $1, $2, $3,
            $4, $5,
            $6, $7, $8, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
        )
        ON CONFLICT (account_id)
        DO UPDATE SET
            price_threshold = EXCLUDED.price_threshold,
            trigger_interval = EXCLUDED.trigger_interval,
            signal_pool_id = EXCLUDED.signal_pool_id,
            signal_pool_ids = EXCLUDED.signal_pool_ids,
            enabled = EXCLUDED.enabled,
            scheduled_trigger_enabled = EXCLUDED.scheduled_trigger_enabled,
            exchange = EXCLUDED.exchange,
            updated_at = CURRENT_TIMESTAMP
        "#,
    )
    .bind(account_id)
    .bind(price_threshold)
    .bind(interval)
    .bind(signal_pool_ids.first().copied())
    .bind(if signal_pool_ids.is_empty() {
        None
    } else {
        Some(
            serde_json::to_string(&signal_pool_ids).map_err(|e| {
                AppError::internal(format!("Failed to serialize signal pool ids: {e}"))
            })?,
        )
    })
    .bind(if payload.enabled { "true" } else { "false" })
    .bind(payload.scheduled_trigger_enabled)
    .bind(&payload.exchange)
    .execute(&state.db)
    .await
    .map_err(|error| AppError::internal(format!("Failed to update strategy: {error}")))?;

    let strategy_row = load_strategy_row(&state, account_id)
        .await?
        .ok_or_else(|| AppError::internal("Strategy row missing after update"))?;
    Ok(Json(
        serialize_strategy(&state, &account, strategy_row).await?,
    ))
}

async fn build_specific_overview(
    state: &AppState,
    account: sqlx::postgres::PgRow,
) -> Result<AccountOverviewResponse, AppError> {
    let account_id = account
        .try_get::<i32, _>("id")
        .map_err(read_account_runtime_error)?;
    let environment = account
        .try_get::<Option<String>, _>("hyperliquid_environment")
        .map_err(read_account_runtime_error)?;
    let current_cash_db = account
        .try_get::<f64, _>("current_cash")
        .map_err(read_account_runtime_error)?;
    let frozen_cash_db = account
        .try_get::<f64, _>("frozen_cash")
        .map_err(read_account_runtime_error)?;
    let (current_cash, frozen_cash) = resolve_cached_balances(
        state,
        account_id,
        environment.as_deref(),
        current_cash_db,
        frozen_cash_db,
    )
    .await?;
    let positions_value =
        estimate_positions_value(state, account_id, environment.as_deref()).await?;
    let positions_count = count_positions(state, account_id, environment.as_deref()).await?;
    let pending_orders = count_pending_orders(state, account_id).await?;

    Ok(AccountOverviewResponse {
        account: AccountOverviewAccount {
            id: account_id,
            name: account
                .try_get("name")
                .map_err(read_account_runtime_error)?,
            account_type: account
                .try_get("account_type")
                .map_err(read_account_runtime_error)?,
            current_cash,
            frozen_cash,
        },
        total_assets: Some(positions_value + current_cash),
        positions_value: Some(positions_value),
        positions_count: Some(positions_count),
        pending_orders: Some(pending_orders),
        portfolio: None,
    })
}

async fn build_default_overview(
    state: &AppState,
    account: sqlx::postgres::PgRow,
) -> Result<AccountOverviewResponse, AppError> {
    let specific = build_specific_overview(state, account).await?;
    Ok(AccountOverviewResponse {
        account: specific.account,
        total_assets: None,
        positions_value: None,
        positions_count: None,
        pending_orders: None,
        portfolio: Some(AccountOverviewPortfolio {
            total_assets: specific.total_assets.unwrap_or(0.0),
            positions_value: specific.positions_value.unwrap_or(0.0),
            positions_count: specific.positions_count.unwrap_or(0),
            pending_orders: specific.pending_orders.unwrap_or(0),
        }),
    })
}

async fn load_account_row(
    state: &AppState,
    account_id: i32,
) -> Result<Option<sqlx::postgres::PgRow>, AppError> {
    sqlx::query(
        r#"
        SELECT id, name, account_type,
               current_cash::float8 AS current_cash,
               frozen_cash::float8 AS frozen_cash,
               is_active,
               auto_trading_enabled,
               hyperliquid_environment
        FROM accounts
        WHERE id = $1
          AND is_active = 'true'
          AND is_deleted IS DISTINCT FROM true
        LIMIT 1
        "#,
    )
    .bind(account_id)
    .fetch_optional(&state.db)
    .await
    .map_err(|error| AppError::internal(format!("Failed to load account: {error}")))
}

async fn resolve_cached_balances(
    state: &AppState,
    account_id: i32,
    environment: Option<&str>,
    current_cash_db: f64,
    frozen_cash_db: f64,
) -> Result<(f64, f64), AppError> {
    let Some(environment) = environment else {
        return Ok((current_cash_db, frozen_cash_db));
    };
    let snapshot = sqlx::query(
        r#"
        SELECT available_balance::float8 AS available_balance,
               used_margin::float8 AS used_margin
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
    .map_err(|error| {
        AppError::internal(format!(
            "Failed to load cached account balance snapshot: {error}"
        ))
    })?;

    if let Some(snapshot) = snapshot {
        let available = snapshot
            .try_get::<f64, _>("available_balance")
            .map_err(read_account_runtime_error)?;
        let used_margin = snapshot
            .try_get::<f64, _>("used_margin")
            .map_err(read_account_runtime_error)?;
        return Ok((available, used_margin));
    }
    Ok((current_cash_db, frozen_cash_db))
}

async fn load_mainnet_wallet_metadata(
    state: &AppState,
    account_id: i32,
) -> Result<(Option<String>, bool), AppError> {
    let row = sqlx::query(
        r#"
        SELECT wallet_address
        FROM hyperliquid_wallets
        WHERE account_id = $1
          AND environment = 'mainnet'
          AND is_active = 'true'
        LIMIT 1
        "#,
    )
    .bind(account_id)
    .fetch_optional(&state.db)
    .await
    .map_err(|error| AppError::internal(format!("Failed to load wallet metadata: {error}")))?;
    Ok(match row {
        Some(row) => (
            row.try_get::<String, _>("wallet_address")
                .map_err(read_account_runtime_error)
                .ok(),
            true,
        ),
        None => (None, false),
    })
}

async fn estimate_positions_value(
    state: &AppState,
    account_id: i32,
    environment: Option<&str>,
) -> Result<f64, AppError> {
    if let Some(environment) = environment {
        let latest_snapshot_time = sqlx::query_scalar::<_, Option<NaiveDateTime>>(
            r#"
            SELECT MAX(snapshot_time)
            FROM hyperliquid_positions
            WHERE account_id = $1
              AND environment = $2
            "#,
        )
        .bind(account_id)
        .bind(environment)
        .fetch_one(&state.db)
        .await
        .map_err(|error| {
            AppError::internal(format!("Failed to load position snapshots: {error}"))
        })?;
        if let Some(snapshot_time) = latest_snapshot_time {
            let total = sqlx::query_scalar::<_, Option<f64>>(
                r#"
                SELECT COALESCE(SUM(position_value::float8), 0)
                FROM hyperliquid_positions
                WHERE account_id = $1
                  AND environment = $2
                  AND snapshot_time = $3
                  AND position_size != 0
                "#,
            )
            .bind(account_id)
            .bind(environment)
            .bind(snapshot_time)
            .fetch_one(&state.db)
            .await
            .map_err(|error| {
                AppError::internal(format!("Failed to sum position value: {error}"))
            })?;
            return Ok(total.unwrap_or(0.0));
        }
    }

    let positions = sqlx::query(
        r#"
        SELECT symbol, quantity::float8 AS quantity, avg_cost::float8 AS avg_cost
        FROM positions
        WHERE account_id = $1
          AND quantity > 0
        "#,
    )
    .bind(account_id)
    .fetch_all(&state.db)
    .await
    .map_err(|error| AppError::internal(format!("Failed to load positions: {error}")))?;

    let mut total = 0.0;
    for row in positions {
        let symbol = row
            .try_get::<String, _>("symbol")
            .map_err(read_account_runtime_error)?;
        let quantity = row
            .try_get::<f64, _>("quantity")
            .map_err(read_account_runtime_error)?;
        let avg_cost = row
            .try_get::<f64, _>("avg_cost")
            .map_err(read_account_runtime_error)?;
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
            AppError::internal(format!("Failed to load price for position: {error}"))
        })?;
        total += quantity * price.flatten().unwrap_or(avg_cost);
    }
    Ok(total)
}

async fn count_positions(
    state: &AppState,
    account_id: i32,
    environment: Option<&str>,
) -> Result<i64, AppError> {
    if let Some(environment) = environment {
        let latest_snapshot_time = sqlx::query_scalar::<_, Option<NaiveDateTime>>(
            r#"
            SELECT MAX(snapshot_time)
            FROM hyperliquid_positions
            WHERE account_id = $1
              AND environment = $2
            "#,
        )
        .bind(account_id)
        .bind(environment)
        .fetch_one(&state.db)
        .await
        .map_err(|error| {
            AppError::internal(format!("Failed to load position snapshot time: {error}"))
        })?;
        if let Some(snapshot_time) = latest_snapshot_time {
            return sqlx::query_scalar::<_, i64>(
                r#"
                SELECT COUNT(*)::bigint
                FROM hyperliquid_positions
                WHERE account_id = $1
                  AND environment = $2
                  AND snapshot_time = $3
                  AND position_size != 0
                "#,
            )
            .bind(account_id)
            .bind(environment)
            .bind(snapshot_time)
            .fetch_one(&state.db)
            .await
            .map_err(|error| {
                AppError::internal(format!("Failed to count hyperliquid positions: {error}"))
            });
        }
    }

    sqlx::query_scalar::<_, i64>(
        r#"
        SELECT COUNT(*)::bigint
        FROM positions
        WHERE account_id = $1
          AND quantity > 0
        "#,
    )
    .bind(account_id)
    .fetch_one(&state.db)
    .await
    .map_err(|error| AppError::internal(format!("Failed to count positions: {error}")))
}

async fn count_pending_orders(state: &AppState, account_id: i32) -> Result<i64, AppError> {
    sqlx::query_scalar::<_, i64>(
        r#"
        SELECT COUNT(*)::bigint
        FROM orders
        WHERE account_id = $1
          AND status = 'PENDING'
        "#,
    )
    .bind(account_id)
    .fetch_one(&state.db)
    .await
    .map_err(|error| AppError::internal(format!("Failed to count pending orders: {error}")))
}

async fn load_strategy_row(
    state: &AppState,
    account_id: i32,
) -> Result<Option<sqlx::postgres::PgRow>, AppError> {
    sqlx::query(
        r#"
        SELECT account_id, price_threshold, trigger_interval, signal_pool_id, signal_pool_ids,
               enabled, scheduled_trigger_enabled, exchange, last_trigger_at
        FROM account_strategy_configs
        WHERE account_id = $1
        LIMIT 1
        "#,
    )
    .bind(account_id)
    .fetch_optional(&state.db)
    .await
    .map_err(|error| AppError::internal(format!("Failed to load strategy: {error}")))
}

async fn load_or_create_strategy_row(
    state: &AppState,
    account: &sqlx::postgres::PgRow,
) -> Result<sqlx::postgres::PgRow, AppError> {
    let account_id = account
        .try_get::<i32, _>("id")
        .map_err(read_account_runtime_error)?;
    if let Some(row) = load_strategy_row(state, account_id).await? {
        return Ok(row);
    }

    let has_binance = sqlx::query_scalar::<_, i64>(
        r#"
        SELECT COUNT(*)::bigint
        FROM binance_wallets
        WHERE account_id = $1
          AND is_active = 'true'
        "#,
    )
    .bind(account_id)
    .fetch_one(&state.db)
    .await
    .map_err(|error| AppError::internal(format!("Failed to check binance wallet: {error}")))?;
    let default_exchange = if has_binance > 0 {
        "binance"
    } else {
        "hyperliquid"
    };
    let enabled = account
        .try_get::<String, _>("auto_trading_enabled")
        .map_err(read_account_runtime_error)?
        == "true";

    sqlx::query(
        r#"
        INSERT INTO account_strategy_configs (
            account_id, price_threshold, trigger_interval, signal_pool_id, signal_pool_ids,
            enabled, scheduled_trigger_enabled, exchange, created_at, updated_at
        )
        VALUES ($1, 1.0, 150, NULL, NULL, $2, true, $3, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        "#,
    )
    .bind(account_id)
    .bind(if enabled { "true" } else { "false" })
    .bind(default_exchange)
    .execute(&state.db)
    .await
    .map_err(|error| AppError::internal(format!("Failed to create default strategy: {error}")))?;

    load_strategy_row(state, account_id)
        .await?
        .ok_or_else(|| AppError::internal("Failed to create default strategy"))
}

async fn serialize_strategy(
    state: &AppState,
    account: &sqlx::postgres::PgRow,
    strategy: sqlx::postgres::PgRow,
) -> Result<StrategyConfigResponse, AppError> {
    let signal_pool_ids = parse_signal_pool_ids(
        strategy
            .try_get::<Option<String>, _>("signal_pool_ids")
            .ok()
            .flatten(),
        strategy
            .try_get::<Option<i32>, _>("signal_pool_id")
            .ok()
            .flatten(),
    );
    let signal_pool_names = if signal_pool_ids.is_empty() {
        Vec::new()
    } else {
        load_signal_pool_names(state, &signal_pool_ids).await?
    };

    let account_id = account
        .try_get::<i32, _>("id")
        .map_err(read_account_runtime_error)?;
    let has_trigger_enabled = strategy
        .try_get::<bool, _>("scheduled_trigger_enabled")
        .map_err(read_account_runtime_error)?
        || !signal_pool_ids.is_empty();
    let prompt_binding_exists = sqlx::query_scalar::<_, i64>(
        r#"
        SELECT COUNT(*)::bigint
        FROM account_prompt_bindings
        WHERE account_id = $1
          AND is_deleted != true
        "#,
    )
    .bind(account_id)
    .fetch_one(&state.db)
    .await
    .map_err(|error| AppError::internal(format!("Failed to check prompt binding: {error}")))?;

    let warning = if has_trigger_enabled && prompt_binding_exists == 0 {
        Some(
            "No prompt template bound. Scheduled and signal triggers will not execute until a prompt is configured."
                .to_owned(),
        )
    } else {
        None
    };

    Ok(StrategyConfigResponse {
        trigger_mode: "unified".to_owned(),
        interval_seconds: strategy
            .try_get::<i32, _>("trigger_interval")
            .map_err(read_account_runtime_error)?
            .max(150),
        tick_batch_size: 1,
        enabled: strategy
            .try_get::<String, _>("enabled")
            .map_err(read_account_runtime_error)?
            == "true"
            && account
                .try_get::<String, _>("auto_trading_enabled")
                .map_err(read_account_runtime_error)?
                == "true",
        scheduled_trigger_enabled: strategy
            .try_get::<bool, _>("scheduled_trigger_enabled")
            .map_err(read_account_runtime_error)?,
        exchange: strategy
            .try_get::<Option<String>, _>("exchange")
            .map_err(read_account_runtime_error)?
            .unwrap_or_else(|| "hyperliquid".to_owned()),
        last_trigger_at: strategy
            .try_get::<Option<NaiveDateTime>, _>("last_trigger_at")
            .map_err(read_account_runtime_error)?
            .map(format_utc_iso),
        price_threshold: strategy
            .try_get::<f64, _>("price_threshold")
            .map_err(read_account_runtime_error)?,
        signal_pool_id: signal_pool_ids.first().copied(),
        signal_pool_ids: if signal_pool_ids.is_empty() {
            None
        } else {
            Some(signal_pool_ids.clone())
        },
        signal_pool_name: signal_pool_names.first().cloned(),
        signal_pool_names: if signal_pool_names.is_empty() {
            None
        } else {
            Some(signal_pool_names)
        },
        warning,
    })
}

async fn load_signal_pool_names(state: &AppState, ids: &[i32]) -> Result<Vec<String>, AppError> {
    let rows = sqlx::query(
        r#"
        SELECT id, pool_name
        FROM signal_pools
        WHERE id = ANY($1)
          AND (is_deleted IS NULL OR is_deleted = false)
        "#,
    )
    .bind(ids)
    .fetch_all(&state.db)
    .await
    .map_err(|error| AppError::internal(format!("Failed to load signal pool names: {error}")))?;
    let mut map = std::collections::HashMap::new();
    for row in rows {
        map.insert(
            row.try_get::<i32, _>("id")
                .map_err(read_account_runtime_error)?,
            row.try_get::<String, _>("pool_name")
                .map_err(read_account_runtime_error)?,
        );
    }
    Ok(ids.iter().filter_map(|id| map.get(id).cloned()).collect())
}

fn parse_signal_pool_ids(raw: Option<String>, fallback: Option<i32>) -> Vec<i32> {
    if let Some(raw) = raw
        && let Ok(ids) = serde_json::from_str::<Vec<i32>>(&raw)
    {
        return ids;
    }
    fallback.into_iter().collect()
}

fn format_utc_iso(value: NaiveDateTime) -> String {
    value.and_utc().to_rfc3339()
}

fn read_account_runtime_error(error: sqlx::Error) -> AppError {
    AppError::internal(format!("Failed to read account runtime data: {error}"))
}

#[cfg(test)]
mod tests {
    use super::{format_utc_iso, parse_signal_pool_ids};
    use chrono::NaiveDate;

    #[test]
    fn parses_signal_pool_ids_with_fallback() {
        assert_eq!(
            parse_signal_pool_ids(Some("[1,2]".to_owned()), None),
            vec![1, 2]
        );
        assert_eq!(parse_signal_pool_ids(None, Some(3)), vec![3]);
        assert!(parse_signal_pool_ids(None, None).is_empty());
    }

    #[test]
    fn formats_last_trigger_as_utc_iso() {
        let dt = NaiveDate::from_ymd_opt(2026, 4, 15)
            .expect("date")
            .and_hms_opt(8, 0, 0)
            .expect("time");
        assert_eq!(format_utc_iso(dt), "2026-04-15T08:00:00+00:00");
    }
}
