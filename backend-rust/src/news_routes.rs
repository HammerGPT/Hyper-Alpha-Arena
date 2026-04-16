use axum::{
    Json,
    extract::{Query, State},
};
use chrono::{Duration, NaiveDateTime, Utc};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use sqlx::Row;
use std::collections::{HashMap, HashSet};

use crate::{error::AppError, state::AppState};

const NEWS_SOURCES_CONFIG_KEY: &str = "news_sources";

#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct NewsSourceConfig {
    #[serde(rename = "type", default = "default_source_type")]
    source_type: String,
    #[serde(default = "default_adapter")]
    adapter: String,
    url: String,
    #[serde(default = "default_enabled")]
    enabled: bool,
    #[serde(default = "default_interval_seconds")]
    interval_seconds: i32,
    #[serde(default)]
    config: Value,
}

#[derive(Deserialize)]
pub struct NewsSourcesUpdateRequest {
    sources: Vec<NewsSourceConfig>,
}

#[derive(Serialize)]
pub struct NewsSourcesResponse {
    sources: Vec<NewsSourceConfig>,
}

#[derive(Serialize)]
pub struct NewsSourcesUpdateResponse {
    success: bool,
    message: String,
    sources: Vec<NewsSourceConfig>,
}

#[derive(Deserialize)]
pub struct NewsArticlesQuery {
    symbols: Option<String>,
    #[serde(default = "default_article_hours")]
    hours: i64,
    #[serde(default = "default_article_limit")]
    limit: i64,
}

#[derive(Serialize)]
pub struct NewsArticleListResponse {
    items: Vec<NewsArticleItem>,
    total: usize,
}

#[derive(Serialize)]
pub struct NewsArticleItem {
    id: i32,
    source_domain: String,
    source_url: String,
    title: String,
    summary: Option<String>,
    published_at: Option<String>,
    symbols: Vec<String>,
    sentiment: Option<String>,
    ai_summary: Option<String>,
    relevance_score: Option<f64>,
    image_url: Option<String>,
}

#[derive(Serialize)]
pub struct NewsStatsResponse {
    total_articles: i64,
    classified: i64,
    with_sentiment: i64,
    last_24h: NewsLast24hStats,
    latest_article_at: Option<String>,
}

#[derive(Serialize)]
pub struct NewsLast24hStats {
    by_domain: HashMap<String, i64>,
    by_sentiment: HashMap<String, i64>,
    total: i64,
}

pub async fn list_news_articles(
    State(state): State<AppState>,
    Query(query): Query<NewsArticlesQuery>,
) -> Result<Json<NewsArticleListResponse>, AppError> {
    let hours = query.hours.clamp(1, 168);
    let limit = query.limit.clamp(1, 50);
    let symbol_filter = parse_symbol_filter(query.symbols.as_deref());
    let cutoff = Utc::now().naive_utc() - Duration::hours(hours);

    let rows = sqlx::query(
        r#"
        SELECT
            id,
            source_domain,
            source_url,
            title,
            summary,
            published_at,
            symbols,
            sentiment,
            ai_summary,
            relevance_score,
            image_url
        FROM news_articles
        WHERE published_at >= $1
        ORDER BY published_at DESC NULLS LAST, id DESC
        LIMIT $2
        "#,
    )
    .bind(cutoff)
    .bind(limit * 5)
    .fetch_all(&state.db)
    .await
    .map_err(|error| AppError::internal(format!("Failed to list news articles: {error}")))?;

    let mut items = Vec::new();
    for row in rows {
        let article_symbols = parse_article_symbols(
            row.try_get::<Option<String>, _>("symbols")
                .map_err(|error| {
                    AppError::internal(format!("Failed to read news article: {error}"))
                })?
                .as_deref(),
        );
        if !symbol_filter.is_empty()
            && !(article_symbols
                .iter()
                .any(|symbol| symbol_filter.contains(symbol))
                || article_symbols.iter().any(|symbol| symbol == "_MACRO"))
        {
            continue;
        }

        items.push(row_to_news_article(row, article_symbols)?);
        if items.len() >= limit as usize {
            break;
        }
    }

    Ok(Json(NewsArticleListResponse {
        total: items.len(),
        items,
    }))
}

pub async fn get_news_sources(
    State(state): State<AppState>,
) -> Result<Json<NewsSourcesResponse>, AppError> {
    let value = sqlx::query_scalar::<_, Option<String>>(
        "SELECT value FROM system_configs WHERE key = $1 LIMIT 1",
    )
    .bind(NEWS_SOURCES_CONFIG_KEY)
    .fetch_optional(&state.db)
    .await
    .map_err(|error| AppError::internal(format!("Failed to get news sources: {error}")))?;

    let sources = match value.flatten() {
        Some(raw) if !raw.trim().is_empty() => {
            serde_json::from_str::<Vec<NewsSourceConfig>>(&raw).unwrap_or_else(|_| Vec::new())
        }
        _ => default_news_sources(),
    };

    Ok(Json(NewsSourcesResponse { sources }))
}

