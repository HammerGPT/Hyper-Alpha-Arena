use chrono::{NaiveDateTime, Utc};
use futures_util::{SinkExt, StreamExt};
use serde_json::{Map, Value, json};
use sqlx::Row;
use std::{
    collections::{BTreeSet, HashSet, VecDeque},
    sync::{
        Arc, LazyLock,
        atomic::{AtomicBool, Ordering},
    },
};
use tokio::{
    sync::{Mutex, Notify, RwLock},
    task::JoinHandle,
    time::{Duration, sleep},
};
use tokio_tungstenite::{connect_async, tungstenite::Message};
use tracing::warn;
use url::form_urlencoded::byte_serialize;

use crate::signal_routes::project_wallet_trigger_into_runtime_states;

const HYPER_INSIGHT_WS_URL: &str = "wss://hyper.akooi.com/ws/events";
const WALLET_TRACKING_SOURCE: &str = "wallet_tracking";
const WALLET_TRIGGER_SYMBOL: &str = "WALLET";
const MAX_RECENT_EVENT_KEYS: usize = 4096;
const WS_IDLE_TIMEOUT: Duration = Duration::from_secs(30);
const WS_MIN_BACKOFF: Duration = Duration::from_secs(1);
const WS_MAX_BACKOFF: Duration = Duration::from_secs(30);
const CONFIG_ENABLED_KEY: &str = "hyper_insight_wallet_enabled";
const CONFIG_ACCESS_TOKEN_KEY: &str = "hyper_insight_wallet_access_token";

#[derive(Clone, Debug)]
pub struct WalletTrackingRuntimeSnapshot {
    pub status: String,
    pub tier: Option<String>,
    pub synced_addresses: Vec<String>,
    pub last_connected_at: Option<String>,
    pub last_message_at: Option<String>,
    pub last_event_at: Option<String>,
    pub last_error: Option<String>,
}

impl Default for WalletTrackingRuntimeSnapshot {
    fn default() -> Self {
        Self {
            status: "disabled".to_owned(),
            tier: None,
            synced_addresses: Vec::new(),
            last_connected_at: None,
            last_message_at: None,
            last_event_at: None,
            last_error: None,
        }
    }
}

#[derive(Default)]
struct RuntimeLifecycle {
    task: Option<JoinHandle<()>>,
}

struct RuntimeConfig {
    enabled: bool,
    access_token: String,
}

enum RunExit {
    Refresh,
    Shutdown,
    Disconnected,
}

#[derive(Default)]
struct RecentEventCache {
    keys: VecDeque<String>,
    set: HashSet<String>,
}

impl RecentEventCache {
    fn insert_or_is_duplicate(&mut self, key: String) -> bool {
        if self.set.contains(&key) {
            return true;
        }

        if self.keys.len() >= MAX_RECENT_EVENT_KEYS
            && let Some(oldest) = self.keys.pop_front()
        {
            self.set.remove(&oldest);
        }

        self.keys.push_back(key.clone());
        self.set.insert(key);
        false
    }
}

struct WalletTrackingRuntimeService {
    state: RwLock<WalletTrackingRuntimeSnapshot>,
    lifecycle: Mutex<RuntimeLifecycle>,
    refresh_notify: Notify,
    shutdown_notify: Notify,
    shutdown_requested: AtomicBool,
    recent_events: Mutex<RecentEventCache>,
}

impl WalletTrackingRuntimeService {
    fn new() -> Self {
        Self {
            state: RwLock::new(WalletTrackingRuntimeSnapshot::default()),
            lifecycle: Mutex::new(RuntimeLifecycle::default()),
            refresh_notify: Notify::new(),
            shutdown_notify: Notify::new(),
            shutdown_requested: AtomicBool::new(false),
            recent_events: Mutex::new(RecentEventCache::default()),
        }
    }

    async fn start(self: &Arc<Self>, db: sqlx::PgPool) {
        self.shutdown_requested.store(false, Ordering::SeqCst);

        let mut lifecycle = self.lifecycle.lock().await;
        if lifecycle
            .task
            .as_ref()
            .is_some_and(|task| !task.is_finished())
        {
            self.refresh_notify.notify_waiters();
            return;
        }

        let service = Arc::clone(self);
        lifecycle.task = Some(tokio::spawn(async move {
            service.run_loop(db).await;
        }));

        self.refresh_notify.notify_waiters();
    }

