use axum::{
    Json,
    extract::{Path, Query, State},
    http::{HeaderMap, HeaderName, HeaderValue},
    response::IntoResponse,
};
use chrono::Utc;
use serde::{Deserialize, Serialize};
use serde_json::Value;
use sqlx::Row;
use tracing::warn;

use crate::{error::AppError, state::AppState};

const MARKET_PRICE_SOURCE_HEADER: &str = "x-rust-market-price-source";
const MARKET_PRICES_SOURCE_HEADER: &str = "x-rust-market-prices-source";
const MARKET_PRICES_LEGACY_FALLBACK_COUNT_HEADER: &str =
    "x-rust-market-prices-legacy-fallback-count";
const MARKET_KLINE_SOURCE_HEADER: &str = "x-rust-market-kline-source";
const MARKET_KLINE_WITH_INDICATORS_SOURCE_HEADER: &str =
    "x-rust-market-kline-with-indicators-source";

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum MarketPriceSource {
    NativeDb,
    LegacyFallback,
}

impl MarketPriceSource {
    fn as_header_value(self) -> &'static str {
        match self {
            Self::NativeDb => "native-db",
            Self::LegacyFallback => "legacy-fallback",
        }
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum MarketPricesSource {
    NativeDb,
    LegacyFallback,
    Mixed,
}

impl MarketPricesSource {
    fn as_header_value(self) -> &'static str {
        match self {
            Self::NativeDb => "native-db",
            Self::LegacyFallback => "legacy-fallback",
            Self::Mixed => "mixed",
        }
    }
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct PriceResponse {
    symbol: String,
    market: String,
    price: f64,
    oracle_price: Option<f64>,
    change24h: Option<f64>,
    volume24h: Option<f64>,
    percentage24h: Option<f64>,
    open_interest: Option<f64>,
    funding_rate: Option<f64>,
    timestamp: i64,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct KlineItem {
    timestamp: i32,
    datetime: String,
    open: Option<f64>,
    high: Option<f64>,
    low: Option<f64>,
    close: Option<f64>,
    volume: Option<f64>,
    amount: Option<f64>,
    chg: Option<f64>,
    percent: Option<f64>,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct KlineResponse {
    symbol: String,
    market: String,
    period: String,
    count: usize,
    data: Vec<KlineItem>,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct MarketStatusResponse {
    symbol: String,
    market: Option<String>,
    market_status: String,
    timestamp: i64,
    current_time: String,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct KlineWithIndicatorsResponse {
    symbol: String,
    market: String,
    period: String,
    count: usize,
    klines: Vec<KlineItem>,
    indicators: Value,
}

#[derive(Deserialize)]
pub struct MarketQuery {
    #[serde(default = "default_market")]
    market: String,
}

#[derive(Deserialize)]
pub struct BatchPricesQuery {
    symbols: String,
    #[serde(default = "default_market")]
    market: String,
}

#[derive(Deserialize)]
pub struct KlineQuery {
    #[serde(default = "default_market")]
    market: String,
    #[serde(default = "default_period")]
    period: String,
    #[serde(default = "default_kline_count")]
    count: i64,
}

#[derive(Serialize)]
pub struct MarketHealthResponse {
    status: String,
    timestamp: i64,
    test_price: Value,
    message: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    error: Option<String>,
}

pub async fn get_market_price(
    State(state): State<AppState>,
    Path(symbol): Path<String>,
    Query(query): Query<MarketQuery>,
) -> Result<impl IntoResponse, AppError> {
    let market = query.market;
    let (response, source) = resolve_price_response(&state, &symbol, &market).await?;
    let mut headers = HeaderMap::new();
    headers.insert(
        HeaderName::from_static(MARKET_PRICE_SOURCE_HEADER),
        HeaderValue::from_static(source.as_header_value()),
    );
    Ok((headers, Json(response)))
}

pub async fn get_market_prices(
    State(state): State<AppState>,
    Query(query): Query<BatchPricesQuery>,
) -> Result<impl IntoResponse, AppError> {
    let symbols = query
        .symbols
        .split(',')
        .map(str::trim)
        .filter(|symbol| !symbol.is_empty())
        .map(str::to_owned)
        .collect::<Vec<_>>();
    if symbols.is_empty() {
        return Err(AppError::bad_request("crypto symbol list cannot be empty"));
    }
    if symbols.len() > 20 {
        return Err(AppError::bad_request("Maximum 20 crypto symbols supported"));
    }

    let mut prices = Vec::new();
    let mut native_success_count = 0usize;
    let mut legacy_fallback_symbols = Vec::new();
    let requested_symbols = symbols
        .iter()
        .map(|symbol| symbol.to_uppercase())
        .collect::<Vec<_>>();
    for symbol in symbols {
        match resolve_price_response(&state, &symbol, &query.market).await {
            Ok((price, source)) => {
                if matches!(source, MarketPriceSource::LegacyFallback) {
                    legacy_fallback_symbols.push(symbol.to_uppercase());
                } else {
                    native_success_count += 1;
                }
                prices.push(price);
            }
            Err(error) => {
                warn!(
                    route = "/api/market/prices",
                    symbol = %symbol.to_uppercase(),
                    market = %query.market,
                    error = %error.message,
                    "market batch price symbol resolution failed"
                );
            }
        }
    }

    if !legacy_fallback_symbols.is_empty() {
        warn!(
            route = "/api/market/prices",
            market = %query.market,
            requested_symbols = %requested_symbols.join(","),
            fallback_symbols = %legacy_fallback_symbols.join(","),
            fallback_count = legacy_fallback_symbols.len(),
            "market batch prices used legacy fallback"
        );
    }

    let source = if native_success_count > 0 && !legacy_fallback_symbols.is_empty() {
        MarketPricesSource::Mixed
    } else if !legacy_fallback_symbols.is_empty() {
        MarketPricesSource::LegacyFallback
    } else {
        MarketPricesSource::NativeDb
    };

    let mut headers = HeaderMap::new();
    headers.insert(
        HeaderName::from_static(MARKET_PRICES_SOURCE_HEADER),
        HeaderValue::from_static(source.as_header_value()),
    );
    let fallback_count_header = HeaderValue::from_str(&legacy_fallback_symbols.len().to_string())
        .map_err(|error| {
        AppError::internal(format!(
            "Failed to serialize legacy fallback count header: {error}"
        ))
    })?;
    headers.insert(
        HeaderName::from_static(MARKET_PRICES_LEGACY_FALLBACK_COUNT_HEADER),
        fallback_count_header,
    );

    Ok((headers, Json(prices)))
}

pub async fn get_market_kline(
    State(state): State<AppState>,
    Path(symbol): Path<String>,
    Query(query): Query<KlineQuery>,
) -> Result<impl IntoResponse, AppError> {
    validate_period(&query.period)?;
    if !(1..=500).contains(&query.count) {
        return Err(AppError::bad_request("Data count must be between 1-500"));
    }

    let (response, source) = resolve_kline_response(
        &state,
        &symbol,
        &query.market,
        &query.period,
        query.count as i32,
    )
    .await?;
    let mut headers = HeaderMap::new();
    headers.insert(
        HeaderName::from_static(MARKET_KLINE_SOURCE_HEADER),
        HeaderValue::from_static(source.as_header_value()),
    );

    Ok((headers, Json(response)))
}

pub async fn get_market_status(
    State(state): State<AppState>,
    Path(symbol): Path<String>,
    Query(query): Query<MarketQuery>,
) -> Result<Json<MarketStatusResponse>, AppError> {
    if normalize_exchange(&query.market).is_some() {
        return Ok(Json(MarketStatusResponse {
            symbol: symbol.to_uppercase(),
            market: Some(query.market),
            market_status: "TRADING".to_owned(),
            timestamp: Utc::now().timestamp_millis(),
            current_time: Utc::now().to_rfc3339(),
        }));
    }

    fallback_get_json(
        &state,
        &format!("/api/market/status/{}?market={}", symbol, query.market),
    )
    .await
}

pub async fn market_data_health(
    State(state): State<AppState>,
) -> Result<Json<MarketHealthResponse>, AppError> {
    match resolve_price_response(&state, "BTC", "hyperliquid").await {
        Ok((price, _)) => Ok(Json(MarketHealthResponse {
            status: "healthy".to_owned(),
            timestamp: Utc::now().timestamp_millis(),
            test_price: serde_json::json!({
                "symbol": "BTC",
                "price": price.price
            }),
            message: "Market data service is running normally".to_owned(),
            error: None,
        })),
        Err(error) => Ok(Json(MarketHealthResponse {
            status: "unhealthy".to_owned(),
            timestamp: Utc::now().timestamp_millis(),
            test_price: serde_json::json!({}),
            message: "Market data service abnormal".to_owned(),
            error: Some(error.message),
        })),
    }
}

pub async fn get_kline_with_indicators(
    State(state): State<AppState>,
    Path(symbol): Path<String>,
    Query(query): Query<KlineQueryWithIndicators>,
) -> Result<impl IntoResponse, AppError> {
    validate_period(&query.period)?;
    if !(1..=500).contains(&query.count) {
        return Err(AppError::bad_request("Data count must be between 1-500"));
    }

    let (response, source) = resolve_kline_with_indicators_response(
        &state,
        &symbol,
        &query.market,
        &query.period,
        query.count as i32,
        &query.indicators,
    )
    .await?;
    let mut headers = HeaderMap::new();
    headers.insert(
        HeaderName::from_static(MARKET_KLINE_WITH_INDICATORS_SOURCE_HEADER),
        HeaderValue::from_static(source.as_header_value()),
    );

    Ok((headers, Json(response)))
}

pub async fn get_available_indicators() -> Json<Value> {
    Json(serde_json::json!({
        "indicators": [
            {"name":"MA5","description":"5-period simple moving average"},
            {"name":"MA10","description":"10-period simple moving average"},
            {"name":"MA20","description":"20-period simple moving average"},
            {"name":"EMA20","description":"20-period exponential moving average"},
            {"name":"EMA50","description":"50-period exponential moving average"},
            {"name":"EMA100","description":"100-period exponential moving average"},
            {"name":"MACD","description":"Moving average convergence divergence"},
            {"name":"RSI14","description":"14-period RSI"},
            {"name":"RSI7","description":"7-period RSI"},
            {"name":"BOLL","description":"Bollinger bands"},
            {"name":"ATR14","description":"14-period average true range"},
            {"name":"VWAP","description":"Volume weighted average price"},
            {"name":"STOCH","description":"Stochastic oscillator"},
            {"name":"OBV","description":"On-balance volume"}
        ],
        "message": "Available indicators"
    }))
}

pub async fn get_crypto_symbols(
    State(state): State<AppState>,
) -> Result<Json<Vec<String>>, AppError> {
    let symbols = if let Some(hyperliquid_symbols) =
        load_available_symbol_names(&state, "hyperliquid_available_symbols").await?
    {
        hyperliquid_symbols
    } else {
        fallback_get_json::<Vec<String>>(&state, "/api/crypto/symbols")
            .await?
            .0
    };
    Ok(Json(symbols))
}

pub async fn get_crypto_price(
    State(state): State<AppState>,
    Path(symbol): Path<String>,
) -> Result<Json<Value>, AppError> {
    let (price, _) = resolve_price_response(&state, &symbol, "CRYPTO").await?;
    Ok(Json(serde_json::json!({
        "symbol": symbol.to_uppercase(),
        "price": price.price,
        "market": "CRYPTO"
    })))
}

pub async fn get_crypto_market_status(
    State(state): State<AppState>,
    Path(symbol): Path<String>,
) -> Result<Json<Value>, AppError> {
    let status = get_market_status(
        State(state),
        Path(symbol.clone()),
        Query(MarketQuery {
            market: "CRYPTO".to_owned(),
        }),
    )
    .await?;
    Ok(Json(serde_json::to_value(status.0).unwrap_or(Value::Null)))
}

pub async fn get_popular_cryptos(
    State(state): State<AppState>,
) -> Result<Json<Vec<Value>>, AppError> {
    let mut results = Vec::new();
    for symbol in ["BTC", "ETH", "SOL", "DOGE", "BNB", "XRP"] {
        if let Ok((price, _)) = resolve_price_response(&state, symbol, "CRYPTO").await {
            results.push(serde_json::json!({
                "symbol": symbol,
                "name": symbol,
                "price": price.price,
                "market": "CRYPTO"
            }));
        }
    }
    Ok(Json(results))
}

#[derive(Deserialize)]
pub struct KlineQueryWithIndicators {
    #[serde(default = "default_market")]
    market: String,
    #[serde(default = "default_indicator_period")]
    period: String,
    #[serde(default = "default_indicator_count")]
    count: i64,
    #[serde(default)]
    indicators: String,
}

async fn resolve_price_response(
    state: &AppState,
    symbol: &str,
    market: &str,
) -> Result<(PriceResponse, MarketPriceSource), AppError> {
    if let Some(exchange) = normalize_exchange(market) {
        if let Some(price) = load_price_from_db(state, symbol, market, exchange).await? {
            return Ok((price, MarketPriceSource::NativeDb));
        }
    }

    let legacy_path = format!("/api/market/price/{}?market={}", symbol, market);
    warn!(
        route = "/api/market/price/{symbol}",
        symbol = %symbol.to_uppercase(),
        market = %market,
        legacy_path = %legacy_path,
        "market price used legacy fallback"
    );

    Ok((
        fallback_get_json(state, &legacy_path).await?.0,
        MarketPriceSource::LegacyFallback,
    ))
}

async fn resolve_kline_response(
    state: &AppState,
    symbol: &str,
    market: &str,
    period: &str,
    count: i32,
) -> Result<(KlineResponse, MarketPriceSource), AppError> {
    if let Some(exchange) = normalize_exchange(market)
        && let Some(data) = load_kline_rows(state, symbol, exchange, period, count).await?
    {
        return Ok((
            KlineResponse {
                symbol: symbol.to_uppercase(),
                market: market.to_owned(),
                period: period.to_owned(),
                count: data.len(),
                data,
            },
            MarketPriceSource::NativeDb,
        ));
    }

    let legacy_path = format!(
        "/api/market/kline/{}?market={}&period={}&count={}",
        symbol, market, period, count
    );
    let fallback_reason = if normalize_exchange(market).is_some() {
        "native-db-miss"
    } else {
        "unsupported-market"
    };
    warn!(
        route = "/api/market/kline/{symbol}",
        symbol = %symbol.to_uppercase(),
        market = %market,
        period = %period,
        count,
        fallback_reason,
        legacy_path = %legacy_path,
        "market kline used legacy fallback"
    );

    Ok((
        fallback_get_json(state, &legacy_path).await?.0,
        MarketPriceSource::LegacyFallback,
    ))
}

async fn resolve_kline_with_indicators_response(
    state: &AppState,
    symbol: &str,
    market: &str,
    period: &str,
    count: i32,
    indicators: &str,
) -> Result<(KlineWithIndicatorsResponse, MarketPriceSource), AppError> {
    let legacy_path = format!(
        "/api/market/kline-with-indicators/{}?market={}&period={}&count={}&indicators={}",
        symbol, market, period, count, indicators
    );
    let fallback_reason = if normalize_exchange(market).is_some() {
        "legacy-indicator-compute"
    } else {
        "unsupported-market"
    };
    warn!(
        route = "/api/market/kline-with-indicators/{symbol}",
        symbol = %symbol.to_uppercase(),
        market = %market,
        period = %period,
        count,
        indicators = %indicators,
        fallback_reason,
        legacy_path = %legacy_path,
        "market kline-with-indicators used legacy fallback"
    );

    Ok((
        fallback_get_json(state, &legacy_path).await?.0,
        MarketPriceSource::LegacyFallback,
    ))
}

async fn load_price_from_db(
    state: &AppState,
    symbol: &str,
    market: &str,
    exchange: &str,
) -> Result<Option<PriceResponse>, AppError> {
    let symbol = symbol.to_uppercase();
    let latest_kline = sqlx::query(
        r#"
        SELECT close_price::float8 AS close_price, timestamp, percent::float8 AS percent, change::float8 AS change
        FROM crypto_klines
        WHERE exchange = $1
          AND symbol = $2
          AND period = '1m'
          AND environment = 'mainnet'
        ORDER BY timestamp DESC
        LIMIT 1
        "#,
    )
    .bind(exchange)
    .bind(&symbol)
    .fetch_optional(&state.db)
    .await
    .map_err(|error| AppError::internal(format!("Failed to load market price: {error}")))?;

    let latest_asset = sqlx::query(
        r#"
        SELECT oracle_price::float8 AS oracle_price,
               open_interest::float8 AS open_interest,
               funding_rate::float8 AS funding_rate,
               day_notional_volume::float8 AS day_notional_volume
        FROM market_asset_metrics
        WHERE exchange = $1
          AND symbol = $2
        ORDER BY timestamp DESC
        LIMIT 1
        "#,
    )
    .bind(exchange)
    .bind(&symbol)
    .fetch_optional(&state.db)
    .await
    .map_err(|error| AppError::internal(format!("Failed to load market asset metrics: {error}")))?;

    if latest_kline.is_none() && latest_asset.is_none() {
        return Ok(None);
    }

    let price = latest_kline
        .as_ref()
        .and_then(|row| row.try_get::<Option<f64>, _>("close_price").ok().flatten())
        .or_else(|| {
            latest_asset
                .as_ref()
                .and_then(|row| row.try_get::<Option<f64>, _>("oracle_price").ok().flatten())
        })
        .unwrap_or(0.0);

    Ok(Some(PriceResponse {
        symbol,
        market: market_label(market),
        price,
        oracle_price: latest_asset
            .as_ref()
            .and_then(|row| row.try_get::<Option<f64>, _>("oracle_price").ok().flatten()),
        change24h: latest_kline
            .as_ref()
            .and_then(|row| row.try_get::<Option<f64>, _>("change").ok().flatten())
            .or(Some(0.0)),
        volume24h: latest_asset
            .as_ref()
            .and_then(|row| {
                row.try_get::<Option<f64>, _>("day_notional_volume")
                    .ok()
                    .flatten()
            })
            .or(Some(0.0)),
        percentage24h: latest_kline
            .as_ref()
            .and_then(|row| row.try_get::<Option<f64>, _>("percent").ok().flatten())
            .or(Some(0.0)),
        open_interest: latest_asset
            .as_ref()
            .and_then(|row| {
                row.try_get::<Option<f64>, _>("open_interest")
                    .ok()
                    .flatten()
            })
            .or(Some(0.0)),
        funding_rate: latest_asset
            .as_ref()
            .and_then(|row| row.try_get::<Option<f64>, _>("funding_rate").ok().flatten())
            .or(Some(0.0)),
        timestamp: Utc::now().timestamp_millis(),
    }))
}

async fn load_kline_rows(
    state: &AppState,
    symbol: &str,
    exchange: &str,
    period: &str,
    count: i32,
) -> Result<Option<Vec<KlineItem>>, AppError> {
    let rows = sqlx::query(
        r#"
        SELECT timestamp, datetime_str,
               open_price::float8 AS open_price,
               high_price::float8 AS high_price,
               low_price::float8 AS low_price,
               close_price::float8 AS close_price,
               volume::float8 AS volume,
               amount::float8 AS amount,
               change::float8 AS change,
               percent::float8 AS percent
        FROM crypto_klines
        WHERE exchange = $1
          AND symbol = $2
          AND period = $3
          AND environment = 'mainnet'
        ORDER BY timestamp DESC
        LIMIT $4
        "#,
    )
    .bind(exchange)
    .bind(symbol.to_uppercase())
    .bind(period)
    .bind(count)
    .fetch_all(&state.db)
    .await
    .map_err(|error| AppError::internal(format!("Failed to load kline data: {error}")))?;

    if rows.is_empty() {
        return Ok(None);
    }

    let mut items = rows
        .into_iter()
        .map(|row| {
            Ok(KlineItem {
                timestamp: row.try_get("timestamp").map_err(read_market_error)?,
                datetime: row.try_get("datetime_str").map_err(read_market_error)?,
                open: row.try_get("open_price").map_err(read_market_error)?,
                high: row.try_get("high_price").map_err(read_market_error)?,
                low: row.try_get("low_price").map_err(read_market_error)?,
                close: row.try_get("close_price").map_err(read_market_error)?,
                volume: row.try_get("volume").map_err(read_market_error)?,
                amount: row.try_get("amount").map_err(read_market_error)?,
                chg: row.try_get("change").map_err(read_market_error)?,
                percent: row.try_get("percent").map_err(read_market_error)?,
            })
        })
        .collect::<Result<Vec<_>, AppError>>()?;

    items.reverse();
    Ok(Some(items))
}

async fn load_available_symbol_names(
    state: &AppState,
    key: &str,
) -> Result<Option<Vec<String>>, AppError> {
    let value = sqlx::query_scalar::<_, Option<String>>(
        "SELECT value FROM system_configs WHERE key = $1 LIMIT 1",
    )
    .bind(key)
    .fetch_optional(&state.db)
    .await
    .map_err(|error| AppError::internal(format!("Failed to load symbol config: {error}")))?;
    let Some(raw) = value.flatten() else {
        return Ok(None);
    };
    let symbols = serde_json::from_str::<Vec<Value>>(&raw)
        .ok()
        .map(|items| {
            items
                .into_iter()
                .filter_map(|item| {
                    item.get("symbol")
                        .and_then(Value::as_str)
                        .map(str::to_owned)
                })
                .collect::<Vec<_>>()
        })
        .unwrap_or_default();
    if symbols.is_empty() {
        Ok(None)
    } else {
        Ok(Some(symbols))
    }
}

async fn fallback_get_json<T: for<'de> serde::Deserialize<'de>>(
    state: &AppState,
    path: &str,
) -> Result<Json<T>, AppError> {
    let response = state
        .client
        .get(state.config.legacy_http_target(path))
        .send()
        .await
        .map_err(|error| AppError::bad_gateway(format!("legacy market request failed: {error}")))?;
    let status = response.status();
    if !status.is_success() {
        return Err(AppError::bad_gateway(format!(
            "legacy market request failed with status {status}"
        )));
    }
    let body = response.json::<T>().await.map_err(|error| {
        AppError::bad_gateway(format!("legacy market response parse failed: {error}"))
    })?;
    Ok(Json(body))
}

fn normalize_exchange(market: &str) -> Option<&'static str> {
    match market.to_ascii_lowercase().as_str() {
        "hyperliquid" | "crypto" | "crYPTO" => Some("hyperliquid"),
        "binance" => Some("binance"),
        _ => None,
    }
}

fn market_label(market: &str) -> String {
    market.to_owned()
}

fn validate_period(period: &str) -> Result<(), AppError> {
    let valid = [
        "1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "8h", "12h", "1d", "3d", "1w", "1M",
    ];
    if valid.contains(&period) {
        Ok(())
    } else {
        Err(AppError::bad_request(format!(
            "Unsupported time period, supported periods: {}",
            valid.join(", ")
        )))
    }
}

fn default_market() -> String {
    "hyperliquid".to_owned()
}

fn default_period() -> String {
    "1m".to_owned()
}

fn default_kline_count() -> i64 {
    100
}

fn default_indicator_period() -> String {
    "1h".to_owned()
}

fn default_indicator_count() -> i64 {
    500
}

fn read_market_error(error: sqlx::Error) -> AppError {
    AppError::internal(format!("Failed to read market data: {error}"))
}

#[cfg(test)]
mod tests {
    use super::{
        MarketPriceSource, MarketPricesSource, default_indicator_count, default_indicator_period,
        normalize_exchange, validate_period,
    };

    #[test]
    fn market_normalization_prefers_supported_exchanges() {
        assert_eq!(normalize_exchange("hyperliquid"), Some("hyperliquid"));
        assert_eq!(normalize_exchange("CRYPTO"), Some("hyperliquid"));
        assert_eq!(normalize_exchange("binance"), Some("binance"));
        assert_eq!(normalize_exchange("US"), None);
    }

    #[test]
    fn period_validation_matches_legacy_list() {
        assert!(validate_period("1h").is_ok());
        assert!(validate_period("10m").is_err());
        assert_eq!(default_indicator_count(), 500);
        assert_eq!(default_indicator_period(), "1h");
    }

    #[test]
    fn market_price_source_header_values_are_stable() {
        assert_eq!(MarketPriceSource::NativeDb.as_header_value(), "native-db");
        assert_eq!(
            MarketPriceSource::LegacyFallback.as_header_value(),
            "legacy-fallback"
        );
    }

    #[test]
    fn market_batch_price_source_header_values_are_stable() {
        assert_eq!(MarketPricesSource::NativeDb.as_header_value(), "native-db");
        assert_eq!(
            MarketPricesSource::LegacyFallback.as_header_value(),
            "legacy-fallback"
        );
        assert_eq!(MarketPricesSource::Mixed.as_header_value(), "mixed");
    }
}
