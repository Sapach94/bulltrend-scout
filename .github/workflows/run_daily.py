import os
import yfinance as yf
import ta
import requests
import numpy as np
from datetime import datetime, timezone

# Récupère les secrets
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Configuration des actifs
SYMBOL_CONFIG = {
    "GC=F": {"mt5": "XAUUSD", "dec": 2, "mult": 1, "tv": "TVC:GC1!"},
    "SI=F": {"mt5": "XAGUSD", "dec": 3, "mult": 10, "tv": "TVC:SI1!"},
    "BTC-USD": {"mt5": "BTCUSD", "dec": 2, "mult": 1, "tv": "BINANCE:BTCUSD"},
    "ETH-USD": {"mt5": "ETHUSD", "dec": 2, "mult": 1, "tv": "BINANCE:ETHUSD"},
    "AAPL": {"mt5": "AAPL", "dec": 2, "mult": 1, "tv": "NASDAQ:AAPL"},
    "NVDA": {"mt5": "NVDA", "dec": 2, "mult": 1, "tv": "NASDAQ:NVDA"},
    "TSLA": {"mt5": "TSLA", "dec": 2, "mult": 1, "tv": "NASDAQ:TSLA"},
    "EURUSD=X": {"mt5": "EURUSD", "dec": 5, "mult": 1, "tv": "FX:EURUSD"},
    "GBPUSD=X": {"mt5": "GBPUSD", "dec": 5, "mult": 1, "tv": "FX:GBPUSD"}
}

def send_telegram(text):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("❌ TOKEN ou CHAT_ID manquant")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML"})

def find_recent_support_resistance(df, window=10):
    recent_high = df['High'][-window:].max()
    recent_low = df['Low'][-window:].min()
    return recent_low, recent_high

def calculate_sl_tp(df, symbol_info, trend="bullish"):
    last_close = df['Close'].iloc[-1]
    atr = ta.volatility.average_true_range(df['High'], df['Low'], df['Close'], window=14).iloc[-1]
    atr_adj = atr * symbol_info["mult"]
    
    support, resistance = find_recent_support_resistance(df, window=10)
    dec = symbol_info["dec"]

    if trend == "bullish":
        sl = min(support, last_close - 1.5 * atr_adj)
        tp1 = resistance
        tp2 = last_close + 2 * (last_close - sl)
        tp = max(tp1, tp2)
    else:
        sl = max(resistance, last_close + 1.5 * atr_adj)
        tp1 = support
        tp2 = last_close - 2 * (sl - last_close)
        tp = min(tp1, tp2)

    sl = round(sl, dec)
    tp = round(tp, dec)
    entry = round(last_close, dec)

    if trend == "bullish" and (sl >= entry or tp <= entry):
        return None, None, None, None
    if trend == "bearish" and (sl <= entry or tp >= entry):
        return None, None, None, None

    rr = abs(tp - entry) / abs(entry - sl) if entry != sl else 0
    return entry, sl, tp, round(rr, 1)

def analyze(symbol):
    try:
        df = yf.download(symbol, period="6mo", interval="1d", progress=False)
        if len(df) < 50:
            return []

        df['MA20'] = ta.trend.sma_indicator(df['Close'], 20)
        df['MA50'] = ta.trend.sma_indicator(df['Close'], 50)
        df['MA200'] = ta.trend.sma_indicator(df['Close'], 200)
        df['RSI'] = ta.momentum.rsi(df['Close'], 14)
        df['ADX'] = ta.trend.adx(df['High'], df['Low'], df['Close'], 14)
        df['DI+'] = ta.trend.adx_pos(df['High'], df['Low'], df['Close'], 14)
        df['DI-'] = ta.trend.adx_neg(df['High'], df['Low'], df['Close'], 14)
        df['VolAvg20'] = df['Volume'].rolling(20).mean()

        last = df.iloc[-1]
        config = SYMBOL_CONFIG[symbol]
        trades = []

        # Tendance haussière
        bull_score = sum([
            last['Close'] > last['MA50'] > last['MA200'],
            last['MA20'] > last['MA50'],
            50 < last['RSI'] < 70,
            last['ADX'] > 20,
            last['DI+'] > last['DI-'],
            last['Volume'] > (1.2 * last['VolAvg20'])
        ])
        if bull_score >= 5:
            entry, sl, tp, rr = calculate_sl_tp(df, config, "bullish")
            if entry and rr >= 1.5:
                trades.append({
                    "type": "📈 ACHAT",
                    "symbol": symbol,
                    "mt5": config["mt5"],
                    "entry": entry,
                    "sl": sl,
                    "tp": tp,
                    "rr": rr,
                    "score": bull_score,
                    "dec": config["dec"],
                    "tv_link": f"https://www.tradingview.com/chart/?symbol={config['tv']}"
                })

        # Tendance baissière
        bear_score = sum([
            last['Close'] < last['MA50'] < last['MA200'],
            last['MA20'] < last['MA50'],
            30 < last['RSI'] < 50,
            last['ADX'] > 20,
            last['DI-'] > last['DI+'],
            last['Volume'] > (1.2 * last['VolAvg20'])
        ])
        if bear_score >= 5:
            entry, sl, tp, rr = calculate_sl_tp(df, config, "bearish")
            if entry and rr >= 1.5:
                trades.append({
                    "type": "📉 VENTE",
                    "symbol": symbol,
                    "mt5": config["mt5"],
                    "entry": entry,
                    "sl": sl,
                    "tp": tp,
                    "rr": rr,
                    "score": bear_score,
                    "dec": config["dec"],
                    "tv_link": f"https://www.tradingview.com/chart/?symbol={config['tv']}"
                })

        return trades
    except Exception as e:
        print(f"Erreur {symbol}: {e}")
        return []

def main():
    all_trades = []
    for symbol in SYMBOL_CONFIG:
        trades = analyze(symbol)
        all_trades.extend(trades)

    now = datetime.now(timezone.utc).strftime("%d/%m %Hh GMT")
    
    if all_trades:
        msg = f"🤖 <b>AlphaTrend AI – {now}</b>\n\n"
        for t in sorted(all_trades, key=lambda x: -x["rr"]):
            msg += (
                f"{t['type']} <b>{t['mt5']}</b>\n"
                f"Entrée : <code>{t['entry']}</code>\n"
                f"SL : <code>{t['sl']}</code> | TP : <code>{t['tp']}</code>\n"
                f"RR : 1:{t['rr']} • Score: {t['score']}/6\n"
                f"<a href='{t['tv_link']}'>📊 Voir sur TradingView</a>\n\n"
            )
        msg += "✅ Copie les niveaux → colle dans MT5.\n"
        msg += "⚠️ Ce n'est pas un conseil financier. Gère ton risque."
    else:
        msg = f"🤖 <b>AlphaTrend AI – {now}</b>\n\nAucune opportunité avec RR ≥ 1.5 aujourd'hui."

    send_telegram(msg)
    print("✅ Rapport envoyé.")

if __name__ == "__main__":
    main()
