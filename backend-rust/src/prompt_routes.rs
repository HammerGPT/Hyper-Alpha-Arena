use axum::{
    Json,
    extract::{Path, State},
};
use chrono::{NaiveDateTime, Utc};
use serde::{Deserialize, Serialize};
use sqlx::Row;

use crate::{error::AppError, state::AppState};

#[derive(Serialize)]
pub struct PromptListResponse {
    templates: Vec<PromptTemplateResponse>,
    bindings: Vec<PromptBindingResponse>,
}

#[derive(Serialize)]
pub struct PromptTemplateResponse {
    id: i32,
    key: String,
    name: String,
    description: Option<String>,
    #[serde(rename = "templateText")]
    template_text: String,
    #[serde(rename = "systemTemplateText")]
    system_template_text: String,
    #[serde(rename = "isSystem")]
    is_system: String,
    #[serde(rename = "isDeleted")]
    is_deleted: String,
    #[serde(rename = "createdBy")]
    created_by: String,
    #[serde(rename = "updatedBy")]
    updated_by: Option<String>,
    #[serde(rename = "createdAt")]
    created_at: Option<String>,
    #[serde(rename = "updatedAt")]
    updated_at: Option<String>,
}

#[derive(Serialize)]
pub struct PromptBindingResponse {
    id: i32,
    #[serde(rename = "accountId")]
    account_id: i32,
    #[serde(rename = "accountName")]
    account_name: String,
    #[serde(rename = "accountModel")]
    account_model: Option<String>,
    #[serde(rename = "promptTemplateId")]
    prompt_template_id: i32,
    #[serde(rename = "promptKey")]
    prompt_key: String,
    #[serde(rename = "promptName")]
    prompt_name: String,
    #[serde(rename = "updatedBy")]
    updated_by: Option<String>,
    #[serde(rename = "updatedAt")]
    updated_at: Option<String>,
}

#[derive(Deserialize)]
pub struct PromptTemplateUpdateRequest {
    #[serde(rename = "templateText")]
    template_text: String,
    description: Option<String>,
    #[serde(rename = "updatedBy")]
    updated_by: Option<String>,
}

#[derive(Deserialize)]
pub struct PromptTemplateCreateRequest {
    name: String,
    description: Option<String>,
    #[serde(rename = "templateText")]
    template_text: Option<String>,
    #[serde(rename = "createdBy")]
    created_by: Option<String>,
}

#[derive(Deserialize)]
pub struct PromptTemplateCopyRequest {
    #[serde(rename = "newName")]
    new_name: Option<String>,
    #[serde(rename = "createdBy")]
    created_by: Option<String>,
}

#[derive(Deserialize)]
pub struct PromptTemplateNameUpdateRequest {
    name: String,
    description: Option<String>,
    #[serde(rename = "updatedBy")]
    updated_by: Option<String>,
}

#[derive(Deserialize)]
pub struct PromptBindingUpsertRequest {
    #[serde(rename = "accountId")]
    account_id: Option<i32>,
    #[serde(rename = "promptTemplateId")]
    prompt_template_id: Option<i32>,
    #[serde(rename = "updatedBy")]
    updated_by: Option<String>,
}

#[derive(Serialize)]
pub struct DeleteResponse {
    success: bool,
    deleted: bool,
    #[serde(skip_serializing_if = "Option::is_none")]
    dependencies: Option<Vec<String>>,
    #[serde(skip_serializing_if = "Option::is_none")]
    message: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    entity: Option<serde_json::Value>,
}

pub async fn list_prompt_templates(
    State(state): State<AppState>,
) -> Result<Json<PromptListResponse>, AppError> {
    let templates = load_templates(&state.db).await?;
    let bindings = load_bindings(&state.db).await?;

    Ok(Json(PromptListResponse {
        templates,
        bindings,
    }))
}

