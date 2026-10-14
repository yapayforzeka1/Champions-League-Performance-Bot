"""Champions League AI performance report renderers.

The weekly report is intentionally self-contained: it renders only from the
already graded snapshot/records and never calls an AI or football API.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from config import ACTIVE_MODEL_ORDER, MODEL_SHORT, REPORT_DIR, SEASON
from performance_engine import _model_identity

BG=(4,17,39); PANEL=(7,27,57); PANEL2=(10,34,70); LINE=(20,126,210)
WHITE=(244,247,252); MUTED=(166,184,207); CYAN=(49,177,255); GOLD=(231,180,70)
GREEN=(48,207,137); RED=(255,79,83); ORANGE=(255,166,58); PURPLE=(180,93,255)
MODEL_COLORS=[CYAN,ORANGE,RED,PURPLE,(93,224,165)]


def _font(size:int,bold:bool=False):
    paths=[
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    ]
    for p in paths:
        if Path(p).exists(): return ImageFont.truetype(p,size)
    return ImageFont.load_default()


def _text(d,xy,text,size=18,bold=False,fill=WHITE,anchor=None):
    d.text(xy,str(text),font=_font(size,bold),fill=fill,anchor=anchor)


def _center(d,box,text,size=18,bold=False,fill=WHITE):
    x1,y1,x2,y2=box; _text(d,((x1+x2)//2,(y1+y2)//2),text,size,bold,fill,"mm")


def _wrap(d,text,font,maxw):
    words=str(text).split(); lines=[]; cur=""
    for word in words:
        t=(cur+" "+word).strip()
        if cur and d.textlength(t,font=font)>maxw: lines.append(cur); cur=word
        else: cur=t
    if cur: lines.append(cur)
    return lines or [""]


def _tick(d,cx,cy,ok):
    fill=GREEN if ok else RED
    d.ellipse((cx-12,cy-12,cx+12,cy+12),fill=fill)
    _text(d,(cx,cy-1),"✓" if ok else "×",16,True,WHITE,"mm")


def _seal(d,x,y,r=64):
    # Project signature: DESIGNED BY / Sercan / FUTBOL • VERİ • ANALİZ • TAHMİN
    d.ellipse((x-r,y-r,x+r,y+r),fill=(5,12,20),outline=GOLD,width=3)
    d.ellipse((x-r+8,y-r+8,x+r-8,y+r-8),outline=GOLD,width=1)
    _text(d,(x,y-r+19),"DESIGNED BY",10,True,GOLD,"mm")
    _text(d,(x,y-18),"♛",22,True,GOLD,"mm")
    _text(d,(x,y+8),"Sercan",25,True,GOLD,"mm")
    _text(d,(x,y+r-20),"FUTBOL • VERİ • ANALİZ • TAHMİN",6,True,GOLD,"mm")


def _ucl_mark(d,x,y):
    # Lightweight competition mark; no network/asset dependency.
    for dx,dy in [(0,-25),(23,-8),(14,20),(-14,20),(-23,-8)]:
        _text(d,(x+dx,y+dy),"★",16,False,WHITE,"mm")
    _text(d,(x,y+43),"UEFA",12,True,WHITE,"mm")
    _text(d,(x,y+61),"CHAMPIONS LEAGUE",13,True,WHITE,"mm")


def _record_team(record,key):
    for k in (key, f"{key}_team", f"{key}_name"):
        v=record.get(k)
        if isinstance(v,str) and v: return v
    teams=record.get("teams") or {}
    v=teams.get(key) if isinstance(teams,dict) else None
    if isinstance(v,dict): return str(v.get("name") or "?")
    if v: return str(v)
    return "?"


def _record_time(record):
    raw=record.get("utcDate") or record.get("utc_date") or record.get("kickoff") or record.get("date")
    if not raw: return "—"
    try:
        dt=datetime.fromisoformat(str(raw).replace("Z","+00:00"))
        return dt.strftime("%d.%m\n%H:%M")
    except Exception: return str(raw)[:16]


def _vote_type(points):
    return {8:"TAM SKOR",6:"GOL FARKI",4:"1-X-2",0:"—"}.get(points,"—")


def _display_models(records):
    """Only current ALs that appear in the matchday, including failed votes."""
    return [m for m in ACTIVE_MODEL_ORDER if any(
        any(_model_identity(v) == m for v in (r.get("ai_votes") or []))
        for r in records
    )]


def _model_row(name,stats):
    dist=stats.get("point_distribution") or {}
    successful=int(stats.get("successful_predictions") or 0); points=int(stats.get("points") or 0)
    max_points=successful*8
    return {"name":name,"short":MODEL_SHORT.get(name,name),"dist":dist,"points":points,
            "successful":successful,"opportunities":int(stats.get("prediction_opportunities") or 0),
            "pct":round(points/max_points*100) if max_points else 0}


def _summary_rows(stats):
    rows=[_model_row(m, (stats.get("models") or {})[m]) for m in ACTIVE_MODEL_ORDER
          if m in (stats.get("models") or {}) and
          int((stats["models"][m].get("successful_predictions") or 0)) +
          int((stats["models"][m].get("failed_predictions") or 0)) > 0]
    c=stats.get("consensus") or {}; n=int(c.get("matches") or 0); pts=int(c.get("points") or 0)
    rows.append({"name":"Konsensüs","short":"KONSENSÜS","dist":c.get("point_distribution") or {},"points":pts,
                 "successful":n,"opportunities":int(c.get("evaluated_matches") or 0),"pct":round(pts/(n*8)*100) if n else 0})
    return rows


def _consensus_cell(record):
    c=record.get("consensus") or {}; pts=record.get("consensus_points")
    score=c.get("score") if c.get("score_consensus") else None
    return {"score":score or "—","exact":bool(record.get("consensus_exact_score_correct")),
            "outcome":bool(record.get("consensus_outcome_correct")),"points":pts}


def render_weekly_image(snapshot:dict[str,Any])->Path:
    records=list(snapshot.get("render_records") or [])
    models=_display_models(records)
    groups=models+["__CONSENSUS__"]
    base_cols=[110,230,230,105] # date, home, away, actual
    group_w=190
    w=sum(base_cols)+group_w*len(groups)+32
    header_h=225; table_head=76; row_h=62
    summary_rows=_summary_rows(snapshot.get("stats") or {})
    summary_h=64+52*len(summary_rows)
    bottom_h=245
    h=header_h+table_head+max(1,len(records))*row_h+18+summary_h+18+bottom_h+30
    im=Image.new("RGB",(w,h),BG); d=ImageDraw.Draw(im)

    # Header
    d.rectangle((0,0,w,header_h-12),fill=(5,25,59))
    _ucl_mark(d,92,62); _seal(d,240,82,66)
    _text(d,(w//2,35),"AI PERFORMANS RAPORU",34,True,WHITE,"ma")
    _text(d,(w//2,82),f"{snapshot.get('season') or SEASON} SEZONU",23,False,WHITE,"ma")
    md=snapshot.get("matchday","?")
    _text(d,(w//2,118),f"MAÇ HAFTASI {md}",24,True,WHITE,"ma")
    _text(d,(w//2,154),"FUTBOL • VERİ • ANALİZ • TAHMİN",12,True,GOLD,"ma")
    _text(d,(w-36,34),"Disiplinli analiz, daha güçlü yarınlar.",14,True,GOLD,"ra")
    _text(d,(w-36,64),"More Than a Game",18,False,WHITE,"ra")

    y=header_h
    _text(d,(20,y-4),"MAÇ BAZLI AI TAHMİN SONUÇLARI",21,True,WHITE)
    _text(d,(w-20,y+1),"✓ Doğru    × Yanlış    TS Tam Skor (5)    DB Doğru Beraberlik (5)    DS Doğru Sonuç (3)",11,False,MUTED,"ra")
    y+=34

    # Table header
    x=16
    headers=["TARİH\n(SAAT TS)","EV SAHİBİ","DEPLASMAN","GERÇEK\nSONUÇ"]
    for cw,label in zip(base_cols,headers):
        d.rectangle((x,y,x+cw,y+table_head),fill=PANEL,outline=LINE,width=1); _center(d,(x,y,x+cw,y+table_head),label,11,True,MUTED); x+=cw
    for gi,g in enumerate(groups):
        color=GREEN if g=="__CONSENSUS__" else MODEL_COLORS[gi%len(MODEL_COLORS)]
        label="KONSENSÜS" if g=="__CONSENSUS__" else MODEL_SHORT.get(g,g)
        d.rectangle((x,y,x+group_w,y+table_head),fill=PANEL,outline=color,width=1)
        _center(d,(x,y,x+group_w,y+28),label,12,True,color)
        subs=[("TAHMİN",68),("SKOR",40),("SONUÇ",44),("PUAN",38)]; sx=x
        for lab,sw in subs:
            _center(d,(sx,y+29,sx+sw,y+table_head),lab,8,True,MUTED); sx+=sw
        x+=group_w
    y+=table_head

    # Match rows
    for ri,record in enumerate(records or [{}]):
        row_bg=(5,24,50) if ri%2==0 else (7,30,60); x=16
        actual=record.get("actual") or {}; ah=actual.get("home"); aa=actual.get("away")
        actual_score=f"{ah}-{aa}" if ah is not None and aa is not None else "—"
        vals=[_record_time(record),_record_team(record,"home"),_record_team(record,"away"),actual_score]
        for ci,(cw,val) in enumerate(zip(base_cols,vals)):
            d.rectangle((x,y,x+cw,y+row_h),fill=row_bg,outline=(18,69,111),width=1)
            if ci in (1,2): _text(d,(x+8,y+row_h//2),val,11,ci==3,WHITE,"lm")
            else: _center(d,(x,y,x+cw,y+row_h),val,12,ci==3,WHITE)
            x+=cw
        votes={_model_identity(v):v for v in (record.get("ai_votes") or [])}
        for g in groups:
            if g=="__CONSENSUS__": cell=_consensus_cell(record)
            else:
                v=votes.get(g) or {}; res=v.get("result") or {}; pts=v.get("points")
                cell={"score":res.get("score") or "—","exact":bool(v.get("exact_score_correct")),"outcome":bool(v.get("outcome_correct")),"points":pts}
            d.rectangle((x,y,x+group_w,y+row_h),fill=row_bg,outline=(18,69,111),width=1)
            _center(d,(x,y,x+68,y+row_h),cell["score"],11,True,WHITE)
            if cell["points"] is None:
                _center(d,(x+68,y,x+108,y+row_h),"—",13,True,MUTED); _center(d,(x+108,y,x+152,y+row_h),"—",13,True,MUTED)
            else:
                _tick(d,x+88,y+row_h//2,cell["exact"]); _tick(d,x+130,y+row_h//2,cell["outcome"])
            pts="—" if cell["points"] is None else str(cell["points"])
            _center(d,(x+152,y,x+190,y+row_h),pts,13,True,GREEN if pts not in ("0","—") else RED if pts=="0" else MUTED)
            if cell["points"] is not None:
                _text(d,(x+5,y+4),_vote_type(int(cell["points"])),7,True,MUTED)
            x+=group_w
        y+=row_h

    y+=18
    # Summary
    d.rounded_rectangle((16,y,w-16,y+summary_h),radius=12,fill=PANEL,outline=LINE,width=2)
    _text(d,(32,y+12),"HAFTALIK PERFORMANS ÖZETİ",20,True,WHITE); y0=y+48
    cols=[(32,140,"MODEL"),(172,108,"8P\nTAM"),(280,108,"6P\nFARK"),(388,108,"4P\nSONUÇ"),(496,108,"0P\nYANLIŞ"),(604,114,"KAPSAMA"),(718,94,"TAHMİN"),(812,116,"TOPLAM\nPUAN"),(928,w-960,"BAŞARI")]
    for cx,cw,label in cols: _center(d,(cx,y0,cx+cw,y0+42),label,9,True,MUTED)
    yy=y0+42
    for i,r in enumerate(summary_rows):
        d.line((32,yy,w-32,yy),fill=(18,69,111),width=1)
        color=GREEN if r["short"]=="KONSENSÜS" else MODEL_COLORS[i%len(MODEL_COLORS)]
        _text(d,(44,yy+24),r["short"],12,True,color,"lm")
        dist=r["dist"]; values=[dist.get("8",0),dist.get("6",0),dist.get("4",0),dist.get("0",0),f"{r['successful']}/{r['opportunities']}",r["successful"],r["points"]]
        centers=[226,334,442,550,661,765,870]
        for cx,val in zip(centers,values): _text(d,(cx,yy+24),str(val),12,True,WHITE,"mm")
        pct=r["pct"]; _text(d,(958,yy+24),f"%{pct}",12,True,WHITE,"lm")
        bx=1010; bw=max(10,int((w-1045)*min(100,pct)/100)); d.rounded_rectangle((bx,yy+16,w-35,yy+32),radius=8,fill=(15,48,83)); d.rounded_rectangle((bx,yy+16,bx+bw,yy+32),radius=8,fill=color)
        yy+=52
    y+=summary_h+18

    # Bottom panels
    gap=14; left=16; avail=w-32; pw=(avail-gap*2)//3
    panels=[(left,"HAFTANIN ÖNE ÇIKANLARI"),(left+pw+gap,"PUANLAMA SİSTEMİ"),(left+2*(pw+gap),"GENEL DEĞERLENDİRME")]
    for px,title in panels:
        d.rounded_rectangle((px,y,px+pw,y+bottom_h),radius=12,fill=PANEL,outline=LINE,width=2); _text(d,(px+18,y+16),title,16,True,CYAN)
    # Highlights from real stats only
    best=max(summary_rows,key=lambda r:(r["points"],r["pct"])) if summary_rows else None
    highlights=[]
    if best: highlights.append(f"{best['short']} {best['points']} puan ile haftanın puan lideri.")
    exact_models = [(m, s) for m, s in (snapshot.get("stats") or {}).get("models", {}).items()
                    if m in models]
    if exact_models:
        exact_name, exact_stats = max(exact_models, key=lambda pair: int(pair[1].get("exact") or 0))
        highlights.append(f"En fazla tam skor: {MODEL_SHORT.get(exact_name, exact_name)} ({int(exact_stats.get('exact') or 0)} maç).")
    highlights.append(f"Değerlendirilen maç: {snapshot.get('evaluated_matches',len(records))} / Planlanan: {snapshot.get('planned_matches',len(records))}.")
    fy=y+54
    for line in highlights[:4]:
        _tick(d,left+28,fy+7,True); font=_font(11); wrapped=_wrap(d,line,font,pw-70)
        for j,t in enumerate(wrapped[:2]): d.text((left+50,fy+j*17),t,font=font,fill=WHITE)
        fy+=45
    score_lines=["Tam skor: 8 puan", "Doğru gol farkı (beraberlik dahil): 6",
                 "Diğer doğru 1-X-2: 4 puan", "Yanlış 1-X-2: 0 puan"]
    py=y+55
    for line in score_lines: _text(d,(left+pw+gap+22,py),line,11,False,WHITE); py+=32
    eval_text="AI modelleri gerçek sonuçlara göre ayrı ayrı puanlanır. Yanıt üretemeyen model 0 puanla cezalandırılmaz; coverage eksikliği olarak izlenir. Konsensüs ayrıca değerlendirilir."
    font=_font(11); py=y+56
    for line in _wrap(d,eval_text,font,pw-40)[:7]: d.text((left+2*(pw+gap)+20,py),line,font=font,fill=WHITE); py+=19
    _text(d,(left+2*(pw+gap)+pw-20,y+bottom_h-34),"Sercan • Futbol • Veri • Analiz • Tahmin",10,True,GOLD,"ra")

    _text(d,(20,h-43),"Not: Eski AL sürümleri yalnızca performans arşivinde korunur.",10,False,MUTED)
    _text(d,(20,h-22),f"UEFA CHAMPIONS LEAGUE  |  {snapshot.get('season') or SEASON}",10,True,MUTED)
    _text(d,(w//2,h-22),"FOOTBALL. DATA. INTELLIGENCE. BETTER PREDICTIONS.",9,False,MUTED,"ma")
    _text(d,(w-20,h-22),"MORE THAN A GAME",10,True,MUTED,"ra")
    REPORT_DIR.mkdir(parents=True,exist_ok=True); path=REPORT_DIR/f"kicktipp_matchday_{md}_weekly.png"; im.save(path,quality=95); return path


def render_season_image(season:dict[str,Any])->Path:
    """Compact season report, keeping the same visual identity/signature."""
    rows=[]
    for m in ACTIVE_MODEL_ORDER:
        s=(season.get("models") or {}).get(m)
        if s and int(s.get("successful_predictions") or 0) + int(s.get("failed_predictions") or 0) > 0:
            rows.append(_model_row(m,s))
    c=season.get("consensus") or {}; n=int(c.get("matches") or 0); pts=int(c.get("points") or 0)
    rows.append({"short":"KONSENSÜS","points":pts,"pct":round(pts/(n*8)*100) if n else 0,"dist":c.get("point_distribution") or {},"successful":n,"opportunities":int(c.get("evaluated_matches") or 0)})
    w=1200; h=560+len(rows)*60; im=Image.new("RGB",(w,h),BG); d=ImageDraw.Draw(im)
    _ucl_mark(d,90,65); _seal(d,235,82,64)
    _text(d,(w//2,40),"SEZON AI PERFORMANS RAPORU",32,True,WHITE,"ma"); _text(d,(w//2,86),season.get("season") or SEASON,22,True,CYAN,"ma")
    mds=season.get("finalized_matchdays") or []; _text(d,(w//2,122),f"{len(mds)} MATCHDAY FINAL",16,True,MUTED,"ma")
    y=180; d.rounded_rectangle((30,y,w-30,y+58),radius=12,fill=PANEL2,outline=LINE)
    heads=[(55,"MODEL"),(335,"TOPLAM PUAN"),(545,"8P / 6P / 4P / 0P"),(860,"BAŞARI"),(1000,"ÜRETİLEN")]
    for x,t in heads:_text(d,(x,y+20),t,12,True,MUTED)
    y+=68
    for i,r in enumerate(rows):
        d.rounded_rectangle((30,y,w-30,y+52),radius=10,fill=PANEL if i%2==0 else PANEL2)
        color=GREEN if r["short"]=="KONSENSÜS" else MODEL_COLORS[i%len(MODEL_COLORS)]
        _text(d,(55,y+17),r["short"],14,True,color); _text(d,(355,y+17),r["points"],14,True,WHITE)
        _text(d,(565,y+17)," / ".join(str(r["dist"].get(k,0)) for k in ("8","6","4","0")),14,True,WHITE); _text(d,(865,y+17),f"%{r['pct']}",14,True,WHITE); _text(d,(1000,y+17),f"{r['successful']}/{r['opportunities']}",14,False,MUTED); y+=60
    _text(d,(30,h-72),"Not: Geçmiş AL sürümlerinin istatistikleri arşivde korunur; güncel sıralamaya dahil edilmez.",10,False,MUTED)
    _text(d,(30,h-42),"DESIGNED BY SERCAN • FUTBOL • VERİ • ANALİZ • TAHMİN",11,True,GOLD)
    REPORT_DIR.mkdir(parents=True,exist_ok=True); path=REPORT_DIR/"kicktipp_season_performance.png"; im.save(path,quality=95); return path