    async fn shutdown(&self) {
        self.shutdown_requested.store(true, Ordering::SeqCst);
        self.shutdown_notify.notify_waiters();
        self.refresh_notify.notify_waiters();

        let task = {
            let mut lifecycle = self.lifecycle.lock().await;
            lifecycle.task.take()
        };
        if let Some(task) = task {
            let _ = task.await;
        }
    }

    fn request_refresh(&self) {
        self.refresh_notify.notify_waiters();
    }

    async fn snapshot(&self) -> WalletTrackingRuntimeSnapshot {
        self.state.read().await.clone()
    }

    async fn run_loop(self: Arc<Self>, db: sqlx::PgPool) {
        let mut backoff = WS_MIN_BACKOFF;
        while !self.shutdown_requested.load(Ordering::SeqCst) {
            let runtime = match load_runtime_config(&db).await {
                Ok(runtime) => runtime,
                Err(error) => {
                    self.set_terminal_error_state(error).await;
                    if self.wait_for_signal(Some(backoff)).await {
                        break;
                    }
                    backoff = increase_backoff(backoff);
                    continue;
                }
            };

            self.apply_idle_state(&runtime).await;
            if !runtime.enabled || runtime.access_token.trim().is_empty() {
                if self.wait_for_signal(None).await {
                    break;
                }
                backoff = WS_MIN_BACKOFF;
                continue;
            }

            match self.connect_once(&db, runtime.access_token.trim()).await {
                Ok(RunExit::Refresh) => {
                    backoff = WS_MIN_BACKOFF;
                }
                Ok(RunExit::Shutdown) => break,
                Ok(RunExit::Disconnected) => {
                    backoff = WS_MIN_BACKOFF;
                }
                Err(error) => {
                    self.set_terminal_error_state(error).await;
                    if self.wait_for_signal(Some(backoff)).await {
                        break;
                    }
                    backoff = increase_backoff(backoff);
                }
            }
        }
    }

    async fn connect_once(&self, db: &sqlx::PgPool, access_token: &str) -> Result<RunExit, String> {
        {
            let mut state = self.state.write().await;
            state.status = "connecting".to_owned();
            state.last_error = None;
        }

        let encoded_token: String = byte_serialize(access_token.as_bytes()).collect();
        let ws_url = format!("{HYPER_INSIGHT_WS_URL}?token={encoded_token}");
        let (mut ws, _) = connect_async(ws_url.as_str()).await.map_err(|error| {
            format!("Failed to connect Hyper Insight runtime websocket: {error}")
        })?;

        {
            let mut state = self.state.write().await;
            state.status = "connected".to_owned();
            state.last_connected_at = Some(format_utc_iso(Utc::now().naive_utc()));
            state.last_error = None;
        }

        loop {
            tokio::select! {
                _ = self.shutdown_notify.notified() => return Ok(RunExit::Shutdown),
                _ = self.refresh_notify.notified() => return Ok(RunExit::Refresh),
                _ = sleep(WS_IDLE_TIMEOUT) => continue,
                next_message = ws.next() => {
                    let next_message = match next_message {
                        Some(message) => message.map_err(|error| format!("Hyper Insight runtime websocket receive failed: {error}"))?,
                        None => return Ok(RunExit::Disconnected),
                    };

                    self.touch_last_message().await;
                    match next_message {
                        Message::Text(text) => {
                            self.handle_runtime_text_message(db, &mut ws, text.as_ref()).await?;
                        }
                        Message::Ping(payload) => {
                            ws.send(Message::Pong(payload))
                                .await
                                .map_err(|error| format!("Hyper Insight runtime websocket pong send failed: {error}"))?;
                        }
                        Message::Close(_) => return Ok(RunExit::Disconnected),
                        Message::Binary(_) | Message::Pong(_) | Message::Frame(_) => {}
                    }
                }
            }
        }
    }

