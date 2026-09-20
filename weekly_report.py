"""Modern AI performance tables for weekly and season Telegram reports."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from config import MODEL_ORDER, MODEL_SHORT, REPORT_DIR, SEASON

BG = (11, 21, 38)
HEADER = (15, 28, 52)
CARD = (18, 32, 51)
CARD2 = (22, 40, 64)
BORDER = (36, 58, 88)
WHITE = (240, 244, 248)
CYAN = (45, 212, 191)
GOLD = (251, 191, 36)
MUTED = (139, 155, 176)
GREEN = (34, 197, 94)
BLUE = (59, 130, 246)
PURPLE = (168, 85, 247)


def _font(size: int, bold: bool = False):
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/lato/Lato-Bold.ttf" if bold else "/usr/share/fonts/truetype/lato/Lato-Regular.ttf",
    ]
    for path in candidates:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def _tw(draw, text, font) -> float:
    return draw.textlength(str(text), font=font)


def _text(draw, xy, text, size=18, bold=False, fill=WHITE):
    draw.text(xy, str(text), font=_font(size, bold), fill=fill)


def _wrap(draw, text: str, font, max_width: float) -> list[str]:
    words = str(text).split()
    lines: list[str] = []
    cur = ""
    for word in words:
        test = (cur + " " + word).strip()
        if cur and _tw(draw, test, font) > max_width:
            lines.append(cur)
            cur = word
        else:
            cur = test
    if cur:
        lines.append(cur)
    return lines or [""]


def _model_row(name: str, stats: dict[str, Any]) -> dict[str, Any]:
    dist = stats.get("point_distribution") or {}
    exact = int(stats.get("exact") or dist.get("6") or 0)
    outcome = int(stats.get("outcome") or 0)
    if not outcome:
        outcome = int(dist.get("6", 0)) + int(dist.get("5", 0)) + int(dist.get("3", 0)) + int(dist.get("2", 0))
    kazanan = int(dist.get("6", 0)) + int(dist.get("5", 0)) + int(dist.get("2", 0))
    if kazanan == 0 and outcome:
        kazanan = outcome
    return {
        "name": name,
        "short": MODEL_SHORT.get(name, name),
        "points": int(stats.get("points") or 0),
        "kazanan": kazanan,
        "skor": exact,
        "sonuc": outcome,
        "avg": float(stats.get("avg") or 0),
        "uret": int(stats.get("successful_predictions") or 0),
        "firs": int(stats.get("prediction_opportunities") or 0),
        "week_points": stats.get("week_points") or {},
    }


def _ranked(models_stats: dict[str, Any]) -> list[dict[str, Any]]:
    rows = [_model_row(m, models_stats[m]) for m in MODEL_ORDER if m in models_stats]
    rows.sort(key=lambda r: (-r["points"], -r["skor"], -r["uret"], r["short"]))
    return rows


def _leaders(rows: list[dict[str, Any]]) -> tuple[dict, dict, dict]:
    if not rows:
        empty = {"short": "—", "points": 0, "skor": 0, "uret": 0, "firs": 0}
        return empty, empty, empty
    by_points = max(rows, key=lambda r: (r["points"], r["skor"], r["uret"]))
    by_skor = max(rows, key=lambda r: (r["skor"], r["points"], r["uret"]))
    by_uret = max(rows, key=lambda r: (r["uret"], r["points"], r["skor"]))
    return by_points, by_skor, by_uret


def _comment_weekly(rows: list[dict[str, Any]], matchday: Any) -> str:
    if not rows:
        return "Bu matchday için değerlendirilebilir AI performansı yok."
    top, skor, uret = _leaders(rows)
    parts = [f"Matchday {matchday} sonunda {top['short']} {top['points']} puanla lider."]
    if skor["short"] != top["short"] and skor["skor"] > 0:
        parts.append(f"Tam skorda {skor['short']} önde ({skor['skor']}).")
    elif top["skor"] > 0:
        parts.append(f"Tam skor liderliği de {top['short']} tarafında ({top['skor']}).")
    zero = [r for r in rows if r["uret"] == 0]
    low = [r for r in rows if 0 < r["uret"] < r["firs"] * 0.7]
    if zero:
        parts.append(f"{', '.join(r['short'] for r in zero)} hiç yanıt üretemedi.")
    elif low:
        parts.append(
            f"{', '.join(r['short'] for r in low)} üretim eksiği nedeniyle toplam puanda geride kaldı."
        )
    if uret["short"] == top["short"]:
        parts.append("Lider aynı zamanda en fazla tahmin üreten model.")
    return " ".join(parts)


def _comment_season(rows: list[dict[str, Any]], weeks: list) -> str:
    if not rows:
        return "Sezon için FINAL matchday verisi yok."
    top, skor, uret = _leaders(rows)
    n = len(weeks)
    parts = [f"{n} matchday sonunda {top['short']} sezon lideri ({top['points']} puan)."]
    if skor["short"] != top["short"] and skor["skor"] > 0:
        parts.append(f"Tam skorda {skor['short']} önde ({skor['skor']}).")
    if uret["uret"] > 0:
        parts.append(f"En fazla tahmin üreten: {uret['short']} ({uret['uret']}/{uret['firs']}).")
    weak = [r for r in rows if r["points"] == 0 or r["uret"] == 0]
    if weak:
        parts.append(f"{', '.join(r['short'] for r in weak)} henüz etkili katkı veremedi.")
    return " ".join(parts)


def _draw_header(draw, w: int, title: str, subtitle: str, right_top: str, right_bottom: str) -> None:
    draw.rectangle((0, 0, w, 115), fill=HEADER)
    _text(draw, (32, 26), title, 26, True, WHITE)
    _text(draw, (32, 64), subtitle, 17, True, CYAN)
    rt = _font(14, True)
    rb = _font(13, True)
    _text(draw, (w - 32 - _tw(draw, right_top, rt), 36), right_top, 14, True, GOLD)
    _text(draw, (w - 32 - _tw(draw, right_bottom, rb), 66), right_bottom, 13, True, MUTED)


def _draw_leaders(draw, y: int, w: int, rows: list[dict[str, Any]]) -> int:
    by_points, by_skor, by_uret = _leaders(rows)
    leaders = [
        ("EN FAZLA PUAN", by_points["short"], f"{by_points['points']} P", GOLD),
        ("EN FAZLA SKOR BİLEN", by_skor["short"], f"{by_skor['skor']} tam skor", GREEN),
        ("EN FAZLA TAHMİN ÜRETEN", by_uret["short"], f"{by_uret['uret']}/{by_uret['firs']}", BLUE),
    ]
    gap = 14
    cw = (w - 64 - gap * 2) // 3
    for i, (title, name, val, color) in enumerate(leaders):
        x = 32 + i * (cw + gap)
        draw.rounded_rectangle((x, y, x + cw, y + 100), radius=14, fill=CARD2, outline=BORDER)
        _text(draw, (x + 16, y + 14), title, 12, True, MUTED)
        _text(draw, (x + 16, y + 42), name, 22, True, color)
        _text(draw, (x + 16, y + 74), val, 14, True, WHITE)
    return y + 116


def _draw_comment(draw, y: int, w: int, comment: str) -> int:
    font = _font(13, False)
    lines = _wrap(draw, comment, font, w - 70)
    box_h = 36 + 18 * min(len(lines), 4)
    draw.rounded_rectangle((20, y, w - 20, y + box_h), radius=12, fill=CARD2, outline=BORDER)
    _text(draw, (36, y + 10), "GENEL YORUM", 12, True, GOLD)
    for i, line in enumerate(lines[:4]):
        draw.text((36, y + 32 + i * 18), line, font=font, fill=MUTED)
    return y + box_h + 16


def render_weekly_image(snapshot: dict[str, Any]) -> Path:
    stats = snapshot["stats"]
    rows = _ranked(stats.get("models") or {})
    matchday = snapshot.get("matchday", "?")
    comment = _comment_weekly(rows, matchday)

    w = 1100
    top = 135
    leaders_h = 116
    header_h = 54
    row_h = 56
    comment_h = 110
    h = top + leaders_h + header_h + max(len(rows), 1) * row_h + comment_h + 40

    im = Image.new("RGB", (w, h), BG)
    d = ImageDraw.Draw(im)
    _draw_header(
        d, w,
        "ŞAMPİYONLAR LİGİ",
        "AI PERFORMANS TABLOSU",
        f"MATCHDAY {matchday}",
        str(snapshot.get("status") or "FINAL"),
    )
    y = _draw_leaders(d, top, w, rows)

    d.rounded_rectangle((20, y, w - 20, y + 46), radius=12, fill=CARD2)
    headers = [
        (36, "#"),
        (70, "MODEL"),
        (210, "KAZANAN"),
        (340, "SKOR"),
        (450, "DOĞRU SONUÇ"),
        (620, "TOPLAM PUAN"),
        (780, "BAŞARI"),
        (920, "ÜRETİLEN"),
    ]
    for x, label in headers:
        _text(d, (x, y + 13), label, 12, True, MUTED)
    y += 54

    for i, r in enumerate(rows):
        bg = CARD if i % 2 == 0 else (16, 28, 46)
        d.rounded_rectangle((20, y, w - 20, y + 52), radius=10, fill=bg)
        _text(d, (42, y + 14), str(i + 1), 15, True, CYAN)
        _text(d, (70, y + 14), r["short"], 15, True, WHITE)
        _text(d, (230, y + 14), str(r["kazanan"]), 16, True, WHITE)
        _text(d, (355, y + 14), str(r["skor"]), 16, True, GREEN)
        _text(d, (490, y + 14), str(r["sonuc"]), 16, True, BLUE)
        _text(d, (650, y + 14), str(r["points"]), 17, True, CYAN)
        _text(d, (790, y + 14), f"{r['avg']:.2f}/6", 15, True, PURPLE)
        _text(d, (930, y + 14), f"{r['uret']}/{r['firs']}", 14, False, MUTED)
        y += row_h

    y += 12
    _draw_comment(d, y, w, comment)

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    path = REPORT_DIR / f"matchday_{matchday}_weekly.png"
    im.save(path, quality=95)
    return path


def render_season_image(season: dict[str, Any]) -> Path:
    weeks = list(season.get("finalized_matchdays") or [])
    rows = _ranked(season.get("models") or {})
    comment = _comment_season(rows, weeks)

    w = 1200 if len(weeks) <= 4 else min(1600, 1000 + len(weeks) * 70)
    top = 135
    leaders_h = 116
    header_h = 54
    row_h = 56
    comment_h = 120
    h = top + leaders_h + header_h + max(len(rows), 1) * row_h + comment_h + 50

    im = Image.new("RGB", (w, h), BG)
    d = ImageDraw.Draw(im)
    week_label = " + ".join(f"MD{md}" for md in weeks) if weeks else "—"
    _draw_header(
        d, w,
        "ŞAMPİYONLAR LİGİ",
        "SEZON AI PERFORMANS TABLOSU",
        SEASON,
        week_label if len(week_label) < 28 else f"{len(weeks)} MATCHDAY",
    )
    y = _draw_leaders(d, top, w, rows)

    md_w = min(70, max(48, 280 // max(len(weeks), 1))) if weeks else 0
    base_md = 170
    after_md = base_md + len(weeks) * md_w + 10

    d.rounded_rectangle((16, y, w - 16, y + 46), radius=12, fill=CARD2)
    _text(d, (28, y + 13), "#", 12, True, MUTED)
    _text(d, (60, y + 13), "MODEL", 12, True, MUTED)
    for i, md in enumerate(weeks):
        _text(d, (base_md + i * md_w, y + 13), f"MD{md}", 12, True, MUTED)
    col_x = {
        "kazanan": after_md,
        "skor": after_md + 100,
        "sonuc": after_md + 180,
        "puan": after_md + 320,
        "basari": after_md + 460,
        "uret": after_md + 570,
    }
    _text(d, (col_x["kazanan"], y + 13), "KAZANAN", 12, True, MUTED)
    _text(d, (col_x["skor"], y + 13), "SKOR", 12, True, MUTED)
    _text(d, (col_x["sonuc"], y + 13), "DOĞRU SONUÇ", 12, True, MUTED)
    _text(d, (col_x["puan"], y + 13), "TOPLAM PUAN", 12, True, MUTED)
    _text(d, (col_x["basari"], y + 13), "BAŞARI", 12, True, MUTED)
    _text(d, (col_x["uret"], y + 13), "ÜRETİLEN", 12, True, MUTED)
    y += 54

    for i, r in enumerate(rows):
        bg = CARD if i % 2 == 0 else (16, 28, 46)
        d.rounded_rectangle((16, y, w - 16, y + 52), radius=10, fill=bg)
        _text(d, (34, y + 14), str(i + 1), 15, True, CYAN)
        _text(d, (60, y + 14), r["short"], 15, True, WHITE)
        wp = r.get("week_points") or {}
        for j, md in enumerate(weeks):
            pts = wp.get(str(md), wp.get(md, "—"))
            _text(d, (base_md + j * md_w, y + 14), str(pts), 14, False, MUTED)
        _text(d, (col_x["kazanan"] + 10, y + 14), str(r["kazanan"]), 16, True, WHITE)
        _text(d, (col_x["skor"] + 10, y + 14), str(r["skor"]), 16, True, GREEN)
        _text(d, (col_x["sonuc"] + 20, y + 14), str(r["sonuc"]), 16, True, BLUE)
        _text(d, (col_x["puan"] + 20, y + 14), str(r["points"]), 17, True, CYAN)
        _text(d, (col_x["basari"], y + 14), f"{r['avg']:.2f}/6", 15, True, PURPLE)
        _text(d, (col_x["uret"], y + 14), f"{r['uret']}/{r['firs']}", 14, False, MUTED)
        y += row_h

    y += 12
    _draw_comment(d, y, w, comment)

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    path = REPORT_DIR / "season_performance.png"
    im.save(path, quality=95)
    return path
