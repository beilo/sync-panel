"""PyInstaller 入口 — 绝对导入 sync_panel.cli.main()。

PyInstaller 把 cli.py 当脚本直接执行时, 相对导入 (.config etc.) 会炸。
此文件在 sync_panel 包同级目录, 通过绝对导入解决。
"""

from sync_panel.cli import main

if __name__ == "__main__":
    import sys
    sys.exit(main())
