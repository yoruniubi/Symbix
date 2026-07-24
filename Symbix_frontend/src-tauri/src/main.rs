// Prevents additional console window on Windows in release, DO NOT REMOVE!!
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

fn main() {
    // 设置 AppUserModelID，使 Windows 通知显示应用名称和图标而非 "Windows PowerShell"
    #[cfg(target_os = "windows")]
    {
        use std::ffi::OsStr;
        use std::os::windows::ffi::OsStrExt;

        // 需与 tauri.conf.json 中的 identifier 一致
        let aumid: Vec<u16> = OsStr::new("com.frank.symbix")
            .encode_wide()
            .chain(std::iter::once(0))
            .collect();

        unsafe {
            extern "system" {
                fn SetCurrentProcessExplicitAppUserModelID(pcwszAppID: *const u16) -> i32;
            }
            SetCurrentProcessExplicitAppUserModelID(aumid.as_ptr());
        }
    }

    symbix_lib::run()
}
