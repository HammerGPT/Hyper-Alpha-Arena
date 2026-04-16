use axum::{
    Json,
    extract::{Query, State},
};
use chrono::{Duration, Local};
use serde::{Deserialize, Serialize};

use crate::{error::AppError, state::AppState};

#[derive(Serialize)]
pub struct RankingFactorsResponse {
    success: bool,
    factors: Vec<FactorDefinition>,
    all_columns: Vec<FactorColumn>,
}

#[derive(Clone, Serialize)]
pub struct FactorDefinition {
    id: &'static str,
    name: &'static str,
    description: &'static str,
    columns: Vec<FactorColumn>,
}

#[derive(Clone, Serialize)]
pub struct FactorColumn {
    key: &'static str,
    label: &'static str,
    #[serde(rename = "type")]
    column_type: &'static str,
    sortable: bool,
}

#[derive(Deserialize)]
pub struct RankingSymbolsQuery {
    #[serde(default = "default_days")]
    days: i64,
}

#[derive(Serialize)]
pub struct RankingSymbolsResponse {
    success: bool,
    symbols: Vec<String>,
    count: usize,
    data_period: String,
}

pub async fn get_available_factors() -> Json<RankingFactorsResponse> {
    Json(build_factors_response())
}

pub async fn get_available_symbols(
    State(state): State<AppState>,
    Query(query): Query<RankingSymbolsQuery>,
) -> Result<Json<RankingSymbolsResponse>, AppError> {
    let days = query.days.max(0);
    let end_date = Local::now().date_naive();
    let start_date = end_date - Duration::days(days);
    let start = start_date.format("%Y-%m-%d").to_string();
    let end = end_date.format("%Y-%m-%d").to_string();

    let symbols = sqlx::query_scalar::<_, String>(
        r#"
        SELECT DISTINCT symbol
        FROM crypto_klines
        WHERE period = '1d'
          AND datetime_str >= $1
          AND datetime_str <= $2
        ORDER BY symbol
        "#,
    )
    .bind(&start)
    .bind(&end)
    .fetch_all(&state.db)
    .await
    .map_err(|error| AppError::internal(format!("Failed to get ranking symbols: {error}")))?;

    Ok(Json(RankingSymbolsResponse {
        success: true,
        count: symbols.len(),
        symbols,
        data_period: format!("{start} to {end}"),
    }))
}

fn build_factors_response() -> RankingFactorsResponse {
    let factors = vec![
        FactorDefinition {
            id: "momentum",
            name: "Momentum",
            description: "Momentum: (later-period low - earlier-period low) / longest candle, sorted descending",
            columns: vec![
                FactorColumn {
                    key: "Momentum",
                    label: "Momentum",
                    column_type: "number",
                    sortable: true,
                },
                FactorColumn {
                    key: "Momentum Score",
                    label: "Momentum Score",
                    column_type: "score",
                    sortable: true,
                },
            ],
        },
        FactorDefinition {
            id: "support",
            name: "Support",
            description: "Support strength based on distance from largest candle within 30 days; higher is better",
            columns: vec![
                FactorColumn {
                    key: "Support",
                    label: "Support",
                    column_type: "number",
                    sortable: true,
                },
                FactorColumn {
                    key: "Support Score",
                    label: "Support Score",
                    column_type: "score",
                    sortable: true,
                },
                FactorColumn {
                    key: "Days From Longest Candle",
                    label: "30 Days From Longest Candle",
                    column_type: "number",
                    sortable: true,
                },
            ],
        },
    ];

    let mut all_columns = factors
        .iter()
        .flat_map(|factor| factor.columns.clone())
        .collect::<Vec<_>>();
    all_columns.push(FactorColumn {
        key: "Composite Score",
        label: "Composite Score",
        column_type: "score",
        sortable: true,
    });

    RankingFactorsResponse {
        success: true,
        factors,
        all_columns,
    }
}

fn default_days() -> i64 {
    100
}

#[cfg(test)]
mod tests {
    use super::{build_factors_response, default_days};

    #[test]
    fn available_factors_match_current_python_definitions() {
        let response = build_factors_response();

        assert!(response.success);
        assert_eq!(response.factors.len(), 2);
        assert_eq!(response.factors[0].id, "momentum");
        assert_eq!(response.factors[1].id, "support");
        assert!(
            response
                .all_columns
                .iter()
                .any(|column| column.key == "Composite Score")
        );
    }

    #[test]
    fn ranking_symbols_default_days_matches_legacy_route() {
        assert_eq!(default_days(), 100);
    }
}
