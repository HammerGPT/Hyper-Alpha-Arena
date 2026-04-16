use axum::{
    Json,
    extract::{Path, State},
};
use serde::{Deserialize, Serialize};
use sqlx::FromRow;

use crate::{error::AppError, state::AppState};

#[derive(Debug, Serialize, FromRow)]
pub struct RegimeConfigResponse {
    id: i32,
    name: String,
    is_default: bool,
    rolling_window: i32,
    breakout_cvd_z: f64,
    breakout_oi_z: f64,
    breakout_price_atr: f64,
    breakout_taker_high: f64,
    breakout_taker_low: f64,
    breakout_body_ratio: f64,
    absorption_cvd_z: f64,
    absorption_price_atr: f64,
    trap_cvd_z: f64,
    trap_oi_z: f64,
    exhaustion_cvd_z: f64,
    exhaustion_rsi_high: f64,
    exhaustion_rsi_low: f64,
    stop_hunt_range_atr: f64,
    stop_hunt_close_atr: f64,
    noise_cvd_z: f64,
    continuation_cvd_divisor: f64,
}

#[derive(Debug, Deserialize)]
pub struct RegimeConfigUpdateRequest {
    rolling_window: Option<i32>,
    breakout_cvd_z: Option<f64>,
    breakout_oi_z: Option<f64>,
    breakout_price_atr: Option<f64>,
    breakout_taker_high: Option<f64>,
    breakout_taker_low: Option<f64>,
    breakout_body_ratio: Option<f64>,
    absorption_cvd_z: Option<f64>,
    absorption_price_atr: Option<f64>,
    trap_cvd_z: Option<f64>,
    trap_oi_z: Option<f64>,
    exhaustion_cvd_z: Option<f64>,
    exhaustion_rsi_high: Option<f64>,
    exhaustion_rsi_low: Option<f64>,
    stop_hunt_range_atr: Option<f64>,
    stop_hunt_close_atr: Option<f64>,
    noise_cvd_z: Option<f64>,
    continuation_cvd_divisor: Option<f64>,
}

pub async fn list_regime_configs(
    State(state): State<AppState>,
) -> Result<Json<Vec<RegimeConfigResponse>>, AppError> {
    let configs = sqlx::query_as::<_, RegimeConfigResponse>(regime_config_select_sql())
        .fetch_all(&state.db)
        .await
        .map_err(|error| AppError::internal(format!("Failed to list configs: {error}")))?;

    Ok(Json(configs))
}

