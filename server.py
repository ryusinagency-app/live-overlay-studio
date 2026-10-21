from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from datetime import datetime, timezone, timedelta
import copy
import json
import os
import threading
import time
import unicodedata
import webbrowser
import base64
import re
import random
import queue
import shutil
import sys
import subprocess
import hashlib
import tempfile
import urllib.request

APP_VERSION = '0.65.15'
SOURCE_ROOT = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent))
FROZEN_APP = bool(getattr(sys, 'frozen', False))

def prepare_app_root():
    if not FROZEN_APP:
        return Path(__file__).resolve().parent
    local_base = Path(os.environ.get('LOCALAPPDATA') or Path.home())
    app_root = local_base / 'LiveOverlayStudio'
    app_root.mkdir(parents=True, exist_ok=True)
    assets = [
        'control.html', 'overlay.html', 'overlay_comp.html',
        'overlay_counters.html', 'overlay_gacha.html',
        'overlay_gacha_history.html', 'overlay_gift_history.html',
        'overlay_missions.html', 'overlay_smoking.html',
        'overlay_smoking_gacha.html', 'overlay_timer.html',
        'overlay_win.html', 'README.txt', 'update_config.json'
    ]
    for name in assets:
        source = SOURCE_ROOT / name
        target = app_root / name
        if source.exists():
            shutil.copy2(source, target)

    # An existing portable-folder state is imported only on the first launch.
    # This lets the owner move from the ZIP version to the EXE without losing data.
    executable_root = Path(sys.executable).resolve().parent
    old_state = executable_root / 'state.json'
    if not (app_root / 'state.json').exists() and old_state.exists():
        shutil.copy2(old_state, app_root / 'state.json')
        media_prefixes = ('smoking_alarm.', 'gacha_', 'smoking_gacha_', 'win_counter_image.')
        for item in executable_root.iterdir():
            if item.is_file() and item.name.startswith(media_prefixes):
                shutil.copy2(item, app_root / item.name)
    return app_root

ROOT = prepare_app_root()
if FROZEN_APP and os.name == 'nt':
    # Keep the running app in a user-writable location so self-updates work
    # even when the original download lives in Downloads or Program Files.
    managed_exe = ROOT / 'Live Overlay Studio.exe'
    current_exe = Path(sys.executable).resolve()
    if current_exe != managed_exe.resolve():
        if not managed_exe.exists():
            shutil.copy2(current_exe, managed_exe)
        subprocess.Popen([str(managed_exe)], cwd=str(ROOT), close_fds=True)
        raise SystemExit(0)
STATE = ROOT / 'state.json'
STATE_LOCK = threading.Lock()
JST = timezone(timedelta(hours=9))
DEFAULT = {
    'cardDefaults': {'background': '', 'border': ''},
    'compCardBg': '',
    'compCardBorder': '',
    'compCardTextColor': '',
    'compCardOpacity': -1,
    'compCardWidth': 0,
    'compCardHeight': 0,
    'compFontFamily': 'global',
    'compTextScale': 100,
    'counters': [
        {'id': 'counter-1', 'label': 'ギフト補填', 'value': 0, 'goal': 40, 'showGoal': True, 'textScale': 100, 'shortcutAdd': 'CTRL+ALT+1', 'shortcutSub': 'CTRL+ALT+SHIFT+1'},
        {'id': 'counter-2', 'label': 'いいね補填', 'value': 0, 'goal': 40, 'showGoal': True, 'textScale': 100, 'shortcutAdd': 'CTRL+ALT+2', 'shortcutSub': 'CTRL+ALT+SHIFT+2'},
        {'id': 'counter-3', 'label': 'WIN', 'value': 0, 'goal': 40, 'showGoal': True, 'textScale': 100, 'shortcutAdd': 'CTRL+ALT+3', 'shortcutSub': 'CTRL+ALT+SHIFT+3'},
    ],
    # ``memos`` replaces the former single compensation card.  The legacy
    # fields remain in saved data for migration compatibility.
    'memos': [
        {'id': 'memo-1', 'title': 'メモ', 'text': 'ここにメモを入力', 'show': True},
    ],
    'compTitle': 'メモ',
    'compText': 'ここにメモを入力',
    'showComp': True,
    'accent': '#e52b3c',
    'gaugeColor': '#e52b3c',
    'panelColor': '#17181e',
    'panelOpacity': 88,
    'textColor': '#ffffff',
    'fontFamily': 'system',
    'textScale': 100,
    'textGlowEnabled': False,
    'textGlowColor': '#e52b3c',
    'textGlowStrength': 12,
    'textOutlineEnabled': False,
    'textOutlineColor': '#000000',
    'textOutlineWidth': 2,
    'textBackgroundEnabled': False,
    'textBackgroundColor': '#000000',
    'textBackgroundOpacity': 55,
    # Per-card overrides. Missing keys and ``mode: global`` intentionally use
    # the common settings above so existing saved data keeps the same look.
    'textEffects': {},
    'missions': [
        {'id': 'mission-1', 'title': 'ギフトミッション', 'giftValue': 0, 'giftGoal': 10, 'unit': '個', 'achievements': 0, 'dailyLimit': 10, 'lastDate': '', 'showAchievements': True, 'noticeUntil': 0, 'textScale': 100, 'shortcutAdd': 'CTRL+ALT+0', 'shortcutSub': 'CTRL+ALT+SHIFT+0'}
    ],
    'giftRules': [],
    'giftWall': {'minCoins':100, 'columns':4, 'rows':2, 'pageSeconds':8, 'history':[], 'displayHistory':[], 'fontFamily':'global', 'textScale':100, 'avatarSize':44, 'nameSize':18, 'giftNameSize':16, 'countSize':15, 'giftImageSize':44, 'cardBg':'#1c1c24', 'cardBorder':'#ffcf59', 'cardTextColor':'#ffffff', 'cardOpacity':93, 'nextId':1},
    'tiktokUsername': '',
    'timer': {'endAt': 0, 'seconds': 0, 'giftName': '', 'defaultText': 'カウント：0秒', 'currentText': ''},
    'winCounter': {'title': '現在', 'currentWin': 0, 'goalWin': 10, 'shortcutAdd': 'CTRL+ALT+7', 'shortcutSub': 'CTRL+ALT+SHIFT+7', 'giftRules': [], 'positiveTextColor': '', 'negativeTextColor': '#ff4055', 'goalTextColor': '', 'titleSize': 30, 'valueSize': 76, 'imageUrl': '', 'imageName': '', 'imageSize': 64, 'imageEnabled': True},
    'gacha': {'mode':'continue', 'continuationRate':70, 'spinSeconds':5, 'soundVolume':65, 'shortcutChoicePlus':'CTRL+ALT+8', 'shortcutChoiceMinus':'CTRL+ALT+9', 'patterns':[{'id':'gacha-pattern-1','name':'WINガチャ','giftName':'','minWin':1,'maxWin':10,'outcomeMode':'range','outcomes':[]}], 'animationUrl':'', 'animationName':'', 'audioUrl':'', 'audioName':'', 'audioVolume':75, 'resultAudioUrl':'', 'resultAudioName':'', 'resultAudioVolume':80, 'effectStyle':'card', 'slotNumberSize':130, 'slotNumberColor':'#ffffff', 'slotX':50, 'slotY':50, 'spinStyle':'dramatic', 'videoAudioEnabled':True, 'videoVolume':75, 'endAnimationUrl':'', 'endAnimationName':'', 'endAudioUrl':'', 'endAudioName':'', 'endAudioVolume':75, 'endSeconds':6, 'queue':[], 'event':{'id':0,'type':'','active':False,'patternName':'','rounds':[],'total':0,'giftName':'','senderName':'','createdAt':0}},
    'smokingTimer': {'endAt': 0, 'remainingSeconds': 0, 'runId': 0, 'audioUrl': '', 'audioName': '', 'volume': 80, 'fontSize': 130, 'titleSize': 56, 'cardBg': '', 'cardBorder': '', 'shortcutAdd5':'', 'shortcutSub5':'', 'shortcutAdd10':'', 'shortcutSub10':'', 'shortcutAdd15':'', 'shortcutSub15':'', 'shortcutAdd30':'', 'shortcutSub30':''},
    'smokingGacha': {'fontFamily':'global', 'patterns': [], 'event': {'id':0,'type':'','active':False,'patternName':'','minutes':0,'senderName':'','choice':'','choiceReady':False,'createdAt':0}, 'queue': [], 'animationUrl':'', 'animationName':'', 'audioUrl':'', 'audioName':'', 'audioVolume':75, 'resultAudioUrl':'', 'resultAudioName':'', 'resultAudioVolume':80, 'effectStyle':'fullscreen-slot', 'spinSeconds':7, 'endSeconds':6, 'slotNumberSize':130, 'slotNumberColor':'#ffffff', 'slotX':50, 'slotY':50, 'spinStyle':'dramatic', 'shortcutPlus':'CTRL+ALT+5', 'shortcutMinus':'CTRL+ALT+SHIFT+5'},
}
TIKTOK_STATUS = {'status': 'stopped', 'message': '未接続', 'username': ''}
TIKTOK_STATUS_LOCK = threading.Lock()
TIKTOK_LISTENER_LOCK = threading.Lock()
TIKTOK_LISTENER_THREAD = None
TIKTOK_LISTENER_USERNAME = ''
TIKTOK_GIFT_ENABLED = False
TIKTOK_GIFT_CATALOG = []
TIKTOK_GIFT_CATALOG_LOCK = threading.Lock()
SERVER_STARTED_AT = time.time()
HOTKEY_STATUS = {'active': False, 'message': 'ショートカット監視を起動しています', 'bindings': 0}
HOTKEY_STATUS_LOCK = threading.Lock()

def _gift_value(value, *names):
    for name in names:
        if isinstance(value, dict) and value.get(name) is not None:
            return value.get(name)
        result = getattr(value, name, None)
        if result is not None:
            return result
    return None

def _gift_image_url(value):
    image = _gift_value(value, 'image', 'gift_image', 'giftImage', 'icon')
    for item in (image, value):
        if not item:
            continue
        direct = _gift_value(item, 'url', 'uri')
        if isinstance(direct, str) and direct.startswith(('http://', 'https://')):
            return direct
        urls = _gift_value(item, 'url_list', 'urlList', 'urls')
        if isinstance(urls, (list, tuple)):
            for url in urls:
                if isinstance(url, str) and url.startswith(('http://', 'https://')):
                    return url
    return ''

def normalize_gift_catalog(raw):
    if isinstance(raw, dict):
        values = list(raw.values())
    elif isinstance(raw, (list, tuple, set)):
        values = list(raw)
    else:
        values = list(_gift_value(raw, 'gifts', 'gift_list', 'giftList') or [])
    result = {}
    for item in values:
        name = str(_gift_value(item, 'name', 'gift_name', 'giftName') or '').strip()
        if not name:
            continue
        raw_price = _gift_value(item, 'diamond_count', 'diamondCount', 'price', 'coin_count', 'coinCount')
        try:
            price = max(0, int(raw_price or 0))
        except (TypeError, ValueError):
            price = 0
        result[normalize_gift_name(name)] = {'name': name, 'price': price, 'imageUrl': _gift_image_url(item)}
    return sorted(result.values(), key=lambda gift: (gift['price'], gift['name'].casefold()))

def update_gift_catalog(raw):
    gifts = normalize_gift_catalog(raw)
    if gifts:
        with TIKTOK_GIFT_CATALOG_LOCK:
            TIKTOK_GIFT_CATALOG[:] = gifts
    return gifts

def remember_gift(gift):
    gifts = normalize_gift_catalog([gift])
    if not gifts:
        return
    with TIKTOK_GIFT_CATALOG_LOCK:
        merged = {normalize_gift_name(item['name']): item for item in TIKTOK_GIFT_CATALOG}
        merged[normalize_gift_name(gifts[0]['name'])] = gifts[0]
        TIKTOK_GIFT_CATALOG[:] = sorted(merged.values(), key=lambda item: (item['price'], item['name'].casefold()))

def today_jst():
    return datetime.now(JST).date().isoformat()

def safe_int(value, default=0):
    """Convert legacy form values without breaking the whole local server."""
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        try:
            return int(float(value))
        except (TypeError, ValueError, OverflowError):
            return default

def safe_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError, OverflowError):
        return default

