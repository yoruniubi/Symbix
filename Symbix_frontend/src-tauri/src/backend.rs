use std::io::{Read, Write};
use std::net::{SocketAddr, TcpStream};
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::time::{Duration, Instant};

use serde::Serialize;
use tauri::{AppHandle, Emitter, Manager};

/// 端口不再写死:每次启动在这个区间里挑一个空闲的(见 `choose_port`)。
/// 8000 仍然优先 —— 手动 `python main.py`、curl 调试都习惯它,只有被占才往上让;
/// 区间走完还挑不到,就交给系统随便分一个。前端拿到的端口来自 `status.url`。
const PORT_BASE: u16 = 8000;
const PORT_TRIES: u16 = 20;

/// 单次探活超时。后端没起来时 connect 会立刻被拒,给长一点只是兜底。
const PROBE_TIMEOUT: Duration = Duration::from_millis(600);
/// 扫端口区间时的超时。区间里可能蹲着「只监听、不答话」的服务,扫 20 个不能让
/// 启动卡住,所以比 PROBE_TIMEOUT 短。
const SCAN_TIMEOUT: Duration = Duration::from_millis(200);

/// 「是不是自家后端」的标记:`GET /` 的固定返回里有这一段
/// (`backend/main.py` 的 `root()`)。8000 上蹲着别人的 HTTP 服务是常事,
/// 只看状态码会把别人认成自己 —— 然后前端所有请求都打到别人身上。
const SYMBIX_MARKER: &[u8] = b"Symbix API";

fn url_for_port(port: u16) -> String {
    format!("http://127.0.0.1:{port}")
}
/// 拉起后等它上线的最长时间。onedir 冷启动实测 1-3 秒,首次建库会慢一些。
const WAIT_TOTAL: Duration = Duration::from_secs(60);
const POLL_INTERVAL: Duration = Duration::from_millis(300);
/// 后端状态。前端挂载时用 `backend_status` 主动拉一次 —— 事件是在 webview
/// 加载完之前就发出去的,只靠 listen 会漏掉第一条。
#[derive(Clone, Serialize)]
pub struct BackendStatus {
    /// external / starting / ready / exited / failed / missing
    pub state: String,
    /// true 表示这个后端是本进程拉起来的,退出时要收尸
    pub managed: bool,
    /// 实际使用的 API base,由选中的端口算出
    pub url: String,
    pub detail: Option<String>,
}

impl Default for BackendStatus {
    /// 拉起之前:url 留空。端口是 `launch()` 里才选的,前端读到空值就先用自己的
    /// 默认值(纯浏览器 `npm run dev` 时也走这条)。
    fn default() -> Self {
        Self { state: String::new(), managed: false, url: String::new(), detail: None }
    }
}

#[derive(Default)]
pub struct BackendState {
    child: Mutex<Option<Child>>,
    status: Mutex<BackendStatus>,
    /// 本次会话的端口:`launch()` 选好后写进来,子进程用 `SYMBIX_PORT` 收到同一个值
    port: Mutex<u16>,
}

/// 记状态 + 广播给前端。url 按 state.port 现算 —— 端口是动态的,不能写死。
fn set_status(app: &AppHandle, state: &str, managed: bool, detail: Option<String>) {
    let backend = app.state::<BackendState>();
    let status = BackendStatus {
        state: state.into(),
        managed,
        url: url_for_port(*backend.port.lock().unwrap()),
        detail,
    };
    println!(
        "[backend] state={} url={} managed={} {:?}",
        status.state, status.url, status.managed, status.detail
    );
    *backend.status.lock().unwrap() = status.clone();
    let _ = app.emit("backend-status", &status);
}

/// 前端挂载时调,拿当前状态(可能已经 ready 了)
#[tauri::command]
pub fn backend_status(app: AppHandle) -> BackendStatus {
    app.state::<BackendState>().status.lock().unwrap().clone()
}

