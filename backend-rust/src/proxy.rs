use axum::{
    body::{Body, Bytes},
    extract::{OriginalUri, State},
    http::{
        HeaderMap, Method, Response,
        header::{self, HeaderName},
    },
};
use futures_util::TryStreamExt;
use reqwest::Client;
use tracing::{error, warn};

use crate::{error::AppError, state::AppState};

static HOP_BY_HOP_HEADERS: &[HeaderName] = &[
    header::CONNECTION,
    header::PROXY_AUTHENTICATE,
    header::PROXY_AUTHORIZATION,
    header::TE,
    header::TRAILER,
    header::TRANSFER_ENCODING,
    header::UPGRADE,
];

pub async fn proxy_http_request(
    State(state): State<AppState>,
    method: Method,
    headers: HeaderMap,
    original_uri: OriginalUri,
    body: Bytes,
) -> Result<Response<Body>, AppError> {
    let target_url = state.config.legacy_http_target(&original_uri.0.to_string());

    let upstream_request =
        build_upstream_request(&state.client, method, &headers, target_url, body)?;
    let upstream_response = upstream_request.send().await.map_err(|error| {
        error!(target = "backend_rust::proxy", %error, target = %original_uri.0, "http proxy request failed");
        AppError::bad_gateway(format!("legacy backend request failed: {error}"))
    })?;

    build_downstream_response(upstream_response).await
}

pub(crate) fn build_upstream_request(
    client: &Client,
    method: Method,
    headers: &HeaderMap,
    target_url: url::Url,
    body: Bytes,
) -> Result<reqwest::RequestBuilder, AppError> {
    let mut builder = client.request(method, target_url);

    for (name, value) in headers {
        if should_skip_request_header(name) {
            continue;
        }
        builder = builder.header(name, value);
    }

    if !body.is_empty() {
        builder = builder.body(body);
    }

    Ok(builder)
}

async fn build_downstream_response(
    upstream_response: reqwest::Response,
) -> Result<Response<Body>, AppError> {
    let status = upstream_response.status();
    let headers = upstream_response.headers().clone();
    let body = upstream_response.bytes().await.map_err(|error| {
        warn!(target = "backend_rust::proxy", %error, "failed to read upstream response body");
        AppError::bad_gateway(format!("failed to read legacy backend response: {error}"))
    })?;

    let mut response_builder = Response::builder().status(status);

    for (name, value) in &headers {
        if should_skip_response_header(name) {
            continue;
        }
        response_builder = response_builder.header(name, value);
    }

    response_builder
        .body(Body::from(body))
        .map_err(|error| AppError::internal(format!("failed to build proxy response: {error}")))
}

pub(crate) fn build_downstream_streaming_response(
    upstream_response: reqwest::Response,
) -> Result<Response<Body>, AppError> {
    let status = upstream_response.status();
    let headers = upstream_response.headers().clone();
    let stream = upstream_response.bytes_stream().map_err(|error| {
        std::io::Error::other(format!("failed to read legacy backend stream: {error}"))
    });

    let mut response_builder = Response::builder().status(status);
    for (name, value) in &headers {
        if should_skip_response_header(name) {
            continue;
        }
        response_builder = response_builder.header(name, value);
    }

    response_builder
        .body(Body::from_stream(stream))
        .map_err(|error| {
            AppError::internal(format!("failed to build streaming proxy response: {error}"))
        })
}

fn should_skip_request_header(name: &HeaderName) -> bool {
    name == header::HOST
        || name.as_str().eq_ignore_ascii_case("keep-alive")
        || HOP_BY_HOP_HEADERS.contains(name)
}

fn should_skip_response_header(name: &HeaderName) -> bool {
    name.as_str().eq_ignore_ascii_case("keep-alive") || HOP_BY_HOP_HEADERS.contains(name)
}

#[cfg(test)]
mod tests {
    use std::{
        net::{IpAddr, Ipv4Addr, SocketAddr},
        time::Duration,
    };

    use axum::{
        Router,
        body::{Body, Bytes, to_bytes},
        http::{HeaderValue, Request, StatusCode, header},
        response::IntoResponse,
        routing::get,
    };
    use tokio::net::TcpListener;
    use tower::ServiceExt;
    use url::Url;

    use crate::{app::build_router, config::AppConfig};

    #[tokio::test]
    async fn proxy_forwards_http_requests_to_legacy_backend() {
        let upstream = Router::new().route(
            "/hello",
            get(|| async {
                let mut response = "proxied response".into_response();
                response
                    .headers_mut()
                    .insert(header::CONTENT_TYPE, HeaderValue::from_static("text/plain"));
                response
                    .headers_mut()
                    .insert("x-upstream", HeaderValue::from_static("ok"));
                response
            }),
        );

        let listener = TcpListener::bind(SocketAddr::new(IpAddr::V4(Ipv4Addr::LOCALHOST), 0))
            .await
            .expect("test upstream listener should bind");
        let upstream_addr = listener
            .local_addr()
            .expect("test upstream listener should have local address");

        tokio::spawn(async move {
            axum::serve(listener, upstream)
                .await
                .expect("test upstream server should run");
        });

        let config = AppConfig {
            bind_addr: SocketAddr::new(IpAddr::V4(Ipv4Addr::LOCALHOST), 8802),
            legacy_http_url: Url::parse(&format!("http://{upstream_addr}"))
                .expect("legacy http url should parse"),
            legacy_ws_url: Url::parse(&format!("ws://{upstream_addr}"))
                .expect("legacy ws url should parse"),
            database_url: "postgresql://alpha_user:alpha_pass@localhost:5432/alpha_arena"
                .to_owned(),
            snapshot_database_url:
                "postgresql://alpha_user:alpha_pass@localhost:5432/alpha_snapshots".to_owned(),
            request_timeout: Duration::from_secs(10),
            connect_timeout: Duration::from_secs(5),
            wallet_runtime_enabled: false,
        };

        let response = build_router(config)
            .oneshot(
                Request::builder()
                    .uri("/hello")
                    .body(Body::empty())
                    .expect("proxy request should be valid"),
            )
            .await
            .expect("proxy router should respond");

        assert_eq!(response.status(), StatusCode::OK);
        assert_eq!(response.headers()["x-upstream"], "ok");

        let body = to_bytes(response.into_body(), usize::MAX)
            .await
            .expect("proxy response body should be readable");
        assert_eq!(body, Bytes::from_static(b"proxied response"));
    }
}
