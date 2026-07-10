"""应用唯一入口：启动 Tkinter 主窗口。"""

from src.gui.app_bootstrap import configure_runtime_environment, create_root, enable_high_dpi_mode

configure_runtime_environment()

from src.gui.main_window import MainWindow


def main() -> None:
    enable_high_dpi_mode()
    root = create_root()
    MainWindow(root)
    root.deiconify()
    root.mainloop()


if __name__ == "__main__":
    main()
