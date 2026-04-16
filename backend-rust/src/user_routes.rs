use axum::{
    Json,
    extract::{Query, State},
};
use chrono::{DateTime, NaiveDateTime, Utc};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use sqlx::Row;
use uuid::Uuid;

use crate::{error::AppError, state::AppState};

#[derive(Deserialize)]
pub struct UserCreateRequest {
    username: String,
    email: Option<String>,
    password: Option<String>,
}

#[derive(Deserialize)]
pub struct UserLoginRequest {
    username: String,
    password: String,
}

#[derive(Deserialize)]
pub struct UserUpdateRequest {
    username: Option<String>,
    email: Option<String>,
}

#[derive(Serialize)]
pub struct UserOut {
    id: i32,
    username: String,
    email: Option<String>,
    is_active: bool,
}

#[derive(Serialize)]
pub struct UserAuthResponse {
    user: UserOut,
    session_token: String,
    expires_at: String,
}

#[derive(Deserialize)]
pub struct ExchangeConfigRequest {
    selected_exchange: String,
}

#[derive(Serialize)]
pub struct ExchangeConfigResponse {
    selected_exchange: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    status: Option<String>,
}

#[derive(Deserialize)]
pub struct MembershipSyncRequest {
    username: String,
    status: Option<String>,
    current_period_end: Option<String>,
}

#[derive(Serialize)]
pub struct MembershipSyncResponse {
    status: String,
    message: String,
    subscription_type: String,
    max_sampling_depth: i32,
}

#[derive(Serialize)]
pub struct ClearMembershipResponse {
    status: String,
    deleted_count: u64,
}

#[derive(Deserialize)]
pub struct SessionTokenQuery {
    session_token: String,
}

pub async fn get_exchange_config(
    State(state): State<AppState>,
) -> Result<Json<ExchangeConfigResponse>, AppError> {
    let selected_exchange = sqlx::query_scalar::<_, String>(
        "SELECT selected_exchange FROM user_exchange_config WHERE user_id = 1 LIMIT 1",
    )
    .fetch_optional(&state.db)
    .await
    .map_err(|error| AppError::internal(format!("Failed to get exchange config: {error}")))?
    .unwrap_or_else(|| "hyperliquid".to_owned());

    Ok(Json(ExchangeConfigResponse {
        selected_exchange,
        status: None,
    }))
}