/// 探一个端口的归属。
///
/// 只做 TCP connect 不够:uvicorn 是「先 bind 端口、再跑 lifespan」,路由就绪前
/// 端口就是通的,那会儿前端发请求会被重置连接。所以真发一次最小请求
/// (HTTP/1.0 + Connection: close,答完就断开,不占连接),并校验响应里的
/// [`SYMBIX_MARKER`] —— 「连得上」和「是我们的人」是两件事。
enum Reach {
    /// 没人监听(connect 被拒),端口可以直接用
    Free,
    /// 已经有 Symbix 后端在服务 → 接管
    Symbix,
    /// 有东西在监听但不是 Symbix(别人的服务、只监听不答话的黑洞)→ 换端口
    Foreign,
}

fn probe_port(port: u16, timeout: Duration) -> Reach {
    let addr = SocketAddr::from(([127, 0, 0, 1], port));
    let Ok(mut sock) = TcpStream::connect_timeout(&addr, timeout) else {
        // 被拒 = 没人监听。真超时(防火墙黑洞)也先当 Free,后面 bind 还会再挡一次。
        return Reach::Free;
    };
    let _ = sock.set_read_timeout(Some(timeout));
    let _ = sock.set_write_timeout(Some(timeout));
    let req = b"GET / HTTP/1.0\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n";
    if sock.write_all(req).is_err() {
        return Reach::Foreign;
    }
    // 身份标记在响应体里,所以这次要比只读状态行多读一点;读到 EOF 或 2KB 为止。
    let mut buf: Vec<u8> = Vec::with_capacity(256);
    let mut chunk = [0u8; 256];
    loop {
        match sock.read(&mut chunk) {
            Ok(0) => break,
            Ok(n) => {
                buf.extend_from_slice(&chunk[..n]);
                if buf.len() >= 2048 {
                    break;
                }
            }
            Err(_) => break,
        }
    }
    if !buf.starts_with(b"HTTP/1.1 200") && !buf.starts_with(b"HTTP/1.0 200") {
        return Reach::Foreign;
    }
    if buf.windows(SYMBIX_MARKER.len()).any(|w| w == SYMBIX_MARKER) {
        Reach::Symbix
    } else {
        Reach::Foreign
    }
}

/// 端口是否已被占用。用 bind 试 —— 不依赖对方愿不愿意答话,只要有人在监听就失败。
fn port_in_use(port: u16) -> bool {
    std::net::TcpListener::bind(("127.0.0.1", port)).is_err()
}

/// 选端口的结论
enum Choice {
    /// 端口空着,拉起后端时用 `SYMBIX_PORT` 传进去
    Spawn(u16),
    /// 已经有 Symbix 在服务 → 接管,不再拉起
    Adopt(u16),
}

/// 挑端口:优先 8000,被占就顺着往上找;区间里全是别人的服务,再让系统分一个。
///
/// 两趟是有意的:先整段找**已经跑着的 Symbix**(手动 `python main.py` 起的、
/// 或上次没退干净的,可能蹲在 8001 而不是 8000),找到就接管、不重复拉起;
/// 确认没有才挑空闲端口自己拉。
fn choose_port() -> Choice {
    for offset in 0..PORT_TRIES {
        let port = PORT_BASE + offset;
        if matches!(probe_port(port, SCAN_TIMEOUT), Reach::Symbix) {
            println!("[backend] 127.0.0.1:{port} 已有 Symbix 后端在服务");
            return Choice::Adopt(port);
        }
    }
    for offset in 0..PORT_TRIES {
        let port = PORT_BASE + offset;
        if !port_in_use(port) {
            return Choice::Spawn(port);
        }
        println!("[backend] 127.0.0.1:{port} 被别的程序占用,跳过");
    }
    // 连号都不够用(几乎不可能):让系统分配一个,uvicorn 会把实际端口打进日志
    let port = std::net::TcpListener::bind("127.0.0.1:0")
        .and_then(|l| l.local_addr())
        .map(|a| a.port())
        .unwrap_or(0);
    println!("[backend] 候选区间全满,改用系统分配的端口 {port}");
    Choice::Spawn(port)
}

