import json
import math
import os
import time
import tkinter as tk
from tkinter import ttk, messagebox
from decimal import Decimal, getcontext

# High precision for offline efficiency math (deterministic)
getcontext().prec = 50

SAVE_FILE = "infinite_tap_save.json"
HIGHSCORES_FILE = "infinite_tap_highscores.json"

# -------------------- Game Formulas --------------------
def tap_upgrade_cost(level: int) -> int:
    return math.ceil(10 * (1.22 ** level) * (1 + 0.08 * level))

def tap_upgrade_time(level: int) -> int:
    return 2 * level + 1  # seconds

def passive_upgrade_cost(level: int) -> int:
    return math.ceil(100 * (1.20 ** level) * (1 + 0.10 * level))

def passive_upgrade_time(level: int) -> int:
    return 5 * level + 3  # seconds

# Offline Efficiency (infinite scaling; gentle + linear blend)
def offline_upgrade_cost(level: int) -> int:
    return math.ceil(750 * (2.10 ** level) * (1 + 0.12 * level))

def offline_upgrade_time(level: int) -> int:
    return 8 * level + 5  # seconds

def offline_efficiency(level: int) -> Decimal:
    # Each level gives +5% efficiency
    percent_bonus = level * 5
    return Decimal(100 + percent_bonus) / Decimal(100)

# Temporal Stability (Hardcore decay window)
def stability_upgrade_cost(level: int) -> int:
    # Brutal ×10 per level
    return 1_000_000 * (10 ** level)

def stability_upgrade_time(level: int) -> int:
    # +1 minute per level (in seconds)
    return 60 * level + 60

def stability_limit_hours(level: int) -> int:
    # Level 0 = Freeplay (no collapse). Level 1 starts at 72h, then +1h per level.
    return 0 if level <= 0 else (72 + level)

# -------------------- Number Formatting --------------------
_BASE_TAGS = ["", "K", "M", "B", "T", "Qa", "Qi", "Sx", "Sp", "Oc", "No", "Dc"]
_SERIES_ONES_TAGS = ["", "U", "D", "T", "Q", "Qn", "Sx", "Sp", "Oc", "N"]
_TENS_TO_CORE = {1:"d",2:"v",3:"tg",4:"qg",5:"qng",6:"sg",7:"stg",8:"og",9:"ng"}
_NAME_TABLE = {
    0:"",1:"Thousand",2:"Million",3:"Billion",4:"Trillion",
    5:"Quadrillion",6:"Quintillion",7:"Sextillion",8:"Septillion",
    9:"Octillion",10:"Nonillion",11:"Decillion",
    12:"Undecillion",13:"Duodecillion",14:"Tredecillion",
    15:"Quattuordecillion",16:"Quindecillion",17:"Sexdecillion",
    18:"Septendecillion",19:"Octodecillion",20:"Novemdecillion",21:"Vigintillion",
}

def _short_tag_for_group(group_index: int) -> str:
    if group_index < len(_BASE_TAGS):
        return _BASE_TAGS[group_index]
    n = group_index - 11  # 1.. -> Ud.. ; 10 -> Vg, etc.
    tens = (n - 1) // 9
    ones = (n - 1) % 9 + 1
    ones_tag = _SERIES_ONES_TAGS[ones]
    tens_core = _TENS_TO_CORE[(tens % 9) + 1]
    hundred_cycles = tens // 9
    core = tens_core + ("c" * hundred_cycles)
    return f"{ones_tag}{core}"

def fmt_with_commas(n: int) -> str:
    return f"{n:,}"

def fmt_short(n: int) -> str:
    if n < 1000:
        return str(n)
    s = str(n)
    group = (len(s) - 1) // 3
    tag = _short_tag_for_group(group)
    leading = len(s) - group * 3
    whole = s[:leading]
    frac = s[leading:leading + 2]
    return f"{whole}.{frac}{tag}" if frac else f"{whole}{tag}"

def scale_name_and_exp(n: int):
    if n == 0:
        return ("Zero", 0)
    exp = (len(str(n)) - 1)
    group = exp // 3
    name = _NAME_TABLE.get(group)
    return (name if name else f"10^{group*3} scale", group * 3)

def wrap_text(s: str, width: int = 80) -> str:
    out, line, count = [], [], 0
    for ch in s:
        line.append(ch); count += 1
        if count >= width:
            out.append("".join(line)); line, count = [], 0
    if line:
        out.append("".join(line))
    return "\n".join(out)

