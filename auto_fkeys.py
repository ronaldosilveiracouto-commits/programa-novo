"""
Auto F-Keys - aciona as teclas F1 a F5 automaticamente no Windows.

As teclas sao enviadas via SendInput com scan codes de hardware, o mesmo
caminho usado por um teclado fisico, entao a janela ativa recebe o
pressionar e o soltar da tecla como se alguem estivesse digitando.

Cada tecla tem o seu proprio intervalo (delay).
Atalho global: F6 ativa/desativa.
"""

import ctypes
import random
import sys
import threading
import time
import tkinter as tk
from ctypes import wintypes
from tkinter import messagebox, ttk

if sys.platform != "win32":
    sys.exit("Este programa funciona apenas no Windows.")

user32 = ctypes.WinDLL("user32", use_last_error=True)

INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_SCANCODE = 0x0008
VK_F6 = 0x75

# Scan codes (set 1) das teclas F1..F5
SCAN_CODES = {"F1": 0x3B, "F2": 0x3C, "F3": 0x3D, "F4": 0x3E, "F5": 0x3F}

ULONG_PTR = ctypes.c_size_t


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    ]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("type", wintypes.DWORD), ("u", _INPUTUNION)]


user32.SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
user32.SendInput.restype = wintypes.UINT
user32.GetAsyncKeyState.argtypes = (ctypes.c_int,)
user32.GetAsyncKeyState.restype = ctypes.c_short


def _send_scan(scan, key_up):
    flags = KEYEVENTF_SCANCODE | (KEYEVENTF_KEYUP if key_up else 0)
    inp = INPUT(type=INPUT_KEYBOARD)
    inp.ki = KEYBDINPUT(wVk=0, wScan=scan, dwFlags=flags, time=0, dwExtraInfo=0)
    if user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT)) != 1:
        raise ctypes.WinError(ctypes.get_last_error())


def press_key(name, hold_min=0.04, hold_max=0.09):
    """Pressiona e solta a tecla, segurando por um tempo aleatorio como uma pessoa."""
    scan = SCAN_CODES[name]
    _send_scan(scan, key_up=False)
    time.sleep(random.uniform(hold_min, hold_max))
    _send_scan(scan, key_up=True)


class App:
    def __init__(self, root):
        self.root = root
        self.running = False
        self.stop_event = threading.Event()
        self.worker = None

        root.title("Auto F-Keys")
        root.resizable(False, False)

        frm = ttk.Frame(root, padding=12)
        frm.grid()

        ttk.Label(frm, text="Tecla").grid(row=0, column=0, sticky="w")
        ttk.Label(frm, text="Delay (s)").grid(row=0, column=1, sticky="w")
        self.key_vars = {}
        self.key_delays = {}
        for i, name in enumerate(SCAN_CODES, start=1):
            var = tk.BooleanVar(value=True)
            ttk.Checkbutton(frm, text=name, variable=var).grid(row=i, column=0, sticky="w")
            delay = tk.DoubleVar(value=float(i))
            ttk.Spinbox(frm, from_=0.05, to=3600, increment=0.5, width=8,
                        textvariable=delay).grid(row=i, column=1, sticky="w", pady=1)
            self.key_vars[name] = var
            self.key_delays[name] = delay

        ttk.Label(frm, text="Variacao aleatoria (+/- s):").grid(row=6, column=0, sticky="w", pady=(4, 0))
        self.jitter = tk.DoubleVar(value=0.2)
        ttk.Spinbox(frm, from_=0, to=600, increment=0.05, width=8,
                    textvariable=self.jitter).grid(row=6, column=1, sticky="w", pady=(4, 0))

        ttk.Label(frm, text="Espera antes de comecar (s):").grid(row=7, column=0, sticky="w", pady=(4, 0))
        self.delay = tk.DoubleVar(value=3.0)
        ttk.Spinbox(frm, from_=0, to=60, increment=1, width=8,
                    textvariable=self.delay).grid(row=7, column=1, sticky="w", pady=(4, 0))

        self.btn = ttk.Button(frm, text="Iniciar (F6)", command=self.toggle)
        self.btn.grid(row=8, column=0, columnspan=2, sticky="ew", pady=(12, 4))

        self.status = tk.StringVar(value="Parado. Clique na janela de destino apos iniciar.")
        ttk.Label(frm, textvariable=self.status, foreground="gray").grid(
            row=9, column=0, columnspan=2, sticky="w")

        root.protocol("WM_DELETE_WINDOW", self.on_close)
        threading.Thread(target=self._hotkey_loop, daemon=True).start()

    # --- controle -------------------------------------------------------
    def toggle(self):
        if self.running:
            self.stop()
        else:
            self.start()

    def start(self):
        try:
            delays = {k: max(0.05, float(self.key_delays[k].get()))
                      for k, v in self.key_vars.items() if v.get()}
            jitter = max(0.0, float(self.jitter.get()))
            delay = max(0.0, float(self.delay.get()))
        except (tk.TclError, ValueError):
            messagebox.showerror("Auto F-Keys", "Valores numericos invalidos.")
            return
        if not delays:
            messagebox.showwarning("Auto F-Keys", "Selecione pelo menos uma tecla.")
            return

        self.running = True
        self.stop_event.clear()
        self.btn.config(text="Parar (F6)")
        self.worker = threading.Thread(
            target=self._run, args=(delays, jitter, delay), daemon=True)
        self.worker.start()

    def stop(self):
        self.running = False
        self.stop_event.set()
        self.btn.config(text="Iniciar (F6)")
        self._set_status("Parado.")

    def on_close(self):
        self.stop_event.set()
        self.root.destroy()

    def _set_status(self, text):
        self.root.after(0, self.status.set, text)

    # --- threads --------------------------------------------------------
    def _run(self, delays, jitter, delay):
        end = time.monotonic() + delay
        while not self.stop_event.is_set() and time.monotonic() < end:
            self._set_status(f"Comecando em {end - time.monotonic():.0f}s... foque a janela de destino.")
            self.stop_event.wait(0.25)

        def next_wait(key):
            return max(0.02, delays[key] + random.uniform(-jitter, jitter))

        # Cada tecla tem o seu proprio relogio; todas comecam juntas, em ordem.
        now = time.monotonic()
        due = {key: now + i * 0.15 for i, key in enumerate(delays)}
        count = 0
        while not self.stop_event.is_set():
            key = min(due, key=due.get)
            wait = due[key] - time.monotonic()
            if wait > 0 and self.stop_event.wait(wait):
                break
            try:
                press_key(key)
            except OSError as e:
                self._set_status(f"Erro ao enviar tecla: {e}")
                self.root.after(0, self.stop)
                return
            count += 1
            self._set_status(f"Rodando - ultima tecla: {key} (total {count})")
            now = time.monotonic()
            due[key] = now + next_wait(key)
            # Folga minima para duas teclas nunca sairem grudadas.
            for other in due:
                if other != key and due[other] < now + 0.1:
                    due[other] = now + 0.1

    def _hotkey_loop(self):
        """Verifica F6 global para iniciar/parar mesmo com outra janela em foco."""
        was_down = False
        while True:
            down = bool(user32.GetAsyncKeyState(VK_F6) & 0x8000)
            if down and not was_down:
                self.root.after(0, self.toggle)
            was_down = down
            time.sleep(0.03)


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
