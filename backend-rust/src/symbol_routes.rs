use axum::{Json, extract::State};
use chrono::NaiveDateTime;
use serde::{Deserialize, Serialize};
use sqlx::Row;
use std::collections::HashSet;

use crate::{error::AppError, state::AppState};

const MAX_WATCHLIST_SYMBOLS: usize = 10;

const HYPERLIQUID_AVAILABLE_KEY: &str = "hyperliquid_available_symbols";
const HYPERLIQUID_SELECTED_KEY: &str = "hyperliquid_selected_symbols";
const BINANCE_AVAILABLE_KEY: &str = "binance_available_symbols";
const BINANCE_SELECTED_KEY: &str = "binance_selected_symbols";

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq, Eq)]
pub struct SymbolMeta {
    symbol: String,
    #[serde(default)]
    name: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    #[serde(rename = "type")]
    symbol_type: Option<String>,
}

#[derive(Serialize)]
pub struct HyperliquidAvailableSymbolsResponse {
    symbols: Vec<SymbolMeta>,
    updated_at: Option<String>,
    max_symbols: usize,
}

#[derive(Serialize)]
pub struct BinanceAvailableSymbolsResponse {
    symbols: Vec<SymbolMeta>,
    count: usize,
    max_symbols: usize,
}

#[derive(Serialize)]
pub struct WatchlistResponse {
    symbols: Vec<String>,
    max_symbols: usize,
}

pub async fn get_hyperliquid_available_symbols(
    State(state): State<AppState>,
) -> Result<Json<HyperliquidAvailableSymbolsResponse>, AppError> {
    let (symbols, updated_at) = load_symbol_meta_config(&state, HYPERLIQUID_AVAILABLE_KEY).await?;
    let symbols = non_empty_symbols_or_default(symbols);

    Ok(Json(HyperliquidAvailableSymbolsResponse {
        symbols,
        updated_at,
        max_symbols: MAX_WATCHLIST_SYMBOLS,
    }))
}

pub async fn get_binance_available_symbols(
    State(state): State<AppState>,
) -> Result<Json<BinanceAvailableSymbolsResponse>, AppError> {
    let (symbols, _) = load_symbol_meta_config(&state, BINANCE_AVAILABLE_KEY).await?;
    let symbols = non_empty_symbols_or_default(symbols);

    Ok(Json(BinanceAvailableSymbolsResponse {
        count: symbols.len(),
        symbols,
        max_symbols: MAX_WATCHLIST_SYMBOLS,
    }))
}

pub async fn get_hyperliquid_watchlist(
    State(state): State<AppState>,
) -> Result<Json<WatchlistResponse>, AppError> {
    let (available, _) = load_symbol_meta_config(&state, HYPERLIQUID_AVAILABLE_KEY).await?;
    let available = non_empty_symbols_or_default(available);
    let raw = load_config_value(&state, HYPERLIQUID_SELECTED_KEY).await?;
    let symbols = hyperliquid_watchlist_from_config(raw.as_deref(), &available);

    Ok(Json(WatchlistResponse {
        symbols,
        max_symbols: MAX_WATCHLIST_SYMBOLS,
    }))
}

pub async fn get_binance_watchlist(
    State(state): State<AppState>,
) -> Result<Json<WatchlistResponse>, AppError> {
    let (available, _) = load_symbol_meta_config(&state, BINANCE_AVAILABLE_KEY).await?;
    let available = non_empty_symbols_or_default(available);
    let raw = load_config_value(&state, BINANCE_SELECTED_KEY).await?;
    let hl_raw = load_config_value(&state, HYPERLIQUID_SELECTED_KEY).await?;
    let symbols = binance_watchlist_from_config(raw.as_deref(), hl_raw.as_deref(), &available);

    Ok(Json(WatchlistResponse {
        symbols,
        max_symbols: MAX_WATCHLIST_SYMBOLS,
    }))
}

async fn load_symbol_meta_config(
    state: &AppState,
    key: &str,
) -> Result<(Vec<SymbolMeta>, Option<String>), AppError> {
    let Some(row) =
        sqlx::query("SELECT value, updated_at FROM system_configs WHERE key = $1 LIMIT 1")
            .bind(key)
            .fetch_optional(&state.db)
            .await
            .map_err(|error| {
                AppError::internal(format!("Failed to load symbol config: {error}"))
            })?
    else {
        return Ok((Vec::new(), None));
    };

    let raw = row
        .try_get::<Option<String>, _>("value")
        .map_err(|error| AppError::internal(format!("Failed to read symbol config: {error}")))?;
    let updated_at = row
        .try_get::<Option<NaiveDateTime>, _>("updated_at")
        .map_err(|error| AppError::internal(format!("Failed to read symbol config: {error}")))?
        .map(format_naive_iso);

    Ok((parse_symbol_meta_json(raw.as_deref()), updated_at))
}

async fn load_config_value(state: &AppState, key: &str) -> Result<Option<String>, AppError> {
    sqlx::query_scalar::<_, Option<String>>(
        "SELECT value FROM system_configs WHERE key = $1 LIMIT 1",
    )
    .bind(key)
    .fetch_optional(&state.db)
    .await
    .map(|value| value.flatten())
    .map_err(|error| AppError::internal(format!("Failed to load config value: {error}")))
}

