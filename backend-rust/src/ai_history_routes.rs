use axum::{
    Json,
    extract::{Path, Query, State},
};
use chrono::NaiveDateTime;
use serde::{Deserialize, Serialize};
use serde_json::Value;
use sqlx::Row;

use crate::{error::AppError, state::AppState};

#[derive(Deserialize)]
pub struct ConversationListQuery {
    program_id: Option<i32>,
    #[serde(default = "default_limit")]
    limit: i64,
}

#[derive(Serialize)]
pub struct PromptConversationListResponse {
    conversations: Vec<PromptConversationItem>,
}

#[derive(Serialize)]
pub struct PromptConversationItem {
    id: i32,
    title: String,
    #[serde(rename = "promptId")]
    prompt_id: Option<i32>,
    #[serde(rename = "messageCount")]
    message_count: i64,
    #[serde(rename = "createdAt")]
    created_at: Option<String>,
    #[serde(rename = "updatedAt")]
    updated_at: Option<String>,
}

#[derive(Serialize)]
pub struct GenericConversationListResponse {
    conversations: Vec<GenericConversationItem>,
}

#[derive(Serialize)]
pub struct GenericConversationItem {
    id: i32,
    title: String,
    created_at: String,
    updated_at: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    program_id: Option<i32>,
}

#[derive(Serialize)]
pub struct AiMessagesResponse<T> {
    messages: Vec<T>,
    compression_points: Vec<Value>,
    token_usage: Option<Value>,
}

#[derive(Serialize)]
pub struct PromptMessageItem {
    id: i32,
    role: String,
    content: String,
    #[serde(rename = "promptResult")]
    prompt_result: Option<String>,
    #[serde(rename = "createdAt")]
    created_at: Option<String>,
    is_complete: bool,
    #[serde(skip_serializing_if = "Option::is_none")]
    tool_calls_log: Option<Value>,
    #[serde(skip_serializing_if = "Option::is_none")]
    reasoning_snapshot: Option<String>,
}

#[derive(Serialize)]
pub struct SignalMessageItem {
    id: i32,
    role: String,
    content: String,
    signal_configs: Option<Value>,
    reasoning_snapshot: Option<String>,
    tool_calls_log: Option<Value>,
    is_complete: Option<bool>,
    created_at: Option<String>,
}

#[derive(Serialize)]
pub struct ProgramMessageItem {
    id: i32,
    role: String,
    content: String,
    #[serde(rename = "saveSuggestion")]
    save_suggestion: Option<SaveSuggestion>,
    reasoning_snapshot: Option<String>,
    tool_calls_log: Option<Value>,
    created_at: String,
    is_complete: bool,
}

#[derive(Serialize)]
pub struct SaveSuggestion {
    code: String,
    name: String,
    description: String,
}

pub async fn list_prompt_conversations(
    State(state): State<AppState>,
    Query(query): Query<ConversationListQuery>,
) -> Result<Json<PromptConversationListResponse>, AppError> {
    let user_id = default_user_id(&state).await?;
    let rows = sqlx::query(
        r#"
        SELECT c.id, c.title, c.prompt_id, c.created_at, c.updated_at,
               COUNT(m.id)::bigint AS message_count
        FROM ai_prompt_conversations c
        LEFT JOIN ai_prompt_messages m ON m.conversation_id = c.id
        WHERE c.user_id = $1
        GROUP BY c.id
        ORDER BY c.updated_at DESC
        LIMIT $2
        "#,
    )
    .bind(user_id)
    .bind(query.limit)
    .fetch_all(&state.db)
    .await
    .map_err(|error| AppError::internal(format!("Failed to list prompt conversations: {error}")))?;

    let conversations = rows
        .into_iter()
        .map(|row| {
            Ok(PromptConversationItem {
                id: row.try_get("id").map_err(read_ai_history_error)?,
                title: row.try_get("title").map_err(read_ai_history_error)?,
                prompt_id: row.try_get("prompt_id").map_err(read_ai_history_error)?,
                message_count: row
                    .try_get("message_count")
                    .map_err(read_ai_history_error)?,
                created_at: row
                    .try_get::<Option<NaiveDateTime>, _>("created_at")
                    .map_err(read_ai_history_error)?
                    .map(format_naive_iso),
                updated_at: row
                    .try_get::<Option<NaiveDateTime>, _>("updated_at")
                    .map_err(read_ai_history_error)?
                    .map(format_naive_iso),
            })
        })
        .collect::<Result<Vec<_>, AppError>>()?;

    Ok(Json(PromptConversationListResponse { conversations }))
}