pub async fn update_news_sources(
    State(state): State<AppState>,
    Json(payload): Json<NewsSourcesUpdateRequest>,
) -> Result<Json<NewsSourcesUpdateResponse>, AppError> {
    let json_str = serde_json::to_string(&payload.sources)
        .map_err(|error| AppError::bad_request(format!("Invalid news sources: {error}")))?;

    sqlx::query(
        r#"
        INSERT INTO system_configs (key, value, description, created_at, updated_at)
        VALUES ($1, $2, 'News source configurations', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        ON CONFLICT (key)
        DO UPDATE SET value = EXCLUDED.value, description = EXCLUDED.description, updated_at = CURRENT_TIMESTAMP
        "#,
    )
    .bind(NEWS_SOURCES_CONFIG_KEY)
    .bind(json_str)
    .execute(&state.db)
    .await
    .map_err(|error| AppError::internal(format!("Failed to update news sources: {error}")))?;

    Ok(Json(NewsSourcesUpdateResponse {
        success: true,
        message: format!("Saved {} news sources", payload.sources.len()),
        sources: payload.sources,
    }))
}

pub async fn get_news_stats(
    State(state): State<AppState>,
) -> Result<Json<NewsStatsResponse>, AppError> {
    let total = scalar_count(&state.db, "SELECT COUNT(id)::bigint FROM news_articles").await?;
    let classified = scalar_count(
        &state.db,
        "SELECT COUNT(id)::bigint FROM news_articles WHERE classified = true",
    )
    .await?;
    let with_sentiment = scalar_count(
        &state.db,
        "SELECT COUNT(id)::bigint FROM news_articles WHERE sentiment IS NOT NULL",
    )
    .await?;

    let h24_ago = Utc::now().naive_utc() - Duration::hours(24);
    let by_domain = grouped_counts(
        &state.db,
        "SELECT source_domain AS key, COUNT(id)::bigint AS count FROM news_articles WHERE published_at >= $1 GROUP BY source_domain",
        h24_ago,
        false,
    )
    .await?;
    let by_sentiment = grouped_counts(
        &state.db,
        "SELECT sentiment AS key, COUNT(id)::bigint AS count FROM news_articles WHERE published_at >= $1 GROUP BY sentiment",
        h24_ago,
        true,
    )
    .await?;
    let latest = sqlx::query_scalar::<_, Option<NaiveDateTime>>(
        "SELECT MAX(published_at) FROM news_articles",
    )
    .fetch_one(&state.db)
    .await
    .map_err(|error| AppError::internal(format!("Failed to get news stats: {error}")))?;
    let total_24h = by_domain.values().sum();

    Ok(Json(NewsStatsResponse {
        total_articles: total,
        classified,
        with_sentiment,
        last_24h: NewsLast24hStats {
            by_domain,
            by_sentiment,
            total: total_24h,
        },
        latest_article_at: latest.map(format_naive_iso),
    }))
}

fn row_to_news_article(
    row: sqlx::postgres::PgRow,
    symbols: Vec<String>,
) -> Result<NewsArticleItem, AppError> {
    let published_at = row
        .try_get::<Option<NaiveDateTime>, _>("published_at")
        .map_err(|error| AppError::internal(format!("Failed to read news article: {error}")))?
        .map(format_naive_iso);

    Ok(NewsArticleItem {
        id: row
            .try_get("id")
            .map_err(|error| AppError::internal(format!("Failed to read news article: {error}")))?,
        source_domain: row
            .try_get("source_domain")
            .map_err(|error| AppError::internal(format!("Failed to read news article: {error}")))?,
        source_url: row
            .try_get("source_url")
            .map_err(|error| AppError::internal(format!("Failed to read news article: {error}")))?,
        title: row
            .try_get("title")
            .map_err(|error| AppError::internal(format!("Failed to read news article: {error}")))?,
        summary: row
            .try_get("summary")
            .map_err(|error| AppError::internal(format!("Failed to read news article: {error}")))?,
        published_at,
        symbols,
        sentiment: row
            .try_get("sentiment")
            .map_err(|error| AppError::internal(format!("Failed to read news article: {error}")))?,
        ai_summary: row
            .try_get("ai_summary")
            .map_err(|error| AppError::internal(format!("Failed to read news article: {error}")))?,
        relevance_score: row
            .try_get("relevance_score")
            .map_err(|error| AppError::internal(format!("Failed to read news article: {error}")))?,
        image_url: row
            .try_get("image_url")
            .map_err(|error| AppError::internal(format!("Failed to read news article: {error}")))?,
    })
}

async fn scalar_count(pool: &sqlx::PgPool, query: &str) -> Result<i64, AppError> {
    sqlx::query_scalar::<_, i64>(query)
        .fetch_one(pool)
        .await
        .map_err(|error| AppError::internal(format!("Failed to get news stats: {error}")))
}

async fn grouped_counts(
    pool: &sqlx::PgPool,
    query: &str,
    cutoff: NaiveDateTime,
    unknown_for_null: bool,
) -> Result<HashMap<String, i64>, AppError> {
    let rows = sqlx::query(query)
        .bind(cutoff)
        .fetch_all(pool)
        .await
        .map_err(|error| AppError::internal(format!("Failed to get news stats: {error}")))?;

    rows.into_iter()
        .map(|row| {
            let key = row.try_get::<Option<String>, _>("key").map_err(|error| {
                AppError::internal(format!("Failed to read news stats: {error}"))
            })?;
            let count = row.try_get::<i64, _>("count").map_err(|error| {
                AppError::internal(format!("Failed to read news stats: {error}"))
            })?;
            let key = match (key, unknown_for_null) {
                (Some(key), _) => key,
                (None, true) => "unknown".to_owned(),
                (None, false) => String::new(),
            };
            Ok((key, count))
        })
        .collect()
}

fn parse_symbol_filter(value: Option<&str>) -> HashSet<String> {
    value
        .unwrap_or_default()
        .split(',')
        .filter_map(|part| {
            let part = part.trim();
            if part.is_empty() {
                None
            } else {
                Some(part.to_uppercase())
            }
        })
        .collect()
}

fn parse_article_symbols(value: Option<&str>) -> Vec<String> {
    let Some(raw) = value.map(str::trim).filter(|raw| !raw.is_empty()) else {
        return Vec::new();
    };

    if let Ok(parsed) = serde_json::from_str::<Vec<Value>>(raw) {
        return parsed
            .into_iter()
            .filter_map(|value| value.as_str().map(|value| value.trim().to_uppercase()))
            .filter(|value| !value.is_empty())
            .collect();
    }

    raw.split(',')
        .filter_map(|part| {
            let part = part.trim();
            if part.is_empty() {
                None
            } else {
                Some(part.to_uppercase())
            }
        })
        .collect()
}

fn default_news_sources() -> Vec<NewsSourceConfig> {
    [
        "https://www.coindesk.com/arc/outboundfeeds/rss/",
        "https://cointelegraph.com/rss",
        "https://decrypt.co/feed",
        "https://crypto.news/feed",
        "https://news.bitcoin.com/feed",
        "https://feeds.bbci.co.uk/news/business/rss.xml",
        "https://rss.nytimes.com/services/xml/rss/nyt/Business.xml",
        "https://www.cnbc.com/id/100003114/device/rss/rss.html",
        "https://feeds.feedburner.com/TheHackersNews",
        "https://www.wired.com/feed/tag/ai/latest/rss",
    ]
    .into_iter()
    .map(|url| NewsSourceConfig {
        source_type: "rss".to_owned(),
        adapter: "rss_generic".to_owned(),
        url: url.to_owned(),
        enabled: true,
        interval_seconds: 300,
        config: json!({}),
    })
    .collect()
}

fn format_naive_iso(value: NaiveDateTime) -> String {
    value.format("%Y-%m-%dT%H:%M:%S%.f").to_string()
}

fn default_source_type() -> String {
    "rss".to_owned()
}

fn default_adapter() -> String {
    "rss_generic".to_owned()
}

fn default_enabled() -> bool {
    true
}

fn default_interval_seconds() -> i32 {
    300
}

fn default_article_hours() -> i64 {
    24
}

fn default_article_limit() -> i64 {
    20
}

#[cfg(test)]
mod tests {
    use super::{default_news_sources, parse_article_symbols, parse_symbol_filter};

    #[test]
    fn parses_news_symbols_from_json_or_csv() {
        assert_eq!(
            parse_article_symbols(Some("[\"btc\", \"ETH\"]")),
            vec!["BTC", "ETH"]
        );
        assert_eq!(parse_article_symbols(Some("btc, eth")), vec!["BTC", "ETH"]);
        assert!(parse_article_symbols(Some("")).is_empty());
    }

    #[test]
    fn parses_symbol_filter_uppercase() {
        let filter = parse_symbol_filter(Some("btc, eth"));
        assert!(filter.contains("BTC"));
        assert!(filter.contains("ETH"));
    }

    #[test]
    fn default_news_sources_match_legacy_count() {
        assert_eq!(default_news_sources().len(), 10);
    }
}