/// 当前会话端口的探活(就绪判定的唯一依据)
fn probe(app: &AppHandle) -> bool {
    let port = *app.state::<BackendState>().port.lock().unwrap();
    matches!(probe_port(port, PROBE_TIMEOUT), Reach::Symbix)
}

fn exe_name() -> &'static str {
    if cfg!(windows) { "SymbixBackend.exe" } else { "SymbixBackend" }
}

fn push_unique(list: &mut Vec<PathBuf>, path: PathBuf) {
    if !list.iter().any(|p| p == &path) {
        list.push(path);
    }
}

/// 后端可执行文件的候选位置,按优先级排。
///
/// 打包后 resource_dir() 在三平台上分别解析到:
///   Windows → exe 所在目录(NSIS 的 $INSTDIR,resources 就落这儿)
///   Linux   → /usr/lib/<productName>
///   macOS   → Symbix.app/Contents/Resources
/// 三处都是 `bundle.resources` 的目标根,所以统一拼 `backend/<exe>`。
fn candidates(app: &AppHandle) -> Vec<PathBuf> {
    let mut list = Vec::new();
    let name = exe_name();

    // 1) 打包后
    if let Ok(dir) = app.path().resource_dir() {
        push_unique(&mut list, dir.join("backend").join(name));
    }
    // 2) 主程序旁边(手动拷 dist 进去、或以后换 sidecar 布局时的兜底)
    if let Ok(exe) = std::env::current_exe() {
        if let Some(dir) = exe.parent() {
            push_unique(&mut list, dir.join("backend").join(name));
            push_unique(&mut list, dir.join(name));
        }
    }
    // 3) 开发态:`npm run tauri dev` 时直接跑仓库里的构建产物
    let dev = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("..")
        .join("..")
        .join("backend")
        .join("dist")
        .join("SymbixBackend")
        .join(name);
    push_unique(&mut list, dev.canonicalize().unwrap_or(dev));

    list
}

/// 仓库里的 backend/(开发态用)。安装后的机器上通常不存在。
fn repo_backend_dir() -> Option<PathBuf> {
    let dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("..")
        .join("..")
        .join("backend");
    if dir.is_dir() { Some(dir) } else { None }
}

/// 0) SYMBIX_BACKEND_CMD:显式指定启动命令,开发时指源码最方便,例如
///    `SYMBIX_BACKEND_CMD=E:\Anaconda\envs\Symbix\python.exe -u main.py`。
///    工作目录优先 SYMBIX_BACKEND_CWD,否则退到仓库 backend/。
///    (端口由 launch() 统一用 SYMBIX_PORT 注入,这里不用管)
fn custom_command() -> Option<(Command, String)> {
    let raw = std::env::var("SYMBIX_BACKEND_CMD").ok()?;
    let mut parts = raw.split_whitespace();
    let program = parts.next()?;
    let args: Vec<&str> = parts.collect();
    let mut cmd = Command::new(program);
    cmd.args(&args);
    if let Some(dir) = custom_cwd() {
        cmd.current_dir(dir);
    }
    let desc = format!("{} {}", program, args.join(" "));
    Some((cmd, desc.trim().to_string()))
}

fn custom_cwd() -> Option<PathBuf> {
    if let Ok(dir) = std::env::var("SYMBIX_BACKEND_CWD") {
        let path = PathBuf::from(dir);
        if path.is_dir() {
            return Some(path);
        }
    }
    repo_backend_dir().or_else(|| std::env::current_dir().ok())
}

/// dev 态解释器探测用的最小依赖集 —— 少了任何一个,后端都会在 import 阶段就死。
/// 特意带上 rank_bm25:它是「本机装了、但 PATH 上那个 python 没有」的典型
/// (`Symbix_sdk/memory/memory_store.py` 模块级 import,最先炸的就是它)。
#[cfg(debug_assertions)]
const PY_DEPS_PROBE: &str = "import fastapi, uvicorn, rank_bm25";

