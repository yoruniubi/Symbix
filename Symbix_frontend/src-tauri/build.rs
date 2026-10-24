use std::path::PathBuf;

fn main() {
    // bundle.resources 指向打包产物 backend/dist/SymbixBackend,tauri-build 在**每次编译**
    // (包括 tauri dev 的 debug 构建)都会校验它存在;但 dev 下后端走源码 python
    // (Rust 侧 plan() 优先源码解释器),根本用不到这个目录。
    // 所以 debug 构建时先建一个空占位目录(在 .gitignore 的 backend/dist/ 覆盖范围内,
    // 不会弄脏 git);release 不建 —— 缺失就该在这里报错,免得打出没有后端的空包。
    if std::env::var("PROFILE").as_deref() == Ok("debug") {
        let dir = PathBuf::from(std::env::var("CARGO_MANIFEST_DIR").unwrap())
            .join("../../backend/dist/SymbixBackend");
        let _ = std::fs::create_dir_all(&dir);
    }
    tauri_build::build()
}
