use axum::{
    Router,
    routing::{any, get},
};
use tower_http::{
    cors::CorsLayer,
    trace::{DefaultMakeSpan, DefaultOnResponse, TraceLayer},
};
use tracing::Level;

use crate::{
    account_management_routes::{
        create_trading_account, delete_trading_account, get_or_create_default_account_endpoint,
        get_trading_account, list_trading_accounts, update_trading_account,
    },
    account_runtime_routes::{
        get_account_overview, get_account_strategy, get_specific_account_overview,
        list_all_accounts, update_account_strategy,
    },
    ai_history_routes::{
        get_program_messages, get_prompt_messages, get_signal_messages, list_program_conversations,
        list_prompt_conversations, list_signal_conversations,
    },
    analytics_routes::{
        get_analytics_by_account, get_analytics_by_factor, get_analytics_by_operation,
        get_analytics_by_strategy, get_analytics_by_symbol, get_analytics_by_trigger_type,
        get_analytics_summary, get_attribution_messages, get_program_analytics_by_operation,
        get_program_analytics_by_program, get_program_analytics_by_symbol,
        get_program_analytics_by_trigger_type, get_program_analytics_summary,
        list_attribution_conversations,
    },
    arena_routes::{
        check_pnl_sync_status, get_aggregated_analytics, get_completed_trades, get_model_chat,
        get_model_chat_snapshots, get_positions_snapshot,
    },
    bot_routes::{
        get_bot_config, get_notification_config, list_bot_configs, update_notification_config,
    },
    config::AppConfig,
    config_routes::{
        check_required_configs, get_global_sampling_config, update_global_sampling_config,
        update_system_config,
    },
    exchange_account_routes::{
        cancel_user_order, check_hyperliquid_wallet_upgrade_needed,
        configure_hyperliquid_account_wallet, create_user_order, delete_hyperliquid_account_wallet,
        disable_hyperliquid_account_trading, enable_hyperliquid_account_trading,
        execute_order_manually, get_binance_balance, get_binance_config, get_binance_daily_quota,
        get_binance_positions, get_binance_price, get_binance_summary, get_binance_wallets_all,
        get_hyperliquid_account_snapshots, get_hyperliquid_account_state,
        get_hyperliquid_account_wallet, get_hyperliquid_agent_wallet_status,
        get_hyperliquid_balance, get_hyperliquid_config, get_hyperliquid_health,
        get_hyperliquid_positions, get_hyperliquid_trading_mode, get_hyperliquid_wallets_all,
        get_order_details, get_orders_health, get_pending_orders, get_user_orders,
        place_hyperliquid_manual_order, process_all_orders, set_hyperliquid_trading_mode,
        setup_hyperliquid_account, switch_hyperliquid_account_environment,
        test_hyperliquid_connection, test_hyperliquid_wallet_connection,
    },
    factor_routes::{
        get_effectiveness_by_window, get_effectiveness_history, get_factor_effectiveness,
        get_factor_library, get_factor_status, get_factor_values, list_custom_factors,
        list_expression_functions, validate_expression,
    },
    handlers::health_handler,
    hyperliquid_action_routes::list_exchange_actions,
    kline_routes::{
        create_backfill_task as create_kline_backfill_task,
        delete_backfill_task as delete_kline_backfill_task,
        get_backfill_status as get_kline_backfill_status, get_backfill_tasks,
        get_kline_data_placeholder, list_backfill_tasks as list_kline_backfill_tasks,
    },
    market_regime_routes::{list_regime_configs, update_regime_config},
    market_routes::{
        get_available_indicators, get_crypto_market_status, get_crypto_price, get_crypto_symbols,
        get_kline_with_indicators, get_market_kline, get_market_price, get_market_prices,
        get_market_status, get_popular_cryptos, market_data_health,
    },
    news_routes::{get_news_sources, get_news_stats, list_news_articles, update_news_sources},
    program_routes::{
        chat_with_program_ai, create_binding, create_program, delete_binding, delete_program,
        get_program, get_program_dev_guide, list_bindings, list_program_accounts, list_programs,
        list_signal_pools, preview_run_binding, run_program_backtest, test_run_program,
        update_binding, update_program, validate_program_code,
    },
    prompt_backtest_routes::{
        create_backtest_task as create_prompt_backtest_task,
        delete_backtest_task as delete_prompt_backtest_task, get_item_detail,
        get_task_items_for_import, get_task_results, get_task_status, list_backtest_tasks,
        retry_backtest_task as retry_prompt_backtest_task,
    },
    prompt_routes::{
        copy_prompt_template, create_prompt_template, delete_prompt_binding,
        delete_prompt_template, list_prompt_templates, update_prompt_template,
        update_prompt_template_name, upsert_prompt_binding,
    },
    proxy::proxy_http_request,
    ranking_routes::{get_available_factors, get_available_symbols},
    signal_routes::{
        chat_with_signal_ai_stream, clear_wallet_tracking_token, create_pool,
        create_pool_from_config, create_signal, delete_pool, delete_signal, get_pool, get_signal,
        get_signal_backtest, get_signal_backtest_preview, get_signal_metric_analysis,
        get_signal_pool_backtest, get_signal_states, get_signal_test, get_trigger_logs,
        get_wallet_tracking_status, list_signals, reset_signal_states, sync_wallet_tracking_token,
        update_pool, update_signal, update_wallet_tracking_runtime,
    },
    state::AppState,
    symbol_routes::{
        get_binance_available_symbols, get_binance_watchlist, get_hyperliquid_available_symbols,
        get_hyperliquid_watchlist,
    },
    system_routes::{
        get_binance_backfill_status, get_collection_days, get_data_coverage,
        get_hyperliquid_backfill_status, get_retention_days_api, get_storage_stats,
        update_retention_days,
    },
    user_routes::{
        clear_membership, get_exchange_config, get_user_profile, list_users, login_user,
        register_user, set_exchange_config, sync_membership_info, update_user_profile,
    },
    ws_proxy::proxy_websocket,
};

pub fn build_router(config: AppConfig) -> Router {
    build_router_with_state(AppState::from_config(config))
}

pub fn build_router_with_state(state: AppState) -> Router {
    Router::new()
        .route("/api/health", get(health_handler))
        .route("/api/config/check-required", get(check_required_configs))
        .route(
            "/api/config/global-sampling",
            get(get_global_sampling_config).put(update_global_sampling_config),
        )
        .route(
            "/api/config/{key}",
            axum::routing::put(update_system_config),
        )
        .route("/api/ranking/factors", get(get_available_factors))
        .route("/api/ranking/symbols", get(get_available_symbols))
        .route(
            "/api/system/retention-days",
            get(get_retention_days_api).put(update_retention_days),
        )
        .route("/api/system/collection-days", get(get_collection_days))
        .route("/api/system/storage-stats", get(get_storage_stats))
        .route("/api/system/data-coverage", get(get_data_coverage))
        .route(
            "/api/system/binance/backfill/status",
            get(get_binance_backfill_status),
        )
        .route(
            "/api/system/hyperliquid/backfill/status",
            get(get_hyperliquid_backfill_status),
        )
        .route("/api/hyperliquid/actions/", get(list_exchange_actions))
        .route("/api/hyperliquid/actions", get(list_exchange_actions))
        .route("/api/hyperliquid/health", get(get_hyperliquid_health))
        .route(
            "/api/hyperliquid/trading-mode",
            get(get_hyperliquid_trading_mode).post(set_hyperliquid_trading_mode),
        )
        .route(
            "/api/hyperliquid/wallets/all",
            get(get_hyperliquid_wallets_all),
        )
        .route(
            "/api/hyperliquid/wallet-upgrade-check",
            get(check_hyperliquid_wallet_upgrade_needed),
        )
        .route(
            "/api/hyperliquid/accounts/{account_id}/config",
            get(get_hyperliquid_config),
        )
        .route(
            "/api/hyperliquid/accounts/{account_id}/setup",
            axum::routing::post(setup_hyperliquid_account),
        )
        .route(
            "/api/hyperliquid/accounts/{account_id}/switch-environment",
            axum::routing::post(switch_hyperliquid_account_environment),
        )
        .route(
            "/api/hyperliquid/accounts/{account_id}/wallet",
            get(get_hyperliquid_account_wallet)
                .post(configure_hyperliquid_account_wallet)
                .delete(delete_hyperliquid_account_wallet),
        )
        .route(
            "/api/hyperliquid/accounts/{account_id}/disable",
            axum::routing::post(disable_hyperliquid_account_trading),
        )
        .route(
            "/api/hyperliquid/accounts/{account_id}/enable",
            axum::routing::post(enable_hyperliquid_account_trading),
        )
        .route(
            "/api/hyperliquid/accounts/{account_id}/orders/manual",
            axum::routing::post(place_hyperliquid_manual_order),
        )
        .route("/api/orders/create", axum::routing::post(create_user_order))
        .route("/api/orders/pending", get(get_pending_orders))
        .route("/api/orders/user/{user_id}", get(get_user_orders))
        .route("/api/orders/order/{order_id}", get(get_order_details))
        .route("/api/orders/health", get(get_orders_health))
        .route(
            "/api/orders/execute/{order_id}",
            axum::routing::post(execute_order_manually),
        )
        .route(
            "/api/orders/cancel/{order_id}",
            axum::routing::post(cancel_user_order),
        )
        .route(
            "/api/orders/process-all",
            axum::routing::post(process_all_orders),
        )
        .route(
            "/api/hyperliquid/accounts/{account_id}/wallet/test",
            axum::routing::post(test_hyperliquid_wallet_connection),
        )
        .route(
            "/api/hyperliquid/accounts/{account_id}/wallet/agent-status",
            get(get_hyperliquid_agent_wallet_status),
        )
        .route(
            "/api/hyperliquid/accounts/{account_id}/balance",
            get(get_hyperliquid_balance),
        )
        .route(
            "/api/hyperliquid/accounts/{account_id}/positions",
            get(get_hyperliquid_positions),
        )
        .route(
            "/api/hyperliquid/accounts/{account_id}/account-state",
            get(get_hyperliquid_account_state),
        )
        .route(
            "/api/hyperliquid/accounts/{account_id}/test-connection",
            get(test_hyperliquid_connection),
        )
        .route(
            "/api/hyperliquid/accounts/{account_id}/snapshots",
            get(get_hyperliquid_account_snapshots),
        )
        .route(
            "/api/binance/accounts/{account_id}/config",
            get(get_binance_config),
        )
        .route(
            "/api/binance/accounts/{account_id}/balance",
            get(get_binance_balance),
        )
        .route(
            "/api/binance/accounts/{account_id}/positions",
            get(get_binance_positions),
        )
        .route(
            "/api/binance/accounts/{account_id}/summary",
            get(get_binance_summary),
        )
        .route(
            "/api/binance/accounts/{account_id}/daily-quota",
            get(get_binance_daily_quota),
        )
        .route("/api/binance/wallets/all", get(get_binance_wallets_all))
        .route("/api/binance/price/{symbol}", get(get_binance_price))
        .route("/api/news/articles", get(list_news_articles))
        .route(
            "/api/news/sources",
            get(get_news_sources).put(update_news_sources),
        )
        .route("/api/news/stats", get(get_news_stats))
        .route("/api/market/price/{symbol}", get(get_market_price))
        .route("/api/market/prices", get(get_market_prices))
        .route("/api/market/kline/{symbol}", get(get_market_kline))
        .route("/api/market/status/{symbol}", get(get_market_status))
        .route("/api/market/health", get(market_data_health))
        .route(
            "/api/market/kline-with-indicators/{symbol}",
            get(get_kline_with_indicators),
        )
        .route(
            "/api/market/indicators/available",
            get(get_available_indicators),
        )
        .route("/api/crypto/symbols", get(get_crypto_symbols))
        .route("/api/crypto/price/{symbol}", get(get_crypto_price))
        .route("/api/crypto/status/{symbol}", get(get_crypto_market_status))
        .route("/api/crypto/popular", get(get_popular_cryptos))
        .route("/api/factors/library", get(get_factor_library))
        .route("/api/factors/values", get(get_factor_values))
        .route("/api/factors/effectiveness", get(get_factor_effectiveness))
        .route(
            "/api/factors/effectiveness/{factor_name}/history",
            get(get_effectiveness_history),
        )
        .route(
            "/api/factors/effectiveness/{factor_name}/by-window",
            get(get_effectiveness_by_window),
        )
        .route("/api/factors/status", get(get_factor_status))
        .route(
            "/api/factors/validate-expression",
            axum::routing::post(validate_expression),
        )
        .route(
            "/api/factors/expression-functions",
            get(list_expression_functions),
        )
        .route(
            "/api/factors/custom",
            get(list_custom_factors).post(proxy_http_request),
        )
        .route(
            "/api/hyperliquid/symbols/available",
            get(get_hyperliquid_available_symbols),
        )
        .route(
            "/api/hyperliquid/symbols/watchlist",
            get(get_hyperliquid_watchlist).put(proxy_http_request),
        )
        .route(
            "/api/binance/symbols/available",
            get(get_binance_available_symbols),
        )
        .route(
            "/api/binance/symbols/watchlist",
            get(get_binance_watchlist).put(proxy_http_request),
        )
        .route("/api/market-regime/configs/list", get(list_regime_configs))
        .route(
            "/api/market-regime/configs/{config_id}",
            axum::routing::put(update_regime_config),
        )
        .route(
            "/api/users/exchange-config",
            get(get_exchange_config).post(set_exchange_config),
        )
        .route("/api/users/register", axum::routing::post(register_user))
        .route("/api/users/login", axum::routing::post(login_user))
        .route(
            "/api/users/profile",
            get(get_user_profile).put(update_user_profile),
        )
        .route("/api/users/", get(list_users))
        .route("/api/users", get(list_users))
        .route(
            "/api/users/sync-membership",
            axum::routing::post(sync_membership_info),
        )
        .route(
            "/api/users/clear-membership",
            axum::routing::post(clear_membership),
        )
        .route(
            "/api/accounts/",
            get(list_trading_accounts).post(create_trading_account),
        )
        .route(
            "/api/accounts",
            get(list_trading_accounts).post(create_trading_account),
        )
        .route(
            "/api/accounts/{account_id}",
            get(get_trading_account)
                .put(update_trading_account)
                .delete(delete_trading_account),
        )
        .route(
            "/api/accounts/{account_id}/default",
            get(get_or_create_default_account_endpoint),
        )
        .route("/api/account/list", get(list_all_accounts))
        .route("/api/account/overview", get(get_account_overview))
        .route(
            "/api/account/{account_id}/overview",
            get(get_specific_account_overview),
        )
        .route(
            "/api/account/{account_id}/strategy",
            get(get_account_strategy).put(update_account_strategy),
        )
        .route(
            "/api/prompts",
            get(list_prompt_templates).post(create_prompt_template),
        )
        .route(
            "/api/prompts/",
            get(list_prompt_templates).post(create_prompt_template),
        )
        .route(
            "/api/prompts/bindings",
            axum::routing::post(upsert_prompt_binding),
        )
        .route(
            "/api/prompts/bindings/{binding_id}",
            axum::routing::delete(delete_prompt_binding),
        )
        .route(
            "/api/prompts/{template_id}/copy",
            axum::routing::post(copy_prompt_template),
        )
        .route(
            "/api/prompts/{template_id}/name",
            axum::routing::patch(update_prompt_template_name),
        )
        .route(
            "/api/prompt-backtest/tasks",
            get(list_backtest_tasks).post(create_prompt_backtest_task),
        )
        .route(
            "/api/prompt-backtest/tasks/{task_id}",
            get(get_task_status).delete(delete_prompt_backtest_task),
        )
        .route(
            "/api/prompt-backtest/tasks/{task_id}/results",
            get(get_task_results),
        )
        .route("/api/prompt-backtest/items/{item_id}", get(get_item_detail))
        .route(
            "/api/prompt-backtest/tasks/{task_id}/items",
            get(get_task_items_for_import),
        )
        .route(
            "/api/prompt-backtest/tasks/{task_id}/retry",
            axum::routing::post(retry_prompt_backtest_task),
        )
        .route("/api/klines/backfill-tasks", get(get_backfill_tasks))
        .route("/api/klines/data", get(get_kline_data_placeholder))
        .route(
            "/api/klines/backfill/status/{task_id}",
            get(get_kline_backfill_status),
        )
        .route("/api/klines/backfill/tasks", get(list_kline_backfill_tasks))
        .route(
            "/api/klines/backfill",
            axum::routing::post(create_kline_backfill_task),
        )
        .route(
            "/api/klines/backfill-tasks/{task_id}",
            axum::routing::delete(delete_kline_backfill_task),
        )
        .route("/api/bot/configs", get(list_bot_configs))
        .route(
            "/api/bot/config/{platform}",
            get(get_bot_config).delete(proxy_http_request),
        )
        .route("/api/bot/config", axum::routing::post(proxy_http_request))
        .route("/api/bot/status", axum::routing::put(proxy_http_request))
        .route(
            "/api/bot/notification-config",
            get(get_notification_config).put(update_notification_config),
        )
        .route(
            "/api/analytics/ai-attribution/conversations",
            get(list_attribution_conversations),
        )
        .route("/api/analytics/summary", get(get_analytics_summary))
        .route("/api/analytics/by-strategy", get(get_analytics_by_strategy))
        .route("/api/analytics/by-account", get(get_analytics_by_account))
        .route("/api/analytics/by-symbol", get(get_analytics_by_symbol))
        .route(
            "/api/analytics/by-operation",
            get(get_analytics_by_operation),
        )
        .route(
            "/api/analytics/by-trigger-type",
            get(get_analytics_by_trigger_type),
        )
        .route("/api/analytics/by-factor", get(get_analytics_by_factor))
        .route(
            "/api/analytics/program-summary",
            get(get_program_analytics_summary),
        )
        .route(
            "/api/analytics/program-by-symbol",
            get(get_program_analytics_by_symbol),
        )
        .route(
            "/api/analytics/program-by-program",
            get(get_program_analytics_by_program),
        )
        .route(
            "/api/analytics/program-by-trigger-type",
            get(get_program_analytics_by_trigger_type),
        )
        .route(
            "/api/analytics/program-by-operation",
            get(get_program_analytics_by_operation),
        )
        .route(
            "/api/analytics/ai-attribution/conversations/{conversation_id}/messages",
            get(get_attribution_messages),
        )
        .route(
            "/api/analytics/ai-attribution/chat-stream",
            axum::routing::post(proxy_http_request),
        )
        .route("/api/arena/model-chat", get(get_model_chat))
        .route(
            "/api/arena/model-chat/{decision_id}/snapshots",
            get(get_model_chat_snapshots),
        )
        .route("/api/arena/check-pnl-status", get(check_pnl_sync_status))
        .route("/api/arena/trades", get(get_completed_trades))
        .route("/api/arena/positions", get(get_positions_snapshot))
        .route("/api/arena/analytics", get(get_aggregated_analytics))
        .route(
            "/api/arena/update-pnl",
            axum::routing::post(proxy_http_request),
        )
        .route(
            "/api/programs/test-run",
            axum::routing::post(test_run_program),
        )
        .route(
            "/api/programs/validate",
            axum::routing::post(validate_program_code),
        )
        .route(
            "/api/programs/ai-chat",
            axum::routing::post(chat_with_program_ai),
        )
        .route(
            "/api/programs/ai-conversations",
            get(list_program_conversations),
        )
        .route(
            "/api/programs/ai-conversations/{conversation_id}/messages",
            get(get_program_messages),
        )
        .route(
            "/api/programs/backtest",
            axum::routing::post(run_program_backtest),
        )
        .route("/api/programs/dev-guide", get(get_program_dev_guide))
        .route("/api/programs/signal-pools/", get(list_signal_pools))
        .route("/api/programs/accounts/", get(list_program_accounts))
        .route(
            "/api/programs/bindings/",
            get(list_bindings).post(create_binding),
        )
        .route(
            "/api/programs/bindings/{binding_id}",
            axum::routing::put(update_binding).delete(delete_binding),
        )
        .route(
            "/api/programs/bindings/{binding_id}/preview-run",
            axum::routing::post(preview_run_binding),
        )
        .route("/api/programs", get(list_programs).post(create_program))
        .route("/api/programs/", get(list_programs).post(create_program))
        .route(
            "/api/programs/{program_id}",
            get(get_program).put(update_program).delete(delete_program),
        )
        .route(
            "/api/prompts/{key}",
            axum::routing::put(update_prompt_template).delete(delete_prompt_template),
        )
        .route(
            "/api/prompts/ai-conversations",
            get(list_prompt_conversations),
        )
        .route(
            "/api/prompts/ai-conversations/{conversation_id}/messages",
            get(get_prompt_messages),
        )
        .route(
            "/api/prompts/ai-chat-stream",
            axum::routing::post(proxy_http_request),
        )
        .route("/api/signals", get(list_signals))
        .route("/api/signals/", get(list_signals))
        .route(
            "/api/signals/definitions",
            axum::routing::post(create_signal),
        )
        .route(
            "/api/signals/definitions/{signal_id}",
            get(get_signal).put(update_signal).delete(delete_signal),
        )
        .route("/api/signals/pools", axum::routing::post(create_pool))
        .route(
            "/api/signals/pools/{pool_id}",
            get(get_pool).put(update_pool).delete(delete_pool),
        )
        .route("/api/signals/logs", get(get_trigger_logs))
        .route(
            "/api/signals/ai-conversations",
            get(list_signal_conversations),
        )
        .route(
            "/api/signals/ai-conversations/{conversation_id}/messages",
            get(get_signal_messages),
        )
        .route(
            "/api/signals/ai-chat-stream",
            axum::routing::post(chat_with_signal_ai_stream),
        )
        .route(
            "/api/signals/create-pool-from-config",
            axum::routing::post(create_pool_from_config),
        )
        .route("/api/signals/analyze", get(get_signal_metric_analysis))
        .route(
            "/api/signals/backtest/{signal_id}",
            get(get_signal_backtest),
        )
        .route(
            "/api/signals/backtest-preview",
            axum::routing::post(get_signal_backtest_preview),
        )
        .route(
            "/api/signals/pool-backtest/{pool_id}",
            get(get_signal_pool_backtest),
        )
        .route("/api/signals/test/{signal_id}", get(get_signal_test))
        .route("/api/signals/states", get(get_signal_states))
        .route(
            "/api/signals/states/reset",
            axum::routing::post(reset_signal_states),
        )
        .route(
            "/api/signals/wallet-tracking/status",
            get(get_wallet_tracking_status),
        )
        .route(
            "/api/signals/wallet-tracking/runtime",
            axum::routing::put(update_wallet_tracking_runtime),
        )
        .route(
            "/api/signals/wallet-tracking/token",
            axum::routing::post(sync_wallet_tracking_token).delete(clear_wallet_tracking_token),
        )
        .route("/ws", get(proxy_websocket))
        .route("/", any(proxy_http_request))
        .route("/{*path}", any(proxy_http_request))
        .layer(
            TraceLayer::new_for_http()
                .make_span_with(DefaultMakeSpan::new().level(Level::INFO))
                .on_response(DefaultOnResponse::new().level(Level::INFO)),
        )
        .layer(CorsLayer::permissive())
        .with_state(state)
}

#[cfg(test)]
mod tests {
    use std::{
        net::{IpAddr, Ipv4Addr, SocketAddr},
        sync::{
            Arc, OnceLock,
            atomic::{AtomicUsize, Ordering},
        },
        time::Duration,
    };

    use axum::{
        Json, Router,
        body::{Body, to_bytes},
        http::{Request, StatusCode, header},
        response::IntoResponse,
        routing::{delete, get, post, put},
    };
    use chrono::Utc;
    use serde_json::{Value, json};
    use sqlx::{PgPool, Row, postgres::PgPoolOptions};
    use tokio::{net::TcpListener, sync::Mutex as AsyncMutex};
    use tower::ServiceExt;
    use url::Url;
    use uuid::Uuid;

    use crate::{
        config::AppConfig,
        wallet_tracking_runtime::{
            WalletTrackingRuntimeSnapshot, reset_snapshot_for_tests, set_snapshot_for_tests,
        },
    };

    use super::build_router;

    #[tokio::test]
    async fn health_route_stays_on_rust_side() {
        let router = build_router(AppConfig::for_tests());
        let response = router
            .oneshot(
                Request::builder()
                    .uri("/api/health")
                    .body(Body::empty())
                    .expect("health request should be valid"),
            )
            .await
            .expect("router should answer health request");

        assert_eq!(response.status(), 200);
    }

    #[tokio::test]
    async fn accounts_list_route_rejects_missing_session_without_proxying() {
        let legacy_accounts_hits = Arc::new(AtomicUsize::new(0));
        let upstream = Router::new()
            .route(
                "/api/accounts/",
                get({
                    let legacy_accounts_hits = Arc::clone(&legacy_accounts_hits);
                    move || {
                        let legacy_accounts_hits = Arc::clone(&legacy_accounts_hits);
                        async move {
                            legacy_accounts_hits.fetch_add(1, Ordering::SeqCst);
                            Json(json!({"source": "legacy-accounts-list"}))
                        }
                    }
                }),
            )
            .route(
                "/api/accounts",
                get({
                    let legacy_accounts_hits = Arc::clone(&legacy_accounts_hits);
                    move || {
                        let legacy_accounts_hits = Arc::clone(&legacy_accounts_hits);
                        async move {
                            legacy_accounts_hits.fetch_add(1, Ordering::SeqCst);
                            Json(json!({"source": "legacy-accounts-list-no-slash"}))
                        }
                    }
                }),
            );
        let upstream_addr = spawn_test_legacy_server(upstream).await;
        let router = build_router(test_config_for_legacy_http(upstream_addr));

        let response = router
            .clone()
            .oneshot(
                Request::builder()
                    .uri("/api/accounts/")
                    .body(Body::empty())
                    .expect("accounts list request should be valid"),
            )
            .await
            .expect("router should answer accounts list request");

        assert_eq!(response.status(), StatusCode::BAD_REQUEST);
        let no_slash_response = router
            .oneshot(
                Request::builder()
                    .uri("/api/accounts")
                    .body(Body::empty())
                    .expect("accounts list no-slash request should be valid"),
            )
            .await
            .expect("router should answer accounts list no-slash request");

        assert_eq!(no_slash_response.status(), StatusCode::BAD_REQUEST);
        assert_eq!(legacy_accounts_hits.load(Ordering::SeqCst), 0);
    }

    #[tokio::test]
    async fn account_detail_route_rejects_non_integer_path_without_proxying() {
        let legacy_account_detail_hits = Arc::new(AtomicUsize::new(0));
        let upstream = Router::new().route(
            "/api/accounts/{account_id}",
            get({
                let legacy_account_detail_hits = Arc::clone(&legacy_account_detail_hits);
                move || {
                    let legacy_account_detail_hits = Arc::clone(&legacy_account_detail_hits);
                    async move {
                        legacy_account_detail_hits.fetch_add(1, Ordering::SeqCst);
                        Json(json!({"source": "legacy-account-detail"}))
                    }
                }
            }),
        );
        let upstream_addr = spawn_test_legacy_server(upstream).await;
        let router = build_router(test_config_for_legacy_http(upstream_addr));

        let response = router
            .oneshot(
                Request::builder()
                    .uri("/api/accounts/not-an-int?session_token=test-token")
                    .body(Body::empty())
                    .expect("account detail request should be valid"),
            )
            .await
            .expect("router should answer account detail request");

        assert_eq!(response.status(), StatusCode::BAD_REQUEST);
        assert_eq!(legacy_account_detail_hits.load(Ordering::SeqCst), 0);
    }

    #[tokio::test]
    async fn account_list_route_uses_native_balance_snapshot_without_legacy_fallback() {
        let pool = local_db_pool().await;
        let (account_id, expected_available, expected_used_margin) =
            create_account_balance_snapshot_test_account(&pool).await;

        let legacy_balance_hits = Arc::new(AtomicUsize::new(0));
        let upstream = Router::new().route(
            "/api/hyperliquid/accounts/{account_id}/balance",
            get({
                let legacy_balance_hits = Arc::clone(&legacy_balance_hits);
                move || {
                    let legacy_balance_hits = Arc::clone(&legacy_balance_hits);
                    async move {
                        legacy_balance_hits.fetch_add(1, Ordering::SeqCst);
                        Json(json!({
                            "available_balance": 999_999.0,
                            "used_margin": 888_888.0
                        }))
                    }
                }
            }),
        );
        let upstream_addr = spawn_test_legacy_server(upstream).await;
        let router = build_router(test_config_for_legacy_http(upstream_addr));

        let response = router
            .oneshot(
                Request::builder()
                    .uri("/api/account/list")
                    .body(Body::empty())
                    .expect("account list request should be valid"),
            )
            .await
            .expect("router should answer account list request");

        assert_eq!(response.status(), StatusCode::OK);
        let body = to_bytes(response.into_body(), usize::MAX)
            .await
            .expect("account list response should be readable");
        let payload: Value = serde_json::from_slice(&body).expect("account list response json");
        let account = payload
            .as_array()
            .and_then(|items| {
                items
                    .iter()
                    .find(|item| item["id"] == json!(account_id))
                    .cloned()
            })
            .expect("fixture account should exist in account list response");

        assert_eq!(account["current_cash"], json!(expected_available));
        assert_eq!(account["frozen_cash"], json!(expected_used_margin));
        assert_eq!(legacy_balance_hits.load(Ordering::SeqCst), 0);

        cleanup_account_balance_snapshot_test_account(&pool, account_id).await;
    }

    #[tokio::test]
    async fn account_overview_route_uses_native_balance_snapshot_without_legacy_fallback() {
        let pool = local_db_pool().await;
        let (account_id, expected_available, expected_used_margin) =
            create_account_balance_snapshot_test_account(&pool).await;

        let legacy_balance_hits = Arc::new(AtomicUsize::new(0));
        let upstream = Router::new().route(
            "/api/hyperliquid/accounts/{account_id}/balance",
            get({
                let legacy_balance_hits = Arc::clone(&legacy_balance_hits);
                move || {
                    let legacy_balance_hits = Arc::clone(&legacy_balance_hits);
                    async move {
                        legacy_balance_hits.fetch_add(1, Ordering::SeqCst);
                        Json(json!({
                            "available_balance": 999_999.0,
                            "used_margin": 888_888.0
                        }))
                    }
                }
            }),
        );
        let upstream_addr = spawn_test_legacy_server(upstream).await;
        let router = build_router(test_config_for_legacy_http(upstream_addr));

        let response = router
            .oneshot(
                Request::builder()
                    .uri(format!("/api/account/{account_id}/overview"))
                    .body(Body::empty())
                    .expect("account overview request should be valid"),
            )
            .await
            .expect("router should answer account overview request");

        assert_eq!(response.status(), StatusCode::OK);
        let body = to_bytes(response.into_body(), usize::MAX)
            .await
            .expect("account overview response should be readable");
        let payload: Value = serde_json::from_slice(&body).expect("account overview response json");

        assert_eq!(payload["account"]["id"], json!(account_id));
        assert_eq!(
            payload["account"]["current_cash"],
            json!(expected_available)
        );
        assert_eq!(
            payload["account"]["frozen_cash"],
            json!(expected_used_margin)
        );
        assert_eq!(payload["total_assets"], json!(expected_available));
        assert_eq!(legacy_balance_hits.load(Ordering::SeqCst), 0);

        cleanup_account_balance_snapshot_test_account(&pool, account_id).await;
    }

    #[tokio::test]
    async fn account_strategy_update_route_updates_natively_without_legacy_sync() {
        let pool = local_db_pool().await;
        let account_id = create_account_strategy_test_account(&pool, "true").await;

        let legacy_strategy_put_hits = Arc::new(AtomicUsize::new(0));
        let upstream = Router::new().route(
            "/api/account/{account_id}/strategy",
            put({
                let legacy_strategy_put_hits = Arc::clone(&legacy_strategy_put_hits);
                move |Json(_payload): Json<Value>| {
                    let legacy_strategy_put_hits = Arc::clone(&legacy_strategy_put_hits);
                    async move {
                        legacy_strategy_put_hits.fetch_add(1, Ordering::SeqCst);
                        Json(json!({"source": "legacy-account-strategy-put"}))
                    }
                }
            }),
        );
        let upstream_addr = spawn_test_legacy_server(upstream).await;
        let router = build_router(test_config_for_legacy_http(upstream_addr));

        let response = router
            .oneshot(
                Request::builder()
                    .method("PUT")
                    .uri(format!("/api/account/{account_id}/strategy"))
                    .header("content-type", "application/json")
                    .body(Body::from(
                        json!({
                            "enabled": true,
                            "scheduled_trigger_enabled": false,
                            "exchange": "binance",
                            "interval_seconds": 300,
                            "price_threshold": 1.5,
                            "signal_pool_ids": [101, 202]
                        })
                        .to_string(),
                    ))
                    .expect("account strategy update request should be valid"),
            )
            .await
            .expect("router should answer account strategy update request");

        assert_eq!(response.status(), StatusCode::OK);
        let body = to_bytes(response.into_body(), usize::MAX)
            .await
            .expect("account strategy update response should be readable");
        let payload: Value =
            serde_json::from_slice(&body).expect("account strategy update response json");
        assert_eq!(payload["interval_seconds"], json!(300));
        assert_eq!(payload["enabled"], json!(true));
        assert_eq!(payload["scheduled_trigger_enabled"], json!(false));
        assert_eq!(payload["exchange"], json!("binance"));
        assert_eq!(payload["price_threshold"], json!(1.5));
        assert_eq!(payload["signal_pool_id"], json!(101));
        assert_eq!(payload["signal_pool_ids"], json!([101, 202]));

        let stored = sqlx::query(
            r#"
            SELECT trigger_interval, price_threshold::float8 AS price_threshold,
                   enabled, scheduled_trigger_enabled, exchange, signal_pool_ids
            FROM account_strategy_configs
            WHERE account_id = $1
            "#,
        )
        .bind(account_id)
        .fetch_one(&pool)
        .await
        .expect("strategy row should persist natively");
        assert_eq!(
            stored
                .try_get::<i32, _>("trigger_interval")
                .expect("trigger interval should read"),
            300
        );
        assert_eq!(
            stored
                .try_get::<f64, _>("price_threshold")
                .expect("price threshold should read"),
            1.5
        );
        assert_eq!(
            stored
                .try_get::<String, _>("enabled")
                .expect("enabled should read"),
            "true"
        );
        assert_eq!(
            stored
                .try_get::<bool, _>("scheduled_trigger_enabled")
                .expect("scheduled trigger flag should read"),
            false
        );
        assert_eq!(
            stored
                .try_get::<Option<String>, _>("exchange")
                .expect("exchange should read")
                .expect("exchange should persist"),
            "binance"
        );
        assert_eq!(
            stored
                .try_get::<Option<String>, _>("signal_pool_ids")
                .expect("signal pool ids should read")
                .expect("signal pool ids should persist"),
            "[101,202]"
        );
        assert_eq!(legacy_strategy_put_hits.load(Ordering::SeqCst), 0);

        cleanup_account_strategy_test_account(&pool, account_id).await;
    }

