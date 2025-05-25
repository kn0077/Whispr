import sys
import os
import threading
import webbrowser
import keyboard
import openai
import subprocess
import json

from PyQt5.QtWidgets import (
    QApplication, QSystemTrayIcon, QMenu, QWidget,
    QLabel, QVBoxLayout, QLineEdit, QPushButton
)
from PyQt5.QtGui import QIcon, QGuiApplication, QFont, QColor, QPainter
from PyQt5.QtCore import Qt, QTimer, QRect

# Load the config.json file
CONFIG_PATH = "config.json"

if not os.path.exists(CONFIG_PATH):
    # Create a default config if it doesn't exist
    default_config = {
        "api_key": "sk-or-xxxxxxxxxxxxxxxxxxxx",
        "hotkey": "ctrl+shift+space",
        "search_commands": {
            "/g": "https://www.google.com/search?q=",
            "/yt": "https://www.youtube.com/results?search_query=",
            "/img": "https://www.google.com/search?tbm=isch&q=",
            "/wiki": "https://en.wikipedia.org/wiki/Special:Search?search="
        },
        "open_apps": {
            "notepad": "C:\\Windows\\System32\\notepad.exe",
            "calculator": "C:\\Windows\\System32\\calc.exe",
        },
        "open_folders": {
            "programfiles": "C:\\Program Files",
        }
    }
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(default_config, f, indent=4)

# Load the config
with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    CONFIG = json.load(f)

# OpenRouter config
client = openai.OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=CONFIG.get("api_key"),
    default_headers={
        "HTTP-Referer": "http://localhost",
        "X-Title": "Minimal ChatGPT Tray"
    }
)

class BlurOverlay(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setWindowOpacity(0.8)
        self.setGeometry(QApplication.primaryScreen().geometry())

    def paintEvent(self, event):
        painter = QPainter(self)
        color = QColor(0, 0, 0, 160)  # semi-transparent black
        painter.fillRect(self.rect(), color)

class TransparentWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setFixedSize(460, 220)

        self.overlay = BlurOverlay()

        self.setStyleSheet("""
            QWidget {
                background-color: rgba(20, 20, 20, 220);
                border-radius: 14px;
            }
        """)

        layout = QVBoxLayout()
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(10)

        self.input = QLineEdit()
        self.input.setPlaceholderText("Type a question or command...")
        self.input.setStyleSheet("""
            QLineEdit {
                background-color: rgba(255, 255, 255, 220);
                padding: 10px;
                font-size: 14px;
                border: none;
                border-radius: 8px;
            }
        """)
        self.input.setFont(QFont("Segoe UI", 10))
        self.input.returnPressed.connect(self.handle_input)

        self.send_button = QPushButton("Send")
        self.send_button.setCursor(Qt.PointingHandCursor)
        self.send_button.clicked.connect(self.handle_input)
        self.send_button.setStyleSheet("""
            QPushButton {
                background-color: #3da860;
                color: white;
                padding: 8px 12px;
                border: none;
                border-radius: 6px;
            }
            QPushButton:hover {
                background-color: #2e8b57;
            }
        """)

        self.response_label = QLabel("")
        self.response_label.setWordWrap(True)
        self.response_label.setStyleSheet("""
            QLabel {
                color: #dddddd;
                font-size: 13px;
                padding: 8px;
            }
        """)

        layout.addWidget(self.input)
        layout.addWidget(self.send_button)
        layout.addWidget(self.response_label)
        self.setLayout(layout)

    def toggle(self):
        if self.isVisible():
            self.hide()
            self.overlay.hide()
        else:
            self.overlay.show()
            self.center()
            self.show()
            QTimer.singleShot(100, self.activate_input)

    def activate_input(self):
        self.activateWindow()
        self.raise_()
        self.input.setFocus()

    def center(self):
        screen = QApplication.primaryScreen().geometry()
        self.move(
            (screen.width() - self.width()) // 2,
            (screen.height() - self.height()) // 2
        )

    def handle_input(self):
        prompt = self.input.text().strip()
        if not prompt:
            self.response_label.setText("⚠️ Please enter some text.")
            return

        # Check for search commands
        for cmd, url in CONFIG.get("search_commands", {}).items():
            if prompt.lower().startswith(cmd + " "):
                query = prompt[len(cmd) + 1:]
                self.open_search(url, query)
                return

        # Check for open command
        if prompt.lower().startswith("/open "):
            app_name = prompt[6:].strip().lower()
            self.open_app(app_name)
            return
        if prompt.lower().startswith("/openfolder "):
            folder_key = prompt[12:].strip().lower()
            self.open_folder(folder_key)
            return

        self.ask_chatgpt(prompt)

    def open_search(self, base_url, query):
        webbrowser.open(base_url + query.replace(" ", "+"))
        self.response_label.setText("🔗 Opened in browser.")
        self.input.clear()
    
    def open_app(self, app_name):
        app_path = CONFIG.get("open_apps", {}).get(app_name)
        if not app_path:
            self.response_label.setText(f"❓ App „{app_name}” is not defined in config.")
            return
        try:
            subprocess.Popen([app_path])
            self.response_label.setText(f"✅ Opened {app_name}")
            self.input.clear()
        except Exception as e:
            self.response_label.setText(f"❌ Error: {e}")

    def open_folder(self, folder_arg):
        folder_arg = folder_arg.strip()

        # If it's a key defined in the config
        folder_path = CONFIG.get("open_folders", {}).get(folder_arg)

        # If not in config, treat as direct path
        if not folder_path:
            folder_path = folder_arg

        if not os.path.exists(folder_path):
            self.response_label.setText(f"❌ Path „{folder_path}” does not exist.")
            return

        try:
            os.startfile(folder_path)
            self.response_label.setText(f"✅ Opened folder:\n{folder_path}")
            self.input.clear()
        except Exception as e:
            self.response_label.setText(f"❌ Error opening folder: {e}")

    def ask_chatgpt(self, prompt):
        self.response_label.setText("⏳ Please wait...")

        def query():
            try:
                response = client.chat.completions.create(
                    model="openai/gpt-3.5-turbo",
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.7,
                )
                answer = response.choices[0].message.content.strip()
                self.response_label.setText(answer)
                QGuiApplication.clipboard().setText(answer)
            except Exception as e:
                self.response_label.setText(f"❌ Error: {e}")

        threading.Thread(target=query).start()

# --- Tray App ---
app = QApplication(sys.argv)
window = TransparentWindow()

icon_path = "icon.png"
tray_icon = QIcon(icon_path) if os.path.exists(icon_path) else QIcon()
tray = QSystemTrayIcon(tray_icon, parent=app)
tray.setToolTip("Minimal Chat")

menu = QMenu()
menu.addAction("Open", lambda: window.toggle())
menu.addAction("Exit", app.quit)
tray.setContextMenu(menu)
tray.show()

def hotkey_triggered():
    QTimer.singleShot(0, window.toggle)

try:
    keyboard.add_hotkey(CONFIG.get("hotkey", "ctrl+shift+space"), hotkey_triggered)
except:
    print("⚠️  Not running as administrator – hotkey unavailable.")

sys.exit(app.exec_())