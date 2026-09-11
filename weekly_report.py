from __future__ import annotations

from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from config import MODEL_ORDER, MODEL_SHORT, REPORT_DIR


def _font(size: int, bold: bool = False):
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    ]
    for path in candidates:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def _wrap(draw, text: str, font, max_width: int) -> list[str]:
    words = str(text).split()
    lines, current = [], ""
    for word in words:
        trial = f"{current} {word}".strip()
        if draw.textbbox((0, 0), trial, font=font)[2] <= max_width:
            current = trial
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines or [""]


def _center(draw, box, text: str, font, fill):
    x1, y1, x2, y2 = box
    bb = draw.textbbox((0, 0), text, font=font)
    draw.text(((x1+x2-(bb[2]-bb[0]))/2, (y1+y2-(bb[3]-bb[1]))/2-2), text, font=font, fill=fill)


def render_weekly_image(snapshot: dict[str, Any]) -> Path:
    rows = [m for m in snapshot.get("matches", []) if m.get("status") == "EVALUATED"]
    rows.sort(key=lambda r: str(r.get("utcDate", "")))
    width = 2200
    row_h = 92
    header_h = 72
    top = 170
    summary_h = 430
    height = top + header_h + max(1, len(rows)) * row_h + summary_h
    image = Image.new("RGB", (width, height), (4, 10, 20))
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, width, 145), fill=(8, 16, 31), outline=(35, 155, 225), width=2)
    draw.text((40, 20), "ŞAMPİYONLAR LİGİ 2026/27", font=_font(38, True), fill=(245,245,245))
    draw.text((40, 82), f"HAFTALIK PERFORMANS RAPORU  •  MATCHDAY {snapshot['matchday']}  •  FINAL", font=_font(21, True), fill=(90,210,255))

    cols = [("MAÇ", 390), ("GERÇEK", 120)]
    for model in MODEL_ORDER:
        cols.extend([(MODEL_SHORT[model], 145), ("PUAN", 78)])
    cols.extend([("KONSENSÜS", 145), ("PUAN", 78)])
    xs=[]; x=24
    for label,w in cols:
        xs.append(x); draw.rectangle((x,top,x+w,top+header_h),fill=(17,39,67),outline=(52,108,155),width=2)
        _center(draw,(x,top,x+w,top+header_h),label,_font(15,True),(242,246,250)); x+=w
    y=top+header_h

    pred_by_id={str(m.get("match_id")): m for m in snapshot.get("matches",[])}
    # Actual records are stored by the engine separately; the image gets them from match rows below.
    records = snapshot.get("render_records", [])
    by_id = {str(r.get("match_id")): r for r in records}
    for row in rows:
        rec=by_id.get(str(row["match_id"]),{})
        actual=rec.get("actual",{})
        actual_score=f"{actual.get('home','-')}-{actual.get('away','-')}"
        match=f"{row.get('home','?')}\n{row.get('away','?')}"
        values=[match,actual_score]
        votes={str(v.get('model')):v for v in rec.get('ai_votes',[])}
        for model in MODEL_ORDER:
            v=votes.get(model)
            if v and v.get('success'):
                values += [str((v.get('result') or {}).get('score','-')), str(v.get('points','-'))]
            else:
                values += ['YOK','-']
        c=rec.get('consensus',{})
        if c.get('winner_consensus'):
            ctext=str(c.get('score')) if c.get('score_consensus') else 'SONUÇ ORTAK'
            cp=rec.get('consensus_points')
            values += [ctext, str(cp if cp is not None else '-')]
        else:
            values += ['ORTAK YOK','-']
        for idx, value in enumerate(values):
            w=cols[idx][1]; x=xs[idx]
            draw.rectangle((x,y,x+w,y+row_h),fill=(7,17,30),outline=(38,70,98),width=1)
            lines=value.split('\n')
            if len(lines)==1:
                _center(draw,(x+4,y+2,x+w-4,y+row_h-2),value,_font(18 if idx==0 else 20,True),(240,243,247))
            else:
                yy=y+18
                for line in lines:
                    _center(draw,(x+4,yy,x+w-4,yy+28),line,_font(17,True),(240,243,247)); yy+=28
        y+=row_h

    y+=25
    stats=snapshot["stats"]
    draw.text((30,y),"AI PERFORMANSI",font=_font(26,True),fill=(255,205,55)); y+=50
    cards=[]
    ranked=sorted(MODEL_ORDER,key=lambda m:(-int(stats['models'][m]['points']),-int(stats['models'][m]['exact']),MODEL_ORDER.index(m)))
    for rank,model in enumerate(ranked,1):
        s=stats['models'][model]
        cards.append((f"{rank}. {MODEL_SHORT[model]}",f"{s['points']} PUAN",f"Başarılı: {s['successful_predictions']} / Fırsat: {s['prediction_opportunities']}",f"Ort: {s['avg']}  •  Tam: {s['exact']}  •  Sonuç: {s['outcome']}",f"Kapsama: %{s['coverage_pct']}"))
    c=stats['consensus']
    cards.append(("KONSENSÜS",f"{c['points']} PUAN",f"Geçerli ortak: {c['matches']}",f"Tam: {c['exact']}  •  Sonuç: {c['outcome']}",f"Ortak yok: {c['no_consensus']}  •  Skor bölünmesi: {c['score_split']}"))
    cw,ch,gap=340,165,15
    for i,card in enumerate(cards):
        x=30+i*(cw+gap)
        draw.rectangle((x,y,x+cw,y+ch),fill=(10,23,39),outline=(55,145,205),width=2)
        draw.text((x+12,y+10),card[0],font=_font(19,True),fill=(245,245,245))
        draw.text((x+12,y+45),card[1],font=_font(25,True),fill=(80,220,255))
        draw.text((x+12,y+82),card[2],font=_font(14,True),fill=(225,225,225))
        draw.text((x+12,y+106),card[3],font=_font(13),fill=(220,220,220))
        draw.text((x+12,y+132),card[4],font=_font(13,True),fill=(255,210,55))

    y += ch + 20
    draw.rectangle((30,y,width-30,height-20),fill=(7,17,30),outline=(48,110,155),width=2)
    info=(f"FINAL durum: {snapshot['evaluated_matches']} maç değerlendirildi, "
          f"{snapshot['unavailable_matches']} tahmin kaydı yok, {snapshot['postponed_matches']} ertelenmiş/iptal. "
          "Tahmin kaydı olmayan maçlar 0 puan verilerek AI başarısızlığına yazılmaz; ayrı 'UNAVAILABLE' olarak raporlanır. "
          "Mistral/Gemini gibi API erişim sorunu yaşayan modeller için puan yanında kapsama oranı da gösterilir.")
    yy=y+18
    for line in _wrap(draw,info,_font(16),width-100):
        draw.text((50,yy),line,font=_font(16),fill=(230,233,238)); yy+=26
    REPORT_DIR.mkdir(parents=True,exist_ok=True)
    path=REPORT_DIR/f"matchday_{snapshot['matchday']}_weekly.png"
    image.save(path)
    return path


