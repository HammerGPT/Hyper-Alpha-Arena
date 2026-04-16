use axum::{
    extract::{
        OriginalUri, State,
        ws::{CloseFrame, Message, Utf8Bytes, WebSocket, WebSocketUpgrade},
    },
    http::{HeaderMap, header},
    response::Response,
};
use futures_util::{SinkExt, StreamExt};
use tokio_tungstenite::{
    connect_async,
    tungstenite::protocol::{
        CloseFrame as TungsteniteCloseFrame, Message as TungsteniteMessage,
        frame::coding::CloseCode as TungsteniteCloseCode,
    },
};
use tracing::{info, warn};

use crate::{error::AppError, state::AppState};

pub async fn proxy_websocket(
    ws: WebSocketUpgrade,
    State(state): State<AppState>,
    headers: HeaderMap,
    original_uri: OriginalUri,
) -> Result<Response, AppError> {
    let upstream_uri = state.config.legacy_ws_target(&original_uri.0.to_string());
    let mut request_builder = http::Request::builder().uri(upstream_uri.as_str());

    for (name, value) in &headers {
        if should_forward_ws_header(name) {
            request_builder = request_builder.header(name, value);
        }
    }

    let upstream_request = request_builder.body(()).map_err(|error| {
        AppError::internal(format!("failed to build upstream ws request: {error}"))
    })?;

    Ok(ws.on_upgrade(move |socket| async move {
        if let Err(error) = proxy_websocket_session(socket, upstream_request).await {
            warn!(target = "backend_rust::ws_proxy", %error, "websocket proxy session ended with error");
        }
    }))
}

async fn proxy_websocket_session(
    downstream_socket: WebSocket,
    upstream_request: http::Request<()>,
) -> Result<(), String> {
    let (upstream_socket, _) = connect_async(upstream_request)
        .await
        .map_err(|error| format!("failed to connect to legacy websocket: {error}"))?;

    let (mut downstream_sender, mut downstream_receiver) = downstream_socket.split();
    let (mut upstream_sender, mut upstream_receiver) = upstream_socket.split();

    info!(
        target = "backend_rust::ws_proxy",
        "websocket proxy connected"
    );

    let downstream_to_upstream = async {
        while let Some(result) = downstream_receiver.next().await {
            let message =
                result.map_err(|error| format!("downstream websocket receive failed: {error}"))?;
            let upstream_message = map_downstream_message(message)?;
            if let Some(upstream_message) = upstream_message {
                upstream_sender
                    .send(upstream_message)
                    .await
                    .map_err(|error| format!("upstream websocket send failed: {error}"))?;
            }
        }

        upstream_sender
            .close()
            .await
            .map_err(|error| format!("failed to close upstream websocket: {error}"))?;

        Ok::<(), String>(())
    };

    let upstream_to_downstream = async {
        while let Some(result) = upstream_receiver.next().await {
            let message =
                result.map_err(|error| format!("upstream websocket receive failed: {error}"))?;
            let downstream_message = map_upstream_message(message)?;
            if let Some(downstream_message) = downstream_message {
                downstream_sender
                    .send(downstream_message)
                    .await
                    .map_err(|error| format!("downstream websocket send failed: {error}"))?;
            }
        }

        downstream_sender
            .close()
            .await
            .map_err(|error| format!("failed to close downstream websocket: {error}"))?;

        Ok::<(), String>(())
    };

    tokio::select! {
        result = downstream_to_upstream => result?,
        result = upstream_to_downstream => result?,
    }

    info!(
        target = "backend_rust::ws_proxy",
        "websocket proxy disconnected"
    );
    Ok(())
}

fn should_forward_ws_header(name: &header::HeaderName) -> bool {
    name != header::HOST
}

fn map_downstream_message(message: Message) -> Result<Option<TungsteniteMessage>, String> {
    match message {
        Message::Text(text) => Ok(Some(TungsteniteMessage::Text(text.to_string().into()))),
        Message::Binary(binary) => Ok(Some(TungsteniteMessage::Binary(binary))),
        Message::Ping(payload) => Ok(Some(TungsteniteMessage::Ping(payload))),
        Message::Pong(payload) => Ok(Some(TungsteniteMessage::Pong(payload))),
        Message::Close(frame) => Ok(Some(TungsteniteMessage::Close(frame.map(|frame| {
            TungsteniteCloseFrame {
                code: map_close_code_to_tungstenite(frame.code),
                reason: frame.reason.to_string().into(),
            }
        })))),
    }
}

fn map_upstream_message(message: TungsteniteMessage) -> Result<Option<Message>, String> {
    match message {
        TungsteniteMessage::Text(text) => {
            Ok(Some(Message::Text(Utf8Bytes::from(text.to_string()))))
        }
        TungsteniteMessage::Binary(binary) => Ok(Some(Message::Binary(binary))),
        TungsteniteMessage::Ping(payload) => Ok(Some(Message::Ping(payload))),
        TungsteniteMessage::Pong(payload) => Ok(Some(Message::Pong(payload))),
        TungsteniteMessage::Close(frame) => {
            Ok(Some(Message::Close(frame.map(|frame| CloseFrame {
                code: map_close_code_to_axum(frame.code),
                reason: Utf8Bytes::from(frame.reason.to_string()),
            }))))
        }
        TungsteniteMessage::Frame(_) => Ok(None),
    }
}

fn map_close_code_to_tungstenite(code: u16) -> TungsteniteCloseCode {
    match code {
        1000 => TungsteniteCloseCode::Normal,
        1001 => TungsteniteCloseCode::Away,
        1002 => TungsteniteCloseCode::Protocol,
        1003 => TungsteniteCloseCode::Unsupported,
        1005 => TungsteniteCloseCode::Status,
        1006 => TungsteniteCloseCode::Abnormal,
        1007 => TungsteniteCloseCode::Invalid,
        1008 => TungsteniteCloseCode::Policy,
        1009 => TungsteniteCloseCode::Size,
        1010 => TungsteniteCloseCode::Extension,
        1011 => TungsteniteCloseCode::Error,
        1012 => TungsteniteCloseCode::Restart,
        1013 => TungsteniteCloseCode::Again,
        1015 => TungsteniteCloseCode::Tls,
        other => TungsteniteCloseCode::Library(other),
    }
}

fn map_close_code_to_axum(code: TungsteniteCloseCode) -> u16 {
    match code {
        TungsteniteCloseCode::Normal => 1000,
        TungsteniteCloseCode::Away => 1001,
        TungsteniteCloseCode::Protocol => 1002,
        TungsteniteCloseCode::Unsupported => 1003,
        TungsteniteCloseCode::Status => 1005,
        TungsteniteCloseCode::Abnormal => 1006,
        TungsteniteCloseCode::Invalid => 1007,
        TungsteniteCloseCode::Policy => 1008,
        TungsteniteCloseCode::Size => 1009,
        TungsteniteCloseCode::Extension => 1010,
        TungsteniteCloseCode::Error => 1011,
        TungsteniteCloseCode::Restart => 1012,
        TungsteniteCloseCode::Again => 1013,
        TungsteniteCloseCode::Tls => 1015,
        TungsteniteCloseCode::Reserved(value)
        | TungsteniteCloseCode::Library(value)
        | TungsteniteCloseCode::Iana(value) => value,
        TungsteniteCloseCode::Bad(value) => value,
    }
}
