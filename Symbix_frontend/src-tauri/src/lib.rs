// Learn more about Tauri commands at https://tauri.app/develop/calling-rust/
#[tauri::command]
fn greet(name: &str) -> String {
    format!("Hello, {}! You've been greeted from Rust!", name)
}

/// 托盘菜单文案国际化:前端语言切换时调用,用对应语言的文案重建菜单。
/// locale 只认 "en" / 其它一律按中文(与前端 AppLocale 对齐)。
#[tauri::command]
fn set_tray_locale(app: tauri::AppHandle, locale: String) -> Result<(), String> {
    let en = locale == "en";
    let (hide, show, quit) = if en {
        ("Hide", "Show", "Quit")
    } else {
        ("隐藏", "显示", "退出")
    };
    let hide_item = MenuItemBuilder::with_id("hide", hide)
        .build(&app)
        .map_err(|e| e.to_string())?;
    let show_item = MenuItemBuilder::with_id("show", show)
        .build(&app)
        .map_err(|e| e.to_string())?;
    let quit_item = MenuItemBuilder::with_id("quit", quit)
        .build(&app)
        .map_err(|e| e.to_string())?;
    let menu = MenuBuilder::new(&app)
        .item(&hide_item)
        .item(&show_item)
        .separator()
        .item(&quit_item)
        .build()
        .map_err(|e| e.to_string())?;
    app.tray_by_id("main").ok_or("tray not found")?.set_menu(Some(menu)).map_err(|e| e.to_string())?;
    Ok(())
}

mod backend;

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

/// 把桌宠窗长期钉在「置顶层」最前面。
///
/// 背景:`tauri.conf.json` 的 `alwaysOnTop` 只在窗口创建时调一次
/// `SetWindowPos(HWND_TOPMOST)`,此后不再管。而任务栏自身也是置顶窗口 ——
/// 同一个置顶层内按“最近激活”排序,于是点一下任务栏(或任务栏缩略图、通知)
/// 就会把桌宠压到任务栏下面,按完 Win+D 再恢复也回不到最前。
///
/// 注意这条路走不了 `window.set_always_on_top(true)`:Tao 的
/// `WindowFlags::apply_diff` 在标志位没变化时直接 `return`,不会调 `SetWindowPos`,
/// 重复设同一个值等于空操作。所以这里自己直接调,并带上 `SWP_NOACTIVATE`
/// 保证只改层级、不抢焦点。
#[cfg(target_os = "windows")]
mod pet_zorder {
    use core::ffi::c_void;
    use std::time::Duration;
    use windows::Win32::Foundation::HWND;
    use windows::Win32::UI::WindowsAndMessaging::{
        SetWindowPos, HWND_TOPMOST, SWP_NOACTIVATE, SWP_NOMOVE, SWP_NOSIZE,
    };

    /// 重申间隔:间隔太大重现“被压住”的窗口期,太小则与其它置顶窗反复抢层级
    const REASSERT_INTERVAL: Duration = Duration::from_millis(2000);

    /// 起一个后台线程周期性重申置顶。
    ///
    /// `hwnd` 内部的裸指针不是 Send,这里只把地址以 `isize` 带进线程再还原;
    /// 窗口自身生命周期由 Tauri 管,句柄在窗口存活期间不会变。
    pub fn keep_on_top(hwnd: HWND) {
        let raw = hwnd.0 as isize;
        let spawned = std::thread::Builder::new()
            .name("pet-zorder".into())
            .spawn(move || loop {
                std::thread::sleep(REASSERT_INTERVAL);
                // 窗口隐藏时调这个也安全:没有 SWP_SHOWWINDOW 就不会把窗显出来
                unsafe {
                    let _ = SetWindowPos(
                        HWND(raw as *mut c_void),
                        Some(HWND_TOPMOST),
                        0,
                        0,
                        0,
                        0,
                        SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE,
                    );
                }
            });
        if let Err(e) = spawned {
            eprintln!("[pet-zorder] 置顶线程启动失败: {e}");
        }
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
        .manage(backend::BackendState::default())
        .invoke_handler(tauri::generate_handler![greet, backend::backend_status, set_tray_locale])
        .setup(|app| {
            // 接管后端生命周期:已在跑就只观察,否则自己拉起并等它就绪。
            // 放最前面是为了让第一条 backend-status 事件(至少 starting)早于
            // 前端挂载,前端拿到的状态不会是空字符串。
            backend::launch(app.handle().clone());

            // 确保 Windows 上透明窗口生效
            #[cfg(target_os = "windows")]
            {
                let window = app.get_webview_window("main").unwrap();
                window.set_decorations(false).unwrap();
                // 桌宠需长期压在任务栏之上,原因见 pet_zorder 模块注释
                if let Ok(hwnd) = window.hwnd() {
                    pet_zorder::keep_on_top(hwnd);
                }
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

            // 创建系统托盘(带 id,便于 set_tray_locale 里 tray_by_id 找到后重建菜单)
            let _tray = TrayIconBuilder::with_id("main")
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
        .build(tauri::generate_context!())
        .expect("error while building tauri application")
        .run(|app, event| {
            // 只有走到退出(托盘「退出」、或系统关进程)才收后端;
            // 关窗口只是 hide,后端要继续活着
            if let tauri::RunEvent::Exit = event {
                backend::shutdown(app);
            }
        });
}
