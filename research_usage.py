"""Weekly research adoption, measured with first-party workspace actions."""
from datetime import date, datetime, timedelta, timezone
import time


def init(db):
    db.executescript("""
        CREATE TABLE IF NOT EXISTS research_days(
          owner INTEGER NOT NULL, cohort TEXT NOT NULL, day TEXT NOT NULL,
          PRIMARY KEY(owner,cohort,day)) WITHOUT ROWID;
        CREATE TABLE IF NOT EXISTS research_runs(
          owner INTEGER NOT NULL, source TEXT NOT NULL, market TEXT NOT NULL, cutoff TEXT NOT NULL,
          days INTEGER NOT NULL, day TEXT NOT NULL, started INTEGER NOT NULL, finished INTEGER,
          PRIMARY KEY(owner,source,market,cutoff,days,day)) WITHOUT ROWID;
        CREATE TABLE IF NOT EXISTS research_details(
          owner INTEGER NOT NULL, source TEXT NOT NULL, market TEXT NOT NULL, cutoff TEXT NOT NULL,
          days INTEGER NOT NULL, day TEXT NOT NULL, item TEXT NOT NULL,
          PRIMARY KEY(owner,source,market,cutoff,days,day,item)) WITHOUT ROWID;
        CREATE INDEX IF NOT EXISTS research_week ON research_days(day,cohort,owner);
        CREATE INDEX IF NOT EXISTS research_completed ON research_runs(day,owner,source) WHERE finished IS NOT NULL;
    """)


def record(db,owner,scope,action,item="",moment=None):
    stamp=int(time.time()) if moment is None else moment
    day=datetime.fromtimestamp(stamp,timezone.utc).date().isoformat()
    event_day=day
    cohort="demo" if scope["source"]=="demo" else "imported"
    window=(owner,scope["source"],scope["market"],scope["date"],scope["days"])
    match_window="owner=? AND source=? AND market=? AND cutoff=? AND days=?"
    if action in ("list","detail"):
        db.execute("INSERT OR IGNORE INTO research_days VALUES(?,?,?)",(owner,cohort,day))
    if action=="list":
        db.execute("INSERT OR IGNORE INTO research_runs VALUES(?,?,?,?,?,?,?,NULL)",(*window,day,stamp))
        return
    eligible=match_window+" AND (day=? OR started BETWEEN ? AND ?) AND finished IS NULL"
    args=(*window,day,stamp-300,stamp)
    if action=="detail":
        db.execute(f"""INSERT OR IGNORE INTO research_details
            SELECT owner,source,market,cutoff,days,day,? FROM research_runs
            WHERE {eligible} ORDER BY day DESC LIMIT 1""",(item,*args))
        return
    if action not in ("save","export"):raise ValueError("Unknown research action")
    # A newly opened list after midnight must not hide a qualifying detail from the preceding run.
    joined="research_runs JOIN research_details USING(owner,source,market,cutoff,days,day)"
    if action=="save":
        eligible+=" AND item=?"
        args=(*args,item)
    completed=db.execute(f"""UPDATE research_runs SET finished=? WHERE {match_window} AND finished IS NULL
        AND day=(SELECT day FROM {joined} WHERE {eligible} ORDER BY day DESC LIMIT 1)
        RETURNING day""",(stamp,*window,*args)).fetchone()
    if completed and event_day != completed[0]:
        db.execute("INSERT OR IGNORE INTO research_days VALUES(?,?,?)",(owner,cohort,event_day))


def weekly(db,as_of=None):
    end=date.fromisoformat(as_of) if as_of else datetime.now(timezone.utc).date()
    start=end-timedelta(days=end.weekday())
    first_stamp=int(datetime(start.year,start.month,start.day,tzinfo=timezone.utc).timestamp())
    stop_stamp=first_stamp+((end-start).days+1)*86400
    rows=[]
    for cohort in ("demo","imported"):
        days=dict(db.execute("""SELECT owner,COUNT(*) FROM research_days WHERE day BETWEEN ? AND ? AND cohort=?
                                GROUP BY owner""",(start.isoformat(),end.isoformat(),cohort)))
        first=db.execute("""SELECT owner,MIN(finished) FROM research_runs WHERE finished<?
            AND (source='demo')=? GROUP BY owner""",(stop_stamp,cohort=="demo"))
        completed=sum(stamp>=first_stamp for owner,stamp in first if owner in days)
        repeat=sum(n>=2 for n in days.values())
        new_starts,within_five=db.execute("""WITH first_visits AS (
            SELECT owner,MIN(started) AS first_start,
                   MIN(CASE WHEN finished < ? THEN finished END) AS first_finish
            FROM research_runs WHERE (source='demo')=? AND started<? GROUP BY owner
        ) SELECT COUNT(*),COUNT(CASE WHEN first_finish-first_start BETWEEN 0 AND 300 THEN 1 END)
          FROM first_visits WHERE first_start>=? AND first_start<?""",
          (stop_stamp+300,cohort=="demo",stop_stamp+300,first_stamp,stop_stamp)).fetchone()
        def share(n):
            return round(n/len(days)*100,2) if days else None
        rows.append({"cohort":cohort,"active":len(days),"first_completed":completed,"first_completed_pct":share(completed),
                     "repeat_days":repeat,"repeat_pct":share(repeat),"first_starts":new_starts,
                     "within_300s":within_five,"within_300s_pct":round(100*within_five/new_starts,2) if new_starts else None})
    return {"start":start.isoformat(),"end":end.isoformat(),"items":rows}