def normalize_state(data):
    data = data if isinstance(data, dict) else {}
    merged = {**copy.deepcopy(DEFAULT), **data}
    changed = False
    raw_card_defaults = merged.get('cardDefaults') if isinstance(merged.get('cardDefaults'), dict) else {}
    valid_hex = lambda value: str(value or '').lower() if re.fullmatch(r'#[0-9a-fA-F]{6}', str(value or '')) else ''
    merged['cardDefaults'] = {'background': valid_hex(raw_card_defaults.get('background')), 'border': valid_hex(raw_card_defaults.get('border'))}
    merged['compCardBg'] = valid_hex(merged.get('compCardBg'))
    merged['compCardBorder'] = valid_hex(merged.get('compCardBorder'))
    merged['compCardTextColor'] = valid_hex(merged.get('compCardTextColor'))
    merged['compFontFamily'] = merged.get('compFontFamily') if merged.get('compFontFamily') in ('global','system','yuGothic','meiryo','gothic','serif','mono') else 'global'
    merged['compTextScale'] = max(50, min(250, safe_int(merged.get('compTextScale', 100), 100)))
    merged['compCardOpacity'] = max(-1, min(100, safe_int(merged.get('compCardOpacity', -1))))
    merged['compCardWidth'] = max(0, min(2000, safe_int(merged.get('compCardWidth') or 0)))
    merged['compCardHeight'] = max(0, min(1200, safe_int(merged.get('compCardHeight') or 0)))
    raw_memos = data.get('memos')
    if not isinstance(raw_memos, list):
        raw_memos = [{
            'id': 'memo-1',
            'title': str(data.get('compTitle') or 'メモ'),
            'text': str(data.get('compText') or ''),
            'show': data.get('showComp', True) is not False,
        }]
        changed = True
    memos = []
    for index, entry in enumerate(raw_memos):
        entry = entry if isinstance(entry, dict) else {}
        memo = {
            'id': str(entry.get('id') or f'memo-{index + 1}'),
            'title': str(entry.get('title') or 'メモ')[:120],
            'text': str(entry.get('text') or '')[:10000],
            'show': entry.get('show', True) is not False,
        }
        memos.append(memo)
        if memo != entry:
            changed = True
    merged['memos'] = memos
    merged['fontFamily'] = merged.get('fontFamily') if merged.get('fontFamily') in ('system','yuGothic','meiryo','gothic','serif','mono') else 'system'
    merged['textGlowEnabled'] = bool(merged.get('textGlowEnabled', False))
    merged['textGlowColor'] = valid_hex(merged.get('textGlowColor')) or '#e52b3c'
    merged['textGlowStrength'] = max(0, min(40, safe_int(merged.get('textGlowStrength', 12))))
    merged['textOutlineEnabled'] = bool(merged.get('textOutlineEnabled', False))
    merged['textOutlineColor'] = valid_hex(merged.get('textOutlineColor')) or '#000000'
    merged['textOutlineWidth'] = max(0, min(10, safe_int(merged.get('textOutlineWidth', 2), 2)))
    merged['textBackgroundEnabled'] = bool(merged.get('textBackgroundEnabled', False))
    merged['textBackgroundColor'] = valid_hex(merged.get('textBackgroundColor')) or '#000000'
    merged['textBackgroundOpacity'] = max(0, min(100, safe_int(merged.get('textBackgroundOpacity', 55), 55)))
    raw_text_effects = merged.get('textEffects') if isinstance(merged.get('textEffects'), dict) else {}
    text_effects = {}
    for raw_key, raw_effect in raw_text_effects.items():
        if not isinstance(raw_effect, dict):
            continue
        key = str(raw_key)[:160]
        if not key:
            continue
        text_effects[key] = {
            'mode': 'custom' if raw_effect.get('mode') == 'custom' else 'global',
            'outlineEnabled': bool(raw_effect.get('outlineEnabled', False)),
            'outlineColor': valid_hex(raw_effect.get('outlineColor')) or '#000000',
            'outlineWidth': max(0, min(10, safe_int(raw_effect.get('outlineWidth', 2), 2))),
            'backgroundEnabled': bool(raw_effect.get('backgroundEnabled', False)),
            'backgroundColor': valid_hex(raw_effect.get('backgroundColor')) or '#000000',
            'backgroundOpacity': max(0, min(100, safe_int(raw_effect.get('backgroundOpacity', 55), 55))),
        }
    merged['textEffects'] = text_effects

    counters = []
    for index, entry in enumerate(merged.get('counters') or []):
        entry = entry if isinstance(entry, dict) else {}
        counter = {'goal': 40, 'showGoal': True, **entry}
        counter.setdefault('id', f'counter-{index+1}')
        counter.setdefault('shortcutAdd', f'CTRL+ALT+{index+1}' if index < 9 else '')
        counter.setdefault('shortcutSub', f'CTRL+ALT+SHIFT+{index+1}' if index < 9 else '')
        counter['id'] = str(counter['id'] or f'counter-{index+1}')
        counter['value'] = max(0, safe_int(counter.get('value') or 0))
        counter['goal'] = max(0, safe_int(counter.get('goal') or 0))
        counter['cardWidth'] = max(0, min(2000, safe_int(counter.get('cardWidth') or 0)))
        counter['cardHeight'] = max(0, min(1200, safe_int(counter.get('cardHeight') or 0)))
        counter['cardBg'] = valid_hex(counter.get('cardBg'))
        counter['cardBorder'] = valid_hex(counter.get('cardBorder'))
        counter['cardTextColor'] = valid_hex(counter.get('cardTextColor'))
        counter['fontFamily'] = counter.get('fontFamily') if counter.get('fontFamily') in ('global','system','yuGothic','meiryo','gothic','serif','mono') else 'global'
        counter['textScale'] = max(50, min(250, safe_int(counter.get('textScale', 100), 100)))
        counter['cardOpacity'] = max(-1, min(100, safe_int(counter.get('cardOpacity', -1))))
        counter['shortcutAdd'] = str(counter.get('shortcutAdd') or '').upper()
        counter['shortcutSub'] = str(counter.get('shortcutSub') or '').upper()
        if counter != entry:
            changed = True
        counters.append(counter)
    merged['counters'] = counters

    raw_missions = data.get('missions')
    if raw_missions is None:
        legacy = data.get('mission')
        if legacy:
            raw_missions = [legacy]
            changed = True
        else:
            raw_missions = copy.deepcopy(DEFAULT['missions'])
    missions = []
    today = today_jst()
    for index, entry in enumerate(raw_missions or []):
        entry = entry if isinstance(entry, dict) else {}
        mission = {**DEFAULT['missions'][0], **entry}
        mission['id'] = str(mission.get('id') or f'mission-{index+1}')
        mission['title'] = str(mission.get('title') or f'ミッション{index+1}')
        mission['unit'] = str(mission.get('unit') or '個')
        if 'shortcutAdd' not in entry:
            old_key = str(entry.get('hotkey') or '').upper()
            mission['shortcutAdd'] = f'CTRL+ALT+{old_key}' if old_key else ('CTRL+ALT+0' if index == 0 else f'CTRL+ALT+F{min(index+1,12)}')
        if 'shortcutSub' not in entry:
            old_key = str(entry.get('hotkey') or '').upper()
            mission['shortcutSub'] = f'CTRL+ALT+SHIFT+{old_key}' if old_key else ('CTRL+ALT+SHIFT+0' if index == 0 else f'CTRL+ALT+SHIFT+F{min(index+1,12)}')
        mission['shortcutAdd'] = str(mission.get('shortcutAdd') or '').upper()
        mission['shortcutSub'] = str(mission.get('shortcutSub') or '').upper()
        mission['giftGoal'] = max(1, safe_int(mission.get('giftGoal') or 1))
        mission['cardWidth'] = max(0, min(2000, safe_int(mission.get('cardWidth') or 0)))
        mission['cardHeight'] = max(0, min(1200, safe_int(mission.get('cardHeight') or 0)))
        mission['cardBg'] = valid_hex(mission.get('cardBg'))
        mission['cardBorder'] = valid_hex(mission.get('cardBorder'))
        mission['cardTextColor'] = valid_hex(mission.get('cardTextColor'))
        mission['fontFamily'] = mission.get('fontFamily') if mission.get('fontFamily') in ('global','system','yuGothic','meiryo','gothic','serif','mono') else 'global'
        mission['textScale'] = max(50, min(250, safe_int(mission.get('textScale', 100), 100)))
        mission['cardOpacity'] = max(-1, min(100, safe_int(mission.get('cardOpacity', -1))))
        mission['dailyLimit'] = max(1, safe_int(mission.get('dailyLimit') or 10))
        mission['giftValue'] = max(0, safe_int(mission.get('giftValue') or 0))
        mission['achievements'] = max(0, min(mission['dailyLimit'], safe_int(mission.get('achievements') or 0)))
        if mission.get('lastDate') != today:
            mission['giftValue'] = 0
            mission['achievements'] = 0
            mission['lastDate'] = today
            changed = True
        mission.pop('hotkey', None)
        if mission != entry:
            changed = True
        missions.append(mission)
    merged['missions'] = missions
    gift_rules = []
    for index, rule in enumerate(merged.get('giftRules') or []):
        if not isinstance(rule, dict):
            continue
        seconds = max(1, min(3600, safe_int(rule.get('seconds') or 1)))
        gift_rules.append({
            'id': str(rule.get('id') or f'gift-rule-{index+1}'),
            'giftName': str(rule.get('giftName') or '').strip(),
            'seconds': seconds,
            'text': str(rule.get('text') or f'カウント：{seconds}秒')[:500],
            'cardBg': valid_hex(rule.get('cardBg')),
            'cardBorder': valid_hex(rule.get('cardBorder')),
            'cardTextColor': valid_hex(rule.get('cardTextColor')),
            'labelTextColor': valid_hex(rule.get('labelTextColor')),
            'fontFamily':rule.get('fontFamily') if rule.get('fontFamily') in ('global','system','yuGothic','meiryo','gothic','serif','mono') else 'global',
            'textScale': max(50, min(250, safe_int(rule.get('textScale', 100), 100))),
            'labelTextScale': max(50, min(400, safe_int(rule.get('labelTextScale', rule.get('textScale', 100)), 100))),
            'cardOpacity': max(-1, min(100, safe_int(rule.get('cardOpacity', -1)))),
        })
    merged['giftRules'] = gift_rules
    raw_wall = merged.get('giftWall') if isinstance(merged.get('giftWall'), dict) else {}
    gift_history = []
    for index, item in enumerate(raw_wall.get('history') or []):
        if not isinstance(item, dict):
            continue
        image_url = str(item.get('giftImageUrl') or item.get('imageUrl') or '')[:2000]
        if not image_url.startswith(('http://', 'https://')):
            image_url = ''
        gift_history.append({
            'id': max(0, safe_int(item.get('id') or index + 1)),
            'senderName': str(item.get('senderName') or 'ゲスト')[:80],
            'avatarUrl': str(item.get('avatarUrl') or '')[:2000] if str(item.get('avatarUrl') or '').startswith(('http://','https://')) else '',
            'giftImageUrl': image_url,
            'giftName': str(item.get('giftName') or 'ギフト')[:80],
            'imageUrl': image_url,
            'price': max(0, min(100000000, safe_int(item.get('price') or 0))),
            'count': max(1, min(1000000, safe_int(item.get('count') or 1))),
            'totalCoins': max(0, min(1000000000, safe_int(item.get('totalCoins') or 0))),
            'createdAt': max(0, safe_float(item.get('createdAt') or 0)),
        })
    merged['giftWall'] = {
        'minCoins': max(0, min(100000000, safe_int(raw_wall.get('minCoins', 100)))),
        'columns': max(1, min(8, safe_int(raw_wall.get('columns', 4)))),
        'rows': max(1, min(5, safe_int(raw_wall.get('rows', 2)))),
        'pageSeconds': max(2, min(60, safe_int(raw_wall.get('pageSeconds', 8)))),
        'scrollDirection': raw_wall.get('scrollDirection') if raw_wall.get('scrollDirection') in ('horizontal','vertical') else 'vertical',
        'history': gift_history[:200],
        'displayHistory': [item for item in gift_history if item['id'] in ({x.get('id') for x in (raw_wall.get('displayHistory') or []) if isinstance(x,dict)} if 'displayHistory' in raw_wall else {x['id'] for x in gift_history})][:200],
        'fontFamily':raw_wall.get('fontFamily') if raw_wall.get('fontFamily') in ('global','system','yuGothic','meiryo','gothic','serif','mono') else 'global',
        'textScale': max(50, min(250, safe_int(raw_wall.get('textScale', 100), 100))),
        'avatarSize': max(20, min(160, safe_int(raw_wall.get('avatarSize', 44), 44))),
        'nameSize': max(8, min(80, safe_int(raw_wall.get('nameSize', 18), 18))),
        'giftNameSize': max(8, min(80, safe_int(raw_wall.get('giftNameSize', 16), 16))),
        'countSize': max(8, min(80, safe_int(raw_wall.get('countSize', 15), 15))),
        'giftImageSize': max(20, min(160, safe_int(raw_wall.get('giftImageSize', 44), 44))),
        'cardBg': valid_hex(raw_wall.get('cardBg')) or '#1c1c24',
        'cardBorder': valid_hex(raw_wall.get('cardBorder')) or '#ffcf59',
        'cardTextColor': valid_hex(raw_wall.get('cardTextColor')) or '#ffffff',
        'cardOpacity': max(0, min(100, safe_int(raw_wall.get('cardOpacity', 93), 93))),
        'nextId': max(1, safe_int(raw_wall.get('nextId') or (max((item['id'] for item in gift_history), default=0) + 1))),
    }
    raw_win = merged.get('winCounter') if isinstance(merged.get('winCounter'), dict) else {}
    old_gacha = data.get('gacha') if isinstance(data.get('gacha'), dict) else {}
    if not isinstance(data.get('winCounter'), dict):
        raw_win = {'currentWin':old_gacha.get('currentWin',0),'goalWin':old_gacha.get('goalWin',10),'shortcutAdd':old_gacha.get('shortcutAdd','CTRL+ALT+7'),'shortcutSub':old_gacha.get('shortcutSub','CTRL+ALT+SHIFT+7'),'giftRules':old_gacha.get('winGiftRules',[])}
    win_gift_rules=[]
    for index,item in enumerate(raw_win.get('giftRules') or []):
        if isinstance(item,dict):
            win_gift_rules.append({'id':str(item.get('id') or f'win-gift-{index+1}'),'giftName':str(item.get('giftName') or '').strip(),'delta':max(-9999,min(9999,safe_int(item.get('delta') or 0)))})
    merged['winCounter']={'fontFamily':raw_win.get('fontFamily') if raw_win.get('fontFamily') in ('global','system','yuGothic','meiryo','gothic','serif','mono') else 'global','title':str(raw_win.get('title','現在'))[:60],'currentWin':max(-999999,min(999999,safe_int(raw_win.get('currentWin') or 0))),'goalWin':max(1,min(999999,safe_int(raw_win.get('goalWin') or 10))),'shortcutAdd':str(raw_win.get('shortcutAdd') or '').upper(),'shortcutSub':str(raw_win.get('shortcutSub') or '').upper(),'giftRules':win_gift_rules,'cardBg':valid_hex(raw_win.get('cardBg')),'cardBorder':valid_hex(raw_win.get('cardBorder')),'cardTextColor':valid_hex(raw_win.get('cardTextColor')),'cardOpacity':max(-1,min(100,safe_int(raw_win.get('cardOpacity',-1)))),'positiveTextColor':valid_hex(raw_win.get('positiveTextColor')),'negativeTextColor':valid_hex(raw_win.get('negativeTextColor')) or '#ff4055','goalTextColor':valid_hex(raw_win.get('goalTextColor')),'titleSize':max(12,min(120,safe_int(raw_win.get('titleSize',30),30))),'valueSize':max(20,min(180,safe_int(raw_win.get('valueSize',76),76))),'imageUrl':str(raw_win.get('imageUrl') or '')[:240],'imageName':str(raw_win.get('imageName') or '')[:120],'imageSize':max(20,min(240,safe_int(raw_win.get('imageSize') or 64))),'imageEnabled':raw_win.get('imageEnabled',True) is not False}
    raw_gacha = merged.get('gacha') if isinstance(merged.get('gacha'), dict) else {}
    patterns = []
    for index, item in enumerate(raw_gacha.get('patterns') or []):
        if not isinstance(item, dict):
            continue
        low = max(-9999, min(9999, safe_int(item.get('minWin') or 0)))
        high = max(-9999, min(9999, safe_int(item.get('maxWin') or 0)))
        outcomes=[]
        for outcome in item.get('outcomes',[])[:50] if isinstance(item.get('outcomes',[]),list) else []:
            if isinstance(outcome,dict):
                outcomes.append({'value':max(-9999,min(9999,safe_int(outcome.get('value') or 0))),'probability':max(0,min(100000,safe_int(outcome.get('probability') or 0)))})
        pattern_opacity=safe_int(item.get('cardOpacity',raw_gacha.get('cardOpacity',94)))
        patterns.append({
            'id':str(item.get('id') or f'gacha-pattern-{index+1}'), 'name':str(item.get('name') or f'パターン{index+1}')[:60], 'giftName':str(item.get('giftName') or '').strip(),
            'minWin':min(low,high), 'maxWin':max(low,high), 'outcomeMode':'weighted' if item.get('outcomeMode')=='weighted' else 'range', 'outcomes':outcomes,
            'winSign':item.get('winSign') if item.get('winSign') in ('plus','minus','both') else 'both', 'mode':'single' if item.get('mode',raw_gacha.get('mode','continue'))=='single' else 'continue',
            'continuationRate':max(0,min(100,safe_int(item.get('continuationRate',raw_gacha.get('continuationRate',70))))),
            'upperAtEnabled':bool(item.get('upperAtEnabled',False)),
            'upperAtEntryRate':max(0,min(100,safe_int(item.get('upperAtEntryRate',5)))),
            'upperAtContinuationRate':max(0,min(100,safe_int(item.get('upperAtContinuationRate',80)))),
            'upperAtAnimationUrl':str(item.get('upperAtAnimationUrl') or '')[:2000], 'upperAtAnimationName':str(item.get('upperAtAnimationName') or '')[:120],
            'upperAtAudioUrl':str(item.get('upperAtAudioUrl') or '')[:2000], 'upperAtAudioName':str(item.get('upperAtAudioName') or '')[:120],
            'upperAtAudioVolume':max(0,min(100,safe_int(item.get('upperAtAudioVolume',75)))),
            'upperAtVideoAudioEnabled':bool(item.get('upperAtVideoAudioEnabled',item.get('videoAudioEnabled',True))),
            'upperAtVideoVolume':max(0,min(100,safe_int(item.get('upperAtVideoVolume',item.get('videoVolume',75))))),
            'upperEntryAnimationUrl':str(item.get('upperEntryAnimationUrl') or '')[:2000], 'upperEntryAnimationName':str(item.get('upperEntryAnimationName') or '')[:120],
            'upperEntryAudioUrl':str(item.get('upperEntryAudioUrl') or '')[:2000], 'upperEntryAudioName':str(item.get('upperEntryAudioName') or '')[:120],
            'upperEntryAudioVolume':max(0,min(100,safe_int(item.get('upperEntryAudioVolume',80)))),
            'upperEntryVideoAudioEnabled':bool(item.get('upperEntryVideoAudioEnabled',True)),
            'upperEntryVideoVolume':max(0,min(100,safe_int(item.get('upperEntryVideoVolume',80)))),
            'upperEntrySeconds':max(1,min(30,safe_int(item.get('upperEntrySeconds',3),3))),
            'continueEffectEnabled':bool(item.get('continueEffectEnabled',False)),
            'continueAnimationUrl':str(item.get('continueAnimationUrl') or '')[:2000], 'continueAnimationName':str(item.get('continueAnimationName') or '')[:120],
            'continueAudioUrl':str(item.get('continueAudioUrl') or '')[:2000], 'continueAudioName':str(item.get('continueAudioName') or '')[:120],
            'continueSeconds':max(1,min(30,safe_int(item.get('continueSeconds',3),3))),
            'continueAudioVolume':max(0,min(100,safe_int(item.get('continueAudioVolume',80)))),
            'continueVideoAudioEnabled':bool(item.get('continueVideoAudioEnabled',True)),
            'continueVideoVolume':max(0,min(100,safe_int(item.get('continueVideoVolume',80)))),
            'upperContinueEffectEnabled':bool(item.get('upperContinueEffectEnabled',False)),
            'upperContinueAnimationUrl':str(item.get('upperContinueAnimationUrl') or '')[:2000], 'upperContinueAnimationName':str(item.get('upperContinueAnimationName') or '')[:120],
            'upperContinueAudioUrl':str(item.get('upperContinueAudioUrl') or '')[:2000], 'upperContinueAudioName':str(item.get('upperContinueAudioName') or '')[:120],
            'upperContinueSeconds':max(1,min(30,safe_int(item.get('upperContinueSeconds',3),3))),
            'upperContinueAudioVolume':max(0,min(100,safe_int(item.get('upperContinueAudioVolume',80)))),
            'upperContinueVideoAudioEnabled':bool(item.get('upperContinueVideoAudioEnabled',True)),
            'upperContinueVideoVolume':max(0,min(100,safe_int(item.get('upperContinueVideoVolume',80)))),
            'startTextColor':valid_hex(item.get('startTextColor')) or '#ffffff', 'startTextSize':max(16,min(400,safe_int(item.get('startTextSize',48)))),
            'resultTextColor':valid_hex(item.get('resultTextColor')) or '#ffffff', 'resultTextSize':max(30,min(400,safe_int(item.get('resultTextSize',130)))),
            'roundTotalTextColor':valid_hex(item.get('roundTotalTextColor')) or '#ffffff', 'roundTotalTextSize':max(14,min(400,safe_int(item.get('roundTotalTextSize',32)))),
            'finalTotalTextColor':valid_hex(item.get('finalTotalTextColor')) or '#ffffff', 'finalTotalTextSize':max(18,min(400,safe_int(item.get('finalTotalTextSize',48)))),
            'patternTextColor':valid_hex(item.get('patternTextColor')) or '#ffffff', 'patternTextSize':max(18,min(400,safe_int(item.get('patternTextSize',40)))),
            'senderTextColor':valid_hex(item.get('senderTextColor')) or '#ffe9a6', 'senderTextSize':max(14,min(400,safe_int(item.get('senderTextSize',32)))),
            'choiceTextColor':valid_hex(item.get('choiceTextColor')) or '#ffe9a6', 'choiceTextSize':max(14,min(400,safe_int(item.get('choiceTextSize',34)))),
            'showPatternText':item.get('showPatternText',True) is not False, 'showSenderText':item.get('showSenderText',True) is not False,
            'showResultText':item.get('showResultText',True) is not False, 'showStateText':item.get('showStateText',True) is not False,
            'showTotalText':item.get('showTotalText',True) is not False, 'showChoiceText':item.get('showChoiceText',True) is not False,
            'effectStyle':item.get('effectStyle',raw_gacha.get('effectStyle','card')) if item.get('effectStyle',raw_gacha.get('effectStyle','card')) in ('card','fullscreen-slot') else 'card',
            'spinSeconds':max(3,min(30,safe_int(item.get('spinSeconds',raw_gacha.get('spinSeconds',5))))),
            'soundVolume':max(0,min(100,safe_int(item.get('soundVolume',raw_gacha.get('soundVolume',65))))),
            'slotNumberSize':max(40,min(400,safe_int(item.get('slotNumberSize',raw_gacha.get('slotNumberSize',130))))),
            'slotNumberColor':valid_hex(item.get('slotNumberColor')) or valid_hex(raw_gacha.get('slotNumberColor')) or '#ffffff',
            'slotX':max(5,min(95,safe_int(item.get('slotX',raw_gacha.get('slotX',50))))), 'slotY':max(10,min(90,safe_int(item.get('slotY',raw_gacha.get('slotY',50))))),
            'spinStyle':item.get('spinStyle',raw_gacha.get('spinStyle','dramatic')) if item.get('spinStyle',raw_gacha.get('spinStyle','dramatic')) in ('dramatic','ease-out','steady') else 'dramatic',
            'animationUrl':str(item.get('animationUrl') or raw_gacha.get('animationUrl') or ''), 'animationName':str(item.get('animationName') or raw_gacha.get('animationName') or '')[:120],
            'audioUrl':str(item.get('audioUrl') or raw_gacha.get('audioUrl') or ''), 'audioName':str(item.get('audioName') or raw_gacha.get('audioName') or '')[:120],
            'audioVolume':max(0,min(100,safe_int(item.get('audioVolume',raw_gacha.get('audioVolume',75))))),
            'resultAudioUrl':str(item.get('resultAudioUrl') or raw_gacha.get('resultAudioUrl') or ''), 'resultAudioName':str(item.get('resultAudioName') or raw_gacha.get('resultAudioName') or '')[:120],
            'resultAudioVolume':max(0,min(100,safe_int(item.get('resultAudioVolume',raw_gacha.get('resultAudioVolume',80))))),
            'videoAudioEnabled':bool(item.get('videoAudioEnabled',raw_gacha.get('videoAudioEnabled',True))), 'videoVolume':max(0,min(100,safe_int(item.get('videoVolume',raw_gacha.get('videoVolume',75))))),
            'cardBg':valid_hex(item.get('cardBg')) or valid_hex(raw_gacha.get('cardBg')) or '#17151c', 'cardBorder':valid_hex(item.get('cardBorder')) or valid_hex(raw_gacha.get('cardBorder')) or '#ffcf59',
            'cardTextColor':valid_hex(item.get('cardTextColor')) or valid_hex(raw_gacha.get('cardTextColor')) or '#ffffff', 'cardOpacity':max(0,min(100,pattern_opacity if pattern_opacity>=0 else 94)),
            'stateTextColor':valid_hex(item.get('stateTextColor')) or valid_hex(item.get('cardTextColor')) or '#ffe9a6', 'stateTextSize':max(14,min(400,safe_int(item.get('stateTextSize',30)))),
            'fontFamily':('global' if item.get('fontFamily') in (None,'system') else item.get('fontFamily')) if item.get('fontFamily') in (None,'global','system','native','yuGothic','meiryo','gothic','serif','mono') else 'global',
            'textGlowEnabled':bool(item.get('textGlowEnabled',merged.get('textGlowEnabled',False))), 'textGlowColor':valid_hex(item.get('textGlowColor')) or valid_hex(merged.get('textGlowColor')) or '#e52b3c', 'textGlowStrength':max(0,min(40,safe_int(item.get('textGlowStrength',merged.get('textGlowStrength',12))))),
            'endSeconds':max(1,min(600,safe_int(item.get('endSeconds',raw_gacha.get('endSeconds',6))))), 'endAudioVolume':max(0,min(100,safe_int(item.get('endAudioVolume',raw_gacha.get('endAudioVolume',75))))),
            'endAnimationUrl':str(item.get('endAnimationUrl') or raw_gacha.get('endAnimationUrl') or ''), 'endAnimationName':str(item.get('endAnimationName') or raw_gacha.get('endAnimationName') or '')[:120],
            'endAudioUrl':str(item.get('endAudioUrl') or raw_gacha.get('endAudioUrl') or ''), 'endAudioName':str(item.get('endAudioName') or raw_gacha.get('endAudioName') or '')[:120],
        })
    raw_event = raw_gacha.get('event') if isinstance(raw_gacha.get('event'), dict) else {}
    event_created_at=max(0,safe_float(raw_event.get('createdAt') or 0))
    event_active=bool(raw_event.get('active',False)) and event_created_at>=SERVER_STARTED_AT
    merged['gacha'] = {
        'mode':'single' if raw_gacha.get('mode') == 'single' else 'continue',
        'continuationRate':max(0,min(100,safe_int(raw_gacha.get('continuationRate',70)))),
        'spinSeconds':max(3,min(30,safe_int(raw_gacha.get('spinSeconds',5)))),
        'soundVolume':max(0,min(100,safe_int(raw_gacha.get('soundVolume',65)))),
        'shortcutChoicePlus':str(raw_gacha.get('shortcutChoicePlus') or 'CTRL+ALT+8').upper(),
        'shortcutChoiceMinus':str(raw_gacha.get('shortcutChoiceMinus') or 'CTRL+ALT+9').upper(),
        'audioUrl':str(raw_gacha.get('audioUrl') or ''),
        'audioName':str(raw_gacha.get('audioName') or ''),
        'audioVolume':max(0,min(100,safe_int(raw_gacha.get('audioVolume',75)))),
        'resultAudioUrl':str(raw_gacha.get('resultAudioUrl') or ''),
        'resultAudioName':str(raw_gacha.get('resultAudioName') or ''),
        'resultAudioVolume':max(0,min(100,safe_int(raw_gacha.get('resultAudioVolume',80)))),
        'effectStyle':'fullscreen-slot' if raw_gacha.get('effectStyle')=='fullscreen-slot' else 'card',
        'slotNumberSize':max(40,min(400,safe_int(raw_gacha.get('slotNumberSize',130)))),
        'slotNumberColor':valid_hex(raw_gacha.get('slotNumberColor')) or '#ffffff',
        'slotX':max(5,min(95,safe_int(raw_gacha.get('slotX',50)))), 'slotY':max(10,min(90,safe_int(raw_gacha.get('slotY',50)))), 'spinStyle':raw_gacha.get('spinStyle') if raw_gacha.get('spinStyle') in ('dramatic','ease-out','steady') else 'dramatic',
        'videoAudioEnabled':bool(raw_gacha.get('videoAudioEnabled',True)),
        'videoVolume':max(0,min(100,safe_int(raw_gacha.get('videoVolume',75)))),
        'endAnimationUrl':str(raw_gacha.get('endAnimationUrl') or ''),
        'endAnimationName':str(raw_gacha.get('endAnimationName') or ''),
        'endAudioUrl':str(raw_gacha.get('endAudioUrl') or ''),
        'endAudioName':str(raw_gacha.get('endAudioName') or ''),
        'endAudioVolume':max(0,min(100,safe_int(raw_gacha.get('endAudioVolume',75)))),
        'endSeconds':max(1,min(600,safe_int(raw_gacha.get('endSeconds',6)))),
        'cardBg':valid_hex(raw_gacha.get('cardBg')),
        'cardBorder':valid_hex(raw_gacha.get('cardBorder')),
        'cardTextColor':valid_hex(raw_gacha.get('cardTextColor')),
        'cardOpacity':max(-1,min(100,safe_int(raw_gacha.get('cardOpacity',-1)))),
        'patterns':patterns,
        'animationUrl':str(raw_gacha.get('animationUrl') or ''),
        'animationName':str(raw_gacha.get('animationName') or ''),
        'historyFontFamily':raw_gacha.get('historyFontFamily') if raw_gacha.get('historyFontFamily') in ('global','system','yuGothic','meiryo','gothic','serif','mono') else 'global',
        'historyTextScale':max(50,min(250,safe_int(raw_gacha.get('historyTextScale',100),100))),
        'historyCardBg':valid_hex(raw_gacha.get('historyCardBg')) or '#17181e',
        'historyCardBorder':valid_hex(raw_gacha.get('historyCardBorder')) or '#ffcf59',
        'historyTextColor':valid_hex(raw_gacha.get('historyTextColor')) or '#ffffff',
        'historyCardOpacity':max(0,min(100,safe_int(raw_gacha.get('historyCardOpacity',93),93))),
        'history':[{'id':max(0,safe_int(item.get('id') or 0)),'senderName':str(item.get('senderName') or '')[:80],'patternName':str(item.get('patternName') or '')[:60],'result':max(-999999,min(999999,safe_int(item.get('result') or 0))),'createdAt':max(0,safe_float(item.get('createdAt') or 0))} for item in (raw_gacha.get('history') or []) if isinstance(item,dict)][:20],
        'queue':([x for x in (raw_gacha.get('queue') or []) if isinstance(x,dict)][:100] if event_active else []),
        'event':{'id':max(0,safe_int(raw_event.get('id') or 0)), 'type':str(raw_event.get('type') or ''), 'active':event_active, 'mode':'single' if raw_event.get('mode')=='single' else 'continue', 'winSign':raw_event.get('winSign') if raw_event.get('winSign') in ('plus','minus','both') else 'plus', 'choice':raw_event.get('choice') if raw_event.get('choice') in ('plus','minus') else '', 'choiceReady':bool(raw_event.get('choiceReady',False)), 'patternId':str(raw_event.get('patternId') or ''), 'patternName':str(raw_event.get('patternName') or ''), 'rounds':raw_event.get('rounds') if isinstance(raw_event.get('rounds'),list) else [], 'appliedRounds':[safe_int(x) for x in raw_event.get('appliedRounds',[]) if str(x).isdigit()], 'total':max(-999999,min(999999,safe_int(raw_event.get('total') or 0))), 'currentWin':max(-999999,min(999999,safe_int(raw_event.get('currentWin') or 0))), 'giftName':str(raw_event.get('giftName') or ''), 'senderName':str(raw_event.get('senderName') or '')[:80], 'createdAt':event_created_at},
    }
    merged['tiktokUsername'] = str(merged.get('tiktokUsername') or '').strip().lstrip('@')
    raw_timer = merged.get('timer') if isinstance(merged.get('timer'), dict) else {}
    merged['timer'] = {
        'endAt': max(0, safe_float(raw_timer.get('endAt') or 0)),
        'seconds': max(0, safe_int(raw_timer.get('seconds') or 0)),
        'giftName': str(raw_timer.get('giftName') or ''),
        'defaultText': str(raw_timer.get('defaultText') or 'カウント：0秒')[:500],
        'currentText': str(raw_timer.get('currentText') or '')[:500],
    }
    raw_smoking = merged.get('smokingTimer') if isinstance(merged.get('smokingTimer'), dict) else {}
    merged['smokingTimer'] = {
        'endAt': max(0, safe_float(raw_smoking.get('endAt') or 0)),
        'remainingSeconds': max(0, safe_int(raw_smoking.get('remainingSeconds') or 0)),
        'runId': max(0, safe_int(raw_smoking.get('runId') or 0)),
        'audioUrl': str(raw_smoking.get('audioUrl') or ''),
        'audioName': str(raw_smoking.get('audioName') or ''),
        'volume': max(0, min(100, safe_int(raw_smoking.get('volume', 80)))),
        'fontSize': max(80, min(180, safe_int(raw_smoking.get('fontSize', 130)))),
        'titleSize': max(32, min(80, safe_int(raw_smoking.get('titleSize', 56)))),
        'cardBg': valid_hex(raw_smoking.get('cardBg')),
        'cardBorder': valid_hex(raw_smoking.get('cardBorder')),
        'cardTextColor': valid_hex(raw_smoking.get('cardTextColor')),
        'cardOpacity': max(-1, min(100, safe_int(raw_smoking.get('cardOpacity', -1)))),
        'fontFamily':raw_smoking.get('fontFamily') if raw_smoking.get('fontFamily') in ('global','system','yuGothic','meiryo','gothic','serif','mono') else 'global',
        'fontFamily':raw_smoking.get('fontFamily') if raw_smoking.get('fontFamily') in ('global','system','yuGothic','meiryo','gothic','serif','mono') else 'global',
        **{f'shortcut{action}{minutes}':str(raw_smoking.get(f'shortcut{action}{minutes}') or '').upper() for minutes in (5,10,15,30) for action in ('Add','Sub')},
    }
    raw_sg=merged.get('smokingGacha') if isinstance(merged.get('smokingGacha'),dict) else {}
    sg_patterns=[]
    for index,item in enumerate(raw_sg.get('patterns') or []):
        if not isinstance(item,dict): continue
        outcomes=[]
        for outcome in item.get('outcomes',[])[:50] if isinstance(item.get('outcomes',[]),list) else []:
            if isinstance(outcome,dict): outcomes.append({'minutes':max(1,min(1440,safe_int(outcome.get('minutes') or 1))),'probability':max(0,min(100000,safe_int(outcome.get('probability') or 0)))})
        sg_patterns.append({'id':str(item.get('id') or f'smoking-pattern-{index+1}'),'name':str(item.get('name') or f'禁煙ガチャ{index+1}')[:60],'giftName':str(item.get('giftName') or '').strip(),'outcomes':outcomes,'spinSeconds':max(3,min(30,safe_int(item.get('spinSeconds',7)) )),'animationUrl':str(item.get('animationUrl') or ''),'animationName':str(item.get('animationName') or '')[:120],'audioUrl':str(item.get('audioUrl') or ''),'audioName':str(item.get('audioName') or '')[:120],'audioVolume':max(0,min(100,safe_int(item.get('audioVolume',75)))),'videoAudioEnabled':bool(item.get('videoAudioEnabled',True)),'videoVolume':max(0,min(100,safe_int(item.get('videoVolume',75))))})
    raw_sg_event=raw_sg.get('event') if isinstance(raw_sg.get('event'),dict) else {}
    sg_created=max(0,safe_float(raw_sg_event.get('createdAt') or 0))
    sg_active=bool(raw_sg_event.get('active',False)) and sg_created>=SERVER_STARTED_AT
    merged['smokingGacha']={'fontFamily':raw_sg.get('fontFamily') if raw_sg.get('fontFamily') in ('global','system','yuGothic','meiryo','gothic','serif','mono') else 'global','patterns':sg_patterns,'event':{'id':max(0,safe_int(raw_sg_event.get('id') or 0)),'type':str(raw_sg_event.get('type') or ''),'active':sg_active,'patternId':str(raw_sg_event.get('patternId') or ''),'patternName':str(raw_sg_event.get('patternName') or ''),'minutes':max(0,safe_int(raw_sg_event.get('minutes') or 0)),'senderName':str(raw_sg_event.get('senderName') or '')[:80],'choice':raw_sg_event.get('choice') if raw_sg_event.get('choice') in ('plus','minus') else '', 'choiceReady':bool(raw_sg_event.get('choiceReady',False)),'preview':bool(raw_sg_event.get('preview',False)),'createdAt':sg_created},'queue':([x for x in (raw_sg.get('queue') or []) if isinstance(x,dict)][:100] if sg_active else []),'animationUrl':str(raw_sg.get('animationUrl') or ''),'animationName':str(raw_sg.get('animationName') or ''),'audioUrl':str(raw_sg.get('audioUrl') or ''),'audioName':str(raw_sg.get('audioName') or ''),'audioVolume':max(0,min(100,safe_int(raw_sg.get('audioVolume',75)))),'resultAudioUrl':str(raw_sg.get('resultAudioUrl') or ''),'resultAudioName':str(raw_sg.get('resultAudioName') or ''),'resultAudioVolume':max(0,min(100,safe_int(raw_sg.get('resultAudioVolume',80)))),'effectStyle':'card' if raw_sg.get('effectStyle')=='card' else 'fullscreen-slot','spinSeconds':max(3,min(30,safe_int(raw_sg.get('spinSeconds',7)))),'endSeconds':max(1,min(600,safe_int(raw_sg.get('endSeconds',6)))),'slotNumberSize':max(40,min(220,safe_int(raw_sg.get('slotNumberSize',130)))),'slotNumberColor':valid_hex(raw_sg.get('slotNumberColor')) or '#ffffff','slotX':max(5,min(95,safe_int(raw_sg.get('slotX',50)))),'slotY':max(10,min(90,safe_int(raw_sg.get('slotY',50)))),'spinStyle':raw_sg.get('spinStyle') if raw_sg.get('spinStyle') in ('dramatic','ease-out','steady') else 'dramatic','shortcutPlus':str(raw_sg.get('shortcutPlus') or 'CTRL+ALT+5').upper(),'shortcutMinus':str(raw_sg.get('shortcutMinus') or 'CTRL+ALT+SHIFT+5').upper()}
    if 'mission' in merged:
        merged.pop('mission', None)
        changed = True
    if 'missions' not in data:
        changed = True
    if merged.get('counters') != data.get('counters', []):
        changed = True
    if merged.get('missions') != data.get('missions', []):
        changed = True
    if merged.get('giftRules') != data.get('giftRules', []):
        changed = True
    if merged.get('giftWall') != data.get('giftWall', DEFAULT['giftWall']):
        changed = True
    if merged.get('winCounter') != data.get('winCounter', DEFAULT['winCounter']):
        changed = True
    if merged.get('tiktokUsername') != data.get('tiktokUsername', ''):
        changed = True
    if merged.get('timer') != data.get('timer', DEFAULT['timer']):
        changed = True
    if merged.get('smokingTimer') != data.get('smokingTimer', DEFAULT['smokingTimer']):
        changed = True
    if merged.get('gacha') != data.get('gacha', DEFAULT['gacha']):
        changed = True
    if merged.get('smokingGacha') != data.get('smokingGacha', DEFAULT['smokingGacha']):
        changed = True
    if merged.get('gaugeColor') != data.get('gaugeColor'):
        changed = True
    if merged.get('cardDefaults') != data.get('cardDefaults', DEFAULT['cardDefaults']):
        changed = True
    if any(merged.get(k) != data.get(k, DEFAULT[k]) for k in ('compCardBg','compCardBorder','compCardTextColor','compCardOpacity','compCardWidth','compCardHeight','compFontFamily')):
        changed = True
    if merged.get('memos') != data.get('memos'):
        changed = True
    return merged, changed