# -------------------- Tooltip --------------------
class HoverTip:
    def __init__(self, widget, text_provider, wraplength_px=420):
        self.widget = widget
        self.text_provider = text_provider
        self.wraplength_px = wraplength_px
        self.tipwin = None
        widget.bind("<Enter>", self._show)
        widget.bind("<Leave>", self._hide)
        widget.bind("<Motion>", self._move)

    def _show(self, event=None):
        if self.tipwin:
            return
        text = self.text_provider()
        if not text:
            return
        self.tipwin = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_attributes("-topmost", True)
        x = self.widget.winfo_pointerx() + 16
        y = self.widget.winfo_pointery() + 16
        tw.wm_geometry(f"+{x}+{y}")
        frame = tk.Frame(tw, background="#ffffff", borderwidth=1, relief="solid")
        frame.pack(fill="both", expand=True)
        label = tk.Label(frame, text=text, justify="left",
                         bg="#ffffff", fg="#000000",
                         font=("Consolas", 10), wraplength=self.wraplength_px)
        label.pack(padx=8, pady=6)

    def _move(self, event=None):
        if not self.tipwin:
            return
        x = self.widget.winfo_pointerx() + 16
        y = self.widget.winfo_pointery() + 16
        self.tipwin.wm_geometry(f"+{x}+{y}")

    def _hide(self, event=None):
        if self.tipwin:
            self.tipwin.destroy()
            self.tipwin = None

