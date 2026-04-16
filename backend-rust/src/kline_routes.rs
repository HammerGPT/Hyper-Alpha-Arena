use axum::{
    Json,
    body::Bytes,
    extract::{Path, Query, State},
    http::{HeaderMap, Method},
    response::Response,
};
use chrono::{DateTime, Duration, NaiveDateTime};
use serde::{Deserialize, Serialize};
use sqlx::Row;

use crate::{
    error::AppError,
    proxy::{build_downstream_streaming_response, build_upstream_request},
    state::AppState,
};

#[derive(Serialize)]
pub struct SimpleBackfillTasksResponse {
    tasks: Vec<SimpleBackfillTask>,
}

#[derive(Serialize)]
pub struct SimpleBackfillTask {
    task_id: i32,
    symbol: String,
    status: String,
    progress: i32,
    total_records: i32,
    collected_records: i32,
}

#[derive(Serialize)]
pub struct KlineDataPlaceholderResponse {
    success: bool,
    data: Vec<serde_json::Value>,
    message: &'static str,
}

#[derive(Serialize)]
pub struct BackfillTaskResponse {
    task_id: i32,
    exchange: String,
    symbol: String,
    start_time: String,
    end_time: String,
    period: String,
    status: String,
    progress: i32,
    total_records: i32,
    collected_records: i32,
    error_message: Option<String>,
    created_at: String,
}

#[derive(Deserialize)]
pub struct ListBackfillTasksQuery {
    status: Option<String>,
    #[serde(default = "default_task_limit")]
    limit: i64,
}

#[derive(Deserialize)]
struct CreateBackfillTaskRequest {
    #[serde(default)]
    exchange: Option<String>,
    symbols: Vec<String>,
    start_time: String,
    end_time: String,
    #[serde(default)]
    period: Option<String>,
}

pub async fn get_backfill_tasks(
    State(state): State<AppState>,
) -> Json<SimpleBackfillTasksResponse> {
    let tasks = match sqlx::query(
        r#"
        SELECT id, symbol, status, progress, total_records, collected_records
        FROM kline_collection_tasks
        ORDER BY created_at DESC
        LIMIT 50
        "#,
    )
    .fetch_all(&state.db)
    .await
    {
        Ok(rows) => rows
            .into_iter()
            .filter_map(|row| row_to_simple_task(row).ok())
            .collect(),
        Err(_) => Vec::new(),
    };

    Json(SimpleBackfillTasksResponse { tasks })
}

pub async fn get_kline_data_placeholder() -> Json<KlineDataPlaceholderResponse> {
    Json(KlineDataPlaceholderResponse {
        success: false,
        data: Vec::new(),
        message: "K-line data service not implemented yet",
    })
}

pub async fn create_backfill_task(
    State(state): State<AppState>,
    headers: HeaderMap,
    body: Bytes,
) -> Result<Response, AppError> {
    validate_create_backfill_task_payload(&body)?;

    let target_url = state.config.legacy_http_target("/api/klines/backfill");
    let upstream_request =
        build_upstream_request(&state.client, Method::POST, &headers, target_url, body)?;
    let upstream_response = upstream_request.send().await.map_err(|error| {
        AppError::bad_gateway(format!("legacy kline backfill request failed: {error}"))
    })?;

    build_downstream_streaming_response(upstream_response)
}

pub async fn delete_backfill_task(
    State(state): State<AppState>,
    headers: HeaderMap,
    Path(task_id): Path<String>,
) -> Result<Response, AppError> {
    let task_id = parse_backfill_task_id(&task_id)?;
    let target_url = state
        .config
        .legacy_http_target(&format!("/api/klines/backfill-tasks/{task_id}"));
    let upstream_request = build_upstream_request(
        &state.client,
        Method::DELETE,
        &headers,
        target_url,
        Bytes::new(),
    )?;
    let upstream_response = upstream_request.send().await.map_err(|error| {
        AppError::bad_gateway(format!(
            "legacy kline backfill delete request failed: {error}"
        ))
    })?;

    build_downstream_streaming_response(upstream_response)
}

pub async fn get_backfill_status(
    State(state): State<AppState>,
    Path(task_id): Path<i32>,
) -> Result<Json<BackfillTaskResponse>, AppError> {
    let task = load_backfill_task(&state, task_id).await?;
    Ok(Json(task))
}