def read_state():
    with STATE_LOCK:
        try:
            data = json.loads(STATE.read_text(encoding='utf-8'))
        except Exception:
            data = copy.deepcopy(DEFAULT)
        try:
            merged, changed = normalize_state(data)
        except Exception as error:
            # Never let one value from an older release stop control.html from
            # opening.  Keep the original file as a recoverable backup.
            if STATE.exists():
                backup = STATE.with_name('state_backup_before_recovery.json')
                if not backup.exists():
                    try:
                        shutil.copy2(STATE, backup)
                    except Exception:
                        pass
            print(f'Saved settings could not be normalized: {error}')
            merged, changed = copy.deepcopy(DEFAULT), False
        if changed or not STATE.exists():
            STATE.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding='utf-8')
        return merged

def write_state(data):
    allowed = {**copy.deepcopy(DEFAULT), **data}
    merged, _ = normalize_state(allowed)
    with STATE_LOCK:
        STATE.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding='utf-8')

def change_mission_gift(mission, delta):
    goal = max(1, int(mission.get('giftGoal', 1)))
    limit = max(1, int(mission.get('dailyLimit', 10)))
    count = max(0, int(mission.get('achievements', 0)))
    if delta > 0 and count >= limit:
        return
    value = max(0, int(mission.get('giftValue', 0)) + delta)
    while value >= goal and count < limit:
        value -= goal
        count += 1
        mission['noticeUntil'] = time.time() + 3
    if count >= limit:
        value = 0
    mission['giftValue'] = value
    mission['achievements'] = count
    mission['lastDate'] = today_jst()

