"""Modern dark performance report images for Telegram."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from config import MODEL_ORDER, MODEL_SHORT, REPORT_DIR, SEASON

# Palette aligned with prediction-bot cards
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
RED = (239, 68, 68)

POINT_COLORS = {
    "6": (22, 163, 74),
    "5": (37, 99, 235),
    "3": (202, 138, 4),
    "2": (234, 88, 12),
    "0": (185, 28, 28),
}


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


def _center(draw, box, text, size=18, bold=False, fill=WHITE):
    f = _font(size, bold)
    bb = draw.textbbox((0, 0), str(text), font=f)
    x1, y1, x2, y2 = box
    draw.text(
        ((x1 + x2 - (bb[2] - bb[0])) / 2, (y1 + y2 - (bb[3] - bb[1])) / 2 - 1),
        str(text),
        font=f,
        fill=fill,
    )


def _panel(draw, box, fill=CARD, radius=14):
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=BORDER, width=1)


def _pill(draw, x, y, text, fill, text_fill=WHITE, pad_x=12, pad_y=5, size=13, bold=True):
    f = _font(size, bold)
    w = _tw(draw, text, f) + pad_x * 2
    h = size + pad_y * 2 + 2
    draw.rounded_rectangle((x, y, x + w, y + h), radius=h // 2, fill=fill)
    draw.text((x + pad_x, y + pad_y - 1), str(text), font=f, fill=text_fill)
    return w


def _distribution_row(draw, x, y, dist: dict | None, cell_w=56, gap=8):
    """Compact 6P..0P chips with counts underneath."""
    dist = dist or {}
    for i, p in enumerate(("6", "5", "3", "2", "0")):
        cx = x + i * (cell_w + gap)
        draw.rounded_rectangle((cx, y, cx + cell_w, y + 28), radius=8, fill=POINT_COLORS[p])
        _center(draw, (cx, y, cx + cell_w, y + 28), f"{p}P", 13, True, WHITE)
        _center(draw, (cx, y + 30, cx + cell_w, y + 52), str(dist.get(p, 0)), 15, True, MUTED)


def _rank_models(stats_models: dict) -> list[tuple[str, dict]]:
    rows = [(m, stats_models[m]) for m in MODEL_ORDER if m in stats_models]
    rows.sort(key=lambda x: (-x[1].get("points", 0), -x[1].get("coverage_pct", 0), x[0]))
    return rows


def render_weekly_image(snapshot: dict[str, Any]) -> Path:
    stats = snapshot["stats"]
    c = stats["consensus"]
    ranked = _rank_models(stats["models"])

    # dynamic height
    w = 1000
    top = 160
    summary_h = 100
    model_h = 88
    consensus_h = 120
    footer_h = 50
    h = top + summary_h + 40 + 36 + len(ranked) * (model_h + 12) + 40 + consensus_h + footer_h + 30

    im = Image.new("RGB", (w, h), BG)
    d = ImageDraw.Draw(im)

    # header bar
    d.rectangle((0, 0, w, top - 20), fill=HEADER)
    _text(d, (32, 28), "ŞAMPİYONLAR LİGİ", 26, True, WHITE)
    _text(d, (32, 64), "HAFTALIK AI PERFORMANS", 18, True, CYAN)
    md = f"MATCHDAY {snapshot['matchday']}"
    fw = _tw(d, md, _font(16, True))
    _pill(d, w - 32 - fw - 24, 36, md, GOLD, (11, 21, 38), pad_x=12, pad_y=6, size=14)
    status = snapshot.get("status", "FINAL")
    _text(d, (w - 32 - fw - 24, 78), status, 13, True, MUTED)

    # summary cards
    y = top
    cards = [
        (str(snapshot.get("evaluated_matches", 0)), "DEĞERLENDİRİLEN"),
        (f"{c.get('matches', 0)}/{c.get('evaluated_matches', 0)}", "ORTAK KARAR"),
        (str(len(MODEL_ORDER)), "AI MODELİ"),
    ]
    gap = 14
    card_w = (w - 64 - gap * 2) // 3
    for i, (val, label) in enumerate(cards):
        x = 32 + i * (card_w + gap)
        _panel(d, (x, y, x + card_w, y + summary_h - 10), CARD2)
        _text(d, (x + 18, y + 18), val, 28, True, CYAN if i != 1 else GOLD)
        _text(d, (x + 18, y + 58), label, 13, True, MUTED)

    y += summary_h + 20
    _text(d, (32, y), "BİREYSEL SIRALAMA", 16, True, GOLD)
    y += 32

    for rank, (model, s) in enumerate(ranked, 1):
        short = MODEL_SHORT.get(model, model)
        _panel(d, (32, y, w - 32, y + model_h))
        # rank circle
        d.ellipse((48, y + 28, 76, y + 56), fill=CARD2, outline=BORDER)
        _center(d, (48, y + 28, 76, y + 56), str(rank), 14, True, CYAN)
        _text(d, (92, y + 16), short, 18, True, WHITE)
        _text(d, (92, y + 44), f"Ort. {s.get('avg', 0)} / 6", 13, False, MUTED)

        pts = f"{s.get('points', 0)} PUAN"
        _text(d, (260, y + 18), pts, 20, True, CYAN)

        _distribution_row(d, 420, y + 16, s.get("point_distribution"))

        cov = f"{s.get('successful_predictions', 0)}/{s.get('prediction_opportunities', 0)}"
        _text(d, (820, y + 18), cov, 16, True, WHITE)
        _text(d, (820, y + 46), f"%{s.get('coverage_pct', 0)}", 13, False, MUTED)
        y += model_h + 12

    y += 8
    _text(d, (32, y), "ORTAK KARAR", 16, True, GOLD)
    y += 28
    _panel(d, (32, y, w - 32, y + consensus_h), CARD2)
    _text(d, (52, y + 18), f"{c.get('points', 0)} PUAN", 22, True, GOLD)
    _text(d, (52, y + 50), f"Ort. {c.get('avg', 0)} / 6", 14, False, MUTED)
    _text(
        d,
        (52, y + 78),
        f"Ortak: {c.get('matches', 0)}/{c.get('evaluated_matches', 0)}  ·  %{c.get('coverage_pct', 0)}",
        13,
        True,
        MUTED,
    )
    _distribution_row(d, 420, y + 24, c.get("point_distribution"))
    _text(d, (820, y + 28), f"Ortak yok: {c.get('no_consensus', 0)}", 13, True, MUTED)
    _text(d, (820, y + 54), f"Skor bölünmesi: {c.get('score_split', 0)}", 13, False, MUTED)

    y = h - 40
    _text(
        d,
        (32, y),
        "6P Tam skor  ·  5P Kazanan+fark  ·  3P Beraberlik  ·  2P Kazanan  ·  0P Yanlış",
        12,
        False,
        MUTED,
    )

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    path = REPORT_DIR / f"matchday_{snapshot['matchday']}_weekly.png"
    im.save(path, quality=95)
    return path


def render_season_image(season: dict[str, Any]) -> Path:
    weeks = list(season.get("finalized_matchdays") or [])
    c = season["consensus"]
    ranked = _rank_models(season["models"])

    w = 1000
    # columns: rank | model | each MD | total | avg | coverage
    col_md = max(1, len(weeks))
    top = 150
    row_h = 56
    header_h = 44
    summary_h = 90
    consensus_h = 110
    h = top + summary_h + 36 + header_h + len(ranked) * row_h + 36 + consensus_h + 50

    im = Image.new("RGB", (w, h), BG)
    d = ImageDraw.Draw(im)

    d.rectangle((0, 0, w, top - 20), fill=HEADER)
    _text(d, (32, 28), "ŞAMPİYONLAR LİGİ", 26, True, WHITE)
    _text(d, (32, 64), "SEZON GENELİ AI PERFORMANS", 18, True, CYAN)
    _text(d, (w - 32 - _tw(d, SEASON, _font(16, True)), 40), SEASON, 16, True, GOLD)

    y = top
    total_matches = max(
        (season["models"][m].get("prediction_opportunities", 0) for m in MODEL_ORDER if m in season["models"]),
        default=0,
    )
    cards = [
        (str(total_matches), "TOPLAM MAÇ"),
        (str(len(weeks)), "FINAL MATCHDAY"),
        (f"{c.get('matches', 0)}/{c.get('evaluated_matches', 0)}", "ORTAK KARAR"),
    ]
    gap = 14
    card_w = (w - 64 - gap * 2) // 3
    for i, (val, label) in enumerate(cards):
        x = 32 + i * (card_w + gap)
        _panel(d, (x, y, x + card_w, y + summary_h - 10), CARD2)
        _text(d, (x + 18, y + 16), val, 26, True, CYAN if i < 2 else GOLD)
        _text(d, (x + 18, y + 52), label, 13, True, MUTED)

    y += summary_h + 16
    _text(d, (32, y), "MODEL SIRALAMASI", 16, True, GOLD)
    y += 28

    # table header
    _panel(d, (32, y, w - 32, y + header_h), CARD2, radius=10)
    _text(d, (48, y + 12), "#", 13, True, MUTED)
    _text(d, (80, y + 12), "MODEL", 13, True, MUTED)
    # week columns
    base_x = 280
    md_w = min(70, max(48, (420 // max(col_md, 1))))
    for i, md in enumerate(weeks):
        _text(d, (base_x + i * md_w, y + 12), f"MD{md}", 12, True, MUTED)
    _text(d, (base_x + col_md * md_w + 10, y + 12), "TOPLAM", 13, True, MUTED)
    _text(d, (base_x + col_md * md_w + 100, y + 12), "ORT.", 13, True, MUTED)
    _text(d, (base_x + col_md * md_w + 170, y + 12), "COV.", 13, True, MUTED)
    y += header_h + 4

    for rank, (model, s) in enumerate(ranked, 1):
        short = MODEL_SHORT.get(model, model)
        bg = CARD if rank % 2 else (16, 28, 46)
        d.rounded_rectangle((32, y, w - 32, y + row_h - 4), radius=8, fill=bg)
        _text(d, (52, y + 16), str(rank), 15, True, CYAN)
        _text(d, (80, y + 16), short, 15, True, WHITE)

        week_points = s.get("week_points") or {}
        for i, md in enumerate(weeks):
            pts = week_points.get(str(md), week_points.get(md, "—"))
            _text(d, (base_x + i * md_w, y + 16), str(pts), 14, False, MUTED)

        _text(d, (base_x + col_md * md_w + 10, y + 16), str(s.get("points", 0)), 15, True, CYAN)
        _text(d, (base_x + col_md * md_w + 100, y + 16), str(s.get("avg", 0)), 14, False, MUTED)
        _text(d, (base_x + col_md * md_w + 170, y + 16), f"%{s.get('coverage_pct', 0)}", 14, False, MUTED)
        y += row_h

    y += 16
    _text(d, (32, y), "ORTAK KARAR — SEZON", 16, True, GOLD)
    y += 28
    _panel(d, (32, y, w - 32, y + consensus_h), CARD2)
    _text(d, (52, y + 18), f"{c.get('points', 0)} PUAN", 22, True, GOLD)
    _text(d, (52, y + 50), f"Ort. {c.get('avg', 0)} / 6  ·  Ortak {c.get('matches', 0)}/{c.get('evaluated_matches', 0)}", 14, False, MUTED)
    _text(d, (52, y + 78), f"Ortak yok: {c.get('no_consensus', 0)}  ·  Tam skor: {c.get('exact', 0)}", 13, False, MUTED)
    _distribution_row(d, 520, y + 28, c.get("point_distribution"))

    y = h - 36
    _text(
        d,
        (32, y),
        "Coverage = API erişimi  ·  Puan = yalnızca başarılı tahminlerin futbol skoru",
        12,
        False,
        MUTED,
    )

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    path = REPORT_DIR / "season_performance.png"
    im.save(path, quality=95)
    return path