/// 2) 开发态兜底:直接跑源码,改了 Python 不用重新打包。
///    解释器按顺序找 `SYMBIX_PY` > `python` > `python3` > 仓库里的 `.venv`/`venv`,
///    每个都**先真 import 一遍核心依赖**,只有跑得起来的才用 —— 否则会出现
///    「起了又秒退」,或者更糟:用错解释器把后端跑成另一个状态。全都不行就退回 exe。
#[cfg(debug_assertions)]
fn python_command() -> Option<(Command, String)> {
    let dir = repo_backend_dir()?;
    if !dir.join("main.py").is_file() {
        println!("[backend] 源码态跳过:{} 下没有 main.py", dir.display());
        return None;
    }
    for python in python_candidates() {
        match probe_python(&python, &dir) {
            Ok(true) => {
                let mut cmd = Command::new(&python);
                // -u:关掉 stdout 缓冲,日志实时出现在 tauri dev 的终端里
                cmd.arg("-u").arg("main.py").current_dir(&dir);
                println!("[backend] 源码态使用解释器 {python}");
                return Some((cmd, format!("{python} -u main.py")));
            }
            Ok(false) => println!("[backend] {python} 缺后端依赖,跳过(可用 SYMBIX_PY 指定)"),
            Err(e) => println!("[backend] {python} 不可用: {e}"),
        }
    }
    println!("[backend] 没找到可用的 Python 解释器,退回打包好的 exe");
    None
}

#[cfg(debug_assertions)]
fn python_candidates() -> Vec<String> {
    let mut list = Vec::new();
    if let Ok(exe) = std::env::var("SYMBIX_PY") {
        list.push(exe);
    }
    for name in ["python", "python3"] {
        list.push(name.to_string());
    }
    if let Some(dir) = repo_backend_dir() {
        for rel in [
            ".venv/Scripts/python.exe",
            ".venv/bin/python",
            "venv/Scripts/python.exe",
            "venv/bin/python",
        ] {
            let path = dir.join(rel);
            if path.is_file() {
                list.push(path.display().to_string());
            }
        }
    }
    push_unique_str(&mut list);
    for path in conda_env_pythons() {
        list.push(path);
    }
    push_unique_str(&mut list);
    list
}

/// conda 环境兜底:只在 PATH 上那些目录旁边找 **名字以 Symbix 开头** 的环境
/// (`<conda>/envs/Symbix*`)。故意做得这么窄 —— 只认项目自己的环境,不会误选
/// 到别人的环境,也不会为了探测去遍历几十个 env 拖慢启动。
#[cfg(debug_assertions)]
fn conda_env_pythons() -> Vec<String> {
    let mut found: Vec<String> = Vec::new();
    let path = std::env::var_os("PATH").unwrap_or_default();
    for dir in std::env::split_paths(&path) {
        // PATH 里 conda 根目录会以 `<root>` / `<root>/Scripts` 等形式出现,两种都算。
        // 用 parent() 而不是 join("..") —— 后者会让同一个环境出现两种写法,
        // 字符串去重就失效了,白多探几次。
        let mut bases = vec![dir.clone()];
        if let Some(parent) = dir.parent() {
            bases.push(parent.to_path_buf());
        }
        for base in bases {
            let Ok(entries) = std::fs::read_dir(base.join("envs")) else {
                continue;
            };
            let mut envs: Vec<PathBuf> = entries.flatten().map(|e| e.path()).collect();
            envs.sort();
            for env in envs {
                let hit = env
                    .file_name()
                    .map(|n| n.to_string_lossy().starts_with("Symbix"))
                    .unwrap_or(false);
                if !hit {
                    continue;
                }
                let exe = env.join(if cfg!(windows) { "python.exe" } else { "bin/python" });
                if exe.is_file() {
                    found.push(exe.display().to_string());
                }
            }
        }
    }
    push_unique_str(&mut found);
    found.truncate(4);
    found
}

