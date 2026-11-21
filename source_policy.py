"""Explicit publication policy for operator and workspace data sources."""
import re

SCHEMA = """
CREATE TABLE IF NOT EXISTS erased_workspaces(uid INTEGER PRIMARY KEY);
CREATE TABLE IF NOT EXISTS source_policy(
 source TEXT PRIMARY KEY, visibility TEXT NOT NULL CHECK(visibility IN ('held','private','shared')),
 owner INTEGER, CHECK((visibility='private' AND owner IS NOT NULL AND owner>0)
                   OR (visibility IN ('held','shared') AND owner IS NULL)));
CREATE INDEX IF NOT EXISTS sources_by_owner ON source_policy(owner,visibility);
"""
VISIBLE = "SELECT source FROM source_policy WHERE visibility='shared' OR (visibility='private' AND owner=?)"


def intent(source, owner=None, shared=False):
    if type(shared) is not bool or (owner is not None and (type(owner) is not int or owner <= 0 or owner > 2**63-1)):
        raise ValueError("来源可见范围无效")
    legacy = re.fullmatch(r"ws-([1-9][0-9]{0,17})-.+", source)
    if legacy:
        expected = int(legacy[1])
        if shared or owner not in (None, expected):
            raise ValueError("来源名称与工作区授权不一致")
    if source == "demo":
        return "shared", None
    if shared and owner is not None:
        raise ValueError("共享来源不可同时指定工作区")
    return ("shared", None) if shared else (("private", owner) if owner else ("held", None))


def known_owner(db, owner):
    return (db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='users'").fetchone()
            and db.execute("SELECT 1 FROM users WHERE id=? AND email IS NOT NULL AND owner IS NULL",(owner,)).fetchone())


def register(db, source, owner=None, shared=False):
    previous=db.execute("SELECT visibility,owner FROM source_policy WHERE source=?",(source,)).fetchone()
    if owner is None and not shared and previous and previous[0]=='private' and source.startswith(f'ws-{previous[1]}-'):
        owner=previous[1]
    visibility, owner = intent(source, owner, shared)
    if owner and not known_owner(db,owner): raise ValueError("请指定已注册的工作区所有者")
    if owner and db.execute("SELECT 1 FROM erased_workspaces WHERE uid=?",(owner,)).fetchone():
        raise ValueError("工作区已注销，请停用对应的供数配置")
    db.execute("INSERT OR IGNORE INTO source_policy VALUES(?,?,?)", (source, visibility, owner))
    existing = db.execute("SELECT visibility,owner FROM source_policy WHERE source=?", (source,)).fetchone()
    if tuple(existing) != (visibility, owner):
        raise ValueError("来源授权与已有设置不一致，请由部署管理员核对")


def migrate(db):
    for (source,) in db.execute("SELECT id FROM analytics_sources WHERE id NOT IN (SELECT source FROM source_policy)").fetchall():
        legacy=re.fullmatch(r"ws-([1-9][0-9]{0,17})-.+",source)
        owner=int(legacy[1]) if legacy else None
        register(db,source,owner if owner and known_owner(db,owner) else None)


def visible(db, owner, source):
    return bool(db.execute("SELECT 1 FROM (" + VISIBLE + ") WHERE source=?", (owner, source)).fetchone())


def set_access(db, source, owner=None, shared=False):
    if source == "demo" or not db.execute("SELECT 1 FROM analytics_sources WHERE id=?", (source,)).fetchone():
        raise ValueError("请选择现有的商业来源")
    if owner is not None and not db.execute("SELECT 1 FROM users WHERE id=? AND email IS NOT NULL AND owner IS NULL", (owner,)).fetchone():
        raise ValueError("工作区所有者不存在")
    visibility, owner = intent(source,owner,shared) if (owner is not None or shared) else ("held",None)
    db.execute("""INSERT INTO source_policy VALUES(?,?,?) ON CONFLICT(source) DO UPDATE
                  SET visibility=excluded.visibility,owner=excluded.owner""", (source,visibility,owner))

