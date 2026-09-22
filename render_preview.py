"""Offline visual preview: no AI, GitHub prediction source, or football-data API calls."""
from __future__ import annotations
import os
from datetime import datetime, timezone, timedelta

from config import MODEL_ORDER
from performance_engine import build_weekly_stats, grade_record
from telegram_report import send_photo
from weekly_report import render_weekly_image, render_season_image


def _vote(model, score, ok=True):
    if not ok: return {"model":model,"success":False,"result":None,"error":"OFFLINE_PREVIEW"}
    h,a=map(int,score.split("-")); outcome="HOME" if h>a else "AWAY" if h<a else "DRAW"
    return {"model":model,"success":True,"result":{"score":score,"outcome":outcome}}


def _rec(mid,home,away,actual,scores,kickoff):
    votes=[_vote(m,scores.get(m),scores.get(m) is not None) for m in MODEL_ORDER]
    r={"match_id":str(mid),"matchday":1,"home":home,"away":away,"utcDate":kickoff.isoformat(),"ai_votes":votes}
    return grade_record(r,actual[0],actual[1])


def main():
    base=datetime(2026,9,16,16,45,tzinfo=timezone.utc)
    games=[
      (1,"Juventus","Dortmund",(2,1),["2-1","1-1","2-1","1-2","2-0"]),
      (2,"Real Madrid","Marseille",(3,0),["3-1","2-0","3-0","2-1","3-0"]),
      (3,"Benfica","Qarabag",(1,1),["1-1","0-1","1-1","2-1","1-1"]),
      (4,"Tottenham","Villarreal",(1,0),["1-0","1-1","2-0","1-0","1-0"]),
      (5,"Olympiacos","Pafos",(0,0),["0-1","0-0","1-1","0-0","0-0"]),
      (6,"Ajax","Inter",(1,2),["1-2","0-2","1-1","1-2","1-2"]),
      (7,"Slavia Prag","Bodo/Glimt",(2,2),["2-1","1-1","2-2","1-2","2-2"]),
      (8,"Bayern Münih","Chelsea",(3,1),["3-1","2-1","3-2","1-1","3-1"]),
    ]
    records={}
    for i,(mid,h,a,actual,scores) in enumerate(games):
        sm={m:scores[j] for j,m in enumerate(MODEL_ORDER)}
        records[str(mid)]=_rec(mid,h,a,actual,sm,base+timedelta(hours=(i//2)*2))
    stats=build_weekly_stats(records,1)
    snap={"season":"2026/27","matchday":1,"status":"FINAL","planned_matches":8,"evaluated_matches":8,"unavailable_matches":0,"postponed_matches":0,"pending_matches":0,"stats":stats,"render_records":list(records.values())}
    weekly=render_weekly_image(snap)
    season={"season":"2026/27","finalized_matchdays":[1],"models":stats["models"],"consensus":stats["consensus"]}
    season_img=render_season_image(season)
    print(f"OFFLINE PERFORMANCE VISUAL TEST OK weekly={weekly} season={season_img}. AI/GitHub/Football-Data API çağrısı yapılmadı.")
    if os.getenv("PREVIEW_SEND_TELEGRAM","false").lower() in {"1","true","yes","on"}:
        send_photo(weekly,"🧪 OFFLINE TEST — Şampiyonlar Ligi AI Performans Görseli")
        send_photo(season_img,"🧪 OFFLINE TEST — Şampiyonlar Ligi Sezon Performans Görseli")
        print("OFFLINE preview Telegram'a gönderildi.")

if __name__=="__main__": main()
