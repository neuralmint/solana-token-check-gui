#!/usr/bin/env python3
"""
Solana Token Checker GUI
A desktop application for checking Solana token data via DexScreener API.
Pure Python + tkinter/ttk — no extra dependencies.
"""

import tkinter as tk
from tkinter import ttk, messagebox
import urllib.request
import urllib.error
import json
import threading
import time
import webbrowser
from datetime import datetime

# ── Configuration ──────────────────────────────────────────────────────────────
DEXSCREENER_API = "https://api.dexscreener.com/latest/dex/tokens/{}"
DARK_BG = "#1a1a2e"
DARK_SECONDARY = "#16213e"
DARK_CARD = "#0f3460"
ACCENT = "#e94560"
TEXT_PRIMARY = "#eaeaea"
TEXT_SECONDARY = "#a0a0b0"
FONT_FAMILY = "Segoe UI"

def build_style():
    """Configure ttk styles for a dark theme."""
    style = ttk.Style()
    style.theme_use("clam")

    style.configure(".", background=DARK_BG, foreground=TEXT_PRIMARY,
                    font=(FONT_FAMILY, 10))
    style.configure("TFrame", background=DARK_BG)
    style.configure("TLabel", background=DARK_BG, foreground=TEXT_PRIMARY,
                    font=(FONT_FAMILY, 10))
    style.configure("TEntry", fieldbackground=DARK_SECONDARY,
                    foreground=TEXT_PRIMARY, insertcolor=TEXT_PRIMARY,
                    borderwidth=0, relief="flat", font=(FONT_FAMILY, 11))
    style.map("TEntry", fieldbackground=[("focus", "#1a2744")])

    # Buttons
    style.configure("Accent.TButton", background=ACCENT, foreground="white",
                    borderwidth=0, focuscolor="none", font=(FONT_FAMILY, 10, "bold"))
    style.map("Accent.TButton",
              background=[("active", "#ff6b81"), ("pressed", "#c0392b")])

    style.configure("Secondary.TButton", background=DARK_CARD, foreground=TEXT_PRIMARY,
                    borderwidth=0, focuscolor="none", font=(FONT_FAMILY, 10))
    style.map("Secondary.TButton",
              background=[("active", "#1a5276"), ("pressed", "#0d2137")])

    # Headings
    style.configure("Heading.TLabel", font=(FONT_FAMILY, 16, "bold"),
                    foreground="white", background=DARK_BG)
    style.configure("Subheading.TLabel", font=(FONT_FAMILY, 12),
                    foreground=TEXT_SECONDARY, background=DARK_BG)
    style.configure("ResultValue.TLabel", font=(FONT_FAMILY, 11, "bold"),
                    background=DARK_CARD, foreground=TEXT_PRIMARY)
    style.configure("ResultLabel.TLabel", font=(FONT_FAMILY, 10),
                    background=DARK_CARD, foreground=TEXT_SECONDARY)
    style.configure("Card.TFrame", background=DARK_CARD, relief="flat",
                    borderwidth=0)
    style.configure("Status.TLabel", font=(FONT_FAMILY, 14, "bold"),
                    background=DARK_BG)

    return style


def make_card(parent):
    """Create a card-style frame with the dark card background."""
    frame = ttk.Frame(parent, style="Card.TFrame")
    frame.configure(borderwidth=0)
    frame["padding"] = 12
    return frame


def format_price(price_str):
    """Format a price string nicely, handling very small values."""
    try:
        price = float(price_str)
        if price < 0.0001:
            return f"${price:.8f}"
        elif price < 1:
            return f"${price:.6f}"
        elif price < 1000:
            return f"${price:.4f}"
        else:
            return f"${price:,.2f}"
    except (ValueError, TypeError):
        return "N/A"


def format_volume(vol_str):
    """Format volume with K/M/B suffixes."""
    try:
        vol = float(vol_str)
        if vol >= 1_000_000_000:
            return f"${vol/1_000_000_000:.2f}B"
        elif vol >= 1_000_000:
            return f"${vol/1_000_000:.2f}M"
        elif vol >= 1_000:
            return f"${vol/1_000:.2f}K"
        else:
            return f"${vol:.2f}"
    except (ValueError, TypeError):
        return "N/A"


