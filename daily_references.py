"""Discover public product videos and cache daily editions for the demo source."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from html import unescape
from http.client import HTTPException
import json
import re
from threading import Lock, BoundedSemaphore
from time import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import analytics

TARGET = 12
_locks = [Lock() for _ in range(64)]
_network = BoundedSemaphore(8)
# Extra search phrases for familiar names. Every other product still gets a direct search.
ALIASES = (
    (r'通勤包|单肩包|托特包|shoulder bag|canvas tote', 'shoulder bag', ('work bag', 'shoulder bag', 'tote bag', 'commuter bag')),
    (r'台灯|阅读灯|desk lamp|reading light', 'desk lamp', ('desk lamp', 'reading light', 'table lamp')),
    (r'保温杯|水杯|水瓶|vacuum bottle|sport flask', 'water bottle', ('water bottle', 'vacuum bottle', 'insulated bottle')),
    (r'耳机|headphones?|headsets?|earbuds?', 'headphones', ('headphones', 'headset', 'earbuds', 'earphones')),
    (r'保湿精华|山茶.*精华|hydrating serum|night serum', 'face serum', ('face serum', 'facial serum', 'skin serum', 'hydrating serum')),
    (r'唇油|lip oil|lip glaze', 'lip oil', ('lip oil', 'lip glaze')),
    (r'手账|便签本|planner', 'weekly planner', ('weekly planner', 'daily planner', 'bullet journal')),
    (r'弹力带|resistance set', 'resistance band', ('resistance band',)),
    (r'手机支架|phone stand', 'phone stand', ('phone stand', 'phone holder')),
    (r'马克杯|ceramic cup', 'coffee mug', ('coffee mug', 'ceramic mug', 'ceramic cup')),
)
CJK = re.compile(r'[\u3400-\u9fff]')
FORMAT = re.compile(r'\b(review|unboxing|demo|test|tutorial|setup|comparison|versus|vs|hands.on|how to)\b|实测|开箱|测评|对比|教程', re.I)
PRODUCT_CONTEXT = re.compile(r"\b(best|trying|try on|first look|how|haul|routine|essentials|features|tips|styling|tested|displays?|fits?|overview|what.s in|what i carry|using|my favou?rite)\b|好物|分享|体验|收纳|怎么用", re.I)


def init(db):
    db.execute("""CREATE TABLE IF NOT EXISTS demo_inspiration_editions (
        scope TEXT NOT NULL, day TEXT NOT NULL, checked INTEGER NOT NULL, payload TEXT NOT NULL,
        PRIMARY KEY(scope,day))""")
    # Legacy scope hashes do not identify which cached searches belong to a
    # commercial source. All of these entries can be regenerated.
    db.execute("DROP TABLE IF EXISTS inspiration_editions")


def get_json(url, params):
    request = Request(url + '?' + urlencode(params), headers={'Accept': 'application/json', 'User-Agent': 'TikFlowSo/1.0'})
    with _network, urlopen(request, timeout=5) as response:
        return json.loads(response.read(2_000_000))


def normalized(text):
    return ' '.join(re.findall(r'[^\W_]+', unescape(text).casefold()))


def mentions(title, phrase):
    if CJK.search(phrase):
        return phrase in title
    words = normalized(phrase).split()
    return bool(words) and re.search(r'\b' + r'\s+'.join(map(re.escape, words)) + r'(?:s|es)?\b', title) is not None


def lookup(subject):
    """Match titles to product terms independently of the provider's fuzzy ranking."""
    try:
        return discover_subject(subject)
    except (HTTPException, OSError, ValueError, KeyError, TypeError):
        return [], True


def discover_subject(subject):
    alias = next(((term, phrases) for pattern, term, phrases in ALIASES
                  if re.search(f'(?:{pattern})s?$', subject, re.I)), None)
    terms = [subject]
    phrases = [normalized(subject)]
    failed = False
    if alias:
        terms.append(alias[0])
        phrases.extend(alias[1])
    elif CJK.search(subject) and len(subject.encode()) <= 500:
        try:
            result = get_json('https://api.mymemory.translated.net/get', {'q': subject, 'langpair': 'zh-CN|en'})
            translation = unescape(result['responseData']['translatedText']).strip()
            if str(result['responseStatus']) == '200' and 1 < len(translation) <= 180:
                terms.append(translation)
                phrases.append(normalized(translation))
            else:
                failed = True
        except (HTTPException, OSError, ValueError, KeyError, TypeError):
            failed = True
    words = normalized(terms[-1]).split()
    if (not alias and len(words) > 2 and not {'with', 'for', 'and', 'of', 'compatible'}.intersection(words)
            and all(re.fullmatch('[a-z]{3,}', w) for w in words[-2:])
            and words[-1] not in {'edition', 'version', 'pack', 'black', 'white', 'inch', 'set', 'kit'}):
        category = ' '.join(words[-2:])
        terms.append(category)
        phrases.append(category)
    queries = [(terms[0], 'relevance'), (terms[-1] + ' review', 'relevance'),
               (terms[-1] + ' unboxing', 'relevance'), (terms[-1], 'recent')]
    model_terms = [normalized(w) for w in re.findall(r'[A-Za-z][A-Za-z0-9-]{3,}', subject)
                   if re.search(r'[0-9]', w) and re.search(r'[A-Za-z].*[A-Za-z]', w)]
    if model_terms:
        queries.insert(1, (' '.join(model_terms) + ' review', 'relevance'))
        phrases.extend(model_terms)
    if len(terms) > 2:
        queries.insert(1, (terms[1], 'relevance'))
    if alias:
        alternate = next((p for p in reversed(alias[1]) if p != alias[0]), None)
        if alternate:
            queries.append((alternate + ' review', 'relevance'))
    videos = []
    consecutive_errors = 0
    for query, order in dict.fromkeys(queries):
        try:
            result = get_json('https://api.dailymotion.com/videos', {'search': query, 'fields': 'id,title,owner.screenname,created_time,duration',
                              'sort': order, 'family_filter': '1', 'limit': 60})
            consecutive_errors = 0
            for rank, row in enumerate(result['list']):
                vid = row.get('id', '')
                title = unescape(row.get('title') or '').strip()
                clean = normalized(title)
                if not re.fullmatch(r'[A-Za-z0-9]+', vid) or not title or not any(mentions(clean, p) for p in phrases if p):
                    continue
                if not (FORMAT.search(title) or PRODUCT_CONTEXT.search(title)):
                    continue
                if not row.get('duration') or not row.get('created_time'):
                    continue
                published = datetime.fromtimestamp(row['created_time'], timezone.utc).date().isoformat()
                direct = mentions(clean, phrases[0]) or any(mentions(clean, m) for m in model_terms)
                score = 35 * direct + 18 * bool(FORMAT.search(title)) + 12 / (1 + rank / 8)
                videos.append({'url': 'https://www.dailymotion.com/video/' + vid, 'title': title,
                               'author': row.get('owner.screenname') or '', 'platform': 'Dailymotion',
                               'published': published, 'subject': subject, 'match': 'name' if direct else 'related', 'score': score})
        except (HTTPException, OSError, ValueError, KeyError, TypeError):
            failed = True
            consecutive_errors += 1
            if consecutive_errors >= 2:
                break
    return videos, failed


