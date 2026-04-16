use reqwest::Client;
use sqlx::{PgPool, postgres::PgPoolOptions};

use crate::config::AppConfig;

#[derive(Clone)]
pub struct AppState {
    pub config: AppConfig,
    pub client: Client,
    pub db: PgPool,
    pub snapshot_db: PgPool,
}

impl AppState {
    pub fn from_config(config: AppConfig) -> Self {
        let client = Client::builder()
            .connect_timeout(config.connect_timeout)
            .timeout(config.request_timeout)
            .build()
            .expect("reqwest client should build");
        let db = PgPoolOptions::new()
            .max_connections(20)
            .connect_lazy(&config.database_url)
            .expect("database URL should be valid");
        let snapshot_db = PgPoolOptions::new()
            .max_connections(20)
            .connect_lazy(&config.snapshot_database_url)
            .expect("snapshot database URL should be valid");

        Self {
            config,
            client,
            db,
            snapshot_db,
        }
    }
}
