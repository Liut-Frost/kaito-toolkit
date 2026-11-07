"""
telegram_alert.py
Sends the alert (chart snapshot + reasoning trail + trade plan) to Telegram.
"""

import requests
from fractal_engine import SignalResult


def send_telegram_photo(bot_token: str, chat_id: str, photo_path: str, caption: str) -> dict:
    url = f"https://api.telegram.org/bot{bot_token}/sendPhoto"
    with open(photo_path, "rb") as photo:
        resp = requests.post(
            url,
            data={"chat_id": chat_id, "caption": caption[:1024], "parse_mode": "HTML"},
            files={"photo": photo},
            timeout=30,
        )
    return resp.json()


def send_telegram_message(bot_token: str, chat_id: str, text: str) -> dict:
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    resp = requests.post(
        url,
        data={"chat_id": chat_id, "text": text[:4096], "parse_mode": "HTML"},
        timeout=30,
    )
    return resp.json()


def format_alert_caption(symbol: str, signal: SignalResult) -> str:
    lines = [f"<b>{symbol} -- {'SIGNAL CONFIRMED' if signal.valid else 'Setup Update'}</b>", ""]

    if signal.trade_plan:
        tp = signal.trade_plan
        lines.append(f"Direction: <b>{tp.direction.upper()}</b>")
        lines.append(f"Entry: {tp.entry:.5f}")
        lines.append(f"Stop Loss: {tp.stop_loss:.5f}")
        lines.append(f"Take Profit: {tp.take_profit:.5f}" if tp.take_profit else "Take Profit: N/A")
        lines.append(f"Risk:Reward: 1:{tp.rr:.2f}")
        lines.append("")

    lines.append("<b>Reasoning trail:</b>")
    for step in signal.reasoning_trail:
        lines.append(f"- {step}")

    return "\n".join(lines)


def deliver_signal(bot_token: str, chat_id: str, symbol: str, signal: SignalResult, chart_path: str = None):
    caption = format_alert_caption(symbol, signal)

    if chart_path:
        result = send_telegram_photo(bot_token, chat_id, chart_path, caption)
        # Telegram photo captions are capped at 1024 chars -- if the trail
        # got cut off, follow up with the full text separately.
        if len(caption) > 1024:
            send_telegram_message(bot_token, chat_id, caption)
        return result
    else:
        return send_telegram_message(bot_token, chat_id, caption)
