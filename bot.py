import logging
import pandas as pd
import numpy as np
import yfinance as yf
from ta.trend import EMAIndicator, MACD
from ta.momentum import RSIIndicator
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from datetime import datetime
import pytz

# ================= CONFIG =================
import os

TOKEN = os.getenv("TOKEN")
CHAT_ID = int(os.getenv("CHAT_ID"))

PAIRS = {
    "EURUSD": "EURUSD=X",
    "GBPUSD": "GBPUSD=X",
    "USDJPY": "JPY=X",
    "AUDUSD": "AUDUSD=X",
    "USDCHF": "CHF=X",
    "USDCAD": "CAD=X",
}

TIMEFRAMES = {
    "M1": "1m",
    "M5": "5m",
}

bot_active = True
stats = {"win": 0, "loss": 0}
last_signal_time = {}

logging.basicConfig(level=logging.INFO)

# ================= INDICATOR ENGINE =================
def analyze(pair, yf_symbol, tf, mode):
    df = yf.download(yf_symbol, period="1d", interval=tf)
    if df.empty or len(df) < 50:
        return None
        
df = df.dropna()
    close = df["Close"].squeeze()

    ema50 = EMAIndicator(close, 50).ema_indicator()
    ema200 = EMAIndicator(close, 200).ema_indicator()
    rsi = RSIIndicator(close, 14).rsi()
    macd = MACD(close)

    last = df.iloc[-1]

    # Trend
    bullish = ema50.iloc[-1] > ema200.iloc[-1]
    bearish = ema50.iloc[-1] < ema200.iloc[-1]

    rsi_val = rsi.iloc[-1]
    macd_hist = macd.macd_diff().iloc[-1]

    if mode == "AGGRESSIVE":
        if bullish and 45 <= rsi_val <= 65 and macd_hist > 0:
            return "BUY"
        if bearish and 35 <= rsi_val <= 55 and macd_hist < 0:
            return "SELL"

    if mode == "SAFE":
        if bullish and 48 <= rsi_val <= 60 and macd_hist > 0:
            return "BUY"
        if bearish and 40 <= rsi_val <= 52 and macd_hist < 0:
            return "SELL"

    return None

# ================= SIGNAL LOOP =================
async def scan_market(context: ContextTypes.DEFAULT_TYPE):
    global bot_active
    if not bot_active:
        return

    for pair, yf_symbol in PAIRS.items():
        for tf_name, tf in TIMEFRAMES.items():
            mode = "AGGRESSIVE" if tf_name == "M1" else "SAFE"

            key = f"{pair}_{tf_name}"
            now = datetime.utcnow()

            if key in last_signal_time:
                if (now - last_signal_time[key]).seconds < (60 if tf_name == "M1" else 300):
                    continue

            direction = analyze(pair, yf_symbol, tf, mode)
            if direction:
                expiry = "1–2 MIN" if tf_name == "M1" else "5 MIN"

                msg = f"""
📊 EXPERT OPTION SIGNAL

MODE: {"⚡ AGGRESSIVE" if mode=="AGGRESSIVE" else "🛡 SAFE"}
PAIR: {pair}
TIMEFRAME: {tf_name}
DIRECTION: {direction}
EXPIRY: {expiry}

⚠️ Enter after candle close
"""
                await context.bot.send_message(chat_id=CHAT_ID, text=msg)
                last_signal_time[key] = now

# ================= COMMANDS =================
async def pause(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global bot_active
    bot_active = False
    await update.message.reply_text("⏸ Signals paused")

async def resume(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global bot_active
    bot_active = True
    await update.message.reply_text("▶️ Signals resumed")

async def win(update: Update, context: ContextTypes.DEFAULT_TYPE):
    stats["win"] += 1
    await update.message.reply_text("✅ WIN recorded")

async def loss(update: Update, context: ContextTypes.DEFAULT_TYPE):
    stats["loss"] += 1
    await update.message.reply_text("❌ LOSS recorded")

async def summary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    total = stats["win"] + stats["loss"]
    rate = (stats["win"] / total * 100) if total > 0 else 0
    await update.message.reply_text(
        f"📊 DAILY SUMMARY\n\nWins: {stats['win']}\nLosses: {stats['loss']}\nWinrate: {rate:.2f}%"
    )

# ================= DAILY REPORT =================
async def daily_report(context: ContextTypes.DEFAULT_TYPE):
    total = stats["win"] + stats["loss"]
    rate = (stats["win"] / total * 100) if total > 0 else 0
    await context.bot.send_message(
        chat_id=CHAT_ID,
        text=f"📅 DAILY REPORT\n\nWins: {stats['win']}\nLosses: {stats['loss']}\nWinrate: {rate:.2f}%"
    )
    stats["win"] = 0
    stats["loss"] = 0

# ================= MAIN =================
def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("pause", pause))
    app.add_handler(CommandHandler("resume", resume))
    app.add_handler(CommandHandler("win", win))
    app.add_handler(CommandHandler("loss", loss))
    app.add_handler(CommandHandler("summary", summary))

    app.job_queue.run_repeating(scan_market, interval=60, first=10)
    app.job_queue.run_daily(daily_report, time=datetime.strptime("23:59", "%H:%M").time())

    app.run_polling()

if __name__ == "__main__":
    main()
