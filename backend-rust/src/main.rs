mod account_management_routes;
mod account_runtime_routes;
mod ai_history_routes;
mod analytics_routes;
mod app;
mod arena_routes;
mod bot_routes;
mod config;
mod config_routes;
mod error;
mod exchange_account_routes;
mod factor_routes;
mod handlers;
mod hyperliquid_action_routes;
mod kline_routes;
mod market_regime_routes;
mod market_routes;
mod news_routes;
mod program_routes;
mod prompt_backtest_routes;
mod prompt_routes;
mod proxy;
mod ranking_routes;
mod signal_routes;
mod state;
mod symbol_routes;
mod system_routes;
mod user_routes;
mod wallet_tracking_runtime;
mod ws_proxy;

use std::process;

use sqlx::postgres::PgPoolOptions;
use tokio::net::TcpListener;
use tracing::{error, info};
use tracing_subscriber::{EnvFilter, layer::SubscriberExt, util::SubscriberInitExt};

use crate::{
    app::build_router,
    config::AppConfig,
    wallet_tracking_runtime::{
        shutdown as shutdown_wallet_tracking_runtime, start as start_wallet_tracking_runtime,
    },
};

#[tokio::main]
async fn main() {
    dotenvy::dotenv().ok();
    init_tracing();

    let config = match AppConfig::from_env() {
        Ok(config) => config,
        Err(error) => {
            error!(target = "backend_rust::bootstrap", %error, "failed to load configuration");
            process::exit(1);
        }
    };

    let wallet_runtime_started = if config.wallet_runtime_enabled {
        let runtime_db = PgPoolOptions::new()
            .max_connections(4)
            .connect_lazy(&config.database_url)
            .expect("runtime database URL should be valid");
        start_wallet_tracking_runtime(runtime_db).await;
        true
    } else {
        info!(
            target = "backend_rust::wallet_tracking_runtime",
            "wallet runtime is disabled (set RUST_WALLET_RUNTIME_ENABLED=true to enable)"
        );
        false
    };
    let router = build_router(config.clone());
    let listener = match TcpListener::bind(config.bind_addr).await {
        Ok(listener) => listener,
        Err(error) => {
            error!(target = "backend_rust::bootstrap", %error, bind_addr = %config.bind_addr, "failed to bind listener");
            process::exit(1);
        }
    };

    info!(
        target = "backend_rust::bootstrap",
        bind_addr = %config.bind_addr,
        legacy_http = %config.legacy_http_url,
        legacy_ws = %config.legacy_ws_url,
        "rust compatibility gateway started"
    );

    let server_result = axum::serve(listener, router)
        .with_graceful_shutdown(shutdown_signal())
        .await;
    if wallet_runtime_started {
        shutdown_wallet_tracking_runtime().await;
    }

    if let Err(error) = server_result {
        error!(target = "backend_rust::bootstrap", %error, "server exited with error");
        process::exit(1);
    }
}

fn init_tracing() {
    tracing_subscriber::registry()
        .with(
            EnvFilter::try_from_default_env()
                .unwrap_or_else(|_| EnvFilter::new("backend_rust=info,tower_http=info")),
        )
        .with(tracing_subscriber::fmt::layer())
        .init();
}

async fn shutdown_signal() {
    let ctrl_c = async {
        tokio::signal::ctrl_c()
            .await
            .expect("ctrl-c handler should install");
    };

    #[cfg(unix)]
    let terminate = async {
        tokio::signal::unix::signal(tokio::signal::unix::SignalKind::terminate())
            .expect("signal handler should install")
            .recv()
            .await;
    };

    #[cfg(not(unix))]
    let terminate = std::future::pending::<()>();

    tokio::select! {
        _ = ctrl_c => {},
        _ = terminate => {},
    }

    info!(
        target = "backend_rust::bootstrap",
        "shutdown signal received"
    );
}