    async fn handle_runtime_text_message(
        &self,
        db: &sqlx::PgPool,
        ws: &mut tokio_tungstenite::WebSocketStream<
            tokio_tungstenite::MaybeTlsStream<tokio::net::TcpStream>,
        >,
        raw_message: &str,
    ) -> Result<(), String> {
        let parsed: Value = serde_json::from_str(raw_message)
            .map_err(|error| format!("Invalid Hyper Insight runtime payload: {error}"))?;
        let Some(payload) = parsed.as_object() else {
            return Ok(());
        };

        match classify_runtime_payload(payload) {
            RuntimePayloadKind::Connected {
                tier,
                synced_addresses,
            } => {
                let mut state = self.state.write().await;
                state.tier = tier;
                state.synced_addresses = synced_addresses;
                state.status = "connected".to_owned();
                state.last_error = None;
            }
            RuntimePayloadKind::SubscriptionUpdate { address, action } => {
                let mut state = self.state.write().await;
                let mut addresses = BTreeSet::from_iter(state.synced_addresses.drain(..));
                if let Some(address) = address.filter(|value| !value.trim().is_empty()) {
                    match action.as_deref() {
                        Some("added") => {
                            addresses.insert(address.to_lowercase());
                        }
                        Some("removed") => {
                            addresses.remove(&address.to_lowercase());
                        }
                        _ => {}
                    }
                }
                state.synced_addresses = addresses.into_iter().collect();
            }
            RuntimePayloadKind::Ping => {
                ws.send(Message::Text(json!({"type": "pong"}).to_string().into()))
                    .await
                    .map_err(|error| {
                        format!("Hyper Insight runtime websocket pong failed: {error}")
                    })?;
            }
            RuntimePayloadKind::Error(detail) => {
                let is_auth = detail.to_lowercase().contains("unauthor");
                let mut state = self.state.write().await;
                state.status = if is_auth { "auth_error" } else { "error" }.to_owned();
                state.last_error = Some(detail.clone());
                return Err(detail);
            }
            RuntimePayloadKind::WalletEvent(event) => {
                self.process_wallet_event(db, event).await?;
            }
            RuntimePayloadKind::Ignore => {}
        }

        Ok(())
    }

    async fn process_wallet_event(
        &self,
        db: &sqlx::PgPool,
        event: Map<String, Value>,
    ) -> Result<(), String> {
        if self.is_duplicate_event(&event).await {
            return Ok(());
        }

        let event_address = event
            .get("address")
            .and_then(Value::as_str)
            .map(str::trim)
            .filter(|value| !value.is_empty())
            .map(str::to_lowercase)
            .unwrap_or_default();
        let event_type = event
            .get("event_type")
            .and_then(Value::as_str)
            .map(str::trim)
            .unwrap_or_default()
            .to_owned();
        if event_address.is_empty() || event_type.is_empty() {
            return Ok(());
        }

        let triggered_at = event_timestamp_to_datetime(event.get("timestamp"));
        let symbol = event
            .get("symbol")
            .and_then(Value::as_str)
            .map(str::trim)
            .filter(|value| !value.is_empty())
            .unwrap_or(WALLET_TRIGGER_SYMBOL)
            .chars()
            .take(20)
            .collect::<String>();

        let pool_rows = sqlx::query(
            r#"
            SELECT id, signal_ids, source_config
            FROM signal_pools
            WHERE enabled = true
              AND COALESCE(is_deleted, false) = false
              AND source_type = $1
            "#,
        )
        .bind(WALLET_TRACKING_SOURCE)
        .fetch_all(db)
        .await
        .map_err(|error| format!("Failed to load wallet tracking signal pools: {error}"))?;

        let mut matched_pool = false;
        for row in pool_rows {
            let pool_id: i32 = row
                .try_get("id")
                .map_err(|error| format!("Failed to parse wallet tracking pool id: {error}"))?;
            let source_config = parse_source_config(
                row.try_get::<Option<String>, _>("source_config")
                    .ok()
                    .flatten()
                    .as_deref(),
            );
            let signal_ids = parse_signal_ids(
                row.try_get::<Option<String>, _>("signal_ids")
                    .ok()
                    .flatten()
                    .as_deref(),
            );
            if !event_matches_pool(&source_config, &event_address, &event_type) {
                continue;
            }

            let trigger_value = json!({
                "source": "hyper_insight",
                "source_type": WALLET_TRACKING_SOURCE,
                "address": event_address,
                "event_type": event_type,
                "event_level": event.get("event_level").cloned().unwrap_or(Value::Null),
                "tier": event.get("tier").cloned().unwrap_or(Value::Null),
                "summary": event.get("summary").cloned().unwrap_or(Value::Null),
                "detail": event.get("detail").cloned().unwrap_or(Value::Null),
                "event_timestamp": event.get("timestamp").cloned().unwrap_or(Value::Null),
            });

            sqlx::query(
                r#"
                INSERT INTO signal_trigger_logs (
                    signal_id, pool_id, symbol, trigger_value, triggered_at, market_regime
                )
                VALUES (NULL, $1, $2, $3, $4, NULL)
                "#,
            )
            .bind(pool_id)
            .bind(&symbol)
            .bind(trigger_value.to_string())
            .bind(triggered_at)
            .execute(db)
            .await
            .map_err(|error| format!("Failed to insert wallet tracking trigger log: {error}"))?;
            project_wallet_trigger_into_runtime_states(
                pool_id,
                &symbol,
                &signal_ids,
                &event_type,
                triggered_at,
            );
            matched_pool = true;
        }

        if matched_pool {
            let mut state = self.state.write().await;
            state.last_event_at = Some(format_utc_iso(triggered_at));
        }

        Ok(())
    }

