// Learn more about Tauri commands at https://tauri.app/develop/calling-rust/
#[tauri::command]
fn greet(name: &str) -> String {
    format!("Hello, {}! You've been greeted from Rust!", name)
}

use tauri::{Manager, menu::{MenuBuilder, MenuItemBuilder}, tray::{TrayIconBuilder, TrayIconEvent, MouseButton}};

/// 让本机回环地址绕过系统代理。
///
/// 系统代理(如 Clash)会把 127.0.0.1 的请求也交给远端节点转发,而远端节点上的
/// 127.0.0.1 并不是本机,连不到本地后端,只能返回 502 空响应(前端表现为
/// "Unexpected end of JSON input")。这里只排除回环地址,外网请求仍照常走代理。
fn ensure_loopback_bypasses_proxy() {
    const LOOPBACK: [&str; 3] = ["127.0.0.1", "localhost", "::1"];
    for key in ["NO_PROXY", "no_proxy"] {
        let current = std::env::var(key).unwrap_or_default();
        let mut hosts: Vec<String> = current
            .split(',')
            .map(|s| s.trim().to_string())
            .filter(|s| !s.is_empty())
            .collect();
        for host in LOOPBACK {
            if !hosts.iter().any(|h| h == host) {
                hosts.push(host.to_string());
            }
        }
        std::env::set_var(key, hosts.join(","));
    }
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    // 必须早于任何 reqwest 客户端构造(tauri-plugin-http 每次请求都会新建客户端)
    ensure_loopback_bypasses_proxy();

    tauri::Builder::default()
        .plugin(tauri_plugin_notification::init())
        .plugin(tauri_plugin_http::init())
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_fs::init())
        .plugin(tauri_plugin_os::init())
        .invoke_handler(tauri::generate_handler![greet])
        .setup(|app| {
            // 确保 Windows 上透明窗口生效
            #[cfg(target_os = "windows")]
            {
                let window = app.get_webview_window("main").unwrap();
                window.set_decorations(false).unwrap();
            }

            // 创建托盘菜单
            let hide_item = MenuItemBuilder::with_id("hide", "隐藏").build(app)?;
            let show_item = MenuItemBuilder::with_id("show", "显示").build(app)?;
            let quit_item = MenuItemBuilder::with_id("quit", "退出").build(app)?;
            let menu = MenuBuilder::new(app)
                .item(&hide_item)
                .item(&show_item)
                .separator()
                .item(&quit_item)
                .build()?;

            // 创建系统托盘
            let _tray = TrayIconBuilder::new()
                .icon(app.default_window_icon().unwrap().clone())
                .menu(&menu)
                .on_menu_event(|app, event| {
                    match event.id().as_ref() {
                        "hide" => {
                            if let Some(window) = app.get_webview_window("main") {
                                let _ = window.hide();
                            }
                        }
                        "show" => {
                            if let Some(window) = app.get_webview_window("main") {
                                let _ = window.show();
                                let _ = window.set_focus();
                            }
                        }
                        "quit" => {
                            app.exit(0);
                        }
                        _ => {}
                    }
                })
                .on_tray_icon_event(|tray, event| {
                    if let TrayIconEvent::Click { button, .. } = event {
                        if button == MouseButton::Left {
                            let app = tray.app_handle();
                            if let Some(window) = app.get_webview_window("main") {
                                let _ = window.show();
                                let _ = window.set_focus();
                            }
                        }
                    }
                })
                .build(app)?;

            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
