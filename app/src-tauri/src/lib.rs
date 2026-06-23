// AI Workspace 同步面板 — Tauri 后端 (薄壳)。
//
// 职责: 把前端请求转成对 sidecar (PyInstaller 打包的 sync-panel-cli) 的调用,
// 收 stdout JSON 原样回前端。不写业务逻辑。
//
// sidecar 单次调用模式: 调一次出一次 JSON 即退出, 无常驻进程。

use tauri_plugin_shell::ShellExt;

// 统一调用 sidecar, 返回 stdout 字符串 (已是 JSON)。
// 失败 (非零退出 / spawn 失败) -> Err(中文错误信息), 前端透传展示。
async fn run_sidecar(app: &tauri::AppHandle, args: Vec<String>) -> Result<String, String> {
    let sidecar = app
        .shell()
        .sidecar("sync-panel-cli")
        .map_err(|e| format!("无法定位 sidecar: {e}"))?
        .args(args);

    let output = sidecar
        .output()
        .await
        .map_err(|e| format!("sidecar 执行失败: {e}"))?;

    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr);
        return Err(format!(
            "sidecar 非零退出 (code={:?}): {stderr}",
            output.status.code()
        ));
    }
    Ok(String::from_utf8_lossy(&output.stdout).to_string())
}

// 把 sidecar 返回的 JSON 字符串解析成 serde_json::Value 回前端。
// 前端拿到的就是结构化对象。
async fn run_json(app: &tauri::AppHandle, args: Vec<String>) -> Result<serde_json::Value, String> {
    let out = run_sidecar(app, args).await?;
    serde_json::from_str(&out).map_err(|e| format!("sidecar 输出非合法 JSON: {e}\n原始输出: {out}"))
}

#[tauri::command]
async fn get_tree(app: tauri::AppHandle) -> Result<serde_json::Value, String> {
    run_json(&app, vec!["tree".into()]).await
}

#[tauri::command]
async fn read_file(
    app: tauri::AppHandle,
    which: String,
    rel: String,
) -> Result<serde_json::Value, String> {
    run_json(
        &app,
        vec![
            "read".into(),
            "--which".into(),
            which,
            "--rel".into(),
            rel,
        ],
    )
    .await
}

#[tauri::command]
async fn build_plan(app: tauri::AppHandle) -> Result<serde_json::Value, String> {
    run_json(&app, vec!["plan".into()]).await
}

#[tauri::command]
async fn apply_sync(app: tauri::AppHandle) -> Result<serde_json::Value, String> {
    run_json(&app, vec!["apply".into()]).await
}

#[tauri::command]
async fn target_status(
    app: tauri::AppHandle,
    target: String,
) -> Result<serde_json::Value, String> {
    run_json(&app, vec!["status".into(), "--target".into(), target]).await
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .invoke_handler(tauri::generate_handler![
            get_tree,
            read_file,
            build_plan,
            apply_sync,
            target_status
        ])
        .run(tauri::generate_context!())
        .expect("Tauri 应用启动失败");
}