#[cfg(debug_assertions)]
fn push_unique_str(list: &mut Vec<String>) {
    let mut seen: Vec<String> = Vec::new();
    list.retain(|item| {
        if seen.contains(item) {
            false
        } else {
            seen.push(item.clone());
            true
        }
    });
}

/// 真跑一次 import,只认退出码 —— 比解析 `--version` 或者猜路径靠谱得多
#[cfg(debug_assertions)]
fn probe_python(python: &str, cwd: &std::path::Path) -> std::io::Result<bool> {
    let status = Command::new(python)
        .arg("-c")
        .arg(PY_DEPS_PROBE)
        .current_dir(cwd)
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .status()?;
    Ok(status.success())
}

#[cfg(test)]
mod tests {
    use std::io::{Read, Write};
    use std::time::Duration;

    /// 造一个假 HTTP 服务:接受连接、堵回 `body`,用它验证探活的身份判定。
    /// 返回端口;线程随测试进程一起消亡,不用回收。
    fn fake_server(body: &'static str) -> u16 {
        let listener = std::net::TcpListener::bind("127.0.0.1:0").expect("bind 失败");
        let port = listener.local_addr().unwrap().port();
        std::thread::spawn(move || {
            for sock in listener.incoming() {
                let Ok(mut sock) = sock else { break };
                let mut buf = [0u8; 512];
                let _ = sock.read(&mut buf);
                let resp = format!(
                    "HTTP/1.1 200 OK\r\nContent-Length: {}\r\nContent-Type: application/json\r\nConnection: close\r\n\r\n{}",
                    body.len(),
                    body
                );
                let _ = sock.write_all(resp.as_bytes());
            }
        });
        port
    }

    /// `cargo test --lib probe_port -- --nocapture`
    /// 三种归属必须分清楚 —— 把别人的 200 当成自家后端是最坑的那种错。
    #[test]
    fn probe_port_tells_symbix_apart_from_others() {
        let free = std::net::TcpListener::bind("127.0.0.1:0").unwrap();
        let free_port = free.local_addr().unwrap().port();
        drop(free);
        let got = super::probe_port(free_port, Duration::from_millis(300));
        println!("[探测] 空闲 {free_port} -> Free? {}", matches!(got, super::Reach::Free));
        assert!(matches!(got, super::Reach::Free), "空闲端口应当判 Free");

        let foreign_port = fake_server("{\"hello\":\"world\"}");
        let got = super::probe_port(foreign_port, Duration::from_millis(500));
        println!("[探测] 别人的 200 {foreign_port} -> Foreign? {}", matches!(got, super::Reach::Foreign));
        assert!(matches!(got, super::Reach::Foreign), "别人的服务不该被认成自家后端");

        let our_port = fake_server("{\"status\":\"ok\",\"service\":\"Symbix API\",\"version\":\"0.1.0\"}");
        let got = super::probe_port(our_port, Duration::from_millis(500));
        println!("[探测] 自家后端 {our_port} -> Symbix? {}", matches!(got, super::Reach::Symbix));
        assert!(matches!(got, super::Reach::Symbix), "带 service 标记的应当认出来");
    }

    /// `cargo test --lib choose_port -- --nocapture`
    /// 8000 被别的程序占着(哑监听,只 bind 不答话)时必须换端口。
    #[test]
    fn choose_port_skips_occupied_base() {
        let Ok(hold) = std::net::TcpListener::bind(("127.0.0.1", super::PORT_BASE)) else {
            println!("[跳过] {} 已被占,做不了占用测试", super::PORT_BASE);
            return;
        };
        let choice = super::choose_port();
        match choice {
            super::Choice::Spawn(port) => {
                println!("[选择] 8000 被占时选了 {port}");
                assert_ne!(port, super::PORT_BASE, "8000 被占时不该再选它");
            }
            super::Choice::Adopt(port) => panic!("哑监听不该被认成 Symbix(port {port})"),
        }
        drop(hold);
    }