    async fn is_duplicate_event(&self, event: &Map<String, Value>) -> bool {
        let key = build_event_key(event);
        let mut cache = self.recent_events.lock().await;
        cache.insert_or_is_duplicate(key)
    }

    async fn touch_last_message(&self) {
        let mut state = self.state.write().await;
        state.last_message_at = Some(format_utc_iso(Utc::now().naive_utc()));
    }

    async fn apply_idle_state(&self, runtime: &RuntimeConfig) {
        let mut state = self.state.write().await;
        if !runtime.enabled {
            state.status = "disabled".to_owned();
            state.tier = None;
            state.synced_addresses.clear();
            state.last_message_at = None;
            state.last_event_at = None;
            state.last_error = None;
            return;
        }

        if runtime.access_token.trim().is_empty() {
            state.status = "waiting_for_token".to_owned();
            state.tier = None;
            state.synced_addresses.clear();
            state.last_message_at = None;
            state.last_event_at = None;
            state.last_error = None;
            return;
        }

        if state.status != "connected" && state.status != "connecting" {
            state.status = "connecting".to_owned();
        }
    }

    async fn set_terminal_error_state(&self, error: String) {
        let mut state = self.state.write().await;
        if state.status != "auth_error" {
            state.status = "error".to_owned();
        }
        state.last_error = Some(error.clone());
        warn!(
            target = "backend_rust::wallet_tracking_runtime",
            error = %error,
            "wallet tracking runtime loop error"
        );
    }

    async fn wait_for_signal(&self, timeout: Option<Duration>) -> bool {
        if self.shutdown_requested.load(Ordering::SeqCst) {
            return true;
        }

        match timeout {
            Some(timeout) => {
                tokio::select! {
                    _ = self.shutdown_notify.notified() => true,
                    _ = self.refresh_notify.notified() => false,
                    _ = sleep(timeout) => false,
                }
            }
            None => {
                tokio::select! {
                    _ = self.shutdown_notify.notified() => true,
                    _ = self.refresh_notify.notified() => false,
                }
            }
        }
    }
}

static WALLET_TRACKING_RUNTIME: LazyLock<Arc<WalletTrackingRuntimeService>> =
    LazyLock::new(|| Arc::new(WalletTrackingRuntimeService::new()));

pub async fn start(db: sqlx::PgPool) {
    WALLET_TRACKING_RUNTIME.start(db).await;
}

pub async fn shutdown() {
    WALLET_TRACKING_RUNTIME.shutdown().await;
}

pub fn request_refresh() {
    WALLET_TRACKING_RUNTIME.request_refresh();
}

pub async fn snapshot() -> WalletTrackingRuntimeSnapshot {
    WALLET_TRACKING_RUNTIME.snapshot().await
}

#[cfg(test)]
pub async fn set_snapshot_for_tests(snapshot: WalletTrackingRuntimeSnapshot) {
    let mut state = WALLET_TRACKING_RUNTIME.state.write().await;
    *state = snapshot;
}

#[cfg(test)]
pub async fn reset_snapshot_for_tests() {
    let mut state = WALLET_TRACKING_RUNTIME.state.write().await;
    *state = WalletTrackingRuntimeSnapshot::default();
}

async fn load_runtime_config(db: &sqlx::PgPool) -> Result<RuntimeConfig, String> {
    let enabled = load_system_config_value(db, CONFIG_ENABLED_KEY)
        .await?
        .as_deref()
        .is_some_and(|value| value == "true");
    let access_token = load_system_config_value(db, CONFIG_ACCESS_TOKEN_KEY)
        .await?
        .unwrap_or_default();

    Ok(RuntimeConfig {
        enabled,
        access_token,
    })
}