pub async fn list_backfill_tasks(
    State(state): State<AppState>,
    Query(query): Query<ListBackfillTasksQuery>,
) -> Result<Json<Vec<BackfillTaskResponse>>, AppError> {
    let rows = sqlx::query(
        r#"
        SELECT id, exchange, symbol, start_time, end_time, period, status, progress,
               total_records, collected_records, error_message, created_at
        FROM kline_collection_tasks
        WHERE ($1::text IS NULL OR status = $1)
        ORDER BY created_at DESC
        LIMIT $2
        "#,
    )
    .bind(query.status.as_deref())
    .bind(query.limit)
    .fetch_all(&state.db)
    .await
    .map_err(|error| AppError::internal(format!("Failed to list tasks: {error}")))?;

    let tasks = rows
        .into_iter()
        .map(row_to_backfill_task)
        .collect::<Result<Vec<_>, _>>()?;

    Ok(Json(tasks))
}

async fn load_backfill_task(
    state: &AppState,
    task_id: i32,
) -> Result<BackfillTaskResponse, AppError> {
    let Some(row) = sqlx::query(
        r#"
        SELECT id, exchange, symbol, start_time, end_time, period, status, progress,
               total_records, collected_records, error_message, created_at
        FROM kline_collection_tasks
        WHERE id = $1
        "#,
    )
    .bind(task_id)
    .fetch_optional(&state.db)
    .await
    .map_err(|error| AppError::internal(format!("Failed to get task status: {error}")))?
    else {
        return Err(AppError::not_found("Task not found"));
    };

    row_to_backfill_task(row)
}

fn row_to_simple_task(row: sqlx::postgres::PgRow) -> Result<SimpleBackfillTask, AppError> {
    Ok(SimpleBackfillTask {
        task_id: row.try_get("id").map_err(read_kline_error)?,
        symbol: row.try_get("symbol").map_err(read_kline_error)?,
        status: row.try_get("status").map_err(read_kline_error)?,
        progress: row.try_get("progress").map_err(read_kline_error)?,
        total_records: row
            .try_get::<Option<i32>, _>("total_records")
            .map_err(read_kline_error)?
            .unwrap_or(0),
        collected_records: row
            .try_get::<Option<i32>, _>("collected_records")
            .map_err(read_kline_error)?
            .unwrap_or(0),
    })
}

fn row_to_backfill_task(row: sqlx::postgres::PgRow) -> Result<BackfillTaskResponse, AppError> {
    Ok(BackfillTaskResponse {
        task_id: row.try_get("id").map_err(read_kline_error)?,
        exchange: row.try_get("exchange").map_err(read_kline_error)?,
        symbol: row.try_get("symbol").map_err(read_kline_error)?,
        start_time: format_naive_iso(row.try_get("start_time").map_err(read_kline_error)?),
        end_time: format_naive_iso(row.try_get("end_time").map_err(read_kline_error)?),
        period: row.try_get("period").map_err(read_kline_error)?,
        status: row.try_get("status").map_err(read_kline_error)?,
        progress: row.try_get("progress").map_err(read_kline_error)?,
        total_records: row
            .try_get::<Option<i32>, _>("total_records")
            .map_err(read_kline_error)?
            .unwrap_or(0),
        collected_records: row
            .try_get::<Option<i32>, _>("collected_records")
            .map_err(read_kline_error)?
            .unwrap_or(0),
        error_message: row.try_get("error_message").map_err(read_kline_error)?,
        created_at: format_naive_iso(row.try_get("created_at").map_err(read_kline_error)?),
    })
}

fn read_kline_error(error: sqlx::Error) -> AppError {
    AppError::internal(format!("Failed to read kline task data: {error}"))
}

fn format_naive_iso(value: NaiveDateTime) -> String {
    value.format("%Y-%m-%dT%H:%M:%S%.f").to_string()
}

fn default_task_limit() -> i64 {
    50
}

fn parse_backfill_task_id(task_id: &str) -> Result<i32, AppError> {
    task_id
        .parse::<i32>()
        .map_err(|_| AppError::bad_request("task_id path parameter must be a valid integer"))
}