def render_season_image(season: dict[str, Any]) -> Path:
    width=1750; row_h=70; height=260+(len(MODEL_ORDER)+1)*row_h+260
    image=Image.new("RGB",(width,height),(4,10,20)); draw=ImageDraw.Draw(image)
    draw.rectangle((0,0,width,145),fill=(8,16,31),outline=(35,155,225),width=2)
    draw.text((40,20),"ŞAMPİYONLAR LİGİ 2026/27",font=_font(38,True),fill=(245,245,245))
    draw.text((40,82),"GENEL PERFORMANS  •  SADECE FINAL MATCHDAY VERİLERİ",font=_font(21,True),fill=(90,210,255))
    weeks=season.get('finalized_matchdays',[])
    x0=30; y=170
    cols=[("AI MODELİ",300)]+[(f"MD {w}",130) for w in weeks]+[("SEZON TOPLAM",180),("ORT.",120)]
    xs=[]; x=x0
    for label,w in cols:
        xs.append(x); draw.rectangle((x,y,x+w,y+50),fill=(17,39,67),outline=(52,108,155),width=2); _center(draw,(x,y,x+w,y+50),str(label),_font(14,True),(242,246,250)); x+=w
    y+=50
    ranked=sorted(MODEL_ORDER,key=lambda m:(-int(season['models'][m]['points']),-int(season['models'][m]['exact']),MODEL_ORDER.index(m)))
    for model in ranked:
        d=season['models'][model]; vals=[MODEL_SHORT[model]]+[str(season['models'][model].get('week_points',{}).get(str(w),0)) for w in weeks]+[str(d['points']),str(d['avg'])]
        x=x0
        for i,val in enumerate(vals):
            w=cols[i][1]; draw.rectangle((x,y,x+w,y+row_h),fill=(7,17,30),outline=(38,70,98),width=1); draw.text((x+12,y+20),val,font=_font(18,True),fill=(245,245,245)); x+=w
        y+=row_h
    d=season['consensus']; vals=['KONSENSÜS']+[str(d.get('week_points',{}).get(str(w),0)) for w in weeks]+[str(d['points']),str(d['avg'])]
    x=x0
    for i,val in enumerate(vals):
        w=cols[i][1]; draw.rectangle((x,y,x+w,y+row_h),fill=(28,25,10),outline=(225,180,45),width=1); draw.text((x+12,y+20),val,font=_font(18,True),fill=(255,220,80)); x+=w
    y+=row_h+30
    draw.text((50,y),f"Final Matchday sayısı: {len(weeks)}",font=_font(20,True),fill=(255,205,55))
    REPORT_DIR.mkdir(parents=True,exist_ok=True)
    path=REPORT_DIR/"season_performance.png"; image.save(path); return path