pub async fn register_user(
    State(state): State<AppState>,
    Json(payload): Json<UserCreateRequest>,
) -> Result<Json<UserOut>, AppError> {
    let existing =
        sqlx::query_scalar::<_, i64>("SELECT COUNT(*)::bigint FROM users WHERE username = $1")
            .bind(&payload.username)
            .fetch_one(&state.db)
            .await
            .map_err(|error| {
                AppError::internal(format!("Failed to check existing user: {error}"))
            })?;

    if existing > 0 {
        return Err(AppError::bad_request("Username already exists"));
    }

    let row = sqlx::query(
        r#"
        INSERT INTO users (username, email, password_hash, is_active, created_at, updated_at)
        VALUES ($1, $2, $3, 'true', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        RETURNING id, username, email, is_active
        "#,
    )
    .bind(&payload.username)
    .bind(payload.email.as_deref())
    .bind(payload.password.as_deref().map(hash_password))
    .fetch_one(&state.db)
    .await
    .map_err(|error| AppError::internal(format!("User registration failed: {error}")))?;

    Ok(Json(row_to_user_out(row)?))
}

pub async fn login_user(
    State(state): State<AppState>,
    Json(payload): Json<UserLoginRequest>,
) -> Result<Json<UserAuthResponse>, AppError> {
    let _ = payload.password;
    let Some(user_row) =
        sqlx::query("SELECT id, username, email, is_active FROM users WHERE username = $1 LIMIT 1")
            .bind(&payload.username)
            .fetch_optional(&state.db)
            .await
            .map_err(|error| AppError::internal(format!("User login failed: {error}")))?
    else {
        return Err(AppError::unauthorized("Invalid credentials"));
    };

    let user = row_to_user_out(user_row)?;
    let session_token = Uuid::new_v4().to_string();
    let expires_at = Utc::now() + chrono::Duration::days(180);

    sqlx::query(
        r#"
        INSERT INTO user_auth_sessions (user_id, session_token, expires_at, created_at)
        VALUES ($1, $2, $3, CURRENT_TIMESTAMP)
        "#,
    )
    .bind(user.id)
    .bind(&session_token)
    .bind(expires_at.naive_utc())
    .execute(&state.db)
    .await
    .map_err(|error| AppError::internal(format!("Failed to create session: {error}")))?;

    Ok(Json(UserAuthResponse {
        user,
        session_token,
        expires_at: expires_at.to_rfc3339(),
    }))
}

pub async fn get_user_profile(
    State(state): State<AppState>,
    Query(query): Query<SessionTokenQuery>,
) -> Result<Json<UserOut>, AppError> {
    let user_id = get_current_user_id(&state, &query.session_token).await?;
    let row = sqlx::query("SELECT id, username, email, is_active FROM users WHERE id = $1 LIMIT 1")
        .bind(user_id)
        .fetch_optional(&state.db)
        .await
        .map_err(|error| AppError::internal(format!("Failed to get user profile: {error}")))?
        .ok_or_else(|| AppError::not_found("User not found"))?;

    Ok(Json(row_to_user_out(row)?))
}

pub async fn update_user_profile(
    State(state): State<AppState>,
    Query(query): Query<SessionTokenQuery>,
    Json(payload): Json<UserUpdateRequest>,
) -> Result<Json<UserOut>, AppError> {
    let user_id = get_current_user_id(&state, &query.session_token).await?;

    if let Some(username) = payload.username.as_deref() {
        let existing = sqlx::query_scalar::<_, i64>(
            "SELECT COUNT(*)::bigint FROM users WHERE username = $1 AND id != $2",
        )
        .bind(username)
        .bind(user_id)
        .fetch_one(&state.db)
        .await
        .map_err(|error| AppError::internal(format!("Failed to check username: {error}")))?;
        if existing > 0 {
            return Err(AppError::bad_request("Username already exists"));
        }
    }

    let current = sqlx::query("SELECT username, email FROM users WHERE id = $1 LIMIT 1")
        .bind(user_id)
        .fetch_optional(&state.db)
        .await
        .map_err(|error| AppError::internal(format!("Failed to update user profile: {error}")))?
        .ok_or_else(|| AppError::not_found("User not found"))?;

    let username = payload
        .username
        .unwrap_or_else(|| current.try_get::<String, _>("username").unwrap_or_default());
    let email = if payload.email.is_some() {
        payload.email
    } else {
        current.try_get::<Option<String>, _>("email").ok().flatten()
    };

    sqlx::query(
        r#"
        UPDATE users
        SET username = $2,
            email = $3,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = $1
        "#,
    )
    .bind(user_id)
    .bind(&username)
    .bind(email.as_deref())
    .execute(&state.db)
    .await
    .map_err(|error| AppError::internal(format!("Failed to update user profile: {error}")))?;

    Ok(Json(UserOut {
        id: user_id,
        username,
        email,
        is_active: true,
    }))
}

pub async fn list_users(State(state): State<AppState>) -> Result<Json<Vec<UserOut>>, AppError> {
    let rows = sqlx::query(
        "SELECT id, username, email, is_active FROM users WHERE is_active = 'true' ORDER BY username",
    )
    .fetch_all(&state.db)
    .await
    .map_err(|error| AppError::internal(format!("Failed to list users: {error}")))?;

    let users = rows
        .into_iter()
        .map(row_to_user_out)
        .collect::<Result<Vec<_>, _>>()?;

    Ok(Json(users))
}

pub async fn set_exchange_config(
    State(state): State<AppState>,
    Json(payload): Json<ExchangeConfigRequest>,
) -> Result<Json<ExchangeConfigResponse>, AppError> {
    validate_exchange(&payload.selected_exchange)?;

    sqlx::query(
        r#"
        INSERT INTO user_exchange_config (user_id, selected_exchange, created_at, updated_at)
        VALUES (1, $1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        ON CONFLICT (user_id)
        DO UPDATE SET selected_exchange = EXCLUDED.selected_exchange, updated_at = CURRENT_TIMESTAMP
        "#,
    )
    .bind(&payload.selected_exchange)
    .execute(&state.db)
    .await
    .map_err(|error| AppError::internal(format!("Failed to set exchange config: {error}")))?;

    Ok(Json(ExchangeConfigResponse {
        selected_exchange: payload.selected_exchange,
        status: Some("success".to_owned()),
    }))
}

pub async fn sync_membership_info(
    State(state): State<AppState>,
    Json(payload): Json<MembershipSyncRequest>,
) -> Result<Json<MembershipSyncResponse>, AppError> {
    let subscription_type = if payload.status.as_deref() == Some("ACTIVE") {
        "premium"
    } else {
        "free"
    };
    let max_sampling_depth = if subscription_type == "premium" {
        60
    } else {
        10
    };
    let expires_at = parse_membership_expiry(payload.current_period_end.as_deref())?;

    let mut tx =
        state.db.begin().await.map_err(|error| {
            AppError::internal(format!("Failed to start membership sync: {error}"))
        })?;

    sqlx::query(
        r#"
        DELETE FROM user_subscriptions
        WHERE user_id IN (SELECT id FROM users WHERE username != 'default')
        "#,
    )
    .execute(&mut *tx)
    .await
    .map_err(|error| AppError::internal(format!("Failed to clear stale memberships: {error}")))?;

    let user_id = sqlx::query_scalar::<_, i32>(
        r#"
        INSERT INTO users (username, email, is_active, created_at, updated_at)
        VALUES ($1, $2, 'true', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        ON CONFLICT (username)
        DO UPDATE SET updated_at = CURRENT_TIMESTAMP
        RETURNING id
        "#,
    )
    .bind(&payload.username)
    .bind(format!("{}@external.user", payload.username))
    .fetch_one(&mut *tx)
    .await
    .map_err(|error| AppError::internal(format!("Failed to upsert membership user: {error}")))?;

    sqlx::query(
        r#"
        INSERT INTO user_subscriptions (
            user_id,
            subscription_type,
            expires_at,
            max_sampling_depth,
            created_at,
            updated_at
        )
        VALUES ($1, $2, $3, $4, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        ON CONFLICT (user_id)
        DO UPDATE SET
            subscription_type = EXCLUDED.subscription_type,
            expires_at = EXCLUDED.expires_at,
            max_sampling_depth = EXCLUDED.max_sampling_depth,
            updated_at = CURRENT_TIMESTAMP
        "#,
    )
    .bind(user_id)
    .bind(subscription_type)
    .bind(expires_at)
    .bind(max_sampling_depth)
    .execute(&mut *tx)
    .await
    .map_err(|error| AppError::internal(format!("Failed to upsert membership: {error}")))?;

    tx.commit().await.map_err(|error| {
        AppError::internal(format!("Failed to commit membership sync: {error}"))
    })?;

    Ok(Json(MembershipSyncResponse {
        status: "success".to_owned(),
        message: format!("Membership synced for {}", payload.username),
        subscription_type: subscription_type.to_owned(),
        max_sampling_depth,
    }))
}

pub async fn clear_membership(
    State(state): State<AppState>,
) -> Result<Json<ClearMembershipResponse>, AppError> {
    let result = sqlx::query(
        r#"
        DELETE FROM user_subscriptions
        WHERE user_id IN (SELECT id FROM users WHERE username != 'default')
        "#,
    )
    .execute(&state.db)
    .await
    .map_err(|error| AppError::internal(format!("Failed to clear membership info: {error}")))?;

    Ok(Json(ClearMembershipResponse {
        status: "success".to_owned(),
        deleted_count: result.rows_affected(),
    }))
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
    .map_err(|error| AppError::internal(format!("Failed to verify session: {error}")))?
    .ok_or_else(|| AppError::unauthorized("Invalid or expired session"))
}

fn row_to_user_out(row: sqlx::postgres::PgRow) -> Result<UserOut, AppError> {
    Ok(UserOut {
        id: row.try_get("id").map_err(read_user_error)?,
        username: row.try_get("username").map_err(read_user_error)?,
        email: row.try_get("email").map_err(read_user_error)?,
        is_active: row
            .try_get::<String, _>("is_active")
            .map_err(read_user_error)?
            == "true",
    })
}

fn hash_password(password: &str) -> String {
    let mut hasher = Sha256::new();
    hasher.update(password.as_bytes());
    format!("{:x}", hasher.finalize())
}

fn read_user_error(error: sqlx::Error) -> AppError {
    AppError::internal(format!("Failed to read user data: {error}"))
}

fn validate_exchange(exchange: &str) -> Result<(), AppError> {
    if matches!(exchange, "hyperliquid" | "binance" | "aster") {
        Ok(())
    } else {
        Err(AppError::bad_request("Invalid exchange selection"))
    }
}

fn parse_membership_expiry(value: Option<&str>) -> Result<Option<NaiveDateTime>, AppError> {
    let Some(value) = value.map(str::trim).filter(|value| !value.is_empty()) else {
        return Ok(None);
    };

    DateTime::parse_from_rfc3339(value)
        .map(|value| Some(value.with_timezone(&Utc).naive_utc()))
        .map_err(|error| AppError::bad_request(format!("Invalid current_period_end: {error}")))
}

#[cfg(test)]
mod tests {
    use axum::http::StatusCode;

    use super::{hash_password, parse_membership_expiry, validate_exchange};

    #[test]
    fn accepts_legacy_exchange_values() {
        assert!(validate_exchange("hyperliquid").is_ok());
        assert!(validate_exchange("binance").is_ok());
        assert!(validate_exchange("aster").is_ok());
    }

    #[test]
    fn rejects_unknown_exchange_values() {
        let error = validate_exchange("coinbase").expect_err("unknown exchange should fail");
        assert_eq!(error.status, StatusCode::BAD_REQUEST);
        assert_eq!(error.message, "Invalid exchange selection");
    }

    #[test]
    fn parses_membership_expiry_to_utc_naive_timestamp() {
        let parsed = parse_membership_expiry(Some("2026-04-14T10:00:00+08:00"))
            .expect("expiry should parse")
            .expect("expiry should be present");
        assert_eq!(parsed.to_string(), "2026-04-14 02:00:00");
    }

    #[test]
    fn accepts_missing_membership_expiry() {
        assert!(
            parse_membership_expiry(None)
                .expect("missing expiry should be accepted")
                .is_none()
        );
    }

    #[test]
    fn password_hash_uses_sha256_hex() {
        assert_eq!(
            hash_password("test"),
            "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08"
        );
    }
}