fn validate_create_backfill_task_payload(body: &Bytes) -> Result<(), AppError> {
    let request: CreateBackfillTaskRequest = serde_json::from_slice(body).map_err(|error| {
        AppError::bad_request(format!("invalid kline backfill payload: {error}"))
    })?;

    if request.symbols.is_empty() {
        return Err(AppError::bad_request(
            "symbols must contain at least one symbol",
        ));
    }

    if request
        .symbols
        .iter()
        .any(|symbol| symbol.trim().is_empty())
    {
        return Err(AppError::bad_request(
            "symbols must not contain empty entries",
        ));
    }

    if request
        .exchange
        .as_deref()
        .is_some_and(|exchange| exchange.trim().is_empty())
    {
        return Err(AppError::bad_request(
            "exchange must be a non-empty string when provided",
        ));
    }

    if request
        .period
        .as_deref()
        .is_some_and(|period| period.trim().is_empty())
    {
        return Err(AppError::bad_request(
            "period must be a non-empty string when provided",
        ));
    }

    let start_time = parse_backfill_datetime(&request.start_time, "start_time")?;
    let end_time = parse_backfill_datetime(&request.end_time, "end_time")?;

    if start_time >= end_time {
        return Err(AppError::bad_request("start_time must be before end_time"));
    }

    if end_time.signed_duration_since(start_time) > Duration::days(30) {
        return Err(AppError::bad_request(
            "Time range too large. Maximum 30 days allowed.",
        ));
    }

    Ok(())
}

fn parse_backfill_datetime(value: &str, field_name: &str) -> Result<NaiveDateTime, AppError> {
    if let Ok(parsed) = DateTime::parse_from_rfc3339(value) {
        return Ok(parsed.naive_utc());
    }

    for format in ["%Y-%m-%dT%H:%M:%S%.f", "%Y-%m-%d %H:%M:%S%.f"] {
        if let Ok(parsed) = NaiveDateTime::parse_from_str(value, format) {
            return Ok(parsed);
        }
    }

    Err(AppError::bad_request(format!(
        "{field_name} must be a valid ISO-8601 datetime"
    )))
}

#[cfg(test)]
mod tests {
    use chrono::NaiveDate;
    use serde_json::json;

    use super::{
        default_task_limit, format_naive_iso, parse_backfill_datetime, parse_backfill_task_id,
        validate_create_backfill_task_payload,
    };

    #[test]
    fn default_task_limit_matches_legacy_route() {
        assert_eq!(default_task_limit(), 50);
    }

    #[test]
    fn formats_kline_task_timestamps_as_iso_strings() {
        let value = NaiveDate::from_ymd_opt(2026, 4, 14)
            .expect("date should be valid")
            .and_hms_opt(11, 12, 13)
            .expect("time should be valid");
        assert_eq!(format_naive_iso(value), "2026-04-14T11:12:13");
    }

    #[test]
    fn parses_backfill_datetime_with_timezone_or_naive_formats() {
        let with_timezone = parse_backfill_datetime("2026-04-16T01:02:03Z", "start_time")
            .expect("zulu timestamp should parse");
        assert_eq!(
            with_timezone,
            NaiveDate::from_ymd_opt(2026, 4, 16)
                .expect("date should be valid")
                .and_hms_opt(1, 2, 3)
                .expect("time should be valid")
        );

        let naive = parse_backfill_datetime("2026-04-16T01:02:03.123", "start_time")
            .expect("naive timestamp should parse");
        assert_eq!(
            naive,
            NaiveDate::from_ymd_opt(2026, 4, 16)
                .expect("date should be valid")
                .and_hms_milli_opt(1, 2, 3, 123)
                .expect("time should be valid")
        );
    }

    #[test]
    fn validates_backfill_payload_time_window_like_legacy_route() {
        let too_large_range = json!({
            "symbols": ["BTC"],
            "start_time": "2026-01-01T00:00:00",
            "end_time": "2026-02-01T00:00:01",
            "period": "1m"
        });
        let error = validate_create_backfill_task_payload(
            &serde_json::to_vec(&too_large_range)
                .expect("payload should serialize")
                .into(),
        )
        .expect_err("payload over 30 days should be rejected");
        assert_eq!(
            error.message,
            "Time range too large. Maximum 30 days allowed."
        );
    }

    #[test]
    fn validates_backfill_task_id_path_contract() {
        assert_eq!(
            parse_backfill_task_id("42").expect("task id should parse"),
            42
        );

        let error =
            parse_backfill_task_id("invalid-task-id").expect_err("invalid task id should fail");
        assert_eq!(
            error.message,
            "task_id path parameter must be a valid integer"
        );
    }
}