pub async fn list_signal_conversations(
    State(state): State<AppState>,
    Query(query): Query<ConversationListQuery>,
) -> Result<Json<GenericConversationListResponse>, AppError> {
    list_generic_conversations(&state, "ai_signal_conversations", query.limit, None)
        .await
        .map(Json)
}

pub async fn list_program_conversations(
    State(state): State<AppState>,
    Query(query): Query<ConversationListQuery>,
) -> Result<Json<Vec<GenericConversationItem>>, AppError> {
    let response = list_generic_conversations(
        &state,
        "ai_program_conversations",
        query.limit.min(100),
        query.program_id,
    )
    .await?;
    Ok(Json(response.conversations))
}

pub async fn get_prompt_messages(
    State(state): State<AppState>,
    Path(conversation_id): Path<i32>,
) -> Result<Json<AiMessagesResponse<PromptMessageItem>>, AppError> {
    let compression_points =
        ensure_conversation_and_compression(&state, "ai_prompt_conversations", conversation_id)
            .await?;
    let rows = sqlx::query(
        r#"
        SELECT id, role, content, prompt_result, reasoning_snapshot,
               tool_calls_log, is_complete, created_at
        FROM ai_prompt_messages
        WHERE conversation_id = $1
        ORDER BY created_at
        "#,
    )
    .bind(conversation_id)
    .fetch_all(&state.db)
    .await
    .map_err(|error| AppError::internal(format!("Failed to get prompt messages: {error}")))?;

    let messages = rows
        .into_iter()
        .map(|row| {
            Ok(PromptMessageItem {
                id: row.try_get("id").map_err(read_ai_history_error)?,
                role: row.try_get("role").map_err(read_ai_history_error)?,
                content: row.try_get("content").map_err(read_ai_history_error)?,
                prompt_result: row
                    .try_get("prompt_result")
                    .map_err(read_ai_history_error)?,
                created_at: row
                    .try_get::<Option<NaiveDateTime>, _>("created_at")
                    .map_err(read_ai_history_error)?
                    .map(format_naive_iso),
                is_complete: row
                    .try_get::<Option<bool>, _>("is_complete")
                    .map_err(read_ai_history_error)?
                    .unwrap_or(true),
                tool_calls_log: parse_optional_json(
                    row.try_get::<Option<String>, _>("tool_calls_log")
                        .map_err(read_ai_history_error)?,
                ),
                reasoning_snapshot: row
                    .try_get("reasoning_snapshot")
                    .map_err(read_ai_history_error)?,
            })
        })
        .collect::<Result<Vec<_>, AppError>>()?;

    Ok(Json(AiMessagesResponse {
        messages,
        compression_points,
        token_usage: None,
    }))
}

pub async fn get_signal_messages(
    State(state): State<AppState>,
    Path(conversation_id): Path<i32>,
) -> Result<Json<AiMessagesResponse<SignalMessageItem>>, AppError> {
    let compression_points =
        ensure_conversation_and_compression(&state, "ai_signal_conversations", conversation_id)
            .await?;
    let rows = sqlx::query(
        r#"
        SELECT id, role, content, signal_configs, reasoning_snapshot,
               tool_calls_log, is_complete, created_at
        FROM ai_signal_messages
        WHERE conversation_id = $1
        ORDER BY created_at
        "#,
    )
    .bind(conversation_id)
    .fetch_all(&state.db)
    .await
    .map_err(|error| AppError::internal(format!("Failed to get signal messages: {error}")))?;

    let messages = rows
        .into_iter()
        .map(|row| {
            Ok(SignalMessageItem {
                id: row.try_get("id").map_err(read_ai_history_error)?,
                role: row.try_get("role").map_err(read_ai_history_error)?,
                content: row.try_get("content").map_err(read_ai_history_error)?,
                signal_configs: parse_optional_json(
                    row.try_get::<Option<String>, _>("signal_configs")
                        .map_err(read_ai_history_error)?,
                ),
                reasoning_snapshot: row
                    .try_get("reasoning_snapshot")
                    .map_err(read_ai_history_error)?,
                tool_calls_log: parse_optional_json(
                    row.try_get::<Option<String>, _>("tool_calls_log")
                        .map_err(read_ai_history_error)?,
                ),
                is_complete: row.try_get("is_complete").map_err(read_ai_history_error)?,
                created_at: row
                    .try_get::<Option<NaiveDateTime>, _>("created_at")
                    .map_err(read_ai_history_error)?
                    .map(format_naive_iso),
            })
        })
        .collect::<Result<Vec<_>, AppError>>()?;

    Ok(Json(AiMessagesResponse {
        messages,
        compression_points,
        token_usage: None,
    }))
}

