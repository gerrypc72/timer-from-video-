"""Timer From Video

Trascina un video o un audio: genera un video con un timer countdown
(hh:mm:ss:ff) che parte dalla durata del sorgente e arriva a zero.
"""
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    HAS_DND = True
except Exception:  # drag&drop non disponibile: resta il pulsante Sfoglia
    HAS_DND = False

APP_NAME = "TimerFromVideo"
CODECS = {
    "MP4 (H.264)": {"ext": ".mp4", "args": ["-c:v", "libx264", "-preset", "veryfast",
                                           "-crf", "18", "-pix_fmt", "yuv420p",
                                           "-movflags", "+faststart"], "mult": 2},
    "HAP (MOV)": {"ext": ".mov", "args": ["-c:v", "hap", "-format", "hap"], "mult": 4},
}
DEFAULTS = {"width": 1920, "fps": 25, "codec": "MP4 (H.264)",
            "same_dir": True, "out_dir": ""}
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


# ---------------------------------------------------------------- impostazioni
def settings_path():
    base = os.environ.get("APPDATA") or os.path.expanduser("~/.config")
    folder = os.path.join(base, APP_NAME)
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, "settings.json")


def load_settings():
    s = dict(DEFAULTS)
    try:
        with open(settings_path(), encoding="utf-8") as f:
            s.update(json.load(f))
    except Exception:
        pass
    return s


def save_settings(s):
    try:
        with open(settings_path(), "w", encoding="utf-8") as f:
            json.dump(s, f, indent=2)
    except Exception:
        pass


# ---------------------------------------------------------------------- ffmpeg
def ffmpeg_exe():
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        import shutil
        exe = shutil.which("ffmpeg")
        if not exe:
            raise RuntimeError("ffmpeg non trovato")
        return exe


def probe(path):
    """Ritorna (durata_secondi, (w, h) del video oppure None)."""
    p = subprocess.run([ffmpeg_exe(), "-hide_banner", "-i", path],
                       capture_output=True, text=True, errors="replace",
                       creationflags=NO_WINDOW)
    out = p.stderr
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", out)
    if not m:
        raise RuntimeError("Impossibile leggere la durata del file.")
    dur = int(m[1]) * 3600 + int(m[2]) * 60 + float(m[3])
    size = None
    for line in out.splitlines():
        if "Video:" in line and "attached pic" not in line:
            mm = re.search(r",\s*(\d{2,5})x(\d{2,5})[\s,\[]", line)
            if mm:
                size = (int(mm[1]), int(mm[2]))
                break
    return dur, size


def font_file():
    win = os.environ.get("WINDIR", r"C:\Windows")
    for name in ("consola.ttf", "cour.ttf", "lucon.ttf"):
        p = os.path.join(win, "Fonts", name)
        if os.path.exists(p):
            return p
    for p in ("/System/Library/Fonts/Supplemental/Courier New.ttf",
              "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"):
        if os.path.exists(p):
            return p
    return None


def build_text(total_frames, base):
    """Testo drawtext (espansione) con timecode hh:mm:ss:ff del tempo residuo."""
    r = f"({total_frames}-n)"
    f = lambda e: "%{eif:" + e + ":d:2}"
    return (f(f"floor({r}/({base}*3600))") + ":" +
            f(f"mod(floor({r}/({base}*60)),60)") + ":" +
            f(f"mod(floor({r}/{base}),60)") + ":" +
            f(f"mod({r},{base})"))


def out_path_for(src, s):
    ext = CODECS[s["codec"]]["ext"]
    src = os.path.abspath(src)
    folder = os.path.dirname(src) if s["same_dir"] or not s["out_dir"] else s["out_dir"]
    name = os.path.splitext(os.path.basename(src))[0] + "_timer" + ext
    return os.path.join(folder, name)


