use std::collections::HashMap;
use std::path::Path;

/// 后端打包产物是否存在(有文件)。
/// dev 环境可能还没跑过 PyInstaller(build.rs 只会建空占位目录),
/// 此时资源映射必然为空 —— 结构断言应跳过而不是报错。
fn backend_built() -> bool {
    let dir = Path::new(env!("CARGO_MANIFEST_DIR")).join("../../backend/dist/SymbixBackend");
    dir.is_dir()
        && std::fs::read_dir(&dir)
            .map(|mut d| d.next().is_some())
            .unwrap_or(false)
}

/// 把一份 resources 映射解析成目标路径列表(统一用 `/`,忽略平台差异)
fn resolve(pattern: &str, dest: &str) -> Vec<String> {
    let map = HashMap::from([(pattern.to_string(), dest.to_string())]);
    let mut targets: Vec<String> = tauri::utils::resources::ResourcePaths::from_map(&map, true)
        .iter()
        .flatten()
        .map(|r| r.target().to_string_lossy().replace('\\', "/"))
        .collect();
    targets.sort();
    targets
}

fn head(targets: &[String]) -> String {
    let n = targets.len().min(5);
    format!("共 {} 项,前 {} 项: {:?}", targets.len(), n, &targets[..n])
}

/// 目录形式:必须保留 `_internal/` 结构,后端 exe 落在 `backend/` 根下
#[test]
fn backend_dir_mapping_keeps_internal_tree() {
    if !backend_built() {
        eprintln!("skip: backend/dist/SymbixBackend 还没构建(未跑 PyInstaller),跳过结构断言");
        return;
    }
    let targets = resolve("../../backend/dist/SymbixBackend", "backend");

    assert!(
        !targets.is_empty(),
        "资源映射没解析出任何文件 —— backend/dist/SymbixBackend 还没构建?"
    );
    assert!(
        targets
            .iter()
            .any(|t| t.ends_with("SymbixBackend.exe") || t.ends_with("SymbixBackend")),
        "映射里没有后端可执行文件;{}",
        head(&targets)
    );
    assert!(
        targets.iter().any(|t| t.starts_with("backend/_internal/")),
        "onedir 的 _internal/ 结构丢了;{}",
        head(&targets)
    );
}

/// 反面教材:同样的内容写成 glob 会被**拍平**,`_internal/` 整棵树消失。
/// 这个测试是故意断言「结构会丢」的,用来解释 tauri.conf.json 为什么不能用 glob。
#[test]
fn glob_mapping_flattens_tree() {
    if !backend_built() {
        eprintln!("skip: backend/dist/SymbixBackend 还没构建(未跑 PyInstaller),跳过 glob 断言");
        return;
    }
    let targets = resolve("../../backend/dist/SymbixBackend/**/*", "backend");

    assert!(!targets.is_empty(), "glob 没匹配到任何文件");
    assert!(
        !targets.iter().any(|t| t.starts_with("backend/_internal/")),
        "glob 竟然保留了目录结构?那这个测试的结论需要重写;{}",
        head(&targets)
    );
}