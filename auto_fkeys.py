"""
Auto F-Keys - aciona as teclas F1 a F5 automaticamente no Windows.

As teclas sao enviadas via SendInput com scan codes de hardware, o mesmo
caminho usado por um teclado fisico, entao a janela ativa recebe o
pressionar e o soltar da tecla como se alguem estivesse digitando.

Atalho global: F9 inicia/para.
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
VK_F9 = 0x78

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

        ttk.Label(frm, text="Teclas:").grid(row=0, column=0, sticky="w")
        keys_frm = ttk.Frame(frm)
        keys_frm.grid(row=0, column=1, columnspan=2, sticky="w")
        self.key_vars = {}
        for i, name in enumerate(SCAN_CODES):
            var = tk.BooleanVar(value=True)
            ttk.Checkbutton(keys_frm, text=name, variable=var).grid(row=0, column=i, padx=2)
            self.key_vars[name] = var

        ttk.Label(frm, text="Modo:").grid(row=1, column=0, sticky="w", pady=(8, 0))
        self.mode = tk.StringVar(value="sequencia")
        ttk.Radiobutton(frm, text="Sequencia (F1, F2, ...)", variable=self.mode,
                        value="sequencia").grid(row=1, column=1, sticky="w", pady=(8, 0))
        ttk.Radiobutton(frm, text="Aleatorio", variable=self.mode,
                        value="aleatorio").grid(row=1, column=2, sticky="w", pady=(8, 0))

        ttk.Label(frm, text="Intervalo entre teclas (s):").grid(row=2, column=0, sticky="w", pady=(8, 0))
        self.interval = tk.DoubleVar(value=1.0)
        ttk.Spinbox(frm, from_=0.05, to=3600, increment=0.1, width=8,
                    textvariable=self.interval).grid(row=2, column=1, sticky="w", pady=(8, 0))

        ttk.Label(frm, text="Variacao aleatoria (+/- s):").grid(row=3, column=0, sticky="w", pady=(4, 0))
        self.jitter = tk.DoubleVar(value=0.2)
        ttk.Spinbox(frm, from_=0, to=600, increment=0.05, width=8,
                    textvariable=self.jitter).grid(row=3, column=1, sticky="w", pady=(4, 0))

        ttk.Label(frm, text="Espera antes de comecar (s):").grid(row=4, column=0, sticky="w", pady=(4, 0))
        self.delay = tk.DoubleVar(value=3.0)
        ttk.Spinbox(frm, from_=0, to=60, increment=1, width=8,
                    textvariable=self.delay).grid(row=4, column=1, sticky="w", pady=(4, 0))

        self.btn = ttk.Button(frm, text="Iniciar (F9)", command=self.toggle)
        self.btn.grid(row=5, column=0, columnspan=3, sticky="ew", pady=(12, 4))

        self.status = tk.StringVar(value="Parado. Clique na janela de destino apos iniciar.")
        ttk.Label(frm, textvariable=self.status, foreground="gray").grid(
            row=6, column=0, columnspan=3, sticky="w")

        root.protocol("WM_DELETE_WINDOW", self.on_close)
        threading.Thread(target=self._hotkey_loop, daemon=True).start()

    # --- controle -------------------------------------------------------
    def toggle(self):
        if self.running:
            self.stop()
        else:
            self.start()

    def start(self):
        keys = [k for k, v in self.key_vars.items() if v.get()]
        if not keys:
            messagebox.showwarning("Auto F-Keys", "Selecione pelo menos uma tecla.")
            return
        try:
            interval = max(0.05, float(self.interval.get()))
            jitter = max(0.0, float(self.jitter.get()))
            delay = max(0.0, float(self.delay.get()))
        except (tk.TclError, ValueError):
            messagebox.showerror("Auto F-Keys", "Valores numericos invalidos.")
            return

        self.running = True
        self.stop_event.clear()
        self.btn.config(text="Parar (F9)")
        self.worker = threading.Thread(
            target=self._run, args=(keys, self.mode.get(), interval, jitter, delay), daemon=True)
        self.worker.start()

    def stop(self):
        self.running = False
        self.stop_event.set()
        self.btn.config(text="Iniciar (F9)")
        self._set_status("Parado.")

    def on_close(self):
        self.stop_event.set()
        self.root.destroy()

    def _set_status(self, text):
        self.root.after(0, self.status.set, text)

    # --- threads --------------------------------------------------------
    def _run(self, keys, mode, interval, jitter, delay):
        end = time.monotonic() + delay
        while not self.stop_event.is_set() and time.monotonic() < end:
            self._set_status(f"Comecando em {end - time.monotonic():.0f}s... foque a janela de destino.")
            self.stop_event.wait(0.25)

        count = 0
        idx = 0
        while not self.stop_event.is_set():
            if mode == "aleatorio":
                key = random.choice(keys)
            else:
                key = keys[idx % len(keys)]
                idx += 1
            try:
                press_key(key)
            except OSError as e:
                self._set_status(f"Erro ao enviar tecla: {e}")
                self.root.after(0, self.stop)
                return
            count += 1
            self._set_status(f"Rodando - ultima tecla: {key} (total {count})")
            wait = max(0.02, interval + random.uniform(-jitter, jitter))
            self.stop_event.wait(wait)

    def _hotkey_loop(self):
        """Verifica F9 global para iniciar/parar mesmo com outra janela em foco."""
        was_down = False
        while True:
            down = bool(user32.GetAsyncKeyState(VK_F9) & 0x8000)
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