def parse_shortcut(value):
    parts = [part.strip().upper() for part in str(value or '').split('+') if part.strip()]
    modifiers = 0
    key = None
    for part in parts:
        if part in ('CTRL', 'CONTROL'):
            modifiers |= 0x0002
        elif part == 'ALT':
            modifiers |= 0x0001
        elif part == 'SHIFT':
            modifiers |= 0x0004
        elif part in ('WIN', 'META'):
            modifiers |= 0x0008
        else:
            if key is not None:
                return None
            key = part
    if not modifiers or not key:
        return None
    vk = None
    if len(key) == 1 and key.isalnum():
        vk = ord(key)
    elif key.startswith('F') and key[1:].isdigit() and 1 <= int(key[1:]) <= 24:
        vk = 0x70 + int(key[1:]) - 1
    else:
        vk = {'SPACE':0x20,'TAB':0x09,'ENTER':0x0D,'ESC':0x1B,'UP':0x26,'DOWN':0x28,'LEFT':0x25,'RIGHT':0x27,'HOME':0x24,'END':0x23,'PAGEUP':0x21,'PAGEDOWN':0x22,'INSERT':0x2D,'DELETE':0x2E}.get(key)
        if key.startswith('NUMPAD') and key[6:].isdigit() and 0 <= int(key[6:]) <= 9:
            vk = 0x60 + int(key[6:])
    return (modifiers, vk) if vk else None

def dispatch_hotkey_action(action):
    with STATE_LOCK:
        try:
            data = json.loads(STATE.read_text(encoding='utf-8'))
        except Exception:
            data = copy.deepcopy(DEFAULT)
        data, _ = normalize_state(data)
        if action['type'] == 'mission':
            for mission in data.get('missions', []):
                if mission.get('id') == action['id']:
                    change_mission_gift(mission, action['delta'])
                    break
        elif action['type'] == 'gacha':
            win=data['winCounter']; win['currentWin']=max(-999999,min(999999,win['currentWin']+action['delta']))
        elif action['type'] == 'gachaChoice':
            choose_gacha_sign_in_state(data, action['choice'])
        elif action['type'] == 'smokingTimer':
            timer=data['smokingTimer']; now=time.time(); remain=max(0,int((timer.get('endAt') or 0)-now)) if timer.get('endAt') else max(0,int(timer.get('remainingSeconds') or 0)); next_value=max(0,remain+int(action['delta']))
            timer['remainingSeconds']=next_value; timer['endAt']=now+next_value if next_value else 0
            if next_value and not remain: timer['runId']=int(timer.get('runId') or 0)+1
        elif action['type'] == 'smokingGachaChoice':
            choose_smoking_gacha_sign_in_state(data, action['choice'])
        else:
            for counter in data.get('counters', []):
                if counter.get('id') == action['id']:
                    counter['value'] = max(0, int(counter.get('value', 0)) + action['delta'])
                    break
        STATE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')

def normalize_gift_name(value):
    value = unicodedata.normalize('NFKC', str(value or '')).casefold()
    return ''.join(value.split())

def run_gacha_draw(data, pattern, gift_name='テスト', sender_name=''):
    gacha=data['gacha']; win=data['winCounter']; rounds=[]; total=win['currentWin']
    mode=pattern.get('mode',gacha['mode']); rate=max(0,min(100,int(pattern.get('continuationRate',gacha['continuationRate']))))
    low,high=pattern['minWin'],pattern['maxWin']; sign=pattern.get('winSign','both')
    magnitude_low,magnitude_high=sorted((abs(low),abs(high)))
    if sign=='plus': low,high=magnitude_low,magnitude_high
    elif sign=='minus': low,high=-magnitude_high,-magnitude_low
    else: low,high=magnitude_low,magnitude_high
    earned=0
    upper_enabled=bool(pattern.get('upperAtEnabled',False)) and mode=='continue'
    upper_enter_rate=max(0,min(100,int(pattern.get('upperAtEntryRate',5))))
    upper_rate=max(0,min(100,int(pattern.get('upperAtContinuationRate',80))))
    phase='normal'
    for _ in range(50):
        weighted=[(abs(item['value']),item['probability']) for item in pattern.get('outcomes',[]) if int(item.get('probability') or 0)>0] if pattern.get('outcomeMode')=='weighted' else []
        delta=random.choices([item[0] for item in weighted],weights=[item[1] for item in weighted],k=1)[0] if weighted else random.randint(low,high)
        if sign=='minus': delta=-abs(delta)
        elif sign in ('plus','both'): delta=abs(delta)
        total=max(-999999,min(999999,total+delta)); earned=max(-999999,min(999999,earned+delta))
        active_rate=upper_rate if phase=='upper' else rate
        keep_going=(mode=='continue' and random.random()*100 < active_rate)
        enter_upper=bool(keep_going and phase=='normal' and upper_enabled and random.random()*100 < upper_enter_rate)
        rounds.append({'delta':delta,'total':earned,'currentWin':total,'continued':keep_going,'phase':phase,'upperEntered':enter_upper})
        if not keep_going: break
        if enter_upper: phase='upper'
    used_ids=[int(gacha.get('event',{}).get('id') or 0)]+[int(x.get('id') or 0) for x in gacha.get('queue',[]) if isinstance(x,dict)]
    event={'id':max(used_ids,default=0)+1,'type':'gacha','active':False,'mode':mode,'winSign':sign,'choice':'','choiceReady':False,'patternId':pattern['id'],'patternName':pattern['name'],'rounds':rounds,'appliedRounds':[],'total':earned,'currentWin':total,'giftName':gift_name,'senderName':str(sender_name or '')[:80],'createdAt':time.time()}
    if gacha.get('event',{}).get('active'):
        gacha.setdefault('queue',[]).append(event)
    else:
        event['active']=True
        gacha['event']=event

