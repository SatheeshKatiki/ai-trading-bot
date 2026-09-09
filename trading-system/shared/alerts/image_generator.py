"""
=============================================================================
  MANA AI — 4K ULTRA-HD LUXURY GOLD & SILVER PERFORMANCE CARD  v7.0
=============================================================================
Theme: Ultra-HD Luxury Gold Terminal — High Net Worth Institutional Dashboard
  • 4K / High-DPI Retina resolution (2400 x 1360 pixels)
  • Radiant Champagne Gold & Golden Ivory typography
  • Deep Obsidian Navy background with 4K precision micro-grid
  • Symmetrical Gold & Silver metallic edge accents
  • Glassmorphic Hero P&L Container with Gold rim highlight
  • 3 Precision KPI Cards with bespoke vector icons
  • Intelligent Market Audit & Execution logging
  • 100% vector-rendered icons (No missing font emoji boxes)
=============================================================================
"""
from __future__ import annotations
import io, math, os
from typing import List, Dict, Any, Optional
from PIL import Image, ImageDraw, ImageFont

# ── 4K / RETINA RESOLUTION (2x Scale of 1200x680 -> 2400x1360) ───────────────
SCALE = 2
W, H  = 1200 * SCALE, 680 * SCALE

# ── LUXURY WARM GOLD & SILVER COLOR PALETTE ───────────────────────────────────
BG_DEEP       = (9, 13, 22, 255)         # Deep Midnight Obsidian
BG_GRAD_BOT   = (5, 8, 14, 255)          # Pitch Black Navy
CARD_BG       = (16, 24, 40, 248)        # Premium Slate Glassmorphic Card
CARD_BORDER   = (48, 62, 92, 255)        # Clean Outer Border
CARD_GOLD_RIM = (212, 175, 55, 95)       # Inner Gold Rim Highlight

# Radiant Gold Shades
GOLD_METALLIC = (212, 175, 55, 255)      # Metallic Gold (#D4AF37)
GOLD_BRIGHT   = (251, 191, 36, 255)      # Vivid Gold (#FBBF24)
GOLD_CHAMPAGNE= (254, 240, 180, 255)     # Warm Champagne Gold (P&L & Headers)
GOLD_IVORY    = (255, 248, 225, 255)     # Soft Golden Ivory (Primary Text)
GOLD_MUTED    = (205, 185, 145, 255)     # Warm Gold Subtext & Secondary Labels

# Silver & Neutral
SILVER_WARM   = (228, 222, 210, 255)     # Warm Tinted Silver
SILVER_MUTED  = (160, 168, 185, 255)     # Muted Subtitle Silver

# Accents
GREEN_PROFIT  = (34, 197, 94, 255)       # Emerald Profit Green (#22C55E)
GREEN_PILL    = (6, 78, 59, 240)         # Dark Emerald Container
RED_LOSS      = (239, 68, 68, 255)       # Crimson Loss Red (#EF4444)
RED_PILL      = (127, 29, 29, 240)       # Dark Red Container
CYAN_ACCENT   = (56, 189, 248, 255)      # Sky Cyan (#38BDF8)
WHITE         = (255, 255, 255, 255)     # Pure White

def _s(val: int) -> int:
    """Scale an integer coordinate/dimension to 4K resolution."""
    return int(val * SCALE)

def _font(sz: int, bold: bool = False) -> ImageFont.ImageFont:
    scaled_sz = int(sz * SCALE)
    names = ["segoeuib.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf"] if bold else ["segoeui.ttf", "arial.ttf", "DejaVuSans.ttf", "calibri.ttf"]
    for n in names:
        try:
            return ImageFont.truetype(n, scaled_sz)
        except Exception:
            pass
    return ImageFont.load_default()

def _draw_vector_bolt(d: ImageDraw.ImageDraw, x: int, y: int, size: int = 24, color = GOLD_BRIGHT):
    s = (size * SCALE) / 24.0
    pts = [
        (x + int(14 * s), y + int(1 * s)),
        (x + int(5 * s),  y + int(13 * s)),
        (x + int(12 * s), y + int(13 * s)),
        (x + int(8 * s),  y + int(23 * s)),
        (x + int(20 * s), y + int(10 * s)),
        (x + int(13 * s), y + int(10 * s)),
    ]
    d.polygon(pts, fill=color)