pub async fn update_prompt_template(
    State(state): State<AppState>,
    Path(key): Path<String>,
    Json(payload): Json<PromptTemplateUpdateRequest>,
) -> Result<Json<PromptTemplateResponse>, AppError> {
    let result = sqlx::query(
        r#"
        UPDATE prompt_templates
        SET
            template_text = $2,
            description = COALESCE($3, description),
            updated_by = $4,
            updated_at = CURRENT_TIMESTAMP
        WHERE key = $1
        RETURNING id
        "#,
    )
    .bind(&key)
    .bind(&payload.template_text)
    .bind(payload.description.as_deref())
    .bind(payload.updated_by.as_deref())
    .fetch_optional(&state.db)
    .await
    .map_err(|error| AppError::internal(format!("Failed to update prompt template: {error}")))?;

    let Some(row) = result else {
        return Err(AppError::not_found(format!(
            "Prompt template with key '{key}' not found"
        )));
    };
    let template_id = row.try_get::<i32, _>("id").map_err(read_prompt_error)?;

    Ok(Json(load_template_by_id(&state, template_id).await?))
}

pub async fn create_prompt_template(
    State(state): State<AppState>,
    Json(payload): Json<PromptTemplateCreateRequest>,
) -> Result<Json<PromptTemplateResponse>, AppError> {
    let created_by = payload.created_by.unwrap_or_else(|| "ui".to_owned());
    let template_text = match payload.template_text {
        Some(value) if !value.is_empty() => value,
        _ => load_default_template_text(&state).await?,
    };
    let key_base = sanitize_template_key(&payload.name);
    let key = generate_unique_template_key(&state, &key_base).await?;

    let row = sqlx::query(
        r#"
        INSERT INTO prompt_templates (
            key, name, description, template_text, system_template_text,
            is_system, is_deleted, created_by, updated_by, created_at, updated_at
        )
        VALUES ($1, $2, $3, $4, $4, 'false', 'false', $5, $5, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        RETURNING id
        "#,
    )
    .bind(&key)
    .bind(&payload.name)
    .bind(payload.description.as_deref())
    .bind(&template_text)
    .bind(&created_by)
    .fetch_one(&state.db)
    .await
    .map_err(|error| AppError::internal(format!("Failed to create prompt template: {error}")))?;

    let template_id = row.try_get::<i32, _>("id").map_err(read_prompt_error)?;
    Ok(Json(load_template_by_id(&state, template_id).await?))
}

pub async fn copy_prompt_template(
    State(state): State<AppState>,
    Path(template_id): Path<i32>,
    Json(payload): Json<PromptTemplateCopyRequest>,
) -> Result<Json<PromptTemplateResponse>, AppError> {
    let source = load_template_row_by_id(&state, template_id)
        .await?
        .ok_or_else(|| {
            AppError::not_found(format!("Prompt template with id '{template_id}' not found"))
        })?;

    let source_key = source
        .try_get::<String, _>("key")
        .map_err(read_prompt_error)?;
    let source_name = source
        .try_get::<String, _>("name")
        .map_err(read_prompt_error)?;
    let source_description = source
        .try_get::<Option<String>, _>("description")
        .map_err(read_prompt_error)?;
    let source_template_text = source
        .try_get::<String, _>("template_text")
        .map_err(read_prompt_error)?;

    let new_key = generate_unique_template_key(&state, &source_key).await?;
    let new_name = payload
        .new_name
        .unwrap_or_else(|| format!("{source_name} (Copy)"));
    let created_by = payload.created_by.unwrap_or_else(|| "ui".to_owned());

    let row = sqlx::query(
        r#"
        INSERT INTO prompt_templates (
            key, name, description, template_text, system_template_text,
            is_system, is_deleted, created_by, updated_by, created_at, updated_at
        )
        VALUES ($1, $2, $3, $4, $4, 'false', 'false', $5, $5, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        RETURNING id
        "#,
    )
    .bind(&new_key)
    .bind(&new_name)
    .bind(source_description.as_deref())
    .bind(&source_template_text)
    .bind(&created_by)
    .fetch_one(&state.db)
    .await
    .map_err(|error| AppError::internal(format!("Failed to copy prompt template: {error}")))?;

    let new_id = row.try_get::<i32, _>("id").map_err(read_prompt_error)?;
    Ok(Json(load_template_by_id(&state, new_id).await?))
}

pub async fn delete_prompt_template(
    State(state): State<AppState>,
    Path(template_id): Path<i32>,
) -> Result<Json<DeleteResponse>, AppError> {
    let Some(template) = load_template_row_by_id(&state, template_id).await? else {
        return Err(AppError::not_found("Template not found"));
    };

    let is_system = template
        .try_get::<String, _>("is_system")
        .map_err(read_prompt_error)?;
    if is_system == "true" {
        return Err(AppError::not_found("Cannot delete system templates"));
    }

    let dependencies = load_prompt_template_dependencies(&state, template_id).await?;
    if !dependencies.is_empty() {
        return Ok(Json(DeleteResponse {
            success: true,
            deleted: false,
            dependencies: Some(dependencies),
            message: Some("Cannot delete: template is bound to traders. Unbind first.".to_owned()),
            entity: None,
        }));
    }

    sqlx::query(
        r#"
        UPDATE prompt_templates
        SET is_deleted = 'true', deleted_at = CURRENT_TIMESTAMP
        WHERE id = $1
        "#,
    )
    .bind(template_id)
    .execute(&state.db)
    .await
    .map_err(|error| AppError::internal(format!("Failed to delete prompt template: {error}")))?;

    Ok(Json(DeleteResponse {
        success: true,
        deleted: true,
        dependencies: None,
        message: None,
        entity: Some(serde_json::json!({
            "id": template_id,
            "name": template.try_get::<String, _>("name").map_err(read_prompt_error)?,
        })),
    }))
}

pub async fn update_prompt_template_name(
    State(state): State<AppState>,
    Path(template_id): Path<i32>,
    Json(payload): Json<PromptTemplateNameUpdateRequest>,
) -> Result<Json<PromptTemplateResponse>, AppError> {
    let result = sqlx::query(
        r#"
        UPDATE prompt_templates
        SET
            name = $2,
            description = $3,
            updated_by = $4,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = $1
        RETURNING id
        "#,
    )
    .bind(template_id)
    .bind(&payload.name)
    .bind(payload.description.as_deref())
    .bind(payload.updated_by.as_deref())
    .fetch_optional(&state.db)
    .await
    .map_err(|error| {
        AppError::internal(format!("Failed to update prompt template name: {error}"))
    })?;

    if result.is_none() {
        return Err(AppError::not_found(format!(
            "Prompt template with id '{template_id}' not found"
        )));
    }

    Ok(Json(load_template_by_id(&state, template_id).await?))
}

pub async fn upsert_prompt_binding(
    State(state): State<AppState>,
    Json(payload): Json<PromptBindingUpsertRequest>,
) -> Result<Json<PromptBindingResponse>, AppError> {
    let account_id = payload
        .account_id
        .ok_or_else(|| AppError::bad_request("accountId is required"))?;
    let prompt_template_id = payload
        .prompt_template_id
        .ok_or_else(|| AppError::bad_request("promptTemplateId is required"))?;

    let account = sqlx::query(
        r#"
        SELECT id, name, model
        FROM accounts
        WHERE id = $1
        LIMIT 1
        "#,
    )
    .bind(account_id)
    .fetch_optional(&state.db)
    .await
    .map_err(|error| AppError::internal(format!("Failed to load account: {error}")))?;
    let Some(account) = account else {
        return Err(AppError::not_found("Account not found"));
    };

    let template = load_template_row_by_id(&state, prompt_template_id)
        .await?
        .ok_or_else(|| AppError::not_found("Prompt template not found"))?;

    let binding = sqlx::query(
        r#"
        INSERT INTO account_prompt_bindings (
            account_id, prompt_template_id, updated_by, is_deleted, deleted_at, created_at, updated_at
        )
        VALUES ($1, $2, $3, false, NULL, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        ON CONFLICT (account_id)
        DO UPDATE SET
            prompt_template_id = EXCLUDED.prompt_template_id,
            updated_by = EXCLUDED.updated_by,
            is_deleted = false,
            deleted_at = NULL,
            updated_at = CURRENT_TIMESTAMP
        RETURNING id, updated_by, updated_at
        "#,
    )
    .bind(account_id)
    .bind(prompt_template_id)
    .bind(payload.updated_by.as_deref())
    .fetch_one(&state.db)
    .await
    .map_err(|error| AppError::internal(format!("Failed to upsert prompt binding: {error}")))?;

    Ok(Json(PromptBindingResponse {
        id: binding.try_get("id").map_err(read_prompt_error)?,
        account_id,
        account_name: account.try_get("name").map_err(read_prompt_error)?,
        account_model: account.try_get("model").map_err(read_prompt_error)?,
        prompt_template_id,
        prompt_key: template.try_get("key").map_err(read_prompt_error)?,
        prompt_name: template.try_get("name").map_err(read_prompt_error)?,
        updated_by: binding.try_get("updated_by").map_err(read_prompt_error)?,
        updated_at: binding
            .try_get::<Option<NaiveDateTime>, _>("updated_at")
            .map_err(read_prompt_error)?
            .map(format_naive_iso),
    }))
}

pub async fn delete_prompt_binding(
    State(state): State<AppState>,
    Path(binding_id): Path<i32>,
) -> Result<Json<DeleteResponse>, AppError> {
    let Some(binding) = sqlx::query(
        r#"
        SELECT id, account_id, prompt_template_id
        FROM account_prompt_bindings
        WHERE id = $1
          AND is_deleted != true
        "#,
    )
    .bind(binding_id)
    .fetch_optional(&state.db)
    .await
    .map_err(|error| AppError::internal(format!("Failed to load prompt binding: {error}")))?
    else {
        return Err(AppError::not_found("Binding not found"));
    };

    sqlx::query(
        r#"
        UPDATE account_prompt_bindings
        SET is_deleted = true, deleted_at = CURRENT_TIMESTAMP
        WHERE id = $1
        "#,
    )
    .bind(binding_id)
    .execute(&state.db)
    .await
    .map_err(|error| AppError::internal(format!("Failed to delete prompt binding: {error}")))?;

    Ok(Json(DeleteResponse {
        success: true,
        deleted: true,
        dependencies: None,
        message: None,
        entity: Some(serde_json::json!({
            "id": binding.try_get::<i32, _>("id").map_err(read_prompt_error)?,
            "account_id": binding.try_get::<i32, _>("account_id").map_err(read_prompt_error)?,
            "prompt_template_id": binding.try_get::<i32, _>("prompt_template_id").map_err(read_prompt_error)?,
        })),
    }))
}

async fn load_templates(pool: &sqlx::PgPool) -> Result<Vec<PromptTemplateResponse>, AppError> {
    let rows = sqlx::query(
        r#"
        SELECT
            id,
            key,
            name,
            description,
            template_text,
            system_template_text,
            is_system,
            is_deleted,
            created_by,
            updated_by,
            created_at,
            updated_at
        FROM prompt_templates
        WHERE is_deleted = 'false'
        ORDER BY created_at DESC
        "#,
    )
    .fetch_all(pool)
    .await
    .map_err(|error| AppError::internal(format!("Failed to list prompt templates: {error}")))?;

    rows.into_iter()
        .map(row_to_template)
        .collect::<Result<Vec<_>, _>>()
}

async fn load_bindings(pool: &sqlx::PgPool) -> Result<Vec<PromptBindingResponse>, AppError> {
    let rows = sqlx::query(
        r#"
        SELECT
            b.id,
            b.account_id,
            a.name AS account_name,
            a.model AS account_model,
            b.prompt_template_id,
            t.key AS prompt_key,
            t.name AS prompt_name,
            b.updated_by,
            b.updated_at
        FROM account_prompt_bindings b
        JOIN accounts a ON b.account_id = a.id
        JOIN prompt_templates t ON b.prompt_template_id = t.id
        WHERE a.is_deleted != true
          AND b.is_deleted != true
        ORDER BY a.name ASC
        "#,
    )
    .fetch_all(pool)
    .await
    .map_err(|error| AppError::internal(format!("Failed to list prompt bindings: {error}")))?;

    rows.into_iter()
        .map(row_to_binding)
        .collect::<Result<Vec<_>, _>>()
}

async fn load_template_by_id(
    state: &AppState,
    template_id: i32,
) -> Result<PromptTemplateResponse, AppError> {
    let row = load_template_row_by_id(state, template_id)
        .await?
        .ok_or_else(|| AppError::not_found("Template not found"))?;
    row_to_template(row)
}

async fn load_template_row_by_id(
    state: &AppState,
    template_id: i32,
) -> Result<Option<sqlx::postgres::PgRow>, AppError> {
    sqlx::query(
        r#"
        SELECT
            id,
            key,
            name,
            description,
            template_text,
            system_template_text,
            is_system,
            is_deleted,
            created_by,
            updated_by,
            created_at,
            updated_at
        FROM prompt_templates
        WHERE id = $1
        LIMIT 1
        "#,
    )
    .bind(template_id)
    .fetch_optional(&state.db)
    .await
    .map_err(|error| AppError::internal(format!("Failed to load prompt template: {error}")))
}

async fn load_default_template_text(state: &AppState) -> Result<String, AppError> {
    sqlx::query_scalar::<_, String>(
        "SELECT template_text FROM prompt_templates WHERE key = 'default' LIMIT 1",
    )
    .fetch_optional(&state.db)
    .await
    .map_err(|error| {
        AppError::internal(format!("Failed to load default prompt template: {error}"))
    })?
    .ok_or_else(|| AppError::not_found("Default prompt template not found"))
}

async fn generate_unique_template_key(
    state: &AppState,
    base_key: &str,
) -> Result<String, AppError> {
    let timestamp = Utc::now().format("%Y%m%d%H%M%S").to_string();
    let original = format!("{base_key}-{timestamp}");
    let mut key = original.clone();
    let mut counter = 1;

    loop {
        let exists = sqlx::query_scalar::<_, i64>(
            "SELECT COUNT(*)::bigint FROM prompt_templates WHERE key = $1",
        )
        .bind(&key)
        .fetch_one(&state.db)
        .await
        .map_err(|error| {
            AppError::internal(format!("Failed to generate unique template key: {error}"))
        })?;

        if exists == 0 {
            return Ok(key);
        }

        key = format!("{original}-{counter}");
        counter += 1;
    }
}

async fn load_prompt_template_dependencies(
    state: &AppState,
    prompt_id: i32,
) -> Result<Vec<String>, AppError> {
    let rows = sqlx::query(
        r#"
        SELECT b.id, a.name
        FROM account_prompt_bindings b
        LEFT JOIN accounts a ON a.id = b.account_id
        WHERE b.prompt_template_id = $1
          AND b.is_deleted != true
        "#,
    )
    .bind(prompt_id)
    .fetch_all(&state.db)
    .await
    .map_err(|error| AppError::internal(format!("Failed to load prompt dependencies: {error}")))?;

    rows.into_iter()
        .map(|row| {
            let binding_id = row.try_get::<i32, _>("id").map_err(read_prompt_error)?;
            let name = row
                .try_get::<Option<String>, _>("name")
                .map_err(read_prompt_error)?
                .unwrap_or_else(|| "unknown".to_owned());
            Ok(format!(
                "Bound to AI Trader: {name} (binding #{binding_id})"
            ))
        })
        .collect()
}

fn row_to_template(row: sqlx::postgres::PgRow) -> Result<PromptTemplateResponse, AppError> {
    Ok(PromptTemplateResponse {
        id: row.try_get("id").map_err(read_prompt_error)?,
        key: row.try_get("key").map_err(read_prompt_error)?,
        name: row.try_get("name").map_err(read_prompt_error)?,
        description: row.try_get("description").map_err(read_prompt_error)?,
        template_text: row.try_get("template_text").map_err(read_prompt_error)?,
        system_template_text: row
            .try_get("system_template_text")
            .map_err(read_prompt_error)?,
        is_system: row.try_get("is_system").map_err(read_prompt_error)?,
        is_deleted: row.try_get("is_deleted").map_err(read_prompt_error)?,
        created_by: row.try_get("created_by").map_err(read_prompt_error)?,
        updated_by: row.try_get("updated_by").map_err(read_prompt_error)?,
        created_at: row
            .try_get::<Option<NaiveDateTime>, _>("created_at")
            .map_err(read_prompt_error)?
            .map(format_naive_iso),
        updated_at: row
            .try_get::<Option<NaiveDateTime>, _>("updated_at")
            .map_err(read_prompt_error)?
            .map(format_naive_iso),
    })
}

fn row_to_binding(row: sqlx::postgres::PgRow) -> Result<PromptBindingResponse, AppError> {
    Ok(PromptBindingResponse {
        id: row.try_get("id").map_err(read_prompt_error)?,
        account_id: row.try_get("account_id").map_err(read_prompt_error)?,
        account_name: row.try_get("account_name").map_err(read_prompt_error)?,
        account_model: row.try_get("account_model").map_err(read_prompt_error)?,
        prompt_template_id: row
            .try_get("prompt_template_id")
            .map_err(read_prompt_error)?,
        prompt_key: row.try_get("prompt_key").map_err(read_prompt_error)?,
        prompt_name: row.try_get("prompt_name").map_err(read_prompt_error)?,
        updated_by: row.try_get("updated_by").map_err(read_prompt_error)?,
        updated_at: row
            .try_get::<Option<NaiveDateTime>, _>("updated_at")
            .map_err(read_prompt_error)?
            .map(format_naive_iso),
    })
}

fn sanitize_template_key(name: &str) -> String {
    let mut key = name
        .to_lowercase()
        .replace(' ', "-")
        .replace('_', "-")
        .chars()
        .filter(|ch| ch.is_ascii_alphanumeric() || *ch == '-')
        .collect::<String>();
    if key.is_empty() {
        key = "template".to_owned();
    }
    key.chars().take(50).collect()
}

fn read_prompt_error(error: sqlx::Error) -> AppError {
    AppError::internal(format!("Failed to read prompt data: {error}"))
}

fn format_naive_iso(value: NaiveDateTime) -> String {
    value.format("%Y-%m-%dT%H:%M:%S%.f").to_string()
}

#[cfg(test)]
mod tests {
    use chrono::NaiveDate;

    use super::{format_naive_iso, sanitize_template_key};

    #[test]
    fn formats_prompt_timestamps_as_iso_strings() {
        let value = NaiveDate::from_ymd_opt(2026, 4, 14)
            .expect("date should be valid")
            .and_hms_opt(8, 9, 10)
            .expect("time should be valid");
        assert_eq!(format_naive_iso(value), "2026-04-14T08:09:10");
    }

    #[test]
    fn sanitizes_template_key_like_legacy_base_key_generation() {
        assert_eq!(
            sanitize_template_key("My Strategy_Prompt"),
            "my-strategy-prompt"
        );
        assert_eq!(sanitize_template_key(""), "template");
    }
}
