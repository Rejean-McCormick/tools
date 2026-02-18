# main.py
from __future__ import annotations

import sys
import traceback
from tkinter import messagebox

from .gui import App


def install_sys_excepthook() -> None:
    def excepthook(exc_type, exc_value, exc_tb):
        tb_text = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        try:
            messagebox.showerror("Unhandled exception", tb_text)
        except Exception:
            print(tb_text, file=sys.stderr)

    sys.excepthook = excepthook


def main() -> None:
    install_sys_excepthook()
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
