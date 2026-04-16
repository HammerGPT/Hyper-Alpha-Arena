use axum::{
    Json,
    body::Bytes,
    extract::{Path, Query, State},
    http::{HeaderMap, Method},
    response::Response,
};
use chrono::NaiveDateTime;
use serde::{Deserialize, Serialize};
use sqlx::Row;

use crate::{
    error::AppError,
    proxy::{build_downstream_streaming_response, build_upstream_request},
    state::AppState,
};

#[derive(Deserialize)]
pub struct ListTasksQuery {
    account_id: Option<i32>,
    #[serde(default = "default_task_limit")]
    limit: i64,
}

#[derive(Serialize)]
pub struct TaskListResponse {
    tasks: Vec<TaskStatusResponse>,
}

#[derive(Clone, Serialize)]
pub struct TaskStatusResponse {
    id: i32,
    account_id: i32,
    name: Option<String>,
    status: String,
    total_count: i32,
    completed_count: i32,
    failed_count: i32,
    created_at: String,
    started_at: Option<String>,
    finished_at: Option<String>,
}

#[derive(Serialize)]
pub struct ResultsResponse {
    task: TaskStatusResponse,
    items: Vec<ResultItemResponse>,
    summary: ResultSummary,
}

#[derive(Clone, Serialize)]
pub struct ResultItemResponse {
    id: i32,
    original_decision_time: Option<String>,
    original_operation: Option<String>,
    original_symbol: Option<String>,
    original_target_portion: Option<f64>,
    original_realized_pnl: Option<f64>,
    new_operation: Option<String>,
    new_symbol: Option<String>,
    new_target_portion: Option<f64>,
    decision_changed: Option<bool>,
    change_type: Option<String>,
    status: String,
}

#[derive(Serialize)]
pub struct ResultSummary {
    total: usize,
    completed: usize,
    failed: usize,
    changed: usize,
    unchanged: usize,
    avoided_loss_count: i32,
    avoided_loss_amount: f64,
    missed_profit_count: i32,
    missed_profit_amount: f64,
}

#[derive(Serialize)]
pub struct ItemDetailResponse {
    id: i32,
    original_operation: Option<String>,
    original_symbol: Option<String>,
    original_reasoning: Option<String>,
    original_decision_json: Option<String>,
    original_prompt_template_name: Option<String>,
    modified_prompt: Option<String>,
    new_operation: Option<String>,
    new_symbol: Option<String>,
    new_reasoning: Option<String>,
    new_decision_json: Option<String>,
    decision_changed: Option<bool>,
    change_type: Option<String>,
    error_message: Option<String>,
}

#[derive(Serialize)]
pub struct TaskItemsImportResponse {
    task_id: i32,
    task_name: Option<String>,
    items: Vec<TaskImportItem>,
}

#[derive(Serialize)]
pub struct TaskImportItem {
    id: i32,
    modified_prompt: Option<String>,
    operation: Option<String>,
    symbol: Option<String>,
    reason: Option<String>,
    decision_time: Option<String>,
    realized_pnl: Option<f64>,
}

#[derive(Debug, Deserialize, Serialize)]
struct CreateTaskRequest {
    account_id: i32,
    #[serde(default)]
    name: Option<String>,
    items: Vec<BacktestItemInput>,
    #[serde(default)]
    replace_rules: Option<Vec<ReplaceRule>>,
}

#[derive(Debug, Deserialize, Serialize)]
struct BacktestItemInput {
    decision_log_id: i32,
    modified_prompt: String,
}

#[derive(Debug, Deserialize, Serialize)]
struct ReplaceRule {
    find: String,
    replace: String,
}

pub async fn create_backtest_task(
    State(state): State<AppState>,
    headers: HeaderMap,
    body: Bytes,
) -> Result<Response, AppError> {
    let payload = parse_create_task_payload(&body)?;
    let request_body = serde_json::to_vec(&payload).map_err(|error| {
        AppError::internal(format!(
            "Failed to encode prompt backtest create payload: {error}"
        ))
    })?;

    let target_url = state
        .config
        .legacy_http_target("/api/prompt-backtest/tasks");
    let upstream_request = build_upstream_request(
        &state.client,
        Method::POST,
        &headers,
        target_url,
        request_body.into(),
    )?;
    let upstream_response = upstream_request.send().await.map_err(|error| {
        AppError::bad_gateway(format!(
            "legacy prompt backtest task create request failed: {error}"
        ))
    })?;

    build_downstream_streaming_response(upstream_response)
}