async fn load_system_config_value(db: &sqlx::PgPool, key: &str) -> Result<Option<String>, String> {
    sqlx::query_scalar::<_, Option<String>>(
        "SELECT value FROM system_configs WHERE key = $1 LIMIT 1",
    )
    .bind(key)
    .fetch_optional(db)
    .await
    .map(|value| value.flatten())
    .map_err(|error| format!("Failed to load runtime config {key}: {error}"))
}

fn increase_backoff(current: Duration) -> Duration {
    current.saturating_mul(2).min(WS_MAX_BACKOFF)
}

fn event_timestamp_to_datetime(raw: Option<&Value>) -> NaiveDateTime {
    raw.and_then(Value::as_i64)
        .and_then(chrono::DateTime::from_timestamp_millis)
        .map(|value| value.naive_utc())
        .unwrap_or_else(|| Utc::now().naive_utc())
}

fn format_utc_iso(value: NaiveDateTime) -> String {
    value.and_utc().to_rfc3339()
}

fn parse_source_config(raw: Option<&str>) -> Value {
    raw.and_then(|text| serde_json::from_str::<Value>(text).ok())
        .unwrap_or_else(|| json!({}))
}

fn parse_signal_ids(raw: Option<&str>) -> Vec<i32> {
    raw.and_then(|text| serde_json::from_str::<Value>(text).ok())
        .and_then(|value| value.as_array().cloned())
        .map(|items| {
            items
                .into_iter()
                .filter_map(|item| item.as_i64())
                .filter(|item| *item >= i32::MIN as i64 && *item <= i32::MAX as i64)
                .map(|item| item as i32)
                .collect::<Vec<_>>()
        })
        .unwrap_or_default()
}

fn event_matches_pool(source_config: &Value, event_address: &str, event_type: &str) -> bool {
    let Some(config) = source_config.as_object() else {
        return false;
    };

    let addresses: BTreeSet<String> = config
        .get("addresses")
        .and_then(Value::as_array)
        .map(|items| {
            items
                .iter()
                .filter_map(Value::as_str)
                .map(str::trim)
                .filter(|item| !item.is_empty())
                .map(str::to_lowercase)
                .collect()
        })
        .unwrap_or_default();
    if addresses.is_empty() || !addresses.contains(event_address) {
        return false;
    }

    let mut event_types: BTreeSet<String> = config
        .get("event_types")
        .and_then(Value::as_array)
        .map(|items| {
            items
                .iter()
                .filter_map(Value::as_str)
                .map(str::trim)
                .filter(|item| !item.is_empty())
                .map(str::to_owned)
                .collect()
        })
        .unwrap_or_default();
    if event_type == "position_change" && event_types.contains("fill") {
        event_types.insert("position_change".to_owned());
    }

    event_types.is_empty() || event_types.contains(event_type)
}

fn build_event_key(event: &Map<String, Value>) -> String {
    let detail_hash = event
        .get("detail")
        .and_then(Value::as_object)
        .and_then(|detail| detail.get("hash"))
        .map(value_key_fragment)
        .unwrap_or_default();
    format!(
        "{}|{}|{}|{}",
        event
            .get("address")
            .map(value_key_fragment)
            .unwrap_or_default(),
        event
            .get("event_type")
            .map(value_key_fragment)
            .unwrap_or_default(),
        event
            .get("timestamp")
            .map(value_key_fragment)
            .unwrap_or_default(),
        detail_hash,
    )
}

fn value_key_fragment(value: &Value) -> String {
    match value {
        Value::Null => String::new(),
        Value::Bool(raw) => raw.to_string(),
        Value::Number(raw) => raw.to_string(),
        Value::String(raw) => raw.clone(),
        other => other.to_string(),
    }
}

enum RuntimePayloadKind {
    Connected {
        tier: Option<String>,
        synced_addresses: Vec<String>,
    },
    SubscriptionUpdate {
        address: Option<String>,
        action: Option<String>,
    },
    Ping,
    Error(String),
    WalletEvent(Map<String, Value>),
    Ignore,
}

