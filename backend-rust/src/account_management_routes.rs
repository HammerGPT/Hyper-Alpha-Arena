use axum::{
    Json,
    extract::{Path, Query, State},
};
use serde::{Deserialize, Serialize};
use sqlx::Row;

use crate::{error::AppError, state::AppState};

#[derive(Deserialize)]
pub struct SessionQuery {
    session_token: String,
}

#[derive(Deserialize)]
pub struct AccountCreateRequest {
    name: String,
    #[serde(default = "default_model")]
    model: String,
    #[serde(default = "default_base_url")]
    base_url: String,
    api_key: String,
    #[serde(default = "default_initial_capital")]
    initial_capital: f64,
    #[serde(default = "default_account_type")]
    account_type: String,
}

#[derive(Deserialize)]
pub struct AccountUpdateRequest {
    name: Option<String>,
    model: Option<String>,
    base_url: Option<String>,
    api_key: Option<String>,
}

#[derive(Serialize)]
pub struct AccountOut {
    id: i32,
    user_id: i32,
    name: String,
    model: String,
    base_url: String,
    api_key: String,
    initial_capital: f64,
    current_cash: f64,
    frozen_cash: f64,
    account_type: String,
    is_active: bool,
}

#[derive(Serialize)]
pub struct MessageResponse {
    message: String,
}

pub async fn list_trading_accounts(
    State(state): State<AppState>,
    Query(query): Query<SessionQuery>,
) -> Result<Json<Vec<AccountOut>>, AppError> {
    let user_id = get_current_user_id(&state, &query.session_token).await?;
    let rows = sqlx::query(
        r#"
        SELECT id, user_id, name, model, base_url, api_key,
               initial_capital::float8 AS initial_capital,
               current_cash::float8 AS current_cash,
               frozen_cash::float8 AS frozen_cash,
               account_type, is_active
        FROM accounts
        WHERE user_id = $1
          AND is_deleted IS DISTINCT FROM true
          AND is_active = 'true'
        ORDER BY id
        "#,
    )
    .bind(user_id)
    .fetch_all(&state.db)
    .await
    .map_err(|error| AppError::internal(format!("Failed to list accounts: {error}")))?;

    let mut accounts = Vec::with_capacity(rows.len());
    for row in rows {
        accounts.push(account_out_from_row(row)?);
    }

    Ok(Json(accounts))
}

