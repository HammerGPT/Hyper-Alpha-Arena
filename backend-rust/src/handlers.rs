use axum::Json;
use serde::Serialize;

#[derive(Serialize)]
pub struct HealthPayload {
    status: &'static str,
    message: &'static str,
    version: &'static str,
    mode: &'static str,
}

pub async fn health_handler() -> Json<HealthPayload> {
    Json(HealthPayload {
        status: "healthy",
        message: "Rust compatibility gateway is running",
        version: env!("CARGO_PKG_VERSION"),
        mode: "compatibility-gateway",
    })
}
