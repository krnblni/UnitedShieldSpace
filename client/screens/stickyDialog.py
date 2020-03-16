import tkinter as tk
from client.utils.windowUtils import centerWindow


class StickyDialog(tk.Toplevel):
    def __init__(self, master=None, message="Error message"):
        super().__init__(master)
        self.minsize(300, 100)
        self.title(None)
        self.resizable(False, False)
        self.attributes("-topmost", "true")
        self.grab_set()
        centerWindow(self, 300, 100)
        tk.Label(self, text=message).pack(expand=True)

    def remove(self):
        self.grab_release()
        self.destroy()