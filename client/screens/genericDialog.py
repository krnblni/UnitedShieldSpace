import tkinter as tk
from client.utils.windowUtils import centerWindow


class GenericDialog(tk.Toplevel):
    def __init__(self, master=None, title="Error title", message="Error message"):
        super().__init__(master)
        self.minsize(300, 100)
        self.title(title)
        self.resizable(False, False)
        self.grab_set()
        centerWindow(self, 300, 100)
        tk.Label(self, text=message).pack(expand=True)
        tk.Button(self, text="Ok", command=self.remove).pack(expand=True)

    def remove(self):
        self.grab_release()
        self.destroy()
