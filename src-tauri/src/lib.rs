//! The vcui shell: starts the voice engine, tells the window how to reach it,
//! and forwards the global shortcut that opens and closes the microphone.

use std::net::TcpListener;
use std::path::PathBuf;
use std::process::{Child, Command};
use std::sync::Mutex;

use serde::Serialize;
use tauri::{Emitter, Manager, RunEvent};
use tauri_plugin_global_shortcut::{Code, Modifiers, Shortcut, ShortcutState};

#[derive(Clone, Serialize)]
struct EngineConfig {
    url: String,
    token: String,
}

struct Engine {
    config: EngineConfig,
    child: Mutex<Option<Child>>,
}

#[tauri::command]
fn engine_config(engine: tauri::State<'_, Engine>) -> EngineConfig {
    engine.config.clone()
}

fn free_port() -> u16 {
    TcpListener::bind("127.0.0.1:0")
        .and_then(|listener| listener.local_addr())
        .map(|address| address.port())
        .unwrap_or(8765)
}

fn new_token() -> String {
    let mut bytes = [0u8; 24];
    getrandom::fill(&mut bytes).expect("the system random source is available");
    bytes.iter().map(|byte| format!("{byte:02x}")).collect()
}

/// How to start the engine:
/// - `VCUI_ENGINE_CMD`, when set, is run through the shell (any build);
/// - a debug build runs the engine from the repository with uv;
/// - a release build runs the packaged engine from the app's resources.
fn engine_command(app: &tauri::App, port: u16) -> Command {
    let port = port.to_string();
    if let Ok(custom) = std::env::var("VCUI_ENGINE_CMD") {
        let mut command = if cfg!(windows) {
            let mut command = Command::new("cmd");
            command.args(["/C", &custom]);
            command
        } else {
            let mut command = Command::new("sh");
            command.args(["-c", &custom]);
            command
        };
        command.env("VCUI_ENGINE_PORT", &port);
        return command;
    }
    if cfg!(debug_assertions) {
        let engine_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../engine");
        let mut command = Command::new("uv");
        command
            .arg("run")
            .arg("--project")
            .arg(engine_dir)
            .args(["vcui-engine", "--dev", "--port", &port]);
        return command;
    }
    let name = if cfg!(windows) { "vcui-engine.exe" } else { "vcui-engine" };
    let executable = app
        .path()
        .resource_dir()
        .map(|dir| dir.join("engine").join(name))
        .unwrap_or_else(|_| PathBuf::from(name));
    let mut command = Command::new(executable);
    command.args(["--port", &port]);
    if let Ok(log_dir) = app.path().app_log_dir() {
        if std::fs::create_dir_all(&log_dir).is_ok() {
            command.arg("--log-file").arg(log_dir.join("engine.log"));
        }
    }
    command
}

fn start_engine(app: &tauri::App, port: u16, token: &str) -> Option<Child> {
    let mut command = engine_command(app, port);
    // The token goes in the environment, not on the command line, where other
    // processes on the computer could read it.
    command.env("VCUI_TOKEN", token);
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        const CREATE_NO_WINDOW: u32 = 0x0800_0000;
        command.creation_flags(CREATE_NO_WINDOW);
    }
    match command.spawn() {
        Ok(child) => Some(child),
        Err(error) => {
            eprintln!("vcui: could not start the voice engine: {error}");
            None
        }
    }
}

fn stop_engine(app: &tauri::AppHandle) {
    if let Some(engine) = app.try_state::<Engine>() {
        if let Some(mut child) = engine.child.lock().ok().and_then(|mut guard| guard.take()) {
            let _ = child.kill();
            let _ = child.wait();
        }
    }
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let toggle = Shortcut::new(Some(Modifiers::SUPER.union(Modifiers::SHIFT)), Code::Space);
    let toggle_other = Shortcut::new(Some(Modifiers::CONTROL.union(Modifiers::SHIFT)), Code::Space);
    let shortcut = if cfg!(target_os = "macos") { toggle } else { toggle_other };

    let app = tauri::Builder::default()
        .plugin(
            tauri_plugin_global_shortcut::Builder::new()
                .with_handler(move |app, pressed, event| {
                    if pressed == &shortcut && event.state() == ShortcutState::Pressed {
                        let _ = app.emit("vcui://toggle", ());
                    }
                })
                .build(),
        )
        .setup(move |app| {
            use tauri_plugin_global_shortcut::GlobalShortcutExt;
            if let Err(error) = app.global_shortcut().register(shortcut) {
                eprintln!("vcui: could not register the global shortcut: {error}");
            }
            let port = free_port();
            let token = new_token();
            let child = start_engine(app, port, &token);
            app.manage(Engine {
                config: EngineConfig { url: format!("ws://127.0.0.1:{port}"), token },
                child: Mutex::new(child),
            });
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![engine_config])
        .build(tauri::generate_context!())
        .expect("error while building vcui");

    app.run(|app, event| {
        if let RunEvent::Exit = event {
            stop_engine(app);
        }
    });
}