def render(src, s, on_progress, proc_holder):
    dur, size = probe(src)
    fps = float(s["fps"])
    base = max(1, round(fps))
    codec = CODECS[s["codec"]]
    mult = codec["mult"]
    w = int(s["width"])
    w -= w % mult
    fs = int(w * 0.12)  # 11 caratteri monospace ~ 80% della larghezza
    h = max(mult, int(round(fs * 1.5 / mult)) * mult)  # striscia: testo + margine
    total = int(round(dur * fps))
    frames = total + 1  # l'ultimo frame mostra 00:00:00:00
    out = out_path_for(src, s)

    with tempfile.TemporaryDirectory() as tmp:
        with open(os.path.join(tmp, "t.txt"), "w", encoding="utf-8") as f:
            f.write(build_text(total, base))
        font = font_file()
        dt = ["textfile=t.txt", "expansion=normal", "fontcolor=white",
              f"fontsize={fs}", "x=(w-text_w)/2", "y=(h-text_h)/2"]
        if font:
            fp = font.replace("\\", "/").replace(":", r"\:")
            dt.insert(0, f"fontfile='{fp}'")
        vf = "drawtext=" + ":".join(dt)
        cmd = [ffmpeg_exe(), "-y", "-hide_banner", "-loglevel", "error",
               "-f", "lavfi", "-i", f"color=c=black:s={w}x{h}:r={fps}",
               "-vf", vf, "-frames:v", str(frames), *codec["args"],
               "-progress", "pipe:1", "-nostats", out]
        proc = subprocess.Popen(cmd, cwd=tmp, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True,
                                errors="replace", creationflags=NO_WINDOW)
        proc_holder.append(proc)
        err = []
        threading.Thread(target=lambda: err.append(proc.stderr.read()),
                         daemon=True).start()
        for line in proc.stdout:
            if line.startswith("frame="):
                try:
                    on_progress(int(line.split("=")[1]) / frames)
                except ValueError:
                    pass
        proc.wait()
        if proc.returncode != 0:
            if os.path.exists(out):
                try:
                    os.remove(out)
                except OSError:
                    pass
            if proc.returncode in (1, -15, -9) and proc_holder and getattr(proc, "cancelled", False):
                raise InterruptedError()
            raise RuntimeError("".join(err).strip() or "ffmpeg ha fallito")
    return out, (w, h)