pub async fn get_program_messages(
    State(state): State<AppState>,
    Path(conversation_id): Path<i32>,
) -> Result<Json<AiMessagesResponse<ProgramMessageItem>>, AppError> {
    let compression_points =
        ensure_conversation_and_compression(&state, "ai_program_conversations", conversation_id)
            .await?;
    let rows = sqlx::query(
        r#"
        SELECT id, role, content, code_suggestion, reasoning_snapshot,
               tool_calls_log, is_complete, created_at
        FROM ai_program_messages
        WHERE conversation_id = $1
        ORDER BY created_at
        "#,
    )
    .bind(conversation_id)
    .fetch_all(&state.db)
    .await
    .map_err(|error| AppError::internal(format!("Failed to get program messages: {error}")))?;

    let messages = rows
        .into_iter()
        .map(|row| {
            Ok(ProgramMessageItem {
                id: row.try_get("id").map_err(read_ai_history_error)?,
                role: row.try_get("role").map_err(read_ai_history_error)?,
                content: row.try_get("content").map_err(read_ai_history_error)?,
                save_suggestion: parse_save_suggestion(
                    row.try_get::<Option<String>, _>("code_suggestion")
                        .map_err(read_ai_history_error)?,
                ),
                reasoning_snapshot: row
                    .try_get("reasoning_snapshot")
                    .map_err(read_ai_history_error)?,
                tool_calls_log: parse_optional_json(
                    row.try_get::<Option<String>, _>("tool_calls_log")
                        .map_err(read_ai_history_error)?,
                ),
                created_at: row
                    .try_get::<Option<NaiveDateTime>, _>("created_at")
                    .map_err(read_ai_history_error)?
                    .map(format_naive_iso)
                    .unwrap_or_default(),
                is_complete: row
                    .try_get::<Option<bool>, _>("is_complete")
                    .map_err(read_ai_history_error)?
                    .unwrap_or(true),
            })
        })
        .collect::<Result<Vec<_>, AppError>>()?;

    Ok(Json(AiMessagesResponse {
        messages,
        compression_points,
        token_usage: None,
    }))
}

async fn list_generic_conversations(
    state: &AppState,
    table: &str,
    limit: i64,
    program_id: Option<i32>,
) -> Result<GenericConversationListResponse, AppError> {
    let user_id = default_user_id(state).await?;
    let rows = if table == "ai_program_conversations" {
        let query = format!(
            "SELECT id, title, program_id, created_at, updated_at FROM {table} WHERE user_id = $1 AND ($2::int4 IS NULL OR program_id = $2) ORDER BY updated_at DESC LIMIT $3"
        );
        sqlx::query(&query)
            .bind(user_id)
            .bind(program_id)
            .bind(limit)
            .fetch_all(&state.db)
            .await
    } else {
        let query = format!(
            "SELECT id, title, NULL::int4 AS program_id, created_at, updated_at FROM {table} WHERE user_id = $1 ORDER BY updated_at DESC LIMIT $2"
        );
        sqlx::query(&query)
            .bind(user_id)
            .bind(limit)
            .fetch_all(&state.db)
            .await
    }
    .map_err(|error| AppError::internal(format!("Failed to list conversations: {error}")))?;

    let conversations = rows
        .into_iter()
        .map(|row| {
            Ok(GenericConversationItem {
                id: row.try_get("id").map_err(read_ai_history_error)?,
                title: row.try_get("title").map_err(read_ai_history_error)?,
                program_id: row.try_get("program_id").map_err(read_ai_history_error)?,
                created_at: row
                    .try_get::<Option<NaiveDateTime>, _>("created_at")
                    .map_err(read_ai_history_error)?
                    .map(format_naive_iso)
                    .unwrap_or_default(),
                updated_at: row
                    .try_get::<Option<NaiveDateTime>, _>("updated_at")
                    .map_err(read_ai_history_error)?
                    .map(format_naive_iso)
                    .unwrap_or_default(),
            })
        })
        .collect::<Result<Vec<_>, AppError>>()?;

    Ok(GenericConversationListResponse { conversations })
}