pub async fn create_trading_account(
    State(state): State<AppState>,
    Query(query): Query<SessionQuery>,
    Json(payload): Json<AccountCreateRequest>,
) -> Result<Json<AccountOut>, AppError> {
    let user_id = get_current_user_id(&state, &query.session_token).await?;
    ensure_unique_account_name(&state, user_id, &payload.name, None).await?;

    let account_type = payload.account_type.clone();
    let row = sqlx::query(
        r#"
        INSERT INTO accounts (
            user_id, version, name, account_type, model, base_url, api_key,
            initial_capital, current_cash, frozen_cash, is_active, auto_trading_enabled,
            hyperliquid_enabled, max_leverage, default_leverage,
            show_on_dashboard, created_at, updated_at
        )
        VALUES ($1, 'v1', $2, $3, $4, $5, $6, $7, $7, 0, 'true', 'true', 'false', 3, 1, true, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        RETURNING id
        "#,
    )
    .bind(user_id)
    .bind(&payload.name)
    .bind(&account_type)
    .bind(if account_type == "AI" {
        Some(payload.model.as_str())
    } else {
        None
    })
    .bind(if account_type == "AI" {
        Some(payload.base_url.as_str())
    } else {
        None
    })
    .bind(if account_type == "AI" {
        Some(payload.api_key.as_str())
    } else {
        None
    })
    .bind(payload.initial_capital)
    .fetch_one(&state.db)
    .await
    .map_err(|error| AppError::internal(format!("Failed to create account: {error}")))?;

    let account_id = row.try_get::<i32, _>("id").map_err(read_account_error)?;
    Ok(Json(load_account_out(&state, account_id).await?))
}

pub async fn get_trading_account(
    State(state): State<AppState>,
    Path(account_id): Path<i32>,
    Query(query): Query<SessionQuery>,
) -> Result<Json<AccountOut>, AppError> {
    let user_id = get_current_user_id(&state, &query.session_token).await?;
    let row = load_account_row(&state, account_id)
        .await?
        .ok_or_else(|| AppError::not_found("Account not found"))?;
    let owner_id = row
        .try_get::<i32, _>("user_id")
        .map_err(read_account_error)?;
    if owner_id != user_id {
        return Err(AppError::forbidden("Access denied"));
    }
    Ok(Json(account_out_from_row(row)?))
}

pub async fn update_trading_account(
    State(state): State<AppState>,
    Path(account_id): Path<i32>,
    Query(query): Query<SessionQuery>,
    Json(payload): Json<AccountUpdateRequest>,
) -> Result<Json<AccountOut>, AppError> {
    let user_id = get_current_user_id(&state, &query.session_token).await?;
    let current = load_account_row(&state, account_id)
        .await?
        .ok_or_else(|| AppError::not_found("Account not found"))?;

    let owner_id = current
        .try_get::<i32, _>("user_id")
        .map_err(read_account_error)?;
    if owner_id != user_id {
        return Err(AppError::forbidden("Access denied"));
    }

    let name = payload
        .name
        .clone()
        .unwrap_or_else(|| current.try_get::<String, _>("name").unwrap_or_default());
    ensure_unique_account_name(&state, user_id, &name, Some(account_id)).await?;

    let model = payload
        .model
        .or_else(|| current.try_get::<Option<String>, _>("model").ok().flatten());
    let base_url = payload.base_url.or_else(|| {
        current
            .try_get::<Option<String>, _>("base_url")
            .ok()
            .flatten()
    });
    let api_key = payload.api_key.or_else(|| {
        current
            .try_get::<Option<String>, _>("api_key")
            .ok()
            .flatten()
    });

    let result = sqlx::query(
        r#"
        UPDATE accounts
        SET name = $2,
            model = $3,
            base_url = $4,
            api_key = $5,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = $1
          AND is_deleted IS DISTINCT FROM true
        "#,
    )
    .bind(account_id)
    .bind(&name)
    .bind(model.as_deref())
    .bind(base_url.as_deref())
    .bind(api_key.as_deref())
    .execute(&state.db)
    .await
    .map_err(|error| AppError::internal(format!("Failed to update account: {error}")))?;

    if result.rows_affected() == 0 {
        return Err(AppError::not_found("Account not found"));
    }

    Ok(Json(load_account_out(&state, account_id).await?))
}

pub async fn delete_trading_account(
    State(state): State<AppState>,
    Path(account_id): Path<i32>,
    Query(query): Query<SessionQuery>,
) -> Result<Json<MessageResponse>, AppError> {
    let user_id = get_current_user_id(&state, &query.session_token).await?;
    let current = load_account_row(&state, account_id)
        .await?
        .ok_or_else(|| AppError::not_found("Account not found"))?;

    let owner_id = current
        .try_get::<i32, _>("user_id")
        .map_err(read_account_error)?;
    if owner_id != user_id {
        return Err(AppError::forbidden("Access denied"));
    }

    let name = current
        .try_get::<String, _>("name")
        .map_err(read_account_error)?;

    sqlx::query(
        r#"
        UPDATE accounts
        SET is_active = 'false',
            updated_at = CURRENT_TIMESTAMP
        WHERE id = $1
          AND is_deleted IS DISTINCT FROM true
        "#,
    )
    .bind(account_id)
    .execute(&state.db)
    .await
    .map_err(|error| AppError::internal(format!("Failed to delete account: {error}")))?;

    Ok(Json(MessageResponse {
        message: format!("Account {name} deactivated successfully"),
    }))
}

pub async fn get_or_create_default_account_endpoint(
    State(state): State<AppState>,
    Path(_account_id): Path<i32>,
    Query(query): Query<SessionQuery>,
) -> Result<Json<AccountOut>, AppError> {
    let user_id = get_current_user_id(&state, &query.session_token).await?;
    let existing = sqlx::query_scalar::<_, i32>(
        r#"
        SELECT id
        FROM accounts
        WHERE user_id = $1
          AND is_deleted IS DISTINCT FROM true
          AND is_active = 'true'
        ORDER BY id
        LIMIT 1
        "#,
    )
    .bind(user_id)
    .fetch_optional(&state.db)
    .await
    .map_err(|error| AppError::internal(format!("Failed to get default account: {error}")))?;

    let account_id = if let Some(id) = existing {
        id
    } else {
        let row = sqlx::query(
            r#"
            INSERT INTO accounts (
                user_id, version, name, account_type, model, base_url, api_key,
                initial_capital, current_cash, frozen_cash, is_active, created_at, updated_at
            )
            VALUES (
                $1, 'v1', 'Default AI Trader', 'AI', 'gpt-4-turbo',
                'https://api.openai.com/v1', 'default-key-please-update-in-settings',
                10000.0, 10000.0, 0.0, 'true', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
            RETURNING id
            "#,
        )
        .bind(user_id)
        .fetch_one(&state.db)
        .await
        .map_err(|error| {
            AppError::internal(format!("Failed to create default account: {error}"))
        })?;
        row.try_get::<i32, _>("id").map_err(read_account_error)?
    };

    Ok(Json(load_account_out(&state, account_id).await?))
}

async fn get_current_user_id(state: &AppState, session_token: &str) -> Result<i32, AppError> {
    sqlx::query_scalar::<_, i32>(
        r#"
        SELECT user_id
        FROM user_auth_sessions
        WHERE session_token = $1
          AND expires_at > CURRENT_TIMESTAMP
        LIMIT 1
        "#,
    )
    .bind(session_token)
    .fetch_optional(&state.db)
    .await
    .map_err(|error| AppError::internal(format!("Failed to verify session token: {error}")))?
    .ok_or_else(|| AppError::unauthorized("Invalid or expired session"))
}

async fn ensure_unique_account_name(
    state: &AppState,
    user_id: i32,
    name: &str,
    exclude_account_id: Option<i32>,
) -> Result<(), AppError> {
    let rows = sqlx::query(
        r#"
        SELECT id, name
        FROM accounts
        WHERE user_id = $1
          AND is_deleted IS DISTINCT FROM true
          AND is_active = 'true'
        "#,
    )
    .bind(user_id)
    .fetch_all(&state.db)
    .await
    .map_err(|error| {
        AppError::internal(format!("Failed to check account name uniqueness: {error}"))
    })?;

    for row in rows {
        let account_id = row.try_get::<i32, _>("id").map_err(read_account_error)?;
        if Some(account_id) == exclude_account_id {
            continue;
        }
        let existing_name = row
            .try_get::<String, _>("name")
            .map_err(read_account_error)?;
        if existing_name == name {
            return Err(AppError::bad_request("Account name already exists"));
        }
    }
    Ok(())
}

async fn load_account_out(state: &AppState, account_id: i32) -> Result<AccountOut, AppError> {
    let row = load_account_row(state, account_id)
        .await?
        .ok_or_else(|| AppError::not_found("Account not found"))?;
    account_out_from_row(row)
}

async fn load_account_row(
    state: &AppState,
    account_id: i32,
) -> Result<Option<sqlx::postgres::PgRow>, AppError> {
    sqlx::query(
        r#"
        SELECT id, user_id, name, model, base_url, api_key,
               initial_capital::float8 AS initial_capital,
               current_cash::float8 AS current_cash,
               frozen_cash::float8 AS frozen_cash,
               account_type, is_active
        FROM accounts
        WHERE id = $1
          AND is_deleted IS DISTINCT FROM true
        LIMIT 1
        "#,
    )
    .bind(account_id)
    .fetch_optional(&state.db)
    .await
    .map_err(|error| AppError::internal(format!("Failed to load account: {error}")))
}

fn account_out_from_row(row: sqlx::postgres::PgRow) -> Result<AccountOut, AppError> {
    Ok(AccountOut {
        id: row.try_get("id").map_err(read_account_error)?,
        user_id: row.try_get("user_id").map_err(read_account_error)?,
        name: row.try_get("name").map_err(read_account_error)?,
        model: row
            .try_get::<Option<String>, _>("model")
            .map_err(read_account_error)?
            .unwrap_or_default(),
        base_url: row
            .try_get::<Option<String>, _>("base_url")
            .map_err(read_account_error)?
            .unwrap_or_default(),
        api_key: mask_api_key(
            row.try_get::<Option<String>, _>("api_key")
                .map_err(read_account_error)?,
        ),
        initial_capital: row
            .try_get::<f64, _>("initial_capital")
            .map_err(read_account_error)?,
        current_cash: row
            .try_get::<f64, _>("current_cash")
            .map_err(read_account_error)?,
        frozen_cash: row
            .try_get::<f64, _>("frozen_cash")
            .map_err(read_account_error)?,
        account_type: row.try_get("account_type").map_err(read_account_error)?,
        is_active: row
            .try_get::<String, _>("is_active")
            .map_err(read_account_error)?
            == "true",
    })
}

fn mask_api_key(api_key: Option<String>) -> String {
    match api_key {
        Some(key) if key.len() > 4 => format!("****{}", &key[key.len() - 4..]),
        Some(_) => "****".to_owned(),
        None => String::new(),
    }
}

fn read_account_error(error: sqlx::Error) -> AppError {
    AppError::internal(format!("Failed to read account data: {error}"))
}

fn default_model() -> String {
    "gpt-4-turbo".to_owned()
}

fn default_base_url() -> String {
    "https://api.openai.com/v1".to_owned()
}

fn default_initial_capital() -> f64 {
    10000.0
}

fn default_account_type() -> String {
    "AI".to_owned()
}

#[cfg(test)]
mod tests {
    use super::{
        default_account_type, default_base_url, default_initial_capital, default_model,
        mask_api_key,
    };

    #[test]
    fn defaults_match_legacy_account_repo() {
        assert_eq!(default_model(), "gpt-4-turbo");
        assert_eq!(default_base_url(), "https://api.openai.com/v1");
        assert_eq!(default_initial_capital(), 10000.0);
        assert_eq!(default_account_type(), "AI");
    }

    #[test]
    fn api_key_masking_matches_legacy_shape() {
        assert_eq!(mask_api_key(Some("abcdef1234".to_owned())), "****1234");
        assert_eq!(mask_api_key(Some("abc".to_owned())), "****");
        assert_eq!(mask_api_key(None), "");
    }
}
