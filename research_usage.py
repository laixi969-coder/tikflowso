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
    cohort="demo" if scope["source"]=="demo" else "imported"
    key=(owner,scope["source"],scope["market"],scope["date"],scope["days"],day)
    condition="owner=? AND source=? AND market=? AND cutoff=? AND days=? AND day=?"
    if action in ("list","detail"):
        db.execute("INSERT OR IGNORE INTO research_days VALUES(?,?,?)",(owner,cohort,day))
    if action=="list":
        db.execute("INSERT OR IGNORE INTO research_runs VALUES(?,?,?,?,?,?,?,NULL)",(*key,stamp))
    elif action=="detail":
        db.execute(f"""INSERT OR IGNORE INTO research_details SELECT ?,?,?,?,?,?,?
            WHERE EXISTS(SELECT 1 FROM research_runs WHERE {condition})""",(*key,item,*key))
    else:
        same_item=" AND item=?" if action=="save" else ""
        args=(*key,item) if same_item else key
        db.execute(f"""UPDATE research_runs SET finished=? WHERE {condition} AND finished IS NULL
            AND EXISTS(SELECT 1 FROM research_details WHERE {condition}{same_item})""",(stamp,*key,*args))


def weekly(db,as_of=None):
    end=date.fromisoformat(as_of) if as_of else datetime.now(timezone.utc).date()
    start=end-timedelta(days=end.weekday())
    rows=[]
    for cohort in ("demo","imported"):
        days=dict(db.execute("""SELECT owner,COUNT(*) FROM research_days WHERE day BETWEEN ? AND ? AND cohort=?
                                GROUP BY owner""",(start.isoformat(),end.isoformat(),cohort)))
        first=db.execute("""SELECT owner,MIN(day) FROM research_runs WHERE finished IS NOT NULL
            AND (source='demo')=? AND day<=? GROUP BY owner""",(cohort=="demo",end.isoformat()))
        completed=sum(day>=start.isoformat() for owner,day in first if owner in days)
        repeat=sum(n>=2 for n in days.values())
        def share(n):
            return round(n/len(days)*100,2) if days else None
        rows.append({"cohort":cohort,"active":len(days),"first_completed":completed,"first_completed_pct":share(completed),
                     "repeat_days":repeat,"repeat_pct":share(repeat)})
    return {"start":start.isoformat(),"end":end.isoformat(),"items":rows}