pub async fn update_regime_config(
    State(state): State<AppState>,
    Path(config_id): Path<i32>,
    Json(payload): Json<RegimeConfigUpdateRequest>,
) -> Result<Json<RegimeConfigResponse>, AppError> {
    let result = sqlx::query(
        r#"
        UPDATE market_regime_configs
        SET
            rolling_window = COALESCE($2, rolling_window),
            breakout_cvd_z = COALESCE($3, breakout_cvd_z),
            breakout_oi_z = COALESCE($4, breakout_oi_z),
            breakout_price_atr = COALESCE($5, breakout_price_atr),
            breakout_taker_high = COALESCE($6, breakout_taker_high),
            breakout_taker_low = COALESCE($7, breakout_taker_low),
            breakout_body_ratio = COALESCE($8, breakout_body_ratio),
            absorption_cvd_z = COALESCE($9, absorption_cvd_z),
            absorption_price_atr = COALESCE($10, absorption_price_atr),
            trap_cvd_z = COALESCE($11, trap_cvd_z),
            trap_oi_z = COALESCE($12, trap_oi_z),
            exhaustion_cvd_z = COALESCE($13, exhaustion_cvd_z),
            exhaustion_rsi_high = COALESCE($14, exhaustion_rsi_high),
            exhaustion_rsi_low = COALESCE($15, exhaustion_rsi_low),
            stop_hunt_range_atr = COALESCE($16, stop_hunt_range_atr),
            stop_hunt_close_atr = COALESCE($17, stop_hunt_close_atr),
            noise_cvd_z = COALESCE($18, noise_cvd_z),
            continuation_cvd_divisor = COALESCE($19, continuation_cvd_divisor),
            updated_at = CURRENT_TIMESTAMP
        WHERE id = $1
        "#,
    )
    .bind(config_id)
    .bind(payload.rolling_window)
    .bind(payload.breakout_cvd_z)
    .bind(payload.breakout_oi_z)
    .bind(payload.breakout_price_atr)
    .bind(payload.breakout_taker_high)
    .bind(payload.breakout_taker_low)
    .bind(payload.breakout_body_ratio)
    .bind(payload.absorption_cvd_z)
    .bind(payload.absorption_price_atr)
    .bind(payload.trap_cvd_z)
    .bind(payload.trap_oi_z)
    .bind(payload.exhaustion_cvd_z)
    .bind(payload.exhaustion_rsi_high)
    .bind(payload.exhaustion_rsi_low)
    .bind(payload.stop_hunt_range_atr)
    .bind(payload.stop_hunt_close_atr)
    .bind(payload.noise_cvd_z)
    .bind(payload.continuation_cvd_divisor)
    .execute(&state.db)
    .await
    .map_err(|error| AppError::internal(format!("Failed to update config: {error}")))?;

    if result.rows_affected() == 0 {
        return Err(AppError::not_found(format!("Config {config_id} not found")));
    }

    let config = sqlx::query_as::<_, RegimeConfigResponse>(&format!(
        "{} WHERE id = $1",
        regime_config_select_sql()
    ))
    .bind(config_id)
    .fetch_one(&state.db)
    .await
    .map_err(|error| AppError::internal(format!("Failed to load updated config: {error}")))?;

    Ok(Json(config))
}

fn regime_config_select_sql() -> &'static str {
    r#"
    SELECT
        id,
        name,
        COALESCE(is_default, false) AS is_default,
        COALESCE(rolling_window, 48) AS rolling_window,
        COALESCE(breakout_cvd_z, 1.5) AS breakout_cvd_z,
        COALESCE(breakout_oi_z, 1.0) AS breakout_oi_z,
        COALESCE(breakout_price_atr, 0.5) AS breakout_price_atr,
        COALESCE(breakout_taker_high, 1.8) AS breakout_taker_high,
        COALESCE(breakout_taker_low, 0.55) AS breakout_taker_low,
        COALESCE(breakout_body_ratio, 0.4) AS breakout_body_ratio,
        COALESCE(absorption_cvd_z, 1.5) AS absorption_cvd_z,
        COALESCE(absorption_price_atr, 0.3) AS absorption_price_atr,
        COALESCE(trap_cvd_z, 1.0) AS trap_cvd_z,
        COALESCE(trap_oi_z, -1.0) AS trap_oi_z,
        COALESCE(exhaustion_cvd_z, 1.0) AS exhaustion_cvd_z,
        COALESCE(exhaustion_rsi_high, 70.0) AS exhaustion_rsi_high,
        COALESCE(exhaustion_rsi_low, 30.0) AS exhaustion_rsi_low,
        COALESCE(stop_hunt_range_atr, 1.0) AS stop_hunt_range_atr,
        COALESCE(stop_hunt_close_atr, 0.3) AS stop_hunt_close_atr,
        COALESCE(noise_cvd_z, 0.5) AS noise_cvd_z,
        COALESCE(continuation_cvd_divisor, 3.0) AS continuation_cvd_divisor
    FROM market_regime_configs
    "#
}

#[cfg(test)]
mod tests {
    use super::regime_config_select_sql;

    #[test]
    fn regime_config_select_applies_legacy_defaults() {
        let sql = regime_config_select_sql();
        assert!(sql.contains("COALESCE(rolling_window, 48)"));
        assert!(sql.contains("COALESCE(continuation_cvd_divisor, 3.0)"));
    }
}
