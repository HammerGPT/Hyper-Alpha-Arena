use std::{
    env,
    net::{IpAddr, SocketAddr},
    time::Duration,
};

use url::Url;

const DEFAULT_BIND_HOST: &str = "0.0.0.0";
const DEFAULT_BIND_PORT: u16 = 8802;
const DEFAULT_LEGACY_HTTP_URL: &str = "http://127.0.0.1:5611";
const DEFAULT_DATABASE_URL: &str = "postgresql://alpha_user:alpha_pass@postgres:5432/alpha_arena";
const DEFAULT_SNAPSHOT_DATABASE_URL: &str =
    "postgresql://alpha_user:alpha_pass@postgres:5432/alpha_snapshots";
const DEFAULT_REQUEST_TIMEOUT_SECS: u64 = 120;
const DEFAULT_CONNECT_TIMEOUT_SECS: u64 = 10;
const DEFAULT_WALLET_RUNTIME_ENABLED: bool = false;

#[derive(Clone, Debug)]
pub struct AppConfig {
    pub bind_addr: SocketAddr,
    pub legacy_http_url: Url,
    pub legacy_ws_url: Url,
    pub database_url: String,
    pub snapshot_database_url: String,
    pub request_timeout: Duration,
    pub connect_timeout: Duration,
    pub wallet_runtime_enabled: bool,
}

impl AppConfig {
    pub fn from_env() -> Result<Self, String> {
        let bind_host =
            env::var("RUST_GATEWAY_HOST").unwrap_or_else(|_| DEFAULT_BIND_HOST.to_owned());
        let bind_ip: IpAddr = bind_host
            .parse()
            .map_err(|error| format!("invalid RUST_GATEWAY_HOST `{bind_host}`: {error}"))?;

        let bind_port = read_u16_env("RUST_GATEWAY_PORT").unwrap_or(DEFAULT_BIND_PORT);
        let bind_addr = SocketAddr::new(bind_ip, bind_port);

        let legacy_http_url = read_url_env("LEGACY_BACKEND_URL", DEFAULT_LEGACY_HTTP_URL)?;
        let legacy_ws_url = match env::var("LEGACY_WS_URL") {
            Ok(value) => parse_url("LEGACY_WS_URL", &value)?,
            Err(_) => derive_ws_url(&legacy_http_url)?,
        };
        let database_url =
            env::var("DATABASE_URL").unwrap_or_else(|_| DEFAULT_DATABASE_URL.to_owned());
        let snapshot_database_url = env::var("SNAPSHOT_DATABASE_URL")
            .unwrap_or_else(|_| DEFAULT_SNAPSHOT_DATABASE_URL.to_owned());

        let request_timeout = Duration::from_secs(
            read_u64_env("RUST_GATEWAY_REQUEST_TIMEOUT_SECS")
                .unwrap_or(DEFAULT_REQUEST_TIMEOUT_SECS),
        );
        let connect_timeout = Duration::from_secs(
            read_u64_env("RUST_GATEWAY_CONNECT_TIMEOUT_SECS")
                .unwrap_or(DEFAULT_CONNECT_TIMEOUT_SECS),
        );
        let wallet_runtime_enabled =
            read_bool_env("RUST_WALLET_RUNTIME_ENABLED").unwrap_or(DEFAULT_WALLET_RUNTIME_ENABLED);

        Ok(Self {
            bind_addr,
            legacy_http_url,
            legacy_ws_url,
            database_url,
            snapshot_database_url,
            request_timeout,
            connect_timeout,
            wallet_runtime_enabled,
        })
    }

    #[cfg(test)]
    pub fn for_tests() -> Self {
        let legacy_http_url =
            Url::parse(DEFAULT_LEGACY_HTTP_URL).expect("test legacy http url should parse");
        let legacy_ws_url =
            derive_ws_url(&legacy_http_url).expect("test legacy ws url should derive");

        Self {
            bind_addr: SocketAddr::new(
                IpAddr::V4(std::net::Ipv4Addr::LOCALHOST),
                DEFAULT_BIND_PORT,
            ),
            legacy_http_url,
            legacy_ws_url,
            database_url: DEFAULT_DATABASE_URL.to_owned(),
            snapshot_database_url: DEFAULT_SNAPSHOT_DATABASE_URL.to_owned(),
            request_timeout: Duration::from_secs(DEFAULT_REQUEST_TIMEOUT_SECS),
            connect_timeout: Duration::from_secs(DEFAULT_CONNECT_TIMEOUT_SECS),
            wallet_runtime_enabled: DEFAULT_WALLET_RUNTIME_ENABLED,
        }
    }

    pub fn legacy_http_target(&self, path_and_query: &str) -> Url {
        join_url(&self.legacy_http_url, path_and_query)
    }

    pub fn legacy_ws_target(&self, path_and_query: &str) -> Url {
        join_url(&self.legacy_ws_url, path_and_query)
    }
}

fn read_u16_env(name: &str) -> Option<u16> {
    env::var(name)
        .ok()
        .and_then(|value| value.parse::<u16>().ok())
}

fn read_u64_env(name: &str) -> Option<u64> {
    env::var(name)
        .ok()
        .and_then(|value| value.parse::<u64>().ok())
}

fn read_bool_env(name: &str) -> Option<bool> {
    env::var(name).ok().and_then(|value| {
        let normalized = value.trim().to_ascii_lowercase();
        match normalized.as_str() {
            "1" | "true" | "yes" | "on" => Some(true),
            "0" | "false" | "no" | "off" => Some(false),
            _ => None,
        }
    })
}

fn read_url_env(name: &str, default: &str) -> Result<Url, String> {
    match env::var(name) {
        Ok(value) => parse_url(name, &value),
        Err(_) => {
            Url::parse(default).map_err(|error| format!("invalid default URL for {name}: {error}"))
        }
    }
}

fn parse_url(name: &str, value: &str) -> Result<Url, String> {
    Url::parse(value).map_err(|error| format!("invalid {name} `{value}`: {error}"))
}

fn derive_ws_url(http_url: &Url) -> Result<Url, String> {
    let mut ws_url = http_url.clone();
    let scheme = match ws_url.scheme() {
        "https" => "wss",
        "http" => "ws",
        "wss" | "ws" => ws_url.scheme(),
        other => return Err(format!("cannot derive websocket URL from scheme `{other}`")),
    }
    .to_owned();
    ws_url
        .set_scheme(&scheme)
        .map_err(|_| "failed to set websocket scheme".to_owned())?;
    Ok(ws_url)
}

fn join_url(base: &Url, path_and_query: &str) -> Url {
    let mut target = base.clone();
    let (path, query) = match path_and_query.split_once('?') {
        Some((path, query)) => (path, Some(query)),
        None => (path_and_query, None),
    };

    target.set_path(path);
    target.set_query(query);
    target
}

#[cfg(test)]
mod tests {
    use url::Url;

    use super::{derive_ws_url, join_url};

    #[test]
    fn derives_websocket_url_from_http() {
        let http_url = Url::parse("http://127.0.0.1:5611").expect("http url should parse");
        let ws_url = derive_ws_url(&http_url).expect("ws url should derive");

        assert_eq!(ws_url.as_str(), "ws://127.0.0.1:5611/");
    }

    #[test]
    fn joins_path_and_query_against_base_url() {
        let base = Url::parse("http://127.0.0.1:5611").expect("base url should parse");
        let joined = join_url(&base, "/api/signals?limit=10");

        assert_eq!(
            joined.as_str(),
            "http://127.0.0.1:5611/api/signals?limit=10"
        );
    }
}