# -------------------- Highscores Persistence --------------------
def load_highscores():
    if not os.path.exists(HIGHSCORES_FILE):
        return []
    try:
        with open(HIGHSCORES_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                return data
            return []
    except Exception:
        return []

def append_highscore(entry: dict):
    scores = load_highscores()
    scores.insert(0, entry)  # newest first
    try:
        with open(HIGHSCORES_FILE, "w", encoding="utf-8") as f:
            json.dump(scores, f, ensure_ascii=False, separators=(",", ":"))
    except Exception:
        pass

# -------------------- Game Class --------------------
class InfiniteTapGame:
    TICK_MS = 1000
    UI_MS = 200
    AUTOSAVE_MS = 10_000
    OFFLINE_CAP_SECONDS = 86_400  # 24h cap for offline earnings

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Infinity Tap — Minimal Incremental (v1.4)")
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        # Dark theme palette
        self.bg = "#0f1115"; self.fg = "#e6e6e6"; self.accent = "#4da3ff"
        self.muted = "#9aa4b2"; self.card = "#171a21"
        self.btn_bg = "#21262d"; self.btn_bg_disabled = "#2a2f37"
        self.btn_border = "#2b3440"; self.good = "#58d68d"; self.warn = "#f5b041"

        self.root.configure(bg=self.bg)
        self._build_styles()

        # --- State ---
        self.coins = 0
        self.income_per_tap = 1
        self.income_per_second = 0

        self.tap_upg_level = 0
        self.passive_upg_level = 0
        self.offline_upg_level = 0
        self.stability_upg_level = 0

        self.tap_research_end_at = 0
        self.passive_research_end_at = 0
        self.offline_research_end_at = 0
        self.stability_research_end_at = 0

        self.last_saved_at = 0

        # pending events to show as non-blocking popups after UI exists
        self._pending_events = []  # list of dicts: {"type": "...", **data}

        # Load (includes decay check & offline earnings)
        self.load()

        # UI
        self._build_ui()

        # loops
        self._schedule_tick()
        self._schedule_ui()
        self._schedule_autosave()
        self.root.after(80, self._process_pending_events)

    # -------- Styles --------
    def _build_styles(self):
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure("Dark.TFrame", background=self.bg)
        style.configure("Card.TFrame", background=self.card)
        style.configure("Dark.TLabel", background=self.bg, foreground=self.fg)
        style.configure("Card.TLabel", background=self.card, foreground=self.fg)
        style.configure("Muted.TLabel", background=self.bg, foreground=self.muted)
        style.configure("Dark.TButton",
                        background=self.btn_bg, foreground=self.fg,
                        bordercolor=self.btn_border, focusthickness=3,
                        focuscolor=self.accent, padding=10)
        style.map("Dark.TButton",
                  background=[("disabled", self.btn_bg_disabled),
                             ("pressed", "#1b1f24"),
                             ("active", "#26303a")])
        style.configure("Tap.TButton", background=self.accent,
                        foreground="#0b1220", padding=18)
        style.map("Tap.TButton",
                  background=[("disabled", "#7fbaff"),
                             ("pressed", "#2d7fd6"),
                             ("active", "#6db1ff")])

    # -------- UI --------
    def _build_ui(self):
        # top card
        self.card_frame = ttk.Frame(self.root, style="Card.TFrame", padding=16)
        self.card_frame.pack(fill="x", padx=16, pady=(16, 8))

        self.coins_var = tk.StringVar()
        self.ipt_var = tk.StringVar()
        self.ips_var = tk.StringVar()
        self.offline_eff_var = tk.StringVar()
        self.stability_var = tk.StringVar()

        self.coins_lbl = ttk.Label(self.card_frame, textvariable=self.coins_var,
                                   style="Card.TLabel", font=("Segoe UI", 16, "bold"))
        self.coins_lbl.grid(row=0, column=0, sticky="w")

        # Tooltip with full integer + scale name
        def tooltip_text():
            n = self.coins
            full_int_wrapped = wrap_text(fmt_with_commas(n), width=80)
            name, _ = scale_name_and_exp(n)
            short = fmt_short(n)
            if n < 1000:
                return f"{full_int_wrapped}\n(Exact Integer)"
            return f"{full_int_wrapped}\n({short} • {name})"
        HoverTip(self.coins_lbl, tooltip_text, wraplength_px=420)

        ttk.Label(self.card_frame, textvariable=self.ipt_var, style="Card.TLabel",
                  font=("Segoe UI", 11)).grid(row=1, column=0, sticky="w", pady=(6,0))
        ttk.Label(self.card_frame, textvariable=self.ips_var, style="Card.TLabel",
                  font=("Segoe UI", 11)).grid(row=2, column=0, sticky="w", pady=(2,0))
        ttk.Label(self.card_frame, textvariable=self.offline_eff_var, style="Card.TLabel",
                  font=("Segoe UI", 11)).grid(row=3, column=0, sticky="w", pady=(2,0))
        ttk.Label(self.card_frame, textvariable=self.stability_var, style="Card.TLabel",
                  font=("Segoe UI", 11)).grid(row=4, column=0, sticky="w", pady=(2,0))

        # Big TAP
        self.tap_btn = ttk.Button(self.root, text="TAP", command=self.on_tap, style="Tap.TButton")
        self.tap_btn.pack(fill="x", padx=16, pady=(8, 8))

        # Upgrades card
        self.upg_frame = ttk.Frame(self.root, style="Card.TFrame", padding=16)
        self.upg_frame.pack(fill="x", padx=16, pady=(0, 8))

        # Tap
        ttk.Label(self.upg_frame, text="Upgrade Tap Income", style="Card.TLabel",
                  font=("Segoe UI", 12, "bold")).grid(row=0, column=0, sticky="w")
        self.tap_info = ttk.Label(self.upg_frame, text="", style="Card.TLabel", font=("Segoe UI", 10))
        self.tap_info.grid(row=1, column=0, sticky="w", pady=(2, 10))
        self.tap_btn2 = ttk.Button(self.upg_frame, text="Research", style="Dark.TButton",
                                   command=self.start_tap_research)
        self.tap_btn2.grid(row=0, column=1, rowspan=2, sticky="e")

        # Passive
        ttk.Label(self.upg_frame, text="Research Passive Income", style="Card.TLabel",
                  font=("Segoe UI", 12, "bold")).grid(row=2, column=0, sticky="w", pady=(8,0))
        self.pass_info = ttk.Label(self.upg_frame, text="", style="Card.TLabel", font=("Segoe UI", 10))
        self.pass_info.grid(row=3, column=0, sticky="w", pady=(2, 10))
        self.pass_btn2 = ttk.Button(self.upg_frame, text="Research", style="Dark.TButton",
                                    command=self.start_passive_research)
        self.pass_btn2.grid(row=2, column=1, rowspan=2, sticky="e")

        # Offline Efficiency
        ttk.Label(self.upg_frame, text="Research Offline Efficiency", style="Card.TLabel",
                  font=("Segoe UI", 12, "bold")).grid(row=4, column=0, sticky="w", pady=(8,0))
        self.off_info = ttk.Label(self.upg_frame, text="", style="Card.TLabel", font=("Segoe UI", 10))
        self.off_info.grid(row=5, column=0, sticky="w", pady=(2, 10))
        self.off_btn2 = ttk.Button(self.upg_frame, text="Research", style="Dark.TButton",
                                   command=self.start_offline_research)
        self.off_btn2.grid(row=4, column=1, rowspan=2, sticky="e")

        # Temporal Stability
        ttk.Label(self.upg_frame, text="Research Temporal Stability", style="Card.TLabel",
                  font=("Segoe UI", 12, "bold")).grid(row=6, column=0, sticky="w", pady=(8,0))
        self.stab_info = ttk.Label(self.upg_frame, text="", style="Card.TLabel", font=("Segoe UI", 10))
        self.stab_info.grid(row=7, column=0, sticky="w", pady=(2, 0))
        self.stab_btn2 = ttk.Button(self.upg_frame, text="Research", style="Dark.TButton",
                                    command=self.start_stability_research)
        self.stab_btn2.grid(row=6, column=1, rowspan=2, sticky="e")

        # Bottom bar: status + legacy
        btm = ttk.Frame(self.root, style="Dark.TFrame")
        btm.pack(fill="x", padx=16, pady=(0, 12))

        self.status_var = tk.StringVar(value="Ready.")
        ttk.Label(btm, textvariable=self.status_var, style="Muted.TLabel",
                  font=("Segoe UI", 9)).pack(side="left")

        self.legacy_btn = ttk.Button(btm, text="View Legacy Runs", style="Dark.TButton",
                                     command=self.show_legacy_runs)
        self.legacy_btn.pack(side="right")

        self._refresh_ui(force=True)

    # -------- Actions --------
    def on_tap(self):
        self.coins += self.income_per_tap
        self._refresh_ui()

    def start_tap_research(self):
        lvl = self.tap_upg_level
        cost = tap_upgrade_cost(lvl)
        if self.coins < cost:
            self._flash_status("Not enough coins for Tap Upgrade.", warn=True); return
        if self.is_tap_researching():
            self._flash_status("Tap upgrade already researching…", warn=True); return
        self.coins -= cost
        self.tap_research_end_at = int(time.time()) + tap_upgrade_time(lvl)
        self._flash_status("Tap upgrade research started.", muted=True)
        self._refresh_ui()

    def start_passive_research(self):
        lvl = self.passive_upg_level
        cost = passive_upgrade_cost(lvl)
        if self.coins < cost:
            self._flash_status("Not enough coins for Passive Research.", warn=True); return
        if self.is_passive_researching():
            self._flash_status("Passive research already in progress…", warn=True); return
        self.coins -= cost
        self.passive_research_end_at = int(time.time()) + passive_upgrade_time(lvl)
        self._flash_status("Passive income research started.", muted=True)
        self._refresh_ui()

    def start_offline_research(self):
        lvl = self.offline_upg_level
        cost = offline_upgrade_cost(lvl)
        if self.coins < cost:
            self._flash_status("Not enough coins for Offline Efficiency.", warn=True); return
        if self.is_offline_researching():
            self._flash_status("Offline Efficiency research already in progress…", warn=True); return
        self.coins -= cost
        self.offline_research_end_at = int(time.time()) + offline_upgrade_time(lvl)
        self._flash_status("Offline Efficiency research started.", muted=True)
        self._refresh_ui()

    def start_stability_research(self):
        lvl = self.stability_upg_level
        cost = stability_upgrade_cost(lvl)
        if self.coins < cost:
            self._flash_status("Not enough coins for Temporal Stability.", warn=True); return
        if self.is_stability_researching():
            self._flash_status("Temporal Stability research already in progress…", warn=True); return
        self.coins -= cost
        self.stability_research_end_at = int(time.time()) + stability_upgrade_time(lvl)
        self._flash_status("Temporal Stability research started.", muted=True)
        self._refresh_ui()

    # -------- Loops --------
    def _schedule_tick(self):
        self._tick()
        self.root.after(self.TICK_MS, self._schedule_tick)

    def _tick(self):
        # Passive tick
        if self.income_per_second > 0:
            self.coins += self.income_per_second

        now = int(time.time())

        # Completions
        if self.is_tap_researching() and now >= self.tap_research_end_at:
           self.tap_research_end_at = 0
           self.tap_upg_level += 1

           tap_bonus = 1 + (self.tap_upg_level // 10)
           self.income_per_tap += tap_bonus

           self._flash_status(f"Tap upgrade complete! +{tap_bonus} per tap.", good=True)

        if self.is_passive_researching() and now >= self.passive_research_end_at:
           self.passive_research_end_at = 0
           self.passive_upg_level += 1

           passive_bonus = 1 + (self.passive_upg_level // 10)
           self.income_per_second += passive_bonus

           self._flash_status(f"Passive research complete! +{passive_bonus} coin/sec.", good=True)

        if self.is_offline_researching() and now >= self.offline_research_end_at:
            self.offline_research_end_at = 0
            self.offline_upg_level += 1
            self._flash_status("Offline Efficiency research complete!", good=True)

        if self.is_stability_researching() and now >= self.stability_research_end_at:
            self.stability_research_end_at = 0
            self.stability_upg_level += 1
            self._flash_status("Temporal Stability research complete!", good=True)

        self.coins = max(0, int(self.coins))

    def _schedule_ui(self):
        self._refresh_ui()
        self.root.after(self.UI_MS, self._schedule_ui)

    def _schedule_autosave(self):
        self.save()
        self._flash_status("Game auto-saved.", muted=True)
        self.root.after(self.AUTOSAVE_MS, self._schedule_autosave)

    # -------- UI Helpers --------
    def is_tap_researching(self) -> bool:
        return self.tap_research_end_at > 0

    def is_passive_researching(self) -> bool:
        return self.passive_research_end_at > 0

    def is_offline_researching(self) -> bool:
        return self.offline_research_end_at > 0

    def is_stability_researching(self) -> bool:
        return self.stability_research_end_at > 0

    def _remaining(self, end_at: int) -> int:
        return max(0, end_at - int(time.time()))

    def _flash_status(self, text: str, good=False, warn=False, muted=False):
        if good: self.status_var.set(f"✅ {text}")
        elif warn: self.status_var.set(f"⚠️ {text}")
        elif muted: self.status_var.set(f"💾 {text}")
        else: self.status_var.set(text)

    def _upgrade_suffixes(self):
        """Compute the '+gain' suffix for each upgrade's next level."""
        # Tap: +1/tap
        next_tap_level = self.tap_upg_level + 1
        tap_bonus = 1 + (next_tap_level // 10)
        tap_suffix = f"+{tap_bonus}/tap"

        # Passive: +1/sec
        next_passive_level = self.passive_upg_level + 1
        passive_bonus = 1 + (next_passive_level // 10)
        passive_suffix = f"+{passive_bonus}/sec"

        # Offline: percentage improvement from L to L+1, rounded to 2 decimals
        L = self.offline_upg_level
        eff_now = offline_efficiency(L)
        eff_next = offline_efficiency(L + 1)
        gain_pct = (eff_next / eff_now) - Decimal(1)
        gain_pct_val = float(gain_pct * 100)
        # Round to 2 decimals, but display with at most 2 decimals (e.g., 0.25%)
        offline_suffix = f"+{gain_pct_val:.2f}%"

        # Stability: +72h at level 0, else +1h
        stability_suffix = "+72h" if self.stability_upg_level == 0 else "+1h"

        return tap_suffix, passive_suffix, offline_suffix, stability_suffix

    def _refresh_ui(self, force=False):
        # Top stats
        self.coins_var.set(f"Coins: {fmt_short(self.coins)}")
        self.ipt_var.set(f"+{fmt_short(self.income_per_tap)} per tap")
        self.ips_var.set(f"+{fmt_short(self.income_per_second)}/sec")

        eff = offline_efficiency(self.offline_upg_level)
        eff_str = f"{eff:.6f}".rstrip("0").rstrip(".")
        self.offline_eff_var.set(f"Offline: x{eff_str} (24h offline earn cap)")

        # Stability line
        lim_hrs = stability_limit_hours(self.stability_upg_level)
        if lim_hrs <= 0:
            self.stability_var.set("Stability: Freeplay (no collapse)")
        else:
            self.stability_var.set(f"Stability: Hardcore (collapse in {lim_hrs}h)")

        # Calculate '+gain' suffixes
        tap_suffix, passive_suffix, offline_suffix, stability_suffix = self._upgrade_suffixes()

        # Tap UI
        t_cost = tap_upgrade_cost(self.tap_upg_level)
        t_time = tap_upgrade_time(self.tap_upg_level)
        if self.is_tap_researching():
            t_rem = self._remaining(self.tap_research_end_at)
            self.tap_info.config(text=f"Researching… {t_rem}s remaining")
            self.tap_btn2.state(["disabled"])
        else:
            self.tap_info.config(text=f"Cost: {fmt_short(t_cost)}  |  Time: {t_time}s  |  Level: {self.tap_upg_level}  |  {tap_suffix}")
            self.tap_btn2.state(["!disabled"] if self.coins >= t_cost else ["disabled"])

        # Passive UI
        p_cost = passive_upgrade_cost(self.passive_upg_level)
        p_time = passive_upgrade_time(self.passive_upg_level)
        if self.is_passive_researching():
            p_rem = self._remaining(self.passive_research_end_at)
            self.pass_info.config(text=f"Researching… {p_rem}s remaining")
            self.pass_btn2.state(["disabled"])
        else:
            self.pass_info.config(text=f"Cost: {fmt_short(p_cost)}  |  Time: {p_time}s  |  Level: {self.passive_upg_level}  |  {passive_suffix}")
            self.pass_btn2.state(["!disabled"] if self.coins >= p_cost else ["disabled"])

        # Offline UI
        o_cost = offline_upgrade_cost(self.offline_upg_level)
        o_time = offline_upgrade_time(self.offline_upg_level)
        if self.is_offline_researching():
            o_rem = self._remaining(self.offline_research_end_at)
            self.off_info.config(text=f"Researching… {o_rem}s remaining")
            self.off_btn2.state(["disabled"])
        else:
            self.off_info.config(text=f"Cost: {fmt_short(o_cost)}  |  Time: {o_time}s  |  Level: {self.offline_upg_level}  |  {offline_suffix}")
            self.off_btn2.state(["!disabled"] if self.coins >= o_cost else ["disabled"])

        # Stability UI
        s_cost = stability_upgrade_cost(self.stability_upg_level)
        s_time = stability_upgrade_time(self.stability_upg_level)
        if self.is_stability_researching():
            s_rem = self._remaining(self.stability_research_end_at)
            self.stab_info.config(text=f"Researching… {s_rem}s remaining")
            self.stab_btn2.state(["disabled"])
        else:
            self.stab_info.config(text=f"Cost: {fmt_short(s_cost)}  |  Time: {s_time}s  |  Level: {self.stability_upg_level}  |  {stability_suffix}")
            self.stab_btn2.state(["!disabled"] if self.coins >= s_cost else ["disabled"])

        self.tap_btn.state(["!disabled"])

    # -------- Highscores Window --------
    def show_legacy_runs(self):
        runs = load_highscores()
        win = tk.Toplevel(self.root)
        win.title("Legacy Runs")
        win.configure(bg=self.bg)
        win.geometry("520x360")
        frame = ttk.Frame(win, style="Dark.TFrame", padding=12)
        frame.pack(fill="both", expand=True)

        header = ttk.Label(frame, text="Legacy Runs", style="Dark.TLabel",
                           font=("Segoe UI", 14, "bold"))
        header.pack(anchor="w", pady=(0, 8))

        if not runs:
            ttk.Label(frame, text="No legacy runs recorded yet.",
                      style="Dark.TLabel", font=("Segoe UI", 10)).pack(anchor="w")
        else:
            # Scrollable text area
            text = tk.Text(frame, bg=self.card, fg=self.fg, insertbackground=self.fg,
                           font=("Consolas", 10), relief="flat", height=12, wrap="word")
            scroll = ttk.Scrollbar(frame, command=text.yview)
            text.configure(yscrollcommand=scroll.set)
            text.pack(side="left", fill="both", expand=True)
            scroll.pack(side="right", fill="y")

            lines = []
            for idx, r in enumerate(runs, start=1):
                coins_val = r.get("coins", 0)
                line = (f"#{idx} — {fmt_short(int(coins_val))} Coins"
                        f"  | Tap {r.get('tap',0)}  Passive {r.get('passive',0)}"
                        f"  Offline {r.get('offline',0)}  Stability {r.get('stability',0)}"
                        f"  — {r.get('date','')}")
                lines.append(line)
            text.insert("1.0", "\n".join(lines))
            text.config(state="disabled")

        ttk.Button(frame, text="OK", style="Dark.TButton",
                   command=win.destroy).pack(anchor="e", pady=(10,0))

    # -------- Persistence --------
    def to_dict(self) -> dict:
        return {
            "coins": int(self.coins),
            "income_per_tap": int(self.income_per_tap),
            "income_per_second": int(self.income_per_second),

            "tap_upg_level": int(self.tap_upg_level),
            "passive_upg_level": int(self.passive_upg_level),
            "offline_upg_level": int(self.offline_upg_level),
            "stability_upg_level": int(self.stability_upg_level),

            "tap_research_end_at": int(self.tap_research_end_at),
            "passive_research_end_at": int(self.passive_research_end_at),
            "offline_research_end_at": int(self.offline_research_end_at),
            "stability_research_end_at": int(self.stability_research_end_at),

            "saved_at": int(time.time()),
        }

    def save(self):
        try:
            with open(SAVE_FILE, "w", encoding="utf-8") as f:
                json.dump(self.to_dict(), f, separators=(",", ":"), ensure_ascii=False)
        except Exception as e:
            self._flash_status(f"Save failed: {e}", warn=True)

    def _record_highscore_and_reset(self, elapsed_hours):
        # Record current run
        timestr = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        entry = {
            "date": timestr,
            "coins": int(self.coins),
            "tap": int(self.tap_upg_level),
            "passive": int(self.passive_upg_level),
            "offline": int(self.offline_upg_level),
            "stability": int(self.stability_upg_level),
            "elapsed_hours": round(elapsed_hours, 2),
        }
        append_highscore(entry)

        # Reset progress (not deleting stability investment)
        self.coins = 0
        self.income_per_tap = 1
        self.income_per_second = 0
        self.tap_upg_level = 0
        self.passive_upg_level = 0
        self.offline_upg_level = 0

        self.tap_research_end_at = 0
        self.passive_research_end_at = 0
        self.offline_research_end_at = 0
        self.stability_research_end_at = 0

        # Queue collapse popup (Start Over only)
        self._pending_events.append({
            "type": "collapse",
            "coins": entry["coins"],
            "tap": entry["tap"],
            "passive": entry["passive"],
            "offline": entry["offline"],
            "stability": entry["stability"],
            "elapsed_hours": entry["elapsed_hours"],
            "limit_hours": stability_limit_hours(self.stability_upg_level),
        })

    def load(self):
        if not os.path.exists(SAVE_FILE):
            return
        try:
            with open(SAVE_FILE, "r", encoding="utf-8") as f:
                d = json.load(f)

            self.coins = int(d.get("coins", 0))
            self.income_per_tap = int(d.get("income_per_tap", 1))
            self.income_per_second = int(d.get("income_per_second", 0))

            self.tap_upg_level = int(d.get("tap_upg_level", 0))
            self.passive_upg_level = int(d.get("passive_upg_level", 0))
            self.offline_upg_level = int(d.get("offline_upg_level", 0))
            self.stability_upg_level = int(d.get("stability_upg_level", 0))

            self.tap_research_end_at = int(d.get("tap_research_end_at", 0))
            self.passive_research_end_at = int(d.get("passive_research_end_at", 0))
            self.offline_research_end_at = int(d.get("offline_research_end_at", 0))
            self.stability_research_end_at = int(d.get("stability_research_end_at", 0))

            self.last_saved_at = int(d.get("saved_at", 0))

            # --- Hardcore decay check (BEFORE offline earnings) ---
            if self.last_saved_at > 0 and self.stability_upg_level > 0:
                elapsed = max(0, int(time.time()) - self.last_saved_at)
                elapsed_hours = elapsed / 3600.0
                limit = stability_limit_hours(self.stability_upg_level)
                if limit > 0 and elapsed_hours > limit:
                    # Collapse: record highscore, reset, and skip offline earnings
                    self._record_highscore_and_reset(elapsed_hours)
                    return  # done; no offline earnings after collapse

            # --- Offline earnings (after decay check), capped at 24h ---
            if self.last_saved_at > 0 and self.income_per_second > 0:
                elapsed = max(0, int(time.time()) - self.last_saved_at)
                counted = min(elapsed, self.OFFLINE_CAP_SECONDS)
                if counted > 0:
                    eff = offline_efficiency(self.offline_upg_level)
                    gained = (Decimal(self.income_per_second) *
                              Decimal(counted) * eff)
                    gained_int = int(gained)  # floor
                    if gained_int > 0:
                        self.coins += gained_int
                        hours = counted // 3600
                        mins = (counted % 3600) // 60
                        timestr = (f"{hours}h {mins}m" if hours else f"{mins}m")
                        self._pending_events.append({
                            "type": "offline_reward",
                            "coins": gained_int,
                            "duration_str": timestr,
                            "eff": str(eff),  # show exact current eff in popup
                        })

        except Exception as e:
            messagebox.showwarning(
                "Load Error",
                f"Save file unreadable/corrupted.\nStarting fresh.\n\nDetails: {e}"
            )

    # -------- Popups (non-blocking overlays) --------
    def _popup_base(self, title_text: str, lines: list[str], button_text: str, button_callback):
        pop = tk.Toplevel(self.root)
        pop.title(title_text)
        pop.configure(bg=self.bg)
        pop.wm_attributes("-topmost", True)
        pop.resizable(False, False)

        # Center on parent
        self.root.update_idletasks()
        w, h = 440, 220
        x = self.root.winfo_x() + (self.root.winfo_width() // 2) - (w // 2)
        y = self.root.winfo_y() + (self.root.winfo_height() // 2) - (h // 2)
        pop.geometry(f"{w}x{h}+{x}+{y}")

        frame = ttk.Frame(pop, style="Card.TFrame", padding=16)
        frame.pack(fill="both", expand=True)

        header = ttk.Label(frame, text=title_text, style="Card.TLabel",
                           font=("Segoe UI", 14, "bold"), foreground=self.fg)
        header.pack(anchor="center", pady=(0, 8))

        for ln in lines:
            ttk.Label(frame, text=ln, style="Card.TLabel",
                      font=("Segoe UI", 11)).pack(anchor="w")

        ttk.Button(frame, text=button_text, style="Dark.TButton",
                   command=lambda: (button_callback(), pop.destroy())
                   ).pack(anchor="e", pady=(14,0))

        # Non-blocking: no grab_set; game continues underneath
        return pop

    def _show_offline_popup(self, coins_gained: int, duration_str: str, eff_str: str):
        # Show efficiency as short multiplier (e.g., x1.03)
        try:
            eff_val = Decimal(eff_str)
            eff_short = f"x{eff_val:.3f}".rstrip("0").rstrip(".")
        except Exception:
            eff_short = ""
        lines = [
            "While you were away:",
            f"• Duration counted: {duration_str}",
            f"• Coins earned: {fmt_short(coins_gained)} {f'({eff_short})' if eff_short else ''}"
        ]
        self._popup_base("💰 OFFLINE EARNINGS", lines, "OK", lambda: None)

    def _show_collapse_popup(self, elapsed_hours: float, limit_hours: int,
                             coins: int, tap: int, passive: int, offline: int, stability: int):
        lines = [
            f"You were gone for {round(elapsed_hours,2)}h, exceeding your {limit_hours}h limit.",
            "",
            "Highscore Recorded:",
            f"• Coins: {fmt_short(coins)}",
            f"• Tap: {tap}  |  Passive: {passive}",
            f"• Offline: {offline}  |  Stability: {stability}",
        ]
        # Start Over button only: reset already applied; this just closes
        def _noop(): pass
        self._popup_base("☠️ UNIVERSE COLLAPSED", lines, "Start Over", _noop)

    def _process_pending_events(self):
        # Show all queued popups; they are non-blocking overlays
        for ev in self._pending_events:
            if ev.get("type") == "offline_reward":
                self._show_offline_popup(ev["coins"], ev["duration_str"], ev["eff"])
            elif ev.get("type") == "collapse":
                self._show_collapse_popup(
                    ev["elapsed_hours"], ev["limit_hours"],
                    ev["coins"], ev["tap"], ev["passive"], ev["offline"], ev["stability"]
                )
        self._pending_events.clear()

    # -------- Close --------
    def on_close(self):
        self.save()
        self.root.destroy()

# -------------------- Bootstrap --------------------
def main():
    root = tk.Tk()
    root.minsize(500, 420)
    game = InfiniteTapGame(root)
    root.mainloop()

if __name__ == "__main__":
    main()
