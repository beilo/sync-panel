# sync-panel

AI Workspace 同步面板 — 把共享技能/规则同步到各 AI 工具的 target 目录。

Tauri 桌面壳 + Python 引擎 (PyInstaller sidecar)。

## 构建

### 前置

- Node.js 22+
- Rust (stable)
- Python 3.13 + PyInstaller（见 `.build-venv/`）

### Mac (Apple Silicon)

```bash
# 1. 编译 Python sidecar
. .build-venv/bin/activate
python -m PyInstaller app/sync-panel-cli-aarch64-apple-darwin.spec \
  --distpath app/src-tauri/binaries --workpath /tmp/pyinstaller-build --noconfirm

# 2. 编译 Tauri 桌面应用
cd app
npm run build
npx @tauri-apps/cli build
```

产物：
- `.app`: `app/src-tauri/target/release/bundle/macos/sync-panel.app`
- `.dmg`: `app/src-tauri/target/release/bundle/dmg/sync-panel_0.1.0_aarch64.dmg`

### Windows

Mac 上无法交叉编译 PyInstaller sidecar（Python 生态限制）。需要 Windows 环境：

```powershell
# 1. 在 Windows 上编译 Python sidecar
python -m PyInstaller app/sync-panel-cli-x86_64-pc-windows-msvc.spec --noconfirm

# 2. 把产物复制到 app/src-tauri/binaries/sync-panel-cli-x86_64-pc-windows-msvc.exe

# 3. 编译 Tauri
cd app
npm run build
npx @tauri-apps/cli build
```

产物：`app/src-tauri/target/release/bundle/msi/sync-panel_0.1.0_x64_en-US.msi`

## 开发

```bash
cd app
npm run dev        # Vite 热更新，localhost:1420
npm test           # e2e 测试（真 sidecar）
```

## 架构

```
app/
├── src/           # React 前端 (TypeScript)
│   ├── App.tsx    # 三栏布局 + Sync 流程
│   ├── api.ts     # Tauri command 封装
│   └── components/
├── src-tauri/     # Rust 薄壳，转发前端请求到 sidecar
│   ├── src/lib.rs
│   └── binaries/  # PyInstaller sidecar
└── dist/          # Vite 构建产物，嵌入 Tauri app

sync_panel/        # Python 引擎
├── engine.py      # Plan 生成 + 执行
├── model.py       # 数据模型
└── cli.py         # CLI 入口
```
