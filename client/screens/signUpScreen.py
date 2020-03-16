import tkinter as tk
import client.screens.loginScreen as loginscreen
from client.utils.textUtils import validateEmail, validateUsername
from client.screens.genericDialog import GenericDialog
from client.screens.stickyDialog import StickyDialog
from client.communication.auth import userSignUp
from grpc import StatusCode


class SignUpScreen:
    def __init__(self, master=None):
        self.root = master
        self.root.title("Sign Up")

        self.username = tk.StringVar()
        self.email = tk.StringVar()
        self.password = tk.StringVar()
        self.confirmPassword = tk.StringVar()

        self.root.grid_rowconfigure(0, weight=1)
        self.root.grid_rowconfigure(2, weight=1)
        self.root.grid_columnconfigure(0, weight=1)
        self.root.grid_columnconfigure(0, weight=1)

        self.initSignUpScreen()

    def initSignUpScreen(self):
        self.frame = tk.Frame(self.root)
        self.frame.grid(row=1, column=1)

        tk.Label(self.frame, text="Create a new account!").grid(row=0, column=1, sticky="NSWE", padx=5, pady=5)

        tk.Label(self.frame, text="Name").grid(row=1, column=0, sticky="W", padx=5, pady=5)
        self.usernameEntry = tk.Entry(self.frame, textvariable=self.username)
        self.usernameEntry.grid(row=1, column=1, sticky="E", padx=5, pady=5)

        tk.Label(self.frame, text="Email").grid(row=2, column=0, sticky="W", padx=5, pady=5)
        self.emailEntry = tk.Entry(self.frame, textvariable=self.email)
        self.emailEntry.grid(row=2, column=1, sticky="E", padx=5, pady=5)

        tk.Label(self.frame, text="Password").grid(row=3, column=0, sticky="W", padx=5, pady=5)
        self.passwordEntry = tk.Entry(self.frame, textvariable=self.password, show="*")
        self.passwordEntry.grid(row=3, column=1, sticky="E", padx=5, pady=5)

        tk.Label(self.frame, text="Confirm Password").grid(row=4, column=0, sticky="W", padx=5, pady=5)
        self.confirmPasswordEntry = tk.Entry(self.frame, textvariable=self.confirmPassword, show="*")
        self.confirmPasswordEntry.grid(row=4, column=1, sticky="E", padx=5, pady=5)

        self.signUpButton = tk.Button(self.frame, text="Sign Up", command=self.signUp)
        self.signUpButton.grid(row=5, column=1, sticky="S", padx=10, pady=10, ipadx=15)

        tk.Label(self.frame, text="Already have an account?").grid(row=6, column=1, sticky="NSWE", padx=5, pady=(20, 0))
        self.loginButton = tk.Button(self.frame, text="Login Now", command=self.launchLoginScreen)
        self.loginButton.grid(row=7, column=1, sticky="S", padx=10, pady=5, ipadx=15)

    def launchLoginScreen(self):
        self.frame.destroy()
        loginscreen.LoginScreen(self.root)

    def signUp(self):
        name = self.username.get()
        email = self.email.get()
        password = self.password.get()
        confPassword = self.confirmPassword.get()

        if name == "" or not validateUsername(name) or len(name) > 32:
            GenericDialog(self.root, title="Validation Error",
                          message="Invalid name!\nContains only alphabets.\nMax length: 32.")
        elif not validateEmail(email):
            GenericDialog(self.root, title="Validation Error", message="Invalid Email Address!")
        elif password != confPassword:
            GenericDialog(self.root, title="Validation Error", message="Passwords do not match!")
        elif password == confPassword and len(password) < 8:
            GenericDialog(self.root, title="Validation Error", message="Password minimum length: 8")
        elif password == confPassword and len(password) > 64:
            GenericDialog(self.root, title="Validation Error", message="Password maximum length: 64")
        else:
            # initiate sign up
            statusCode = userSignUp(username=name, email=email, password=password)
            if statusCode == StatusCode.OK:
                print("user created")
                GenericDialog(self.root, title="Success!", message="User account created.\nYou can now login!")
            elif statusCode == StatusCode.ALREADY_EXISTS:
                print("user already exist")
                GenericDialog(self.root, title="Account Error!", message="User account already exists.\nPlease login!")
            elif statusCode == StatusCode.INTERNAL:
                print("internal server error")
                GenericDialog(self.root, title="Error!", message="Internal Server Error!")
            elif statusCode == StatusCode.UNAVAILABLE:
                print("server unavailable")
                GenericDialog(self.root, title="Error!", message="Could not connect to server!")
            else:
                print("error status code = " + statusCode)
                GenericDialog(self.root, title="Error!", message="Error Code: " + statusCode)