    /// 诊断用:`cargo test --lib python_candidates -- --nocapture`
    /// 它会打印 dev 态按什么顺序找解释器、哪个真能跑 ——
    /// 遇到「后端起了又秒退」先看这个输出,比翻日志快。
    #[test]
    fn python_candidates_are_ordered_and_unique() {
        let dir = super::repo_backend_dir().expect("没找到仓库 backend 目录");
        let list = super::python_candidates();
        assert!(!list.is_empty(), "一个解释器候选都没有");
        let mut sorted = list.clone();
        sorted.sort();
        sorted.dedup();
        assert_eq!(sorted.len(), list.len(), "候选列表里有重复");
        println!("[候选] {list:?}");
        for python in &list {
            let ok = super::probe_python(python, &dir).unwrap_or(false);
            println!("[探测] {:<52} {}", python, if ok { "可用" } else { "不可用" });
        }
    }
}

/// 3) 打包出来的 exe:资源目录 / 主程序旁 / 仓库里的构建产物
fn exe_commands(app: &AppHandle) -> Vec<(Command, String)> {
    let cands = candidates(app);
    let found = cands.iter().find(|p| p.is_file()).cloned();
    let Some(exe) = found else {
        eprintln!("[backend] 没找到打包好的后端 exe,找过:");
        for path in &cands {
            eprintln!("    {}", path.display());
        }
        return Vec::new();
    };
    let mut cmd = Command::new(&exe);
    if let Some(dir) = exe.parent() {
        cmd.current_dir(dir);
    }
    vec![(cmd, exe.display().to_string())]
}

/// 启动方案,按优先级排队。注意 `python main.py` 排在 exe 前面:开发态改源码
/// 立即生效,不会被一个过期的构建产物盖掉;要测打包产物就设
/// SYMBIX_BACKEND_EXE。
fn plan(app: &AppHandle) -> Vec<(Command, String)> {
    let mut list = Vec::new();
    if let Some(item) = custom_command() {
        list.push(item);
    }
    if let Ok(exe) = std::env::var("SYMBIX_BACKEND_EXE") {
        let path = PathBuf::from(exe);
        let mut cmd = Command::new(&path);
        if let Some(dir) = path.parent() {
            cmd.current_dir(dir);
        }
        let desc = path.display().to_string();
        list.push((cmd, desc));
    }
    #[cfg(debug_assertions)]
    {
        if let Some(item) = python_command() {
            list.push(item);
        }
    }
    list.extend(exe_commands(app));
    list
}

/// 把子进程的 stdout/stderr 落到 app_log_dir()/backend.log
fn attach_log(cmd: Command, app: &AppHandle) -> Command {
    let Ok(dir) = app.path().app_log_dir() else {
        return cmd;
    };
    let _ = std::fs::create_dir_all(&dir);
    let log = dir.join("backend.log");
    let Ok(file) = std::fs::OpenOptions::new().create(true).append(true).open(&log) else {
        return cmd;
    };
    let Ok(clone) = file.try_clone() else {
        return cmd;
    };
    println!("[backend] 后端日志 -> {}", log.display());
    let mut cmd = cmd;
    cmd.stdout(Stdio::from(file));
    cmd.stderr(Stdio::from(clone));
    cmd
}

