import matplotlib
matplotlib.use("Agg")  # must be before pyplot import — required for headless servers

from flask import Flask, request, jsonify, render_template, send_from_directory
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import yfinance as yf
import pandas as pd
import os
import uuid
from datetime import datetime, timedelta

app = Flask(__name__)

PLOT_DIR = os.path.join("static", "plots")
os.makedirs(PLOT_DIR, exist_ok=True)


def cleanup_old_plots():
    """Delete plot PNGs older than 1 hour to save disk space."""
    cutoff = datetime.now() - timedelta(hours=1)
    for fname in os.listdir(PLOT_DIR):
        fpath = os.path.join(PLOT_DIR, fname)
        if os.path.isfile(fpath):
            modified = datetime.fromtimestamp(os.path.getmtime(fpath))
            if modified < cutoff:
                os.remove(fpath)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/analyze", methods=["POST"])
def analyze():
    cleanup_old_plots()

    data = request.get_json()
    if not data:
        return jsonify({"error": "No data received"}), 400

    symbol      = data.get("symbol", "").strip().upper()
    moving_avg  = data.get("moving_avg", True)
    show_volume = data.get("volume", False)
    dark_export = data.get("dark_export", False)

    if not symbol:
        return jsonify({"error": "Symbol is required"}), 400

    # ── Fetch data ──────────────────────────────────────────────────────────
    try:
        df = yf.download(symbol, period="6mo", auto_adjust=True, progress=False)
    except Exception as e:
        return jsonify({"error": f"Failed to fetch data: {str(e)}"}), 500

    if df is None or df.empty:
        return jsonify({"error": f"No data found for symbol '{symbol}'"}), 404

    # ── Process data ─────────────────────────────────────────────────────────
    df = df[["Close", "Volume"]].dropna()
    df.index = pd.to_datetime(df.index)

    latest_price = round(float(df["Close"].iloc[-1]), 2)
    start_price  = round(float(df["Close"].iloc[0]),  2)
    high_price   = round(float(df["Close"].max()),     2)
    low_price    = round(float(df["Close"].min()),     2)
    pct_change   = round(((latest_price - start_price) / start_price) * 100, 2)

    if moving_avg:
        df["MA20"] = df["Close"].rolling(window=20).mean()

    # ── Generate plot ─────────────────────────────────────────────────────────
    style = "dark_background" if dark_export else "seaborn-v0_8-whitegrid"
    plt.style.use(style)

    fig_color   = "#0f0f23" if dark_export else "#faf9ff"
    line_color  = "#818cf8" if dark_export else "#4f46e5"
    ma_color    = "#a78bfa" if dark_export else "#7c3aed"
    text_color  = "#e2e8f0" if dark_export else "#1e1b4b"
    grid_color  = "#1e2340" if dark_export else "#ede9fe"

    if show_volume:
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 7),
                                        gridspec_kw={"height_ratios": [3, 1]},
                                        facecolor=fig_color)
        ax2.set_facecolor(fig_color)
    else:
        fig, ax1 = plt.subplots(figsize=(12, 5), facecolor=fig_color)

    ax1.set_facecolor(fig_color)

    # Price line with fill
    ax1.plot(df.index, df["Close"], color=line_color, linewidth=2.5,
             label="Close price", zorder=3)
    ax1.fill_between(df.index, df["Close"], df["Close"].min(),
                     color=line_color, alpha=0.06)

    # Moving average
    if moving_avg and "MA20" in df.columns:
        ax1.plot(df.index, df["MA20"], color=ma_color, linewidth=1.5,
                 linestyle="--", alpha=0.8, label="MA 20")

    # Peak marker
    peak_idx = df["Close"].idxmax()
    peak_val = df["Close"].max()
    ax1.annotate(f"  ${peak_val:.2f}",
                 xy=(peak_idx, peak_val),
                 fontsize=9, color=line_color,
                 arrowprops=dict(arrowstyle="-", color=line_color, alpha=0.4))
    ax1.scatter([peak_idx], [peak_val], color=line_color, s=50, zorder=5)

    # Axes styling
    ax1.xaxis.set_major_formatter(mdates.DateFormatter("%b '%y"))
    ax1.xaxis.set_major_locator(mdates.MonthLocator())
    ax1.tick_params(colors=text_color, labelsize=9)
    ax1.spines[:].set_color(grid_color)
    ax1.set_ylabel("Price (USD)", color=text_color, fontsize=10)
    ax1.set_title(f"{symbol} — 6-Month Price History", color=text_color,
                  fontsize=13, fontweight="bold", pad=14)
    ax1.legend(facecolor=fig_color, edgecolor=grid_color,
               labelcolor=text_color, fontsize=9)
    ax1.grid(color=grid_color, linewidth=0.5)

    # Volume bars
    if show_volume:
        colors = ["#6366f1" if c >= o else "#f43f5e"
                  for c, o in zip(df["Close"], df["Close"].shift(1).fillna(df["Close"]))]
        ax2.bar(df.index, df["Volume"], color=colors, alpha=0.7, width=1)
        ax2.set_facecolor(fig_color)
        ax2.tick_params(colors=text_color, labelsize=8)
        ax2.spines[:].set_color(grid_color)
        ax2.set_ylabel("Volume", color=text_color, fontsize=9)
        ax2.grid(color=grid_color, linewidth=0.4)
        ax2.xaxis.set_major_formatter(mdates.DateFormatter("%b"))

    plt.tight_layout(pad=2)

    # Save
    filename = f"{symbol}_{uuid.uuid4().hex[:8]}.png"
    filepath = os.path.join(PLOT_DIR, filename)
    fig.savefig(filepath, dpi=150, bbox_inches="tight", facecolor=fig_color)
    plt.close(fig)

    return jsonify({
        "image_path": f"/static/plots/{filename}",
        "stats": {
            "symbol":       symbol,
            "latest_price": f"${latest_price:,.2f}",
            "pct_change":   f"{'+' if pct_change >= 0 else ''}{pct_change:.2f}%",
            "high":         f"${high_price:,.2f}",
            "low":          f"${low_price:,.2f}",
            "up":           pct_change >= 0
        }
    })


if __name__ == "__main__":
    app.run(debug=True)
