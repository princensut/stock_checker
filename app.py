import matplotlib
matplotlib.use("Agg")  # MUST be first — before any pyplot import

import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from flask import Flask, request, jsonify, render_template
import yfinance as yf
import pandas as pd
import os
import uuid
from datetime import datetime, timedelta

app = Flask(__name__)

PLOT_DIR = os.path.join("static", "plots")
os.makedirs(PLOT_DIR, exist_ok=True)


def flatten_columns(df):
    """yfinance v0.2+ sometimes returns MultiIndex columns — flatten them."""
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [col[0] for col in df.columns]
    return df


def cleanup_old_plots():
    """Delete PNGs older than 1 hour to save disk space."""
    cutoff = datetime.now() - timedelta(hours=1)
    for fname in os.listdir(PLOT_DIR):
        fpath = os.path.join(PLOT_DIR, fname)
        if os.path.isfile(fpath):
            try:
                if datetime.fromtimestamp(os.path.getmtime(fpath)) < cutoff:
                    os.remove(fpath)
            except Exception:
                pass


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/analyze", methods=["POST"])
def analyze():
    cleanup_old_plots()

    payload = request.get_json(silent=True)
    if not payload:
        return jsonify({"error": "Invalid or missing JSON body"}), 400

    symbol      = str(payload.get("symbol", "")).strip().upper()
    moving_avg  = bool(payload.get("moving_avg", True))
    show_volume = bool(payload.get("volume", False))
    dark_export = bool(payload.get("dark_export", False))

    if not symbol:
        return jsonify({"error": "Symbol is required"}), 400

    # ── 1. Fetch data ───────────────────────────────────────────────────────
    try:
        df = yf.download(
            symbol,
            period="6mo",
            auto_adjust=True,
            progress=False,
            threads=False
        )
    except Exception as e:
        return jsonify({"error": f"Data fetch failed: {str(e)}"}), 500

    df = flatten_columns(df)

    if df is None or df.empty:
        return jsonify({"error": f"No data found for '{symbol}'. Check the ticker symbol."}), 404

    # ── 2. Validate & process ───────────────────────────────────────────────
    if "Close" not in df.columns:
        return jsonify({"error": f"Unexpected data format for '{symbol}'"}), 500

    if show_volume and "Volume" not in df.columns:
        show_volume = False

    df = df.copy()
    df.index = pd.to_datetime(df.index)
    df["Close"] = pd.to_numeric(df["Close"], errors="coerce")
    df = df.dropna(subset=["Close"])

    if len(df) < 2:
        return jsonify({"error": "Not enough data points to generate a chart"}), 404

    latest_price = float(df["Close"].iloc[-1])
    start_price  = float(df["Close"].iloc[0])
    high_price   = float(df["Close"].max())
    low_price    = float(df["Close"].min())
    pct_change   = ((latest_price - start_price) / start_price) * 100

    if moving_avg and len(df) >= 20:
        df["MA20"] = df["Close"].rolling(window=20).mean()
    else:
        moving_avg = False

    # ── 3. Generate plot ────────────────────────────────────────────────────
    # Try modern style name first, fall back for older matplotlib versions
    for style_name in ["seaborn-v0_8-whitegrid", "seaborn-whitegrid", "default"]:
        try:
            plt.style.use(style_name)
            break
        except OSError:
            continue

    fig_color  = "#0f0f23" if dark_export else "#faf9ff"
    line_color = "#818cf8" if dark_export else "#4f46e5"
    ma_color   = "#a78bfa" if dark_export else "#7c3aed"
    text_color = "#e2e8f0" if dark_export else "#1e1b4b"
    grid_color = "#1e2340" if dark_export else "#ede9fe"

    if show_volume:
        fig, (ax1, ax2) = plt.subplots(
            2, 1, figsize=(12, 7),
            gridspec_kw={"height_ratios": [3, 1]},
            facecolor=fig_color
        )
        ax2.set_facecolor(fig_color)
    else:
        fig, ax1 = plt.subplots(figsize=(12, 5), facecolor=fig_color)

    ax1.set_facecolor(fig_color)

    # Price line + area fill
    ax1.plot(df.index, df["Close"],
             color=line_color, linewidth=2.5, label="Close price", zorder=3)
    ax1.fill_between(df.index, df["Close"], df["Close"].min(),
                     color=line_color, alpha=0.10)

    # Moving average
    if moving_avg and "MA20" in df.columns:
        ax1.plot(df.index, df["MA20"],
                 color=ma_color, linewidth=1.5,
                 linestyle="--", alpha=0.85, label="MA 20")

    # Peak annotation
    try:
        peak_idx = df["Close"].idxmax()
        peak_val = float(df["Close"].max())
        ax1.scatter([peak_idx], [peak_val], color=line_color, s=60, zorder=5)
        ax1.annotate(
            f"  ${peak_val:,.2f}",
            xy=(peak_idx, peak_val),
            fontsize=9, color=line_color,
            arrowprops=dict(arrowstyle="-", color=line_color, alpha=0.4)
        )
    except Exception:
        pass

    # Axes styling
    ax1.xaxis.set_major_formatter(mdates.DateFormatter("%b '%y"))
    ax1.xaxis.set_major_locator(mdates.MonthLocator())
    plt.setp(ax1.xaxis.get_majorticklabels(), rotation=0, ha="center")
    ax1.tick_params(colors=text_color, labelsize=9)
    for spine in ax1.spines.values():
        spine.set_color(grid_color)
    ax1.set_ylabel("Price (USD)", color=text_color, fontsize=10)
    ax1.set_title(
        f"{symbol}  —  6-Month Price History",
        color=text_color, fontsize=13, fontweight="bold", pad=14
    )
    ax1.legend(facecolor=fig_color, edgecolor=grid_color,
               labelcolor=text_color, fontsize=9)
    ax1.grid(color=grid_color, linewidth=0.5)

    # Volume bars
    if show_volume:
        try:
            vol = pd.to_numeric(df["Volume"], errors="coerce").fillna(0)
            bar_colors = [
                "#6366f1" if c >= o else "#f43f5e"
                for c, o in zip(df["Close"], df["Close"].shift(1).fillna(df["Close"]))
            ]
            ax2.bar(df.index, vol, color=bar_colors, alpha=0.7, width=1)
            ax2.set_facecolor(fig_color)
            ax2.tick_params(colors=text_color, labelsize=8)
            for spine in ax2.spines.values():
                spine.set_color(grid_color)
            ax2.set_ylabel("Volume", color=text_color, fontsize=9)
            ax2.grid(color=grid_color, linewidth=0.4)
            ax2.xaxis.set_major_formatter(mdates.DateFormatter("%b"))
        except Exception:
            pass

    plt.tight_layout(pad=2)

    # ── 4. Save PNG ─────────────────────────────────────────────────────────
    filename = f"{symbol}_{uuid.uuid4().hex[:8]}.png"
    filepath = os.path.join(PLOT_DIR, filename)
    fig.savefig(filepath, dpi=150, bbox_inches="tight", facecolor=fig_color)
    plt.close(fig)

    # ── 5. Return JSON ───────────────────────────────────────────────────────
    return jsonify({
        "image_path": f"/static/plots/{filename}",
        "stats": {
            "symbol":       symbol,
            "latest_price": f"${latest_price:,.2f}",
            "pct_change":   f"{'+' if pct_change >= 0 else ''}{pct_change:.2f}%",
            "high":         f"${high_price:,.2f}",
            "low":          f"${low_price:,.2f}",
            "up":           bool(pct_change >= 0)
        }
    })


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