pub async fn delete_backtest_task(
    State(state): State<AppState>,
    headers: HeaderMap,
    Path(task_id): Path<String>,
) -> Result<Response, AppError> {
    let task_id = parse_prompt_backtest_task_id(&task_id)?;
    let target_url = state
        .config
        .legacy_http_target(&format!("/api/prompt-backtest/tasks/{task_id}"));
    let upstream_request = build_upstream_request(
        &state.client,
        Method::DELETE,
        &headers,
        target_url,
        Bytes::new(),
    )?;
    let upstream_response = upstream_request.send().await.map_err(|error| {
        AppError::bad_gateway(format!(
            "legacy prompt backtest task delete request failed: {error}"
        ))
    })?;

    build_downstream_streaming_response(upstream_response)
}

pub async fn retry_backtest_task(
    State(state): State<AppState>,
    headers: HeaderMap,
    Path(task_id): Path<String>,
) -> Result<Response, AppError> {
    let task_id = parse_prompt_backtest_task_id(&task_id)?;
    let target_url = state
        .config
        .legacy_http_target(&format!("/api/prompt-backtest/tasks/{task_id}/retry"));
    let upstream_request = build_upstream_request(
        &state.client,
        Method::POST,
        &headers,
        target_url,
        Bytes::new(),
    )?;
    let upstream_response = upstream_request.send().await.map_err(|error| {
        AppError::bad_gateway(format!(
            "legacy prompt backtest task retry request failed: {error}"
        ))
    })?;

    build_downstream_streaming_response(upstream_response)
}

pub async fn list_backtest_tasks(
    State(state): State<AppState>,
    Query(query): Query<ListTasksQuery>,
) -> Result<Json<TaskListResponse>, AppError> {
    let rows = sqlx::query(
        r#"
        SELECT id, account_id, name, status, total_count, completed_count, failed_count,
               created_at, started_at, finished_at
        FROM prompt_backtest_tasks
        WHERE ($1::int4 IS NULL OR account_id = $1)
        ORDER BY created_at DESC
        LIMIT $2
        "#,
    )
    .bind(query.account_id)
    .bind(query.limit)
    .fetch_all(&state.db)
    .await
    .map_err(|error| {
        AppError::internal(format!("Failed to list prompt backtest tasks: {error}"))
    })?;

    let tasks = rows
        .into_iter()
        .map(row_to_task)
        .collect::<Result<Vec<_>, _>>()?;

    Ok(Json(TaskListResponse { tasks }))
}

pub async fn get_task_status(
    State(state): State<AppState>,
    Path(task_id): Path<i32>,
) -> Result<Json<TaskStatusResponse>, AppError> {
    let task = load_task(&state, task_id).await?;
    Ok(Json(task))
}

pub async fn get_task_results(
    State(state): State<AppState>,
    Path(task_id): Path<i32>,
) -> Result<Json<ResultsResponse>, AppError> {
    let task = load_task(&state, task_id).await?;
    let rows = sqlx::query(
        r#"
        SELECT
            id,
            original_decision_time,
            original_operation,
            original_symbol,
            original_target_portion::float8 AS original_target_portion,
            original_realized_pnl::float8 AS original_realized_pnl,
            new_operation,
            new_symbol,
            new_target_portion::float8 AS new_target_portion,
            decision_changed,
            change_type,
            status
        FROM prompt_backtest_items
        WHERE task_id = $1
        ORDER BY original_decision_time DESC
        "#,
    )
    .bind(task_id)
    .fetch_all(&state.db)
    .await
    .map_err(|error| {
        AppError::internal(format!("Failed to get prompt backtest results: {error}"))
    })?;

    let items = rows
        .into_iter()
        .map(row_to_result_item)
        .collect::<Result<Vec<_>, _>>()?;
    let summary = summarize_results(&items);

    Ok(Json(ResultsResponse {
        task,
        items,
        summary,
    }))
}

