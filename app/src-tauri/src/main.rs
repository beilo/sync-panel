// 桌面入口 — 转发到 lib.rs 的 run()。
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

fn main() {
    sync_panel_lib::run()
}