def compute_risk_score(pair):
    """Compute a risk score (0-100) and category based on pair data.
    0 = safest, 100 = highest risk.
    """
    score = 0
    reasons = []

    try:
        age_days = float(pair.get("pairCreatedAt", 0))
        if age_days > 0:
            age_seconds = time.time() * 1000 - age_days
            age_hours = age_seconds / (1000 * 3600)
            if age_hours < 24:
                score += 35
                reasons.append("Created <24h ago")
            elif age_hours < 72:
                score += 20
                reasons.append("Created <3 days ago")
            elif age_hours < 168:
                score += 10
                reasons.append("Created <1 week ago")
    except (ValueError, TypeError):
        score += 5

    liquidity_usd = pair.get("liquidity", {}).get("usd", 0)
    if liquidity_usd:
        try:
            liq = float(liquidity_usd)
            if liq < 1000:
                score += 30
                reasons.append("Low liquidity (<$1K)")
            elif liq < 10000:
                score += 20
                reasons.append(f"Low liquidity (<$10K)")
            elif liq < 100000:
                score += 10
            elif liq > 1000000:
                score -= 10  # bonus for high liquidity
        except (ValueError, TypeError):
            score += 20
    else:
        score += 25
        reasons.append("No liquidity data")

    txns = pair.get("txns", {})
    h24 = txns.get("h24", {}) if txns else {}
    total_txns = 0
    try:
        total_txns = int(h24.get("buys", 0)) + int(h24.get("sells", 0))
    except (ValueError, TypeError):
        pass

    if total_txns == 0:
        score += 20
        reasons.append("No 24h transactions")
    elif total_txns < 10:
        score += 15
        reasons.append("Very low 24h volume")

    volume_h24 = pair.get("volume", {}).get("h24", 0)
    if volume_h24:
        try:
            if float(volume_h24) < 100:
                score += 20
                reasons.append("Tiny 24h volume (<$100)")
            elif float(volume_h24) < 1000:
                score += 10
        except (ValueError, TypeError):
            pass

    price_change_h24 = pair.get("priceChange", {}).get("h24", 0)
    if price_change_h24:
        try:
            pc = abs(float(price_change_h24))
            if pc > 500:
                score += 20
                reasons.append("Extreme price volatility")
            elif pc > 100:
                score += 10
                reasons.append("High price volatility")
        except (ValueError, TypeError):
            pass

    fdv = pair.get("fdv", 0)
    if fdv:
        try:
            fdv_float = float(fdv)
            if fdv_float < 10000:
                score += 15
                reasons.append("Low FDV (<$10K)")
        except (ValueError, TypeError):
            pass

    score = max(0, min(100, score))

    if score <= 20:
        category = "low"
        color = "#2ecc71"  # green
    elif score <= 40:
        category = "medium"
        color = "#f1c40f"  # yellow
    elif score <= 65:
        category = "high"
        color = "#e67e22"  # orange
    else:
        category = "critical"
        color = "#e74c3c"  # red

    return score, category, color, reasons