pub async fn get_item_detail(
    State(state): State<AppState>,
    Path(item_id): Path<i32>,
) -> Result<Json<ItemDetailResponse>, AppError> {
    let Some(row) = sqlx::query(
        r#"
        SELECT
            id,
            original_operation,
            original_symbol,
            original_reasoning,
            original_decision_json,
            original_prompt_template_name,
            modified_prompt,
            new_operation,
            new_symbol,
            new_reasoning,
            new_decision_json,
            decision_changed,
            change_type,
            error_message
        FROM prompt_backtest_items
        WHERE id = $1
        "#,
    )
    .bind(item_id)
    .fetch_optional(&state.db)
    .await
    .map_err(|error| AppError::internal(format!("Failed to get prompt backtest item: {error}")))?
    else {
        return Err(AppError::not_found("Item not found"));
    };

    Ok(Json(ItemDetailResponse {
        id: row.try_get("id").map_err(read_prompt_backtest_error)?,
        original_operation: row
            .try_get("original_operation")
            .map_err(read_prompt_backtest_error)?,
        original_symbol: row
            .try_get("original_symbol")
            .map_err(read_prompt_backtest_error)?,
        original_reasoning: row
            .try_get("original_reasoning")
            .map_err(read_prompt_backtest_error)?,
        original_decision_json: row
            .try_get("original_decision_json")
            .map_err(read_prompt_backtest_error)?,
        original_prompt_template_name: row
            .try_get("original_prompt_template_name")
            .map_err(read_prompt_backtest_error)?,
        modified_prompt: row
            .try_get("modified_prompt")
            .map_err(read_prompt_backtest_error)?,
        new_operation: row
            .try_get("new_operation")
            .map_err(read_prompt_backtest_error)?,
        new_symbol: row
            .try_get("new_symbol")
            .map_err(read_prompt_backtest_error)?,
        new_reasoning: row
            .try_get("new_reasoning")
            .map_err(read_prompt_backtest_error)?,
        new_decision_json: row
            .try_get("new_decision_json")
            .map_err(read_prompt_backtest_error)?,
        decision_changed: row
            .try_get("decision_changed")
            .map_err(read_prompt_backtest_error)?,
        change_type: row
            .try_get("change_type")
            .map_err(read_prompt_backtest_error)?,
        error_message: row
            .try_get("error_message")
            .map_err(read_prompt_backtest_error)?,
    }))
}

pub async fn get_task_items_for_import(
    State(state): State<AppState>,
    Path(task_id): Path<i32>,
) -> Result<Json<TaskItemsImportResponse>, AppError> {
    let task = load_task(&state, task_id).await?;
    let rows = sqlx::query(
        r#"
        SELECT
            item.original_decision_log_id AS id,
            item.modified_prompt,
            item.original_operation AS operation,
            item.original_symbol AS symbol,
            decision.reason,
            decision.decision_time,
            decision.realized_pnl::float8 AS realized_pnl
        FROM prompt_backtest_items item
        LEFT JOIN ai_decision_logs decision ON item.original_decision_log_id = decision.id
        WHERE item.task_id = $1
        "#,
    )
    .bind(task_id)
    .fetch_all(&state.db)
    .await
    .map_err(|error| AppError::internal(format!("Failed to get prompt backtest items: {error}")))?;

    let items = rows
        .into_iter()
        .map(|row| {
            Ok(TaskImportItem {
                id: row.try_get("id").map_err(read_prompt_backtest_error)?,
                modified_prompt: row
                    .try_get("modified_prompt")
                    .map_err(read_prompt_backtest_error)?,
                operation: row
                    .try_get("operation")
                    .map_err(read_prompt_backtest_error)?,
                symbol: row.try_get("symbol").map_err(read_prompt_backtest_error)?,
                reason: row.try_get("reason").map_err(read_prompt_backtest_error)?,
                decision_time: row
                    .try_get::<Option<NaiveDateTime>, _>("decision_time")
                    .map_err(read_prompt_backtest_error)?
                    .map(format_utc_iso),
                realized_pnl: row
                    .try_get("realized_pnl")
                    .map_err(read_prompt_backtest_error)?,
            })
        })
        .collect::<Result<Vec<_>, AppError>>()?;

    Ok(Json(TaskItemsImportResponse {
        task_id,
        task_name: task.name,
        items,
    }))
}

async fn load_task(state: &AppState, task_id: i32) -> Result<TaskStatusResponse, AppError> {
    let Some(row) = sqlx::query(
        r#"
        SELECT id, account_id, name, status, total_count, completed_count, failed_count,
               created_at, started_at, finished_at
        FROM prompt_backtest_tasks
        WHERE id = $1
        "#,
    )
    .bind(task_id)
    .fetch_optional(&state.db)
    .await
    .map_err(|error| AppError::internal(format!("Failed to get prompt backtest task: {error}")))?
    else {
        return Err(AppError::not_found("Task not found"));
    };

    row_to_task(row)
}