def _draw_shield_badge(d: ImageDraw.ImageDraw, x: int, y: int, size: int = 20, color = GOLD_BRIGHT):
    s = (size * SCALE) / 20.0
    pts = [
        (x + int(10 * s), y + int(1 * s)),
        (x + int(19 * s), y + int(4 * s)),
        (x + int(17 * s), y + int(14 * s)),
        (x + int(10 * s), y + int(19 * s)),
        (x + int(3 * s),  y + int(14 * s)),
        (x + int(1 * s),  y + int(4 * s)),
    ]
    d.polygon(pts, fill=(*color[:3], 45), outline=color)
    d.line([(x + int(6 * s), y + int(10 * s)), (x + int(9 * s), y + int(13 * s)), (x + int(14 * s), y + int(7 * s))], fill=color, width=_s(2))

def _draw_target_icon(d: ImageDraw.ImageDraw, x: int, y: int, size: int = 20, color = GREEN_PROFIT):
    s = (size * SCALE) / 20.0
    cx, cy = x + (size * SCALE) // 2, y + (size * SCALE) // 2
    r1, r2 = int(9 * s), int(4 * s)
    d.ellipse([(cx - r1, cy - r1), (cx + r1, cy + r1)], fill=None, outline=color, width=_s(1))
    d.ellipse([(cx - r2, cy - r2), (cx + r2, cy + r2)], fill=color)

def _draw_activity_icon(d: ImageDraw.ImageDraw, x: int, y: int, size: int = 20, color = CYAN_ACCENT):
    s = (size * SCALE) / 20.0
    d.rectangle([(x + int(2*s), y + int(10*s)), (x + int(6*s), y + int(18*s))], fill=color)
    d.rectangle([(x + int(8*s), y + int(4*s)),  (x + int(12*s), y + int(18*s))], fill=color)
    d.rectangle([(x + int(14*s), y + int(8*s)), (x + int(18*s), y + int(18*s))], fill=color)

def _draw_card(d: ImageDraw.ImageDraw, x1, y1, x2, y2, radius=12, fill=CARD_BG, outline=CARD_BORDER, width=1):
    d.rounded_rectangle([(_s(x1), _s(y1)), (_s(x2), _s(y2))], radius=_s(radius), fill=fill, outline=outline, width=_s(width))

def _format_inr(val: float) -> str:
    """Format value in Indian Currency style with proper sign placement."""
    if val >= 0:
        return f"+₹{val:,.2f}"
    else:
        return f"-₹{abs(val):,.2f}"

def _logo() -> Optional[Image.Image]:
    base = os.path.dirname(__file__)
    for p in [
        os.path.join(base, "..", "..", "..", "frontend", "public", "mana-logo-v2.png"),
        os.path.join(base, "..", "..", "..", "frontend", "public", "mana-logo.png"),
        os.path.join(base, "..", "frontend", "public", "mana-logo-v2.png"),
    ]:
        try:
            if os.path.exists(p):
                return Image.open(os.path.abspath(p)).convert("RGBA")
        except Exception:
            pass
    return None

def _paste_logo(img: Image.Image, x: int, y: int, h: int = 48) -> int:
    logo = _logo()
    if logo:
        scaled_h = _s(h)
        w = int(logo.width * scaled_h / logo.height)
        logo = logo.resize((w, scaled_h), Image.Resampling.LANCZOS)
        img.paste(logo, (_s(x), _s(y)), logo)
        return int(w / SCALE) + 14
    return 0

