import tkinter as tk
from client.utils.windowUtils import centerWindow

class SplashScreen(tk.Toplevel):
    def __init__(self, master: tk.Tk):
        super().__init__(master)
        self.root = master
        self.root.config(menu=tk.Menu(self.root))
        self.title("Welcome to United Shield Space")
        self.w = 400
        self.h = 300
        self.resizable(False, False)
        centerWindow(self, self.w, self.h)
        self.splash()

    def splash(self):
        self.update()