# ------------------------------------------------------------------------- GUI
class App:
    def __init__(self):
        self.root = TkinterDnD.Tk() if HAS_DND else tk.Tk()
        self.root.title("Timer From Video")
        self.root.geometry("520x470")
        self.root.minsize(480, 440)
        self.s = load_settings()
        self.src = None
        self.busy = False
        self.procs = []
        self._build()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def _build(self):
        r = self.root
        pad = {"padx": 12, "pady": 6}
        self.drop = tk.Label(r, text="Trascina qui un video o un audio\n(o clicca per sfogliare)",
                             relief="groove", bd=2, height=6, bg="#f2f2f2", cursor="hand2")
        self.drop.pack(fill="x", **pad)
        self.drop.bind("<Button-1>", lambda e: self.browse())
        if HAS_DND:
            self.drop.drop_target_register(DND_FILES)
            self.drop.dnd_bind("<<Drop>>", self.on_drop)

        opt = ttk.LabelFrame(r, text="Impostazioni")
        opt.pack(fill="x", **pad)
        self.v_width = tk.StringVar(value=str(self.s["width"]))
        self.v_fps = tk.StringVar(value=str(self.s["fps"]))
        self.v_codec = tk.StringVar(value=self.s["codec"])
        self.v_same = tk.BooleanVar(value=self.s["same_dir"])
        self.v_dir = tk.StringVar(value=self.s["out_dir"])
        ttk.Label(opt, text="Larghezza (px)").grid(row=0, column=0, sticky="w", padx=8, pady=4)
        ttk.Entry(opt, textvariable=self.v_width, width=8).grid(row=0, column=1, sticky="w")
        ttk.Label(opt, text="FPS").grid(row=0, column=2, sticky="e", padx=8)
        ttk.Entry(opt, textvariable=self.v_fps, width=8).grid(row=0, column=3, sticky="w")
        ttk.Label(opt, text="Codec").grid(row=1, column=0, sticky="w", padx=8, pady=4)
        ttk.Combobox(opt, textvariable=self.v_codec, values=list(CODECS), state="readonly",
                     width=14).grid(row=1, column=1, columnspan=2, sticky="w")
        ttk.Checkbutton(opt, text="Salva accanto al sorgente", variable=self.v_same,
                        command=self._toggle_dir).grid(row=2, column=0, columnspan=4,
                                                       sticky="w", padx=8, pady=4)
        self.e_dir = ttk.Entry(opt, textvariable=self.v_dir)
        self.e_dir.grid(row=3, column=0, columnspan=3, sticky="ew", padx=8, pady=(0, 8))
        self.b_dir = ttk.Button(opt, text="Scegli…", command=self.pick_dir)
        self.b_dir.grid(row=3, column=3, padx=8, pady=(0, 8))
        opt.columnconfigure(2, weight=1)
        self._toggle_dir()

        self.lbl_src = ttk.Label(r, text="Nessun file selezionato", wraplength=480)
        self.lbl_src.pack(fill="x", padx=12)
        self.bar = ttk.Progressbar(r, maximum=1.0)
        self.bar.pack(fill="x", **pad)
        row = ttk.Frame(r)
        row.pack(fill="x", **pad)
        self.btn = ttk.Button(row, text="Genera", command=self.start)
        self.btn.pack(side="left")
        self.btn_cancel = ttk.Button(row, text="Annulla", command=self.cancel, state="disabled")
        self.btn_cancel.pack(side="left", padx=8)
        self.status = ttk.Label(r, text="Pronto." if HAS_DND else
                                "Pronto (drag&drop non disponibile: usa Sfoglia).")
        self.status.pack(fill="x", padx=12, pady=(0, 8))

    def _toggle_dir(self):
        st = "disabled" if self.v_same.get() else "normal"
        self.e_dir.configure(state=st)
        self.b_dir.configure(state=st)

    def pick_dir(self):
        d = filedialog.askdirectory(initialdir=self.v_dir.get() or None)
        if d:
            self.v_dir.set(d)

    def browse(self):
        p = filedialog.askopenfilename(title="Scegli video o audio")
        if p:
            self.set_src(p)

    def on_drop(self, e):
        files = self.root.tk.splitlist(e.data)
        if files:
            self.set_src(files[0])
        return e.action

    def set_src(self, p):
        self.src = p
        self.lbl_src.config(text=p)
        self.drop.config(text=os.path.basename(p))
        self.start()  # al rilascio parte subito

    def read_settings(self):
        try:
            w = int(self.v_width.get())
            fps = float(self.v_fps.get().replace(",", "."))
            assert w >= 64 and 1 <= fps <= 240
        except Exception:
            raise ValueError("Larghezza (>= 64) o FPS (1-240) non validi.")
        if fps == int(fps):
            fps = int(fps)
        self.s = {"width": w, "fps": fps, "codec": self.v_codec.get(),
                  "same_dir": self.v_same.get(), "out_dir": self.v_dir.get()}
        if not self.s["same_dir"] and not self.s["out_dir"]:
            raise ValueError("Scegli la cartella di destinazione.")
        save_settings(self.s)

    def start(self):
        if self.busy or not self.src:
            if not self.src:
                self.browse()
            return
        try:
            self.read_settings()
        except ValueError as e:
            messagebox.showerror("Errore", str(e))
            return
        self.busy = True
        self.procs.clear()
        self.btn.config(state="disabled")
        self.btn_cancel.config(state="normal")
        self.bar["value"] = 0
        self.status.config(text="Rendering…")
        threading.Thread(target=self.work, daemon=True).start()

    def work(self):
        try:
            out, (w, h) = render(self.src, self.s,
                                 lambda p: self.root.after(0, self.bar.configure, {"value": p}),
                                 self.procs)
            self.root.after(0, self.done, f"Fatto: {out}  ({w}x{h})", None)
        except InterruptedError:
            self.root.after(0, self.done, "Annullato.", None)
        except Exception as e:
            self.root.after(0, self.done, "Errore.", str(e))

    def done(self, msg, err):
        self.busy = False
        self.btn.config(state="normal")
        self.btn_cancel.config(state="disabled")
        self.status.config(text=msg)
        if err:
            messagebox.showerror("Errore", err)
        elif msg.startswith("Fatto"):
            self.bar["value"] = 1

    def cancel(self):
        for p in self.procs:
            p.cancelled = True
            p.terminate()

    def on_close(self):
        self.cancel()
        self.root.destroy()


if __name__ == "__main__":
    # modalita' CLI per test: timer_from_video.py file [width fps codec]
    if len(sys.argv) > 1 and os.path.exists(sys.argv[1]):
        st = load_settings()
        if len(sys.argv) > 2:
            st["width"] = int(sys.argv[2])
        if len(sys.argv) > 3:
            st["fps"] = float(sys.argv[3])
        if len(sys.argv) > 4:
            st["codec"] = sys.argv[4]
        print(render(sys.argv[1], st, lambda p: None, []))
    else:
        App().root.mainloop()