fn classify_runtime_payload(payload: &Map<String, Value>) -> RuntimePayloadKind {
    match payload.get("type").and_then(Value::as_str) {
        Some("connected") => {
            let synced_addresses = payload
                .get("addresses")
                .and_then(Value::as_array)
                .map(|items| {
                    items
                        .iter()
                        .filter_map(Value::as_str)
                        .map(str::trim)
                        .filter(|item| !item.is_empty())
                        .map(str::to_lowercase)
                        .collect()
                })
                .unwrap_or_default();
            RuntimePayloadKind::Connected {
                tier: payload
                    .get("tier")
                    .and_then(Value::as_str)
                    .map(str::to_owned),
                synced_addresses,
            }
        }
        Some("subscription_update") => RuntimePayloadKind::SubscriptionUpdate {
            address: payload
                .get("address")
                .and_then(Value::as_str)
                .map(str::to_owned),
            action: payload
                .get("action")
                .and_then(Value::as_str)
                .map(str::to_owned),
        },
        Some("ping") => RuntimePayloadKind::Ping,
        Some("error") => RuntimePayloadKind::Error(
            payload
                .get("detail")
                .and_then(Value::as_str)
                .unwrap_or("Unknown upstream error")
                .to_owned(),
        ),
        _ => {
            if payload.get("version").and_then(Value::as_i64) == Some(1)
                && payload.get("address").is_some()
                && payload.get("event_type").is_some()
            {
                RuntimePayloadKind::WalletEvent(payload.clone())
            } else {
                RuntimePayloadKind::Ignore
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use serde_json::json;

    use super::{
        RuntimePayloadKind, build_event_key, classify_runtime_payload, event_matches_pool,
        parse_signal_ids, parse_source_config,
    };

    #[test]
    fn wallet_pool_event_matching_supports_fill_compatibility_alias() {
        let config = parse_source_config(Some(
            r#"{"addresses":["0xAbC"],"event_types":["fill","funding"]}"#,
        ));

        assert!(event_matches_pool(&config, "0xabc", "fill"));
        assert!(event_matches_pool(&config, "0xabc", "position_change"));
        assert!(!event_matches_pool(&config, "0xabc", "liquidation"));
        assert!(!event_matches_pool(&config, "0xdef", "fill"));
    }

    #[test]
    fn runtime_payload_classifier_extracts_connected_snapshot_fields() {
        let payload = json!({
            "type": "connected",
            "tier": "premium",
            "addresses": ["0xAbC", " 0xDef "]
        });
        let payload = payload.as_object().expect("payload should be object");

        match classify_runtime_payload(payload) {
            RuntimePayloadKind::Connected {
                tier,
                synced_addresses,
            } => {
                assert_eq!(tier.as_deref(), Some("premium"));
                assert_eq!(synced_addresses, vec!["0xabc", "0xdef"]);
            }
            _ => panic!("payload should be classified as connected"),
        }
    }

    #[test]
    fn runtime_payload_classifier_detects_wallet_event_shape() {
        let payload = json!({
            "version": 1,
            "address": "0xabc",
            "event_type": "position_change",
            "timestamp": 123456
        });
        let payload = payload.as_object().expect("payload should be object");

        match classify_runtime_payload(payload) {
            RuntimePayloadKind::WalletEvent(event) => {
                assert_eq!(
                    event.get("address").and_then(|value| value.as_str()),
                    Some("0xabc")
                );
            }
            _ => panic!("payload should be classified as wallet event"),
        }
    }

    #[test]
    fn event_key_uses_detail_hash_when_present() {
        let first = json!({
            "address": "0xabc",
            "event_type": "position_change",
            "timestamp": 111,
            "detail": {"hash": "hash-a"}
        });
        let second = json!({
            "address": "0xabc",
            "event_type": "position_change",
            "timestamp": 111,
            "detail": {"hash": "hash-b"}
        });

        let first_key = build_event_key(first.as_object().expect("first event should be object"));
        let second_key =
            build_event_key(second.as_object().expect("second event should be object"));
        assert_ne!(first_key, second_key);
    }

    #[test]
    fn parse_signal_ids_reads_integer_arrays_from_storage_text() {
        assert_eq!(parse_signal_ids(Some("[1,2,3]")), vec![1, 2, 3]);
        assert_eq!(parse_signal_ids(Some("[1,\"oops\",4]")), vec![1, 4]);
        assert!(parse_signal_ids(Some("not-json")).is_empty());
    }
}