/// 拉起后端。已经在跑就不重复拉(也不记在自己名下,退出时不许杀)。
pub fn launch(app: AppHandle) {
    let choice = choose_port();
    let port = match choice {
        Choice::Adopt(p) | Choice::Spawn(p) => p,
    };
    *app.state::<BackendState>().port.lock().unwrap() = port;
    if let Choice::Adopt(_) = choice {
        println!("[backend] {} 已在服务,视为外部托管,不再拉起", url_for_port(port));
        set_status(&app, "external", false, None);
        return;
    }
    println!("[backend] 本次会话后端端口 {port}");

    let plans = plan(&app);
    if plans.is_empty() {
        let hint = "找不到后端:开发时请先 `python main.py`,或设 SYMBIX_BACKEND_CMD 指过去;
打包运行的包里应当有 backend/SymbixBackend";
        set_status(&app, "missing", false, Some(hint.into()));
        return;
    }

    // 依次试,谁先 spawn 成功就用谁(比如 python 不在 PATH 就自动退到 exe)
    let mut last_err: Option<String> = None;
    for (mut cmd, desc) in plans {
        // 端口用环境变量交给后端(main.py 读 SYMBIX_PORT),前后端只有一个来源;
        // 单独 `python main.py` 不带这个变量,依旧落回 8000。
        cmd.env("SYMBIX_PORT", port.to_string());
        // release:藏掉控制台黑窗(console=True 的后端会弹一个空黑框),日志改落到
        //          app_log_dir()/backend.log
        // dev:    照旧继承终端,后端日志直接混在 tauri dev 的输出里,方便调试
        if !cfg!(debug_assertions) {
            #[cfg(windows)]
            {
                use std::os::windows::process::CommandExt;
                const CREATE_NO_WINDOW: u32 = 0x0800_0000;
                cmd.creation_flags(CREATE_NO_WINDOW);
            }
            cmd = attach_log(cmd, &app);
        }
        match cmd.spawn() {
            Ok(child) => {
                println!("[backend] 已拉起 {desc} (pid {})", child.id());
                *app.state::<BackendState>().child.lock().unwrap() = Some(child);
                let detail = Some(desc);
                set_status(&app, "starting", true, detail);
                wait_ready(app);
                return;
            }
            Err(e) => {
                eprintln!("[backend] 拉起 {desc} 失败: {e}");
                last_err = Some(format!("{desc}: {e}"));
            }
        }
    }
    set_status(&app, "failed", true, last_err);
}

/// 后台等它就绪。进程提前挂掉就立刻报错,别让用户白等满 60 秒。
fn wait_ready(app: AppHandle) {
    let spawned = std::thread::Builder::new()
        .name("backend-wait".into())
        .spawn(move || {
            let start = Instant::now();
            loop {
                if probe(&app) {
                    println!("[backend] 就绪,用时 {:.1}s", start.elapsed().as_secs_f32());
                    set_status(&app, "ready", true, None);
                    return;
                }
                if let Some(detail) = exited_detail(&app) {
                    set_status(&app, "exited", true, Some(detail));
                    return;
                }
                if start.elapsed() > WAIT_TOTAL {
                    let detail = format!("等待 {}s 仍未就绪", WAIT_TOTAL.as_secs());
                    set_status(&app, "failed", true, Some(detail));
                    return;
                }
                std::thread::sleep(POLL_INTERVAL);
            }
        });
    if let Err(e) = spawned {
        eprintln!("[backend] 就绪探测线程起不来: {e}");
    }
}

/// 子进程已经退出了吗?退出就返回原因(端口被占、缺依赖、崩了都走这里)。
fn exited_detail(app: &AppHandle) -> Option<String> {
    let state = app.state::<BackendState>();
    let mut guard = state.child.lock().unwrap();
    match guard.as_mut().map(|child| child.try_wait()) {
        Some(Ok(Some(status))) => Some(format!("后端进程提前退出({status})")),
        Some(Err(e)) => Some(format!("后端进程状态异常: {e}")),
        _ => None,
    }
}

/// 退出时收尸。只管自己拉起来的那个(state=external 时 child 是 None)。
pub fn shutdown(app: &AppHandle) {
    let state = app.state::<BackendState>();
    let mut guard = state.child.lock().unwrap();
    let Some(mut child) = guard.take() else { return };
    let pid = child.id();
    println!("[backend] 退出,收掉 pid {pid}");
    // uvicorn / MCP server 都可能是它的子进程,/T 连根收,免得留下孤儿占着端口
    #[cfg(windows)]
    {
        let _ = Command::new("taskkill")
            .args(["/F", "/T", "/PID", &pid.to_string()])
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .status();
    }
    let _ = child.kill();
    let _ = child.wait();
}