    #[tokio::test]
    async fn account_strategy_get_route_creates_default_without_legacy_sync() {
        let pool = local_db_pool().await;
        let account_id = create_account_strategy_test_account(&pool, "false").await;

        let legacy_strategy_get_hits = Arc::new(AtomicUsize::new(0));
        let upstream = Router::new().route(
            "/api/account/{account_id}/strategy",
            get({
                let legacy_strategy_get_hits = Arc::clone(&legacy_strategy_get_hits);
                move || {
                    let legacy_strategy_get_hits = Arc::clone(&legacy_strategy_get_hits);
                    async move {
                        legacy_strategy_get_hits.fetch_add(1, Ordering::SeqCst);
                        Json(json!({"source": "legacy-account-strategy-get"}))
                    }
                }
            }),
        );
        let upstream_addr = spawn_test_legacy_server(upstream).await;
        let router = build_router(test_config_for_legacy_http(upstream_addr));

        let response = router
            .oneshot(
                Request::builder()
                    .uri(format!("/api/account/{account_id}/strategy"))
                    .body(Body::empty())
                    .expect("account strategy get request should be valid"),
            )
            .await
            .expect("router should answer account strategy get request");

        assert_eq!(response.status(), StatusCode::OK);
        let body = to_bytes(response.into_body(), usize::MAX)
            .await
            .expect("account strategy get response should be readable");
        let payload: Value =
            serde_json::from_slice(&body).expect("account strategy get response json");
        assert_eq!(payload["trigger_mode"], json!("unified"));
        assert_eq!(payload["interval_seconds"], json!(150));
        assert_eq!(payload["enabled"], json!(false));
        assert_eq!(payload["scheduled_trigger_enabled"], json!(true));
        assert_eq!(payload["exchange"], json!("hyperliquid"));
        assert_eq!(payload["price_threshold"], json!(1.0));
        assert_eq!(payload["signal_pool_id"], Value::Null);
        assert_eq!(payload["signal_pool_ids"], Value::Null);

        let stored = sqlx::query(
            r#"
            SELECT trigger_interval, price_threshold::float8 AS price_threshold,
                   enabled, scheduled_trigger_enabled, exchange
            FROM account_strategy_configs
            WHERE account_id = $1
            "#,
        )
        .bind(account_id)
        .fetch_optional(&pool)
        .await
        .expect("default strategy row query should succeed")
        .expect("default strategy row should be created");
        assert_eq!(
            stored
                .try_get::<i32, _>("trigger_interval")
                .expect("trigger interval should read"),
            150
        );
        assert_eq!(
            stored
                .try_get::<f64, _>("price_threshold")
                .expect("price threshold should read"),
            1.0
        );
        assert_eq!(
            stored
                .try_get::<String, _>("enabled")
                .expect("enabled should read"),
            "false"
        );
        assert_eq!(
            stored
                .try_get::<bool, _>("scheduled_trigger_enabled")
                .expect("scheduled trigger flag should read"),
            true
        );
        assert_eq!(
            stored
                .try_get::<Option<String>, _>("exchange")
                .expect("exchange should read")
                .expect("exchange should persist"),
            "hyperliquid"
        );
        assert_eq!(legacy_strategy_get_hits.load(Ordering::SeqCst), 0);

        cleanup_account_strategy_test_account(&pool, account_id).await;
    }

    #[tokio::test]
    async fn hyperliquid_wallet_config_route_forwards_legacy_contract_through_native_handler() {
        let legacy_wallet_config_hits = Arc::new(AtomicUsize::new(0));
        let upstream = Router::new().route(
            "/api/hyperliquid/accounts/{account_id}/wallet",
            post({
                let legacy_wallet_config_hits = Arc::clone(&legacy_wallet_config_hits);
                move |axum::extract::Path(account_id): axum::extract::Path<String>,
                      Json(payload): Json<Value>| {
                    let legacy_wallet_config_hits = Arc::clone(&legacy_wallet_config_hits);
                    async move {
                        legacy_wallet_config_hits.fetch_add(1, Ordering::SeqCst);
                        assert_eq!(account_id, "77");
                        assert_eq!(payload["environment"], json!("mainnet"));
                        assert_eq!(
                            payload["private_key"],
                            json!(
                                "0x0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
                            )
                        );
                        assert_eq!(payload["max_leverage"], json!(7));
                        assert_eq!(payload["default_leverage"], json!(3));

                        Json(json!({
                            "success": true,
                            "walletId": 321,
                            "walletAddress": "0xabc123",
                            "message": "Mainnet wallet configured for account"
                        }))
                    }
                }
            }),
        );
        let upstream_addr = spawn_test_legacy_server(upstream).await;
        let router = build_router(test_config_for_legacy_http(upstream_addr));

        let response = router
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/api/hyperliquid/accounts/77/wallet")
                    .header("content-type", "application/json")
                    .body(Body::from(
                        json!({
                            "privateKey": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
                            "environment": "mainnet",
                            "maxLeverage": 7,
                            "defaultLeverage": 3
                        })
                        .to_string(),
                    ))
                    .expect("wallet config request should be valid"),
            )
            .await
            .expect("router should answer wallet config request");