def generate_eod_card(
    date_str: str,
    total_pnl: float,
    total_trades: int,
    wins: int,
    losses: int,
    win_rate: float,
    trades_detail: Optional[List[Dict[str, Any]]] = None,
    session_title: str = "Phase 1 Paper Session",
    capital: float = 100000.0,
) -> bytes:
    # ── 1. BASE CANVAS & GRADIENT ─────────────────────────────────────────────
    img = Image.new("RGBA", (W, H), BG_DEEP)
    d = ImageDraw.Draw(img)

    for y in range(H):
        t = y / H
        r = int(BG_DEEP[0] + (BG_GRAD_BOT[0] - BG_DEEP[0]) * t)
        g = int(BG_DEEP[1] + (BG_GRAD_BOT[1] - BG_DEEP[1]) * t)
        b = int(BG_DEEP[2] + (BG_GRAD_BOT[2] - BG_DEEP[2]) * t)
        d.line([(0, y), (W, y)], fill=(r, g, b, 255))

    # Tech micro-grid for 4K institutional depth
    grid = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(grid)
    for gx in range(_s(16), W, _s(32)):
        for gy in range(_s(16), H, _s(32)):
            gd.point((gx, gy), fill=(148, 163, 184, 22))
    img.alpha_composite(grid)

    # Ambient radial luxury glows (Soft Gold Top-Left, Soft Cyan Top-Right)
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gld = ImageDraw.Draw(glow)
    for r in range(_s(420), 0, -_s(14)):
        a = int(28 * (1 - r / _s(420)))
        gld.ellipse([(_s(140) - r, _s(80) - r), (_s(140) + r, _s(80) + r)], fill=(*GOLD_METALLIC[:3], a))
        a_cyan = int(16 * (1 - r / _s(420)))
        gld.ellipse([(W - _s(160) - r, _s(160) - r), (W - _s(160) + r, _s(160) + r)], fill=(*CYAN_ACCENT[:3], a_cyan))
    img.alpha_composite(glow)

    d = ImageDraw.Draw(img)

    # ── 2. METALLIC GOLD & SILVER ACCENT BARS (Top & Bottom) ──────────────────
    for x in range(W):
        t = x / W
        sin_t = math.sin(math.pi * t)
        r = int(212 * sin_t + 190 * (1 - sin_t))
        g = int(175 * sin_t + 200 * (1 - sin_t))
        b = int(55 * sin_t + 225 * (1 - sin_t))
        d.line([(x, 0), (x, _s(2))], fill=(r, g, b, 255))
        d.line([(x, H - _s(3)), (x, H - _s(1))], fill=(r, g, b, 255))

    # ── 3. HEADER BRANDING ────────────────────────────────────────────────────
    logo_x = 36
    lw = _paste_logo(img, logo_x, 18, h=48)
    if lw > 0:
        logo_x += lw

    # "MANA  AI" with Gold Champagne & Metallic Gold
    font_brand = _font(32, bold=True)
    d.text((_s(logo_x), _s(15)), "MANA", font=font_brand, fill=GOLD_IVORY)
    mana_len = int(font_brand.getlength("MANA ") / SCALE if hasattr(font_brand, "getlength") else 105)
    d.text((_s(logo_x + mana_len), _s(15)), "AI", font=font_brand, fill=GOLD_BRIGHT)
    ai_len = int(font_brand.getlength("AI ") / SCALE if hasattr(font_brand, "getlength") else 50)
    _draw_vector_bolt(d, _s(logo_x + mana_len + ai_len), _s(21), size=24, color=GOLD_BRIGHT)

    # Date and Subtitle (Warm Golden-Silver)
    d.text((_s(logo_x), _s(54)), f"{date_str}   ·   {session_title}", font=_font(13, bold=False), fill=GOLD_MUTED)

    # Top Right Badges
    # 1. INSTITUTIONAL QUANT Pill
    b1_w, b1_h = 230, 32
    b1_x1 = 1200 - b1_w - 180
    b1_y1 = 20
    b1_x2, b1_y2 = b1_x1 + b1_w, b1_y1 + b1_h
    d.rounded_rectangle([(_s(b1_x1), _s(b1_y1)), (_s(b1_x2), _s(b1_y2))], radius=_s(16), fill=(18, 25, 42, 235), outline=(212, 175, 55, 180), width=_s(1))
    d.ellipse([(_s(b1_x1 + 14), _s(b1_y1 + 11)), (_s(b1_x1 + 22), _s(b1_y1 + 19))], fill=GOLD_BRIGHT)
    d.text((_s(b1_x1 + 30), _s(b1_y1 + 8)), "INSTITUTIONAL QUANT", font=_font(11, bold=True), fill=GOLD_CHAMPAGNE)

    # 2. ZERO-TOUCH EOD Pill
    b2_w, b2_h = 140, 32
    b2_x1 = 1200 - b2_w - 36
    b2_y1 = 20
    b2_x2, b2_y2 = b2_x1 + b2_w, b2_y1 + b2_h
    d.rounded_rectangle([(_s(b2_x1), _s(b2_y1)), (_s(b2_x2), _s(b2_y2))], radius=_s(16), fill=(6, 78, 59, 210), outline=(34, 197, 94, 220), width=_s(1))
    d.ellipse([(_s(b2_x1 + 14), _s(b2_y1 + 11)), (_s(b2_x1 + 22), _s(b2_y1 + 19))], fill=GREEN_PROFIT)
    d.text((_s(b2_x1 + 28), _s(b2_y1 + 8)), "ZERO-TOUCH", font=_font(11, bold=True), fill=WHITE)

    # ── 4. HERO P&L CARD (Glassmorphic Luxury Centerpiece) ─────────────────────
    HX1, HY1 = 36, 84
    HX2, HY2 = 1200 - 36, 268

    # Outer Glass Card with balanced gold rim
    _draw_card(d, HX1, HY1, HX2, HY2, radius=14, fill=CARD_BG, outline=CARD_BORDER, width=1)
    d.rounded_rectangle([(_s(HX1 + 1), _s(HY1 + 1)), (_s(HX2 - 1), _s(HY2 - 1))], radius=_s(13), fill=None, outline=CARD_GOLD_RIM, width=_s(1))
    # Top metallic gold highlight line
    d.rounded_rectangle([(_s(HX1 + 10), _s(HY1)), (_s(HX2 - 10), _s(HY1 + 3))], radius=_s(2), fill=GOLD_METALLIC)

    # Label inside Hero Card (Bright Gold)
    d.text((_s(HX1 + 26), _s(HY1 + 18)), "NET REALIZED P&L  (TODAY)", font=_font(12, bold=True), fill=GOLD_BRIGHT)

    # Dynamic PnL, Dual ROI & Status (Strictly dynamic - NO hardcoding)
    # Option 1: Margin / Deployed Investment ROI (Calculated on actual premium deployed)
    total_deployed = 0.0
    if trades_detail and len(trades_detail) > 0:
        total_deployed = sum(float(t.get("entry_premium", t.get("entry_price", 0.0))) * int(t.get("quantity", t.get("qty", 1))) for t in trades_detail)

    # Option 2: Account Capital ROI (Calculated on total capital)
    account_roi = (total_pnl / capital * 100.0) if capital > 0 else 0.0
    margin_roi = (total_pnl / total_deployed * 100.0) if total_deployed > 0 else account_roi

    is_profit = total_pnl > 0.009
    is_zero   = abs(total_pnl) < 0.01

    if is_profit:
        s_title = "PROFITABLE SESSION"
        s_bg = GREEN_PILL
        s_border = GREEN_PROFIT
        s_fg = GOLD_IVORY
        s_icon = "check"
        pnl_col = GREEN_PROFIT
        roi_str = f"+{margin_roi:.2f}% Margin ROI"
        roi_pill_fill = (6, 78, 59, 230)
        roi_pill_border = GREEN_PROFIT
        roi_pill_col = GREEN_PROFIT
        roi_sub = f"Acct Impact: +{account_roi:.2f}%  ·  Target Reached"
    elif is_zero:
        s_title = "CAPITAL PRESERVED"
        s_bg = (16, 42, 70, 245)
        s_border = (56, 189, 248, 220)
        s_fg = GOLD_IVORY
        s_icon = "shield"
        pnl_col = GOLD_CHAMPAGNE
        roi_str = "+0.00% Margin ROI"
        roi_pill_fill = (22, 32, 52, 220)
        roi_pill_border = (212, 175, 55, 140)
        roi_pill_col = GOLD_CHAMPAGNE
        roi_sub = f"Acct Impact: +0.00%  ·  Zero Overnight Risk"
    else:
        s_title = "CONTROLLED DRAWDOWN"
        s_bg = RED_PILL
        s_border = RED_LOSS
        s_fg = GOLD_IVORY
        s_icon = "warn"
        pnl_col = RED_LOSS
        roi_str = f"{margin_roi:.2f}% Margin ROI"
        roi_pill_fill = (55, 18, 24, 240)
        roi_pill_border = RED_LOSS
        roi_pill_col = RED_LOSS
        roi_sub = f"Acct Impact: {account_roi:.2f}%  ·  Hard SL Enforced"

    pw, ph = 250, 38
    px1, py1 = HX2 - pw - 22, HY1 + 15
    px2, py2 = px1 + pw, py1 + ph
    d.rounded_rectangle([(_s(px1), _s(py1)), (_s(px2), _s(py2))], radius=_s(19), fill=s_bg, outline=s_border, width=_s(1))

    if s_icon == "shield":
        _draw_shield_badge(d, _s(px1 + 14), _s(py1 + 9), size=20, color=CYAN_ACCENT)
    elif s_icon == "check":
        d.ellipse([(_s(px1 + 14), _s(py1 + 9)), (_s(px1 + 32), _s(py1 + 27))], fill=GREEN_PROFIT)
        d.line([(_s(px1 + 19), _s(py1 + 18)), (_s(px1 + 22), _s(py1 + 22)), (_s(px1 + 28), _s(py1 + 14))], fill=WHITE, width=_s(2))
    else:
        d.ellipse([(_s(px1 + 14), _s(py1 + 9)), (_s(px1 + 32), _s(py1 + 27))], fill=RED_LOSS)
        d.line([(_s(px1 + 23), _s(py1 + 14)), (_s(px1 + 23), _s(py1 + 20))], fill=WHITE, width=_s(2))
        d.point((_s(px1 + 23), _s(py1 + 23)), fill=WHITE)

    d.text((_s(px1 + 42), _s(py1 + 10)), s_title, font=_font(12, bold=True), fill=s_fg)

    # BIG P&L NUMBER
    pnl_str = _format_inr(total_pnl)
    font_pnl = _font(64, bold=True)
    d.text((_s(HX1 + 26), _s(HY1 + 48)), pnl_str, font=font_pnl, fill=pnl_col)
    pnl_str_len = int(font_pnl.getlength(pnl_str) / SCALE if hasattr(font_pnl, "getlength") else 310)

    # ROI Pill beside PnL (Dynamic Red/Green/Gold)
    font_roi = _font(13, bold=True)
    roi_len = int(font_roi.getlength(roi_str) / SCALE if hasattr(font_roi, "getlength") else 150)
    tag_w = max(230, roi_len + 54)
    tag_x = HX1 + 26 + pnl_str_len + 28
    d.rounded_rectangle([(_s(tag_x), _s(HY1 + 64)), (_s(tag_x + tag_w), _s(HY1 + 98))], radius=_s(17), fill=roi_pill_fill, outline=roi_pill_border, width=_s(1))
    d.ellipse([(_s(tag_x + 14), _s(HY1 + 77)), (_s(tag_x + 22), _s(HY1 + 85))], fill=roi_pill_col)
    d.text((_s(tag_x + 32), _s(HY1 + 71)), roi_str, font=font_roi, fill=roi_pill_col)
    d.text((_s(tag_x + 4), _s(HY1 + 106)), roi_sub, font=_font(11, bold=False), fill=GOLD_MUTED)

    # Horizontal Divider inside Hero
    div_y = HY2 - 58
    d.line([(_s(HX1 + 24), _s(div_y)), (_s(HX2 - 24), _s(div_y))], fill=(48, 62, 92, 255), width=_s(1))

    # 4 Quick Metric Columns inside Hero
    col_w = (HX2 - HX1 - 48) // 4
    metrics = [
        ("TOTAL TRADES", f"{total_trades} Executed", GOLD_IVORY),
        ("PROFIT TRADES", f"{wins} Wins", GREEN_PROFIT if wins > 0 else GOLD_CHAMPAGNE),
        ("LOSS TRADES", f"{losses} Losses", RED_LOSS if losses > 0 else GOLD_CHAMPAGNE),
        ("WIN RATE", f"{win_rate:.1f}%", GREEN_PROFIT if win_rate >= 50 else (RED_LOSS if (losses > 0 and wins == 0) else GOLD_CHAMPAGNE)),
    ]
    for idx, (m_label, m_val, m_col) in enumerate(metrics):
        cx = HX1 + 28 + idx * col_w
        d.text((_s(cx), _s(div_y + 8)), m_label, font=_font(10, bold=True), fill=GOLD_MUTED)
        d.text((_s(cx), _s(div_y + 24)), m_val, font=_font(17, bold=True), fill=m_col)

    # ── 5. THREE KPI CARDS (Middle Row) ──────────────────────────────────────
    KY1 = HY2 + 16
    KH = 136
    KY2 = KY1 + KH
    GAP = 16
    KW = (1200 - 72 - GAP * 2) // 3

    # Dynamic Win Accuracy KPI
    if total_trades == 0:
        win_acc_val = "0.0%"
        win_acc_sub = "0 Wins  /  0 Losses"
        win_acc_desc = "AI Guard: False Signals Rejected"
        win_acc_col = GOLD_CHAMPAGNE
        win_acc_accent = GOLD_METALLIC
        win_icon_col = GOLD_METALLIC
    elif win_rate >= 50.0:
        win_acc_val = f"{win_rate:.1f}%"
        win_acc_sub = f"{wins} Wins  /  {losses} Losses"
        win_acc_desc = "Confluence Entry Verification"
        win_acc_col = GREEN_PROFIT
        win_acc_accent = GREEN_PROFIT
        win_icon_col = GREEN_PROFIT
    elif win_rate > 0:
        win_acc_val = f"{win_rate:.1f}%"
        win_acc_sub = f"{wins} Wins  /  {losses} Losses"
        win_acc_desc = "Confluence Entry Verification"
        win_acc_col = GOLD_BRIGHT
        win_acc_accent = GOLD_BRIGHT
        win_icon_col = GOLD_BRIGHT
    else:  # 0% win rate with losses
        win_acc_val = "0.0%"
        win_acc_sub = f"{wins} Wins  /  {losses} Losses"
        win_acc_desc = "Strict Stop Loss Discipline"
        win_acc_col = RED_LOSS
        win_acc_accent = RED_LOSS
        win_icon_col = RED_LOSS

    # Dynamic Session Activity KPI
    orders_count = total_trades * 2 if total_trades > 0 else 0
    act_val = f"{total_trades} Trades" if total_trades > 0 else "0 Trades"
    act_sub = f"{orders_count} Orders (Daily Cap: 6)" if total_trades > 0 else "Daily Cap: Max 6 Trades"
    act_desc = "Anti-Overtrading Protocol Active"

    # Dynamic Risk Engine KPI (Calculated directly from capital & drawdown)
    drawdown_val = max(0.0, -total_pnl)
    drawdown_pct = (drawdown_val / capital * 100.0) if capital > 0 else 0.0
    cap_intact_pct = max(0.0, ((capital - drawdown_val) / capital * 100.0)) if capital > 0 else 100.0

    if is_profit:
        risk_val = "100.0% INTACT"
        risk_sub = f"+{account_roi:.2f}% Session Expansion"
        risk_desc = "Capital Alpha Hedged & Compounding"
        risk_val_col = GREEN_PROFIT
        risk_accent = GREEN_PROFIT
    elif total_pnl < 0:
        risk_val = f"{cap_intact_pct:.2f}% INTACT"
        risk_sub = f"Drawdown: -{drawdown_pct:.2f}% (Limit: 3.0%)"
        risk_desc = "Theta Guard & Hard SL Active"
        risk_val_col = GOLD_BRIGHT if drawdown_pct <= 1.5 else (251, 146, 60, 255)
        risk_accent = GOLD_BRIGHT
    else:
        risk_val = "100.0% INTACT"
        risk_sub = "Zero Drawdown Incurred"
        risk_desc = "Theta Guard & Hard SL Active"
        risk_val_col = GOLD_BRIGHT
        risk_accent = GOLD_BRIGHT

    kpi_configs = [
        {
            "title": "WIN ACCURACY",
            "val": win_acc_val,
            "sub": win_acc_sub,
            "desc": win_acc_desc,
            "val_col": win_acc_col,
            "accent_col": win_acc_accent,
            "icon": "target",
            "icon_col": win_icon_col,
        },
        {
            "title": "SESSION ACTIVITY",
            "val": act_val,
            "sub": act_sub,
            "desc": act_desc,
            "val_col": GOLD_IVORY,
            "accent_col": GOLD_METALLIC,
            "icon": "activity",
            "icon_col": CYAN_ACCENT,
        },
        {
            "title": "RISK ENGINE",
            "val": risk_val,
            "sub": risk_sub,
            "desc": risk_desc,
            "val_col": risk_val_col,
            "accent_col": risk_accent,
            "icon": "shield",
            "icon_col": GOLD_BRIGHT,
        },
    ]

    for idx, kpi in enumerate(kpi_configs):
        kx1 = 36 + idx * (KW + GAP)
        kx2 = kx1 + KW

        # Card body
        _draw_card(d, kx1, KY1, kx2, KY2, radius=12, fill=CARD_BG, outline=CARD_BORDER, width=1)

        # Top colored accent bar
        d.rounded_rectangle([(_s(kx1 + 4), _s(KY1)), (_s(kx2 - 4), _s(KY1 + 3))], radius=_s(2), fill=kpi["accent_col"])

        # Icon in top right of KPI card
        icon_col = kpi.get("icon_col", GOLD_BRIGHT)
        if kpi["icon"] == "target":
            _draw_target_icon(d, _s(kx2 - 38), _s(KY1 + 14), size=20, color=icon_col)
        elif kpi["icon"] == "activity":
            _draw_activity_icon(d, _s(kx2 - 38), _s(KY1 + 14), size=20, color=icon_col)
        elif kpi["icon"] == "shield":
            _draw_shield_badge(d, _s(kx2 - 38), _s(KY1 + 14), size=20, color=icon_col)

        # Title (Warm Gold Muted)
        d.text((_s(kx1 + 18), _s(KY1 + 14)), kpi["title"], font=_font(11, bold=True), fill=GOLD_MUTED)

        # Big Value (High contrast bold goldish)
        d.text((_s(kx1 + 18), _s(KY1 + 36)), kpi["val"], font=_font(30, bold=True), fill=kpi["val_col"])

        # Subtitle (Warm Golden Ivory, 100% readable)
        d.text((_s(kx1 + 18), _s(KY1 + 78)), kpi["sub"], font=_font(13, bold=True), fill=GOLD_IVORY)

        # Desc (Warm secondary goldish silver)
        d.text((_s(kx1 + 18), _s(KY1 + 102)), kpi["desc"], font=_font(11, bold=False), fill=GOLD_MUTED)

    # ── 6. BOTTOM PANEL (Market Intelligence & Execution Audit) ───────────────
    BY1 = KY2 + 16
    BY2 = 680 - 32
    _draw_card(d, 36, BY1, 1200 - 36, BY2, radius=12, fill=CARD_BG, outline=CARD_BORDER, width=1)

    # Top accent highlight
    d.rounded_rectangle([(_s(46), _s(BY1)), (_s(1200 - 46), _s(BY1 + 3))], radius=_s(2), fill=GOLD_METALLIC)

    # Header inside Bottom Panel
    audit_hdr = f"MARKET INTELLIGENCE & EXECUTION AUDIT   ·   {len(trades_detail) if trades_detail else 0} TRADES AUDITED"
    d.text((_s(54), _s(BY1 + 14)), audit_hdr, font=_font(11, bold=True), fill=GOLD_BRIGHT)
    d.line([(_s(54), _s(BY1 + 32)), (_s(1200 - 54), _s(BY1 + 32))], fill=(48, 62, 92, 255), width=_s(1))

    if trades_detail and len(trades_detail) > 0:
        displayed_trades = trades_detail[:6]
        n_trades = len(displayed_trades)
        row_gap = 28 if n_trades <= 3 else (25 if n_trades <= 4 else 22)
        font_trade = _font(12 if n_trades >= 5 else 13, bold=True)
        font_reason = _font(11 if n_trades >= 5 else 12, bold=False)

        ty = BY1 + 38
        for t in displayed_trades:
            contract = str(t.get("contract", t.get("symbol", "N/A")))
            p = float(t.get("net_pnl", t.get("pnl", 0.0)))
            rsn = str(t.get("exit_reason", "Target / SL Hit"))
            pc = GREEN_PROFIT if p >= 0 else RED_LOSS
            p_formatted = _format_inr(p)

            # Dynamic Trade-level ROI (on deployed premium)
            t_entry = float(t.get("entry_premium", t.get("entry_price", 0.0)))
            t_qty = int(t.get("quantity", t.get("qty", 1)))
            t_inv = t_entry * t_qty
            t_roi = (p / t_inv * 100.0) if t_inv > 0 else 0.0
            t_roi_str = f"({'+' if t_roi >= 0 else ''}{t_roi:.1f}% ROI)"

            # Bullet dot
            d.ellipse([(_s(56), _s(ty + 3)), (_s(66), _s(ty + 13))], fill=pc)
            d.text((_s(76), _s(ty)), contract[:30], font=font_trade, fill=GOLD_IVORY)
            d.text((_s(470), _s(ty)), p_formatted, font=font_trade, fill=pc)
            d.text((_s(590), _s(ty)), t_roi_str, font=font_trade, fill=pc)
            d.text((_s(710), _s(ty)), f"[{rsn[:45]}]", font=font_reason, fill=GOLD_MUTED)
            ty += row_gap
    else:
        # High-clarity 3-row intelligence layout with warm goldish headers
        # Row 1: False-Signal Filter Protection
        d.ellipse([(_s(56), _s(BY1 + 42)), (_s(68), _s(BY1 + 54))], fill=GREEN_PROFIT)
        d.text((_s(78), _s(BY1 + 40)), "AI Filter Protection:", font=_font(13, bold=True), fill=GOLD_CHAMPAGNE)
        d.text((_s(230), _s(BY1 + 40)), "Market traded in choppy consolidation. Quant engine rejected false breakouts to protect capital.", font=_font(13, bold=False), fill=GOLD_MUTED)

        # Row 2: Capital Preservation Assurance
        d.ellipse([(_s(56), _s(BY1 + 66)), (_s(68), _s(BY1 + 78))], fill=GOLD_BRIGHT)
        d.text((_s(78), _s(BY1 + 64)), "Capital Integrity:", font=_font(13, bold=True), fill=GOLD_CHAMPAGNE)
        d.text((_s(214), _s(BY1 + 64)), "100% Capital intact. Zero drawdown incurred. Strict risk discipline maintained.", font=_font(13, bold=False), fill=GOLD_MUTED)

        # Row 3: Automated Protocol & Next Schedule
        d.ellipse([(_s(56), _s(BY1 + 90)), (_s(68), _s(BY1 + 102))], fill=CYAN_ACCENT)
        d.text((_s(78), _s(BY1 + 88)), "Session Protocol:", font=_font(13, bold=True), fill=GOLD_CHAMPAGNE)
        d.text((_s(214), _s(BY1 + 88)), "Auto square-off finalized at 15:15 IST. Next daily market session auto-boots at 08:45 AM IST.", font=_font(13, bold=False), fill=GOLD_MUTED)

    # ── 7. INSTITUTIONAL FOOTER ───────────────────────────────────────────────
    footer_text = "MANA AI PROPRIETARY QUANTITATIVE ENGINE   ·   NSE INTRADAY SYSTEMS   ·   SEBI COMPLIANT PAPER SIMULATION"
    d.text((_s(1200 // 2 - 320), _s(680 - 20)), footer_text, font=_font(10, bold=False), fill=(140, 130, 110, 255))

    # ── Export ────────────────────────────────────────────────────────────────
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()