def select(candidates, previous):
    ranked = sorted(candidates, key=lambda v: (v['url'] not in previous, v['score'], v['published']), reverse=True)
    urls, titles, selected = set(), set(), []
    for row in ranked:
        title = normalized(row['title'])
        if row['url'] in urls or title in titles:
            continue
        selected.append({key: value for key, value in row.items() if key != 'score'})
        urls.add(row['url'])
        titles.add(title)
        if len(selected) == TARGET:
            break
    return selected


def edition(db, params, now=None):
    now = now or datetime.now(timezone.utc)
    try:
        day = now.astimezone(ZoneInfo(params.get('tz') or 'UTC')).date()
    except (ZoneInfoNotFoundError, ValueError):
        raise ValueError('时区无效') from None
    subject = ' '.join(params.get('subject', '').split())
    if len(subject) > 1500:
        raise ValueError('商品名称过长')
    scope = analytics.scope_for(db, params)
    if scope['source'] != 'demo':
        if params.get('external_search') != '1' or not subject:
            return {'day': day.isoformat(), 'target': TARGET, 'items': [], 'incomplete_search': False,
                    'external_search_enabled': False}
        # Only the single, explicitly submitted term goes to the provider. The
        # response stays with this request and writes no workspace data to the cache.
        db.commit()
        candidates, failed = lookup(subject)
        items = select(candidates, set())
        return {'day': day.isoformat(), 'target': TARGET, 'items': items,
                'incomplete_search': failed and len(items) < TARGET}
    names = [subject] if subject else list(dict.fromkeys(
        ' '.join(p['name'].split()) for p in analytics.ranking_page(db, scope, {'kind': 'products', 'limit': 1000})['items'] if p['name'].strip()))
    key = sha256(json.dumps([scope['source'], scope['market'], names], ensure_ascii=False).encode()).hexdigest()
    db.commit()  # Release the request's session transaction before waiting for a provider or another reader.
    with _locks[int(key[:2], 16) % len(_locks)]:
        stored = db.execute('SELECT checked,payload FROM demo_inspiration_editions WHERE scope=? AND day=?', (key, day.isoformat())).fetchone()
        prior_today = None
        if stored:
            prior_today = json.loads(stored[1])
            if not prior_today['incomplete_search'] or stored[0] > time() - 300:
                return prior_today
        history = db.execute('SELECT payload FROM demo_inspiration_editions WHERE scope=? AND day BETWEEN ? AND ?', (
            key, (day - timedelta(days=7)).isoformat(), (day - timedelta(days=1)).isoformat()))
        previous = {v['url'] for (payload,) in history for v in json.loads(payload)['items']}
        candidates = []
        failed = False
        # Keep the leaders in view and rotate the next products through the ranked catalog.
        if not subject and len(names) > 6:
            rest = names[2:]
            start = (day.toordinal() * 4) % len(rest)
            names = names[:2] + rest[start:] + rest[:start]
        # Bound discovery on a single page load even when a large catalog has scarce matches.
        names = names[:24]
        for start in range(0, len(names), 6):
            batch = names[start:start + 6]
            with ThreadPoolExecutor(max_workers=len(batch)) as pool:
                searches = list(pool.map(lookup, batch))
                for rows, missed in searches:
                    candidates.extend(rows)
                    failed |= missed
            if all(not rows and missed for rows, missed in searches) or len(select(candidates, previous)) >= TARGET:
                break
        if prior_today:
            candidates.extend({**row, 'score': 0} for row in prior_today['items'])
        items = select(candidates, previous)
        payload = {'day': day.isoformat(), 'target': TARGET, 'items': items,
                   'incomplete_search': failed and len(items) < TARGET}
        db.execute('DELETE FROM demo_inspiration_editions WHERE day < ?', ((day - timedelta(days=9)).isoformat(),))
        db.execute('INSERT OR REPLACE INTO demo_inspiration_editions VALUES (?,?,?,?)',
                   (key, day.isoformat(), int(time()), json.dumps(payload, ensure_ascii=False)))
        db.commit()
        return payload