fn row_to_task(row: sqlx::postgres::PgRow) -> Result<TaskStatusResponse, AppError> {
    Ok(TaskStatusResponse {
        id: row.try_get("id").map_err(read_prompt_backtest_error)?,
        account_id: row
            .try_get("account_id")
            .map_err(read_prompt_backtest_error)?,
        name: row.try_get("name").map_err(read_prompt_backtest_error)?,
        status: row.try_get("status").map_err(read_prompt_backtest_error)?,
        total_count: row
            .try_get("total_count")
            .map_err(read_prompt_backtest_error)?,
        completed_count: row
            .try_get("completed_count")
            .map_err(read_prompt_backtest_error)?,
        failed_count: row
            .try_get("failed_count")
            .map_err(read_prompt_backtest_error)?,
        created_at: row
            .try_get::<Option<NaiveDateTime>, _>("created_at")
            .map_err(read_prompt_backtest_error)?
            .map(format_utc_iso)
            .unwrap_or_default(),
        started_at: row
            .try_get::<Option<NaiveDateTime>, _>("started_at")
            .map_err(read_prompt_backtest_error)?
            .map(format_utc_iso),
        finished_at: row
            .try_get::<Option<NaiveDateTime>, _>("finished_at")
            .map_err(read_prompt_backtest_error)?
            .map(format_utc_iso),
    })
}

fn row_to_result_item(row: sqlx::postgres::PgRow) -> Result<ResultItemResponse, AppError> {
    Ok(ResultItemResponse {
        id: row.try_get("id").map_err(read_prompt_backtest_error)?,
        original_decision_time: row
            .try_get::<Option<NaiveDateTime>, _>("original_decision_time")
            .map_err(read_prompt_backtest_error)?
            .map(format_utc_iso),
        original_operation: row
            .try_get("original_operation")
            .map_err(read_prompt_backtest_error)?,
        original_symbol: row
            .try_get("original_symbol")
            .map_err(read_prompt_backtest_error)?,
        original_target_portion: row
            .try_get("original_target_portion")
            .map_err(read_prompt_backtest_error)?,
        original_realized_pnl: row
            .try_get("original_realized_pnl")
            .map_err(read_prompt_backtest_error)?,
        new_operation: row
            .try_get("new_operation")
            .map_err(read_prompt_backtest_error)?,
        new_symbol: row
            .try_get("new_symbol")
            .map_err(read_prompt_backtest_error)?,
        new_target_portion: row
            .try_get("new_target_portion")
            .map_err(read_prompt_backtest_error)?,
        decision_changed: row
            .try_get("decision_changed")
            .map_err(read_prompt_backtest_error)?,
        change_type: row
            .try_get("change_type")
            .map_err(read_prompt_backtest_error)?,
        status: row.try_get("status").map_err(read_prompt_backtest_error)?,
    })
}

fn summarize_results(items: &[ResultItemResponse]) -> ResultSummary {
    let completed = items
        .iter()
        .filter(|item| item.status == "completed")
        .collect::<Vec<_>>();
    let failed = items.iter().filter(|item| item.status == "failed").count();
    let changed = completed
        .iter()
        .filter(|item| item.decision_changed.unwrap_or(false))
        .collect::<Vec<_>>();
    let unchanged = completed
        .iter()
        .filter(|item| !item.decision_changed.unwrap_or(false))
        .count();

    let mut avoided_loss_count = 0;
    let mut avoided_loss_amount = 0.0;
    let mut missed_profit_count = 0;
    let mut missed_profit_amount = 0.0;

    for item in &changed {
        let pnl = item.original_realized_pnl.unwrap_or(0.0);
        let original = item
            .original_operation
            .as_deref()
            .unwrap_or("")
            .to_lowercase();
        let new = item.new_operation.as_deref().unwrap_or("").to_lowercase();
        if matches!(original.as_str(), "buy" | "sell") && new == "hold" && pnl < 0.0 {
            avoided_loss_count += 1;
            avoided_loss_amount += pnl;
        }
        if matches!(original.as_str(), "buy" | "sell") && new == "hold" && pnl > 0.0 {
            missed_profit_count += 1;
            missed_profit_amount += pnl;
        }
    }

    ResultSummary {
        total: items.len(),
        completed: completed.len(),
        failed,
        changed: changed.len(),
        unchanged,
        avoided_loss_count,
        avoided_loss_amount,
        missed_profit_count,
        missed_profit_amount,
    }
}

fn read_prompt_backtest_error(error: sqlx::Error) -> AppError {
    AppError::internal(format!("Failed to read prompt backtest data: {error}"))
}