        assert_eq!(response.status(), StatusCode::OK);
        let body = to_bytes(response.into_body(), usize::MAX)
            .await
            .expect("wallet config response body should be readable");
        let payload: Value =
            serde_json::from_slice(&body).expect("wallet config response should be json");
        assert_eq!(payload["success"], json!(true));
        assert_eq!(payload["walletId"], json!(321));
        assert_eq!(payload["walletAddress"], json!("0xabc123"));
        assert_eq!(legacy_wallet_config_hits.load(Ordering::SeqCst), 1);
    }

    #[tokio::test]
    async fn hyperliquid_wallet_config_route_validates_path_and_payload_without_proxying() {
        let legacy_wallet_config_hits = Arc::new(AtomicUsize::new(0));
        let upstream = Router::new().route(
            "/api/hyperliquid/accounts/{account_id}/wallet",
            post({
                let legacy_wallet_config_hits = Arc::clone(&legacy_wallet_config_hits);
                move || {
                    let legacy_wallet_config_hits = Arc::clone(&legacy_wallet_config_hits);
                    async move {
                        legacy_wallet_config_hits.fetch_add(1, Ordering::SeqCst);
                        Json(json!({"source": "legacy"}))
                    }
                }
            }),
        );
        let upstream_addr = spawn_test_legacy_server(upstream).await;
        let router = build_router(test_config_for_legacy_http(upstream_addr));

        let invalid_id_response = router
            .clone()
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/api/hyperliquid/accounts/not-an-int/wallet")
                    .header("content-type", "application/json")
                    .body(Body::from(
                        json!({
                            "privateKey": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
                        })
                        .to_string(),
                    ))
                    .expect("invalid account id request should be valid"),
            )
            .await
            .expect("router should answer invalid account id request");

        assert_eq!(
            invalid_id_response.status(),
            StatusCode::UNPROCESSABLE_ENTITY
        );
        let invalid_id_body = to_bytes(invalid_id_response.into_body(), usize::MAX)
            .await
            .expect("invalid account id response should be readable");
        let invalid_id_payload: Value =
            serde_json::from_slice(&invalid_id_body).expect("invalid account id response json");
        assert_eq!(
            invalid_id_payload["detail"],
            json!("account_id must be a valid integer")
        );

        let invalid_private_key_response = router
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/api/hyperliquid/accounts/77/wallet")
                    .header("content-type", "application/json")
                    .body(Body::from(
                        json!({
                            "privateKey": "bad-key",
                            "environment": "testnet"
                        })
                        .to_string(),
                    ))
                    .expect("invalid private key request should be valid"),
            )
            .await
            .expect("router should answer invalid private key request");

        assert_eq!(
            invalid_private_key_response.status(),
            StatusCode::UNPROCESSABLE_ENTITY
        );
        let invalid_private_key_body =
            to_bytes(invalid_private_key_response.into_body(), usize::MAX)
                .await
                .expect("invalid private key response should be readable");
        let invalid_private_key_payload: Value = serde_json::from_slice(&invalid_private_key_body)
            .expect("invalid private key response json");
        assert_eq!(
            invalid_private_key_payload["detail"],
            json!(
                "Invalid private key format. Must be 64 hex characters (with or without 0x prefix)"
            )
        );
        assert_eq!(legacy_wallet_config_hits.load(Ordering::SeqCst), 0);
    }

    #[tokio::test]
    async fn hyperliquid_wallet_delete_route_forwards_legacy_contract_through_native_handler() {
        let legacy_wallet_delete_hits = Arc::new(AtomicUsize::new(0));
        let upstream = Router::new().route(
            "/api/hyperliquid/accounts/{account_id}/wallet",
            delete({
                let legacy_wallet_delete_hits = Arc::clone(&legacy_wallet_delete_hits);
                move |axum::extract::Path(account_id): axum::extract::Path<String>,
                      axum::extract::Query(query): axum::extract::Query<
                    std::collections::HashMap<String, String>,
                >| {
                    let legacy_wallet_delete_hits = Arc::clone(&legacy_wallet_delete_hits);
                    async move {
                        legacy_wallet_delete_hits.fetch_add(1, Ordering::SeqCst);
                        assert_eq!(account_id, "77");
                        assert_eq!(
                            query.get("environment").map(String::as_str),
                            Some("mainnet")
                        );

                        Json(json!({
                            "success": true,
                            "accountId": 77,
                            "accountName": "Wallet Delete Test",
                            "environment": "mainnet",
                            "message": "Mainnet wallet deleted"
                        }))
                    }
                }
            }),
        );
        let upstream_addr = spawn_test_legacy_server(upstream).await;
        let router = build_router(test_config_for_legacy_http(upstream_addr));

        let response = router
            .oneshot(
                Request::builder()
                    .method("DELETE")
                    .uri("/api/hyperliquid/accounts/77/wallet?environment=mainnet")
                    .body(Body::empty())
                    .expect("wallet delete request should be valid"),
            )
            .await
            .expect("router should answer wallet delete request");

        assert_eq!(response.status(), StatusCode::OK);
        let body = to_bytes(response.into_body(), usize::MAX)
            .await
            .expect("wallet delete response body should be readable");
        let payload: Value =
            serde_json::from_slice(&body).expect("wallet delete response should be json");
        assert_eq!(payload["success"], json!(true));
        assert_eq!(payload["accountId"], json!(77));
        assert_eq!(payload["environment"], json!("mainnet"));
        assert_eq!(legacy_wallet_delete_hits.load(Ordering::SeqCst), 1);
    }

    #[tokio::test]
    async fn hyperliquid_wallet_delete_route_validates_path_and_query_without_proxying() {
        let legacy_wallet_delete_hits = Arc::new(AtomicUsize::new(0));
        let upstream = Router::new().route(
            "/api/hyperliquid/accounts/{account_id}/wallet",
            delete({
                let legacy_wallet_delete_hits = Arc::clone(&legacy_wallet_delete_hits);
                move || {
                    let legacy_wallet_delete_hits = Arc::clone(&legacy_wallet_delete_hits);
                    async move {
                        legacy_wallet_delete_hits.fetch_add(1, Ordering::SeqCst);
                        Json(json!({"source": "legacy"}))
                    }
                }
            }),
        );
        let upstream_addr = spawn_test_legacy_server(upstream).await;
        let router = build_router(test_config_for_legacy_http(upstream_addr));

        let invalid_id_response = router
            .clone()
            .oneshot(
                Request::builder()
                    .method("DELETE")
                    .uri("/api/hyperliquid/accounts/not-an-int/wallet?environment=testnet")
                    .body(Body::empty())
                    .expect("invalid account id delete request should be valid"),
            )
            .await
            .expect("router should answer invalid account id delete request");
        assert_eq!(
            invalid_id_response.status(),
            StatusCode::UNPROCESSABLE_ENTITY
        );
        let invalid_id_body = to_bytes(invalid_id_response.into_body(), usize::MAX)
            .await
            .expect("invalid account id delete response should be readable");
        let invalid_id_payload: Value =
            serde_json::from_slice(&invalid_id_body).expect("invalid account id delete json");
        assert_eq!(
            invalid_id_payload["detail"],
            json!("account_id must be a valid integer")
        );

        let missing_environment_response = router
            .clone()
            .oneshot(
                Request::builder()
                    .method("DELETE")
                    .uri("/api/hyperliquid/accounts/77/wallet")
                    .body(Body::empty())
                    .expect("missing environment delete request should be valid"),
            )
            .await
            .expect("router should answer missing environment delete request");
        assert_eq!(
            missing_environment_response.status(),
            StatusCode::UNPROCESSABLE_ENTITY
        );
        let missing_environment_body =
            to_bytes(missing_environment_response.into_body(), usize::MAX)
                .await
                .expect("missing environment delete response should be readable");
        let missing_environment_payload: Value = serde_json::from_slice(&missing_environment_body)
            .expect("missing environment delete response json");
        assert_eq!(
            missing_environment_payload["detail"],
            json!("environment query parameter is required")
        );

        let invalid_environment_response = router
            .oneshot(
                Request::builder()
                    .method("DELETE")
                    .uri("/api/hyperliquid/accounts/77/wallet?environment=sandbox")
                    .body(Body::empty())
                    .expect("invalid environment delete request should be valid"),
            )
            .await
            .expect("router should answer invalid environment delete request");
        assert_eq!(
            invalid_environment_response.status(),
            StatusCode::UNPROCESSABLE_ENTITY
        );
        let invalid_environment_body =
            to_bytes(invalid_environment_response.into_body(), usize::MAX)
                .await
                .expect("invalid environment delete response should be readable");
        let invalid_environment_payload: Value = serde_json::from_slice(&invalid_environment_body)
            .expect("invalid environment delete response json");
        assert_eq!(
            invalid_environment_payload["detail"],
            json!("environment query parameter must be 'testnet' or 'mainnet'")
        );

        assert_eq!(legacy_wallet_delete_hits.load(Ordering::SeqCst), 0);
    }

    #[tokio::test]
    async fn hyperliquid_trading_mode_route_forwards_legacy_contract_through_native_handler() {
        let legacy_trading_mode_hits = Arc::new(AtomicUsize::new(0));
        let upstream = Router::new().route(
            "/api/hyperliquid/trading-mode",
            post({
                let legacy_trading_mode_hits = Arc::clone(&legacy_trading_mode_hits);
                move |Json(payload): Json<Value>| {
                    let legacy_trading_mode_hits = Arc::clone(&legacy_trading_mode_hits);
                    async move {
                        legacy_trading_mode_hits.fetch_add(1, Ordering::SeqCst);
                        assert_eq!(payload["mode"], json!("mainnet"));

                        Json(json!({
                            "success": true,
                            "mode": "mainnet",
                            "changed": true,
                            "oldMode": "testnet",
                            "message": "Trading mode switched from testnet to mainnet"
                        }))
                    }
                }
            }),
        );
        let upstream_addr = spawn_test_legacy_server(upstream).await;
        let router = build_router(test_config_for_legacy_http(upstream_addr));

        let response = router
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/api/hyperliquid/trading-mode")
                    .header("content-type", "application/json")
                    .body(Body::from(json!({ "mode": "mainnet" }).to_string()))
                    .expect("trading mode request should be valid"),
            )
            .await
            .expect("router should answer trading mode request");

        assert_eq!(response.status(), StatusCode::OK);
        let body = to_bytes(response.into_body(), usize::MAX)
            .await
            .expect("trading mode response body should be readable");
        let payload: Value =
            serde_json::from_slice(&body).expect("trading mode response should be json");
        assert_eq!(payload["success"], json!(true));
        assert_eq!(payload["mode"], json!("mainnet"));
        assert_eq!(payload["changed"], json!(true));
        assert_eq!(legacy_trading_mode_hits.load(Ordering::SeqCst), 1);
    }

    #[tokio::test]
    async fn hyperliquid_trading_mode_route_validates_payload_without_proxying() {
        let legacy_trading_mode_hits = Arc::new(AtomicUsize::new(0));
        let upstream = Router::new().route(
            "/api/hyperliquid/trading-mode",
            post({
                let legacy_trading_mode_hits = Arc::clone(&legacy_trading_mode_hits);
                move || {
                    let legacy_trading_mode_hits = Arc::clone(&legacy_trading_mode_hits);
                    async move {
                        legacy_trading_mode_hits.fetch_add(1, Ordering::SeqCst);
                        Json(json!({"source": "legacy"}))
                    }
                }
            }),
        );
        let upstream_addr = spawn_test_legacy_server(upstream).await;
        let router = build_router(test_config_for_legacy_http(upstream_addr));

        let missing_mode_response = router
            .clone()
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/api/hyperliquid/trading-mode")
                    .header("content-type", "application/json")
                    .body(Body::from(json!({}).to_string()))
                    .expect("missing mode request should be valid"),
            )
            .await
            .expect("router should answer missing mode request");
        assert_eq!(
            missing_mode_response.status(),
            StatusCode::UNPROCESSABLE_ENTITY
        );
        let missing_mode_body = to_bytes(missing_mode_response.into_body(), usize::MAX)
            .await
            .expect("missing mode response should be readable");
        let missing_mode_payload: Value =
            serde_json::from_slice(&missing_mode_body).expect("missing mode response json");
        assert_eq!(missing_mode_payload["detail"], json!("mode is required"));

        let invalid_mode_response = router
            .clone()
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/api/hyperliquid/trading-mode")
                    .header("content-type", "application/json")
                    .body(Body::from(json!({ "mode": "sandbox" }).to_string()))
                    .expect("invalid mode request should be valid"),
            )
            .await
            .expect("router should answer invalid mode request");
        assert_eq!(
            invalid_mode_response.status(),
            StatusCode::UNPROCESSABLE_ENTITY
        );
        let invalid_mode_body = to_bytes(invalid_mode_response.into_body(), usize::MAX)
            .await
            .expect("invalid mode response should be readable");
        let invalid_mode_payload: Value =
            serde_json::from_slice(&invalid_mode_body).expect("invalid mode response json");
        assert_eq!(
            invalid_mode_payload["detail"],
            json!("mode must be 'testnet' or 'mainnet'")
        );

        let non_string_mode_response = router
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/api/hyperliquid/trading-mode")
                    .header("content-type", "application/json")
                    .body(Body::from(json!({ "mode": 1 }).to_string()))
                    .expect("non-string mode request should be valid"),
            )
            .await
            .expect("router should answer non-string mode request");
        assert_eq!(
            non_string_mode_response.status(),
            StatusCode::UNPROCESSABLE_ENTITY
        );
        let non_string_mode_body = to_bytes(non_string_mode_response.into_body(), usize::MAX)
            .await
            .expect("non-string mode response should be readable");
        let non_string_mode_payload: Value =
            serde_json::from_slice(&non_string_mode_body).expect("non-string mode response json");
        assert_eq!(
            non_string_mode_payload["detail"],
            json!("mode must be a string")
        );

        assert_eq!(legacy_trading_mode_hits.load(Ordering::SeqCst), 0);
    }

    #[tokio::test]
    async fn hyperliquid_disable_route_forwards_legacy_contract_through_native_handler() {
        let legacy_disable_hits = Arc::new(AtomicUsize::new(0));
        let upstream = Router::new().route(
            "/api/hyperliquid/accounts/{account_id}/disable",
            post({
                let legacy_disable_hits = Arc::clone(&legacy_disable_hits);
                move |axum::extract::Path(account_id): axum::extract::Path<String>| {
                    let legacy_disable_hits = Arc::clone(&legacy_disable_hits);
                    async move {
                        legacy_disable_hits.fetch_add(1, Ordering::SeqCst);
                        assert_eq!(account_id, "77");
                        Json(json!({
                            "status": "success",
                            "account_id": 77,
                            "account_name": "Disable Route Test",
                            "message": "Hyperliquid trading disabled successfully"
                        }))
                    }
                }
            }),
        );
        let upstream_addr = spawn_test_legacy_server(upstream).await;
        let router = build_router(test_config_for_legacy_http(upstream_addr));

        let response = router
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/api/hyperliquid/accounts/77/disable")
                    .body(Body::empty())
                    .expect("disable request should be valid"),
            )
            .await
            .expect("router should answer disable request");

        assert_eq!(response.status(), StatusCode::OK);
        let body = to_bytes(response.into_body(), usize::MAX)
            .await
            .expect("disable response body should be readable");
        let payload: Value =
            serde_json::from_slice(&body).expect("disable response should be json");
        assert_eq!(payload["status"], json!("success"));
        assert_eq!(payload["account_id"], json!(77));
        assert_eq!(
            payload["message"],
            json!("Hyperliquid trading disabled successfully")
        );
        assert_eq!(legacy_disable_hits.load(Ordering::SeqCst), 1);
    }

    #[tokio::test]
    async fn hyperliquid_disable_route_validates_path_without_proxying() {
        let legacy_disable_hits = Arc::new(AtomicUsize::new(0));
        let upstream = Router::new().route(
            "/api/hyperliquid/accounts/{account_id}/disable",
            post({
                let legacy_disable_hits = Arc::clone(&legacy_disable_hits);
                move || {
                    let legacy_disable_hits = Arc::clone(&legacy_disable_hits);
                    async move {
                        legacy_disable_hits.fetch_add(1, Ordering::SeqCst);
                        Json(json!({"source": "legacy"}))
                    }
                }
            }),
        );
        let upstream_addr = spawn_test_legacy_server(upstream).await;
        let router = build_router(test_config_for_legacy_http(upstream_addr));

        let invalid_id_response = router
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/api/hyperliquid/accounts/not-an-int/disable")
                    .body(Body::empty())
                    .expect("invalid disable request should be valid"),
            )
            .await
            .expect("router should answer invalid disable request");
        assert_eq!(
            invalid_id_response.status(),
            StatusCode::UNPROCESSABLE_ENTITY
        );
        let invalid_id_body = to_bytes(invalid_id_response.into_body(), usize::MAX)
            .await
            .expect("invalid disable response should be readable");
        let invalid_id_payload: Value =
            serde_json::from_slice(&invalid_id_body).expect("invalid disable response json");
        assert_eq!(
            invalid_id_payload["detail"],
            json!("account_id must be a valid integer")
        );

        assert_eq!(legacy_disable_hits.load(Ordering::SeqCst), 0);
    }

    #[tokio::test]
    async fn hyperliquid_enable_route_forwards_legacy_contract_through_native_handler() {
        let legacy_enable_hits = Arc::new(AtomicUsize::new(0));
        let upstream = Router::new().route(
            "/api/hyperliquid/accounts/{account_id}/enable",
            post({
                let legacy_enable_hits = Arc::clone(&legacy_enable_hits);
                move |axum::extract::Path(account_id): axum::extract::Path<String>| {
                    let legacy_enable_hits = Arc::clone(&legacy_enable_hits);
                    async move {
                        legacy_enable_hits.fetch_add(1, Ordering::SeqCst);
                        assert_eq!(account_id, "88");
                        Json(json!({
                            "status": "success",
                            "account_id": 88,
                            "account_name": "Enable Route Test",
                            "message": "Hyperliquid trading enabled successfully"
                        }))
                    }
                }
            }),
        );
        let upstream_addr = spawn_test_legacy_server(upstream).await;
        let router = build_router(test_config_for_legacy_http(upstream_addr));

        let response = router
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/api/hyperliquid/accounts/88/enable")
                    .body(Body::empty())
                    .expect("enable request should be valid"),
            )
            .await
            .expect("router should answer enable request");

        assert_eq!(response.status(), StatusCode::OK);
        let body = to_bytes(response.into_body(), usize::MAX)
            .await
            .expect("enable response body should be readable");
        let payload: Value = serde_json::from_slice(&body).expect("enable response should be json");
        assert_eq!(payload["status"], json!("success"));
        assert_eq!(payload["account_id"], json!(88));
        assert_eq!(
            payload["message"],
            json!("Hyperliquid trading enabled successfully")
        );
        assert_eq!(legacy_enable_hits.load(Ordering::SeqCst), 1);
    }

    #[tokio::test]
    async fn hyperliquid_enable_route_validates_path_without_proxying() {
        let legacy_enable_hits = Arc::new(AtomicUsize::new(0));
        let upstream = Router::new().route(
            "/api/hyperliquid/accounts/{account_id}/enable",
            post({
                let legacy_enable_hits = Arc::clone(&legacy_enable_hits);
                move || {
                    let legacy_enable_hits = Arc::clone(&legacy_enable_hits);
                    async move {
                        legacy_enable_hits.fetch_add(1, Ordering::SeqCst);
                        Json(json!({"source": "legacy"}))
                    }
                }
            }),
        );
        let upstream_addr = spawn_test_legacy_server(upstream).await;
        let router = build_router(test_config_for_legacy_http(upstream_addr));

        let invalid_id_response = router
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/api/hyperliquid/accounts/not-an-int/enable")
                    .body(Body::empty())
                    .expect("invalid enable request should be valid"),
            )
            .await
            .expect("router should answer invalid enable request");
        assert_eq!(
            invalid_id_response.status(),
            StatusCode::UNPROCESSABLE_ENTITY
        );
        let invalid_id_body = to_bytes(invalid_id_response.into_body(), usize::MAX)
            .await
            .expect("invalid enable response should be readable");
        let invalid_id_payload: Value =
            serde_json::from_slice(&invalid_id_body).expect("invalid enable response json");
        assert_eq!(
            invalid_id_payload["detail"],
            json!("account_id must be a valid integer")
        );

        assert_eq!(legacy_enable_hits.load(Ordering::SeqCst), 0);
    }

    #[tokio::test]
    async fn hyperliquid_setup_route_forwards_legacy_contract_through_native_handler() {
        let legacy_setup_hits = Arc::new(AtomicUsize::new(0));
        let upstream = Router::new().route(
            "/api/hyperliquid/accounts/{account_id}/setup",
            post({
                let legacy_setup_hits = Arc::clone(&legacy_setup_hits);
                move |axum::extract::Path(account_id): axum::extract::Path<String>,
                      Json(payload): Json<Value>| {
                    let legacy_setup_hits = Arc::clone(&legacy_setup_hits);
                    async move {
                        legacy_setup_hits.fetch_add(1, Ordering::SeqCst);
                        assert_eq!(account_id, "77");
                        assert_eq!(payload["environment"], json!("mainnet"));
                        assert_eq!(
                            payload["private_key"],
                            json!(
                                "0x0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
                            )
                        );
                        assert_eq!(payload["max_leverage"], json!(5));
                        assert_eq!(payload["default_leverage"], json!(2));

                        Json(json!({
                            "status": "success",
                            "account_id": 77,
                            "environment": "mainnet",
                            "message": "Hyperliquid account setup completed successfully"
                        }))
                    }
                }
            }),
        );
        let upstream_addr = spawn_test_legacy_server(upstream).await;
        let router = build_router(test_config_for_legacy_http(upstream_addr));

        let response = router
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/api/hyperliquid/accounts/77/setup")
                    .header("content-type", "application/json")
                    .body(Body::from(
                        json!({
                            "environment": "mainnet",
                            "privateKey": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
                            "maxLeverage": 5,
                            "defaultLeverage": 2
                        })
                        .to_string(),
                    ))
                    .expect("setup request should be valid"),
            )
            .await
            .expect("router should answer setup request");

        assert_eq!(response.status(), StatusCode::OK);
        let body = to_bytes(response.into_body(), usize::MAX)
            .await
            .expect("setup response body should be readable");
        let payload: Value = serde_json::from_slice(&body).expect("setup response should be json");
        assert_eq!(payload["status"], json!("success"));
        assert_eq!(payload["account_id"], json!(77));
        assert_eq!(payload["environment"], json!("mainnet"));
        assert_eq!(legacy_setup_hits.load(Ordering::SeqCst), 1);
    }

    #[tokio::test]
    async fn hyperliquid_setup_route_validates_path_and_payload_without_proxying() {
        let legacy_setup_hits = Arc::new(AtomicUsize::new(0));
        let upstream = Router::new().route(
            "/api/hyperliquid/accounts/{account_id}/setup",
            post({
                let legacy_setup_hits = Arc::clone(&legacy_setup_hits);
                move || {
                    let legacy_setup_hits = Arc::clone(&legacy_setup_hits);
                    async move {
                        legacy_setup_hits.fetch_add(1, Ordering::SeqCst);
                        Json(json!({"source": "legacy"}))
                    }
                }
            }),
        );
        let upstream_addr = spawn_test_legacy_server(upstream).await;
        let router = build_router(test_config_for_legacy_http(upstream_addr));

        let invalid_id_response = router
            .clone()
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/api/hyperliquid/accounts/not-an-int/setup")
                    .header("content-type", "application/json")
                    .body(Body::from(
                        json!({
                            "environment": "testnet",
                            "privateKey": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
                        })
                        .to_string(),
                    ))
                    .expect("invalid setup path request should be valid"),
            )
            .await
            .expect("router should answer invalid setup path request");
        assert_eq!(
            invalid_id_response.status(),
            StatusCode::UNPROCESSABLE_ENTITY
        );
        let invalid_id_body = to_bytes(invalid_id_response.into_body(), usize::MAX)
            .await
            .expect("invalid setup path response should be readable");
        let invalid_id_payload: Value =
            serde_json::from_slice(&invalid_id_body).expect("invalid setup path response json");
        assert_eq!(
            invalid_id_payload["detail"],
            json!("account_id must be a valid integer")
        );

        let missing_environment_response = router
            .clone()
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/api/hyperliquid/accounts/77/setup")
                    .header("content-type", "application/json")
                    .body(Body::from(
                        json!({
                            "privateKey": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
                        })
                        .to_string(),
                    ))
                    .expect("missing environment setup request should be valid"),
            )
            .await
            .expect("router should answer missing environment setup request");
        assert_eq!(
            missing_environment_response.status(),
            StatusCode::UNPROCESSABLE_ENTITY
        );
        let missing_environment_body =
            to_bytes(missing_environment_response.into_body(), usize::MAX)
                .await
                .expect("missing environment setup response should be readable");
        let missing_environment_payload: Value = serde_json::from_slice(&missing_environment_body)
            .expect("missing environment setup response json");
        assert_eq!(
            missing_environment_payload["detail"],
            json!("environment is required")
        );

        let invalid_environment_response = router
            .clone()
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/api/hyperliquid/accounts/77/setup")
                    .header("content-type", "application/json")
                    .body(Body::from(
                        json!({
                            "environment": "sandbox",
                            "privateKey": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
                        })
                        .to_string(),
                    ))
                    .expect("invalid environment setup request should be valid"),
            )
            .await
            .expect("router should answer invalid environment setup request");
        assert_eq!(
            invalid_environment_response.status(),
            StatusCode::UNPROCESSABLE_ENTITY
        );
        let invalid_environment_body =
            to_bytes(invalid_environment_response.into_body(), usize::MAX)
                .await
                .expect("invalid environment setup response should be readable");
        let invalid_environment_payload: Value = serde_json::from_slice(&invalid_environment_body)
            .expect("invalid environment setup response json");
        assert_eq!(
            invalid_environment_payload["detail"],
            json!("environment must be 'testnet' or 'mainnet'")
        );

        assert_eq!(legacy_setup_hits.load(Ordering::SeqCst), 0);
    }

    #[tokio::test]
    async fn hyperliquid_switch_environment_route_forwards_legacy_contract_through_native_handler()
    {
        let legacy_switch_hits = Arc::new(AtomicUsize::new(0));
        let upstream = Router::new().route(
            "/api/hyperliquid/accounts/{account_id}/switch-environment",
            post({
                let legacy_switch_hits = Arc::clone(&legacy_switch_hits);
                move |axum::extract::Path(account_id): axum::extract::Path<String>,
                      Json(payload): Json<Value>| {
                    let legacy_switch_hits = Arc::clone(&legacy_switch_hits);
                    async move {
                        legacy_switch_hits.fetch_add(1, Ordering::SeqCst);
                        assert_eq!(account_id, "77");
                        assert_eq!(payload["target_environment"], json!("mainnet"));
                        assert_eq!(payload["confirm_switch"], json!(true));

                        Json(json!({
                            "success": true,
                            "account_id": 77,
                            "old_environment": "testnet",
                            "new_environment": "mainnet",
                            "message": "Successfully switched from testnet to mainnet"
                        }))
                    }
                }
            }),
        );
        let upstream_addr = spawn_test_legacy_server(upstream).await;
        let router = build_router(test_config_for_legacy_http(upstream_addr));

        let response = router
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/api/hyperliquid/accounts/77/switch-environment")
                    .header("content-type", "application/json")
                    .body(Body::from(
                        json!({
                            "targetEnvironment": "mainnet",
                            "confirm": true
                        })
                        .to_string(),
                    ))
                    .expect("switch-environment request should be valid"),
            )
            .await
            .expect("router should answer switch-environment request");

        assert_eq!(response.status(), StatusCode::OK);
        let body = to_bytes(response.into_body(), usize::MAX)
            .await
            .expect("switch-environment response body should be readable");
        let payload: Value =
            serde_json::from_slice(&body).expect("switch-environment response should be json");
        assert_eq!(payload["success"], json!(true));
        assert_eq!(payload["account_id"], json!(77));
        assert_eq!(payload["new_environment"], json!("mainnet"));
        assert_eq!(legacy_switch_hits.load(Ordering::SeqCst), 1);
    }

    #[tokio::test]
    async fn hyperliquid_switch_environment_route_validates_path_and_payload_without_proxying() {
        let legacy_switch_hits = Arc::new(AtomicUsize::new(0));
        let upstream = Router::new().route(
            "/api/hyperliquid/accounts/{account_id}/switch-environment",
            post({
                let legacy_switch_hits = Arc::clone(&legacy_switch_hits);
                move || {
                    let legacy_switch_hits = Arc::clone(&legacy_switch_hits);
                    async move {
                        legacy_switch_hits.fetch_add(1, Ordering::SeqCst);
                        Json(json!({"source": "legacy"}))
                    }
                }
            }),
        );
        let upstream_addr = spawn_test_legacy_server(upstream).await;
        let router = build_router(test_config_for_legacy_http(upstream_addr));

        let invalid_id_response = router
            .clone()
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/api/hyperliquid/accounts/not-an-int/switch-environment")
                    .header("content-type", "application/json")
                    .body(Body::from(
                        json!({
                            "target_environment": "mainnet",
                            "confirm_switch": true
                        })
                        .to_string(),
                    ))
                    .expect("invalid switch-environment path request should be valid"),
            )
            .await
            .expect("router should answer invalid switch-environment path request");
        assert_eq!(
            invalid_id_response.status(),
            StatusCode::UNPROCESSABLE_ENTITY
        );
        let invalid_id_body = to_bytes(invalid_id_response.into_body(), usize::MAX)
            .await
            .expect("invalid switch-environment path response should be readable");
        let invalid_id_payload: Value = serde_json::from_slice(&invalid_id_body)
            .expect("invalid switch-environment path response json");
        assert_eq!(
            invalid_id_payload["detail"],
            json!("account_id must be a valid integer")
        );

        let missing_target_response = router
            .clone()
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/api/hyperliquid/accounts/77/switch-environment")
                    .header("content-type", "application/json")
                    .body(Body::from(json!({"confirm_switch": true}).to_string()))
                    .expect("missing target switch-environment request should be valid"),
            )
            .await
            .expect("router should answer missing target switch-environment request");
        assert_eq!(
            missing_target_response.status(),
            StatusCode::UNPROCESSABLE_ENTITY
        );
        let missing_target_body = to_bytes(missing_target_response.into_body(), usize::MAX)
            .await
            .expect("missing target switch-environment response should be readable");
        let missing_target_payload: Value = serde_json::from_slice(&missing_target_body)
            .expect("missing target switch-environment response json");
        assert_eq!(
            missing_target_payload["detail"],
            json!("target_environment (or targetEnvironment) is required")
        );

        let invalid_target_response = router
            .clone()
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/api/hyperliquid/accounts/77/switch-environment")
                    .header("content-type", "application/json")
                    .body(Body::from(
                        json!({
                            "target_environment": "sandbox",
                            "confirm_switch": true
                        })
                        .to_string(),
                    ))
                    .expect("invalid target switch-environment request should be valid"),
            )
            .await
            .expect("router should answer invalid target switch-environment request");
        assert_eq!(
            invalid_target_response.status(),
            StatusCode::UNPROCESSABLE_ENTITY
        );
        let invalid_target_body = to_bytes(invalid_target_response.into_body(), usize::MAX)
            .await
            .expect("invalid target switch-environment response should be readable");
        let invalid_target_payload: Value = serde_json::from_slice(&invalid_target_body)
            .expect("invalid target switch-environment response json");
        assert_eq!(
            invalid_target_payload["detail"],
            json!("target_environment must be 'testnet' or 'mainnet'")
        );

        let invalid_confirm_response = router
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/api/hyperliquid/accounts/77/switch-environment")
                    .header("content-type", "application/json")
                    .body(Body::from(
                        json!({
                            "target_environment": "mainnet",
                            "confirm_switch": "yes"
                        })
                        .to_string(),
                    ))
                    .expect("invalid confirm switch-environment request should be valid"),
            )
            .await
            .expect("router should answer invalid confirm switch-environment request");
        assert_eq!(
            invalid_confirm_response.status(),
            StatusCode::UNPROCESSABLE_ENTITY
        );
        let invalid_confirm_body = to_bytes(invalid_confirm_response.into_body(), usize::MAX)
            .await
            .expect("invalid confirm switch-environment response should be readable");
        let invalid_confirm_payload: Value = serde_json::from_slice(&invalid_confirm_body)
            .expect("invalid confirm switch-environment response json");
        assert_eq!(
            invalid_confirm_payload["detail"],
            json!("confirm_switch (or confirmSwitch/confirm) must be a boolean")
        );

        assert_eq!(legacy_switch_hits.load(Ordering::SeqCst), 0);
    }

    #[tokio::test]
    async fn hyperliquid_manual_order_route_forwards_legacy_contract_through_native_handler() {
        let legacy_manual_order_hits = Arc::new(AtomicUsize::new(0));
        let upstream = Router::new().route(
            "/api/hyperliquid/accounts/{account_id}/orders/manual",
            post({
                let legacy_manual_order_hits = Arc::clone(&legacy_manual_order_hits);
                move |axum::extract::Path(account_id): axum::extract::Path<String>,
                      Json(payload): Json<Value>| {
                    let legacy_manual_order_hits = Arc::clone(&legacy_manual_order_hits);
                    async move {
                        legacy_manual_order_hits.fetch_add(1, Ordering::SeqCst);
                        assert_eq!(account_id, "77");
                        assert_eq!(payload["symbol"], json!("BTC"));
                        assert_eq!(payload["is_buy"], json!(true));
                        assert_eq!(payload["size"], json!(0.01));
                        assert_eq!(payload["price"], json!(50000.0));
                        assert_eq!(payload["time_in_force"], json!("Gtc"));
                        assert_eq!(payload["leverage"], json!(3));
                        assert_eq!(payload["reduce_only"], json!(false));
                        assert_eq!(payload["take_profit_price"], json!(55000.0));
                        assert_eq!(payload["stop_loss_price"], json!(47500.0));
                        assert_eq!(payload["environment"], json!("mainnet"));

                        Json(json!({
                            "account_id": 77,
                            "environment": "mainnet",
                            "order_result": {
                                "main_order": {
                                    "status": "resting",
                                    "orderId": "manual-order-1",
                                    "filledAmount": 0.0,
                                    "averagePrice": 0.0
                                }
                            }
                        }))
                    }
                }
            }),
        );
        let upstream_addr = spawn_test_legacy_server(upstream).await;
        let router = build_router(test_config_for_legacy_http(upstream_addr));

        let response = router
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/api/hyperliquid/accounts/77/orders/manual")
                    .header("content-type", "application/json")
                    .body(Body::from(
                        json!({
                            "symbol": "BTC",
                            "isBuy": true,
                            "size": 0.01,
                            "price": 50000.0,
                            "timeInForce": "Gtc",
                            "leverage": 3,
                            "reduceOnly": false,
                            "takeProfitPrice": 55000.0,
                            "stopLossPrice": 47500.0,
                            "environment": "mainnet"
                        })
                        .to_string(),
                    ))
                    .expect("manual-order request should be valid"),
            )
            .await
            .expect("router should answer manual-order request");

        assert_eq!(response.status(), StatusCode::OK);
        let body = to_bytes(response.into_body(), usize::MAX)
            .await
            .expect("manual-order response body should be readable");
        let payload: Value =
            serde_json::from_slice(&body).expect("manual-order response should be json");
        assert_eq!(payload["account_id"], json!(77));
        assert_eq!(payload["environment"], json!("mainnet"));
        assert_eq!(
            payload["order_result"]["main_order"]["status"],
            json!("resting")
        );
        assert_eq!(legacy_manual_order_hits.load(Ordering::SeqCst), 1);
    }

    #[tokio::test]
    async fn hyperliquid_manual_order_route_validates_path_and_payload_without_proxying() {
        let legacy_manual_order_hits = Arc::new(AtomicUsize::new(0));
        let upstream = Router::new().route(
            "/api/hyperliquid/accounts/{account_id}/orders/manual",
            post({
                let legacy_manual_order_hits = Arc::clone(&legacy_manual_order_hits);
                move || {
                    let legacy_manual_order_hits = Arc::clone(&legacy_manual_order_hits);
                    async move {
                        legacy_manual_order_hits.fetch_add(1, Ordering::SeqCst);
                        Json(json!({"source": "legacy"}))
                    }
                }
            }),
        );
        let upstream_addr = spawn_test_legacy_server(upstream).await;
        let router = build_router(test_config_for_legacy_http(upstream_addr));

        let invalid_id_response = router
            .clone()
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/api/hyperliquid/accounts/not-an-int/orders/manual")
                    .header("content-type", "application/json")
                    .body(Body::from(
                        json!({
                            "symbol": "BTC",
                            "is_buy": true,
                            "size": 0.01,
                            "price": 50000.0
                        })
                        .to_string(),
                    ))
                    .expect("invalid manual-order path request should be valid"),
            )
            .await
            .expect("router should answer invalid manual-order path request");
        assert_eq!(
            invalid_id_response.status(),
            StatusCode::UNPROCESSABLE_ENTITY
        );
        let invalid_id_body = to_bytes(invalid_id_response.into_body(), usize::MAX)
            .await
            .expect("invalid manual-order path response should be readable");
        let invalid_id_payload: Value =
            serde_json::from_slice(&invalid_id_body).expect("invalid manual-order path json");
        assert_eq!(
            invalid_id_payload["detail"],
            json!("account_id must be a valid integer")
        );

        let missing_symbol_response = router
            .clone()
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/api/hyperliquid/accounts/77/orders/manual")
                    .header("content-type", "application/json")
                    .body(Body::from(
                        json!({
                            "is_buy": true,
                            "size": 0.01,
                            "price": 50000.0
                        })
                        .to_string(),
                    ))
                    .expect("missing symbol manual-order request should be valid"),
            )
            .await
            .expect("router should answer missing symbol manual-order request");
        assert_eq!(
            missing_symbol_response.status(),
            StatusCode::UNPROCESSABLE_ENTITY
        );
        let missing_symbol_body = to_bytes(missing_symbol_response.into_body(), usize::MAX)
            .await
            .expect("missing symbol manual-order response should be readable");
        let missing_symbol_payload: Value =
            serde_json::from_slice(&missing_symbol_body).expect("missing symbol manual-order json");
        assert_eq!(
            missing_symbol_payload["detail"],
            json!("symbol is required")
        );

        let invalid_time_in_force_response = router
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/api/hyperliquid/accounts/77/orders/manual")
                    .header("content-type", "application/json")
                    .body(Body::from(
                        json!({
                            "symbol": "BTC",
                            "is_buy": true,
                            "size": 0.01,
                            "price": 50000.0,
                            "time_in_force": "IOC"
                        })
                        .to_string(),
                    ))
                    .expect("invalid time-in-force manual-order request should be valid"),
            )
            .await
            .expect("router should answer invalid time-in-force manual-order request");
        assert_eq!(
            invalid_time_in_force_response.status(),
            StatusCode::UNPROCESSABLE_ENTITY
        );
        let invalid_time_in_force_body =
            to_bytes(invalid_time_in_force_response.into_body(), usize::MAX)
                .await
                .expect("invalid time-in-force manual-order response should be readable");
        let invalid_time_in_force_payload: Value =
            serde_json::from_slice(&invalid_time_in_force_body)
                .expect("invalid time-in-force manual-order response json");
        assert_eq!(
            invalid_time_in_force_payload["detail"],
            json!("time_in_force must be one of 'Ioc', 'Gtc', or 'Alo'")
        );

        assert_eq!(legacy_manual_order_hits.load(Ordering::SeqCst), 0);
    }

    #[tokio::test]
    async fn orders_create_route_forwards_legacy_contract_through_native_handler() {
        let legacy_order_create_hits = Arc::new(AtomicUsize::new(0));
        let upstream = Router::new().route(
            "/api/orders/create",
            post({
                let legacy_order_create_hits = Arc::clone(&legacy_order_create_hits);
                move |Json(payload): Json<Value>| {
                    let legacy_order_create_hits = Arc::clone(&legacy_order_create_hits);
                    async move {
                        legacy_order_create_hits.fetch_add(1, Ordering::SeqCst);
                        assert_eq!(payload["user_id"], json!(42));
                        assert_eq!(payload["symbol"], json!("BTC"));
                        assert_eq!(payload["name"], json!("Momentum entry"));
                        assert_eq!(payload["side"], json!("BUY"));
                        assert_eq!(payload["order_type"], json!("LIMIT"));
                        assert_eq!(payload["price"], json!(64000.5));
                        assert_eq!(payload["quantity"], json!(0.25));
                        assert_eq!(payload["session_token"], json!("session-token-123"));
                        assert!(payload.get("userId").is_none());
                        assert!(payload.get("orderType").is_none());
                        assert!(payload.get("sessionToken").is_none());

                        Json(json!({
                            "id": 901,
                            "order_no": "ORD-901",
                            "user_id": 42,
                            "symbol": "BTC",
                            "name": "Momentum entry",
                            "market": "CRYPTO",
                            "side": "BUY",
                            "order_type": "LIMIT",
                            "price": 64000.5,
                            "quantity": 0.25,
                            "filled_quantity": 0,
                            "status": "PENDING"
                        }))
                    }
                }
            }),
        );
        let upstream_addr = spawn_test_legacy_server(upstream).await;
        let router = build_router(test_config_for_legacy_http(upstream_addr));

        let response = router
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/api/orders/create")
                    .header("content-type", "application/json")
                    .body(Body::from(
                        json!({
                            "userId": 42,
                            "symbol": "BTC",
                            "name": "Momentum entry",
                            "side": "BUY",
                            "orderType": "LIMIT",
                            "price": 64000.5,
                            "quantity": 0.25,
                            "sessionToken": "session-token-123"
                        })
                        .to_string(),
                    ))
                    .expect("order-create request should be valid"),
            )
            .await
            .expect("router should answer order-create request");

        assert_eq!(response.status(), StatusCode::OK);
        let body = to_bytes(response.into_body(), usize::MAX)
            .await
            .expect("order-create response body should be readable");
        let payload: Value =
            serde_json::from_slice(&body).expect("order-create response should be json");
        assert_eq!(payload["id"], json!(901));
        assert_eq!(payload["order_no"], json!("ORD-901"));
        assert_eq!(payload["status"], json!("PENDING"));
        assert_eq!(legacy_order_create_hits.load(Ordering::SeqCst), 1);
    }

    #[tokio::test]
    async fn orders_create_route_validates_payload_without_proxying() {
        let legacy_order_create_hits = Arc::new(AtomicUsize::new(0));
        let upstream = Router::new().route(
            "/api/orders/create",
            post({
                let legacy_order_create_hits = Arc::clone(&legacy_order_create_hits);
                move || {
                    let legacy_order_create_hits = Arc::clone(&legacy_order_create_hits);
                    async move {
                        legacy_order_create_hits.fetch_add(1, Ordering::SeqCst);
                        Json(json!({"source": "legacy"}))
                    }
                }
            }),
        );
        let upstream_addr = spawn_test_legacy_server(upstream).await;
        let router = build_router(test_config_for_legacy_http(upstream_addr));

        let invalid_payload_response = router
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/api/orders/create")
                    .header("content-type", "application/json")
                    .body(Body::from(
                        json!({
                            "symbol": "BTC",
                            "name": "Momentum entry",
                            "side": "BUY",
                            "order_type": "LIMIT",
                            "quantity": 0.25
                        })
                        .to_string(),
                    ))
                    .expect("invalid order-create request should be valid"),
            )
            .await
            .expect("router should answer invalid order-create request");

        assert_eq!(
            invalid_payload_response.status(),
            StatusCode::UNPROCESSABLE_ENTITY
        );
        let body = to_bytes(invalid_payload_response.into_body(), usize::MAX)
            .await
            .expect("invalid order-create response body should be readable");
        let payload: Value =
            serde_json::from_slice(&body).expect("invalid order-create response should be json");
        assert_eq!(payload["detail"], json!("user_id (or userId) is required"));
        assert_eq!(legacy_order_create_hits.load(Ordering::SeqCst), 0);
    }

    #[tokio::test]
    async fn orders_pending_route_forwards_legacy_contract_through_native_handler() {
        let legacy_pending_orders_hits = Arc::new(AtomicUsize::new(0));
        let upstream = Router::new().route(
            "/api/orders/pending",
            get({
                let legacy_pending_orders_hits = Arc::clone(&legacy_pending_orders_hits);
                move |axum::extract::Query(query): axum::extract::Query<
                    std::collections::HashMap<String, String>,
                >| {
                    let legacy_pending_orders_hits = Arc::clone(&legacy_pending_orders_hits);
                    async move {
                        legacy_pending_orders_hits.fetch_add(1, Ordering::SeqCst);
                        assert_eq!(query.get("user_id").map(String::as_str), Some("42"));

                        Json(json!([
                            {
                                "id": 1001,
                                "order_no": "ORD-1001",
                                "user_id": 42,
                                "status": "PENDING"
                            }
                        ]))
                    }
                }
            }),
        );
        let upstream_addr = spawn_test_legacy_server(upstream).await;
        let router = build_router(test_config_for_legacy_http(upstream_addr));

        let response = router
            .oneshot(
                Request::builder()
                    .method("GET")
                    .uri("/api/orders/pending?user_id=42")
                    .body(Body::empty())
                    .expect("pending-orders request should be valid"),
            )
            .await
            .expect("router should answer pending-orders request");

        assert_eq!(response.status(), StatusCode::OK);
        let body = to_bytes(response.into_body(), usize::MAX)
            .await
            .expect("pending-orders response body should be readable");
        let payload: Value =
            serde_json::from_slice(&body).expect("pending-orders response should be json");
        assert_eq!(payload[0]["id"], json!(1001));
        assert_eq!(payload[0]["user_id"], json!(42));
        assert_eq!(payload[0]["status"], json!("PENDING"));
        assert_eq!(legacy_pending_orders_hits.load(Ordering::SeqCst), 1);
    }

    #[tokio::test]
    async fn orders_pending_route_validates_query_without_proxying() {
        let legacy_pending_orders_hits = Arc::new(AtomicUsize::new(0));
        let upstream = Router::new().route(
            "/api/orders/pending",
            get({
                let legacy_pending_orders_hits = Arc::clone(&legacy_pending_orders_hits);
                move || {
                    let legacy_pending_orders_hits = Arc::clone(&legacy_pending_orders_hits);
                    async move {
                        legacy_pending_orders_hits.fetch_add(1, Ordering::SeqCst);
                        Json(json!([{"source": "legacy"}]))
                    }
                }
            }),
        );
        let upstream_addr = spawn_test_legacy_server(upstream).await;
        let router = build_router(test_config_for_legacy_http(upstream_addr));

        let invalid_user_id_response = router
            .oneshot(
                Request::builder()
                    .method("GET")
                    .uri("/api/orders/pending?user_id=not-an-int")
                    .body(Body::empty())
                    .expect("invalid pending-orders request should be valid"),
            )
            .await
            .expect("router should answer invalid pending-orders request");

        assert_eq!(
            invalid_user_id_response.status(),
            StatusCode::UNPROCESSABLE_ENTITY
        );
        let body = to_bytes(invalid_user_id_response.into_body(), usize::MAX)
            .await
            .expect("invalid pending-orders response body should be readable");
        let payload: Value =
            serde_json::from_slice(&body).expect("invalid pending-orders response should be json");
        assert_eq!(
            payload["detail"],
            json!("user_id query parameter must be a valid integer")
        );
        assert_eq!(legacy_pending_orders_hits.load(Ordering::SeqCst), 0);
    }

    #[tokio::test]
    async fn orders_user_route_forwards_legacy_contract_through_native_handler() {
        let legacy_user_orders_hits = Arc::new(AtomicUsize::new(0));
        let upstream = Router::new().route(
            "/api/orders/user/{user_id}",
            get({
                let legacy_user_orders_hits = Arc::clone(&legacy_user_orders_hits);
                move |axum::extract::Path(user_id): axum::extract::Path<String>,
                      axum::extract::Query(query): axum::extract::Query<
                    std::collections::HashMap<String, String>,
                >| {
                    let legacy_user_orders_hits = Arc::clone(&legacy_user_orders_hits);
                    async move {
                        legacy_user_orders_hits.fetch_add(1, Ordering::SeqCst);
                        assert_eq!(user_id, "42");
                        assert_eq!(query.get("status").map(String::as_str), Some("PENDING"));

                        Json(json!([
                            {
                                "id": 2001,
                                "order_no": "ORD-2001",
                                "user_id": 42,
                                "status": "PENDING"
                            }
                        ]))
                    }
                }
            }),
        );
        let upstream_addr = spawn_test_legacy_server(upstream).await;
        let router = build_router(test_config_for_legacy_http(upstream_addr));

        let response = router
            .oneshot(
                Request::builder()
                    .method("GET")
                    .uri("/api/orders/user/42?status=PENDING")
                    .body(Body::empty())
                    .expect("user-orders request should be valid"),
            )
            .await
            .expect("router should answer user-orders request");

        assert_eq!(response.status(), StatusCode::OK);
        let body = to_bytes(response.into_body(), usize::MAX)
            .await
            .expect("user-orders response body should be readable");
        let payload: Value =
            serde_json::from_slice(&body).expect("user-orders response should be json");
        assert_eq!(payload[0]["id"], json!(2001));
        assert_eq!(payload[0]["user_id"], json!(42));
        assert_eq!(payload[0]["status"], json!("PENDING"));
        assert_eq!(legacy_user_orders_hits.load(Ordering::SeqCst), 1);
    }

    #[tokio::test]
    async fn orders_user_route_validates_path_without_proxying() {
        let legacy_user_orders_hits = Arc::new(AtomicUsize::new(0));
        let upstream = Router::new().route(
            "/api/orders/user/{user_id}",
            get({
                let legacy_user_orders_hits = Arc::clone(&legacy_user_orders_hits);
                move || {
                    let legacy_user_orders_hits = Arc::clone(&legacy_user_orders_hits);
                    async move {
                        legacy_user_orders_hits.fetch_add(1, Ordering::SeqCst);
                        Json(json!([{"source": "legacy"}]))
                    }
                }
            }),
        );
        let upstream_addr = spawn_test_legacy_server(upstream).await;
        let router = build_router(test_config_for_legacy_http(upstream_addr));

        let invalid_user_id_response = router
            .oneshot(
                Request::builder()
                    .method("GET")
                    .uri("/api/orders/user/not-an-int")
                    .body(Body::empty())
                    .expect("invalid user-orders request should be valid"),
            )
            .await
            .expect("router should answer invalid user-orders request");

        assert_eq!(
            invalid_user_id_response.status(),
            StatusCode::UNPROCESSABLE_ENTITY
        );
        let body = to_bytes(invalid_user_id_response.into_body(), usize::MAX)
            .await
            .expect("invalid user-orders response body should be readable");
        let payload: Value =
            serde_json::from_slice(&body).expect("invalid user-orders response should be json");
        assert_eq!(
            payload["detail"],
            json!("user_id path parameter must be a valid integer")
        );
        assert_eq!(legacy_user_orders_hits.load(Ordering::SeqCst), 0);
    }

    #[tokio::test]
    async fn orders_order_detail_route_forwards_legacy_contract_through_native_handler() {
        let legacy_order_detail_hits = Arc::new(AtomicUsize::new(0));
        let upstream = Router::new().route(
            "/api/orders/order/{order_id}",
            get({
                let legacy_order_detail_hits = Arc::clone(&legacy_order_detail_hits);
                move |axum::extract::Path(order_id): axum::extract::Path<String>| {
                    let legacy_order_detail_hits = Arc::clone(&legacy_order_detail_hits);
                    async move {
                        legacy_order_detail_hits.fetch_add(1, Ordering::SeqCst);
                        assert_eq!(order_id, "3003");

                        Json(json!({
                            "id": 3003,
                            "order_no": "ORD-3003",
                            "user_id": 42,
                            "symbol": "ETH",
                            "status": "PENDING"
                        }))
                    }
                }
            }),
        );
        let upstream_addr = spawn_test_legacy_server(upstream).await;
        let router = build_router(test_config_for_legacy_http(upstream_addr));

        let response = router
            .oneshot(
                Request::builder()
                    .method("GET")
                    .uri("/api/orders/order/3003")
                    .body(Body::empty())
                    .expect("order-detail request should be valid"),
            )
            .await
            .expect("router should answer order-detail request");

        assert_eq!(response.status(), StatusCode::OK);
        let body = to_bytes(response.into_body(), usize::MAX)
            .await
            .expect("order-detail response body should be readable");
        let payload: Value =
            serde_json::from_slice(&body).expect("order-detail response should be json");
        assert_eq!(payload["id"], json!(3003));
        assert_eq!(payload["order_no"], json!("ORD-3003"));
        assert_eq!(payload["status"], json!("PENDING"));
        assert_eq!(legacy_order_detail_hits.load(Ordering::SeqCst), 1);
    }

    #[tokio::test]
    async fn orders_order_detail_route_validates_path_without_proxying() {
        let legacy_order_detail_hits = Arc::new(AtomicUsize::new(0));
        let upstream = Router::new().route(
            "/api/orders/order/{order_id}",
            get({
                let legacy_order_detail_hits = Arc::clone(&legacy_order_detail_hits);
                move || {
                    let legacy_order_detail_hits = Arc::clone(&legacy_order_detail_hits);
                    async move {
                        legacy_order_detail_hits.fetch_add(1, Ordering::SeqCst);
                        Json(json!({"source": "legacy"}))
                    }
                }
            }),
        );
        let upstream_addr = spawn_test_legacy_server(upstream).await;
        let router = build_router(test_config_for_legacy_http(upstream_addr));

        let invalid_order_id_response = router
            .oneshot(
                Request::builder()
                    .method("GET")
                    .uri("/api/orders/order/not-an-int")
                    .body(Body::empty())
                    .expect("invalid order-detail request should be valid"),
            )
            .await
            .expect("router should answer invalid order-detail request");

        assert_eq!(
            invalid_order_id_response.status(),
            StatusCode::UNPROCESSABLE_ENTITY
        );
        let body = to_bytes(invalid_order_id_response.into_body(), usize::MAX)
            .await
            .expect("invalid order-detail response body should be readable");
        let payload: Value =
            serde_json::from_slice(&body).expect("invalid order-detail response should be json");
        assert_eq!(
            payload["detail"],
            json!("order_id path parameter must be a valid integer")
        );
        assert_eq!(legacy_order_detail_hits.load(Ordering::SeqCst), 0);
    }

    #[tokio::test]
    async fn orders_health_route_forwards_legacy_contract_through_native_handler() {
        let legacy_orders_health_hits = Arc::new(AtomicUsize::new(0));
        let upstream = Router::new().route(
            "/api/orders/health",
            get({
                let legacy_orders_health_hits = Arc::clone(&legacy_orders_health_hits);
                move || {
                    let legacy_orders_health_hits = Arc::clone(&legacy_orders_health_hits);
                    async move {
                        legacy_orders_health_hits.fetch_add(1, Ordering::SeqCst);
                        Json(json!({
                            "status": "healthy",
                            "timestamp": 1_776_312_000_000_i64,
                            "statistics": {
                                "total_orders": 12,
                                "pending_orders": 3,
                                "filled_orders": 8,
                                "cancelled_orders": 1
                            },
                            "message": "Order service is running normally"
                        }))
                    }
                }
            }),
        );
        let upstream_addr = spawn_test_legacy_server(upstream).await;
        let router = build_router(test_config_for_legacy_http(upstream_addr));

        let response = router
            .oneshot(
                Request::builder()
                    .method("GET")
                    .uri("/api/orders/health")
                    .body(Body::empty())
                    .expect("orders-health request should be valid"),
            )
            .await
            .expect("router should answer orders-health request");

        assert_eq!(response.status(), StatusCode::OK);
        let body = to_bytes(response.into_body(), usize::MAX)
            .await
            .expect("orders-health response body should be readable");
        let payload: Value =
            serde_json::from_slice(&body).expect("orders-health response should be json");
        assert_eq!(payload["status"], json!("healthy"));
        assert_eq!(payload["statistics"]["total_orders"], json!(12));
        assert_eq!(payload["statistics"]["pending_orders"], json!(3));
        assert_eq!(
            payload["message"],
            json!("Order service is running normally")
        );
        assert_eq!(legacy_orders_health_hits.load(Ordering::SeqCst), 1);
    }

    #[tokio::test]
    async fn orders_health_route_rejects_post_without_proxying() {
        let legacy_orders_health_hits = Arc::new(AtomicUsize::new(0));
        let upstream = Router::new().route(
            "/api/orders/health",
            get({
                let legacy_orders_health_hits = Arc::clone(&legacy_orders_health_hits);
                move || {
                    let legacy_orders_health_hits = Arc::clone(&legacy_orders_health_hits);
                    async move {
                        legacy_orders_health_hits.fetch_add(1, Ordering::SeqCst);
                        Json(json!({"source": "legacy"}))
                    }
                }
            }),
        );
        let upstream_addr = spawn_test_legacy_server(upstream).await;
        let router = build_router(test_config_for_legacy_http(upstream_addr));

        let response = router
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/api/orders/health")
                    .body(Body::empty())
                    .expect("POST orders-health request should be valid"),
            )
            .await
            .expect("router should answer POST orders-health request");

        assert_eq!(response.status(), StatusCode::METHOD_NOT_ALLOWED);
        assert_eq!(legacy_orders_health_hits.load(Ordering::SeqCst), 0);
    }

    #[tokio::test]
    async fn market_price_route_marks_legacy_fallback_with_source_header() {
        let legacy_market_price_hits = Arc::new(AtomicUsize::new(0));
        let upstream = Router::new().route(
            "/api/market/price/{symbol}",
            get({
                let legacy_market_price_hits = Arc::clone(&legacy_market_price_hits);
                move |axum::extract::Path(symbol): axum::extract::Path<String>,
                      axum::extract::Query(query): axum::extract::Query<
                    std::collections::HashMap<String, String>,
                >| {
                    let legacy_market_price_hits = Arc::clone(&legacy_market_price_hits);
                    async move {
                        legacy_market_price_hits.fetch_add(1, Ordering::SeqCst);
                        assert_eq!(symbol, "BTC");
                        assert_eq!(query.get("market").map(String::as_str), Some("US"));

                        Json(json!({
                            "symbol": "BTC.US",
                            "market": "US",
                            "price": 100.25,
                            "oracle_price": 100.25,
                            "change24h": 0.5,
                            "volume24h": 1000.0,
                            "percentage24h": 0.2,
                            "open_interest": 0.0,
                            "funding_rate": 0.0,
                            "timestamp": 1_776_312_400_000_i64
                        }))
                    }
                }
            }),
        );
        let upstream_addr = spawn_test_legacy_server(upstream).await;
        let router = build_router(test_config_for_legacy_http(upstream_addr));

        let response = router
            .oneshot(
                Request::builder()
                    .method("GET")
                    .uri("/api/market/price/BTC?market=US")
                    .body(Body::empty())
                    .expect("market-price request should be valid"),
            )
            .await
            .expect("router should answer market-price request");

        assert_eq!(response.status(), StatusCode::OK);
        assert_eq!(
            response
                .headers()
                .get("x-rust-market-price-source")
                .and_then(|value| value.to_str().ok()),
            Some("legacy-fallback")
        );
        let body = to_bytes(response.into_body(), usize::MAX)
            .await
            .expect("market-price response body should be readable");
        let payload: Value =
            serde_json::from_slice(&body).expect("market-price response should be json");
        assert_eq!(payload["symbol"], json!("BTC.US"));
        assert_eq!(payload["market"], json!("US"));
        assert_eq!(payload["price"], json!(100.25));
        assert_eq!(legacy_market_price_hits.load(Ordering::SeqCst), 1);
    }

    #[tokio::test]
    async fn market_price_route_rejects_post_without_proxying() {
        let legacy_market_price_hits = Arc::new(AtomicUsize::new(0));
        let upstream = Router::new().route(
            "/api/market/price/{symbol}",
            get({
                let legacy_market_price_hits = Arc::clone(&legacy_market_price_hits);
                move || {
                    let legacy_market_price_hits = Arc::clone(&legacy_market_price_hits);
                    async move {
                        legacy_market_price_hits.fetch_add(1, Ordering::SeqCst);
                        Json(json!({"source": "legacy"}))
                    }
                }
            }),
        );
        let upstream_addr = spawn_test_legacy_server(upstream).await;
        let router = build_router(test_config_for_legacy_http(upstream_addr));

        let response = router
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/api/market/price/BTC?market=US")
                    .body(Body::empty())
                    .expect("POST market-price request should be valid"),
            )
            .await
            .expect("router should answer POST market-price request");

        assert_eq!(response.status(), StatusCode::METHOD_NOT_ALLOWED);
        assert_eq!(legacy_market_price_hits.load(Ordering::SeqCst), 0);
    }

    #[tokio::test]
    async fn market_prices_route_marks_legacy_fallback_with_batch_source_headers() {
        let legacy_market_price_hits = Arc::new(AtomicUsize::new(0));
        let upstream = Router::new().route(
            "/api/market/price/{symbol}",
            get({
                let legacy_market_price_hits = Arc::clone(&legacy_market_price_hits);
                move |axum::extract::Path(symbol): axum::extract::Path<String>,
                      axum::extract::Query(query): axum::extract::Query<
                    std::collections::HashMap<String, String>,
                >| {
                    let legacy_market_price_hits = Arc::clone(&legacy_market_price_hits);
                    async move {
                        legacy_market_price_hits.fetch_add(1, Ordering::SeqCst);
                        assert_eq!(query.get("market").map(String::as_str), Some("US"));

                        Json(json!({
                            "symbol": format!("{symbol}.US"),
                            "market": "US",
                            "price": if symbol == "BTC" { 100.25 } else { 200.5 },
                            "oracle_price": if symbol == "BTC" { 100.25 } else { 200.5 },
                            "change24h": 0.5,
                            "volume24h": 1000.0,
                            "percentage24h": 0.2,
                            "open_interest": 0.0,
                            "funding_rate": 0.0,
                            "timestamp": 1_776_312_400_000_i64
                        }))
                    }
                }
            }),
        );
        let upstream_addr = spawn_test_legacy_server(upstream).await;
        let router = build_router(test_config_for_legacy_http(upstream_addr));

        let response = router
            .oneshot(
                Request::builder()
                    .method("GET")
                    .uri("/api/market/prices?symbols=BTC,ETH&market=US")
                    .body(Body::empty())
                    .expect("market-prices request should be valid"),
            )
            .await
            .expect("router should answer market-prices request");

        assert_eq!(response.status(), StatusCode::OK);
        assert_eq!(
            response
                .headers()
                .get("x-rust-market-prices-source")
                .and_then(|value| value.to_str().ok()),
            Some("legacy-fallback")
        );
        assert_eq!(
            response
                .headers()
                .get("x-rust-market-prices-legacy-fallback-count")
                .and_then(|value| value.to_str().ok()),
            Some("2")
        );

        let body = to_bytes(response.into_body(), usize::MAX)
            .await
            .expect("market-prices response body should be readable");
        let payload: Value =
            serde_json::from_slice(&body).expect("market-prices response should be json");
        assert_eq!(
            payload,
            json!([
                {
                    "symbol": "BTC.US",
                    "market": "US",
                    "price": 100.25,
                    "oracle_price": 100.25,
                    "change24h": 0.5,
                    "volume24h": 1000.0,
                    "percentage24h": 0.2,
                    "open_interest": 0.0,
                    "funding_rate": 0.0,
                    "timestamp": 1_776_312_400_000_i64
                },
                {
                    "symbol": "ETH.US",
                    "market": "US",
                    "price": 200.5,
                    "oracle_price": 200.5,
                    "change24h": 0.5,
                    "volume24h": 1000.0,
                    "percentage24h": 0.2,
                    "open_interest": 0.0,
                    "funding_rate": 0.0,
                    "timestamp": 1_776_312_400_000_i64
                }
            ])
        );
        assert_eq!(legacy_market_price_hits.load(Ordering::SeqCst), 2);
    }

    #[tokio::test]
    async fn market_prices_route_rejects_more_than_twenty_symbols_without_proxying() {
        let legacy_market_price_hits = Arc::new(AtomicUsize::new(0));
        let upstream = Router::new().route(
            "/api/market/price/{symbol}",
            get({
                let legacy_market_price_hits = Arc::clone(&legacy_market_price_hits);
                move || {
                    let legacy_market_price_hits = Arc::clone(&legacy_market_price_hits);
                    async move {
                        legacy_market_price_hits.fetch_add(1, Ordering::SeqCst);
                        Json(json!({"source": "legacy"}))
                    }
                }
            }),
        );
        let upstream_addr = spawn_test_legacy_server(upstream).await;
        let router = build_router(test_config_for_legacy_http(upstream_addr));

        let symbols = (1..=21)
            .map(|idx| format!("S{idx:02}"))
            .collect::<Vec<_>>()
            .join(",");
        let response = router
            .oneshot(
                Request::builder()
                    .method("GET")
                    .uri(format!("/api/market/prices?symbols={symbols}&market=US"))
                    .body(Body::empty())
                    .expect("invalid market-prices request should be valid"),
            )
            .await
            .expect("router should answer invalid market-prices request");

        assert_eq!(response.status(), StatusCode::BAD_REQUEST);
        let body = to_bytes(response.into_body(), usize::MAX)
            .await
            .expect("invalid market-prices response body should be readable");
        let payload: Value =
            serde_json::from_slice(&body).expect("invalid market-prices response should be json");
        assert_eq!(
            payload["detail"],
            json!("Maximum 20 crypto symbols supported")
        );
        assert_eq!(legacy_market_price_hits.load(Ordering::SeqCst), 0);
    }

    #[tokio::test]
    async fn market_prices_route_rejects_post_without_proxying() {
        let legacy_market_price_hits = Arc::new(AtomicUsize::new(0));
        let upstream = Router::new().route(
            "/api/market/price/{symbol}",
            get({
                let legacy_market_price_hits = Arc::clone(&legacy_market_price_hits);
                move || {
                    let legacy_market_price_hits = Arc::clone(&legacy_market_price_hits);
                    async move {
                        legacy_market_price_hits.fetch_add(1, Ordering::SeqCst);
                        Json(json!({"source": "legacy"}))
                    }
                }
            }),
        );
        let upstream_addr = spawn_test_legacy_server(upstream).await;
        let router = build_router(test_config_for_legacy_http(upstream_addr));

        let response = router
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/api/market/prices?symbols=BTC,ETH&market=US")
                    .body(Body::empty())
                    .expect("POST market-prices request should be valid"),
            )
            .await
            .expect("router should answer POST market-prices request");

        assert_eq!(response.status(), StatusCode::METHOD_NOT_ALLOWED);
        assert_eq!(legacy_market_price_hits.load(Ordering::SeqCst), 0);
    }

    #[tokio::test]
    async fn market_status_route_marks_legacy_fallback_with_source_header() {
        let legacy_market_status_hits = Arc::new(AtomicUsize::new(0));
        let upstream = Router::new().route(
            "/api/market/status/{symbol}",
            get({
                let legacy_market_status_hits = Arc::clone(&legacy_market_status_hits);
                move |axum::extract::Path(symbol): axum::extract::Path<String>,
                      axum::extract::Query(query): axum::extract::Query<
                    std::collections::HashMap<String, String>,
                >| {
                    let legacy_market_status_hits = Arc::clone(&legacy_market_status_hits);
                    async move {
                        legacy_market_status_hits.fetch_add(1, Ordering::SeqCst);
                        assert_eq!(symbol, "BTC");
                        assert_eq!(query.get("market").map(String::as_str), Some("US"));
                        Json(json!({
                            "symbol": "BTC",
                            "market": "US",
                            "market_status": "CLOSED",
                            "timestamp": 1_776_312_400_000_i64,
                            "current_time": "2026-04-16T00:00:00Z"
                        }))
                    }
                }
            }),
        );
        let upstream_addr = spawn_test_legacy_server(upstream).await;
        let router = build_router(test_config_for_legacy_http(upstream_addr));

        let response = router
            .oneshot(
                Request::builder()
                    .method("GET")
                    .uri("/api/market/status/BTC?market=US")
                    .body(Body::empty())
                    .expect("market-status request should be valid"),
            )
            .await
            .expect("router should answer market-status request");

        assert_eq!(response.status(), StatusCode::OK);
        assert_eq!(
            response
                .headers()
                .get("x-rust-market-status-source")
                .and_then(|value| value.to_str().ok()),
            Some("legacy-fallback")
        );
        let body = to_bytes(response.into_body(), usize::MAX)
            .await
            .expect("market-status response body should be readable");
        let payload: Value =
            serde_json::from_slice(&body).expect("market-status response should be json");
        assert_eq!(payload["symbol"], json!("BTC"));
        assert_eq!(payload["market"], json!("US"));
        assert_eq!(payload["market_status"], json!("CLOSED"));
        assert_eq!(payload["current_time"], json!("2026-04-16T00:00:00Z"));
        assert_eq!(legacy_market_status_hits.load(Ordering::SeqCst), 1);
    }

    #[tokio::test]
    async fn market_status_route_uses_native_status_without_legacy_fallback() {
        let legacy_market_status_hits = Arc::new(AtomicUsize::new(0));
        let upstream = Router::new().route(
            "/api/market/status/{symbol}",
            get({
                let legacy_market_status_hits = Arc::clone(&legacy_market_status_hits);
                move || {
                    let legacy_market_status_hits = Arc::clone(&legacy_market_status_hits);
                    async move {
                        legacy_market_status_hits.fetch_add(1, Ordering::SeqCst);
                        Json(json!({"source": "legacy"}))
                    }
                }
            }),
        );
        let upstream_addr = spawn_test_legacy_server(upstream).await;
        let router = build_router(test_config_for_legacy_http(upstream_addr));

        let response = router
            .oneshot(
                Request::builder()
                    .method("GET")
                    .uri("/api/market/status/BTC?market=hyperliquid")
                    .body(Body::empty())
                    .expect("native market-status request should be valid"),
            )
            .await
            .expect("router should answer native market-status request");

        assert_eq!(response.status(), StatusCode::OK);
        assert_eq!(
            response
                .headers()
                .get("x-rust-market-status-source")
                .and_then(|value| value.to_str().ok()),
            Some("native-synthetic")
        );
        let body = to_bytes(response.into_body(), usize::MAX)
            .await
            .expect("native market-status response body should be readable");
        let payload: Value =
            serde_json::from_slice(&body).expect("native market-status response should be json");
        assert_eq!(payload["symbol"], json!("BTC"));
        assert_eq!(payload["market"], json!("hyperliquid"));
        assert_eq!(payload["market_status"], json!("TRADING"));
        assert!(
            payload["timestamp"]
                .as_i64()
                .is_some_and(|timestamp| timestamp > 0),
            "timestamp should be generated"
        );
        assert!(
            payload["current_time"]
                .as_str()
                .is_some_and(|current_time| !current_time.is_empty()),
            "current_time should be generated"
        );
        assert_eq!(legacy_market_status_hits.load(Ordering::SeqCst), 0);
    }

    #[tokio::test]
    async fn market_status_route_rejects_post_without_proxying() {
        let legacy_market_status_hits = Arc::new(AtomicUsize::new(0));
        let upstream = Router::new().route(
            "/api/market/status/{symbol}",
            get({
                let legacy_market_status_hits = Arc::clone(&legacy_market_status_hits);
                move || {
                    let legacy_market_status_hits = Arc::clone(&legacy_market_status_hits);
                    async move {
                        legacy_market_status_hits.fetch_add(1, Ordering::SeqCst);
                        Json(json!({"source": "legacy"}))
                    }
                }
            }),
        );
        let upstream_addr = spawn_test_legacy_server(upstream).await;
        let router = build_router(test_config_for_legacy_http(upstream_addr));

        let response = router
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/api/market/status/BTC?market=US")
                    .body(Body::empty())
                    .expect("POST market-status request should be valid"),
            )
            .await
            .expect("router should answer POST market-status request");

        assert_eq!(response.status(), StatusCode::METHOD_NOT_ALLOWED);
        assert_eq!(legacy_market_status_hits.load(Ordering::SeqCst), 0);
    }

    #[tokio::test]
    async fn market_health_route_marks_source_header() {
        let legacy_market_price_hits = Arc::new(AtomicUsize::new(0));
        let upstream = Router::new().route(
            "/api/market/price/{symbol}",
            get({
                let legacy_market_price_hits = Arc::clone(&legacy_market_price_hits);
                move |axum::extract::Path(symbol): axum::extract::Path<String>,
                      axum::extract::Query(query): axum::extract::Query<
                    std::collections::HashMap<String, String>,
                >| {
                    let legacy_market_price_hits = Arc::clone(&legacy_market_price_hits);
                    async move {
                        legacy_market_price_hits.fetch_add(1, Ordering::SeqCst);
                        assert_eq!(symbol, "BTC");
                        assert_eq!(query.get("market").map(String::as_str), Some("hyperliquid"));

                        Json(json!({
                            "symbol": "BTC",
                            "market": "hyperliquid",
                            "price": 100.25,
                            "oracle_price": 100.25,
                            "change24h": 0.5,
                            "volume24h": 1000.0,
                            "percentage24h": 0.2,
                            "open_interest": 0.0,
                            "funding_rate": 0.0,
                            "timestamp": 1_776_312_400_000_i64
                        }))
                    }
                }
            }),
        );
        let upstream_addr = spawn_test_legacy_server(upstream).await;
        let router = build_router(test_config_for_legacy_http(upstream_addr));

        let response = router
            .oneshot(
                Request::builder()
                    .method("GET")
                    .uri("/api/market/health")
                    .body(Body::empty())
                    .expect("market-health request should be valid"),
            )
            .await
            .expect("router should answer market-health request");

        assert_eq!(response.status(), StatusCode::OK);
        let source_header = response
            .headers()
            .get("x-rust-market-health-source")
            .and_then(|value| value.to_str().ok())
            .map(str::to_owned);
        let body = to_bytes(response.into_body(), usize::MAX)
            .await
            .expect("market-health response body should be readable");
        let payload: Value =
            serde_json::from_slice(&body).expect("market-health response should be json");
        let legacy_hits = legacy_market_price_hits.load(Ordering::SeqCst);
        let expected_source = if legacy_hits == 0 {
            "native-db"
        } else {
            "legacy-fallback"
        };
        assert_eq!(source_header.as_deref(), Some(expected_source));
        assert_eq!(payload["status"], json!("healthy"));
        assert_eq!(payload["test_price"]["symbol"], json!("BTC"));
        assert!(
            payload["test_price"]["price"].as_f64().is_some(),
            "health test_price.price should be numeric"
        );
        assert_eq!(
            payload["message"],
            json!("Market data service is running normally")
        );
        assert!(
            payload["timestamp"]
                .as_i64()
                .is_some_and(|timestamp| timestamp > 0),
            "timestamp should be generated"
        );
        assert!(
            payload.get("error").is_none(),
            "healthy payload should not include error"
        );
        assert!(
            legacy_hits <= 1,
            "health probe should call legacy price at most once"
        );
    }

    #[tokio::test]
    async fn market_health_route_rejects_post_without_proxying() {
        let legacy_market_price_hits = Arc::new(AtomicUsize::new(0));
        let upstream = Router::new().route(
            "/api/market/price/{symbol}",
            get({
                let legacy_market_price_hits = Arc::clone(&legacy_market_price_hits);
                move || {
                    let legacy_market_price_hits = Arc::clone(&legacy_market_price_hits);
                    async move {
                        legacy_market_price_hits.fetch_add(1, Ordering::SeqCst);
                        Json(json!({"source": "legacy"}))
                    }
                }
            }),
        );
        let upstream_addr = spawn_test_legacy_server(upstream).await;
        let router = build_router(test_config_for_legacy_http(upstream_addr));

        let response = router
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/api/market/health")
                    .body(Body::empty())
                    .expect("POST market-health request should be valid"),
            )
            .await
            .expect("router should answer POST market-health request");

        assert_eq!(response.status(), StatusCode::METHOD_NOT_ALLOWED);
        assert_eq!(legacy_market_price_hits.load(Ordering::SeqCst), 0);
    }

    #[tokio::test]
    async fn crypto_price_route_marks_legacy_fallback_with_source_header() {
        let symbol = format!("ZZ{}", &Uuid::new_v4().simple().to_string()[..10]).to_uppercase();
        let legacy_market_price_hits = Arc::new(AtomicUsize::new(0));
        let upstream = Router::new().route(
            "/api/market/price/{symbol}",
            get({
                let legacy_market_price_hits = Arc::clone(&legacy_market_price_hits);
                let expected_symbol = symbol.clone();
                move |axum::extract::Path(symbol): axum::extract::Path<String>,
                      axum::extract::Query(query): axum::extract::Query<
                    std::collections::HashMap<String, String>,
                >| {
                    let legacy_market_price_hits = Arc::clone(&legacy_market_price_hits);
                    let expected_symbol = expected_symbol.clone();
                    async move {
                        legacy_market_price_hits.fetch_add(1, Ordering::SeqCst);
                        assert_eq!(symbol, expected_symbol);
                        assert_eq!(query.get("market").map(String::as_str), Some("CRYPTO"));

                        Json(json!({
                            "symbol": "BTC.CRYPTO",
                            "market": "CRYPTO",
                            "price": 100.25,
                            "oracle_price": 100.25,
                            "change24h": 0.5,
                            "volume24h": 1000.0,
                            "percentage24h": 0.2,
                            "open_interest": 0.0,
                            "funding_rate": 0.0,
                            "timestamp": 1_776_312_400_000_i64
                        }))
                    }
                }
            }),
        );
        let upstream_addr = spawn_test_legacy_server(upstream).await;
        let router = build_router(test_config_for_legacy_http(upstream_addr));

        let response = router
            .oneshot(
                Request::builder()
                    .method("GET")
                    .uri(format!("/api/crypto/price/{symbol}"))
                    .body(Body::empty())
                    .expect("crypto-price request should be valid"),
            )
            .await
            .expect("router should answer crypto-price request");

        assert_eq!(response.status(), StatusCode::OK);
        assert_eq!(
            response
                .headers()
                .get("x-rust-crypto-price-source")
                .and_then(|value| value.to_str().ok()),
            Some("legacy-fallback")
        );
        let body = to_bytes(response.into_body(), usize::MAX)
            .await
            .expect("crypto-price response body should be readable");
        let payload: Value =
            serde_json::from_slice(&body).expect("crypto-price response should be json");
        assert_eq!(
            payload,
            json!({
                "symbol": symbol,
                "price": 100.25,
                "market": "CRYPTO"
            })
        );
        assert_eq!(legacy_market_price_hits.load(Ordering::SeqCst), 1);
    }

    #[tokio::test]
    async fn crypto_price_route_rejects_post_without_proxying() {
        let legacy_market_price_hits = Arc::new(AtomicUsize::new(0));
        let upstream = Router::new().route(
            "/api/market/price/{symbol}",
            get({
                let legacy_market_price_hits = Arc::clone(&legacy_market_price_hits);
                move || {
                    let legacy_market_price_hits = Arc::clone(&legacy_market_price_hits);
                    async move {
                        legacy_market_price_hits.fetch_add(1, Ordering::SeqCst);
                        Json(json!({"source": "legacy"}))
                    }
                }
            }),
        );
        let upstream_addr = spawn_test_legacy_server(upstream).await;
        let router = build_router(test_config_for_legacy_http(upstream_addr));

        let response = router
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/api/crypto/price/BTC")
                    .body(Body::empty())
                    .expect("POST crypto-price request should be valid"),
            )
            .await
            .expect("router should answer POST crypto-price request");

        assert_eq!(response.status(), StatusCode::METHOD_NOT_ALLOWED);
        assert_eq!(legacy_market_price_hits.load(Ordering::SeqCst), 0);
    }

    #[tokio::test]
    async fn crypto_status_route_marks_native_source_header() {
        let legacy_market_status_hits = Arc::new(AtomicUsize::new(0));
        let upstream = Router::new().route(
            "/api/market/status/{symbol}",
            get({
                let legacy_market_status_hits = Arc::clone(&legacy_market_status_hits);
                move || {
                    let legacy_market_status_hits = Arc::clone(&legacy_market_status_hits);
                    async move {
                        legacy_market_status_hits.fetch_add(1, Ordering::SeqCst);
                        Json(json!({"source": "legacy"}))
                    }
                }
            }),
        );
        let upstream_addr = spawn_test_legacy_server(upstream).await;
        let router = build_router(test_config_for_legacy_http(upstream_addr));

        let response = router
            .oneshot(
                Request::builder()
                    .method("GET")
                    .uri("/api/crypto/status/BTC")
                    .body(Body::empty())
                    .expect("crypto-status request should be valid"),
            )
            .await
            .expect("router should answer crypto-status request");

        assert_eq!(response.status(), StatusCode::OK);
        assert_eq!(
            response
                .headers()
                .get("x-rust-crypto-status-source")
                .and_then(|value| value.to_str().ok()),
            Some("native-synthetic")
        );
        let body = to_bytes(response.into_body(), usize::MAX)
            .await
            .expect("crypto-status response body should be readable");
        let payload: Value =
            serde_json::from_slice(&body).expect("crypto-status response should be json");
        assert_eq!(payload["symbol"], json!("BTC"));
        assert_eq!(payload["market"], json!("CRYPTO"));
        assert_eq!(payload["market_status"], json!("TRADING"));
        assert!(
            payload["timestamp"]
                .as_i64()
                .is_some_and(|timestamp| timestamp > 0),
            "timestamp should be generated"
        );
        assert!(
            payload["current_time"]
                .as_str()
                .is_some_and(|current_time| !current_time.is_empty()),
            "current_time should be generated"
        );
        assert_eq!(legacy_market_status_hits.load(Ordering::SeqCst), 0);
    }

    #[tokio::test]
    async fn crypto_status_route_rejects_post_without_proxying() {
        let legacy_market_status_hits = Arc::new(AtomicUsize::new(0));
        let upstream = Router::new().route(
            "/api/market/status/{symbol}",
            get({
                let legacy_market_status_hits = Arc::clone(&legacy_market_status_hits);
                move || {
                    let legacy_market_status_hits = Arc::clone(&legacy_market_status_hits);
                    async move {
                        legacy_market_status_hits.fetch_add(1, Ordering::SeqCst);
                        Json(json!({"source": "legacy"}))
                    }
                }
            }),
        );
        let upstream_addr = spawn_test_legacy_server(upstream).await;
        let router = build_router(test_config_for_legacy_http(upstream_addr));

        let response = router
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/api/crypto/status/BTC")
                    .body(Body::empty())
                    .expect("POST crypto-status request should be valid"),
            )
            .await
            .expect("router should answer POST crypto-status request");

        assert_eq!(response.status(), StatusCode::METHOD_NOT_ALLOWED);
        assert_eq!(legacy_market_status_hits.load(Ordering::SeqCst), 0);
    }

    #[tokio::test]
    async fn crypto_popular_route_marks_source_header() {
        let legacy_market_price_hits = Arc::new(AtomicUsize::new(0));
        let upstream = Router::new().route(
            "/api/market/price/{symbol}",
            get({
                let legacy_market_price_hits = Arc::clone(&legacy_market_price_hits);
                move |axum::extract::Path(symbol): axum::extract::Path<String>,
                      axum::extract::Query(query): axum::extract::Query<
                    std::collections::HashMap<String, String>,
                >| {
                    let legacy_market_price_hits = Arc::clone(&legacy_market_price_hits);
                    async move {
                        legacy_market_price_hits.fetch_add(1, Ordering::SeqCst);
                        assert_eq!(query.get("market").map(String::as_str), Some("CRYPTO"));
                        let price = match symbol.as_str() {
                            "BTC" => 101_000.0,
                            "ETH" => 5_100.0,
                            "SOL" => 180.0,
                            "DOGE" => 0.23,
                            "BNB" => 720.0,
                            "XRP" => 1.8,
                            unexpected => panic!("unexpected symbol requested: {unexpected}"),
                        };
                        Json(json!({
                            "symbol": format!("{symbol}.CRYPTO"),
                            "market": "CRYPTO",
                            "price": price,
                            "oracle_price": price,
                            "change24h": 0.5,
                            "volume24h": 1000.0,
                            "percentage24h": 0.2,
                            "open_interest": 0.0,
                            "funding_rate": 0.0,
                            "timestamp": 1_776_312_400_000_i64
                        }))
                    }
                }
            }),
        );
        let upstream_addr = spawn_test_legacy_server(upstream).await;
        let router = build_router(test_config_for_legacy_http(upstream_addr));

        let response = router
            .oneshot(
                Request::builder()
                    .method("GET")
                    .uri("/api/crypto/popular")
                    .body(Body::empty())
                    .expect("crypto-popular request should be valid"),
            )
            .await
            .expect("router should answer crypto-popular request");

        assert_eq!(response.status(), StatusCode::OK);
        let source_header = response
            .headers()
            .get("x-rust-crypto-popular-source")
            .and_then(|value| value.to_str().ok())
            .map(str::to_owned);
        let body = to_bytes(response.into_body(), usize::MAX)
            .await
            .expect("crypto-popular response body should be readable");
        let payload: Value =
            serde_json::from_slice(&body).expect("crypto-popular response should be json");
        let legacy_hits = legacy_market_price_hits.load(Ordering::SeqCst);

        let expected_source = if legacy_hits == 0 {
            "native-db"
        } else if legacy_hits == 6 {
            "legacy-fallback"
        } else {
            "mixed"
        };
        assert_eq!(source_header.as_deref(), Some(expected_source));
        assert_eq!(payload.as_array().map(Vec::len), Some(6));
        for item in payload
            .as_array()
            .expect("crypto-popular payload should be array")
        {
            let symbol = item["symbol"]
                .as_str()
                .expect("symbol should be present in each entry");
            assert_eq!(item["name"], json!(symbol));
            assert_eq!(item["market"], json!("CRYPTO"));
            assert!(
                item["price"].as_f64().is_some(),
                "price should be numeric in each entry"
            );
        }

        let expected_symbols = ["BTC", "ETH", "SOL", "DOGE", "BNB", "XRP"];
        let actual_symbols = payload
            .as_array()
            .expect("crypto-popular payload should be array")
            .iter()
            .map(|item| item["symbol"].as_str().unwrap_or_default().to_owned())
            .collect::<Vec<_>>();
        assert_eq!(actual_symbols, expected_symbols);
        assert!(
            legacy_hits <= 6,
            "fallback call count should not exceed popular symbol count"
        );
    }

    #[tokio::test]
    async fn crypto_popular_route_rejects_post_without_proxying() {
        let legacy_market_price_hits = Arc::new(AtomicUsize::new(0));
        let upstream = Router::new().route(
            "/api/market/price/{symbol}",
            get({
                let legacy_market_price_hits = Arc::clone(&legacy_market_price_hits);
                move || {
                    let legacy_market_price_hits = Arc::clone(&legacy_market_price_hits);
                    async move {
                        legacy_market_price_hits.fetch_add(1, Ordering::SeqCst);
                        Json(json!({"source": "legacy"}))
                    }
                }
            }),
        );
        let upstream_addr = spawn_test_legacy_server(upstream).await;
        let router = build_router(test_config_for_legacy_http(upstream_addr));

        let response = router
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/api/crypto/popular")
                    .body(Body::empty())
                    .expect("POST crypto-popular request should be valid"),
            )
            .await
            .expect("router should answer POST crypto-popular request");

        assert_eq!(response.status(), StatusCode::METHOD_NOT_ALLOWED);
        assert_eq!(legacy_market_price_hits.load(Ordering::SeqCst), 0);
    }

    #[tokio::test]
    async fn crypto_symbols_route_marks_legacy_fallback_with_source_header() {
        let _guard = crypto_symbols_config_test_lock().lock().await;
        let pool = local_db_pool().await;
        let backup = backup_system_config(&pool, CRYPTO_SYMBOLS_CONFIG_KEY).await;
        delete_system_config(&pool, CRYPTO_SYMBOLS_CONFIG_KEY).await;

        let legacy_crypto_symbols_hits = Arc::new(AtomicUsize::new(0));
        let upstream = Router::new().route(
            "/api/crypto/symbols",
            get({
                let legacy_crypto_symbols_hits = Arc::clone(&legacy_crypto_symbols_hits);
                move || {
                    let legacy_crypto_symbols_hits = Arc::clone(&legacy_crypto_symbols_hits);
                    async move {
                        legacy_crypto_symbols_hits.fetch_add(1, Ordering::SeqCst);
                        Json(json!(["BTC/USD", "ETH/USD"]))
                    }
                }
            }),
        );
        let upstream_addr = spawn_test_legacy_server(upstream).await;
        let router = build_router(test_config_for_legacy_http(upstream_addr));

        let response = router
            .oneshot(
                Request::builder()
                    .method("GET")
                    .uri("/api/crypto/symbols")
                    .body(Body::empty())
                    .expect("crypto-symbols request should be valid"),
            )
            .await
            .expect("router should answer crypto-symbols request");

        assert_eq!(response.status(), StatusCode::OK);
        assert_eq!(
            response
                .headers()
                .get("x-rust-crypto-symbols-source")
                .and_then(|value| value.to_str().ok()),
            Some("legacy-fallback")
        );
        let body = to_bytes(response.into_body(), usize::MAX)
            .await
            .expect("crypto-symbols response body should be readable");
        let payload: Value =
            serde_json::from_slice(&body).expect("crypto-symbols response should be json");
        let legacy_hits = legacy_crypto_symbols_hits.load(Ordering::SeqCst);

        restore_system_config(&pool, CRYPTO_SYMBOLS_CONFIG_KEY, backup).await;

        assert_eq!(payload, json!(["BTC/USD", "ETH/USD"]));
        assert_eq!(legacy_hits, 1);
    }

    #[tokio::test]
    async fn crypto_symbols_route_uses_native_config_without_legacy_fallback() {
        let _guard = crypto_symbols_config_test_lock().lock().await;
        let pool = local_db_pool().await;
        let backup = backup_system_config(&pool, CRYPTO_SYMBOLS_CONFIG_KEY).await;
        upsert_system_config(
            &pool,
            CRYPTO_SYMBOLS_CONFIG_KEY,
            r#"[{"symbol":"BTC/USD"},{"symbol":"ETH/USD"}]"#,
            Some("crypto symbols native-config fixture"),
        )
        .await;

        let legacy_crypto_symbols_hits = Arc::new(AtomicUsize::new(0));
        let upstream = Router::new().route(
            "/api/crypto/symbols",
            get({
                let legacy_crypto_symbols_hits = Arc::clone(&legacy_crypto_symbols_hits);
                move || {
                    let legacy_crypto_symbols_hits = Arc::clone(&legacy_crypto_symbols_hits);
                    async move {
                        legacy_crypto_symbols_hits.fetch_add(1, Ordering::SeqCst);
                        Json(json!(["legacy"]))
                    }
                }
            }),
        );
        let upstream_addr = spawn_test_legacy_server(upstream).await;
        let router = build_router(test_config_for_legacy_http(upstream_addr));

        let response = router
            .oneshot(
                Request::builder()
                    .method("GET")
                    .uri("/api/crypto/symbols")
                    .body(Body::empty())
                    .expect("native crypto-symbols request should be valid"),
            )
            .await
            .expect("router should answer native crypto-symbols request");

        let response_status = response.status();
        let source_header = response
            .headers()
            .get("x-rust-crypto-symbols-source")
            .and_then(|value| value.to_str().ok())
            .map(str::to_owned);
        let body = to_bytes(response.into_body(), usize::MAX)
            .await
            .expect("native crypto-symbols response body should be readable");
        let payload: Value =
            serde_json::from_slice(&body).expect("native crypto-symbols response should be json");
        let legacy_hits = legacy_crypto_symbols_hits.load(Ordering::SeqCst);

        restore_system_config(&pool, CRYPTO_SYMBOLS_CONFIG_KEY, backup).await;

        assert_eq!(response_status, StatusCode::OK);
        assert_eq!(source_header.as_deref(), Some("native-config"));
        assert_eq!(payload, json!(["BTC/USD", "ETH/USD"]));
        assert_eq!(legacy_hits, 0);
    }

    #[tokio::test]
    async fn crypto_symbols_route_rejects_post_without_proxying() {
        let legacy_crypto_symbols_hits = Arc::new(AtomicUsize::new(0));
        let upstream = Router::new().route(
            "/api/crypto/symbols",
            get({
                let legacy_crypto_symbols_hits = Arc::clone(&legacy_crypto_symbols_hits);
                move || {
                    let legacy_crypto_symbols_hits = Arc::clone(&legacy_crypto_symbols_hits);
                    async move {
                        legacy_crypto_symbols_hits.fetch_add(1, Ordering::SeqCst);
                        Json(json!(["legacy"]))
                    }
                }
            }),
        );
        let upstream_addr = spawn_test_legacy_server(upstream).await;
        let router = build_router(test_config_for_legacy_http(upstream_addr));

        let response = router
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/api/crypto/symbols")
                    .body(Body::empty())
                    .expect("POST crypto-symbols request should be valid"),
            )
            .await
            .expect("router should answer POST crypto-symbols request");

        assert_eq!(response.status(), StatusCode::METHOD_NOT_ALLOWED);
        assert_eq!(legacy_crypto_symbols_hits.load(Ordering::SeqCst), 0);
    }

    #[tokio::test]
    async fn market_kline_route_marks_legacy_fallback_with_source_header() {
        let legacy_market_kline_hits = Arc::new(AtomicUsize::new(0));
        let upstream = Router::new().route(
            "/api/market/kline/{symbol}",
            get({
                let legacy_market_kline_hits = Arc::clone(&legacy_market_kline_hits);
                move |axum::extract::Path(symbol): axum::extract::Path<String>,
                      axum::extract::Query(query): axum::extract::Query<
                    std::collections::HashMap<String, String>,
                >| {
                    let legacy_market_kline_hits = Arc::clone(&legacy_market_kline_hits);
                    async move {
                        legacy_market_kline_hits.fetch_add(1, Ordering::SeqCst);
                        assert_eq!(symbol, "BTC");
                        assert_eq!(query.get("market").map(String::as_str), Some("US"));
                        assert_eq!(query.get("period").map(String::as_str), Some("1h"));
                        assert_eq!(query.get("count").map(String::as_str), Some("2"));

                        Json(json!({
                            "symbol": "BTC",
                            "market": "US",
                            "period": "1h",
                            "count": 2,
                            "data": [
                                {
                                    "timestamp": 1_776_312_400_i32,
                                    "datetime": "2026-04-16T00:00:00Z",
                                    "open": 100.0,
                                    "high": 101.0,
                                    "low": 99.5,
                                    "close": 100.25,
                                    "volume": 5000.0,
                                    "amount": 501250.0,
                                    "chg": 0.5,
                                    "percent": 0.2
                                },
                                {
                                    "timestamp": 1_776_312_460_i32,
                                    "datetime": "2026-04-16T00:01:00Z",
                                    "open": 100.25,
                                    "high": 100.75,
                                    "low": 100.0,
                                    "close": 100.5,
                                    "volume": 4200.0,
                                    "amount": 422100.0,
                                    "chg": 0.25,
                                    "percent": 0.1
                                }
                            ]
                        }))
                    }
                }
            }),
        );
        let upstream_addr = spawn_test_legacy_server(upstream).await;
        let router = build_router(test_config_for_legacy_http(upstream_addr));

        let response = router
            .oneshot(
                Request::builder()
                    .method("GET")
                    .uri("/api/market/kline/BTC?market=US&period=1h&count=2")
                    .body(Body::empty())
                    .expect("market-kline request should be valid"),
            )
            .await
            .expect("router should answer market-kline request");

        assert_eq!(response.status(), StatusCode::OK);
        assert_eq!(
            response
                .headers()
                .get("x-rust-market-kline-source")
                .and_then(|value| value.to_str().ok()),
            Some("legacy-fallback")
        );
        let body = to_bytes(response.into_body(), usize::MAX)
            .await
            .expect("market-kline response body should be readable");
        let payload: Value =
            serde_json::from_slice(&body).expect("market-kline response should be json");
        assert_eq!(payload["symbol"], json!("BTC"));
        assert_eq!(payload["market"], json!("US"));
        assert_eq!(payload["period"], json!("1h"));
        assert_eq!(payload["count"], json!(2));
        assert_eq!(
            payload["data"][0]["datetime"],
            json!("2026-04-16T00:00:00Z")
        );
        assert_eq!(legacy_market_kline_hits.load(Ordering::SeqCst), 1);
    }

    #[tokio::test]
    async fn market_kline_route_validates_query_without_proxying() {
        let legacy_market_kline_hits = Arc::new(AtomicUsize::new(0));
        let upstream = Router::new().route(
            "/api/market/kline/{symbol}",
            get({
                let legacy_market_kline_hits = Arc::clone(&legacy_market_kline_hits);
                move || {
                    let legacy_market_kline_hits = Arc::clone(&legacy_market_kline_hits);
                    async move {
                        legacy_market_kline_hits.fetch_add(1, Ordering::SeqCst);
                        Json(json!({"source": "legacy"}))
                    }
                }
            }),
        );
        let upstream_addr = spawn_test_legacy_server(upstream).await;
        let router = build_router(test_config_for_legacy_http(upstream_addr));

        let response = router
            .oneshot(
                Request::builder()
                    .method("GET")
                    .uri("/api/market/kline/BTC?market=US&period=10m&count=2")
                    .body(Body::empty())
                    .expect("invalid market-kline request should be valid"),
            )
            .await
            .expect("router should answer invalid market-kline request");

        assert_eq!(response.status(), StatusCode::BAD_REQUEST);
        let body = to_bytes(response.into_body(), usize::MAX)
            .await
            .expect("invalid market-kline response body should be readable");
        let payload: Value =
            serde_json::from_slice(&body).expect("invalid market-kline response should be json");
        assert!(
            payload["detail"]
                .as_str()
                .is_some_and(|detail| detail.contains("Unsupported time period")),
            "detail should mention unsupported period"
        );
        assert_eq!(legacy_market_kline_hits.load(Ordering::SeqCst), 0);
    }

    #[tokio::test]
    async fn market_kline_route_rejects_post_without_proxying() {
        let legacy_market_kline_hits = Arc::new(AtomicUsize::new(0));
        let upstream = Router::new().route(
            "/api/market/kline/{symbol}",
            get({
                let legacy_market_kline_hits = Arc::clone(&legacy_market_kline_hits);
                move || {
                    let legacy_market_kline_hits = Arc::clone(&legacy_market_kline_hits);
                    async move {
                        legacy_market_kline_hits.fetch_add(1, Ordering::SeqCst);
                        Json(json!({"source": "legacy"}))
                    }
                }
            }),
        );
        let upstream_addr = spawn_test_legacy_server(upstream).await;
        let router = build_router(test_config_for_legacy_http(upstream_addr));

        let response = router
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/api/market/kline/BTC?market=US&period=1h&count=2")
                    .body(Body::empty())
                    .expect("POST market-kline request should be valid"),
            )
            .await
            .expect("router should answer POST market-kline request");

        assert_eq!(response.status(), StatusCode::METHOD_NOT_ALLOWED);
        assert_eq!(legacy_market_kline_hits.load(Ordering::SeqCst), 0);
    }

    #[tokio::test]
    async fn market_kline_with_indicators_route_marks_legacy_fallback_with_source_header() {
        let legacy_market_kline_with_indicators_hits = Arc::new(AtomicUsize::new(0));
        let upstream = Router::new().route(
            "/api/market/kline-with-indicators/{symbol}",
            get({
                let legacy_market_kline_with_indicators_hits =
                    Arc::clone(&legacy_market_kline_with_indicators_hits);
                move |axum::extract::Path(symbol): axum::extract::Path<String>,
                      axum::extract::Query(query): axum::extract::Query<
                    std::collections::HashMap<String, String>,
                >| {
                    let legacy_market_kline_with_indicators_hits =
                        Arc::clone(&legacy_market_kline_with_indicators_hits);
                    async move {
                        legacy_market_kline_with_indicators_hits.fetch_add(1, Ordering::SeqCst);
                        assert_eq!(symbol, "BTC");
                        assert_eq!(query.get("market").map(String::as_str), Some("US"));
                        assert_eq!(query.get("period").map(String::as_str), Some("1h"));
                        assert_eq!(query.get("count").map(String::as_str), Some("2"));
                        assert_eq!(
                            query.get("indicators").map(String::as_str),
                            Some("EMA20,RSI14")
                        );

                        Json(json!({
                            "symbol": "BTC",
                            "market": "US",
                            "period": "1h",
                            "count": 2,
                            "klines": [
                                {
                                    "timestamp": 1_776_312_400_i32,
                                    "datetime": "2026-04-16T00:00:00Z",
                                    "open": 100.0,
                                    "high": 101.0,
                                    "low": 99.5,
                                    "close": 100.25,
                                    "volume": 5000.0,
                                    "amount": 501250.0,
                                    "chg": 0.5,
                                    "percent": 0.2
                                },
                                {
                                    "timestamp": 1_776_312_460_i32,
                                    "datetime": "2026-04-16T00:01:00Z",
                                    "open": 100.25,
                                    "high": 100.75,
                                    "low": 100.0,
                                    "close": 100.5,
                                    "volume": 4200.0,
                                    "amount": 422100.0,
                                    "chg": 0.25,
                                    "percent": 0.1
                                }
                            ],
                            "indicators": {
                                "EMA20": [100.25, 100.5],
                                "RSI14": [52.2, 54.8]
                            }
                        }))
                    }
                }
            }),
        );
        let upstream_addr = spawn_test_legacy_server(upstream).await;
        let router = build_router(test_config_for_legacy_http(upstream_addr));

        let response = router
            .oneshot(
                Request::builder()
                    .method("GET")
                    .uri("/api/market/kline-with-indicators/BTC?market=US&period=1h&count=2&indicators=EMA20,RSI14")
                    .body(Body::empty())
                    .expect("market-kline-with-indicators request should be valid"),
            )
            .await
            .expect("router should answer market-kline-with-indicators request");

        assert_eq!(response.status(), StatusCode::OK);
        assert_eq!(
            response
                .headers()
                .get("x-rust-market-kline-with-indicators-source")
                .and_then(|value| value.to_str().ok()),
            Some("legacy-fallback")
        );
        let body = to_bytes(response.into_body(), usize::MAX)
            .await
            .expect("market-kline-with-indicators response body should be readable");
        let payload: Value = serde_json::from_slice(&body)
            .expect("market-kline-with-indicators response should be json");
        assert_eq!(payload["symbol"], json!("BTC"));
        assert_eq!(payload["market"], json!("US"));
        assert_eq!(payload["period"], json!("1h"));
        assert_eq!(payload["count"], json!(2));
        assert_eq!(
            payload["klines"][0]["datetime"],
            json!("2026-04-16T00:00:00Z")
        );
        assert_eq!(payload["indicators"]["EMA20"][0], json!(100.25));
        assert_eq!(
            legacy_market_kline_with_indicators_hits.load(Ordering::SeqCst),
            1
        );
    }

    #[tokio::test]
    async fn market_kline_with_indicators_route_uses_legacy_default_period_without_proxying() {
        let legacy_market_kline_with_indicators_hits = Arc::new(AtomicUsize::new(0));
        let upstream = Router::new().route(
            "/api/market/kline-with-indicators/{symbol}",
            get({
                let legacy_market_kline_with_indicators_hits =
                    Arc::clone(&legacy_market_kline_with_indicators_hits);
                move |axum::extract::Query(query): axum::extract::Query<
                    std::collections::HashMap<String, String>,
                >| {
                    let legacy_market_kline_with_indicators_hits =
                        Arc::clone(&legacy_market_kline_with_indicators_hits);
                    async move {
                        legacy_market_kline_with_indicators_hits.fetch_add(1, Ordering::SeqCst);
                        assert_eq!(query.get("period").map(String::as_str), Some("1h"));
                        assert_eq!(query.get("count").map(String::as_str), Some("500"));

                        Json(json!({
                            "symbol": "BTC",
                            "market": "hyperliquid",
                            "period": "1h",
                            "count": 0,
                            "klines": [],
                            "indicators": {}
                        }))
                    }
                }
            }),
        );
        let upstream_addr = spawn_test_legacy_server(upstream).await;
        let router = build_router(test_config_for_legacy_http(upstream_addr));

        let response = router
            .oneshot(
                Request::builder()
                    .method("GET")
                    .uri("/api/market/kline-with-indicators/BTC")
                    .body(Body::empty())
                    .expect("default market-kline-with-indicators request should be valid"),
            )
            .await
            .expect("router should answer default market-kline-with-indicators request");

        assert_eq!(response.status(), StatusCode::OK);
        assert_eq!(
            legacy_market_kline_with_indicators_hits.load(Ordering::SeqCst),
            1
        );
    }

    #[tokio::test]
    async fn market_kline_with_indicators_route_validates_query_without_proxying() {
        let legacy_market_kline_with_indicators_hits = Arc::new(AtomicUsize::new(0));
        let upstream = Router::new().route(
            "/api/market/kline-with-indicators/{symbol}",
            get({
                let legacy_market_kline_with_indicators_hits =
                    Arc::clone(&legacy_market_kline_with_indicators_hits);
                move || {
                    let legacy_market_kline_with_indicators_hits =
                        Arc::clone(&legacy_market_kline_with_indicators_hits);
                    async move {
                        legacy_market_kline_with_indicators_hits.fetch_add(1, Ordering::SeqCst);
                        Json(json!({"source": "legacy"}))
                    }
                }
            }),
        );
        let upstream_addr = spawn_test_legacy_server(upstream).await;
        let router = build_router(test_config_for_legacy_http(upstream_addr));

        let response = router
            .oneshot(
                Request::builder()
                    .method("GET")
                    .uri("/api/market/kline-with-indicators/BTC?market=US&period=10m&count=2&indicators=EMA20")
                    .body(Body::empty())
                    .expect("invalid market-kline-with-indicators request should be valid"),
            )
            .await
            .expect("router should answer invalid market-kline-with-indicators request");

        assert_eq!(response.status(), StatusCode::BAD_REQUEST);
        let body = to_bytes(response.into_body(), usize::MAX)
            .await
            .expect("invalid market-kline-with-indicators response body should be readable");
        let payload: Value = serde_json::from_slice(&body)
            .expect("invalid market-kline-with-indicators response should be json");
        assert!(
            payload["detail"]
                .as_str()
                .is_some_and(|detail| detail.contains("Unsupported time period")),
            "detail should mention unsupported period"
        );
        assert_eq!(
            legacy_market_kline_with_indicators_hits.load(Ordering::SeqCst),
            0
        );
    }

    #[tokio::test]
    async fn market_kline_with_indicators_route_rejects_post_without_proxying() {
        let legacy_market_kline_with_indicators_hits = Arc::new(AtomicUsize::new(0));
        let upstream = Router::new().route(
            "/api/market/kline-with-indicators/{symbol}",
            get({
                let legacy_market_kline_with_indicators_hits =
                    Arc::clone(&legacy_market_kline_with_indicators_hits);
                move || {
                    let legacy_market_kline_with_indicators_hits =
                        Arc::clone(&legacy_market_kline_with_indicators_hits);
                    async move {
                        legacy_market_kline_with_indicators_hits.fetch_add(1, Ordering::SeqCst);
                        Json(json!({"source": "legacy"}))
                    }
                }
            }),
        );
        let upstream_addr = spawn_test_legacy_server(upstream).await;
        let router = build_router(test_config_for_legacy_http(upstream_addr));

        let response = router
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/api/market/kline-with-indicators/BTC?market=US&period=1h&count=2&indicators=EMA20")
                    .body(Body::empty())
                    .expect("POST market-kline-with-indicators request should be valid"),
            )
            .await
            .expect("router should answer POST market-kline-with-indicators request");

        assert_eq!(response.status(), StatusCode::METHOD_NOT_ALLOWED);
        assert_eq!(
            legacy_market_kline_with_indicators_hits.load(Ordering::SeqCst),
            0
        );
    }

    #[tokio::test]
    async fn prompt_backtest_task_create_route_forwards_legacy_contract_through_native_handler() {
        let legacy_prompt_backtest_create_hits = Arc::new(AtomicUsize::new(0));
        let upstream = Router::new().route(
            "/api/prompt-backtest/tasks",
            post({
                let legacy_prompt_backtest_create_hits =
                    Arc::clone(&legacy_prompt_backtest_create_hits);
                move |axum::extract::Json(payload): axum::extract::Json<Value>| {
                    let legacy_prompt_backtest_create_hits =
                        Arc::clone(&legacy_prompt_backtest_create_hits);
                    async move {
                        legacy_prompt_backtest_create_hits.fetch_add(1, Ordering::SeqCst);
                        assert_eq!(payload["account_id"], json!(77));
                        assert_eq!(payload["name"], json!("April Replay"));
                        assert_eq!(
                            payload["items"],
                            json!([
                                {
                                    "decision_log_id": 1001,
                                    "modified_prompt": "Prompt A"
                                },
                                {
                                    "decision_log_id": 1002,
                                    "modified_prompt": "Prompt B"
                                }
                            ])
                        );
                        assert_eq!(
                            payload["replace_rules"],
                            json!([
                                {
                                    "find": "BTC",
                                    "replace": "ETH"
                                }
                            ])
                        );

                        Json(json!({
                            "task_id": 501,
                            "status": "pending",
                            "total_count": 2
                        }))
                    }
                }
            }),
        );
        let upstream_addr = spawn_test_legacy_server(upstream).await;
        let router = build_router(test_config_for_legacy_http(upstream_addr));

        let response = router
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/api/prompt-backtest/tasks")
                    .header(header::CONTENT_TYPE, "application/json")
                    .body(Body::from(
                        json!({
                            "account_id": 77,
                            "name": "April Replay",
                            "items": [
                                { "decision_log_id": 1001, "modified_prompt": "Prompt A" },
                                { "decision_log_id": 1002, "modified_prompt": "Prompt B" }
                            ],
                            "replace_rules": [
                                { "find": "BTC", "replace": "ETH" }
                            ]
                        })
                        .to_string(),
                    ))
                    .expect("prompt-backtest create request should be valid"),
            )
            .await
            .expect("router should answer prompt-backtest create request");

        assert_eq!(response.status(), StatusCode::OK);
        let body = to_bytes(response.into_body(), usize::MAX)
            .await
            .expect("prompt-backtest create response body should be readable");
        let payload: Value =
            serde_json::from_slice(&body).expect("prompt-backtest create response should be json");
        assert_eq!(payload["task_id"], json!(501));
        assert_eq!(payload["status"], json!("pending"));
        assert_eq!(payload["total_count"], json!(2));
        assert_eq!(legacy_prompt_backtest_create_hits.load(Ordering::SeqCst), 1);
    }

    #[tokio::test]
    async fn prompt_backtest_task_create_route_validates_payload_without_proxying() {
        let legacy_prompt_backtest_create_hits = Arc::new(AtomicUsize::new(0));
        let upstream = Router::new().route(
            "/api/prompt-backtest/tasks",
            post({
                let legacy_prompt_backtest_create_hits =
                    Arc::clone(&legacy_prompt_backtest_create_hits);
                move || {
                    let legacy_prompt_backtest_create_hits =
                        Arc::clone(&legacy_prompt_backtest_create_hits);
                    async move {
                        legacy_prompt_backtest_create_hits.fetch_add(1, Ordering::SeqCst);
                        Json(json!({ "source": "legacy" }))
                    }
                }
            }),
        );
        let upstream_addr = spawn_test_legacy_server(upstream).await;
        let router = build_router(test_config_for_legacy_http(upstream_addr));

        let response = router
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/api/prompt-backtest/tasks")
                    .header(header::CONTENT_TYPE, "application/json")
                    .body(Body::from(
                        json!({
                            "name": "Missing account id",
                            "items": [
                                { "decision_log_id": 1001, "modified_prompt": "Prompt A" }
                            ]
                        })
                        .to_string(),
                    ))
                    .expect("invalid prompt-backtest create request should be valid"),
            )
            .await
            .expect("router should answer invalid prompt-backtest create request");

        assert_eq!(response.status(), StatusCode::BAD_REQUEST);
        let body = to_bytes(response.into_body(), usize::MAX)
            .await
            .expect("invalid prompt-backtest create response body should be readable");
        let payload: Value = serde_json::from_slice(&body)
            .expect("invalid prompt-backtest create response should be json");
        let detail = payload["detail"]
            .as_str()
            .expect("detail should be a string");
        assert!(detail.contains("invalid prompt backtest create payload"));
        assert!(detail.contains("account_id"));
        assert_eq!(legacy_prompt_backtest_create_hits.load(Ordering::SeqCst), 0);
    }

    #[tokio::test]
    async fn prompt_backtest_task_create_route_rejects_put_without_proxying() {
        let legacy_prompt_backtest_create_hits = Arc::new(AtomicUsize::new(0));
        let upstream = Router::new().route(
            "/api/prompt-backtest/tasks",
            post({
                let legacy_prompt_backtest_create_hits =
                    Arc::clone(&legacy_prompt_backtest_create_hits);
                move || {
                    let legacy_prompt_backtest_create_hits =
                        Arc::clone(&legacy_prompt_backtest_create_hits);
                    async move {
                        legacy_prompt_backtest_create_hits.fetch_add(1, Ordering::SeqCst);
                        Json(json!({ "source": "legacy" }))
                    }
                }
            }),
        );
        let upstream_addr = spawn_test_legacy_server(upstream).await;
        let router = build_router(test_config_for_legacy_http(upstream_addr));

        let response = router
            .oneshot(
                Request::builder()
                    .method("PUT")
                    .uri("/api/prompt-backtest/tasks")
                    .body(Body::empty())
                    .expect("PUT prompt-backtest create request should be valid"),
            )
            .await
            .expect("router should answer PUT prompt-backtest create request");

        assert_eq!(response.status(), StatusCode::METHOD_NOT_ALLOWED);
        assert_eq!(legacy_prompt_backtest_create_hits.load(Ordering::SeqCst), 0);
    }

    #[tokio::test]
    async fn prompt_backtest_task_delete_route_forwards_legacy_contract_through_native_handler() {
        let legacy_prompt_backtest_delete_hits = Arc::new(AtomicUsize::new(0));
        let upstream = Router::new().route(
            "/api/prompt-backtest/tasks/{task_id}",
            delete({
                let legacy_prompt_backtest_delete_hits =
                    Arc::clone(&legacy_prompt_backtest_delete_hits);
                move |axum::extract::Path(task_id): axum::extract::Path<String>| {
                    let legacy_prompt_backtest_delete_hits =
                        Arc::clone(&legacy_prompt_backtest_delete_hits);
                    async move {
                        legacy_prompt_backtest_delete_hits.fetch_add(1, Ordering::SeqCst);
                        assert_eq!(task_id, "601");

                        Json(json!({
                            "success": true,
                            "message": "Task deleted"
                        }))
                    }
                }
            }),
        );
        let upstream_addr = spawn_test_legacy_server(upstream).await;
        let router = build_router(test_config_for_legacy_http(upstream_addr));

        let response = router
            .oneshot(
                Request::builder()
                    .method("DELETE")
                    .uri("/api/prompt-backtest/tasks/601")
                    .body(Body::empty())
                    .expect("prompt-backtest delete request should be valid"),
            )
            .await
            .expect("router should answer prompt-backtest delete request");

        assert_eq!(response.status(), StatusCode::OK);
        let body = to_bytes(response.into_body(), usize::MAX)
            .await
            .expect("prompt-backtest delete response body should be readable");
        let payload: Value =
            serde_json::from_slice(&body).expect("prompt-backtest delete response should be json");
        assert_eq!(payload["success"], json!(true));
        assert_eq!(payload["message"], json!("Task deleted"));
        assert_eq!(legacy_prompt_backtest_delete_hits.load(Ordering::SeqCst), 1);
    }

    #[tokio::test]
    async fn prompt_backtest_task_delete_route_validates_path_without_proxying() {
        let legacy_prompt_backtest_delete_hits = Arc::new(AtomicUsize::new(0));
        let upstream = Router::new().route(
            "/api/prompt-backtest/tasks/{task_id}",
            delete({
                let legacy_prompt_backtest_delete_hits =
                    Arc::clone(&legacy_prompt_backtest_delete_hits);
                move || {
                    let legacy_prompt_backtest_delete_hits =
                        Arc::clone(&legacy_prompt_backtest_delete_hits);
                    async move {
                        legacy_prompt_backtest_delete_hits.fetch_add(1, Ordering::SeqCst);
                        Json(json!({ "source": "legacy" }))
                    }
                }
            }),
        );
        let upstream_addr = spawn_test_legacy_server(upstream).await;
        let router = build_router(test_config_for_legacy_http(upstream_addr));

        let response = router
            .oneshot(
                Request::builder()
                    .method("DELETE")
                    .uri("/api/prompt-backtest/tasks/not-an-int")
                    .body(Body::empty())
                    .expect("invalid prompt-backtest delete request should be valid"),
            )
            .await
            .expect("router should answer invalid prompt-backtest delete request");

        assert_eq!(response.status(), StatusCode::BAD_REQUEST);
        let body = to_bytes(response.into_body(), usize::MAX)
            .await
            .expect("invalid prompt-backtest delete response body should be readable");
        let payload: Value = serde_json::from_slice(&body)
            .expect("invalid prompt-backtest delete response should be json");
        assert_eq!(
            payload["detail"],
            json!("task_id path parameter must be a valid integer")
        );
        assert_eq!(legacy_prompt_backtest_delete_hits.load(Ordering::SeqCst), 0);
    }

    #[tokio::test]
    async fn prompt_backtest_task_delete_route_rejects_put_without_proxying() {
        let legacy_prompt_backtest_delete_hits = Arc::new(AtomicUsize::new(0));
        let upstream = Router::new().route(
            "/api/prompt-backtest/tasks/{task_id}",
            delete({
                let legacy_prompt_backtest_delete_hits =
                    Arc::clone(&legacy_prompt_backtest_delete_hits);
                move || {
                    let legacy_prompt_backtest_delete_hits =
                        Arc::clone(&legacy_prompt_backtest_delete_hits);
                    async move {
                        legacy_prompt_backtest_delete_hits.fetch_add(1, Ordering::SeqCst);
                        Json(json!({ "source": "legacy" }))
                    }
                }
            }),
        );
        let upstream_addr = spawn_test_legacy_server(upstream).await;
        let router = build_router(test_config_for_legacy_http(upstream_addr));

        let response = router
            .oneshot(
                Request::builder()
                    .method("PUT")
                    .uri("/api/prompt-backtest/tasks/601")
                    .body(Body::empty())
                    .expect("PUT prompt-backtest delete request should be valid"),
            )
            .await
            .expect("router should answer PUT prompt-backtest delete request");

        assert_eq!(response.status(), StatusCode::METHOD_NOT_ALLOWED);
        assert_eq!(legacy_prompt_backtest_delete_hits.load(Ordering::SeqCst), 0);
    }

    #[tokio::test]
    async fn prompt_backtest_task_retry_route_forwards_legacy_contract_through_native_handler() {
        let legacy_prompt_backtest_retry_hits = Arc::new(AtomicUsize::new(0));
        let upstream = Router::new().route(
            "/api/prompt-backtest/tasks/{task_id}/retry",
            post({
                let legacy_prompt_backtest_retry_hits =
                    Arc::clone(&legacy_prompt_backtest_retry_hits);
                move |axum::extract::Path(task_id): axum::extract::Path<String>| {
                    let legacy_prompt_backtest_retry_hits =
                        Arc::clone(&legacy_prompt_backtest_retry_hits);
                    async move {
                        legacy_prompt_backtest_retry_hits.fetch_add(1, Ordering::SeqCst);
                        assert_eq!(task_id, "601");

                        Json(json!({
                            "success": true,
                            "message": "Retrying 2 failed items",
                            "retry_count": 2
                        }))
                    }
                }
            }),
        );
        let upstream_addr = spawn_test_legacy_server(upstream).await;
        let router = build_router(test_config_for_legacy_http(upstream_addr));

        let response = router
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/api/prompt-backtest/tasks/601/retry")
                    .body(Body::empty())
                    .expect("prompt-backtest retry request should be valid"),
            )
            .await
            .expect("router should answer prompt-backtest retry request");

        assert_eq!(response.status(), StatusCode::OK);
        let body = to_bytes(response.into_body(), usize::MAX)
            .await
            .expect("prompt-backtest retry response body should be readable");
        let payload: Value =
            serde_json::from_slice(&body).expect("prompt-backtest retry response should be json");
        assert_eq!(payload["success"], json!(true));
        assert_eq!(payload["message"], json!("Retrying 2 failed items"));
        assert_eq!(payload["retry_count"], json!(2));
        assert_eq!(legacy_prompt_backtest_retry_hits.load(Ordering::SeqCst), 1);
    }

    #[tokio::test]
    async fn prompt_backtest_task_retry_route_validates_path_without_proxying() {
        let legacy_prompt_backtest_retry_hits = Arc::new(AtomicUsize::new(0));
        let upstream = Router::new().route(
            "/api/prompt-backtest/tasks/{task_id}/retry",
            post({
                let legacy_prompt_backtest_retry_hits =
                    Arc::clone(&legacy_prompt_backtest_retry_hits);
                move || {
                    let legacy_prompt_backtest_retry_hits =
                        Arc::clone(&legacy_prompt_backtest_retry_hits);
                    async move {
                        legacy_prompt_backtest_retry_hits.fetch_add(1, Ordering::SeqCst);
                        Json(json!({ "source": "legacy" }))
                    }
                }
            }),
        );
        let upstream_addr = spawn_test_legacy_server(upstream).await;
        let router = build_router(test_config_for_legacy_http(upstream_addr));

        let response = router
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/api/prompt-backtest/tasks/not-an-int/retry")
                    .body(Body::empty())
                    .expect("invalid prompt-backtest retry request should be valid"),
            )
            .await
            .expect("router should answer invalid prompt-backtest retry request");

        assert_eq!(response.status(), StatusCode::BAD_REQUEST);
        let body = to_bytes(response.into_body(), usize::MAX)
            .await
            .expect("invalid prompt-backtest retry response body should be readable");
        let payload: Value = serde_json::from_slice(&body)
            .expect("invalid prompt-backtest retry response should be json");
        assert_eq!(
            payload["detail"],
            json!("task_id path parameter must be a valid integer")
        );
        assert_eq!(legacy_prompt_backtest_retry_hits.load(Ordering::SeqCst), 0);
    }

    #[tokio::test]
    async fn prompt_backtest_task_retry_route_rejects_put_without_proxying() {
        let legacy_prompt_backtest_retry_hits = Arc::new(AtomicUsize::new(0));
        let upstream = Router::new().route(
            "/api/prompt-backtest/tasks/{task_id}/retry",
            post({
                let legacy_prompt_backtest_retry_hits =
                    Arc::clone(&legacy_prompt_backtest_retry_hits);
                move || {
                    let legacy_prompt_backtest_retry_hits =
                        Arc::clone(&legacy_prompt_backtest_retry_hits);
                    async move {
                        legacy_prompt_backtest_retry_hits.fetch_add(1, Ordering::SeqCst);
                        Json(json!({ "source": "legacy" }))
                    }
                }
            }),
        );
        let upstream_addr = spawn_test_legacy_server(upstream).await;
        let router = build_router(test_config_for_legacy_http(upstream_addr));

        let response = router
            .oneshot(
                Request::builder()
                    .method("PUT")
                    .uri("/api/prompt-backtest/tasks/601/retry")
                    .body(Body::empty())
                    .expect("PUT prompt-backtest retry request should be valid"),
            )
            .await
            .expect("router should answer PUT prompt-backtest retry request");

        assert_eq!(response.status(), StatusCode::METHOD_NOT_ALLOWED);
        assert_eq!(legacy_prompt_backtest_retry_hits.load(Ordering::SeqCst), 0);
    }

    #[tokio::test]
    async fn kline_backfill_route_forwards_legacy_contract_through_native_handler() {
        let legacy_kline_backfill_hits = Arc::new(AtomicUsize::new(0));
        let upstream = Router::new().route(
            "/api/klines/backfill",
            post({
                let legacy_kline_backfill_hits = Arc::clone(&legacy_kline_backfill_hits);
                move |axum::extract::Json(payload): axum::extract::Json<Value>| {
                    let legacy_kline_backfill_hits = Arc::clone(&legacy_kline_backfill_hits);
                    async move {
                        legacy_kline_backfill_hits.fetch_add(1, Ordering::SeqCst);
                        assert_eq!(payload["exchange"], json!("hyperliquid"));
                        assert_eq!(payload["symbols"], json!(["BTC", "ETH"]));
                        assert_eq!(payload["period"], json!("1m"));
                        assert_eq!(payload["start_time"], json!("2026-04-01T00:00:00"));
                        assert_eq!(payload["end_time"], json!("2026-04-02T00:00:00"));

                        Json(json!({
                            "message": "Created 2 backfill tasks",
                            "task_ids": [301, 302],
                            "skipped_symbols": [],
                            "exchange": "hyperliquid",
                            "symbols": ["BTC", "ETH"],
                            "time_range": "2026-04-01T00:00:00 to 2026-04-02T00:00:00"
                        }))
                    }
                }
            }),
        );
        let upstream_addr = spawn_test_legacy_server(upstream).await;
        let router = build_router(test_config_for_legacy_http(upstream_addr));

        let response = router
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/api/klines/backfill")
                    .header(header::CONTENT_TYPE, "application/json")
                    .body(Body::from(
                        json!({
                            "exchange": "hyperliquid",
                            "symbols": ["BTC", "ETH"],
                            "start_time": "2026-04-01T00:00:00",
                            "end_time": "2026-04-02T00:00:00",
                            "period": "1m"
                        })
                        .to_string(),
                    ))
                    .expect("kline backfill request should be valid"),
            )
            .await
            .expect("router should answer kline backfill request");

        assert_eq!(response.status(), StatusCode::OK);
        let body = to_bytes(response.into_body(), usize::MAX)
            .await
            .expect("kline backfill response body should be readable");
        let payload: Value =
            serde_json::from_slice(&body).expect("kline backfill response should be json");
        assert_eq!(payload["message"], json!("Created 2 backfill tasks"));
        assert_eq!(payload["task_ids"], json!([301, 302]));
        assert_eq!(legacy_kline_backfill_hits.load(Ordering::SeqCst), 1);
    }

    #[tokio::test]
    async fn kline_backfill_route_validates_payload_without_proxying() {
        let legacy_kline_backfill_hits = Arc::new(AtomicUsize::new(0));
        let upstream = Router::new().route(
            "/api/klines/backfill",
            post({
                let legacy_kline_backfill_hits = Arc::clone(&legacy_kline_backfill_hits);
                move || {
                    let legacy_kline_backfill_hits = Arc::clone(&legacy_kline_backfill_hits);
                    async move {
                        legacy_kline_backfill_hits.fetch_add(1, Ordering::SeqCst);
                        Json(json!({"source": "legacy"}))
                    }
                }
            }),
        );
        let upstream_addr = spawn_test_legacy_server(upstream).await;
        let router = build_router(test_config_for_legacy_http(upstream_addr));

        let response = router
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/api/klines/backfill")
                    .header(header::CONTENT_TYPE, "application/json")
                    .body(Body::from(
                        json!({
                            "symbols": [],
                            "start_time": "2026-04-01T00:00:00",
                            "end_time": "2026-04-02T00:00:00",
                            "period": "1m"
                        })
                        .to_string(),
                    ))
                    .expect("invalid kline backfill request should be valid"),
            )
            .await
            .expect("router should answer invalid kline backfill request");

        assert_eq!(response.status(), StatusCode::BAD_REQUEST);
        let body = to_bytes(response.into_body(), usize::MAX)
            .await
            .expect("invalid kline backfill response body should be readable");
        let payload: Value =
            serde_json::from_slice(&body).expect("invalid kline backfill response should be json");
        assert_eq!(
            payload["detail"],
            json!("symbols must contain at least one symbol")
        );
        assert_eq!(legacy_kline_backfill_hits.load(Ordering::SeqCst), 0);
    }

    #[tokio::test]
    async fn kline_backfill_route_rejects_get_without_proxying() {
        let legacy_kline_backfill_hits = Arc::new(AtomicUsize::new(0));
        let upstream = Router::new().route(
            "/api/klines/backfill",
            post({
                let legacy_kline_backfill_hits = Arc::clone(&legacy_kline_backfill_hits);
                move || {
                    let legacy_kline_backfill_hits = Arc::clone(&legacy_kline_backfill_hits);
                    async move {
                        legacy_kline_backfill_hits.fetch_add(1, Ordering::SeqCst);
                        Json(json!({"source": "legacy"}))
                    }
                }
            }),
        );
        let upstream_addr = spawn_test_legacy_server(upstream).await;
        let router = build_router(test_config_for_legacy_http(upstream_addr));

        let response = router
            .oneshot(
                Request::builder()
                    .method("GET")
                    .uri("/api/klines/backfill")
                    .body(Body::empty())
                    .expect("GET kline backfill request should be valid"),
            )
            .await
            .expect("router should answer GET kline backfill request");

        assert_eq!(response.status(), StatusCode::METHOD_NOT_ALLOWED);
        assert_eq!(legacy_kline_backfill_hits.load(Ordering::SeqCst), 0);
    }

    #[tokio::test]
    async fn kline_backfill_delete_route_forwards_legacy_contract_through_native_handler() {
        let legacy_kline_backfill_delete_hits = Arc::new(AtomicUsize::new(0));
        let upstream = Router::new().route(
            "/api/klines/backfill-tasks/{task_id}",
            delete({
                let legacy_kline_backfill_delete_hits =
                    Arc::clone(&legacy_kline_backfill_delete_hits);
                move |axum::extract::Path(task_id): axum::extract::Path<String>| {
                    let legacy_kline_backfill_delete_hits =
                        Arc::clone(&legacy_kline_backfill_delete_hits);
                    async move {
                        legacy_kline_backfill_delete_hits.fetch_add(1, Ordering::SeqCst);
                        assert_eq!(task_id, "901");

                        Json(json!({
                            "message": "Task 901 deleted successfully"
                        }))
                    }
                }
            }),
        );
        let upstream_addr = spawn_test_legacy_server(upstream).await;
        let router = build_router(test_config_for_legacy_http(upstream_addr));

        let response = router
            .oneshot(
                Request::builder()
                    .method("DELETE")
                    .uri("/api/klines/backfill-tasks/901")
                    .body(Body::empty())
                    .expect("kline backfill delete request should be valid"),
            )
            .await
            .expect("router should answer kline backfill delete request");

        assert_eq!(response.status(), StatusCode::OK);
        let body = to_bytes(response.into_body(), usize::MAX)
            .await
            .expect("kline backfill delete response body should be readable");
        let payload: Value =
            serde_json::from_slice(&body).expect("kline backfill delete response should be json");
        assert_eq!(payload["message"], json!("Task 901 deleted successfully"));
        assert_eq!(legacy_kline_backfill_delete_hits.load(Ordering::SeqCst), 1);
    }

    #[tokio::test]
    async fn kline_backfill_delete_route_validates_path_without_proxying() {
        let legacy_kline_backfill_delete_hits = Arc::new(AtomicUsize::new(0));
        let upstream = Router::new().route(
            "/api/klines/backfill-tasks/{task_id}",
            delete({
                let legacy_kline_backfill_delete_hits =
                    Arc::clone(&legacy_kline_backfill_delete_hits);
                move || {
                    let legacy_kline_backfill_delete_hits =
                        Arc::clone(&legacy_kline_backfill_delete_hits);
                    async move {
                        legacy_kline_backfill_delete_hits.fetch_add(1, Ordering::SeqCst);
                        Json(json!({"source": "legacy"}))
                    }
                }
            }),
        );
        let upstream_addr = spawn_test_legacy_server(upstream).await;
        let router = build_router(test_config_for_legacy_http(upstream_addr));

        let response = router
            .oneshot(
                Request::builder()
                    .method("DELETE")
                    .uri("/api/klines/backfill-tasks/not-an-int")
                    .body(Body::empty())
                    .expect("invalid kline backfill delete request should be valid"),
            )
            .await
            .expect("router should answer invalid kline backfill delete request");

        assert_eq!(response.status(), StatusCode::BAD_REQUEST);
        let body = to_bytes(response.into_body(), usize::MAX)
            .await
            .expect("invalid kline backfill delete response body should be readable");
        let payload: Value = serde_json::from_slice(&body)
            .expect("invalid kline backfill delete response should be json");
        assert_eq!(
            payload["detail"],
            json!("task_id path parameter must be a valid integer")
        );
        assert_eq!(legacy_kline_backfill_delete_hits.load(Ordering::SeqCst), 0);
    }

    #[tokio::test]
    async fn kline_backfill_delete_route_rejects_get_without_proxying() {
        let legacy_kline_backfill_delete_hits = Arc::new(AtomicUsize::new(0));
        let upstream = Router::new().route(
            "/api/klines/backfill-tasks/{task_id}",
            delete({
                let legacy_kline_backfill_delete_hits =
                    Arc::clone(&legacy_kline_backfill_delete_hits);
                move || {
                    let legacy_kline_backfill_delete_hits =
                        Arc::clone(&legacy_kline_backfill_delete_hits);
                    async move {
                        legacy_kline_backfill_delete_hits.fetch_add(1, Ordering::SeqCst);
                        Json(json!({"source": "legacy"}))
                    }
                }
            }),
        );
        let upstream_addr = spawn_test_legacy_server(upstream).await;
        let router = build_router(test_config_for_legacy_http(upstream_addr));

        let response = router
            .oneshot(
                Request::builder()
                    .method("GET")
                    .uri("/api/klines/backfill-tasks/901")
                    .body(Body::empty())
                    .expect("GET kline backfill delete request should be valid"),
            )
            .await
            .expect("router should answer GET kline backfill delete request");

        assert_eq!(response.status(), StatusCode::METHOD_NOT_ALLOWED);
        assert_eq!(legacy_kline_backfill_delete_hits.load(Ordering::SeqCst), 0);
    }

    #[tokio::test]
    async fn orders_execute_route_forwards_legacy_contract_through_native_handler() {
        let legacy_order_execute_hits = Arc::new(AtomicUsize::new(0));
        let upstream = Router::new().route(
            "/api/orders/execute/{order_id}",
            post({
                let legacy_order_execute_hits = Arc::clone(&legacy_order_execute_hits);
                move |axum::extract::Path(order_id): axum::extract::Path<String>| {
                    let legacy_order_execute_hits = Arc::clone(&legacy_order_execute_hits);
                    async move {
                        legacy_order_execute_hits.fetch_add(1, Ordering::SeqCst);
                        assert_eq!(order_id, "3001");

                        Json(json!({
                            "success": true,
                            "order_id": 3001,
                            "executed": true,
                            "message": "Order executed successfully"
                        }))
                    }
                }
            }),
        );
        let upstream_addr = spawn_test_legacy_server(upstream).await;
        let router = build_router(test_config_for_legacy_http(upstream_addr));

        let response = router
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/api/orders/execute/3001")
                    .body(Body::empty())
                    .expect("order-execute request should be valid"),
            )
            .await
            .expect("router should answer order-execute request");

        assert_eq!(response.status(), StatusCode::OK);
        let body = to_bytes(response.into_body(), usize::MAX)
            .await
            .expect("order-execute response body should be readable");
        let payload: Value =
            serde_json::from_slice(&body).expect("order-execute response should be json");
        assert_eq!(payload["success"], json!(true));
        assert_eq!(payload["order_id"], json!(3001));
        assert_eq!(payload["executed"], json!(true));
        assert_eq!(payload["message"], json!("Order executed successfully"));
        assert_eq!(legacy_order_execute_hits.load(Ordering::SeqCst), 1);
    }

    #[tokio::test]
    async fn orders_execute_route_validates_path_without_proxying() {
        let legacy_order_execute_hits = Arc::new(AtomicUsize::new(0));
        let upstream = Router::new().route(
            "/api/orders/execute/{order_id}",
            post({
                let legacy_order_execute_hits = Arc::clone(&legacy_order_execute_hits);
                move || {
                    let legacy_order_execute_hits = Arc::clone(&legacy_order_execute_hits);
                    async move {
                        legacy_order_execute_hits.fetch_add(1, Ordering::SeqCst);
                        Json(json!({"source": "legacy"}))
                    }
                }
            }),
        );
        let upstream_addr = spawn_test_legacy_server(upstream).await;
        let router = build_router(test_config_for_legacy_http(upstream_addr));

        let invalid_order_id_response = router
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/api/orders/execute/not-an-int")
                    .body(Body::empty())
                    .expect("invalid order-execute request should be valid"),
            )
            .await
            .expect("router should answer invalid order-execute request");

        assert_eq!(
            invalid_order_id_response.status(),
            StatusCode::UNPROCESSABLE_ENTITY
        );
        let body = to_bytes(invalid_order_id_response.into_body(), usize::MAX)
            .await
            .expect("invalid order-execute response body should be readable");
        let payload: Value =
            serde_json::from_slice(&body).expect("invalid order-execute response should be json");
        assert_eq!(
            payload["detail"],
            json!("order_id path parameter must be a valid integer")
        );
        assert_eq!(legacy_order_execute_hits.load(Ordering::SeqCst), 0);
    }

    #[tokio::test]
    async fn orders_cancel_route_forwards_legacy_contract_through_native_handler() {
        let legacy_order_cancel_hits = Arc::new(AtomicUsize::new(0));
        let upstream = Router::new().route(
            "/api/orders/cancel/{order_id}",
            post({
                let legacy_order_cancel_hits = Arc::clone(&legacy_order_cancel_hits);
                move |axum::extract::Path(order_id): axum::extract::Path<String>,
                      axum::extract::Query(params): axum::extract::Query<
                    std::collections::HashMap<String, String>,
                >| {
                    let legacy_order_cancel_hits = Arc::clone(&legacy_order_cancel_hits);
                    async move {
                        legacy_order_cancel_hits.fetch_add(1, Ordering::SeqCst);
                        assert_eq!(order_id, "3002");
                        assert_eq!(
                            params.get("reason").map(String::as_str),
                            Some("User cancelled")
                        );

                        Json(json!({
                            "message": "Order cancelled successfully",
                            "order_id": 3002
                        }))
                    }
                }
            }),
        );
        let upstream_addr = spawn_test_legacy_server(upstream).await;
        let router = build_router(test_config_for_legacy_http(upstream_addr));

        let response = router
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/api/orders/cancel/3002")
                    .body(Body::empty())
                    .expect("order-cancel request should be valid"),
            )
            .await
            .expect("router should answer order-cancel request");

        assert_eq!(response.status(), StatusCode::OK);
        let body = to_bytes(response.into_body(), usize::MAX)
            .await
            .expect("order-cancel response body should be readable");
        let payload: Value =
            serde_json::from_slice(&body).expect("order-cancel response should be json");
        assert_eq!(payload["message"], json!("Order cancelled successfully"));
        assert_eq!(payload["order_id"], json!(3002));
        assert_eq!(legacy_order_cancel_hits.load(Ordering::SeqCst), 1);
    }

    #[tokio::test]
    async fn orders_cancel_route_validates_path_without_proxying() {
        let legacy_order_cancel_hits = Arc::new(AtomicUsize::new(0));
        let upstream = Router::new().route(
            "/api/orders/cancel/{order_id}",
            post({
                let legacy_order_cancel_hits = Arc::clone(&legacy_order_cancel_hits);
                move || {
                    let legacy_order_cancel_hits = Arc::clone(&legacy_order_cancel_hits);
                    async move {
                        legacy_order_cancel_hits.fetch_add(1, Ordering::SeqCst);
                        Json(json!({"source": "legacy"}))
                    }
                }
            }),
        );
        let upstream_addr = spawn_test_legacy_server(upstream).await;
        let router = build_router(test_config_for_legacy_http(upstream_addr));

        let invalid_order_id_response = router
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/api/orders/cancel/not-an-int")
                    .body(Body::empty())
                    .expect("invalid order-cancel request should be valid"),
            )
            .await
            .expect("router should answer invalid order-cancel request");

        assert_eq!(
            invalid_order_id_response.status(),
            StatusCode::UNPROCESSABLE_ENTITY
        );
        let body = to_bytes(invalid_order_id_response.into_body(), usize::MAX)
            .await
            .expect("invalid order-cancel response body should be readable");
        let payload: Value =
            serde_json::from_slice(&body).expect("invalid order-cancel response should be json");
        assert_eq!(
            payload["detail"],
            json!("order_id path parameter must be a valid integer")
        );
        assert_eq!(legacy_order_cancel_hits.load(Ordering::SeqCst), 0);
    }

    #[tokio::test]
    async fn orders_process_all_route_forwards_legacy_contract_through_native_handler() {
        let legacy_process_all_hits = Arc::new(AtomicUsize::new(0));
        let upstream = Router::new().route(
            "/api/orders/process-all",
            post({
                let legacy_process_all_hits = Arc::clone(&legacy_process_all_hits);
                move || {
                    let legacy_process_all_hits = Arc::clone(&legacy_process_all_hits);
                    async move {
                        legacy_process_all_hits.fetch_add(1, Ordering::SeqCst);
                        Json(json!({
                            "executed_count": 2,
                            "total_checked": 5,
                            "message": "Processing complete: Checked 5 orders, executed 2"
                        }))
                    }
                }
            }),
        );
        let upstream_addr = spawn_test_legacy_server(upstream).await;
        let router = build_router(test_config_for_legacy_http(upstream_addr));

        let response = router
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/api/orders/process-all")
                    .body(Body::empty())
                    .expect("process-all request should be valid"),
            )
            .await
            .expect("router should answer process-all request");

        assert_eq!(response.status(), StatusCode::OK);
        let body = to_bytes(response.into_body(), usize::MAX)
            .await
            .expect("process-all response body should be readable");
        let payload: Value =
            serde_json::from_slice(&body).expect("process-all response should be json");
        assert_eq!(payload["executed_count"], json!(2));
        assert_eq!(payload["total_checked"], json!(5));
        assert_eq!(
            payload["message"],
            json!("Processing complete: Checked 5 orders, executed 2")
        );
        assert_eq!(legacy_process_all_hits.load(Ordering::SeqCst), 1);
    }

    #[tokio::test]
    async fn orders_process_all_route_rejects_get_without_proxying() {
        let legacy_process_all_hits = Arc::new(AtomicUsize::new(0));
        let upstream = Router::new().route(
            "/api/orders/process-all",
            post({
                let legacy_process_all_hits = Arc::clone(&legacy_process_all_hits);
                move || {
                    let legacy_process_all_hits = Arc::clone(&legacy_process_all_hits);
                    async move {
                        legacy_process_all_hits.fetch_add(1, Ordering::SeqCst);
                        Json(json!({"source": "legacy"}))
                    }
                }
            }),
        );
        let upstream_addr = spawn_test_legacy_server(upstream).await;
        let router = build_router(test_config_for_legacy_http(upstream_addr));

        let response = router
            .oneshot(
                Request::builder()
                    .method("GET")
                    .uri("/api/orders/process-all")
                    .body(Body::empty())
                    .expect("GET process-all request should be valid"),
            )
            .await
            .expect("router should answer GET process-all request");

        assert_eq!(response.status(), StatusCode::METHOD_NOT_ALLOWED);
        assert_eq!(legacy_process_all_hits.load(Ordering::SeqCst), 0);
    }

    #[tokio::test]
    async fn program_validate_route_stays_on_rust_side_and_returns_validation_contract() {
        let router = build_router(AppConfig::for_tests());
        let response = router
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/api/programs/validate")
                    .header("content-type", "application/json")
                    .body(Body::from(
                        json!({
                            "code": "class MomentumStrategy:\n    def __init__(self):\n        self.ready = True\n\n    def should_trade(self, data):\n        return 'hold'\n"
                        })
                        .to_string(),
                    ))
                    .expect("validate request should be valid"),
            )
            .await
            .expect("router should answer validate request");

        assert_eq!(response.status(), StatusCode::OK);

        let body = to_bytes(response.into_body(), usize::MAX)
            .await
            .expect("validate response body should be readable");
        let payload: Value =
            serde_json::from_slice(&body).expect("validate response should be json");

        assert_eq!(payload["is_valid"], Value::Bool(true));
        assert_eq!(payload["errors"], json!([]));
        assert_eq!(payload["warnings"], json!([]));
    }

    #[tokio::test]
    async fn program_test_run_route_stays_on_rust_side_and_returns_success_contract() {
        let router = build_router(AppConfig::for_tests());
        let response = router
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/api/programs/test-run")
                    .header("content-type", "application/json")
                    .body(Body::from(
                        json!({
                            "code": "class MomentumStrategy:\n    def should_trade(self, data):\n        return Decision(operation='hold', symbol=data.trigger_symbol, reason='sandbox ok')\n",
                            "symbol": "BTC",
                            "period": "1h"
                        })
                        .to_string(),
                    ))
                    .expect("test-run request should be valid"),
            )
            .await
            .expect("router should answer test-run request");

        assert_eq!(response.status(), StatusCode::OK);

        let body = to_bytes(response.into_body(), usize::MAX)
            .await
            .expect("test-run response body should be readable");
        let payload: Value =
            serde_json::from_slice(&body).expect("test-run response should be json");

        assert_eq!(payload["success"], Value::Bool(true));
        assert_eq!(
            payload["decision"]["action"],
            Value::String("hold".to_owned())
        );
        assert_eq!(
            payload["decision"]["symbol"],
            Value::String("BTC".to_owned())
        );
        assert_eq!(
            payload["decision"]["reason"],
            Value::String("sandbox ok".to_owned())
        );
        assert_eq!(payload["error_type"], Value::Null);
    }

    #[tokio::test]
    async fn program_test_run_route_returns_structured_execution_failures() {
        let router = build_router(AppConfig::for_tests());
        let response = router
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/api/programs/test-run")
                    .header("content-type", "application/json")
                    .body(Body::from(
                        json!({
                            "code": "class BrokenStrategy:\n    def should_trade(self, data):\n        return missing_name\n",
                            "symbol": "BTC",
                            "period": "1h"
                        })
                        .to_string(),
                    ))
                    .expect("test-run request should be valid"),
            )
            .await
            .expect("router should answer test-run request");

        assert_eq!(response.status(), StatusCode::OK);

        let body = to_bytes(response.into_body(), usize::MAX)
            .await
            .expect("test-run response body should be readable");
        let payload: Value =
            serde_json::from_slice(&body).expect("test-run response should be json");

        assert_eq!(payload["success"], Value::Bool(false));
        assert_eq!(payload["error_type"], Value::String("NameError".to_owned()));
        assert_eq!(
            payload["error_message"],
            Value::String("name 'missing_name' is not defined".to_owned())
        );
        assert_eq!(payload["error_location"]["line"], json!(3));
        assert_eq!(
            payload["error_location"]["code_context"],
            Value::String("return missing_name".to_owned())
        );
        assert!(
            payload["suggestions"]
                .as_array()
                .expect("suggestions should be an array")
                .iter()
                .any(|item| item
                    == &Value::String(
                        "Check if the variable/function is defined before use".to_owned()
                    ))
        );
    }

    #[tokio::test]
    async fn program_backtest_route_rejects_invalid_time_range_without_proxying() {
        let router = build_router(AppConfig::for_tests());
        let response = router
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/api/programs/backtest")
                    .header("content-type", "application/json")
                    .body(Body::from(
                        json!({
                            "binding_id": 1,
                            "start_time_ms": 2_000_000,
                            "end_time_ms": 2_000_000
                        })
                        .to_string(),
                    ))
                    .expect("backtest request should be valid"),
            )
            .await
            .expect("router should answer backtest request");

        assert_eq!(response.status(), StatusCode::BAD_REQUEST);

        let body = to_bytes(response.into_body(), usize::MAX)
            .await
            .expect("backtest error body should be readable");
        let payload: Value =
            serde_json::from_slice(&body).expect("backtest error response should be json");
        assert_eq!(
            payload["detail"],
            json!("End time must be after start time")
        );
    }

    #[tokio::test]
    async fn program_backtest_route_returns_not_found_for_missing_binding() {
        let router = build_router(local_db_test_config());
        let response = router
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/api/programs/backtest")
                    .header("content-type", "application/json")
                    .body(Body::from(
                        json!({
                            "binding_id": 2_147_483_000i32,
                            "start_time_ms": 1_700_000_000_000i64,
                            "end_time_ms": 1_700_003_600_000i64
                        })
                        .to_string(),
                    ))
                    .expect("backtest request should be valid"),
            )
            .await
            .expect("router should answer backtest request");

        assert_eq!(response.status(), StatusCode::NOT_FOUND);

        let body = to_bytes(response.into_body(), usize::MAX)
            .await
            .expect("backtest missing-binding body should be readable");
        let payload: Value = serde_json::from_slice(&body)
            .expect("backtest missing-binding response should be json");
        assert_eq!(payload["detail"], json!("Binding not found"));
    }

    #[tokio::test]
    async fn program_ai_chat_route_returns_background_task_contract_from_rust_handler() {
        let upstream = Router::new().route(
            "/api/programs/ai-chat",
            post(|Json(payload): Json<Value>| async move {
                assert_eq!(payload["message"], json!("make me safer"));
                assert_eq!(payload["account_id"], json!(7));
                assert_eq!(payload["conversation_id"], json!(12));
                assert_eq!(payload["program_id"], json!(34));
                assert_eq!(payload["use_background_task"], json!(true));
                Json(json!({"task_id": "program_123", "status": "started"}))
            }),
        );
        let upstream_addr = spawn_test_legacy_server(upstream).await;
        let router = build_router(test_config_for_legacy_http(upstream_addr));

        let response = router
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/api/programs/ai-chat")
                    .header("content-type", "application/json")
                    .body(Body::from(
                        json!({
                            "message": "make me safer",
                            "account_id": 7,
                            "conversation_id": 12,
                            "program_id": 34
                        })
                        .to_string(),
                    ))
                    .expect("ai-chat background request should be valid"),
            )
            .await
            .expect("router should answer ai-chat background request");

        assert_eq!(response.status(), StatusCode::OK);
        assert_eq!(
            response.headers().get(header::CONTENT_TYPE).unwrap(),
            "application/json"
        );

        let body = to_bytes(response.into_body(), usize::MAX)
            .await
            .expect("ai-chat background response body should be readable");
        let payload: Value =
            serde_json::from_slice(&body).expect("ai-chat background response should be json");
        assert_eq!(payload["task_id"], json!("program_123"));
        assert_eq!(payload["status"], json!("started"));
    }

    #[tokio::test]
    async fn program_ai_chat_route_preserves_sse_contract_from_rust_handler() {
        let upstream = Router::new().route(
            "/api/programs/ai-chat",
            post(|Json(payload): Json<Value>| async move {
                assert_eq!(payload["message"], json!("stream please"));
                assert_eq!(payload["account_id"], json!(9));
                assert_eq!(payload["use_background_task"], json!(false));

                (
                    [(header::CONTENT_TYPE, "text/event-stream")],
                    "event: conversation_created\n\
                     data: {\"conversation_id\":55}\n\n\
                     event: content\n\
                     data: {\"content\":\"hello from legacy\"}\n\n\
                     event: done\n\
                     data: {\"conversation_id\":55,\"content\":\"hello from legacy\"}\n\n",
                )
                    .into_response()
            }),
        );
        let upstream_addr = spawn_test_legacy_server(upstream).await;
        let router = build_router(test_config_for_legacy_http(upstream_addr));

        let response = router
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/api/programs/ai-chat")
                    .header("content-type", "application/json")
                    .body(Body::from(
                        json!({
                            "message": "stream please",
                            "account_id": 9,
                            "use_background_task": false
                        })
                        .to_string(),
                    ))
                    .expect("ai-chat sse request should be valid"),
            )
            .await
            .expect("router should answer ai-chat sse request");

        assert_eq!(response.status(), StatusCode::OK);
        assert_eq!(
            response.headers().get(header::CONTENT_TYPE).unwrap(),
            "text/event-stream"
        );

        let body = to_bytes(response.into_body(), usize::MAX)
            .await
            .expect("ai-chat sse response body should be readable");
        let text = String::from_utf8(body.to_vec()).expect("ai-chat sse body should be utf-8");
        assert!(text.contains("event: conversation_created"));
        assert!(text.contains("data: {\"conversation_id\":55}"));
        assert!(text.contains("event: content"));
        assert!(text.contains("hello from legacy"));
        assert!(text.contains("event: done"));
    }

    #[tokio::test]
    async fn signal_ai_chat_stream_route_returns_background_task_contract_from_rust_handler() {
        let upstream = Router::new().route(
            "/api/signals/ai-chat-stream",
            post(|Json(payload): Json<Value>| async move {
                assert_eq!(payload["account_id"], json!(17));
                assert_eq!(payload["user_message"], json!("generate momentum signal"));
                assert_eq!(payload["conversation_id"], json!(88));
                assert_eq!(payload["use_background_task"], json!(true));
                Json(json!({"task_id": "signal_123", "status": "started"}))
            }),
        );
        let upstream_addr = spawn_test_legacy_server(upstream).await;
        let router = build_router(test_config_for_legacy_http(upstream_addr));

        let response = router
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/api/signals/ai-chat-stream")
                    .header("content-type", "application/json")
                    .body(Body::from(
                        json!({
                            "accountId": 17,
                            "userMessage": "generate momentum signal",
                            "conversationId": 88
                        })
                        .to_string(),
                    ))
                    .expect("signal ai-chat-stream background request should be valid"),
            )
            .await
            .expect("router should answer signal ai-chat-stream background request");

        assert_eq!(response.status(), StatusCode::OK);
        assert_eq!(
            response.headers().get(header::CONTENT_TYPE).unwrap(),
            "application/json"
        );

        let body = to_bytes(response.into_body(), usize::MAX)
            .await
            .expect("signal ai-chat-stream background response body should be readable");
        let payload: Value = serde_json::from_slice(&body)
            .expect("signal ai-chat-stream background response should be json");
        assert_eq!(payload["task_id"], json!("signal_123"));
        assert_eq!(payload["status"], json!("started"));
    }

    #[tokio::test]
    async fn signal_ai_chat_stream_route_preserves_sse_contract_from_rust_handler() {
        let upstream = Router::new().route(
            "/api/signals/ai-chat-stream",
            post(|Json(payload): Json<Value>| async move {
                assert_eq!(payload["account_id"], json!(22));
                assert_eq!(payload["user_message"], json!("stream signal output"));
                assert_eq!(payload["conversation_id"], Value::Null);
                assert_eq!(payload["use_background_task"], json!(false));

                (
                    [(header::CONTENT_TYPE, "text/event-stream")],
                    "event: status\n\
                     data: {\"status\":\"starting\"}\n\n\
                     event: signal_config\n\
                     data: {\"metric\":\"cvd\"}\n\n\
                     event: done\n\
                     data: {\"conversation_id\":144}\n\n",
                )
                    .into_response()
            }),
        );
        let upstream_addr = spawn_test_legacy_server(upstream).await;
        let router = build_router(test_config_for_legacy_http(upstream_addr));

        let response = router
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/api/signals/ai-chat-stream")
                    .header("content-type", "application/json")
                    .body(Body::from(
                        json!({
                            "accountId": 22,
                            "userMessage": "stream signal output",
                            "useBackgroundTask": false
                        })
                        .to_string(),
                    ))
                    .expect("signal ai-chat-stream sse request should be valid"),
            )
            .await
            .expect("router should answer signal ai-chat-stream sse request");

        assert_eq!(response.status(), StatusCode::OK);
        assert_eq!(
            response.headers().get(header::CONTENT_TYPE).unwrap(),
            "text/event-stream"
        );

        let body = to_bytes(response.into_body(), usize::MAX)
            .await
            .expect("signal ai-chat-stream sse response body should be readable");
        let text =
            String::from_utf8(body.to_vec()).expect("signal ai-chat-stream sse body should utf-8");
        assert!(text.contains("event: status"));
        assert!(text.contains("event: signal_config"));
        assert!(text.contains("event: done"));
        assert!(text.contains("\"conversation_id\":144"));
    }

    #[tokio::test]
    async fn signal_ai_chat_stream_route_validates_request_without_proxying() {
        let legacy_ai_chat_hits = Arc::new(AtomicUsize::new(0));
        let upstream = Router::new().route(
            "/api/signals/ai-chat-stream",
            post({
                let legacy_ai_chat_hits = Arc::clone(&legacy_ai_chat_hits);
                move || {
                    let legacy_ai_chat_hits = Arc::clone(&legacy_ai_chat_hits);
                    async move {
                        legacy_ai_chat_hits.fetch_add(1, Ordering::SeqCst);
                        Json(json!({"source": "legacy"}))
                    }
                }
            }),
        );
        let upstream_addr = spawn_test_legacy_server(upstream).await;
        let router = build_router(test_config_for_legacy_http(upstream_addr));

        let response = router
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/api/signals/ai-chat-stream")
                    .header("content-type", "application/json")
                    .body(Body::from(
                        json!({
                            "userMessage": "missing account"
                        })
                        .to_string(),
                    ))
                    .expect("invalid signal ai-chat-stream request should be valid"),
            )
            .await
            .expect("router should answer invalid signal ai-chat-stream request");

        assert_eq!(response.status(), StatusCode::UNPROCESSABLE_ENTITY);
        assert_eq!(legacy_ai_chat_hits.load(Ordering::SeqCst), 0);
    }

    #[tokio::test]
    async fn signal_backtest_route_forwards_legacy_contract_through_native_handler() {
        let legacy_backtest_hits = Arc::new(AtomicUsize::new(0));
        let upstream = Router::new().route(
            "/api/signals/backtest/{signal_id}",
            get({
                let legacy_backtest_hits = Arc::clone(&legacy_backtest_hits);
                move |axum::extract::Path(signal_id): axum::extract::Path<String>,
                      axum::extract::Query(query): axum::extract::Query<
                    std::collections::HashMap<String, String>,
                >| {
                    let legacy_backtest_hits = Arc::clone(&legacy_backtest_hits);
                    async move {
                        legacy_backtest_hits.fetch_add(1, Ordering::SeqCst);
                        assert_eq!(signal_id, "42");
                        assert_eq!(query.get("symbol").map(String::as_str), Some("BTC"));
                        assert_eq!(
                            query.get("kline_min_ts").map(String::as_str),
                            Some("1700000000000")
                        );
                        assert_eq!(
                            query.get("kline_max_ts").map(String::as_str),
                            Some("1700000009999")
                        );

                        Json(json!({
                            "signal_id": 42,
                            "signal_name": "Legacy Signal",
                            "symbol": "BTC",
                            "time_window": "5m",
                            "condition": {"metric": "cvd", "operator": ">", "threshold": 12},
                            "trigger_count": 1,
                            "triggers": [{
                                "timestamp": 1700000005000_i64,
                                "value": 25.5_f64,
                                "threshold": 12,
                                "operator": ">"
                            }]
                        }))
                    }
                }
            }),
        );
        let upstream_addr = spawn_test_legacy_server(upstream).await;
        let router = build_router(test_config_for_legacy_http(upstream_addr));

        let response = router
            .oneshot(
                Request::builder()
                    .uri("/api/signals/backtest/42?symbol=BTC&kline_min_ts=1700000000000&kline_max_ts=1700000009999")
                    .body(Body::empty())
                    .expect("signal backtest request should be valid"),
            )
            .await
            .expect("router should answer signal backtest request");

        assert_eq!(response.status(), StatusCode::OK);
        let body = to_bytes(response.into_body(), usize::MAX)
            .await
            .expect("signal backtest response body should be readable");
        let payload: Value =
            serde_json::from_slice(&body).expect("signal backtest response should be json");

        assert_eq!(payload["signal_id"], json!(42));
        assert_eq!(payload["symbol"], json!("BTC"));
        assert_eq!(payload["condition"]["metric"], json!("cvd"));
        assert_eq!(payload["trigger_count"], json!(1));
        assert_eq!(legacy_backtest_hits.load(Ordering::SeqCst), 1);
    }

    #[tokio::test]
    async fn signal_backtest_route_validates_path_and_query_without_proxying() {
        let legacy_backtest_hits = Arc::new(AtomicUsize::new(0));
        let upstream = Router::new().route(
            "/api/signals/backtest/{signal_id}",
            get({
                let legacy_backtest_hits = Arc::clone(&legacy_backtest_hits);
                move || {
                    let legacy_backtest_hits = Arc::clone(&legacy_backtest_hits);
                    async move {
                        legacy_backtest_hits.fetch_add(1, Ordering::SeqCst);
                        Json(json!({"source": "legacy"}))
                    }
                }
            }),
        );
        let upstream_addr = spawn_test_legacy_server(upstream).await;
        let router = build_router(test_config_for_legacy_http(upstream_addr));

        let invalid_id_response = router
            .clone()
            .oneshot(
                Request::builder()
                    .uri("/api/signals/backtest/not-an-int?symbol=BTC")
                    .body(Body::empty())
                    .expect("invalid signal_id request should be valid"),
            )
            .await
            .expect("router should answer invalid signal_id request");

        assert_eq!(
            invalid_id_response.status(),
            StatusCode::UNPROCESSABLE_ENTITY
        );
        let invalid_id_body = to_bytes(invalid_id_response.into_body(), usize::MAX)
            .await
            .expect("invalid signal_id response body should be readable");
        let invalid_id_payload: Value =
            serde_json::from_slice(&invalid_id_body).expect("invalid signal_id response json");
        assert_eq!(
            invalid_id_payload["detail"],
            json!("signal_id must be a valid integer")
        );

        let missing_symbol_response = router
            .oneshot(
                Request::builder()
                    .uri("/api/signals/backtest/42")
                    .body(Body::empty())
                    .expect("missing symbol request should be valid"),
            )
            .await
            .expect("router should answer missing symbol request");

        assert_eq!(
            missing_symbol_response.status(),
            StatusCode::UNPROCESSABLE_ENTITY
        );
        let missing_symbol_body = to_bytes(missing_symbol_response.into_body(), usize::MAX)
            .await
            .expect("missing symbol response body should be readable");
        let missing_symbol_payload: Value =
            serde_json::from_slice(&missing_symbol_body).expect("missing symbol response json");
        assert_eq!(
            missing_symbol_payload["detail"],
            json!("symbol query parameter is required")
        );

        assert_eq!(legacy_backtest_hits.load(Ordering::SeqCst), 0);
    }

    #[tokio::test]
    async fn signal_pool_backtest_route_forwards_legacy_contract_through_native_handler() {
        let legacy_pool_backtest_hits = Arc::new(AtomicUsize::new(0));
        let upstream = Router::new().route(
            "/api/signals/pool-backtest/{pool_id}",
            get({
                let legacy_pool_backtest_hits = Arc::clone(&legacy_pool_backtest_hits);
                move |axum::extract::Path(pool_id): axum::extract::Path<String>,
                      axum::extract::Query(query): axum::extract::Query<
                    std::collections::HashMap<String, String>,
                >| {
                    let legacy_pool_backtest_hits = Arc::clone(&legacy_pool_backtest_hits);
                    async move {
                        legacy_pool_backtest_hits.fetch_add(1, Ordering::SeqCst);
                        assert_eq!(pool_id, "7");
                        assert_eq!(query.get("symbol").map(String::as_str), Some("BTC"));
                        assert_eq!(
                            query.get("kline_min_ts").map(String::as_str),
                            Some("1700000000000")
                        );
                        assert_eq!(
                            query.get("kline_max_ts").map(String::as_str),
                            Some("1700000009999")
                        );

                        Json(json!({
                            "pool_id": 7,
                            "pool_name": "Legacy Pool",
                            "symbol": "BTC",
                            "logic": "OR",
                            "trigger_count": 2,
                            "triggers": [
                                {"timestamp": 1700000005000_i64, "signal_id": 3, "condition_met": true},
                                {"timestamp": 1700000007000_i64, "signal_id": 4, "condition_met": true}
                            ]
                        }))
                    }
                }
            }),
        );
        let upstream_addr = spawn_test_legacy_server(upstream).await;
        let router = build_router(test_config_for_legacy_http(upstream_addr));

        let response = router
            .oneshot(
                Request::builder()
                    .uri("/api/signals/pool-backtest/7?symbol=BTC&kline_min_ts=1700000000000&kline_max_ts=1700000009999")
                    .body(Body::empty())
                    .expect("signal pool backtest request should be valid"),
            )
            .await
            .expect("router should answer signal pool backtest request");

        assert_eq!(response.status(), StatusCode::OK);
        let body = to_bytes(response.into_body(), usize::MAX)
            .await
            .expect("signal pool backtest response body should be readable");
        let payload: Value =
            serde_json::from_slice(&body).expect("signal pool backtest response should be json");

        assert_eq!(payload["pool_id"], json!(7));
        assert_eq!(payload["symbol"], json!("BTC"));
        assert_eq!(payload["logic"], json!("OR"));
        assert_eq!(payload["trigger_count"], json!(2));
        assert_eq!(legacy_pool_backtest_hits.load(Ordering::SeqCst), 1);
    }

    #[tokio::test]
    async fn signal_pool_backtest_route_validates_path_and_query_without_proxying() {
        let legacy_pool_backtest_hits = Arc::new(AtomicUsize::new(0));
        let upstream = Router::new().route(
            "/api/signals/pool-backtest/{pool_id}",
            get({
                let legacy_pool_backtest_hits = Arc::clone(&legacy_pool_backtest_hits);
                move || {
                    let legacy_pool_backtest_hits = Arc::clone(&legacy_pool_backtest_hits);
                    async move {
                        legacy_pool_backtest_hits.fetch_add(1, Ordering::SeqCst);
                        Json(json!({"source": "legacy"}))
                    }
                }
            }),
        );
        let upstream_addr = spawn_test_legacy_server(upstream).await;
        let router = build_router(test_config_for_legacy_http(upstream_addr));

        let invalid_id_response = router
            .clone()
            .oneshot(
                Request::builder()
                    .uri("/api/signals/pool-backtest/not-an-int?symbol=BTC")
                    .body(Body::empty())
                    .expect("invalid pool_id request should be valid"),
            )
            .await
            .expect("router should answer invalid pool_id request");

        assert_eq!(
            invalid_id_response.status(),
            StatusCode::UNPROCESSABLE_ENTITY
        );
        let invalid_id_body = to_bytes(invalid_id_response.into_body(), usize::MAX)
            .await
            .expect("invalid pool_id response body should be readable");
        let invalid_id_payload: Value =
            serde_json::from_slice(&invalid_id_body).expect("invalid pool_id response json");
        assert_eq!(
            invalid_id_payload["detail"],
            json!("pool_id must be a valid integer")
        );

        let missing_symbol_response = router
            .oneshot(
                Request::builder()
                    .uri("/api/signals/pool-backtest/7")
                    .body(Body::empty())
                    .expect("missing symbol request should be valid"),
            )
            .await
            .expect("router should answer missing symbol request");

        assert_eq!(
            missing_symbol_response.status(),
            StatusCode::UNPROCESSABLE_ENTITY
        );
        let missing_symbol_body = to_bytes(missing_symbol_response.into_body(), usize::MAX)
            .await
            .expect("missing symbol response body should be readable");
        let missing_symbol_payload: Value =
            serde_json::from_slice(&missing_symbol_body).expect("missing symbol response json");
        assert_eq!(
            missing_symbol_payload["detail"],
            json!("symbol query parameter is required")
        );

        assert_eq!(legacy_pool_backtest_hits.load(Ordering::SeqCst), 0);
    }

    #[tokio::test]
    async fn signal_test_route_forwards_legacy_contract_through_native_handler() {
        let legacy_signal_test_hits = Arc::new(AtomicUsize::new(0));
        let upstream = Router::new().route(
            "/api/signals/test/{signal_id}",
            get({
                let legacy_signal_test_hits = Arc::clone(&legacy_signal_test_hits);
                move |axum::extract::Path(signal_id): axum::extract::Path<String>,
                      axum::extract::Query(query): axum::extract::Query<
                    std::collections::HashMap<String, String>,
                >| {
                    let legacy_signal_test_hits = Arc::clone(&legacy_signal_test_hits);
                    async move {
                        legacy_signal_test_hits.fetch_add(1, Ordering::SeqCst);
                        assert_eq!(signal_id, "11");
                        assert_eq!(query.get("symbol").map(String::as_str), Some("BTC"));

                        Json(json!({
                            "signal_id": 11,
                            "signal_name": "Legacy Signal",
                            "symbol": "BTC",
                            "metric": "cvd",
                            "operator": ">",
                            "threshold": 12.0_f64,
                            "time_window": 60,
                            "current_value": 15.4_f64,
                            "condition_met": true,
                            "is_active": false,
                            "would_trigger": true,
                            "market_data_available": true
                        }))
                    }
                }
            }),
        );
        let upstream_addr = spawn_test_legacy_server(upstream).await;
        let router = build_router(test_config_for_legacy_http(upstream_addr));

        let response = router
            .oneshot(
                Request::builder()
                    .uri("/api/signals/test/11?symbol=BTC")
                    .body(Body::empty())
                    .expect("signal test request should be valid"),
            )
            .await
            .expect("router should answer signal test request");

        assert_eq!(response.status(), StatusCode::OK);
        let body = to_bytes(response.into_body(), usize::MAX)
            .await
            .expect("signal test response body should be readable");
        let payload: Value =
            serde_json::from_slice(&body).expect("signal test response should be json");

        assert_eq!(payload["signal_id"], json!(11));
        assert_eq!(payload["symbol"], json!("BTC"));
        assert_eq!(payload["metric"], json!("cvd"));
        assert_eq!(payload["condition_met"], json!(true));
        assert_eq!(legacy_signal_test_hits.load(Ordering::SeqCst), 1);
    }

    #[tokio::test]
    async fn signal_test_route_validates_path_and_query_without_proxying() {
        let legacy_signal_test_hits = Arc::new(AtomicUsize::new(0));
        let upstream = Router::new().route(
            "/api/signals/test/{signal_id}",
            get({
                let legacy_signal_test_hits = Arc::clone(&legacy_signal_test_hits);
                move || {
                    let legacy_signal_test_hits = Arc::clone(&legacy_signal_test_hits);
                    async move {
                        legacy_signal_test_hits.fetch_add(1, Ordering::SeqCst);
                        Json(json!({"source": "legacy"}))
                    }
                }
            }),
        );
        let upstream_addr = spawn_test_legacy_server(upstream).await;
        let router = build_router(test_config_for_legacy_http(upstream_addr));

        let invalid_id_response = router
            .clone()
            .oneshot(
                Request::builder()
                    .uri("/api/signals/test/not-an-int?symbol=BTC")
                    .body(Body::empty())
                    .expect("invalid signal test id request should be valid"),
            )
            .await
            .expect("router should answer invalid signal test id request");

        assert_eq!(
            invalid_id_response.status(),
            StatusCode::UNPROCESSABLE_ENTITY
        );
        let invalid_id_body = to_bytes(invalid_id_response.into_body(), usize::MAX)
            .await
            .expect("invalid signal test id response body should be readable");
        let invalid_id_payload: Value =
            serde_json::from_slice(&invalid_id_body).expect("invalid signal test id response json");
        assert_eq!(
            invalid_id_payload["detail"],
            json!("signal_id must be a valid integer")
        );

        let missing_symbol_response = router
            .oneshot(
                Request::builder()
                    .uri("/api/signals/test/11")
                    .body(Body::empty())
                    .expect("missing symbol signal test request should be valid"),
            )
            .await
            .expect("router should answer missing symbol signal test request");

        assert_eq!(
            missing_symbol_response.status(),
            StatusCode::UNPROCESSABLE_ENTITY
        );
        let missing_symbol_body = to_bytes(missing_symbol_response.into_body(), usize::MAX)
            .await
            .expect("missing symbol signal test response body should be readable");
        let missing_symbol_payload: Value = serde_json::from_slice(&missing_symbol_body)
            .expect("missing symbol signal test response json");
        assert_eq!(
            missing_symbol_payload["detail"],
            json!("symbol query parameter is required")
        );

        assert_eq!(legacy_signal_test_hits.load(Ordering::SeqCst), 0);
    }

    #[tokio::test]
    async fn signal_create_pool_from_config_route_forwards_legacy_contract_through_native_handler()
    {
        let legacy_create_pool_hits = Arc::new(AtomicUsize::new(0));
        let upstream = Router::new().route(
            "/api/signals/create-pool-from-config",
            post({
                let legacy_create_pool_hits = Arc::clone(&legacy_create_pool_hits);
                move |Json(payload): Json<Value>| {
                    let legacy_create_pool_hits = Arc::clone(&legacy_create_pool_hits);
                    async move {
                        legacy_create_pool_hits.fetch_add(1, Ordering::SeqCst);
                        assert_eq!(payload["name"], json!("Momentum Pool"));
                        assert_eq!(payload["symbol"], json!("BTC"));
                        assert_eq!(payload["logic"], json!("AND"));
                        assert_eq!(payload["exchange"], json!("hyperliquid"));
                        assert_eq!(payload["signals"][0]["metric"], json!("cvd"));
                        assert_eq!(payload["signals"][0]["operator"], json!(">"));
                        assert_eq!(payload["signals"][0]["threshold"], json!(12.0));
                        assert_eq!(payload["signals"][0]["time_window"], json!("5m"));

                        Json(json!({
                            "success": true,
                            "pool": {
                                "id": 77,
                                "pool_name": "Momentum Pool",
                                "signal_ids": [301],
                                "symbols": ["BTC"],
                                "logic": "AND",
                                "exchange": "hyperliquid",
                                "source_type": "market_signals",
                                "source_config": {}
                            },
                            "signals": [
                                {
                                    "id": 301,
                                    "signal_name": "Momentum Pool_1",
                                    "trigger_condition": {
                                        "metric": "cvd",
                                        "operator": ">",
                                        "threshold": 12.0,
                                        "time_window": "5m"
                                    },
                                    "exchange": "hyperliquid"
                                }
                            ]
                        }))
                    }
                }
            }),
        );
        let upstream_addr = spawn_test_legacy_server(upstream).await;
        let router = build_router(test_config_for_legacy_http(upstream_addr));

        let response = router
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/api/signals/create-pool-from-config")
                    .header("content-type", "application/json")
                    .body(Body::from(
                        json!({
                            "name": "Momentum Pool",
                            "symbol": "BTC",
                            "signals": [
                                {
                                    "metric": "cvd",
                                    "operator": ">",
                                    "threshold": 12.0,
                                    "time_window": "5m"
                                }
                            ]
                        })
                        .to_string(),
                    ))
                    .expect("create pool from config request should be valid"),
            )
            .await
            .expect("router should answer create pool from config request");

        assert_eq!(response.status(), StatusCode::OK);
        let body = to_bytes(response.into_body(), usize::MAX)
            .await
            .expect("create pool from config response body should be readable");
        let payload: Value =
            serde_json::from_slice(&body).expect("create pool from config response should be json");

        assert_eq!(payload["success"], json!(true));
        assert_eq!(payload["pool"]["id"], json!(77));
        assert_eq!(payload["signals"][0]["id"], json!(301));
        assert_eq!(legacy_create_pool_hits.load(Ordering::SeqCst), 1);
    }

    #[tokio::test]
    async fn signal_create_pool_from_config_route_validates_request_without_proxying() {
        let legacy_create_pool_hits = Arc::new(AtomicUsize::new(0));
        let upstream = Router::new().route(
            "/api/signals/create-pool-from-config",
            post({
                let legacy_create_pool_hits = Arc::clone(&legacy_create_pool_hits);
                move || {
                    let legacy_create_pool_hits = Arc::clone(&legacy_create_pool_hits);
                    async move {
                        legacy_create_pool_hits.fetch_add(1, Ordering::SeqCst);
                        Json(json!({"source": "legacy"}))
                    }
                }
            }),
        );
        let upstream_addr = spawn_test_legacy_server(upstream).await;
        let router = build_router(test_config_for_legacy_http(upstream_addr));

        let empty_signals_response = router
            .clone()
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/api/signals/create-pool-from-config")
                    .header("content-type", "application/json")
                    .body(Body::from(
                        json!({
                            "name": "Momentum Pool",
                            "symbol": "BTC",
                            "signals": []
                        })
                        .to_string(),
                    ))
                    .expect("empty signals request should be valid"),
            )
            .await
            .expect("router should answer empty signals request");

        assert_eq!(empty_signals_response.status(), StatusCode::BAD_REQUEST);
        let empty_signals_body = to_bytes(empty_signals_response.into_body(), usize::MAX)
            .await
            .expect("empty signals response body should be readable");
        let empty_signals_payload: Value =
            serde_json::from_slice(&empty_signals_body).expect("empty signals response json");
        assert_eq!(
            empty_signals_payload["detail"],
            json!("No signals provided")
        );

        let missing_fields_response = router
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/api/signals/create-pool-from-config")
                    .header("content-type", "application/json")
                    .body(Body::from(
                        json!({
                            "name": "Momentum Pool",
                            "symbol": "BTC",
                            "signals": [
                                { "metric": "cvd" }
                            ]
                        })
                        .to_string(),
                    ))
                    .expect("missing fields request should be valid"),
            )
            .await
            .expect("router should answer missing fields request");

        assert_eq!(missing_fields_response.status(), StatusCode::BAD_REQUEST);
        let missing_fields_body = to_bytes(missing_fields_response.into_body(), usize::MAX)
            .await
            .expect("missing fields response body should be readable");
        let missing_fields_payload: Value =
            serde_json::from_slice(&missing_fields_body).expect("missing fields response json");
        assert_eq!(
            missing_fields_payload["detail"],
            json!("Signal 1 missing required fields (metric, operator, threshold, time_window)")
        );

        assert_eq!(legacy_create_pool_hits.load(Ordering::SeqCst), 0);
    }

    #[tokio::test]
    async fn signal_backtest_preview_route_forwards_legacy_contract_through_native_handler() {
        let legacy_preview_hits = Arc::new(AtomicUsize::new(0));
        let upstream = Router::new().route(
            "/api/signals/backtest-preview",
            post({
                let legacy_preview_hits = Arc::clone(&legacy_preview_hits);
                move |Json(payload): Json<Value>| {
                    let legacy_preview_hits = Arc::clone(&legacy_preview_hits);
                    async move {
                        legacy_preview_hits.fetch_add(1, Ordering::SeqCst);
                        assert_eq!(payload["symbol"], json!("BTC"));
                        assert_eq!(payload["exchange"], json!("hyperliquid"));
                        assert_eq!(payload["trigger_condition"]["metric"], json!("cvd"));
                        assert_eq!(payload["trigger_condition"]["operator"], json!(">"));
                        assert_eq!(payload["trigger_condition"]["threshold"], json!(12.0));
                        assert_eq!(payload["kline_min_ts"], json!(1700000000000_i64));
                        assert_eq!(payload["kline_max_ts"], json!(1700000009999_i64));

                        Json(json!({
                            "signal_id": Value::Null,
                            "signal_name": "Temporary Preview",
                            "symbol": "BTC",
                            "time_window": "5m",
                            "condition": {
                                "metric": "cvd",
                                "operator": ">",
                                "threshold": 12.0
                            },
                            "trigger_count": 2,
                            "triggers": [
                                {"timestamp": 1700000003000_i64, "value": 13.2, "threshold": 12.0},
                                {"timestamp": 1700000006000_i64, "value": 15.4, "threshold": 12.0}
                            ]
                        }))
                    }
                }
            }),
        );
        let upstream_addr = spawn_test_legacy_server(upstream).await;
        let router = build_router(test_config_for_legacy_http(upstream_addr));

        let response = router
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/api/signals/backtest-preview")
                    .header("content-type", "application/json")
                    .body(Body::from(
                        json!({
                            "symbol": "BTC",
                            "triggerCondition": {
                                "metric": "cvd",
                                "operator": ">",
                                "threshold": 12.0,
                                "time_window": "5m"
                            },
                            "klineMinTs": 1700000000000_i64,
                            "klineMaxTs": 1700000009999_i64
                        })
                        .to_string(),
                    ))
                    .expect("signal backtest preview request should be valid"),
            )
            .await
            .expect("router should answer signal backtest preview request");

        assert_eq!(response.status(), StatusCode::OK);
        let body = to_bytes(response.into_body(), usize::MAX)
            .await
            .expect("signal backtest preview response body should be readable");
        let payload: Value =
            serde_json::from_slice(&body).expect("signal backtest preview response json");

        assert_eq!(payload["signal_id"], Value::Null);
        assert_eq!(payload["symbol"], json!("BTC"));
        assert_eq!(payload["condition"]["metric"], json!("cvd"));
        assert_eq!(payload["trigger_count"], json!(2));
        assert_eq!(legacy_preview_hits.load(Ordering::SeqCst), 1);
    }

    #[tokio::test]
    async fn signal_backtest_preview_route_validates_request_without_proxying() {
        let legacy_preview_hits = Arc::new(AtomicUsize::new(0));
        let upstream = Router::new().route(
            "/api/signals/backtest-preview",
            post({
                let legacy_preview_hits = Arc::clone(&legacy_preview_hits);
                move || {
                    let legacy_preview_hits = Arc::clone(&legacy_preview_hits);
                    async move {
                        legacy_preview_hits.fetch_add(1, Ordering::SeqCst);
                        Json(json!({"source": "legacy"}))
                    }
                }
            }),
        );
        let upstream_addr = spawn_test_legacy_server(upstream).await;
        let router = build_router(test_config_for_legacy_http(upstream_addr));

        let missing_trigger_response = router
            .clone()
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/api/signals/backtest-preview")
                    .header("content-type", "application/json")
                    .body(Body::from(json!({"symbol": "BTC"}).to_string()))
                    .expect("missing triggerCondition request should be valid"),
            )
            .await
            .expect("router should answer missing triggerCondition request");

        assert_eq!(
            missing_trigger_response.status(),
            StatusCode::UNPROCESSABLE_ENTITY
        );
        let missing_trigger_body = to_bytes(missing_trigger_response.into_body(), usize::MAX)
            .await
            .expect("missing triggerCondition response body should be readable");
        let missing_trigger_payload: Value = serde_json::from_slice(&missing_trigger_body)
            .expect("missing triggerCondition response should be json");
        assert_eq!(
            missing_trigger_payload["detail"],
            json!("triggerCondition (or trigger_condition) must be an object")
        );

        let invalid_ts_response = router
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/api/signals/backtest-preview")
                    .header("content-type", "application/json")
                    .body(Body::from(
                        json!({
                            "symbol": "BTC",
                            "triggerCondition": {"metric": "cvd"},
                            "klineMinTs": "bad-timestamp"
                        })
                        .to_string(),
                    ))
                    .expect("invalid klineMinTs request should be valid"),
            )
            .await
            .expect("router should answer invalid klineMinTs request");

        assert_eq!(
            invalid_ts_response.status(),
            StatusCode::UNPROCESSABLE_ENTITY
        );
        let invalid_ts_body = to_bytes(invalid_ts_response.into_body(), usize::MAX)
            .await
            .expect("invalid klineMinTs response body should be readable");
        let invalid_ts_payload: Value =
            serde_json::from_slice(&invalid_ts_body).expect("invalid klineMinTs response json");
        assert_eq!(
            invalid_ts_payload["detail"],
            json!("klineMinTs (or kline_min_ts) must be a valid integer")
        );

        assert_eq!(legacy_preview_hits.load(Ordering::SeqCst), 0);
    }

    #[tokio::test]
    async fn signal_analyze_route_is_native_and_returns_parity_stat_contract() {
        let pool = local_db_pool().await;
        let symbol = format!("S{}", &Uuid::new_v4().simple().to_string()[..10]).to_uppercase();
        let interval_ms = 5 * 60 * 1000;
        let now_ms = Utc::now().timestamp_millis();
        let base_ts = ((now_ms / interval_ms) - 4) * interval_ms;
        let legacy_analyze_hits = Arc::new(AtomicUsize::new(0));
        let upstream = Router::new().route(
            "/api/signals/analyze",
            get({
                let legacy_analyze_hits = Arc::clone(&legacy_analyze_hits);
                move || {
                    let legacy_analyze_hits = Arc::clone(&legacy_analyze_hits);
                    async move {
                        legacy_analyze_hits.fetch_add(1, Ordering::SeqCst);
                        Json(json!({"source": "legacy"}))
                    }
                }
            }),
        );

        for (offset, buy, sell) in [
            (0_i64, 1_200.0_f64, 200.0_f64),
            (1_i64, 1_500.0_f64, 300.0_f64),
            (2_i64, 900.0_f64, 100.0_f64),
            (3_i64, 1_800.0_f64, 400.0_f64),
        ] {
            sqlx::query(
                r#"
                INSERT INTO market_trades_aggregated (
                    exchange,
                    symbol,
                    timestamp,
                    taker_buy_volume,
                    taker_sell_volume,
                    taker_buy_count,
                    taker_sell_count,
                    taker_buy_notional,
                    taker_sell_notional
                )
                VALUES ($1, $2, $3, 0, 0, 0, 0, $4, $5)
                "#,
            )
            .bind("hyperliquid")
            .bind(&symbol)
            .bind(base_ts + offset * interval_ms)
            .bind(buy)
            .bind(sell)
            .execute(&pool)
            .await
            .expect("signal analyze trade fixture should insert");
        }

        let upstream_addr = spawn_test_legacy_server(upstream).await;
        let router = build_router(test_config_for_legacy_http(upstream_addr));
        let response = router
            .oneshot(
                Request::builder()
                    .uri(format!(
                        "/api/signals/analyze?symbol={symbol}&metric=cvd&period=5m&days=1&exchange=hyperliquid"
                    ))
                    .body(Body::empty())
                    .expect("signal analyze request should be valid"),
            )
            .await
            .expect("router should answer signal analyze request");

        assert_eq!(response.status(), StatusCode::OK);
        let body = to_bytes(response.into_body(), usize::MAX)
            .await
            .expect("signal analyze response body should be readable");
        let payload: Value =
            serde_json::from_slice(&body).expect("signal analyze response should be json");

        sqlx::query("DELETE FROM market_trades_aggregated WHERE exchange = $1 AND symbol = $2")
            .bind("hyperliquid")
            .bind(&symbol)
            .execute(&pool)
            .await
            .expect("signal analyze fixtures should clean up");

        assert_eq!(payload["status"], json!("ok"));
        assert_eq!(payload["symbol"], json!(symbol));
        assert_eq!(payload["metric"], json!("cvd"));
        assert_eq!(payload["period"], json!("5m"));
        assert!(
            payload["sample_count"]
                .as_i64()
                .is_some_and(|count| count >= 3)
        );
        assert!(
            payload["time_range_hours"]
                .as_f64()
                .is_some_and(|hours| hours > 0.0)
        );
        assert!(payload["statistics"]["mean"].is_number());
        assert!(payload["statistics"]["std"].is_number());
        assert!(payload["statistics"]["min"].is_number());
        assert!(payload["statistics"]["max"].is_number());
        assert!(payload["statistics"]["abs_percentiles"]["p75"].is_number());
        assert!(payload["statistics"]["abs_percentiles"]["p90"].is_number());
        assert!(payload["statistics"]["abs_percentiles"]["p95"].is_number());
        assert!(payload["statistics"]["abs_percentiles"]["p99"].is_number());
        assert_eq!(
            payload["suggestions"]["moderate"]["recommended"],
            json!(true)
        );
        assert_eq!(legacy_analyze_hits.load(Ordering::SeqCst), 0);
    }

    #[tokio::test]
    async fn signal_analyze_route_rejects_days_over_30_without_proxying() {
        let legacy_analyze_hits = Arc::new(AtomicUsize::new(0));
        let upstream = Router::new().route(
            "/api/signals/analyze",
            get({
                let legacy_analyze_hits = Arc::clone(&legacy_analyze_hits);
                move || {
                    let legacy_analyze_hits = Arc::clone(&legacy_analyze_hits);
                    async move {
                        legacy_analyze_hits.fetch_add(1, Ordering::SeqCst);
                        Json(json!({"source": "legacy"}))
                    }
                }
            }),
        );
        let upstream_addr = spawn_test_legacy_server(upstream).await;
        let router = build_router(test_config_for_legacy_http(upstream_addr));

        let response = router
            .oneshot(
                Request::builder()
                    .uri("/api/signals/analyze?symbol=BTC&metric=cvd&days=31")
                    .body(Body::empty())
                    .expect("signal analyze invalid-days request should be valid"),
            )
            .await
            .expect("router should answer signal analyze invalid-days request");

        assert_eq!(response.status(), StatusCode::BAD_REQUEST);
        let body = to_bytes(response.into_body(), usize::MAX)
            .await
            .expect("signal analyze invalid-days response body should be readable");
        let payload: Value =
            serde_json::from_slice(&body).expect("signal analyze invalid-days response json");
        assert_eq!(
            payload["detail"],
            json!("days must be less than or equal to 30")
        );
        assert_eq!(legacy_analyze_hits.load(Ordering::SeqCst), 0);
    }

    #[tokio::test]
    async fn signal_states_routes_are_native_with_default_contract_and_reset_semantics() {
        let legacy_states_hits = Arc::new(AtomicUsize::new(0));
        let legacy_reset_hits = Arc::new(AtomicUsize::new(0));
        let upstream = Router::new()
            .route(
                "/api/signals/states",
                get({
                    let legacy_states_hits = Arc::clone(&legacy_states_hits);
                    move || {
                        let legacy_states_hits = Arc::clone(&legacy_states_hits);
                        async move {
                            legacy_states_hits.fetch_add(1, Ordering::SeqCst);
                            Json(json!({"states": {"signal_states": {"legacy": true}}}))
                        }
                    }
                }),
            )
            .route(
                "/api/signals/states/reset",
                post({
                    let legacy_reset_hits = Arc::clone(&legacy_reset_hits);
                    move || {
                        let legacy_reset_hits = Arc::clone(&legacy_reset_hits);
                        async move {
                            legacy_reset_hits.fetch_add(1, Ordering::SeqCst);
                            Json(json!({"message": "legacy"}))
                        }
                    }
                }),
            );
        let upstream_addr = spawn_test_legacy_server(upstream).await;
        let router = build_router(test_config_for_legacy_http(upstream_addr));

        let states_response = router
            .clone()
            .oneshot(
                Request::builder()
                    .uri("/api/signals/states")
                    .body(Body::empty())
                    .expect("signal states request should be valid"),
            )
            .await
            .expect("router should answer signal states request");
        assert_eq!(states_response.status(), StatusCode::OK);
        let states_body = to_bytes(states_response.into_body(), usize::MAX)
            .await
            .expect("signal states response should be readable");
        let states_payload: Value =
            serde_json::from_slice(&states_body).expect("signal states response should be json");
        assert_eq!(states_payload["states"]["signal_states"], json!({}));
        assert_eq!(states_payload["states"]["pool_states"], json!({}));
        assert!(
            states_payload["cache_info"]["pools_count"]
                .as_i64()
                .is_some()
        );
        assert!(
            states_payload["cache_info"]["signals_count"]
                .as_i64()
                .is_some()
        );

        let reset_response = router
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/api/signals/states/reset?symbol=BTC")
                    .body(Body::empty())
                    .expect("signal states reset request should be valid"),
            )
            .await
            .expect("router should answer signal states reset request");
        assert_eq!(reset_response.status(), StatusCode::OK);
        let reset_body = to_bytes(reset_response.into_body(), usize::MAX)
            .await
            .expect("signal states reset response should be readable");
        let reset_payload: Value =
            serde_json::from_slice(&reset_body).expect("signal states reset response json");
        assert_eq!(
            reset_payload,
            json!({"message": "Signal and pool states reset successfully"})
        );

        assert_eq!(legacy_states_hits.load(Ordering::SeqCst), 0);
        assert_eq!(legacy_reset_hits.load(Ordering::SeqCst), 0);
    }

    #[tokio::test]
    async fn wallet_tracking_status_route_returns_native_snapshot_and_pool_count() {
        let _guard = wallet_runtime_test_lock().lock().await;
        reset_snapshot_for_tests().await;
        let pool = local_db_pool().await;
        let backup = backup_wallet_runtime_configs(&pool).await;
        reset_wallet_runtime_configs(&pool).await;
        let tag = Uuid::new_v4().simple().to_string();
        let wallet_pool_name = format!("wallet-status-{tag}");
        let disabled_wallet_pool_name = format!("wallet-status-disabled-{tag}");
        let market_pool_name = format!("market-status-{tag}");

        for (pool_name, enabled, source_type) in [
            (&wallet_pool_name, true, "wallet_tracking"),
            (&disabled_wallet_pool_name, false, "wallet_tracking"),
            (&market_pool_name, true, "market_signals"),
        ] {
            sqlx::query(
                r#"
                INSERT INTO signal_pools (
                    pool_name, signal_ids, symbols, enabled, logic, exchange, source_type, source_config, created_at
                )
                VALUES ($1, '[]', '[]', $2, 'OR', 'hyperliquid', $3, '{}', CURRENT_TIMESTAMP)
                "#,
            )
            .bind(pool_name)
            .bind(enabled)
            .bind(source_type)
            .execute(&pool)
            .await
            .expect("signal pool fixture should insert");
        }

        let router = build_router(local_db_test_config());
        let response = router
            .oneshot(
                Request::builder()
                    .uri("/api/signals/wallet-tracking/status")
                    .body(Body::empty())
                    .expect("wallet tracking status request should be valid"),
            )
            .await
            .expect("router should answer wallet tracking status request");

        assert_eq!(response.status(), StatusCode::OK);

        let body = to_bytes(response.into_body(), usize::MAX)
            .await
            .expect("wallet tracking status body should be readable");
        let payload: Value =
            serde_json::from_slice(&body).expect("wallet tracking status should be json");

        assert_eq!(payload["enabled"], json!(false));
        assert_eq!(payload["status"], json!("disabled"));
        assert_eq!(payload["tier"], Value::Null);
        assert_eq!(payload["synced_addresses"], json!([]));
        assert_eq!(payload["last_connected_at"], Value::Null);
        assert_eq!(payload["last_message_at"], Value::Null);
        assert_eq!(payload["last_event_at"], Value::Null);
        assert_eq!(payload["last_error"], Value::Null);
        assert_eq!(payload["active_wallet_pool_count"], json!(1));
        assert_eq!(payload["token_synced_at"], Value::Null);

        sqlx::query("DELETE FROM signal_pools WHERE pool_name = ANY($1)")
            .bind(vec![
                wallet_pool_name,
                disabled_wallet_pool_name,
                market_pool_name,
            ])
            .execute(&pool)
            .await
            .expect("signal pool fixtures should clean up");

        restore_wallet_runtime_configs(&pool, backup).await;
        reset_snapshot_for_tests().await;
    }

    #[tokio::test]
    async fn wallet_tracking_status_route_surfaces_live_runtime_snapshot_fields() {
        let _guard = wallet_runtime_test_lock().lock().await;
        reset_snapshot_for_tests().await;
        let pool = local_db_pool().await;
        let backup = backup_wallet_runtime_configs(&pool).await;
        reset_wallet_runtime_configs(&pool).await;

        for (key, value) in [
            ("hyper_insight_wallet_enabled", "true"),
            ("hyper_insight_wallet_access_token", "live-runtime-token"),
            (
                "hyper_insight_wallet_token_synced_at",
                "2026-04-15T12:34:56",
            ),
        ] {
            sqlx::query(
                r#"
                INSERT INTO system_configs (key, value, description, created_at, updated_at)
                VALUES ($1, $2, NULL, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                ON CONFLICT (key)
                DO UPDATE SET value = EXCLUDED.value, updated_at = CURRENT_TIMESTAMP
                "#,
            )
            .bind(key)
            .bind(value)
            .execute(&pool)
            .await
            .expect("wallet runtime config fixture should upsert");
        }

        set_snapshot_for_tests(WalletTrackingRuntimeSnapshot {
            status: "connected".to_owned(),
            tier: Some("premium".to_owned()),
            synced_addresses: vec!["0xabc".to_owned(), "0xdef".to_owned()],
            last_connected_at: Some("2026-04-15T12:35:00+00:00".to_owned()),
            last_message_at: Some("2026-04-15T12:35:10+00:00".to_owned()),
            last_event_at: Some("2026-04-15T12:35:20+00:00".to_owned()),
            last_error: None,
        })
        .await;

        let router = build_router(local_db_test_config());
        let response = router
            .oneshot(
                Request::builder()
                    .uri("/api/signals/wallet-tracking/status")
                    .body(Body::empty())
                    .expect("wallet tracking status request should be valid"),
            )
            .await
            .expect("router should answer wallet tracking status request");
        assert_eq!(response.status(), StatusCode::OK);

        let body = to_bytes(response.into_body(), usize::MAX)
            .await
            .expect("wallet tracking status body should be readable");
        let payload: Value =
            serde_json::from_slice(&body).expect("wallet tracking status should be json");

        assert_eq!(payload["enabled"], json!(true));
        assert_eq!(payload["status"], json!("connected"));
        assert_eq!(payload["tier"], json!("premium"));
        assert_eq!(payload["synced_addresses"], json!(["0xabc", "0xdef"]));
        assert_eq!(
            payload["last_connected_at"],
            json!("2026-04-15T12:35:00+00:00")
        );
        assert_eq!(
            payload["last_message_at"],
            json!("2026-04-15T12:35:10+00:00")
        );
        assert_eq!(payload["last_event_at"], json!("2026-04-15T12:35:20+00:00"));
        assert_eq!(payload["last_error"], Value::Null);
        assert_eq!(payload["token_synced_at"], json!("2026-04-15T12:34:56"));

        restore_wallet_runtime_configs(&pool, backup).await;
        reset_snapshot_for_tests().await;
    }

    #[tokio::test]
    async fn wallet_tracking_runtime_route_persists_enable_and_token_natively() {
        let _guard = wallet_runtime_test_lock().lock().await;
        reset_snapshot_for_tests().await;
        let pool = local_db_pool().await;
        let backup = backup_wallet_runtime_configs(&pool).await;
        reset_wallet_runtime_configs(&pool).await;
        let legacy_runtime_hits = Arc::new(AtomicUsize::new(0));
        let upstream = Router::new().route(
            "/api/signals/wallet-tracking/runtime",
            put({
                let legacy_runtime_hits = Arc::clone(&legacy_runtime_hits);
                move |Json(_payload): Json<Value>| {
                    let legacy_runtime_hits = Arc::clone(&legacy_runtime_hits);
                    async move {
                        legacy_runtime_hits.fetch_add(1, Ordering::SeqCst);
                        Json(json!({"status": "legacy"}))
                    }
                }
            }),
        );
        let upstream_addr = spawn_test_legacy_server(upstream).await;
        let router = build_router(test_config_for_legacy_http(upstream_addr));

        let waiting_response = router
            .clone()
            .oneshot(
                Request::builder()
                    .method("PUT")
                    .uri("/api/signals/wallet-tracking/runtime")
                    .header("content-type", "application/json")
                    .body(Body::from(json!({"enabled": true}).to_string()))
                    .expect("wallet runtime enable request should be valid"),
            )
            .await
            .expect("router should answer wallet runtime enable request");
        assert_eq!(waiting_response.status(), StatusCode::OK);
        let waiting_body = to_bytes(waiting_response.into_body(), usize::MAX)
            .await
            .expect("wallet runtime enable response body should be readable");
        let waiting_payload: Value =
            serde_json::from_slice(&waiting_body).expect("wallet runtime response should be json");
        assert_eq!(waiting_payload["enabled"], json!(true));
        assert_eq!(waiting_payload["status"], json!("waiting_for_token"));

        let token_response = router
            .clone()
            .oneshot(
                Request::builder()
                    .method("PUT")
                    .uri("/api/signals/wallet-tracking/runtime")
                    .header("content-type", "application/json")
                    .body(Body::from(
                        json!({"enabled": true, "access_token": "wallet-runtime-token"})
                            .to_string(),
                    ))
                    .expect("wallet runtime token request should be valid"),
            )
            .await
            .expect("router should answer wallet runtime token request");
        assert_eq!(token_response.status(), StatusCode::OK);
        let token_body = to_bytes(token_response.into_body(), usize::MAX)
            .await
            .expect("wallet runtime token response body should be readable");
        let token_payload: Value =
            serde_json::from_slice(&token_body).expect("wallet runtime response should be json");
        assert_eq!(token_payload["enabled"], json!(true));
        assert_eq!(token_payload["status"], json!("connecting"));
        assert_eq!(token_payload["tier"], Value::Null);
        assert_eq!(token_payload["synced_addresses"], json!([]));
        assert!(
            token_payload["token_synced_at"]
                .as_str()
                .is_some_and(|value| { value.starts_with("20") && value.contains('T') })
        );

        let disabled_response = router
            .oneshot(
                Request::builder()
                    .method("PUT")
                    .uri("/api/signals/wallet-tracking/runtime")
                    .header("content-type", "application/json")
                    .body(Body::from(json!({"enabled": false}).to_string()))
                    .expect("wallet runtime disable request should be valid"),
            )
            .await
            .expect("router should answer wallet runtime disable request");
        assert_eq!(disabled_response.status(), StatusCode::OK);
        let disabled_body = to_bytes(disabled_response.into_body(), usize::MAX)
            .await
            .expect("wallet runtime disable response body should be readable");
        let disabled_payload: Value =
            serde_json::from_slice(&disabled_body).expect("wallet runtime response should be json");
        assert_eq!(disabled_payload["enabled"], json!(false));
        assert_eq!(disabled_payload["status"], json!("disabled"));
        assert_eq!(
            load_test_system_config(&pool, "hyper_insight_wallet_enabled").await,
            Some("false".to_owned())
        );
        assert_eq!(
            load_test_system_config(&pool, "hyper_insight_wallet_access_token").await,
            Some("wallet-runtime-token".to_owned())
        );
        assert_eq!(legacy_runtime_hits.load(Ordering::SeqCst), 0);

        restore_wallet_runtime_configs(&pool, backup).await;
        reset_snapshot_for_tests().await;
    }

    #[tokio::test]
    async fn wallet_tracking_token_routes_sync_and_clear_natively() {
        let _guard = wallet_runtime_test_lock().lock().await;
        reset_snapshot_for_tests().await;
        let pool = local_db_pool().await;
        let backup = backup_wallet_runtime_configs(&pool).await;
        reset_wallet_runtime_configs(&pool).await;
        let legacy_token_hits = Arc::new(AtomicUsize::new(0));
        let upstream = Router::new().route(
            "/api/signals/wallet-tracking/token",
            post({
                let legacy_token_hits = Arc::clone(&legacy_token_hits);
                move |Json(_payload): Json<Value>| {
                    let legacy_token_hits = Arc::clone(&legacy_token_hits);
                    async move {
                        legacy_token_hits.fetch_add(1, Ordering::SeqCst);
                        Json(json!({"success": true}))
                    }
                }
            })
            .delete({
                let legacy_token_hits = Arc::clone(&legacy_token_hits);
                move || {
                    let legacy_token_hits = Arc::clone(&legacy_token_hits);
                    async move {
                        legacy_token_hits.fetch_add(1, Ordering::SeqCst);
                        Json(json!({"success": true}))
                    }
                }
            }),
        );
        let upstream_addr = spawn_test_legacy_server(upstream).await;
        let router = build_router(test_config_for_legacy_http(upstream_addr));

        let enable_response = router
            .clone()
            .oneshot(
                Request::builder()
                    .method("PUT")
                    .uri("/api/signals/wallet-tracking/runtime")
                    .header("content-type", "application/json")
                    .body(Body::from(json!({"enabled": true}).to_string()))
                    .expect("wallet runtime enable request should be valid"),
            )
            .await
            .expect("router should answer wallet runtime enable request");
        assert_eq!(enable_response.status(), StatusCode::OK);
        let enable_body = to_bytes(enable_response.into_body(), usize::MAX)
            .await
            .expect("wallet runtime enable response should be readable");
        let enable_payload: Value =
            serde_json::from_slice(&enable_body).expect("wallet runtime enable response json");
        assert_eq!(enable_payload["status"], json!("waiting_for_token"));

        let sync_response = router
            .clone()
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/api/signals/wallet-tracking/token")
                    .header("content-type", "application/json")
                    .body(Body::from(
                        json!({"access_token": "wallet-token-sync"}).to_string(),
                    ))
                    .expect("wallet token sync request should be valid"),
            )
            .await
            .expect("router should answer wallet token sync request");
        assert_eq!(sync_response.status(), StatusCode::OK);
        let sync_body = to_bytes(sync_response.into_body(), usize::MAX)
            .await
            .expect("wallet token sync response should be readable");
        let sync_payload: Value =
            serde_json::from_slice(&sync_body).expect("wallet token sync response json");
        assert_eq!(sync_payload, json!({"success": true}));
        assert_eq!(
            load_test_system_config(&pool, "hyper_insight_wallet_access_token").await,
            Some("wallet-token-sync".to_owned())
        );
        let synced_at = load_test_system_config(&pool, "hyper_insight_wallet_token_synced_at")
            .await
            .expect("wallet token synced_at should be persisted");
        assert!(synced_at.starts_with("20"));

        let status_after_sync = router
            .clone()
            .oneshot(
                Request::builder()
                    .uri("/api/signals/wallet-tracking/status")
                    .body(Body::empty())
                    .expect("wallet status request should be valid"),
            )
            .await
            .expect("router should answer wallet status request");
        assert_eq!(status_after_sync.status(), StatusCode::OK);
        let status_after_sync_body = to_bytes(status_after_sync.into_body(), usize::MAX)
            .await
            .expect("wallet status response should be readable");
        let status_after_sync_payload: Value =
            serde_json::from_slice(&status_after_sync_body).expect("wallet status response json");
        assert_eq!(status_after_sync_payload["status"], json!("connecting"));
        assert_eq!(
            status_after_sync_payload["token_synced_at"],
            json!(synced_at.clone())
        );

        let clear_response = router
            .clone()
            .oneshot(
                Request::builder()
                    .method("DELETE")
                    .uri("/api/signals/wallet-tracking/token")
                    .body(Body::empty())
                    .expect("wallet token clear request should be valid"),
            )
            .await
            .expect("router should answer wallet token clear request");
        assert_eq!(clear_response.status(), StatusCode::OK);
        let clear_body = to_bytes(clear_response.into_body(), usize::MAX)
            .await
            .expect("wallet token clear response should be readable");
        let clear_payload: Value =
            serde_json::from_slice(&clear_body).expect("wallet token clear response json");
        assert_eq!(clear_payload, json!({"success": true}));
        assert_eq!(
            load_test_system_config(&pool, "hyper_insight_wallet_access_token").await,
            Some(String::new())
        );
        assert_eq!(
            load_test_system_config(&pool, "hyper_insight_wallet_token_synced_at").await,
            Some(synced_at.clone())
        );

        let status_after_clear = router
            .oneshot(
                Request::builder()
                    .uri("/api/signals/wallet-tracking/status")
                    .body(Body::empty())
                    .expect("wallet status request should be valid"),
            )
            .await
            .expect("router should answer wallet status request");
        assert_eq!(status_after_clear.status(), StatusCode::OK);
        let status_after_clear_body = to_bytes(status_after_clear.into_body(), usize::MAX)
            .await
            .expect("wallet status response should be readable");
        let status_after_clear_payload: Value =
            serde_json::from_slice(&status_after_clear_body).expect("wallet status response json");
        assert_eq!(status_after_clear_payload["enabled"], json!(true));
        assert_eq!(
            status_after_clear_payload["status"],
            json!("waiting_for_token")
        );
        assert_eq!(
            status_after_clear_payload["token_synced_at"],
            json!(synced_at.clone())
        );
        assert_eq!(legacy_token_hits.load(Ordering::SeqCst), 0);

        restore_wallet_runtime_configs(&pool, backup).await;
        reset_snapshot_for_tests().await;
    }

    #[tokio::test]
    async fn wallet_pool_mutation_refresh_no_longer_uses_legacy_wallet_endpoints() {
        let _guard = wallet_runtime_test_lock().lock().await;
        reset_snapshot_for_tests().await;
        let pool = local_db_pool().await;
        let backup = backup_wallet_runtime_configs(&pool).await;
        reset_wallet_runtime_configs(&pool).await;
        let status_hits = Arc::new(AtomicUsize::new(0));
        let runtime_hits = Arc::new(AtomicUsize::new(0));

        let upstream = Router::new()
            .route(
                "/api/signals/wallet-tracking/status",
                axum::routing::get({
                    let status_hits = Arc::clone(&status_hits);
                    move || {
                        let status_hits = Arc::clone(&status_hits);
                        async move {
                            status_hits.fetch_add(1, Ordering::SeqCst);
                            Json(json!({"enabled": true}))
                        }
                    }
                }),
            )
            .route(
                "/api/signals/wallet-tracking/runtime",
                put({
                    let runtime_hits = Arc::clone(&runtime_hits);
                    move |Json(payload): Json<Value>| {
                        let runtime_hits = Arc::clone(&runtime_hits);
                        async move {
                            runtime_hits.fetch_add(1, Ordering::SeqCst);
                            Json(json!({"payload": payload, "success": true}))
                        }
                    }
                }),
            );
        let upstream_addr = spawn_test_legacy_server(upstream).await;
        let router = build_router(test_config_for_legacy_http(upstream_addr));
        let pool_name = format!("wallet-refresh-{}", Uuid::new_v4().simple());

        let response = router
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/api/signals/pools")
                    .header("content-type", "application/json")
                    .body(Body::from(
                        json!({
                            "pool_name": pool_name,
                            "enabled": true,
                            "source_type": "wallet_tracking",
                            "source_config": {"addresses": ["0xabc"]}
                        })
                        .to_string(),
                    ))
                    .expect("signal pool create request should be valid"),
            )
            .await
            .expect("router should answer signal pool create request");

        assert_eq!(response.status(), StatusCode::OK);
        assert_eq!(status_hits.load(Ordering::SeqCst), 0);
        assert_eq!(runtime_hits.load(Ordering::SeqCst), 0);

        sqlx::query("DELETE FROM signal_pools WHERE pool_name = $1")
            .bind(&pool_name)
            .execute(&pool)
            .await
            .expect("signal pool fixture should clean up");

        restore_wallet_runtime_configs(&pool, backup).await;
        reset_snapshot_for_tests().await;
    }

    #[tokio::test]
    async fn signal_states_route_is_native_and_reports_cache_snapshot_shape() {
        let pool = local_db_pool().await;
        let tag = Uuid::new_v4().simple().to_string();
        let enabled_signal_name = format!("signal-states-enabled-{tag}");
        let disabled_signal_name = format!("signal-states-disabled-{tag}");
        let market_pool_name = format!("signal-states-market-pool-{tag}");
        let wallet_pool_name = format!("signal-states-wallet-pool-{tag}");
        let legacy_states_hits = Arc::new(AtomicUsize::new(0));

        sqlx::query(
            r#"
            INSERT INTO signal_definitions (
                signal_name, description, trigger_condition, enabled, exchange, created_at, updated_at
            )
            VALUES ($1, 'fixture', '{}', true, 'hyperliquid', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            "#,
        )
        .bind(&enabled_signal_name)
        .execute(&pool)
        .await
        .expect("enabled signal definition fixture should insert");

        sqlx::query(
            r#"
            INSERT INTO signal_definitions (
                signal_name, description, trigger_condition, enabled, exchange, created_at, updated_at
            )
            VALUES ($1, 'fixture', '{}', false, 'hyperliquid', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            "#,
        )
        .bind(&disabled_signal_name)
        .execute(&pool)
        .await
        .expect("disabled signal definition fixture should insert");

        for (pool_name, source_type) in [
            (&market_pool_name, "market_signals"),
            (&wallet_pool_name, "wallet_tracking"),
        ] {
            sqlx::query(
                r#"
                INSERT INTO signal_pools (
                    pool_name, signal_ids, symbols, enabled, logic, exchange, source_type, source_config, created_at
                )
                VALUES ($1, '[]', '[]', true, 'OR', 'hyperliquid', $2, '{}', CURRENT_TIMESTAMP)
                "#,
            )
            .bind(pool_name)
            .bind(source_type)
            .execute(&pool)
            .await
            .expect("signal pool fixture should insert");
        }

        let upstream = Router::new().route(
            "/api/signals/states",
            axum::routing::get({
                let legacy_states_hits = Arc::clone(&legacy_states_hits);
                move || {
                    let legacy_states_hits = Arc::clone(&legacy_states_hits);
                    async move {
                        legacy_states_hits.fetch_add(1, Ordering::SeqCst);
                        Json(json!({"source": "legacy"}))
                    }
                }
            }),
        );
        let upstream_addr = spawn_test_legacy_server(upstream).await;
        let router = build_router(test_config_for_legacy_http(upstream_addr));

        let response = router
            .oneshot(
                Request::builder()
                    .uri("/api/signals/states")
                    .body(Body::empty())
                    .expect("signal states request should be valid"),
            )
            .await
            .expect("router should answer signal states request");
        assert_eq!(response.status(), StatusCode::OK);

        let body = to_bytes(response.into_body(), usize::MAX)
            .await
            .expect("signal states response body should be readable");
        let payload: Value =
            serde_json::from_slice(&body).expect("signal states response should be json");
        assert_eq!(payload["states"]["signal_states"], json!({}));
        assert_eq!(payload["states"]["pool_states"], json!({}));
        assert!(
            payload["cache_info"]["signals_count"]
                .as_i64()
                .is_some_and(|count| count >= 1)
        );
        assert!(
            payload["cache_info"]["pools_count"]
                .as_i64()
                .is_some_and(|count| count >= 1)
        );
        assert_eq!(legacy_states_hits.load(Ordering::SeqCst), 0);

        sqlx::query("DELETE FROM signal_pools WHERE pool_name = ANY($1)")
            .bind(vec![market_pool_name, wallet_pool_name])
            .execute(&pool)
            .await
            .expect("signal pool fixtures should clean up");

        sqlx::query("DELETE FROM signal_definitions WHERE signal_name = ANY($1)")
            .bind(vec![enabled_signal_name, disabled_signal_name])
            .execute(&pool)
            .await
            .expect("signal definition fixtures should clean up");
    }

    #[tokio::test]
    async fn signal_states_reset_route_is_native_and_accepts_filter_params() {
        let legacy_reset_hits = Arc::new(AtomicUsize::new(0));
        let upstream = Router::new().route(
            "/api/signals/states/reset",
            post({
                let legacy_reset_hits = Arc::clone(&legacy_reset_hits);
                move || {
                    let legacy_reset_hits = Arc::clone(&legacy_reset_hits);
                    async move {
                        legacy_reset_hits.fetch_add(1, Ordering::SeqCst);
                        Json(json!({"source": "legacy"}))
                    }
                }
            }),
        );
        let upstream_addr = spawn_test_legacy_server(upstream).await;
        let router = build_router(test_config_for_legacy_http(upstream_addr));

        let response = router
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/api/signals/states/reset?signal_id=7&pool_id=9&symbol=BTC")
                    .body(Body::empty())
                    .expect("signal states reset request should be valid"),
            )
            .await
            .expect("router should answer signal states reset request");

        assert_eq!(response.status(), StatusCode::OK);
        let body = to_bytes(response.into_body(), usize::MAX)
            .await
            .expect("signal states reset response body should be readable");
        let payload: Value =
            serde_json::from_slice(&body).expect("signal states reset response should be json");
        assert_eq!(
            payload["message"],
            json!("Signal and pool states reset successfully")
        );
        assert_eq!(legacy_reset_hits.load(Ordering::SeqCst), 0);
    }

    #[tokio::test]
    async fn program_preview_run_route_returns_not_found_for_missing_binding() {
        let router = build_router(local_db_test_config());
        let response = router
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/api/programs/bindings/2147483000/preview-run")
                    .body(Body::empty())
                    .expect("preview-run request should be valid"),
            )
            .await
            .expect("router should answer preview-run request");

        assert_eq!(response.status(), StatusCode::NOT_FOUND);

        let body = to_bytes(response.into_body(), usize::MAX)
            .await
            .expect("preview-run response body should be readable");
        let payload: Value =
            serde_json::from_slice(&body).expect("preview-run response should be json");
        assert_eq!(payload["detail"], json!("Binding not found"));
    }

    #[tokio::test]
    async fn program_preview_run_route_returns_success_contract_from_rust_handler() {
        let fixture = PreviewRunFixture::create_hyperliquid_success()
            .await
            .expect("preview-run fixture should be created");
        let router = build_router(local_db_test_config());

        let response = router
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri(format!(
                        "/api/programs/bindings/{}/preview-run",
                        fixture.binding_id
                    ))
                    .body(Body::empty())
                    .expect("preview-run request should be valid"),
            )
            .await
            .expect("router should answer preview-run request");

        assert_eq!(response.status(), StatusCode::OK);

        let body = to_bytes(response.into_body(), usize::MAX)
            .await
            .expect("preview-run response body should be readable");
        let payload: Value =
            serde_json::from_slice(&body).expect("preview-run response should be json");
        fixture.cleanup().await;

        assert_eq!(payload["success"], json!(true));
        assert_eq!(payload["decision"]["operation"], json!("hold"));
        assert_eq!(payload["decision"]["symbol"], json!(fixture.symbol));
        assert_eq!(payload["decision"]["reason"], json!("fixture-ok"));
        assert_eq!(payload["input_data"]["environment"], json!("testnet"));
        assert_eq!(payload["input_data"]["exchange"], json!("hyperliquid"));
        assert_eq!(
            payload["input_data"]["signal_pool_name"],
            json!(fixture.signal_pool_name)
        );
        assert_eq!(payload["input_data"]["pool_logic"], json!("OR"));
        assert_eq!(
            payload["input_data"]["signal_source_type"],
            json!("market_signals")
        );
        assert_eq!(payload["input_data"]["positions_count"], json!(1));
        assert_eq!(payload["input_data"]["open_orders_count"], json!(1));
        assert_eq!(payload["input_data"]["recent_trades_count"], json!(1));
        assert_eq!(payload["input_data"]["current_price"], json!(1234.5));
        assert_eq!(payload["data_queries"][0]["method"], json!("get_price"));
        assert_eq!(
            payload["data_queries"][0]["args"]["symbol"],
            json!(fixture.symbol)
        );
        assert_eq!(payload["execution_logs"][0], json!("px=1234.5"));
    }

    #[tokio::test]
    async fn program_preview_run_route_returns_wallet_error_contract() {
        let fixture = PreviewRunFixture::create_binance_missing_wallet()
            .await
            .expect("binance preview-run fixture should be created");
        let router = build_router(local_db_test_config());

        let response = router
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri(format!(
                        "/api/programs/bindings/{}/preview-run",
                        fixture.binding_id
                    ))
                    .body(Body::empty())
                    .expect("preview-run request should be valid"),
            )
            .await
            .expect("router should answer preview-run request");

        assert_eq!(response.status(), StatusCode::OK);

        let body = to_bytes(response.into_body(), usize::MAX)
            .await
            .expect("preview-run response body should be readable");
        let payload: Value =
            serde_json::from_slice(&body).expect("preview-run response should be json");
        fixture.cleanup().await;

        assert_eq!(payload["success"], json!(false));
        assert_eq!(
            payload["error"],
            json!("Binance testnet wallet not configured for this AI Trader")
        );
        assert_eq!(payload["input_data"], Value::Null);
        assert_eq!(payload["decision"], Value::Null);
    }

    fn local_db_test_config() -> AppConfig {
        AppConfig {
            bind_addr: SocketAddr::new(IpAddr::V4(Ipv4Addr::LOCALHOST), 8802),
            legacy_http_url: Url::parse("http://127.0.0.1:5611")
                .expect("legacy http test url should parse"),
            legacy_ws_url: Url::parse("ws://127.0.0.1:5611")
                .expect("legacy ws test url should parse"),
            database_url: "postgresql://alpha_user:alpha_pass@localhost:5432/alpha_arena"
                .to_owned(),
            snapshot_database_url:
                "postgresql://alpha_user:alpha_pass@localhost:5432/alpha_snapshots".to_owned(),
            request_timeout: Duration::from_secs(10),
            connect_timeout: Duration::from_secs(5),
            wallet_runtime_enabled: false,
        }
    }

    fn test_config_for_legacy_http(upstream_addr: SocketAddr) -> AppConfig {
        AppConfig {
            bind_addr: SocketAddr::new(IpAddr::V4(Ipv4Addr::LOCALHOST), 8802),
            legacy_http_url: Url::parse(&format!("http://{upstream_addr}"))
                .expect("legacy http test url should parse"),
            legacy_ws_url: Url::parse(&format!("ws://{upstream_addr}"))
                .expect("legacy ws test url should parse"),
            database_url: "postgresql://alpha_user:alpha_pass@localhost:5432/alpha_arena"
                .to_owned(),
            snapshot_database_url:
                "postgresql://alpha_user:alpha_pass@localhost:5432/alpha_snapshots".to_owned(),
            request_timeout: Duration::from_secs(10),
            connect_timeout: Duration::from_secs(5),
            wallet_runtime_enabled: false,
        }
    }

    async fn spawn_test_legacy_server(router: Router) -> SocketAddr {
        let listener = TcpListener::bind(SocketAddr::new(IpAddr::V4(Ipv4Addr::LOCALHOST), 0))
            .await
            .expect("test upstream listener should bind");
        let addr = listener
            .local_addr()
            .expect("test upstream listener should have local address");

        tokio::spawn(async move {
            axum::serve(listener, router)
                .await
                .expect("test upstream server should run");
        });

        addr
    }

    async fn local_db_pool() -> PgPool {
        PgPoolOptions::new()
            .max_connections(4)
            .connect("postgresql://alpha_user:alpha_pass@localhost:5432/alpha_arena")
            .await
            .expect("local preview-run test database should connect")
    }

    const WALLET_RUNTIME_CONFIG_KEYS: [&str; 3] = [
        "hyper_insight_wallet_enabled",
        "hyper_insight_wallet_access_token",
        "hyper_insight_wallet_token_synced_at",
    ];
    const CRYPTO_SYMBOLS_CONFIG_KEY: &str = "hyperliquid_available_symbols";

    #[derive(Clone)]
    struct SystemConfigBackup {
        key: String,
        value: Option<String>,
        description: Option<String>,
    }

    fn wallet_runtime_test_lock() -> &'static AsyncMutex<()> {
        static LOCK: OnceLock<AsyncMutex<()>> = OnceLock::new();
        LOCK.get_or_init(|| AsyncMutex::new(()))
    }

    fn crypto_symbols_config_test_lock() -> &'static AsyncMutex<()> {
        static LOCK: OnceLock<AsyncMutex<()>> = OnceLock::new();
        LOCK.get_or_init(|| AsyncMutex::new(()))
    }

    async fn backup_system_config(pool: &PgPool, key: &str) -> Option<SystemConfigBackup> {
        sqlx::query(
            r#"
            SELECT key, value, description
            FROM system_configs
            WHERE key = $1
            LIMIT 1
            "#,
        )
        .bind(key)
        .fetch_optional(pool)
        .await
        .expect("system config backup should load")
        .map(|row| SystemConfigBackup {
            key: row
                .try_get::<String, _>("key")
                .expect("system config backup key should read"),
            value: row
                .try_get::<Option<String>, _>("value")
                .expect("system config backup value should read"),
            description: row
                .try_get::<Option<String>, _>("description")
                .expect("system config backup description should read"),
        })
    }

    async fn upsert_system_config(
        pool: &PgPool,
        key: &str,
        value: &str,
        description: Option<&str>,
    ) {
        sqlx::query(
            r#"
            INSERT INTO system_configs (key, value, description, created_at, updated_at)
            VALUES ($1, $2, $3, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT (key)
            DO UPDATE SET
                value = EXCLUDED.value,
                description = EXCLUDED.description,
                updated_at = CURRENT_TIMESTAMP
            "#,
        )
        .bind(key)
        .bind(value)
        .bind(description)
        .execute(pool)
        .await
        .expect("system config should upsert");
    }

    async fn delete_system_config(pool: &PgPool, key: &str) {
        sqlx::query("DELETE FROM system_configs WHERE key = $1")
            .bind(key)
            .execute(pool)
            .await
            .expect("system config should delete");
    }

    async fn restore_system_config(pool: &PgPool, key: &str, backup: Option<SystemConfigBackup>) {
        delete_system_config(pool, key).await;
        if let Some(item) = backup {
            sqlx::query(
                r#"
                INSERT INTO system_configs (key, value, description, created_at, updated_at)
                VALUES ($1, $2, $3, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                "#,
            )
            .bind(item.key)
            .bind(item.value)
            .bind(item.description)
            .execute(pool)
            .await
            .expect("system config backup should restore");
        }
    }

    async fn backup_wallet_runtime_configs(pool: &PgPool) -> Vec<SystemConfigBackup> {
        sqlx::query(
            r#"
            SELECT key, value, description
            FROM system_configs
            WHERE key = ANY($1)
            "#,
        )
        .bind(
            WALLET_RUNTIME_CONFIG_KEYS
                .iter()
                .map(|key| (*key).to_owned())
                .collect::<Vec<_>>(),
        )
        .fetch_all(pool)
        .await
        .expect("wallet runtime config backup should load")
        .into_iter()
        .map(|row| SystemConfigBackup {
            key: row
                .try_get::<String, _>("key")
                .expect("system config backup key should read"),
            value: row
                .try_get::<Option<String>, _>("value")
                .expect("system config backup value should read"),
            description: row
                .try_get::<Option<String>, _>("description")
                .expect("system config backup description should read"),
        })
        .collect()
    }

    async fn reset_wallet_runtime_configs(pool: &PgPool) {
        sqlx::query("DELETE FROM system_configs WHERE key = ANY($1)")
            .bind(
                WALLET_RUNTIME_CONFIG_KEYS
                    .iter()
                    .map(|key| (*key).to_owned())
                    .collect::<Vec<_>>(),
            )
            .execute(pool)
            .await
            .expect("wallet runtime config reset should succeed");
    }

    async fn restore_wallet_runtime_configs(pool: &PgPool, backup: Vec<SystemConfigBackup>) {
        reset_wallet_runtime_configs(pool).await;
        for item in backup {
            sqlx::query(
                r#"
                INSERT INTO system_configs (key, value, description, created_at, updated_at)
                VALUES ($1, $2, $3, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                "#,
            )
            .bind(item.key)
            .bind(item.value)
            .bind(item.description)
            .execute(pool)
            .await
            .expect("wallet runtime config restore should succeed");
        }
    }

    async fn load_test_system_config(pool: &PgPool, key: &str) -> Option<String> {
        sqlx::query_scalar::<_, Option<String>>(
            "SELECT value FROM system_configs WHERE key = $1 LIMIT 1",
        )
        .bind(key)
        .fetch_optional(pool)
        .await
        .expect("test system config should load")
        .flatten()
    }

    async fn create_account_strategy_test_account(
        pool: &PgPool,
        auto_trading_enabled: &str,
    ) -> i32 {
        let tag = Uuid::new_v4().simple().to_string();
        let account_name = format!("strategy-sync-account-{tag}");
        sqlx::query(
            r#"
            INSERT INTO accounts (
                user_id, version, name, account_type, is_active, auto_trading_enabled,
                model, initial_capital, current_cash, frozen_cash, hyperliquid_enabled,
                show_on_dashboard
            )
            VALUES (
                1, 'v1', $1, 'AI', 'true', $2,
                'gpt-5', 10000, 10000, 0, 'false', true
            )
            RETURNING id
            "#,
        )
        .bind(account_name)
        .bind(auto_trading_enabled)
        .fetch_one(pool)
        .await
        .expect("account strategy fixture account should insert")
        .try_get::<i32, _>("id")
        .expect("account strategy fixture account id should read")
    }

    async fn cleanup_account_strategy_test_account(pool: &PgPool, account_id: i32) {
        let _ = sqlx::query("DELETE FROM account_strategy_configs WHERE account_id = $1")
            .bind(account_id)
            .execute(pool)
            .await;
        let _ = sqlx::query("DELETE FROM account_prompt_bindings WHERE account_id = $1")
            .bind(account_id)
            .execute(pool)
            .await;
        let _ = sqlx::query("DELETE FROM accounts WHERE id = $1")
            .bind(account_id)
            .execute(pool)
            .await;
    }

    async fn create_account_balance_snapshot_test_account(pool: &PgPool) -> (i32, f64, f64) {
        let tag = Uuid::new_v4().simple().to_string();
        let account_name = format!("balance-snapshot-account-{tag}");
        let account_id = sqlx::query(
            r#"
            INSERT INTO accounts (
                user_id, version, name, account_type, is_active, auto_trading_enabled,
                model, initial_capital, current_cash, frozen_cash, hyperliquid_enabled,
                show_on_dashboard, hyperliquid_environment
            )
            VALUES (
                1, 'v1', $1, 'AI', 'true', 'true',
                'gpt-5', 10000, 10000, 0, 'true', true, 'mainnet'
            )
            RETURNING id
            "#,
        )
        .bind(account_name)
        .fetch_one(pool)
        .await
        .expect("account balance fixture account should insert")
        .try_get::<i32, _>("id")
        .expect("account balance fixture account id should read");

        let available_balance = 4321.0;
        let used_margin = 789.0;
        sqlx::query(
            r#"
            INSERT INTO hyperliquid_account_snapshots (
                account_id, environment, wallet_address, total_equity, available_balance,
                used_margin, maintenance_margin, trigger_event
            )
            VALUES ($1, 'mainnet', $2, $3, $4, $5, 0, 'fixture-balance')
            "#,
        )
        .bind(account_id)
        .bind(format!("0x{}", &tag[..16]))
        .bind(available_balance + used_margin)
        .bind(available_balance)
        .bind(used_margin)
        .execute(pool)
        .await
        .expect("account balance fixture snapshot should insert");

        (account_id, available_balance, used_margin)
    }

    async fn cleanup_account_balance_snapshot_test_account(pool: &PgPool, account_id: i32) {
        let _ = sqlx::query("DELETE FROM hyperliquid_positions WHERE account_id = $1")
            .bind(account_id)
            .execute(pool)
            .await;
        let _ = sqlx::query("DELETE FROM hyperliquid_account_snapshots WHERE account_id = $1")
            .bind(account_id)
            .execute(pool)
            .await;
        let _ = sqlx::query("DELETE FROM hyperliquid_wallets WHERE account_id = $1")
            .bind(account_id)
            .execute(pool)
            .await;
        let _ = sqlx::query("DELETE FROM orders WHERE account_id = $1")
            .bind(account_id)
            .execute(pool)
            .await;
        let _ = sqlx::query("DELETE FROM positions WHERE account_id = $1")
            .bind(account_id)
            .execute(pool)
            .await;
        let _ = sqlx::query("DELETE FROM accounts WHERE id = $1")
            .bind(account_id)
            .execute(pool)
            .await;
    }

    struct PreviewRunFixture {
        pool: PgPool,
        binding_id: i32,
        account_id: i32,
        program_id: i32,
        signal_pool_id: Option<i32>,
        order_id: Option<i32>,
        symbol: String,
        signal_pool_name: String,
    }

    impl PreviewRunFixture {
        async fn create_hyperliquid_success() -> Result<Self, sqlx::Error> {
            let pool = local_db_pool().await;
            let tag = Uuid::new_v4().simple().to_string();
            let symbol = format!("PV{}", &tag[..6]).to_uppercase();
            let account_name = format!("preview-account-{tag}");
            let program_name = format!("preview-program-{tag}");
            let signal_pool_name = format!("preview-pool-{tag}");
            let order_no = tag[..32].to_owned();

            let account_id = sqlx::query(
                r#"
                INSERT INTO accounts (
                    user_id, version, name, account_type, is_active, auto_trading_enabled,
                    model, initial_capital, current_cash, frozen_cash, hyperliquid_enabled,
                    show_on_dashboard
                )
                VALUES (
                    1, 'v1', $1, 'AI', 'true', 'true',
                    'gpt-5', 10000, 10000, 0, 'false', true
                )
                RETURNING id
                "#,
            )
            .bind(&account_name)
            .fetch_one(&pool)
            .await?
            .try_get::<i32, _>("id")?;

            let program_code = format!(
                "class PreviewStrategy:\n    def init(self, params):\n        self.params = params\n    def should_trade(self, data):\n        last_trade = data.recent_trades[0] if data.recent_trades else None\n        log('px=' + str(data.get_price(data.trigger_symbol)))\n        return Decision(operation='hold', symbol=data.trigger_symbol, reason=self.params.get('note') if last_trade and last_trade.symbol == data.trigger_symbol else 'bad-fixture')\n"
            );
            let program_id = sqlx::query(
                r#"
                INSERT INTO trading_programs (user_id, name, description, code)
                VALUES (1, $1, 'preview route fixture', $2)
                RETURNING id
                "#,
            )
            .bind(&program_name)
            .bind(&program_code)
            .fetch_one(&pool)
            .await?
            .try_get::<i32, _>("id")?;

            let signal_pool_id = sqlx::query(
                r#"
                INSERT INTO signal_pools (
                    pool_name, signal_ids, symbols, logic, enabled, exchange, source_type, source_config
                )
                VALUES ($1, '[]', $2, 'OR', true, 'hyperliquid', 'market_signals', '{}')
                RETURNING id
                "#,
            )
            .bind(&signal_pool_name)
            .bind(json!([symbol.clone()]).to_string())
            .fetch_one(&pool)
            .await?
            .try_get::<i32, _>("id")?;

            let binding_id = sqlx::query(
                r#"
                INSERT INTO account_program_bindings (
                    account_id, program_id, signal_pool_ids, trigger_interval,
                    scheduled_trigger_enabled, is_active, params_override, exchange
                )
                VALUES ($1, $2, $3, 300, false, true, $4, 'hyperliquid')
                RETURNING id
                "#,
            )
            .bind(account_id)
            .bind(program_id)
            .bind(json!([signal_pool_id]).to_string())
            .bind(json!({"note": "fixture-ok"}).to_string())
            .fetch_one(&pool)
            .await?
            .try_get::<i32, _>("id")?;

            sqlx::query(
                r#"
                INSERT INTO hyperliquid_wallets (
                    account_id, environment, private_key_encrypted, wallet_address,
                    max_leverage, default_leverage, key_type, is_active
                )
                VALUES ($1, 'testnet', 'fixture-key', $2, 20, 3, 'private_key', 'true')
                "#,
            )
            .bind(account_id)
            .bind(format!("0x{}", &tag[..16]))
            .execute(&pool)
            .await?;

            sqlx::query(
                r#"
                INSERT INTO hyperliquid_account_snapshots (
                    account_id, environment, wallet_address, total_equity,
                    available_balance, used_margin, maintenance_margin, trigger_event
                )
                VALUES ($1, 'testnet', $2, 12000, 9000, 3000, 500, 'fixture')
                "#,
            )
            .bind(account_id)
            .bind(format!("0x{}", &tag[..16]))
            .execute(&pool)
            .await?;

            sqlx::query(
                r#"
                INSERT INTO hyperliquid_positions (
                    account_id, environment, wallet_address, symbol, position_size,
                    entry_price, current_price, position_value, unrealized_pnl,
                    margin_used, liquidation_price, leverage
                )
                VALUES ($1, 'testnet', $2, $3, 1.5, 1200, 1234.5, 1851.75, 51.75, 200, 900, 3)
                "#,
            )
            .bind(account_id)
            .bind(format!("0x{}", &tag[..16]))
            .bind(&symbol)
            .execute(&pool)
            .await?;

            sqlx::query(
                r#"
                INSERT INTO crypto_klines (
                    exchange, symbol, market, period, timestamp, datetime_str, environment,
                    open_price, high_price, low_price, close_price, volume
                )
                VALUES
                    ('hyperliquid', $1, 'CRYPTO', '1m', 2000000001, '2033-05-18 03:33:21', 'testnet', 1230, 1240, 1225, 1234.5, 1000),
                    ('hyperliquid', $1, 'CRYPTO', '1h', 2000000000, '2033-05-18 03:00:00', 'testnet', 1200, 1245, 1190, 1230, 5000)
                ON CONFLICT (exchange, symbol, market, period, timestamp, environment) DO NOTHING
                "#,
            )
            .bind(&symbol)
            .execute(&pool)
            .await?;

            let order_id = sqlx::query(
                r#"
                INSERT INTO orders (
                    version, account_id, order_no, symbol, name, market, side, order_type,
                    price, quantity, filled_quantity, status, hyperliquid_environment,
                    leverage, margin_mode, reduce_only, hyperliquid_order_id
                )
                VALUES (
                    'v1', $1, $2, $3, $3, 'CRYPTO', 'buy', 'limit',
                    1230, 0.5, 0, 'open', 'testnet',
                    3, 'cross', 'false', $4
                )
                RETURNING id
                "#,
            )
            .bind(account_id)
            .bind(&order_no)
            .bind(&symbol)
            .bind(format!("oid-{tag}"))
            .fetch_one(&pool)
            .await?
            .try_get::<i32, _>("id")?;

            sqlx::query(
                r#"
                INSERT INTO trades (
                    order_id, account_id, symbol, name, market, side, price, quantity,
                    commission, hyperliquid_environment
                )
                VALUES ($1, $2, $3, $3, 'CRYPTO', 'buy', 1200, 0.25, 0, 'testnet')
                "#,
            )
            .bind(order_id)
            .bind(account_id)
            .bind(&symbol)
            .execute(&pool)
            .await?;

            Ok(Self {
                pool,
                binding_id,
                account_id,
                program_id,
                signal_pool_id: Some(signal_pool_id),
                order_id: Some(order_id),
                symbol,
                signal_pool_name,
            })
        }

        async fn create_binance_missing_wallet() -> Result<Self, sqlx::Error> {
            let pool = local_db_pool().await;
            let tag = Uuid::new_v4().simple().to_string();
            let symbol = format!("BN{}", &tag[..6]).to_uppercase();
            let account_name = format!("preview-binance-account-{tag}");
            let program_name = format!("preview-binance-program-{tag}");

            let account_id = sqlx::query(
                r#"
                INSERT INTO accounts (
                    user_id, version, name, account_type, is_active, auto_trading_enabled,
                    model, initial_capital, current_cash, frozen_cash, hyperliquid_enabled,
                    show_on_dashboard
                )
                VALUES (
                    1, 'v1', $1, 'AI', 'true', 'true',
                    'gpt-5', 10000, 10000, 0, 'false', true
                )
                RETURNING id
                "#,
            )
            .bind(&account_name)
            .fetch_one(&pool)
            .await?
            .try_get::<i32, _>("id")?;

            let program_id = sqlx::query(
                r#"
                INSERT INTO trading_programs (user_id, name, description, code)
                VALUES (1, $1, 'preview route fixture', $2)
                RETURNING id
                "#,
            )
            .bind(&program_name)
            .bind(
                "class PreviewStrategy:\n    def should_trade(self, data):\n        return Decision(operation='hold', symbol='BTC', reason='noop')\n",
            )
            .fetch_one(&pool)
            .await?
            .try_get::<i32, _>("id")?;

            let binding_id = sqlx::query(
                r#"
                INSERT INTO account_program_bindings (
                    account_id, program_id, trigger_interval,
                    scheduled_trigger_enabled, is_active, exchange
                )
                VALUES ($1, $2, 300, true, true, 'binance')
                RETURNING id
                "#,
            )
            .bind(account_id)
            .bind(program_id)
            .fetch_one(&pool)
            .await?
            .try_get::<i32, _>("id")?;

            Ok(Self {
                pool,
                binding_id,
                account_id,
                program_id,
                signal_pool_id: None,
                order_id: None,
                symbol,
                signal_pool_name: String::new(),
            })
        }

        async fn cleanup(&self) {
            if let Some(order_id) = self.order_id {
                let _ = sqlx::query("DELETE FROM trades WHERE order_id = $1")
                    .bind(order_id)
                    .execute(&self.pool)
                    .await;
                let _ = sqlx::query("DELETE FROM orders WHERE id = $1")
                    .bind(order_id)
                    .execute(&self.pool)
                    .await;
            } else {
                let _ = sqlx::query("DELETE FROM trades WHERE account_id = $1")
                    .bind(self.account_id)
                    .execute(&self.pool)
                    .await;
            }
            let _ = sqlx::query("DELETE FROM hyperliquid_positions WHERE account_id = $1")
                .bind(self.account_id)
                .execute(&self.pool)
                .await;
            let _ = sqlx::query("DELETE FROM hyperliquid_account_snapshots WHERE account_id = $1")
                .bind(self.account_id)
                .execute(&self.pool)
                .await;
            let _ = sqlx::query("DELETE FROM hyperliquid_wallets WHERE account_id = $1")
                .bind(self.account_id)
                .execute(&self.pool)
                .await;
            let _ = sqlx::query("DELETE FROM crypto_klines WHERE symbol = $1")
                .bind(&self.symbol)
                .execute(&self.pool)
                .await;
            let _ = sqlx::query("DELETE FROM binance_wallets WHERE account_id = $1")
                .bind(self.account_id)
                .execute(&self.pool)
                .await;
            let _ = sqlx::query("DELETE FROM account_program_bindings WHERE id = $1")
                .bind(self.binding_id)
                .execute(&self.pool)
                .await;
            if let Some(signal_pool_id) = self.signal_pool_id {
                let _ = sqlx::query("DELETE FROM signal_pools WHERE id = $1")
                    .bind(signal_pool_id)
                    .execute(&self.pool)
                    .await;
            }
            let _ = sqlx::query("DELETE FROM trading_programs WHERE id = $1")
                .bind(self.program_id)
                .execute(&self.pool)
                .await;
            let _ = sqlx::query("DELETE FROM accounts WHERE id = $1")
                .bind(self.account_id)
                .execute(&self.pool)
                .await;
        }
    }
}