def run_smoking_gacha_draw(data, pattern, sender_name='テスト', preview=False):
    g=data['smokingGacha']; options=[x for x in pattern.get('outcomes',[]) if int(x.get('probability') or 0)>0]
    if options: minutes=int(random.choices(options,weights=[x['probability'] for x in options],k=1)[0]['minutes'])
    else: minutes=5
    ids=[int(g.get('event',{}).get('id') or 0)]+[int(x.get('id') or 0) for x in g.get('queue',[]) if isinstance(x,dict)]
    event={'id':max(ids,default=0)+1,'type':'smoking-gacha','active':False,'patternId':pattern['id'],'patternName':pattern['name'],'minutes':minutes,'senderName':str(sender_name or '')[:80],'choice':'','choiceReady':False,'preview':bool(preview),'createdAt':time.time()}
    if g.get('event',{}).get('active'): g.setdefault('queue',[]).append(event)
    else: event['active']=True;g['event']=event

def mark_smoking_gacha_choice_ready(event_id):
    with STATE_LOCK:
        try: data=json.loads(STATE.read_text(encoding='utf-8'))
        except Exception: data=copy.deepcopy(DEFAULT)
        data,_=normalize_state(data);ev=data['smokingGacha']['event']
        if int(ev.get('id') or 0)!=event_id or not ev.get('active') or ev.get('choice'): return False
        ev['choiceReady']=True;STATE.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8');return True

def choose_smoking_gacha_sign_in_state(data, choice):
    ev=data['smokingGacha']['event']
    if ev.get('type')!='smoking-gacha' or not ev.get('active') or not ev.get('choiceReady') or ev.get('choice'): return False
    choice='minus' if choice=='minus' else 'plus';ev['choice']=choice
    if not ev.get('preview'):
        timer=data['smokingTimer'];now=time.time();remain=max(0,int((timer.get('endAt') or 0)-now)) if timer.get('endAt') else max(0,int(timer.get('remainingSeconds') or 0));delta=int(ev.get('minutes') or 0)*60*(1 if choice=='plus' else -1);next_value=max(0,remain+delta)
        timer['remainingSeconds']=next_value;timer['endAt']=now+next_value if next_value else 0
        if next_value and not remain:timer['runId']=int(timer.get('runId') or 0)+1
    ev['choice']=choice;return True

def choose_smoking_gacha_sign(event_id, choice):
    with STATE_LOCK:
        try:data=json.loads(STATE.read_text(encoding='utf-8'))
        except Exception:data=copy.deepcopy(DEFAULT)
        data,_=normalize_state(data);ev=data['smokingGacha']['event']
        if int(ev.get('id') or 0)!=event_id or not choose_smoking_gacha_sign_in_state(data,choice):return False
        STATE.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8');return True

def complete_smoking_gacha_event(event_id):
    with STATE_LOCK:
        try:data=json.loads(STATE.read_text(encoding='utf-8'))
        except Exception:data=copy.deepcopy(DEFAULT)
        data,_=normalize_state(data);g=data['smokingGacha'];ev=g['event']
        if int(ev.get('id') or 0)!=event_id or not ev.get('active') or not ev.get('choice'):return False
        ev['active']=False;queue_items=g.setdefault('queue',[])
        if queue_items:
            nxt=queue_items.pop(0);nxt['active']=True;nxt['createdAt']=time.time();g['event']=nxt
        STATE.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8');return True

def complete_gacha_event(event_id):
    with STATE_LOCK:
        try:
            data=json.loads(STATE.read_text(encoding='utf-8'))
        except Exception:
            data=copy.deepcopy(DEFAULT)
        data,_=normalize_state(data); gacha=data['gacha']; event=gacha['event']
        if int(event.get('id') or 0)!=event_id or not event.get('active'):
            return False
        if event.get('type') == 'gacha' and not any(int(item.get('id') or 0)==event_id for item in gacha.get('history', [])):
            result=int(event.get('total') or 0)
            if event.get('winSign') == 'both':
                result= -abs(result) if event.get('choice') == 'minus' else abs(result)
            gacha.setdefault('history', []).insert(0, {'id':event_id,'senderName':str(event.get('senderName') or 'ゲスト')[:80],'patternName':str(event.get('patternName') or 'WINガチャ')[:60],'result':result,'createdAt':max(0,float(event.get('createdAt') or time.time()))})
            gacha['history']=gacha['history'][:20]
        event['active']=False
        queue=gacha.setdefault('queue',[])
        if queue:
            next_event=queue.pop(0); next_event['active']=True; next_event['createdAt']=time.time()
            gacha['event']=next_event
        STATE.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
        return True

def choose_gacha_sign_in_state(data, choice):
    event=data['gacha']['event']
    if event.get('type')!='gacha' or event.get('winSign')!='both' or not event.get('choiceReady') or event.get('choice'):
        return False
    choice='minus' if choice=='minus' else 'plus'; amount=abs(int(event.get('total') or 0))
    delta=-amount if choice=='minus' else amount
    win=data['winCounter']; win['currentWin']=max(-999999,min(999999,win['currentWin']+delta))
    event['choice']=choice; event['currentWin']=win['currentWin']
    return True

def choose_gacha_sign(event_id, choice):
    with STATE_LOCK:
        try:
            data=json.loads(STATE.read_text(encoding='utf-8'))
        except Exception:
            data=copy.deepcopy(DEFAULT)
        data,_=normalize_state(data)
        if int(data['gacha']['event'].get('id') or 0)!=event_id or not choose_gacha_sign_in_state(data,choice):
            return False
        STATE.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
        return True

def mark_gacha_choice_ready(event_id):
    with STATE_LOCK:
        try:
            data=json.loads(STATE.read_text(encoding='utf-8'))
        except Exception:
            data=copy.deepcopy(DEFAULT)
        data,_=normalize_state(data); event=data['gacha']['event']
        if int(event.get('id') or 0)!=event_id or event.get('winSign')!='both':
            return False
        event['choiceReady']=True
        STATE.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
        return True

def apply_gacha_round(event_id, round_index):
    with STATE_LOCK:
        try:
            data=json.loads(STATE.read_text(encoding='utf-8'))
        except Exception:
            data=copy.deepcopy(DEFAULT)
        data,_=normalize_state(data); event=data['gacha']['event']
        if event.get('type')!='gacha' or int(event.get('id') or 0)!=event_id:
            return False
        rounds=event.get('rounds') or []; applied=event.setdefault('appliedRounds',[])
        if round_index<0 or round_index>=len(rounds) or round_index in applied:
            return round_index in applied
        if event.get('winSign')=='both':
            return False
        delta=int(rounds[round_index].get('delta') or 0)
        win=data['winCounter']; win['currentWin']=max(-999999,min(999999,win['currentWin']+delta))
        applied.append(round_index); event['currentWin']=win['currentWin']
        STATE.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
        return True

def process_gift_event(gift_name, count=1, sender_name='', gift_info=None, avatar_url=''):
    name = normalize_gift_name(gift_name)
    if not name:
        return False
    with STATE_LOCK:
        try:
            data = json.loads(STATE.read_text(encoding='utf-8'))
        except Exception:
            data = copy.deepcopy(DEFAULT)
        data, _ = normalize_state(data)
        matched = False
        recorded = False
        count=max(1,int(count or 1))
        item_info = normalize_gift_catalog([gift_info])[0] if gift_info else None
        if item_info is None or not item_info.get('price') or not item_info.get('imageUrl'):
            with TIKTOK_GIFT_CATALOG_LOCK:
                cached = next((copy.deepcopy(item) for item in TIKTOK_GIFT_CATALOG if normalize_gift_name(item.get('name')) == name), None)
            if cached:
                item_info = {**(item_info or {}), **{k:v for k,v in cached.items() if not (item_info or {}).get(k)}}
        item_info = item_info or {'name':gift_name, 'price':0, 'imageUrl':''}
        price=max(0,int(item_info.get('price') or 0))
        total_coins=price*count
        wall=data['giftWall']
        if price>0 and total_coins>=wall['minCoins']:
            gift_id=wall['nextId']
            wall['nextId']+=1
            gift_entry={'id':gift_id,'senderName':str(sender_name or 'ゲスト')[:80],'giftName':str(item_info.get('name') or gift_name)[:80],'imageUrl':str(item_info.get('imageUrl') or '')[:2000],'giftImageUrl':str(item_info.get('imageUrl') or '')[:2000],'avatarUrl':str(avatar_url or '')[:2000] if str(avatar_url or '').startswith(('http://','https://')) else '', 'price':price,'count':count,'totalCoins':total_coins,'createdAt':time.time()}
            wall['history'].insert(0, gift_entry)
            wall['history']=wall['history'][:200]
            wall.setdefault('displayHistory',[]).insert(0,copy.deepcopy(gift_entry))
            wall['displayHistory']=wall['displayHistory'][:200]
            recorded=True
        rule = next((r for r in data.get('giftRules', []) if normalize_gift_name(r.get('giftName')) == name), None)
        if rule:
            data['timer'] = {**data.get('timer', {}), 'endAt': 0, 'seconds': rule['seconds'], 'giftName': rule['giftName'], 'currentText': rule.get('text') or f"カウント：{rule['seconds']}秒"}
            matched = True
        gacha=data['gacha']; win=data['winCounter']
        pattern=next((p for p in gacha['patterns'] if p['giftName'] and normalize_gift_name(p['giftName'])==name),None)
        smoke_pattern=next((p for p in data['smokingGacha']['patterns'] if p['giftName'] and normalize_gift_name(p['giftName'])==name),None)
        gift_rule=next((x for x in win['giftRules'] if x['giftName'] and normalize_gift_name(x['giftName'])==name),None)
        # WIN adjustment gifts only change the counter, even if the same gift
        # name was also entered as a gacha trigger.
        if gift_rule:
            pattern=None
        if pattern:
            run_gacha_draw(data,pattern,gift_name,sender_name)
            matched=True
        if smoke_pattern:
            run_smoking_gacha_draw(data,smoke_pattern,sender_name)
            matched=True
        if gift_rule:
            delta=gift_rule['delta']*count
            win['currentWin']=max(-999999,min(999999,win['currentWin']+delta))
            matched=True
        if not matched and not recorded:
            return False
        STATE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
        return matched

def get_tiktok_status():
    with TIKTOK_STATUS_LOCK:
        return {**TIKTOK_STATUS,'enabled':TIKTOK_GIFT_ENABLED}

def start_tiktok_gift_listener(username):
    global TIKTOK_LISTENER_THREAD, TIKTOK_LISTENER_USERNAME, TIKTOK_GIFT_ENABLED, TIKTOK_STATUS
    username = str(username or '').strip().lstrip('@')
    if not username:
        return {'status': 'error', 'message': 'TikTokユーザー名を入力してください', 'username': ''}
    with TIKTOK_LISTENER_LOCK:
        if TIKTOK_LISTENER_THREAD and TIKTOK_LISTENER_THREAD.is_alive():
            if username == TIKTOK_LISTENER_USERNAME:
                TIKTOK_GIFT_ENABLED=True
                with TIKTOK_STATUS_LOCK:
                    TIKTOK_STATUS={'status':'connected','message':f'@{username} ギフト受信ON','username':username}
                return get_tiktok_status()
            return {'status': 'error', 'message': '接続先を変更するにはサーバーを再起動してください', 'username': TIKTOK_LISTENER_USERNAME}
        TIKTOK_LISTENER_USERNAME = username
        TIKTOK_GIFT_ENABLED = True
        TIKTOK_LISTENER_THREAD = threading.Thread(target=tiktok_gift_listener, args=(username,), daemon=True)
        TIKTOK_LISTENER_THREAD.start()
    return {'status': 'connecting', 'message': 'TikTok LIVEへ接続しています', 'username': username}

def stop_tiktok_gift_listener():
    global TIKTOK_GIFT_ENABLED, TIKTOK_STATUS
    TIKTOK_GIFT_ENABLED=False
    with TIKTOK_STATUS_LOCK:
        TIKTOK_STATUS={'status':'stopped','message':'ギフト受信OFF','username':TIKTOK_LISTENER_USERNAME}
    return get_tiktok_status()

def tiktok_gift_listener(username):
    global TIKTOK_STATUS
    def update_status(status, message):
        global TIKTOK_STATUS
        with TIKTOK_STATUS_LOCK:
            TIKTOK_STATUS = {'status': status, 'message': message, 'username': username}
    while True:
        try:
            from TikTokLive import TikTokLiveClient
            from TikTokLive.events import ConnectEvent, DisconnectEvent, GiftEvent
            client = TikTokLiveClient(unique_id=username)
            @client.on(ConnectEvent)
            async def on_connect(event):
                update_gift_catalog(getattr(client, 'gift_info', None))
                if TIKTOK_GIFT_ENABLED: update_status('connected', f'@{username} ギフト受信ON')
            @client.on(DisconnectEvent)
            async def on_disconnect(event):
                if TIKTOK_GIFT_ENABLED: update_status('reconnecting', 'TikTok LIVEとの接続が切れました。再接続します')
            @client.on(GiftEvent)
            async def on_gift(event):
                if not TIKTOK_GIFT_ENABLED:
                    return
                gift = getattr(event, 'gift', None)
                if gift is None:
                    update_status('connected', 'ギフトイベントを受信しましたが、ギフト名を取得できません')
                    return
                remember_gift(gift)
                gift_name = str(getattr(gift, 'name', '') or '').strip()
                if not gift_name:
                    update_status('connected', 'ギフトイベントを受信しましたが、ギフト名を取得できません')
                    return
                # Skip intermediate updates for streakable gifts; handle non-streak gifts immediately.
                gift_type = getattr(gift, 'type', None)
                if getattr(event, 'streaking', False) and gift_type in (None, 1):
                    return
                sender = getattr(event, 'user', None) or getattr(event, 'user_info', None)
                sender_name = str(_gift_value(sender, 'nickname', 'unique_id', 'uniqueId', 'username') or '').strip()
                avatar_url = _gift_image_url({'image':_gift_value(sender, 'avatar', 'avatar_thumb', 'avatarThumb', 'profile_picture', 'profilePicture')})
                gift_items = normalize_gift_catalog([gift])
                gift_info = gift_items[0] if gift_items else None
                matched = process_gift_event(gift_name, getattr(event, 'repeat_count', 1), sender_name, gift_info, avatar_url)
                if matched:
                    seconds = read_state().get('timer', {}).get('seconds', 0)
                    update_status('connected', f'ギフト反応: {gift_name}（タイマー／WINガチャ）')
                else:
                    update_status('connected', f'ギフト受信: {gift_name}（ギフト設定の名前と一致しません）')
            if TIKTOK_GIFT_ENABLED: update_status('connecting', f'@{username} のLIVEを待っています')
            client.run(fetch_gift_info=True)
            if TIKTOK_GIFT_ENABLED: update_status('reconnecting', 'LIVE接続が終了しました。再接続します')
        except Exception as error:
            if TIKTOK_GIFT_ENABLED: update_status('error', f'接続エラー: {error}')
        time.sleep(5)

