use axum::{
    Json,
    extract::{Path, State},
};
use chrono::NaiveDateTime;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use sqlx::Row;

use crate::{error::AppError, state::AppState};

const NOTIFICATION_CONFIG_KEY: &str = "bot_notification_config";

#[derive(Serialize)]
pub struct BotConfigsResponse {
    configs: Vec<BotConfigSummary>,
}

#[derive(Serialize)]
pub struct BotConfigResponse {
    config: Option<BotConfigDetail>,
    configured: bool,
}

#[derive(Serialize)]
pub struct BotConfigSummary {
    id: i32,
    platform: String,
    bot_username: Option<String>,
    status: String,
    has_token: bool,
}

#[derive(Serialize)]
pub struct BotConfigDetail {
    id: i32,
    platform: String,
    bot_username: Option<String>,
    bot_app_id: Option<String>,
    status: String,
    error_message: Option<String>,
    has_token: bool,
    created_at: Option<String>,
    updated_at: Option<String>,
}

#[derive(Debug, Deserialize, Serialize)]
pub struct NotificationConfig {
    #[serde(default = "default_true")]
    ai_trader: bool,
    #[serde(default = "default_true")]
    program_trader: bool,
    #[serde(default)]
    signal_pools: Value,
}

#[derive(Serialize)]
pub struct NotificationConfigResponse {
    config: NotificationConfig,
}

#[derive(Serialize)]
pub struct NotificationConfigUpdateResponse {
    success: bool,
    config: NotificationConfig,
}

pub async fn list_bot_configs(
    State(state): State<AppState>,
) -> Result<Json<BotConfigsResponse>, AppError> {
    let rows = sqlx::query(
        r#"
        SELECT id, platform, bot_username, status, bot_token_encrypted
        FROM bot_configs
        ORDER BY platform
        "#,
    )
    .fetch_all(&state.db)
    .await
    .map_err(|error| AppError::internal(format!("Failed to list bot configs: {error}")))?;

    let configs = rows
        .into_iter()
        .map(|row| {
            Ok(BotConfigSummary {
                id: row.try_get("id").map_err(read_bot_error)?,
                platform: row.try_get("platform").map_err(read_bot_error)?,
                bot_username: row.try_get("bot_username").map_err(read_bot_error)?,
                status: row.try_get("status").map_err(read_bot_error)?,
                has_token: row
                    .try_get::<Option<String>, _>("bot_token_encrypted")
                    .map_err(read_bot_error)?
                    .is_some(),
            })
        })
        .collect::<Result<Vec<_>, AppError>>()?;

    Ok(Json(BotConfigsResponse { configs }))
}

pub async fn get_bot_config(
    State(state): State<AppState>,
    Path(platform): Path<String>,
) -> Result<Json<BotConfigResponse>, AppError> {
    let Some(row) = sqlx::query(
        r#"
        SELECT id, platform, bot_username, bot_app_id, status, error_message,
               bot_token_encrypted, created_at, updated_at
        FROM bot_configs
        WHERE platform = $1
        LIMIT 1
        "#,
    )
    .bind(platform)
    .fetch_optional(&state.db)
    .await
    .map_err(|error| AppError::internal(format!("Failed to get bot config: {error}")))?
    else {
        return Ok(Json(BotConfigResponse {
            config: None,
            configured: false,
        }));
    };

    Ok(Json(BotConfigResponse {
        configured: true,
        config: Some(BotConfigDetail {
            id: row.try_get("id").map_err(read_bot_error)?,
            platform: row.try_get("platform").map_err(read_bot_error)?,
            bot_username: row.try_get("bot_username").map_err(read_bot_error)?,
            bot_app_id: row.try_get("bot_app_id").map_err(read_bot_error)?,
            status: row.try_get("status").map_err(read_bot_error)?,
            error_message: row.try_get("error_message").map_err(read_bot_error)?,
            has_token: row
                .try_get::<Option<String>, _>("bot_token_encrypted")
                .map_err(read_bot_error)?
                .is_some(),
            created_at: row
                .try_get::<Option<NaiveDateTime>, _>("created_at")
                .map_err(read_bot_error)?
                .map(format_naive_iso),
            updated_at: row
                .try_get::<Option<NaiveDateTime>, _>("updated_at")
                .map_err(read_bot_error)?
                .map(format_naive_iso),
        }),
    }))
}

pub async fn get_notification_config(
    State(state): State<AppState>,
) -> Result<Json<NotificationConfigResponse>, AppError> {
    let config = load_notification_config(&state).await?;
    Ok(Json(NotificationConfigResponse { config }))
}

pub async fn update_notification_config(
    State(state): State<AppState>,
    Json(payload): Json<NotificationConfig>,
) -> Result<Json<NotificationConfigUpdateResponse>, AppError> {
    let value = serde_json::to_string(&payload)
        .map_err(|error| AppError::bad_request(format!("Invalid notification config: {error}")))?;

    sqlx::query(
        r#"
        INSERT INTO system_configs (key, value, created_at, updated_at)
        VALUES ($1, $2, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        ON CONFLICT (key)
        DO UPDATE SET value = EXCLUDED.value, updated_at = CURRENT_TIMESTAMP
        "#,
    )
    .bind(NOTIFICATION_CONFIG_KEY)
    .bind(value)
    .execute(&state.db)
    .await
    .map_err(|error| {
        AppError::internal(format!("Failed to update notification config: {error}"))
    })?;

    Ok(Json(NotificationConfigUpdateResponse {
        success: true,
        config: payload,
    }))
}

async fn load_notification_config(state: &AppState) -> Result<NotificationConfig, AppError> {
    let value = sqlx::query_scalar::<_, Option<String>>(
        "SELECT value FROM system_configs WHERE key = $1 LIMIT 1",
    )
    .bind(NOTIFICATION_CONFIG_KEY)
    .fetch_optional(&state.db)
    .await
    .map_err(|error| AppError::internal(format!("Failed to get notification config: {error}")))?;

    let Some(raw) = value.flatten() else {
        return Ok(default_notification_config());
    };

    Ok(serde_json::from_str::<NotificationConfig>(&raw)
        .unwrap_or_else(|_| default_notification_config()))
}

fn default_notification_config() -> NotificationConfig {
    NotificationConfig {
        ai_trader: true,
        program_trader: true,
        signal_pools: json!({}),
    }
}

fn read_bot_error(error: sqlx::Error) -> AppError {
    AppError::internal(format!("Failed to read bot config: {error}"))
}

fn format_naive_iso(value: NaiveDateTime) -> String {
    value.format("%Y-%m-%dT%H:%M:%S%.f").to_string()
}

fn default_true() -> bool {
    true
}

#[cfg(test)]
mod tests {
    use super::default_notification_config;

    #[test]
    fn default_notification_config_matches_legacy_route() {
        let config = default_notification_config();
        assert!(config.ai_trader);
        assert!(config.program_trader);
        assert_eq!(config.signal_pools, serde_json::json!({}));
    }
}
