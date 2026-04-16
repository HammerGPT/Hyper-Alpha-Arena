use axum::{
    Json,
    extract::{Path, State},
};
use serde::{Deserialize, Serialize};
use sqlx::{FromRow, PgPool};
use tracing::warn;

use crate::{error::AppError, state::AppState};

#[derive(Serialize)]
pub struct CheckRequiredResponse {
    has_required_configs: bool,
    missing_configs: Vec<String>,
}

#[derive(Debug, Serialize, FromRow)]
pub struct GlobalSamplingResponse {
    sampling_interval: i32,
    sampling_depth: i32,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct GlobalSamplingUpdate {
    sampling_interval: Option<i32>,
    sampling_depth: Option<i32>,
}

#[derive(Debug, Deserialize)]
pub struct ConfigValueRequest {
    value: String,
}

#[derive(Serialize)]
pub struct ConfigValueResponse {
    success: bool,
    key: String,
    value: String,
}

pub async fn check_required_configs() -> Json<CheckRequiredResponse> {
    Json(CheckRequiredResponse {
        has_required_configs: true,
        missing_configs: Vec::new(),
    })
}

pub async fn get_global_sampling_config(
    State(state): State<AppState>,
) -> Result<Json<GlobalSamplingResponse>, AppError> {
    let config = get_or_create_global_sampling(&state.db).await?;
    Ok(Json(config))
}

pub async fn update_global_sampling_config(
    State(state): State<AppState>,
    Json(payload): Json<GlobalSamplingUpdate>,
) -> Result<Json<GlobalSamplingResponse>, AppError> {
    validate_global_sampling_update(&payload)?;

    let config = upsert_global_sampling(&state.db, payload.clone()).await?;
    sync_legacy_sampling_pool(&state, &payload).await;

    Ok(Json(config))
}

pub async fn update_system_config(
    State(state): State<AppState>,
    Path(key): Path<String>,
    Json(payload): Json<ConfigValueRequest>,
) -> Result<Json<ConfigValueResponse>, AppError> {
    sqlx::query(
        r#"
        INSERT INTO system_configs (key, value, created_at, updated_at)
        VALUES ($1, $2, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        ON CONFLICT (key)
        DO UPDATE SET value = EXCLUDED.value, updated_at = CURRENT_TIMESTAMP
        "#,
    )
    .bind(&key)
    .bind(&payload.value)
    .execute(&state.db)
    .await
    .map_err(|error| AppError::internal(format!("Failed to update system config: {error}")))?;

    Ok(Json(ConfigValueResponse {
        success: true,
        key,
        value: payload.value,
    }))
}

async fn get_or_create_global_sampling(pool: &PgPool) -> Result<GlobalSamplingResponse, AppError> {
    if let Some(config) = sqlx::query_as::<_, GlobalSamplingResponse>(
        r#"
        SELECT sampling_interval, sampling_depth
        FROM global_sampling_configs
        ORDER BY id
        LIMIT 1
        "#,
    )
    .fetch_optional(pool)
    .await
    .map_err(|error| AppError::internal(format!("Failed to get global sampling config: {error}")))?
    {
        return Ok(config);
    }

    sqlx::query_as::<_, GlobalSamplingResponse>(
        r#"
        INSERT INTO global_sampling_configs (sampling_interval, sampling_depth, created_at, updated_at)
        VALUES (18, 10, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        RETURNING sampling_interval, sampling_depth
        "#,
    )
    .fetch_one(pool)
    .await
    .map_err(|error| AppError::internal(format!("Failed to create global sampling config: {error}")))
}

async fn upsert_global_sampling(
    pool: &PgPool,
    payload: GlobalSamplingUpdate,
) -> Result<GlobalSamplingResponse, AppError> {
    let current = get_or_create_global_sampling(pool).await?;
    let next_interval = payload
        .sampling_interval
        .unwrap_or(current.sampling_interval);
    let next_depth = payload.sampling_depth.unwrap_or(current.sampling_depth);

    sqlx::query_as::<_, GlobalSamplingResponse>(
        r#"
        UPDATE global_sampling_configs
        SET sampling_interval = $1, sampling_depth = $2, updated_at = CURRENT_TIMESTAMP
        WHERE id = (
            SELECT id
            FROM global_sampling_configs
            ORDER BY id
            LIMIT 1
        )
        RETURNING sampling_interval, sampling_depth
        "#,
    )
    .bind(next_interval)
    .bind(next_depth)
    .fetch_one(pool)
    .await
    .map_err(|error| {
        AppError::internal(format!("Failed to update global sampling config: {error}"))
    })
}

fn validate_global_sampling_update(payload: &GlobalSamplingUpdate) -> Result<(), AppError> {
    if let Some(interval) = payload.sampling_interval {
        if !(5..=60).contains(&interval) {
            return Err(AppError::bad_request(
                "sampling_interval must be between 5 and 60 seconds",
            ));
        }
    }

    if let Some(depth) = payload.sampling_depth {
        if !(10..=60).contains(&depth) {
            return Err(AppError::bad_request(
                "sampling_depth must be between 10 and 60",
            ));
        }
    }

    Ok(())
}

async fn sync_legacy_sampling_pool(state: &AppState, payload: &GlobalSamplingUpdate) {
    let target = state
        .config
        .legacy_http_target("/api/config/global-sampling");
    match state.client.put(target).json(payload).send().await {
        Ok(response) if response.status().is_success() => {}
        Ok(response) => {
            warn!(
                target = "backend_rust::config_routes",
                status = %response.status(),
                "legacy global sampling sync returned non-success status"
            );
        }
        Err(error) => {
            warn!(
                target = "backend_rust::config_routes",
                %error,
                "legacy global sampling sync failed"
            );
        }
    }
}

#[cfg(test)]
mod tests {
    use axum::http::StatusCode;

    use super::{GlobalSamplingUpdate, validate_global_sampling_update};

    #[test]
    fn accepts_valid_sampling_update() {
        let update = GlobalSamplingUpdate {
            sampling_interval: Some(18),
            sampling_depth: Some(20),
        };

        assert!(validate_global_sampling_update(&update).is_ok());
    }

    #[test]
    fn rejects_out_of_range_sampling_interval() {
        let update = GlobalSamplingUpdate {
            sampling_interval: Some(4),
            sampling_depth: None,
        };

        let error = validate_global_sampling_update(&update).expect_err("interval should fail");
        assert_eq!(error.status, StatusCode::BAD_REQUEST);
        assert_eq!(
            error.message,
            "sampling_interval must be between 5 and 60 seconds"
        );
    }

    #[test]
    fn rejects_out_of_range_sampling_depth() {
        let update = GlobalSamplingUpdate {
            sampling_interval: None,
            sampling_depth: Some(61),
        };

        let error = validate_global_sampling_update(&update).expect_err("depth should fail");
        assert_eq!(error.status, StatusCode::BAD_REQUEST);
        assert_eq!(error.message, "sampling_depth must be between 10 and 60");
    }
}