def start_global_hotkeys():
    if os.name != 'nt':
        with HOTKEY_STATUS_LOCK:
            HOTKEY_STATUS.update(active=False, message='Windowsで起動するとグローバルショートカットを使えます')
        print('Global shortcuts are available when this app runs on Windows.')
        return
    def run():
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.WinDLL('user32', use_last_error=True)
        kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
        WH_KEYBOARD_LL = 13
        WM_KEYDOWN, WM_SYSKEYDOWN = 0x0100, 0x0104
        WM_KEYUP, WM_SYSKEYUP = 0x0101, 0x0105
        KEY_FLAGS = 0x8000
        VK_CONTROL, VK_SHIFT, VK_MENU = 0x11, 0x10, 0x12
        VK_LWIN, VK_RWIN = 0x5B, 0x5C
        class KBDLLHOOKSTRUCT(ctypes.Structure):
            _fields_ = [('vkCode', wintypes.DWORD), ('scanCode', wintypes.DWORD), ('flags', wintypes.DWORD), ('time', wintypes.DWORD), ('dwExtraInfo', ctypes.c_size_t)]
        HOOKPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
        get_async = user32.GetAsyncKeyState
        get_async.argtypes = [ctypes.c_int]
        get_async.restype = ctypes.c_short
        call_next = user32.CallNextHookEx
        call_next.argtypes = [wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
        call_next.restype = ctypes.c_ssize_t
        user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD]
        user32.SetWindowsHookExW.restype = wintypes.HHOOK
        get_module_handle = kernel32.GetModuleHandleW
        get_module_handle.argtypes = [wintypes.LPCWSTR]
        get_module_handle.restype = ctypes.c_void_p
        action_map = {}
        actions_lock = threading.Lock()
        action_queue = queue.Queue()
        pressed = set()
        def modifiers_down():
            mods = 0
            if get_async(VK_CONTROL) & KEY_FLAGS: mods |= 0x0002
            if get_async(VK_MENU) & KEY_FLAGS: mods |= 0x0001
            if get_async(VK_SHIFT) & KEY_FLAGS: mods |= 0x0004
            if (get_async(VK_LWIN) | get_async(VK_RWIN)) & KEY_FLAGS: mods |= 0x0008
            return mods
        def refresh_actions():
            nonlocal action_map
            try:
                # Read the settings under the same lock used by every state
                # writer. Otherwise the polling thread can see a half-written
                # JSON file and briefly replace the live key map with defaults.
                with STATE_LOCK:
                    data = json.loads(STATE.read_text(encoding='utf-8')) if STATE.exists() else copy.deepcopy(DEFAULT)
            except Exception:
                # Keep the last valid bindings if the file is temporarily
                # unavailable or invalid; the next poll will retry.
                return
            desired = {}
            for counter in data.get('counters', []):
                cid = str(counter.get('id') or counter.get('label') or '')
                for field, delta in (('shortcutAdd', 1), ('shortcutSub', -1)):
                    binding = str(counter.get(field) or '').upper()
                    if binding and binding not in desired: desired[binding] = {'type':'counter','id':cid,'delta':delta}
            for mission in data.get('missions', []):
                mid = str(mission.get('id') or '')
                for field, delta in (('shortcutAdd', 1), ('shortcutSub', -1)):
                    binding = str(mission.get(field) or '').upper()
                    if binding and binding not in desired: desired[binding] = {'type':'mission','id':mid,'delta':delta}
            win = data.get('winCounter', {})
            for field, delta in (('shortcutAdd', 1), ('shortcutSub', -1)):
                binding = str(win.get(field) or '').upper()
                if binding and binding not in desired: desired[binding] = {'type':'gacha','delta':delta}
            smoking=data.get('smokingTimer',{})
            for minutes in (5,10,15,30):
                for suffix,delta in (('Add',1),('Sub',-1)):
                    binding=str(smoking.get(f'shortcut{suffix}{minutes}') or '').upper()
                    if binding and binding not in desired: desired[binding]={'type':'smokingTimer','delta':minutes*60*delta}
            smoking_gacha=data.get('smokingGacha',{})
            for field,choice in (('shortcutPlus','plus'),('shortcutMinus','minus')):
                binding=str(smoking_gacha.get(field) or '').upper()
                if binding and binding not in desired: desired[binding]={'type':'smokingGachaChoice','choice':choice}
            gacha = data.get('gacha', {})
            for field, choice in (('shortcutChoicePlus','plus'), ('shortcutChoiceMinus','minus')):
                binding = str(gacha.get(field) or '').upper()
                if binding and binding not in desired: desired[binding] = {'type':'gachaChoice','choice':choice}
            compiled = {}
            for binding, action in desired.items():
                parsed = parse_shortcut(binding)
                if parsed: compiled[parsed] = action
            with actions_lock:
                action_map = compiled
            with HOTKEY_STATUS_LOCK:
                HOTKEY_STATUS['bindings'] = len(compiled)
        def refresh_worker():
            while True:
                refresh_actions()
                time.sleep(.4)
        def action_worker():
            while True:
                action = action_queue.get()
                try:
                    dispatch_hotkey_action(action)
                except Exception as error:
                    print(f'Global shortcut action error: {error}')
                finally:
                    action_queue.task_done()
        refresh_actions()
        threading.Thread(target=refresh_worker, daemon=True).start()
        threading.Thread(target=action_worker, daemon=True).start()
        @HOOKPROC
        def keyboard_proc(n_code, w_param, l_param):
            if n_code >= 0:
                try:
                    key = ctypes.cast(l_param, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents.vkCode
                    if w_param in (WM_KEYUP, WM_SYSKEYUP):
                        pressed.discard(key)
                    elif w_param in (WM_KEYDOWN, WM_SYSKEYDOWN) and key not in pressed:
                        pressed.add(key)
                        with actions_lock:
                            action = action_map.get((modifiers_down(), key))
                        if action:
                            action_queue.put_nowait(action)
                except Exception as error:
                    print(f'Global shortcut error: {error}')
            return call_next(None, n_code, w_param, l_param)
        hook = user32.SetWindowsHookExW(WH_KEYBOARD_LL, keyboard_proc, get_module_handle(None), 0)
        if not hook:
            error = ctypes.get_last_error()
            with HOTKEY_STATUS_LOCK:
                HOTKEY_STATUS.update(active=False, message=f'ショートカット監視を開始できません（Windowsエラー {error}）')
            print(f'Global shortcut hook could not start (Windows error {error}). Try running start.bat with the same privilege level as GTA.')
            return
        with HOTKEY_STATUS_LOCK:
            HOTKEY_STATUS.update(active=True, message='グローバルショートカット監視中')
        print('Global keyboard shortcuts are active.')
        msg = wintypes.MSG()
        while True:
            user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
    def guarded_run():
        try:
            run()
        except Exception as error:
            with HOTKEY_STATUS_LOCK:
                HOTKEY_STATUS.update(active=False, message=f'ショートカット監視エラー: {error}')
            print(f'Global shortcut monitor error: {error}')
    threading.Thread(target=guarded_run, daemon=True).start()

def get_hotkey_status():
    with HOTKEY_STATUS_LOCK:
        return dict(HOTKEY_STATUS)

def version_numbers(value):
    parts = re.findall(r'\d+', str(value or ''))
    return tuple(int(part) for part in (parts[:4] or ['0']))

def check_for_update():
    config_path = ROOT / 'update_config.json'
    if not config_path.exists():
        return {'configured': False}
    try:
        config = json.loads(config_path.read_text(encoding='utf-8'))
        owner = str(config.get('githubOwner') or '').strip()
        repository = str(config.get('githubRepository') or '').strip()
        if not owner or not repository:
            return {'configured': False}
        api_url = f'https://api.github.com/repos/{owner}/{repository}/releases/latest'
        request = urllib.request.Request(api_url, headers={'Accept': 'application/vnd.github+json', 'User-Agent': f'Live-Overlay-Studio/{APP_VERSION}'})
        with urllib.request.urlopen(request, timeout=8) as response:
            release = json.loads(response.read().decode('utf-8'))
        latest = str(release.get('tag_name') or release.get('name') or '').strip()
        page_url = str(release.get('html_url') or f'https://github.com/{owner}/{repository}/releases/latest')
        expected_asset = 'Live_Overlay_Studio_Windows_x64.exe'
        asset = next((item for item in release.get('assets', []) if item.get('name') == expected_asset), None)
        asset_url = str(asset.get('browser_download_url') or '') if asset else ''
        trusted_prefix = f'https://github.com/{owner}/{repository}/releases/download/'
        if asset_url and not asset_url.startswith(trusted_prefix):
            asset_url = ''
        return {
            'configured': True,
            'available': version_numbers(latest) > version_numbers(APP_VERSION) and bool(asset_url),
            'currentVersion': APP_VERSION,
            'latestVersion': latest or APP_VERSION,
            'pageUrl': page_url,
            'assetUrl': asset_url,
            'assetDigest': str(asset.get('digest') or '') if asset else '',
        }
    except Exception as error:
        return {'configured': True, 'error': str(error)}

class Handler(SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        # PyInstaller's --windowed mode has no sys.stderr.  The default
        # SimpleHTTPRequestHandler logger writes to stderr before sending the
        # HTTP response, which made every request close without a response in
        # the Windows EXE.  Request logging is unnecessary for the GUI app.
        return

    def end_headers(self):
        if getattr(self, 'path', '') != '/api/state':
            self.send_header('Cache-Control', 'no-store, max-age=0')
        super().end_headers()
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)
    def do_GET(self):
        if self.path == '/api/state':
            body = json.dumps(read_state(), ensure_ascii=False).encode('utf-8')
            self.send_response(200); self.send_header('Content-Type','application/json; charset=utf-8'); self.send_header('Cache-Control','no-store'); self.send_header('Content-Length',str(len(body))); self.end_headers(); self.wfile.write(body); return
        if self.path == '/api/tiktok/status':
            body = json.dumps(get_tiktok_status(), ensure_ascii=False).encode('utf-8')
            self.send_response(200); self.send_header('Content-Type','application/json; charset=utf-8'); self.send_header('Cache-Control','no-store'); self.send_header('Content-Length',str(len(body))); self.end_headers(); self.wfile.write(body); return
        if self.path == '/api/hotkeys/status':
            body = json.dumps(get_hotkey_status(), ensure_ascii=False).encode('utf-8')
            self.send_response(200); self.send_header('Content-Type','application/json; charset=utf-8'); self.send_header('Cache-Control','no-store'); self.send_header('Content-Length',str(len(body))); self.end_headers(); self.wfile.write(body); return
        if self.path == '/api/tiktok/gifts':
            with TIKTOK_GIFT_CATALOG_LOCK:
                gifts = copy.deepcopy(TIKTOK_GIFT_CATALOG)
            status = get_tiktok_status()
            body = json.dumps({'gifts': gifts, 'connected': status.get('status') == 'connected', 'enabled': status.get('enabled', False)}, ensure_ascii=False).encode('utf-8')
            self.send_response(200); self.send_header('Content-Type','application/json; charset=utf-8'); self.send_header('Cache-Control','no-store'); self.send_header('Content-Length',str(len(body))); self.end_headers(); self.wfile.write(body); return
        return super().do_GET()
    def do_POST(self):
        if self.path not in ('/api/state', '/api/giftwall/reset-display', '/api/giftwall/restore-display', '/api/tiktok/connect', '/api/tiktok/toggle', '/api/gift/test', '/api/smoking-audio', '/api/win-image', '/api/gacha-audio', '/api/gacha-result-audio', '/api/gacha-animation', '/api/gacha-end-audio', '/api/gacha-end-animation', '/api/gacha/test', '/api/gacha/apply-round', '/api/gacha/choose-sign', '/api/gacha/choice-ready', '/api/gacha/complete', '/api/smoking-gacha-animation', '/api/smoking-gacha-audio', '/api/smoking-gacha-result-audio', '/api/smoking-gacha/test', '/api/smoking-gacha/choice-ready', '/api/smoking-gacha/choose-sign', '/api/smoking-gacha/complete'):
            self.send_error(404); return
        try:
            n = int(self.headers.get('Content-Length','0'))
            data = json.loads(self.rfile.read(n))
            if self.path == '/api/giftwall/reset-display':
                if self.client_address[0] not in ('127.0.0.1','::1'):
                    self.send_error(403); return
                with STATE_LOCK:
                    try:
                        current=json.loads(STATE.read_text(encoding='utf-8'))
                    except Exception:
                        current=copy.deepcopy(DEFAULT)
                    current,_=normalize_state(current)
                    current['giftWall']['displayHistory']=[]
                    STATE.write_text(json.dumps(current,ensure_ascii=False,indent=2),encoding='utf-8')
                result={'ok':True,'historyCount':len(current['giftWall'].get('history',[]))}
            elif self.path == '/api/giftwall/restore-display':
                if self.client_address[0] not in ('127.0.0.1','::1'):
                    self.send_error(403); return
                with STATE_LOCK:
                    try:
                        current=json.loads(STATE.read_text(encoding='utf-8'))
                    except Exception:
                        current=copy.deepcopy(DEFAULT)
                    current,_=normalize_state(current)
                    wall=current['giftWall']; threshold=wall['minCoins']
                    wall['displayHistory']=[copy.deepcopy(item) for item in wall.get('history',[]) if item.get('totalCoins',0)>=threshold][:200]
                    STATE.write_text(json.dumps(current,ensure_ascii=False,indent=2),encoding='utf-8')
                result={'ok':True,'displayCount':len(wall['displayHistory']),'historyCount':len(wall.get('history',[]))}
            elif self.path == '/api/state':
                manual_win_value = bool(data.pop('_manualWinCounterValue', False))
                # Apply control-panel settings and live gift events as one
                # transaction. A stale control-page snapshot must never erase
                # history received since that page was opened.
                with STATE_LOCK:
                    try:
                        current_raw=json.loads(STATE.read_text(encoding='utf-8'))
                    except Exception:
                        current_raw=copy.deepcopy(DEFAULT)
                    current,_=normalize_state(current_raw)
                    if isinstance(data.get('timer'), dict):
                        data['timer']['currentText'] = current.get('timer', {}).get('currentText', data['timer'].get('currentText', ''))
                        data['timer']['giftName'] = current.get('timer', {}).get('giftName', data['timer'].get('giftName', ''))
                    if isinstance(data.get('winCounter'),dict) and not manual_win_value:
                        data['winCounter']['currentWin']=current.get('winCounter',{}).get('currentWin',data['winCounter'].get('currentWin',0))
                    if isinstance(data.get('gacha'),dict):
                        live_gacha=current.get('gacha',{})
                        data['gacha']['event']=live_gacha.get('event',{})
                        data['gacha']['queue']=live_gacha.get('queue',[])
                        # A stale control-page save must not erase history that
                        # the overlay appended after the page's last refresh.
                        data['gacha']['history']=copy.deepcopy(live_gacha.get('history',[]))
                    if isinstance(data.get('smokingGacha'),dict):
                        data['smokingGacha']['event']=current.get('smokingGacha',{}).get('event',{})
                        data['smokingGacha']['queue']=current.get('smokingGacha',{}).get('queue',[])
                    if isinstance(data.get('giftWall'),dict):
                        live_wall=current.get('giftWall',DEFAULT['giftWall'])
                        data['giftWall']={**live_wall,**data['giftWall'],
                            'history':copy.deepcopy(live_wall.get('history',[])),
                            'displayHistory':copy.deepcopy(live_wall.get('displayHistory',[])),
                            'nextId':live_wall.get('nextId',1)}
                    merged,_=normalize_state({**copy.deepcopy(DEFAULT),**data})
                    STATE.write_text(json.dumps(merged,ensure_ascii=False,indent=2),encoding='utf-8')
                result = {'ok': True}
            elif self.path == '/api/smoking-audio':
                if self.client_address[0] not in ('127.0.0.1', '::1'):
                    self.send_error(403); return
                match = re.fullmatch(r'data:audio/(wav|x-wav|mpeg|mp3|ogg|mp4|m4a|aac|webm);base64,([A-Za-z0-9+/=]+)', str(data.get('dataUrl') or ''))
                if not match:
                    raise ValueError('MP3、WAV、OGG、MP4、WebM形式の音源を選択してください')
                audio = base64.b64decode(match.group(2), validate=True)
                if not audio or len(audio) > 15 * 1024 * 1024:
                    raise ValueError('音源は15MB以下にしてください')
                ext = {'mpeg':'mp3','mp4':'m4a','m4a':'m4a','x-wav':'wav'}.get(match.group(1), match.group(1))
                filename = 'smoking_alarm.' + ext
                (ROOT / filename).write_bytes(audio)
                state = read_state()
                state['smokingTimer']['audioUrl'] = '/' + filename
                state['smokingTimer']['audioName'] = Path(str(data.get('name') or filename)).name[:120]
                write_state(state)
                result = {'ok': True, 'smokingTimer': read_state()['smokingTimer']}
            elif self.path == '/api/win-image':
                if self.client_address[0] not in ('127.0.0.1', '::1'):
                    self.send_error(403); return
                state = read_state()
                if bool(data.get('clear')):
                    state['winCounter']['imageUrl'] = ''
                    state['winCounter']['imageName'] = ''
                else:
                    match = re.fullmatch(r'data:image/(png|jpeg|webp|gif);base64,([A-Za-z0-9+/=]+)', str(data.get('dataUrl') or ''))
                    if not match:
                        raise ValueError('PNG、JPG、WebP、GIF形式の画像を選択してください')
                    raw = base64.b64decode(match.group(2), validate=True)
                    if not raw or len(raw) > 10 * 1024 * 1024:
                        raise ValueError('画像は10MB以下にしてください')
                    ext = 'jpg' if match.group(1) == 'jpeg' else match.group(1)
                    filename = 'win_counter_image.' + ext
                    for old in ROOT.glob('win_counter_image.*'):
                        if old.is_file() and old.name != filename:
                            old.unlink(missing_ok=True)
                    (ROOT / filename).write_bytes(raw)
                    # Keep the filename stable for migration, but change the
                    # URL on every upload so browser sources cannot reuse the
                    # previous image from memory or disk cache.
                    state['winCounter']['imageUrl'] = '/' + filename + '?v=' + str(safe_int(time.time() * 1000))
                    state['winCounter']['imageName'] = Path(str(data.get('name') or filename)).name[:120]
                    state['winCounter']['imageEnabled'] = True
                write_state(state)
                result = {'ok': True, 'winCounter': read_state()['winCounter']}
            elif self.path == '/api/gacha-audio':
                if self.client_address[0] not in ('127.0.0.1', '::1'):
                    self.send_error(403); return
                match = re.fullmatch(r'data:audio/(wav|x-wav|mpeg|mp3|ogg|mp4|m4a|aac|webm);base64,([A-Za-z0-9+/=]+)', str(data.get('dataUrl') or ''))
                if not match:
                    raise ValueError('MP3、WAV、OGG、M4A、AAC、WebM形式の音源を選択してください')
                raw = base64.b64decode(match.group(2), validate=True)
                if not raw or len(raw) > 15 * 1024 * 1024:
                    raise ValueError('音源は15MB以下にしてください')
                ext = {'mpeg':'mp3','mp4':'m4a','m4a':'m4a','x-wav':'wav'}.get(match.group(1), match.group(1))
                pattern_id = str(data.get('patternId') or '')
                safe_id = re.sub(r'[^A-Za-z0-9_-]', '_', pattern_id)[:80]
                stage = str(data.get('stage') or 'normal')
                stage_prefixes = {'upperEntry':'gacha_upper_entry_audio_','upperAT':'gacha_upper_audio_','normalContinue':'gacha_continue_audio_','upperContinue':'gacha_upper_continue_audio_'}
                prefix = stage_prefixes.get(stage, 'gacha_audio_')
                filename = (prefix + safe_id if safe_id else prefix.rstrip('_')) + '.' + ext
                (ROOT / filename).write_bytes(raw)
                state = read_state()
                pattern = next((item for item in state['gacha']['patterns'] if item['id'] == pattern_id), None) if pattern_id else None
                target = pattern if pattern is not None else state['gacha']
                url_key = {'upperEntry':'upperEntryAudioUrl','upperAT':'upperAtAudioUrl','normalContinue':'continueAudioUrl','upperContinue':'upperContinueAudioUrl'}.get(stage, 'audioUrl')
                name_key = {'upperEntry':'upperEntryAudioName','upperAT':'upperAtAudioName','normalContinue':'continueAudioName','upperContinue':'upperContinueAudioName'}.get(stage, 'audioName')
                target[url_key] = '/' + filename + '?v=' + str(safe_int(time.time() * 1000))
                target[name_key] = Path(str(data.get('name') or filename)).name[:120]
                write_state(state)
                result = {'ok': True, 'gacha': read_state()['gacha']}
            elif self.path == '/api/gacha-result-audio':
                if self.client_address[0] not in ('127.0.0.1','::1'): self.send_error(403); return
                match=re.fullmatch(r'data:audio/(wav|x-wav|mpeg|mp3|ogg|mp4|m4a|aac|webm);base64,([A-Za-z0-9+/=]+)',str(data.get('dataUrl') or ''))
                if not match: raise ValueError('MP3、WAV、OGG、M4A、AAC、WebM形式の結果音源を選択してください')
                raw=base64.b64decode(match.group(2),validate=True)
                if not raw or len(raw)>15*1024*1024: raise ValueError('結果音源は15MB以下にしてください')
                ext={'mpeg':'mp3','mp4':'m4a','m4a':'m4a','x-wav':'wav'}.get(match.group(1),match.group(1));pattern_id=str(data.get('patternId') or '');safe_id=re.sub(r'[^A-Za-z0-9_-]','_',pattern_id)[:80]
                filename='gacha_result'+('_'+safe_id if safe_id else '')+'.'+ext;(ROOT/filename).write_bytes(raw)
                state=read_state();pattern=next((item for item in state['gacha']['patterns'] if item['id']==pattern_id),None) if pattern_id else None;target=pattern if pattern is not None else state['gacha'];target['resultAudioUrl']='/'+filename+'?v='+str(safe_int(time.time()*1000));target['resultAudioName']=Path(str(data.get('name') or filename)).name[:120];write_state(state)
                result={'ok':True,'gacha':read_state()['gacha']}
            elif self.path in ('/api/gacha-end-animation', '/api/gacha-end-audio'):
                if self.client_address[0] not in ('127.0.0.1', '::1'):
                    self.send_error(403); return
                state=read_state();pattern_id=str(data.get('patternId') or '');pattern=next((item for item in state['gacha']['patterns'] if item['id']==pattern_id),None) if pattern_id else None;target=pattern if pattern is not None else state['gacha'];safe_id=re.sub(r'[^A-Za-z0-9_-]','_',pattern_id)[:80]
                if self.path == '/api/gacha-end-animation':
                    match=re.fullmatch(r'data:(image/(gif|png|jpeg|webp)|video/(mp4|webm));base64,([A-Za-z0-9+/=]+)',str(data.get('dataUrl') or ''))
                    if not match:raise ValueError('終了素材はGIF、PNG、JPG、WebP、MP4、WebM形式にしてください')
                    raw=base64.b64decode(match.group(4),validate=True)
                    if not raw or len(raw)>30*1024*1024:raise ValueError('終了素材は30MB以下にしてください')
                    ext={'jpeg':'jpg'}.get(match.group(2) or match.group(3),match.group(2) or match.group(3));filename='gacha_end'+('_'+safe_id if safe_id else '')+'.'+ext;(ROOT/filename).write_bytes(raw);target['endAnimationUrl']='/'+filename+'?v='+str(safe_int(time.time()*1000));target['endAnimationName']=Path(str(data.get('name') or filename)).name[:120]
                else:
                    match=re.fullmatch(r'data:audio/(wav|x-wav|mpeg|mp3|ogg|mp4|m4a|aac|webm);base64,([A-Za-z0-9+/=]+)',str(data.get('dataUrl') or ''))
                    if not match:raise ValueError('終了音源はMP3、WAV、OGG、M4A、AAC、WebM形式にしてください')
                    raw=base64.b64decode(match.group(2),validate=True)
                    if not raw or len(raw)>15*1024*1024:raise ValueError('終了音源は15MB以下にしてください')
                    ext={'mpeg':'mp3','mp4':'m4a','m4a':'m4a','x-wav':'wav'}.get(match.group(1),match.group(1));filename='gacha_end_audio'+('_'+safe_id if safe_id else '')+'.'+ext;(ROOT/filename).write_bytes(raw);target['endAudioUrl']='/'+filename+'?v='+str(safe_int(time.time()*1000));target['endAudioName']=Path(str(data.get('name') or filename)).name[:120]
                write_state(state);result={'ok':True,'gacha':read_state()['gacha']}
            elif self.path == '/api/gacha-animation':
                if self.client_address[0] not in ('127.0.0.1', '::1'):
                    self.send_error(403); return
                match = re.fullmatch(r'data:(image/(gif|png|jpeg|webp)|video/(mp4|webm));base64,([A-Za-z0-9+/=]+)', str(data.get('dataUrl') or ''))
                if not match:
                    raise ValueError('GIF、PNG、JPG、WebP、MP4、WebM形式にしてください')
                raw = base64.b64decode(match.group(4), validate=True)
                if not raw or len(raw) > 30 * 1024 * 1024:
                    raise ValueError('アニメーション素材は30MB以下にしてください')
                ext=(match.group(2) or match.group(3));ext={'jpeg':'jpg'}.get(ext,ext)
                pattern_id = str(data.get('patternId') or '')
                safe_id = re.sub(r'[^A-Za-z0-9_-]', '_', pattern_id)[:80]
                stage = str(data.get('stage') or 'normal')
                stage_prefixes = {'upperEntry':'gacha_upper_entry_animation_','upperAT':'gacha_upper_animation_','normalContinue':'gacha_continue_animation_','upperContinue':'gacha_upper_continue_animation_'}
                prefix = stage_prefixes.get(stage, 'gacha_animation_')
                filename=(prefix + safe_id if safe_id else prefix.rstrip('_'))+'.'+ext
                (ROOT/filename).write_bytes(raw)
                state=read_state();pattern=next((item for item in state['gacha']['patterns'] if item['id']==pattern_id),None) if pattern_id else None;target=pattern if pattern is not None else state['gacha'];url_key={'upperEntry':'upperEntryAnimationUrl','upperAT':'upperAtAnimationUrl','normalContinue':'continueAnimationUrl','upperContinue':'upperContinueAnimationUrl'}.get(stage,'animationUrl');name_key={'upperEntry':'upperEntryAnimationName','upperAT':'upperAtAnimationName','normalContinue':'continueAnimationName','upperContinue':'upperContinueAnimationName'}.get(stage,'animationName');target[url_key]='/'+filename+'?v='+str(safe_int(time.time()*1000));target[name_key]=Path(str(data.get('name') or filename)).name[:120];write_state(state)
                result={'ok':True,'gacha':read_state()['gacha']}
            elif self.path == '/api/gacha/test':
                if self.client_address[0] not in ('127.0.0.1', '::1'):
                    self.send_error(403); return
                state=read_state();pattern=next((x for x in state['gacha']['patterns'] if x['id']==str(data.get('patternId') or '')),None)
                if not pattern:
                    raise ValueError('テストするパターンを選べません')
                run_gacha_draw(state,pattern,'テスト','テスト')
                write_state(state);result={'ok':True}
            elif self.path in ('/api/smoking-gacha-animation','/api/smoking-gacha-audio','/api/smoking-gacha-result-audio'):
                if self.client_address[0] not in ('127.0.0.1','::1'): self.send_error(403); return
                state=read_state();sg=state['smokingGacha'];pattern_id=str(data.get('patternId') or '')
                pattern=next((x for x in sg['patterns'] if x['id']==pattern_id),None) if pattern_id else None;target=pattern if pattern is not None else sg
                if self.path.endswith('animation'):
                    match=re.fullmatch(r'data:(image/(gif|png|jpeg|webp)|video/(mp4|webm));base64,([A-Za-z0-9+/=]+)',str(data.get('dataUrl') or ''))
                    if not match: raise ValueError('GIF、PNG、JPG、WebP、MP4、WebM形式の演出素材を選択してください')
                    raw=base64.b64decode(match.group(4),validate=True)
                    if not raw or len(raw)>30*1024*1024: raise ValueError('演出素材は30MB以下にしてください')
                    ext={'jpeg':'jpg'}.get(match.group(2) or match.group(3),match.group(2) or match.group(3));kind='animation'
                else:
                    match=re.fullmatch(r'data:audio/(wav|x-wav|mpeg|mp3|ogg|mp4|m4a|aac|webm);base64,([A-Za-z0-9+/=]+)',str(data.get('dataUrl') or ''))
                    if not match: raise ValueError('MP3、WAV、OGG、M4A、AAC、WebM形式の音源を選択してください')
                    raw=base64.b64decode(match.group(2),validate=True)
                    if not raw or len(raw)>15*1024*1024: raise ValueError('音源は15MB以下にしてください')
                    ext={'mpeg':'mp3','mp4':'m4a','m4a':'m4a','x-wav':'wav'}.get(match.group(1),match.group(1));kind='resultAudio' if self.path.endswith('result-audio') else 'audio'
                safe_id=re.sub(r'[^A-Za-z0-9_-]','_',pattern_id)[:80]
                filename='smoking_gacha_'+kind+('_'+safe_id if safe_id else '')+'.'+ext;(ROOT/filename).write_bytes(raw)
                target[kind+'Url']='/'+filename;target[kind+'Name']=Path(str(data.get('name') or filename)).name[:120]
                write_state(state);result={'ok':True,'smokingGacha':read_state()['smokingGacha']}
            elif self.path == '/api/smoking-gacha/test':
                if self.client_address[0] not in ('127.0.0.1','::1'): self.send_error(403); return
                state=read_state();pattern=next((x for x in state['smokingGacha']['patterns'] if x['id']==str(data.get('patternId') or '')),None)
                if not pattern: raise ValueError('テストする禁煙ガチャを選択してください')
                run_smoking_gacha_draw(state,pattern,'テスト',True);write_state(state)
                result={'ok':True,'smokingGacha':read_state()['smokingGacha']}
            elif self.path == '/api/smoking-gacha/choice-ready':
                result={'ok':mark_smoking_gacha_choice_ready(int(data.get('eventId') or 0))}
            elif self.path == '/api/smoking-gacha/choose-sign':
                result={'ok':choose_smoking_gacha_sign(int(data.get('eventId') or 0),str(data.get('choice') or ''))}
            elif self.path == '/api/smoking-gacha/complete':
                result={'ok':complete_smoking_gacha_event(int(data.get('eventId') or 0))}
            elif self.path == '/api/gacha/apply-round':
                ok=apply_gacha_round(int(data.get('eventId') or 0),int(data.get('roundIndex') or 0))
                result={'ok':ok}
            elif self.path == '/api/gacha/choose-sign':
                ok=choose_gacha_sign(int(data.get('eventId') or 0),str(data.get('choice') or ''))
                result={'ok':ok}
            elif self.path == '/api/gacha/choice-ready':
                result={'ok':mark_gacha_choice_ready(int(data.get('eventId') or 0))}
            elif self.path == '/api/gacha/complete':
                result={'ok':complete_gacha_event(int(data.get('eventId') or 0))}
            elif self.path == '/api/tiktok/connect':
                result = start_tiktok_gift_listener(read_state().get('tiktokUsername', ''))
                if result.get('status') == 'error':
                    body = json.dumps(result, ensure_ascii=False).encode('utf-8')
                    self.send_response(400); self.send_header('Content-Type','application/json; charset=utf-8'); self.send_header('Content-Length',str(len(body))); self.end_headers(); self.wfile.write(body); return
            elif self.path == '/api/tiktok/toggle':
                result=start_tiktok_gift_listener(read_state().get('tiktokUsername','')) if bool(data.get('enabled')) else stop_tiktok_gift_listener()
            else:
                if self.client_address[0] not in ('127.0.0.1', '::1'):
                    self.send_error(403); return
                result = {'ok': process_gift_event(data.get('giftName', ''), 1)}
            body = json.dumps(result, ensure_ascii=False).encode('utf-8')
            self.send_response(200); self.send_header('Content-Type','application/json; charset=utf-8'); self.send_header('Content-Length',str(len(body))); self.end_headers(); self.wfile.write(body)
        except Exception as e:
            self.send_error(400, str(e))

class LocalThreadingHTTPServer(ThreadingHTTPServer):
    # Allow the app to be reopened immediately after it was closed.  Windows
    # can otherwise keep port 8765 reserved briefly and make the browser show
    # an error page even though the desktop window opened normally.
    allow_reuse_address = True

def run_desktop_app(server):
    import tkinter as tk
    from tkinter import messagebox

    control_url = 'http://127.0.0.1:8765/control.html'
    overlay_url = 'http://127.0.0.1:8765/overlay.html?build=664'
    window = tk.Tk()
    window.title('Live Overlay Studio')
    window.geometry('560x400')
    window.minsize(500, 300)
    window.configure(bg='#17181e')

    title = tk.Label(window, text='Live Overlay Studio', bg='#17181e', fg='#ffffff', font=('Segoe UI', 20, 'bold'))
    title.pack(pady=(24, 8))
    status = tk.Label(window, text=f'● 起動準備中  v{APP_VERSION}  ポート 8765', bg='#17181e', fg='#ffe38a', font=('Segoe UI', 11, 'bold'))
    status.pack(pady=(0, 10))
    update_status = tk.Label(window, text='更新を確認しています…', bg='#17181e', fg='#b8bbc7', font=('Segoe UI', 9))
    update_status.pack(pady=(0, 10))

    def button(text, command):
        return tk.Button(window, text=text, command=command, bg='#e52b3c', fg='white', activebackground='#ff4d5d', activeforeground='white', relief='flat', font=('Segoe UI', 11, 'bold'), padx=18, pady=9, cursor='hand2')

    def launch_browser(url):
        try:
            if os.name == 'nt':
                os.startfile(url)
            else:
                webbrowser.open_new_tab(url)
        except Exception as error:
            status.configure(text='● ブラウザーを開けません', fg='#ff7d8a')
            messagebox.showerror('ブラウザー起動エラー', f'既定のブラウザーを開けませんでした。\n\n{error}\n\nURL:\n{url}')

    def open_when_ready(url, show_error=True):
        status.configure(text=f'● 操作画面を準備中  v{APP_VERSION}', fg='#ffe38a')
        def worker():
            last_error = ''
            for _ in range(30):
                try:
                    with urllib.request.urlopen('http://127.0.0.1:8765/api/state', timeout=.5) as response:
                        if response.status == 200:
                            window.after(0, lambda: status.configure(text=f'● 起動中  v{APP_VERSION}  ポート 8765', fg='#6ee7a8'))
                            window.after(0, lambda: launch_browser(url))
                            return
                except Exception as error:
                    last_error = str(error)
                    time.sleep(.2)
            window.after(0, lambda: status.configure(text='● ローカルサーバー起動エラー', fg='#ff7d8a'))
            if show_error:
                window.after(0, lambda: messagebox.showerror(
                    '操作画面を開けません',
                    'ローカルサーバーが応答しませんでした。\n'
                    'アプリを一度終了し、再起動してください。\n\n'
                    f'詳細: {last_error or "不明なエラー"}'
                ))
        threading.Thread(target=worker, daemon=True).start()

    button('操作画面を開く', lambda: open_when_ready(control_url)).pack(pady=5)
    button('全体オーバーレイを開く', lambda: open_when_ready(overlay_url)).pack(pady=5)

    def copy_url():
        window.clipboard_clear()
        window.clipboard_append(overlay_url)
        window.update()
        messagebox.showinfo('コピー完了', '全体オーバーレイURLをコピーしました。')

    copy_button = tk.Button(window, text='オーバーレイURLをコピー', command=copy_url, bg='#343641', fg='white', activebackground='#4a4d5a', activeforeground='white', relief='flat', font=('Segoe UI', 10), padx=14, pady=7, cursor='hand2')
    copy_button.pack(pady=5)
    update_info = {'url': '', 'assetUrl': '', 'digest': '', 'version': ''}
    update_button = tk.Button(window, text='更新して再起動', command=lambda: download_update(), bg='#7567dc', fg='white', activebackground='#8b79ff', activeforeground='white', relief='flat', font=('Segoe UI', 10, 'bold'), padx=14, pady=7, cursor='hand2')

    def ps_quote(value):
        return "'" + str(value).replace("'", "''") + "'"

    def apply_downloaded_update(staged_path):
        target_path = Path(sys.executable).resolve()
        script = (
            "$ErrorActionPreference='Stop'\n"
            f"$target={ps_quote(target_path)}\n"
            f"$staged={ps_quote(staged_path)}\n"
            f"$targetProcessId={os.getpid()}\n"
            "$log=Join-Path $env:LOCALAPPDATA 'LiveOverlayStudio\\update.log'\n"
            "try {\n"
            "  for ($i=0; $i -lt 180 -and (Get-Process -Id $targetProcessId -ErrorAction SilentlyContinue); $i++) { Start-Sleep -Seconds 1 }\n"
            "  if (Get-Process -Id $targetProcessId -ErrorAction SilentlyContinue) { throw 'アプリの終了を確認できませんでした。' }\n"
            "  Start-Sleep -Milliseconds 500\n"
            "  Copy-Item -LiteralPath $staged -Destination $target -Force\n"
            "  Start-Process -FilePath $target\n"
            "  Remove-Item -LiteralPath $staged -Force -ErrorAction SilentlyContinue\n"
            "} catch {\n"
            "  $_ | Out-File -LiteralPath $log -Encoding utf8\n"
            "  try { Add-Type -AssemblyName PresentationFramework; [System.Windows.MessageBox]::Show(('更新に失敗しました。アプリを置いたフォルダーに書き込み権限があるか確認してください。' + [Environment]::NewLine + $_.Exception.Message), 'Live Overlay Studio') | Out-Null } catch {}\n"
            "  if (Test-Path -LiteralPath $target) { Start-Process -FilePath $target }\n"
            "}\n"
        )
        encoded = base64.b64encode(script.encode('utf-16le')).decode('ascii')
        try:
            subprocess.Popen(
                ['powershell.exe', '-NoProfile', '-WindowStyle', 'Hidden', '-ExecutionPolicy', 'Bypass', '-EncodedCommand', encoded],
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
            )
        except Exception as error:
            messagebox.showerror('更新できません', f'更新処理を開始できませんでした。\n\n{error}')
            return
        status.configure(text='● 更新を適用して再起動しています…', fg='#ffe38a')
        server.shutdown()
        server.server_close()
        window.destroy()

    def download_update():
        if not FROZEN_APP:
            messagebox.showinfo('Windowsアプリ版が必要です', '自動更新はWindowsアプリ（EXE）版で利用できます。ZIP版は手動で差し替えてください。')
            return
        asset_url = update_info.get('assetUrl') or ''
        if not asset_url:
            messagebox.showerror('更新ファイルがありません', 'GitHubリリースにWindows版EXEがまだ添付されていません。しばらくしてから再確認してください。')
            return
        update_button.configure(state='disabled')
        update_status.configure(text='更新ファイルをダウンロードしています…', fg='#ffe38a')

        def worker():
            temp_path = None
            try:
                app_root = Path(os.environ.get('LOCALAPPDATA') or Path.home()) / 'LiveOverlayStudio'
                app_root.mkdir(parents=True, exist_ok=True)
                fd, name = tempfile.mkstemp(prefix='LiveOverlayStudio-update-', suffix='.exe.part', dir=str(app_root))
                os.close(fd)
                temp_path = Path(name)
                digest = hashlib.sha256()
                request = urllib.request.Request(asset_url, headers={'User-Agent': f'Live-Overlay-Studio/{APP_VERSION}'})
                with urllib.request.urlopen(request, timeout=60) as response, temp_path.open('wb') as output:
                    while True:
                        block = response.read(1024 * 1024)
                        if not block:
                            break
                        digest.update(block)
                        output.write(block)
                expected = update_info.get('digest') or ''
                if expected.startswith('sha256:') and digest.hexdigest().lower() != expected.split(':', 1)[1].lower():
                    raise ValueError('ダウンロードした更新ファイルのチェックサムが一致しません。')
                staged = temp_path.with_suffix('')
                os.replace(temp_path, staged)
                temp_path = None
                window.after(0, lambda: apply_downloaded_update(staged))
            except Exception as error:
                if temp_path:
                    try: temp_path.unlink(missing_ok=True)
                    except Exception: pass
                error_text = str(error)
                window.after(0, lambda error_text=error_text: (update_button.configure(state='normal'), update_status.configure(text='更新をダウンロードできませんでした', fg='#ff7d8a'), messagebox.showerror('更新できません', error_text)))
        threading.Thread(target=worker, daemon=True).start()

    def show_update_result(result):
        if result.get('available'):
            update_info.update({'url': result.get('pageUrl', ''), 'assetUrl': result.get('assetUrl', ''), 'digest': result.get('assetDigest', ''), 'version': result.get('latestVersion', '')})
            update_status.configure(text=f"新しいバージョン {result.get('latestVersion')} があります", fg='#ffe38a')
            update_button.pack(pady=5)
        elif result.get('configured') and result.get('latestVersion') and version_numbers(result.get('latestVersion')) > version_numbers(APP_VERSION):
            update_status.configure(text=f"新しいバージョン {result.get('latestVersion')} を準備中です", fg='#ffe38a')
        elif result.get('configured') and not result.get('error'):
            update_status.configure(text='最新バージョンです', fg='#6ee7a8')
        elif result.get('error'):
            update_status.configure(text='更新情報を確認できませんでした', fg='#b8bbc7')
        else:
            update_status.configure(text='更新配布先の設定待ちです', fg='#b8bbc7')

    def update_worker():
        result = check_for_update()
        window.after(0, lambda: show_update_result(result))

    threading.Thread(target=update_worker, daemon=True).start()
    note = tk.Label(window, text='この画面を閉じるとオーバーレイも終了します。\n最小化したまま配信できます。', bg='#17181e', fg='#b8bbc7', font=('Segoe UI', 9), justify='center')
    note.pack(pady=(14, 0))

    def close_app():
        if messagebox.askokcancel('終了', 'Live Overlay Studioを終了しますか？'):
            server.shutdown()
            server.server_close()
            window.destroy()

    window.protocol('WM_DELETE_WINDOW', close_app)
    def server_worker():
        try:
            server.serve_forever()
        except Exception as error:
            window.after(0, lambda: status.configure(text='● ローカルサーバー停止', fg='#ff7d8a'))
            window.after(0, lambda: messagebox.showerror('サーバーエラー', str(error)))

    threading.Thread(target=server_worker, daemon=True).start()
    window.after(300, lambda: open_when_ready(control_url, show_error=False))
    window.mainloop()

def main():
    start_global_hotkeys()
    try:
        # Every page is used only by this PC, so listening on localhost avoids
        # firewall prompts and accidental access from other devices.
        server = LocalThreadingHTTPServer(('127.0.0.1', 8765), Handler)
    except OSError:
        # A second launch should focus the already running app instead of failing.
        webbrowser.open('http://127.0.0.1:8765/control.html')
        return
    if FROZEN_APP and os.name == 'nt':
        run_desktop_app(server)
        return
    if os.name == 'nt':
        threading.Timer(1.5, lambda: webbrowser.open('http://127.0.0.1:8765/control.html')).start()
    print('Live Overlay Studio running: http://127.0.0.1:8765/control.html')
    print('Overlay source: http://127.0.0.1:8765/overlay.html')
    server.serve_forever()

if __name__ == '__main__':
    main()