class SolanaTokenChecker:
    """Main application class."""

    def __init__(self, root):
        self.root = root
        self.root.title("Solana Token Checker")
        self.root.configure(bg=DARK_BG)
        self.root.minsize(520, 600)

        # Center the window
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        w, h = 600, 700
        x = (screen_w - w) // 2
        y = (screen_h - h) // 2
        self.root.geometry(f"{w}x{h}+{x}+{y}")

        self.style = build_style()
        self.result_data = None
        self.trending_data = []
        self.current_view = "check"  # "check" or "trending"

        self._build_ui()
        self._bind_events()

    def _build_ui(self):
        """Construct the user interface."""
        # ── Header ──────────────────────────────────────────────────────────
        header = ttk.Frame(self.root, style="TFrame")
        header.pack(fill="x", padx=20, pady=(20, 5))

        ttk.Label(header, text="Solana Token Checker",
                  style="Heading.TLabel").pack(anchor="w")
        ttk.Label(header, text="Powered by DexScreener API",
                  style="Subheading.TLabel").pack(anchor="w")

        # ── Input Area ─────────────────────────────────────────────────────
        input_frame = ttk.Frame(self.root, style="TFrame")
        input_frame.pack(fill="x", padx=20, pady=(15, 10))

        ttk.Label(input_frame, text="Token Address / CA:",
                  style="TLabel").pack(anchor="w", pady=(0, 5))

        entry_frame = ttk.Frame(input_frame, style="TFrame")
        entry_frame.pack(fill="x")

        self.address_entry = ttk.Entry(entry_frame, style="TEntry")
        self.address_entry.pack(side="left", fill="x", expand=True, padx=(0, 8), ipady=6)

        self.check_btn = ttk.Button(entry_frame, text="Check Token",
                                    style="Accent.TButton",
                                    command=self.check_token)
        self.check_btn.pack(side="left")

        # ── Button Row ─────────────────────────────────────────────────────
        btn_frame = ttk.Frame(self.root, style="TFrame")
        btn_frame.pack(fill="x", padx=20, pady=(0, 12))

        self.trending_btn = ttk.Button(btn_frame, text="🔥 Trending",
                                       style="Secondary.TButton",
                                       command=self.fetch_trending)
        self.trending_btn.pack(side="left", padx=(0, 8))

        self.clear_btn = ttk.Button(btn_frame, text="Clear",
                                    style="Secondary.TButton",
                                    command=self.clear_results)
        self.clear_btn.pack(side="left")

        # ── Status Bar ─────────────────────────────────────────────────────
        self.status_label = ttk.Label(self.root, text="Ready",
                                      style="Status.TLabel")
        self.status_label.pack(fill="x", padx=20, pady=(0, 5))

        # ── Results Area (scrollable canvas) ───────────────────────────────
        canvas_frame = ttk.Frame(self.root, style="TFrame")
        canvas_frame.pack(fill="both", expand=True, padx=20, pady=(0, 20))

        self.canvas = tk.Canvas(canvas_frame, bg=DARK_BG,
                                highlightthickness=0, borderwidth=0)
        scrollbar = ttk.Scrollbar(canvas_frame, orient="vertical",
                                  command=self.canvas.yview)
        self.scrollable_frame = ttk.Frame(self.canvas, style="TFrame")

        self.scrollable_frame.bind("<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))

        self.canvas_window = self.canvas.create_window(
            (0, 0), window=self.scrollable_frame, anchor="nw", width=560)

        self.canvas.configure(yscrollcommand=scrollbar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # Bind canvas resize to stretch inner frame
        self.canvas.bind("<Configure>", self._on_canvas_configure)

        # Mouse wheel scrolling
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)

        # Placeholder text
        self.placeholder_frame = ttk.Frame(self.scrollable_frame, style="TFrame")
        self.placeholder_frame.pack(fill="both", expand=True, pady=60)
        ttk.Label(self.placeholder_frame,
                  text="Enter a Solana token address and click\n'Check Token' to get started.",
                  style="Subheading.TLabel",
                  justify="center").pack(expand=True)

        self.input_history = []
        self.results_container = ttk.Frame(self.scrollable_frame, style="TFrame")

    def _on_canvas_configure(self, event):
        """Resize the inner frame to match canvas width."""
        self.canvas.itemconfig(self.canvas_window, width=event.width)

    def _on_mousewheel(self, event):
        self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _bind_events(self):
        """Bind keyboard shortcuts."""
        self.address_entry.bind("<Return>", lambda e: self.check_token())
        self.root.bind("<Control-c>", lambda e: self.clear_results())

    def set_status(self, text, color=None):
        """Update the status bar text."""
        self.status_label.configure(text=text)
        if color:
            self.status_label.configure(foreground=color)
        else:
            self.status_label.configure(foreground=TEXT_PRIMARY if "Error" not in text else ACCENT)

    def clear_results(self):
        """Clear all results and reset the view."""
        for widget in self.results_container.winfo_children():
            widget.destroy()
        self.results_container.pack_forget()
        self.placeholder_frame.pack(fill="both", expand=True, pady=60)
        self.address_entry.delete(0, tk.END)
        self.set_status("Ready", TEXT_SECONDARY)
        self.current_view = "check"

    def check_token(self):
        """Initiate a token check in a background thread."""
        address = self.address_entry.get().strip()
        if not address:
            messagebox.showwarning("Input Required", "Please enter a token address.")
            return
        if len(address) < 32:
            self.set_status("Warning: Address seems too short for a valid Solana address", ACCENT)
            # Still try, API will tell us
        self.set_status("🔍 Checking token...", "#3498db")
        self.check_btn.configure(state="disabled")
        self.trending_btn.configure(state="disabled")
        thread = threading.Thread(target=self._check_token_thread, args=(address,),
                                  daemon=True)
        thread.start()

    def _check_token_thread(self, address):
        """Fetch token data from DexScreener (runs in background thread)."""
        try:
            url = DEXSCREENER_API.format(address)
            req = urllib.request.Request(url, headers={
                "User-Agent": "SolanaTokenChecker/1.0",
                "Accept": "application/json"
            })
            with urllib.request.urlopen(req, timeout=15) as response:
                data = json.loads(response.read().decode("utf-8"))
            self.root.after(0, self._display_token_result, address, data)
        except urllib.error.HTTPError as e:
            self.root.after(0, self._show_error,
                            f"API Error: HTTP {e.code} — {e.reason}")
        except urllib.error.URLError as e:
            self.root.after(0, self._show_error,
                            f"Connection Error: {e.reason}")
        except json.JSONDecodeError:
            self.root.after(0, self._show_error,
                            "Invalid response from API")
        except Exception as e:
            self.root.after(0, self._show_error,
                            f"Unexpected error: {str(e)}")

    def _display_token_result(self, address, data):
        """Render token results in the UI."""
        self.check_btn.configure(state="normal")
        self.trending_btn.configure(state="normal")

        pairs = data.get("pairs")
        if not pairs:
            self.set_status(f"❌ No data found for this address", ACCENT)
            self._show_error(f"No token data found for address:\n{address[:8]}...{address[-6:]}\n\n"
                             f"The address may be invalid or the token has no liquidity pools on DexScreener.")
            return

        # Filter for Solana pairs
        sol_pairs = [p for p in pairs if p.get("chainId") == "solana"]
        if not sol_pairs:
            # Use the first pair anyway if no Solana-specific ones
            sol_pairs = [pairs[0]]

        sol_pairs.sort(
            key=lambda p: float(p.get("liquidity", {}).get("usd", 0) or 0),
            reverse=True
        )

        self.result_data = sol_pairs
        self.current_view = "check"
        self._render_token_info(sol_pairs, address)

    def _render_token_info(self, pairs, address):
        """Render the token information cards."""
        # Remove placeholder
        self.placeholder_frame.pack_forget()
        self.results_container.pack(fill="both", expand=True)

        # Clear previous
        for widget in self.results_container.winfo_children():
            widget.destroy()

        pair = pairs[0]  # Highest liquidity pair
        base = pair.get("baseToken", {})
        quote = pair.get("quoteToken", {})

        token_name = base.get("name", "Unknown")
        token_symbol = base.get("symbol", "???")
        token_address = base.get("address", address)

        # ── Token Header Card ───────────────────────────────────────────────
        header_card = make_card(self.results_container)
        header_card.pack(fill="x", pady=(0, 10))

        ttk.Label(header_card, text=f"{token_name} ({token_symbol})",
                  font=(FONT_FAMILY, 14, "bold"), background=DARK_CARD,
                  foreground="white").pack(anchor="w")

        addr_text = f"{token_address[:8]}...{token_address[-6:]}"
        addr_frame = ttk.Frame(header_card, style="Card.TFrame")
        addr_frame.pack(anchor="w", pady=(2, 0))
        ttk.Label(addr_frame, text=f"CA: {addr_text}",
                  font=(FONT_FAMILY, 9), background=DARK_CARD,
                  foreground="#5dade2", cursor="hand2").pack(side="left")

        # ── Price Card ──────────────────────────────────────────────────────
        price_card = make_card(self.results_container)
        price_card.pack(fill="x", pady=(0, 8))

        price_usd = pair.get("priceUsd", "N/A")
        price_native = pair.get("priceNative", "N/A")

        ttk.Label(price_card, text="💰 Price",
                  style="ResultLabel.TLabel").pack(anchor="w")
        ttk.Label(price_card,
                  text=format_price(price_usd),
                  font=(FONT_FAMILY, 22, "bold"),
                  background=DARK_CARD,
                  foreground="#2ecc71").pack(anchor="w", pady=(2, 0))

        # Price change
        pc_h24 = pair.get("priceChange", {}).get("h24", 0)
        if pc_h24:
            try:
                pc_val = float(pc_h24)
                pc_color = "#2ecc71" if pc_val >= 0 else ACCENT
                pc_sign = "+" if pc_val >= 0 else ""
                ttk.Label(price_card,
                          text=f"24h: {pc_sign}{pc_val:.2f}%",
                          font=(FONT_FAMILY, 10),
                          background=DARK_CARD,
                          foreground=pc_color).pack(anchor="w")
            except (ValueError, TypeError):
                pass

        # ── Market Data Cards (2-column grid) ───────────────────────────────
        metrics_frame = ttk.Frame(self.results_container, style="TFrame")
        metrics_frame.pack(fill="x", pady=(0, 8))

        # Column 1
        col1 = ttk.Frame(metrics_frame, style="TFrame")
        col1.pack(side="left", fill="x", expand=True, padx=(0, 6))

        # Liquidity
        liq_frame = make_card(col1)
        liq_frame.pack(fill="x", pady=(0, 6))
        ttk.Label(liq_frame, text="💧 Liquidity",
                  style="ResultLabel.TLabel").pack(anchor="w")
        liq_usd = pair.get("liquidity", {}).get("usd", 0)
        ttk.Label(liq_frame,
                  text=format_volume(liq_usd),
                  style="ResultValue.TLabel",
                  foreground="#3498db").pack(anchor="w")

        # 24h Volume
        vol_frame = make_card(col1)
        vol_frame.pack(fill="x")
        ttk.Label(vol_frame, text="📊 24h Volume",
                  style="ResultLabel.TLabel").pack(anchor="w")
        vol_h24 = pair.get("volume", {}).get("h24", 0)
        ttk.Label(vol_frame,
                  text=format_volume(vol_h24),
                  style="ResultValue.TLabel",
                  foreground="#9b59b6").pack(anchor="w")

        # Column 2
        col2 = ttk.Frame(metrics_frame, style="TFrame")
        col2.pack(side="left", fill="x", expand=True, padx=(6, 0))

        # FDV
        fdv_frame = make_card(col2)
        fdv_frame.pack(fill="x", pady=(0, 6))
        ttk.Label(fdv_frame, text="📈 FDV",
                  style="ResultLabel.TLabel").pack(anchor="w")
        fdv = pair.get("fdv", 0)
        ttk.Label(fdv_frame,
                  text=format_volume(fdv) if fdv else "N/A",
                  style="ResultValue.TLabel",
                  foreground="#f39c12").pack(anchor="w")

        # Market Cap
        mcap_frame = make_card(col2)
        mcap_frame.pack(fill="x")
        ttk.Label(mcap_frame, text="🏷️ Market Cap",
                  style="ResultLabel.TLabel").pack(anchor="w")
        mcap = pair.get("marketCap", 0)
        ttk.Label(mcap_frame,
                  text=format_volume(mcap) if mcap else "N/A",
                  style="ResultValue.TLabel",
                  foreground="#1abc9c").pack(anchor="w")

        # ── Pair Info Card ───────────────────────────────────────────────
        pair_card = make_card(self.results_container)
        pair_card.pack(fill="x", pady=(0, 8))

        ttk.Label(pair_card, text="🔗 Pair Info",
                  style="ResultLabel.TLabel").pack(anchor="w")

        info_frame = ttk.Frame(pair_card, style="Card.TFrame")
        info_frame.pack(fill="x", pady=(4, 0))

        labels_data = [
            ("Pair", f"{base.get('symbol', '?')}/{quote.get('symbol', '?')}"),
            ("DEX", pair.get("dexId", "N/A")),
            ("Created", self._format_age(pair.get("pairCreatedAt", 0))),
            ("5m Txns", self._format_txns(pair, "m5")),
            ("1h Txns", self._format_txns(pair, "h1")),
            ("24h Txns", self._format_txns(pair, "h24")),
        ]

        for i, (label, value) in enumerate(labels_data):
            row = ttk.Frame(info_frame, style="Card.TFrame")
            row.pack(fill="x", pady=(1, 0))
            ttk.Label(row, text=label, width=10,
                      font=(FONT_FAMILY, 9), background=DARK_CARD,
                      foreground=TEXT_SECONDARY, anchor="w").pack(side="left")
            ttk.Label(row, text=value,
                      font=(FONT_FAMILY, 9, "bold"), background=DARK_CARD,
                      foreground=TEXT_PRIMARY, anchor="w").pack(side="left",
                                                                padx=(8, 0))

        # ── Risk Score Card ─────────────────────────────────────────────
        risk_score, risk_cat, risk_color, reasons = compute_risk_score(pair)

        risk_card = make_card(self.results_container)
        risk_card.pack(fill="x", pady=(0, 8))

        ttk.Label(risk_card, text="🛡️ Risk Assessment",
                  style="ResultLabel.TLabel").pack(anchor="w")

        score_frame = ttk.Frame(risk_card, style="Card.TFrame")
        score_frame.pack(fill="x", pady=(6, 0))

        # The score bar
        bar_bg = ttk.Frame(score_frame, style="Card.TFrame", height=18)
        bar_bg.pack(fill="x", pady=(0, 6))
        bar_bg.pack_propagate(False)

        bar_canvas = tk.Canvas(bar_bg, height=18, bg="#1a1a2e",
                                highlightthickness=0, borderwidth=0)
        bar_canvas.pack(fill="x")

        # Draw gradient-like bar
        bar_width = 500
        bar_canvas.create_rectangle(0, 0, bar_width * (risk_score / 100), 18,
                                     fill=risk_color, outline="", tags="fillbar")

        # Label
        risk_labels = {
            "low": "✅ Low Risk",
            "medium": "⚠️ Medium Risk",
            "high": "🔶 High Risk",
            "critical": "🚨 CRITICAL"
        }
        risk_text = risk_labels.get(risk_cat, "Unknown")

        ttk.Label(score_frame,
                  text=f"Score: {risk_score}/100 — {risk_text}",
                  font=(FONT_FAMILY, 12, "bold"),
                  background=DARK_CARD,
                  foreground=risk_color).pack(anchor="w")

        if reasons:
            reasons_frame = ttk.Frame(score_frame, style="Card.TFrame")
            reasons_frame.pack(fill="x", pady=(4, 0))
            ttk.Label(reasons_frame, text="Risk factors:",
                      font=(FONT_FAMILY, 9), background=DARK_CARD,
                      foreground=TEXT_SECONDARY).pack(anchor="w")
            for reason in reasons[:5]:
                ttk.Label(reasons_frame, text=f"  • {reason}",
                          font=(FONT_FAMILY, 9), background=DARK_CARD,
                          foreground="#e67e22").pack(anchor="w")

        # ── DexScreener Link ─────────────────────────────────────────────
        url = f"https://dexscreener.com/solana/{token_address}"
        link_card = make_card(self.results_container)
        link_card.pack(fill="x", pady=(0, 8))

        link_label = ttk.Label(link_card,
                               text="🔗 View on DexScreener ↗",
                               font=(FONT_FAMILY, 10, "bold"),
                               background=DARK_CARD,
                               foreground="#5dade2",
                               cursor="hand2")
        link_label.pack(anchor="w")
        link_label.bind("<Button-1>", lambda e, u=url: webbrowser.open(u))

        self.set_status(f"✅ Loaded data for {token_name} ({token_symbol})",
                        "#2ecc71")

    def _format_age(self, created_at):
        """Format a Unix timestamp (ms) into a human-readable age."""
        try:
            created_seconds = int(created_at) / 1000
            now = time.time()
            delta = now - created_seconds
            if delta < 0:
                return "Just now"
            days = int(delta // 86400)
            hours = int((delta % 86400) // 3600)
            mins = int((delta % 3600) // 60)
            parts = []
            if days > 0:
                parts.append(f"{days}d")
            if hours > 0:
                parts.append(f"{hours}h")
            parts.append(f"{mins}m")
            return " ".join(parts) + " ago" if parts else "Just now"
        except (ValueError, TypeError):
            return "N/A"

    def _format_txns(self, pair, period):
        """Format transaction counts for a given period."""
        txns = pair.get("txns", {})
        period_data = txns.get(period, {}) if txns else {}
        buys = period_data.get("buys", 0)
        sells = period_data.get("sells", 0)
        if buys == 0 and sells == 0:
            return "None"
        return f"B: {buys} / S: {sells}"

    def _show_error(self, message):
        """Display an error message."""
        self.check_btn.configure(state="normal")
        self.trending_btn.configure(state="normal")
        self.placeholder_frame.pack_forget()
        self.results_container.pack(fill="both", expand=True)
        for widget in self.results_container.winfo_children():
            widget.destroy()

        error_card = make_card(self.results_container)
        error_card.pack(fill="x", pady=20)

        ttk.Label(error_card,
                  text="❌ Error",
                  font=(FONT_FAMILY, 14, "bold"),
                  background=DARK_CARD,
                  foreground=ACCENT).pack(anchor="w", pady=(0, 8))

        ttk.Label(error_card,
                  text=message,
                  font=(FONT_FAMILY, 10),
                  background=DARK_CARD,
                  foreground=TEXT_PRIMARY,
                  wraplength=500,
                  justify="left").pack(anchor="w")

        self.set_status("❌ " + message.split("\n")[0], ACCENT)

    def fetch_trending(self):
        """Fetch trending Solana tokens via DexScreener."""
        self.set_status("🔥 Fetching trending tokens...", "#e67e22")
        self.check_btn.configure(state="disabled")
        self.trending_btn.configure(state="disabled")
        thread = threading.Thread(target=self._trending_thread, daemon=True)
        thread.start()

    def _trending_thread(self):
        """Fetch trending data from DexScreener search endpoint."""
        try:
            # DexScreener doesn't have a dedicated trending endpoint,
            # so we search for common pairs or use tokens sorted by volume
            url = "https://api.dexscreener.com/latest/dex/tokens/solana"
            req = urllib.request.Request(url, headers={
                "User-Agent": "SolanaTokenChecker/1.0",
                "Accept": "application/json"
            })
            with urllib.request.urlopen(req, timeout=15) as response:
                data = json.loads(response.read().decode("utf-8"))

            pairs = data.get("pairs", [])
            sol_pairs = [p for p in pairs if p.get("chainId") == "solana"]

            if len(sol_pairs) < 5:
                # Try a broader search
                url2 = "https://api.dexscreener.com/latest/dex/tokens/SOL"
                req2 = urllib.request.Request(url2, headers={
                    "User-Agent": "SolanaTokenChecker/1.0",
                    "Accept": "application/json"
                })
                with urllib.request.urlopen(req2, timeout=15) as response2:
                    data2 = json.loads(response2.read().decode("utf-8"))
                pairs2 = data2.get("pairs", [])
                sol_pairs2 = [p for p in pairs2 if p.get("chainId") == "solana"]
                sol_pairs.extend(sol_pairs2)

            # Deduplicate by baseToken address
            seen = set()
            unique_pairs = []
            for p in sol_pairs:
                addr = p.get("baseToken", {}).get("address", "")
                if addr and addr not in seen:
                    seen.add(addr)
                    unique_pairs.append(p)

            # Sort by 24h volume descending (trending = highest volume)
            unique_pairs.sort(
                key=lambda p: float(p.get("volume", {}).get("h24", 0) or 0),
                reverse=True
            )

            self.root.after(0, self._display_trending, unique_pairs[:20])
        except Exception as e:
            self.root.after(0, self._show_error,
                            f"Failed to fetch trending: {str(e)}")

    def _display_trending(self, pairs):
        """Display trending tokens in a table format."""
        self.check_btn.configure(state="normal")
        self.trending_btn.configure(state="normal")

        self.placeholder_frame.pack_forget()
        self.results_container.pack(fill="both", expand=True)
        for widget in self.results_container.winfo_children():
            widget.destroy()

        self.current_view = "trending"
        self.trending_data = pairs

        if not pairs:
            self._show_error("No trending tokens found.")
            return

        # Header
        header_card = make_card(self.results_container)
        header_card.pack(fill="x", pady=(0, 10))
        ttk.Label(header_card, text="🔥 Trending Solana Tokens",
                  font=(FONT_FAMILY, 14, "bold"), background=DARK_CARD,
                  foreground="white").pack(anchor="w")
        ttk.Label(header_card, text=f"Top {len(pairs)} by 24h volume",
                  font=(FONT_FAMILY, 10), background=DARK_CARD,
                  foreground=TEXT_SECONDARY).pack(anchor="w")

        # Table header
        table_frame = ttk.Frame(self.results_container, style="TFrame")
        table_frame.pack(fill="both", expand=True)

        # Scrollable table area
        table_canvas = tk.Canvas(table_frame, bg=DARK_BG,
                                  highlightthickness=0, borderwidth=0)
        table_scroll = ttk.Scrollbar(table_frame, orient="vertical",
                                      command=table_canvas.yview)
        table_inner = ttk.Frame(table_canvas, style="TFrame")

        table_inner.bind("<Configure>",
            lambda e: table_canvas.configure(scrollregion=table_canvas.bbox("all")))

        table_canvas_window = table_canvas.create_window(
            (0, 0), window=table_inner, anchor="nw")

        table_canvas.configure(yscrollcommand=table_scroll.set)
        table_canvas.pack(side="left", fill="both", expand=True)
        table_scroll.pack(side="right", fill="y")

        def on_tc_configure(event):
            table_canvas.itemconfig(table_canvas_window, width=event.width)
        table_canvas.bind("<Configure>", on_tc_configure)

        # Mouse wheel for table
        def on_table_wheel(event):
            table_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        table_canvas.bind_all("<MouseWheel>", on_table_wheel)

        # Column headers
        col_header = ttk.Frame(table_inner, style="Card.TFrame")
        col_header.pack(fill="x", pady=(0, 4))
        col_header.configure(padding=(8, 6))

        for i, (text, width) in enumerate([
            ("#", 30), ("Token", 120), ("Price", 90),
            ("24h Vol", 90), ("Liq", 80), ("Risk", 70)
        ]):
            lbl = ttk.Label(col_header, text=text,
                           font=(FONT_FAMILY, 9, "bold"),
                           background=DARK_CARD, foreground=TEXT_SECONDARY,
                           width=width//7)
            lbl.pack(side="left", padx=(4, 0))

        # Rows
        for idx, pair in enumerate(pairs):
            base = pair.get("baseToken", {})
            sym = base.get("symbol", "???")
            price = format_price(pair.get("priceUsd", "N/A"))
            vol = format_volume(pair.get("volume", {}).get("h24", 0))
            liq = format_volume(pair.get("liquidity", {}).get("usd", 0))

            risk_score, risk_cat, risk_color, _ = compute_risk_score(pair)

            bg = DARK_SECONDARY if idx % 2 == 0 else "#1a1a2e"

            row = ttk.Frame(table_inner, style="TFrame")
            row.configure(padding=(8, 5))
            # Manually set bg using Canvas or Frame trick
            row_inner = tk.Frame(row, bg=bg)
            row_inner.pack(fill="both", expand=True)

            row_data = [
                (str(idx + 1), TEXT_SECONDARY, 30),
                (sym, TEXT_PRIMARY, 120),
                (price, "#2ecc71" if float(pair.get("priceUsd", 0) or 0) > 0 else TEXT_SECONDARY, 90),
                (vol, "#9b59b6", 90),
                (liq, "#3498db", 80),
                (risk_cat.upper(), risk_color, 70),
            ]

            for text, color, width in row_data:
                lbl = tk.Label(row_inner, text=text, bg=bg, fg=color,
                              font=(FONT_FAMILY, 9), anchor="w", padx=4)
                lbl.pack(side="left", fill="x", expand=True)

            row.pack(fill="x")
            # Store address for click action
            addr = base.get("address", "")
            if addr:
                row.bind("<Button-1>", lambda e, a=addr: self._trending_click(a))
                for child in row.winfo_children():
                    child.bind("<Button-1>", lambda e, a=addr: self._trending_click(a))

        self.set_status(f"🔥 Showing {len(pairs)} trending tokens", "#e67e22")

    def _trending_click(self, address):
        """Handle clicking on a trending token row."""
        self.address_entry.delete(0, tk.END)
        self.address_entry.insert(0, address)
        self.check_token()


def main():
    root = tk.Tk()
    app = SolanaTokenChecker(root)
    root.mainloop()


if __name__ == "__main__":
    main()