async fn ensure_conversation_and_compression(
    state: &AppState,
    table: &str,
    conversation_id: i32,
) -> Result<Vec<Value>, AppError> {
    let user_id = default_user_id(state).await?;
    let query =
        format!("SELECT compression_points FROM {table} WHERE id = $1 AND user_id = $2 LIMIT 1");
    let Some(row) = sqlx::query(&query)
        .bind(conversation_id)
        .bind(user_id)
        .fetch_optional(&state.db)
        .await
        .map_err(|error| AppError::internal(format!("Failed to get conversation: {error}")))?
    else {
        return Err(AppError::not_found("Conversation not found"));
    };

    Ok(row
        .try_get::<Option<String>, _>("compression_points")
        .map_err(read_ai_history_error)?
        .and_then(|raw| serde_json::from_str::<Vec<Value>>(&raw).ok())
        .unwrap_or_default())
}

async fn default_user_id(state: &AppState) -> Result<i32, AppError> {
    sqlx::query_scalar::<_, i32>("SELECT id FROM users WHERE username = 'default' LIMIT 1")
        .fetch_optional(&state.db)
        .await
        .map_err(|error| AppError::internal(format!("Failed to get default user: {error}")))?
        .ok_or_else(|| AppError::not_found("User not found"))
}

fn parse_optional_json(raw: Option<String>) -> Option<Value> {
    raw.and_then(|raw| serde_json::from_str::<Value>(&raw).ok())
}

fn parse_save_suggestion(raw: Option<String>) -> Option<SaveSuggestion> {
    let raw = raw?;
    if let Ok(value) = serde_json::from_str::<Value>(&raw)
        && value.get("code").is_some()
    {
        return Some(SaveSuggestion {
            code: value
                .get("code")
                .and_then(Value::as_str)
                .unwrap_or_default()
                .to_owned(),
            name: value
                .get("name")
                .and_then(Value::as_str)
                .unwrap_or("Saved Code")
                .to_owned(),
            description: value
                .get("description")
                .and_then(Value::as_str)
                .unwrap_or_default()
                .to_owned(),
        });
    }

    Some(SaveSuggestion {
        code: raw,
        name: "Saved Code".to_owned(),
        description: String::new(),
    })
}

fn read_ai_history_error(error: sqlx::Error) -> AppError {
    AppError::internal(format!("Failed to read AI conversation data: {error}"))
}

fn format_naive_iso(value: NaiveDateTime) -> String {
    value.format("%Y-%m-%dT%H:%M:%S%.f").to_string()
}

fn default_limit() -> i64 {
    20
}

#[cfg(test)]
mod tests {
    use super::{parse_optional_json, parse_save_suggestion};

    #[test]
    fn parses_program_save_suggestion_json_or_plain_code() {
        let json = parse_save_suggestion(Some(
            r#"{"code":"print(1)","name":"Demo","description":"Desc"}"#.to_owned(),
        ))
        .expect("json suggestion should parse");
        assert_eq!(json.code, "print(1)");
        assert_eq!(json.name, "Demo");

        let plain = parse_save_suggestion(Some("print(2)".to_owned()))
            .expect("plain code suggestion should parse");
        assert_eq!(plain.code, "print(2)");
        assert_eq!(plain.name, "Saved Code");
    }

    #[test]
    fn parses_optional_tool_call_json() {
        assert!(parse_optional_json(Some("[1]".to_owned())).is_some());
        assert!(parse_optional_json(Some("bad".to_owned())).is_none());
    }
}
