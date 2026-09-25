"""
Auto F-Keys - aciona as teclas F1 a F5 automaticamente no Windows.

Dois modos de envio:
- Janela em foco: SendInput com scan codes de hardware, o mesmo caminho de
  um teclado fisico.
- Janela escolhida (segundo plano): mensagens WM_KEYDOWN/WM_KEYUP postadas
  direto na janela alvo, que continua recebendo as teclas mesmo atras de
  outros programas ou minimizada.

Cada tecla tem o seu proprio intervalo (delay).
Atalhos globais: F6 ativa/desativa, F7 captura a janela sob o mouse.
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
VK_F7 = 0x76
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101

# Scan codes (set 1) das teclas F1..F5
SCAN_CODES = {"F1": 0x3B, "F2": 0x3C, "F3": 0x3D, "F4": 0x3E, "F5": 0x3F}
# Virtual-key codes das mesmas teclas
VK_CODES = {"F1": 0x70, "F2": 0x71, "F3": 0x72, "F4": 0x73, "F5": 0x74}

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
user32.PostMessageW.argtypes = (wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
user32.PostMessageW.restype = wintypes.BOOL
user32.IsWindow.argtypes = (wintypes.HWND,)
user32.IsWindow.restype = wintypes.BOOL
user32.IsWindowVisible.argtypes = (wintypes.HWND,)
user32.IsWindowVisible.restype = wintypes.BOOL
user32.GetWindowTextLengthW.argtypes = (wintypes.HWND,)
user32.GetWindowTextW.argtypes = (wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
user32.GetCursorPos.argtypes = (ctypes.POINTER(wintypes.POINT),)
user32.WindowFromPoint.argtypes = (wintypes.POINT,)
user32.WindowFromPoint.restype = wintypes.HWND
user32.GetAncestor.argtypes = (wintypes.HWND, wintypes.UINT)
user32.GetAncestor.restype = wintypes.HWND
WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
user32.EnumWindows.argtypes = (WNDENUMPROC, wintypes.LPARAM)
GA_ROOT = 2


def window_title(hwnd):
    n = user32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(n + 1)
    user32.GetWindowTextW(hwnd, buf, n + 1)
    return buf.value


def list_windows():
    """Janelas principais visiveis e com titulo: [(hwnd, titulo), ...]."""
    result = []

    def cb(hwnd, _):
        if user32.IsWindowVisible(hwnd):
            title = window_title(hwnd)
            if title and title != "Auto F-Keys":
                result.append((hwnd, title))
        return True

    user32.EnumWindows(WNDENUMPROC(cb), 0)
    return result


def window_under_mouse():
    pt = wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(pt))
    return user32.WindowFromPoint(pt)


def _send_scan(scan, key_up):
    flags = KEYEVENTF_SCANCODE | (KEYEVENTF_KEYUP if key_up else 0)
    inp = INPUT(type=INPUT_KEYBOARD)
    inp.ki = KEYBDINPUT(wVk=0, wScan=scan, dwFlags=flags, time=0, dwExtraInfo=0)
    if user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT)) != 1:
        raise ctypes.WinError(ctypes.get_last_error())


def _post_key(hwnd, name, key_up):
    scan = SCAN_CODES[name]
    # lParam igual ao gerado pelo teclado: repeticao=1, scan code, e no
    # KEYUP os bits "estado anterior" (30) e "transicao" (31) ligados.
    lparam = 1 | (scan << 16)
    if key_up:
        lparam |= (1 << 30) | (1 << 31)
    msg = WM_KEYUP if key_up else WM_KEYDOWN
    if not user32.PostMessageW(hwnd, msg, VK_CODES[name], lparam):
        raise ctypes.WinError(ctypes.get_last_error())


def press_key(name, hwnd=None, hold_min=0.04, hold_max=0.09):
    """Pressiona e solta a tecla, segurando por um tempo aleatorio como uma pessoa.

    Sem hwnd vai para a janela em foco; com hwnd vai direto para aquela
    janela, mesmo que ela esteja em segundo plano.
    """
    if hwnd:
        _post_key(hwnd, name, key_up=False)
        time.sleep(random.uniform(hold_min, hold_max))
        _post_key(hwnd, name, key_up=True)
    else:
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

        # --- destino ---
        dest = ttk.LabelFrame(frm, text="Enviar para", padding=8)
        dest.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        self.target_mode = tk.StringVar(value="janela")
        ttk.Radiobutton(dest, text="Janela escolhida (funciona em segundo plano)",
                        variable=self.target_mode, value="janela").grid(
            row=0, column=0, columnspan=2, sticky="w")
        self.windows = []
        self.target_hwnd = None
        self.win_combo = ttk.Combobox(dest, state="readonly", width=42)
        self.win_combo.grid(row=1, column=0, sticky="ew", padx=(20, 4), pady=2)
        self.win_combo.bind("<<ComboboxSelected>>", self._on_pick_window)
        ttk.Button(dest, text="Atualizar", command=self.refresh_windows).grid(row=1, column=1)
        ttk.Label(dest, text="Dica: F7 captura a janela/campo que estiver sob o mouse.",
                  foreground="gray").grid(row=2, column=0, columnspan=2, sticky="w", padx=(20, 0))
        ttk.Radiobutton(dest, text="Janela em foco (teclado simulado)",
                        variable=self.target_mode, value="foco").grid(
            row=3, column=0, columnspan=2, sticky="w", pady=(4, 0))

        ttk.Label(frm, text="Tecla").grid(row=1, column=0, sticky="w")
        ttk.Label(frm, text="Delay (s)").grid(row=1, column=1, sticky="w")
        self.key_vars = {}
        self.key_delays = {}
        for i, name in enumerate(SCAN_CODES, start=2):
            var = tk.BooleanVar(value=True)
            ttk.Checkbutton(frm, text=name, variable=var).grid(row=i, column=0, sticky="w")
            delay = tk.DoubleVar(value=float(i - 1))
            ttk.Spinbox(frm, from_=0.05, to=3600, increment=0.5, width=8,
                        textvariable=delay).grid(row=i, column=1, sticky="w", pady=1)
            self.key_vars[name] = var
            self.key_delays[name] = delay

        ttk.Label(frm, text="Variacao aleatoria (+/- s):").grid(row=7, column=0, sticky="w", pady=(4, 0))
        self.jitter = tk.DoubleVar(value=0.2)
        ttk.Spinbox(frm, from_=0, to=600, increment=0.05, width=8,
                    textvariable=self.jitter).grid(row=7, column=1, sticky="w", pady=(4, 0))

        ttk.Label(frm, text="Espera antes de comecar (s):").grid(row=8, column=0, sticky="w", pady=(4, 0))
        self.delay = tk.DoubleVar(value=3.0)
        ttk.Spinbox(frm, from_=0, to=60, increment=1, width=8,
                    textvariable=self.delay).grid(row=8, column=1, sticky="w", pady=(4, 0))

        self.btn = ttk.Button(frm, text="Iniciar (F6)", command=self.toggle)
        self.btn.grid(row=9, column=0, columnspan=2, sticky="ew", pady=(12, 4))

        self.status = tk.StringVar(value="Parado.")
        ttk.Label(frm, textvariable=self.status, foreground="gray").grid(
            row=10, column=0, columnspan=2, sticky="w")

        self.refresh_windows()
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        threading.Thread(target=self._hotkey_loop, daemon=True).start()

    # --- janela alvo ----------------------------------------------------
    def refresh_windows(self):
        self.windows = list_windows()
        self.win_combo["values"] = [f"{t}  [{h:#x}]" for h, t in self.windows]
        if self.target_hwnd and user32.IsWindow(self.target_hwnd):
            for i, (h, _) in enumerate(self.windows):
                if h == self.target_hwnd:
                    self.win_combo.current(i)

    def _on_pick_window(self, _event=None):
        i = self.win_combo.current()
        if i >= 0:
            self.target_hwnd = self.windows[i][0]
            self.target_mode.set("janela")

    def capture_under_mouse(self):
        hwnd = window_under_mouse()
        if not hwnd:
            return
        top = user32.GetAncestor(hwnd, GA_ROOT) or hwnd
        if window_title(top) == "Auto F-Keys":
            return
        self.target_hwnd = hwnd
        self.target_mode.set("janela")
        label = window_title(hwnd) or window_title(top) or "(sem titulo)"
        if hwnd != top:
            label = f"{window_title(top)} > campo {hwnd:#x}"
        self.win_combo.set(f"{label}  [{hwnd:#x}]")
        self._set_status(f"Janela capturada: {label}")

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
        target = None
        if self.target_mode.get() == "janela":
            target = self.target_hwnd
            if not target or not user32.IsWindow(target):
                messagebox.showwarning(
                    "Auto F-Keys",
                    "Escolha a janela de destino na lista (ou aponte o mouse e aperte F7).")
                return

        self.running = True
        self.stop_event.clear()
        self.btn.config(text="Parar (F6)")
        self.worker = threading.Thread(
            target=self._run, args=(delays, jitter, delay, target), daemon=True)
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
    def _run(self, delays, jitter, delay, target):
        end = time.monotonic() + delay
        while not self.stop_event.is_set() and time.monotonic() < end:
            hint = "" if target else " foque a janela de destino."
            self._set_status(f"Comecando em {end - time.monotonic():.0f}s...{hint}")
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
            if target and not user32.IsWindow(target):
                self._set_status("A janela de destino foi fechada.")
                self.root.after(0, self.stop)
                return
            try:
                press_key(key, target)
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
        """Verifica F6 (iniciar/parar) e F7 (capturar janela) mesmo com outra janela em foco."""
        actions = {VK_F6: self.toggle, VK_F7: self.capture_under_mouse}
        was_down = {vk: False for vk in actions}
        while True:
            for vk, action in actions.items():
                down = bool(user32.GetAsyncKeyState(vk) & 0x8000)
                if down and not was_down[vk]:
                    self.root.after(0, action)
                was_down[vk] = down
            time.sleep(0.03)


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