fn parse_symbol_meta_json(value: Option<&str>) -> Vec<SymbolMeta> {
    let Some(raw) = value.map(str::trim).filter(|value| !value.is_empty()) else {
        return Vec::new();
    };

    serde_json::from_str::<Vec<serde_json::Value>>(raw)
        .map(|items| {
            items
                .into_iter()
                .filter_map(|item| {
                    let symbol = item.get("symbol")?.as_str()?.trim().to_uppercase();
                    if symbol.is_empty() {
                        return None;
                    }
                    let name = item
                        .get("name")
                        .and_then(|value| value.as_str())
                        .unwrap_or(&symbol)
                        .to_owned();
                    let symbol_type = item
                        .get("type")
                        .or_else(|| item.get("category"))
                        .and_then(|value| value.as_str())
                        .map(str::to_owned);
                    Some(SymbolMeta {
                        symbol,
                        name,
                        symbol_type,
                    })
                })
                .collect()
        })
        .unwrap_or_default()
}

fn parse_symbol_list_json(value: Option<&str>) -> Option<Vec<String>> {
    let raw = value?.trim();
    if raw.is_empty() {
        return Some(Vec::new());
    }
    serde_json::from_str::<Vec<serde_json::Value>>(raw)
        .ok()
        .map(|values| {
            values
                .into_iter()
                .filter_map(|value| value.as_str().map(|value| value.trim().to_uppercase()))
                .filter(|value| !value.is_empty())
                .collect()
        })
}

fn hyperliquid_watchlist_from_config(raw: Option<&str>, available: &[SymbolMeta]) -> Vec<String> {
    let available_set = available_symbols_set(available);
    if let Some(selected) = parse_symbol_list_json(raw) {
        let filtered = selected
            .into_iter()
            .filter(|symbol| available_set.contains(symbol))
            .take(MAX_WATCHLIST_SYMBOLS)
            .collect::<Vec<_>>();
        if !filtered.is_empty() {
            return filtered;
        }
        if raw.is_some() {
            return Vec::new();
        }
    }

    available
        .iter()
        .take(MAX_WATCHLIST_SYMBOLS)
        .map(|item| item.symbol.clone())
        .collect()
}

fn binance_watchlist_from_config(
    raw: Option<&str>,
    hyperliquid_raw: Option<&str>,
    available: &[SymbolMeta],
) -> Vec<String> {
    let available_set = available_symbols_set(available);
    if let Some(selected) = parse_symbol_list_json(raw) {
        let filtered = dedupe_valid_symbols(selected, &available_set, MAX_WATCHLIST_SYMBOLS);
        if !filtered.is_empty() {
            return filtered;
        }
    }

    if let Some(hl_selected) = parse_symbol_list_json(hyperliquid_raw) {
        let filtered = dedupe_valid_symbols(hl_selected, &available_set, MAX_WATCHLIST_SYMBOLS);
        if !filtered.is_empty() {
            return filtered;
        }
    }

    if available_set.contains("BTC") {
        vec!["BTC".to_owned()]
    } else {
        available
            .iter()
            .take(3)
            .map(|item| item.symbol.clone())
            .collect()
    }
}

fn dedupe_valid_symbols(
    symbols: Vec<String>,
    available_set: &HashSet<String>,
    limit: usize,
) -> Vec<String> {
    let mut seen = HashSet::new();
    symbols
        .into_iter()
        .filter(|symbol| available_set.contains(symbol) && seen.insert(symbol.clone()))
        .take(limit)
        .collect()
}

fn available_symbols_set(available: &[SymbolMeta]) -> HashSet<String> {
    available.iter().map(|item| item.symbol.clone()).collect()
}

fn non_empty_symbols_or_default(symbols: Vec<SymbolMeta>) -> Vec<SymbolMeta> {
    if symbols.is_empty() {
        vec![SymbolMeta {
            symbol: "BTC".to_owned(),
            name: "Bitcoin".to_owned(),
            symbol_type: None,
        }]
    } else {
        symbols
    }
}

fn format_naive_iso(value: NaiveDateTime) -> String {
    value.format("%Y-%m-%dT%H:%M:%S%.f").to_string()
}

#[cfg(test)]
mod tests {
    use super::{
        SymbolMeta, binance_watchlist_from_config, hyperliquid_watchlist_from_config,
        parse_symbol_meta_json,
    };

    #[test]
    fn parses_symbol_meta_from_config_json() {
        let symbols =
            parse_symbol_meta_json(Some(r#"[{"symbol":"btc","name":"Bitcoin","type":"perp"}]"#));
        assert_eq!(
            symbols,
            vec![SymbolMeta {
                symbol: "BTC".to_owned(),
                name: "Bitcoin".to_owned(),
                symbol_type: Some("perp".to_owned()),
            }]
        );
    }

    #[test]
    fn hyperliquid_empty_saved_watchlist_stays_empty() {
        let available = vec![btc()];
        assert!(hyperliquid_watchlist_from_config(Some("[]"), &available).is_empty());
    }

    #[test]
    fn binance_can_initialize_from_hyperliquid_watchlist() {
        let available = vec![btc(), eth()];
        assert_eq!(
            binance_watchlist_from_config(None, Some(r#"["ETH","SOL"]"#), &available),
            vec!["ETH"]
        );
    }

    fn btc() -> SymbolMeta {
        SymbolMeta {
            symbol: "BTC".to_owned(),
            name: "Bitcoin".to_owned(),
            symbol_type: None,
        }
    }

    fn eth() -> SymbolMeta {
        SymbolMeta {
            symbol: "ETH".to_owned(),
            name: "Ethereum".to_owned(),
            symbol_type: None,
        }
    }
}