fn format_utc_iso(value: NaiveDateTime) -> String {
    format!("{}+00:00", value.format("%Y-%m-%dT%H:%M:%S%.f"))
}

fn default_task_limit() -> i64 {
    20
}

fn parse_create_task_payload(body: &Bytes) -> Result<CreateTaskRequest, AppError> {
    serde_json::from_slice(body).map_err(|error| {
        AppError::bad_request(format!("invalid prompt backtest create payload: {error}"))
    })
}

fn parse_prompt_backtest_task_id(task_id: &str) -> Result<i32, AppError> {
    task_id
        .parse::<i32>()
        .map_err(|_| AppError::bad_request("task_id path parameter must be a valid integer"))
}

#[cfg(test)]
mod tests {
    use chrono::NaiveDate;
    use serde_json::json;

    use super::{
        ResultItemResponse, format_utc_iso, parse_create_task_payload,
        parse_prompt_backtest_task_id, summarize_results,
    };

    #[test]
    fn formats_timestamps_like_legacy_backtest_api() {
        let value = NaiveDate::from_ymd_opt(2026, 4, 14)
            .expect("date should be valid")
            .and_hms_opt(1, 2, 3)
            .expect("time should be valid");
        assert_eq!(format_utc_iso(value), "2026-04-14T01:02:03+00:00");
    }

    #[test]
    fn summarizes_avoided_loss_and_missed_profit() {
        let items = vec![
            fake_result(
                "completed",
                Some(true),
                Some("buy"),
                Some("hold"),
                Some(-10.0),
            ),
            fake_result(
                "completed",
                Some(true),
                Some("sell"),
                Some("hold"),
                Some(5.0),
            ),
            fake_result("failed", None, None, None, None),
        ];
        let summary = summarize_results(&items);
        assert_eq!(summary.total, 3);
        assert_eq!(summary.completed, 2);
        assert_eq!(summary.failed, 1);
        assert_eq!(summary.changed, 2);
        assert_eq!(summary.avoided_loss_count, 1);
        assert_eq!(summary.avoided_loss_amount, -10.0);
        assert_eq!(summary.missed_profit_count, 1);
        assert_eq!(summary.missed_profit_amount, 5.0);
    }

    #[test]
    fn parses_create_task_payload_with_optional_replace_rules() {
        let payload = json!({
            "account_id": 123,
            "name": "Regression batch",
            "items": [
                { "decision_log_id": 10, "modified_prompt": "Prompt A" },
                { "decision_log_id": 11, "modified_prompt": "Prompt B" }
            ],
            "replace_rules": [
                { "find": "BTC", "replace": "ETH" }
            ]
        });

        let parsed = parse_create_task_payload(
            &serde_json::to_vec(&payload)
                .expect("payload should serialize")
                .into(),
        )
        .expect("payload should parse");

        assert_eq!(parsed.account_id, 123);
        assert_eq!(parsed.items.len(), 2);
        assert_eq!(parsed.replace_rules.as_ref().map(Vec::len), Some(1));
    }

    #[test]
    fn rejects_create_task_payload_missing_account_id() {
        let payload = json!({
            "items": [
                { "decision_log_id": 10, "modified_prompt": "Prompt A" }
            ]
        });

        let error = parse_create_task_payload(
            &serde_json::to_vec(&payload)
                .expect("payload should serialize")
                .into(),
        )
        .expect_err("missing account_id should fail");

        assert!(
            error
                .message
                .contains("invalid prompt backtest create payload")
        );
        assert!(error.message.contains("account_id"));
    }

    #[test]
    fn validates_prompt_backtest_task_id_path_contract() {
        assert_eq!(
            parse_prompt_backtest_task_id("42").expect("task_id should parse"),
            42
        );

        let error = parse_prompt_backtest_task_id("invalid-task-id")
            .expect_err("invalid task id should fail");
        assert_eq!(
            error.message,
            "task_id path parameter must be a valid integer"
        );
    }

    fn fake_result(
        status: &str,
        changed: Option<bool>,
        original: Option<&str>,
        new: Option<&str>,
        pnl: Option<f64>,
    ) -> ResultItemResponse {
        ResultItemResponse {
            id: 1,
            original_decision_time: None,
            original_operation: original.map(str::to_owned),
            original_symbol: None,
            original_target_portion: None,
            original_realized_pnl: pnl,
            new_operation: new.map(str::to_owned),
            new_symbol: None,
            new_target_portion: None,
            decision_changed: changed,
            change_type: None,
            status: status.to_owned(),
        }
    }
}
