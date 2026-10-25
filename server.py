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
import socket

APP_VERSION = '0.66.42'
SOURCE_ROOT = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent))
FROZEN_APP = bool(getattr(sys, 'frozen', False))

def get_lan_ip():
    """Return this PC's IPv4 LAN address for LIVE Studio browser sources."""
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(('8.8.8.8', 80))
        address = probe.getsockname()[0]
        if address and not address.startswith('127.'):
            return address
    except OSError:
        pass
    finally:
        probe.close()
    try:
        address = socket.gethostbyname(socket.gethostname())
        if address and not address.startswith('127.'):
            return address
    except OSError:
        pass
    return '127.0.0.1'

LAN_IP = get_lan_ip()

def prepare_app_root():
    if not FROZEN_APP:
        source_root = Path(__file__).resolve().parent
        # A test/source build should reuse the installed app's saved settings
        # on its first launch, while leaving the original app data untouched.
        local_base = Path(os.environ.get('LOCALAPPDATA') or Path.home())
        installed_root = local_base / 'LiveOverlayStudio'
        source_state = source_root / 'state.json'
        installed_state = installed_root / 'state.json'
        if not source_state.exists() and installed_state.exists():
            try:
                shutil.copy2(installed_state, source_state)
                media_prefixes = ('smoking_alarm.', 'gacha_', 'pachinko_', 'smoking_gacha_', 'other_gacha_', 'gift_media_', 'win_counter_')
                for item in installed_root.iterdir():
                    if item.is_file() and item.name.startswith(media_prefixes):
                        shutil.copy2(item, source_root / item.name)
            except OSError as error:
                print(f'Could not copy existing settings into test folder: {error}')
        return source_root
    local_base = Path(os.environ.get('LOCALAPPDATA') or Path.home())
    app_root = local_base / 'LiveOverlayStudio'
    app_root.mkdir(parents=True, exist_ok=True)
    # Preserve the existing file before this release normalizes saved settings.
    saved_state = app_root / 'state.json'
    recovery_backup = app_root / f'state_before_{APP_VERSION}.json'
    if saved_state.exists() and not recovery_backup.exists():
        try:
            shutil.copy2(saved_state, recovery_backup)
        except OSError as error:
            print(f'Could not back up settings before update: {error}')
    assets = [
        'control.html', 'overlay.html', 'overlay_comp.html',
        'overlay_counters.html', 'overlay_gacha.html', 'overlay_other_gacha.html',
        'overlay_gacha_history.html', 'overlay_gacha_ranking.html', 'overlay_gacha_set_ranking.html',
        'overlay_gacha_win_ranking.html', 'overlay_gacha_rankings.html', 'overlay_gift_history.html',
        'overlay_missions.html', 'overlay_gift_media.html', 'overlay_smoking.html',
        'overlay_smoking_gacha.html', 'overlay_timer.html', 'overlay_pachinko.html',
        'overlay_win.html', 'v6608.js', 'README.txt', 'update_config.json', 'app_icon.ico'
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
        media_prefixes = ('smoking_alarm.', 'gacha_', 'smoking_gacha_', 'other_gacha_', 'gift_media_', 'win_counter_image.')
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
        try:
            # The app may already have an older managed EXE in LocalAppData.
            # Always replace it with the explicitly launched build so a new
            # release does not silently reopen the old version forever.
            shutil.copy2(current_exe, managed_exe)
        except OSError as error:
            try:
                import ctypes
                ctypes.windll.user32.MessageBoxW(
                    None,
                    'Live Overlay Studioを更新できませんでした。\n'
                    '起動中の古いアプリをすべて終了してから、もう一度起動してください。\n\n'
                    f'{error}',
                    'アプリを更新できません',
                    0x10,
                )
            except Exception:
                pass
            raise SystemExit(1)
        subprocess.Popen([str(managed_exe)], cwd=str(ROOT), close_fds=True)
        raise SystemExit(0)
STATE = ROOT / 'state.json'
STATE_LOCK = threading.Lock()
OVERLAY_SNAPSHOT_LOCK = threading.Lock()
OVERLAY_SNAPSHOT_CACHE = {'signature': None, 'at': 0, 'state': None}
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
    'giftWall': {'minCoins':100, 'columns':4, 'rows':2, 'pageSeconds':8, 'scrollDirection':'vertical', 'scrollStyle':'page', 'scrollSpeed':40, 'loop':True, 'newestFirst':True, 'history':[], 'displayHistory':[], 'fontFamily':'global', 'textScale':100, 'avatarSize':44, 'nameSize':18, 'giftNameSize':16, 'countSize':15, 'giftImageSize':44, 'cardBg':'#1c1c24', 'cardBorder':'#ffcf59', 'cardTextColor':'#ffffff', 'cardOpacity':93, 'nextId':1},
    'tiktokUsername': '',
    'timer': {'endAt': 0, 'seconds': 0, 'giftName': '', 'defaultText': 'カウント：0秒', 'currentText': ''},
    'winCounter': {'title': '現在', 'currentWin': 0, 'goalWin': 10, 'shortcutAdd': 'CTRL+ALT+7', 'shortcutSub': 'CTRL+ALT+SHIFT+7', 'giftRules': [], 'positiveTextColor': '', 'negativeTextColor': '#ff4055', 'goalTextColor': '', 'titleSize': 30, 'valueSize': 76, 'imageUrl': '', 'imageName': '', 'imageSize': 64, 'imageEnabled': True, 'soundEnabled': False, 'addSoundUrl': '', 'addSoundName': '', 'addSoundVolume': 75, 'subSoundUrl': '', 'subSoundName': '', 'subSoundVolume': 75, 'goalSoundUrl': '', 'goalSoundName': '', 'goalSoundVolume': 75, 'soundVolume': 75},
    'minecraftBridge': {'enabled': False, 'logPath': '', 'marker': 'bedrock_win'},
    'gtaBridge': {'enabled': False, 'logPath': '', 'marker': 'Sent WebSocket message: {"type":"win"', 'winAmount': 1, 'loseEnabled': True, 'loseMarker': 'Sent WebSocket message: {"type":"lose"', 'loseAmount': 1},
    'gacha': {'mode':'continue', 'continuationRate':70, 'spinSeconds':5, 'soundVolume':65, 'shortcutChoicePlus':'CTRL+ALT+8', 'shortcutChoiceMinus':'CTRL+ALT+9', 'patterns':[{'id':'gacha-pattern-1','name':'WINガチャ','giftName':'','minWin':1,'maxWin':10,'outcomeMode':'range','outcomes':[]}], 'animationUrl':'', 'animationName':'', 'audioUrl':'', 'audioName':'', 'audioVolume':75, 'resultAudioUrl':'', 'resultAudioName':'', 'resultAudioVolume':80, 'effectStyle':'card', 'slotNumberSize':130, 'slotNumberColor':'#ffffff', 'slotX':50, 'slotY':50, 'spinStyle':'dramatic', 'videoAudioEnabled':True, 'videoVolume':75, 'endAnimationUrl':'', 'endAnimationName':'', 'endAudioUrl':'', 'endAudioName':'', 'endAudioVolume':75, 'endSeconds':6, 'queue':[], 'event':{'id':0,'type':'','active':False,'patternName':'','rounds':[],'total':0,'giftName':'','senderName':'','createdAt':0}},
    'pachinkoGacha': {'patterns': [], 'queue': [], 'history': [], 'event': {'id':0,'type':'','active':False,'patternId':'','patternName':'','senderName':'','spins':0,'hitSpin':0,'route':'','rounds':[],'total':0,'createdAt':0}},
    'otherGacha': {'patterns':[], 'queue':[], 'event':{'id':0,'type':'','active':False,'patternId':'','patternName':'','rounds':[],'senderName':'','createdAt':0}},
    'giftMedia': {'rules':[], 'queue':[], 'event':{'id':0,'type':'','active':False,'ruleId':'','giftName':'','senderName':'','count':1,'imageUrl':'','videoUrl':'','audioUrl':'','audioVolume':75,'videoVolume':75,'width':800,'height':450,'duration':6,'createdAt':0}},
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
HOTKEY_STATUS = {'active': False, 'message': 'ショートカット監視を起動しています', 'bindings': 0, 'registered': 0, 'registrationFailures': 0, 'lastInputAt': 0}
HOTKEY_STATUS_LOCK = threading.Lock()
MINECRAFT_WATCH_STATUS = {'status': 'stopped', 'message': 'Minecraftログ連携はオフです', 'lastEventAt': 0, 'winsReceived': 0}
MINECRAFT_WATCH_LOCK = threading.Lock()
MINECRAFT_WATCH_THREAD = None
GTA_WATCH_STATUS = {'status': 'stopped', 'message': 'GTA連携はオフです', 'lastEventAt': 0, 'eventsReceived': 0}
GTA_WATCH_LOCK = threading.Lock()
GTA_WATCH_THREAD = None

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

def pachinko_boundary_stages():
    return tuple(phase+edge for phase in ('reach','cz','hit','at','upper','lt') for edge in ('Enter','Exit'))

def safe_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError, OverflowError):
        return default

def safe_hex(value):
    text = str(value or '').lower()
    return text if re.fullmatch(r'#[0-9a-f]{6}', text) else ''

def valid_hex(value):
    return safe_hex(value)

def clean_local_path(value):
    """Accept paths copied from Windows Explorer, which may include quotes."""
    value = str(value or '').strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
        value = value[1:-1].strip()
    return value

def normalize_state(data):
    data = data if isinstance(data, dict) else {}
    merged = {**copy.deepcopy(DEFAULT), **data}
    valid_hex = lambda value: str(value or '').lower() if re.fullmatch(r'#[0-9a-fA-F]{6}', str(value or '')) else ''
    raw_other = merged.get('otherGacha') if isinstance(merged.get('otherGacha'), dict) else {}
    raw_other_event = raw_other.get('event') if isinstance(raw_other.get('event'), dict) else {}
    other_patterns=[]
    for index, item in enumerate(raw_other.get('patterns') or []):
        if not isinstance(item, dict): continue
        outcomes=[]
        for outcome in (item.get('outcomes') or [])[:100]:
            if not isinstance(outcome, dict): continue
            label=str(outcome.get('label') or '')[:100]
            probability=max(0,min(10000,safe_int(outcome.get('probability',0))))
            if label and probability: outcomes.append({'label':label,'probability':probability})
        raw_layout=item.get('layout') if isinstance(item.get('layout'),dict) else {}
        layout={key:max(0,min(100,safe_int(raw_layout.get(key,default),default))) for key,default in (('patternX',50),('patternY',17),('senderX',50),('senderY',28),('stateX',50),('stateY',78),('resultX',50),('resultY',53))}
        raw_scene_layouts=item.get('sceneLayouts') if isinstance(item.get('sceneLayouts'),dict) else {}
        scene_layouts={}
        for scene in ('spin','result','continue','end'):
            source=raw_scene_layouts.get(scene) if isinstance(raw_scene_layouts.get(scene),dict) else {}
            scene_layouts[scene]={key:max(0,min(100,safe_int(source.get(key,default),default))) for key,default in (('patternX',50),('patternY',17),('senderX',50),('senderY',28),('stateX',50),('stateY',78),('resultX',50),('resultY',53))}
        raw_styles=item.get('sceneStyles') if isinstance(item.get('sceneStyles'),dict) else {}
        scene_styles={}
        for scene in ('spin','result','continue','end'):
            src=raw_styles.get(scene) if isinstance(raw_styles.get(scene),dict) else {}
            style={'fontFamily':src.get('fontFamily') if src.get('fontFamily') in ('global','yuGothic','meiryo','gothic','serif','mono') else 'global'}
            for text_key,default_color,default_size in (('pattern','#ffffff',36),('sender','#ffe9a6',24),('state','#ffe08a',30),('result','#ffffff',100)):
                item_style=src.get(text_key) if isinstance(src.get(text_key),dict) else {}
                color=valid_hex(item_style.get('color'))
                style[text_key]={'visible':item_style.get('visible') is not False,'color':color or default_color,'size':max(14,min(300,safe_int(item_style.get('size',default_size),default_size)))}
            scene_styles[scene]=style
        other_patterns.append({'id':str(item.get('id') or f'other-gacha-{index+1}')[:80], 'name':str(item.get('name') or f'その他ガチャ{index+1}')[:60], 'enabled':item.get('enabled',True) is not False, 'giftName':str(item.get('giftName') or '').strip()[:120], 'mode':'continue' if item.get('mode')=='continue' else 'single', 'continuationRate':max(0,min(100,safe_int(item.get('continuationRate',70)))), 'spinSeconds':max(1,min(30,safe_int(item.get('spinSeconds',5)))), 'outcomes':outcomes, 'effectStyle':str(item.get('effectStyle') or 'slot')[:30], 'resultColor':valid_hex(item.get('resultColor')) or '#ffffff', 'resultSize':max(24,min(300,safe_int(item.get('resultSize',100)))), 'background':valid_hex(item.get('background')) or '#17151c', 'opacity':max(0,min(100,safe_int(item.get('opacity',90)))), 'layout':layout, 'sceneLayouts':scene_layouts, 'sceneStyles':scene_styles, 'animationUrl':str(item.get('animationUrl') or '')[:2000], 'animationName':str(item.get('animationName') or '')[:120], 'audioUrl':str(item.get('audioUrl') or '')[:2000], 'audioName':str(item.get('audioName') or '')[:120], 'audioVolume':max(0,min(100,safe_int(item.get('audioVolume',75)))), 'resultAudioUrl':str(item.get('resultAudioUrl') or '')[:2000], 'resultAudioName':str(item.get('resultAudioName') or '')[:120], 'resultAudioVolume':max(0,min(100,safe_int(item.get('resultAudioVolume',80)))), 'videoAudioEnabled':bool(item.get('videoAudioEnabled',True)), 'videoVolume':max(0,min(100,safe_int(item.get('videoVolume',75))))})
    other_created=max(0,safe_float(raw_other_event.get('createdAt') or 0))
    other_active=bool(raw_other_event.get('active',False)) and other_created>=SERVER_STARTED_AT
    event_layout=raw_other_event.get('layout') if isinstance(raw_other_event.get('layout'),dict) else {}
    event_layout={key:max(0,min(100,safe_int(event_layout.get(key,default),default))) for key,default in (('patternX',50),('patternY',17),('senderX',50),('senderY',28),('stateX',50),('stateY',78),('resultX',50),('resultY',53))}
    raw_event_scenes=raw_other_event.get('sceneLayouts') if isinstance(raw_other_event.get('sceneLayouts'),dict) else {}
    event_scene_layouts={}
    for scene in ('spin','result','continue','end'):
        source=raw_event_scenes.get(scene) if isinstance(raw_event_scenes.get(scene),dict) else {}
        event_scene_layouts[scene]={key:max(0,min(100,safe_int(source.get(key,default),default))) for key,default in (('patternX',50),('patternY',17),('senderX',50),('senderY',28),('stateX',50),('stateY',78),('resultX',50),('resultY',53))}
    raw_event_styles=raw_other_event.get('sceneStyles') if isinstance(raw_other_event.get('sceneStyles'),dict) else {}
    event_scene_styles={}
    for scene in ('spin','result','continue','end'):
        src=raw_event_styles.get(scene) if isinstance(raw_event_styles.get(scene),dict) else {}
        style={'fontFamily':src.get('fontFamily') if src.get('fontFamily') in ('global','yuGothic','meiryo','gothic','serif','mono') else 'global'}
        for text_key,default_color,default_size in (('pattern','#ffffff',36),('sender','#ffe9a6',24),('state','#ffe08a',30),('result','#ffffff',100)):
            item_style=src.get(text_key) if isinstance(src.get(text_key),dict) else {}
            color=valid_hex(item_style.get('color'))
            style[text_key]={'visible':item_style.get('visible') is not False,'color':color or default_color,'size':max(14,min(300,safe_int(item_style.get('size',default_size),default_size)))}
        event_scene_styles[scene]=style
    merged['otherGacha']={'patterns':other_patterns,'queue':[x for x in (raw_other.get('queue') or []) if isinstance(x,dict)][:100] if other_active else [], 'event':{'id':max(0,safe_int(raw_other_event.get('id') or 0)),'type':'other-gacha' if raw_other_event.get('type')=='other-gacha' else '', 'active':other_active, 'patternId':str(raw_other_event.get('patternId') or '')[:80], 'patternName':str(raw_other_event.get('patternName') or '')[:60], 'rounds':raw_other_event.get('rounds') if isinstance(raw_other_event.get('rounds'),list) else [], 'outcomes':[{'label':str(x.get('label') or '')[:100]} for x in (raw_other_event.get('outcomes') or []) if isinstance(x,dict)][:100], 'spinSeconds':max(1,min(30,safe_int(raw_other_event.get('spinSeconds',5)))), 'effectStyle':str(raw_other_event.get('effectStyle') or 'slot')[:30], 'resultColor':valid_hex(raw_other_event.get('resultColor')) or '#ffffff', 'resultSize':max(24,min(300,safe_int(raw_other_event.get('resultSize',100)))), 'background':valid_hex(raw_other_event.get('background')) or '#17151c', 'opacity':max(0,min(100,safe_int(raw_other_event.get('opacity',90)))), 'layout':event_layout, 'sceneLayouts':event_scene_layouts, 'sceneStyles':event_scene_styles, 'animationUrl':str(raw_other_event.get('animationUrl') or '')[:2000], 'audioUrl':str(raw_other_event.get('audioUrl') or '')[:2000], 'audioVolume':max(0,min(100,safe_int(raw_other_event.get('audioVolume',75)))), 'resultAudioUrl':str(raw_other_event.get('resultAudioUrl') or '')[:2000], 'resultAudioVolume':max(0,min(100,safe_int(raw_other_event.get('resultAudioVolume',80)))), 'videoAudioEnabled':bool(raw_other_event.get('videoAudioEnabled',True)), 'videoVolume':max(0,min(100,safe_int(raw_other_event.get('videoVolume',75)))), 'senderName':str(raw_other_event.get('senderName') or '')[:80], 'createdAt':other_created}}
    raw_gift_media=merged.get('giftMedia') if isinstance(merged.get('giftMedia'),dict) else {}
    raw_gm_event=raw_gift_media.get('event') if isinstance(raw_gift_media.get('event'),dict) else {}
    gm_rules=[]
    for index,item in enumerate(raw_gift_media.get('rules') or []):
        if not isinstance(item,dict): continue
        rid=str(item.get('id') or f'gift-media-{index+1}')[:80]
        gm_rules.append({'id':rid,'name':str(item.get('name') or f'ギフト演出{index+1}')[:60],'enabled':item.get('enabled',True) is not False,'giftName':str(item.get('giftName') or '').strip()[:120], 'imageUrl':str(item.get('imageUrl') or '')[:2000], 'imageName':str(item.get('imageName') or '')[:120], 'videoUrl':str(item.get('videoUrl') or '')[:2000], 'videoName':str(item.get('videoName') or '')[:120], 'audioUrl':str(item.get('audioUrl') or '')[:2000], 'audioName':str(item.get('audioName') or '')[:120], 'audioVolume':max(0,min(100,safe_int(item.get('audioVolume',75)))), 'videoVolume':max(0,min(100,safe_int(item.get('videoVolume',75)))), 'width':max(80,min(3840,safe_int(item.get('width',800)))), 'height':max(60,min(2160,safe_int(item.get('height',450)))), 'duration':max(0,min(600,safe_int(item.get('duration',6))))})
    gm_created=max(0,safe_float(raw_gm_event.get('createdAt') or 0))
    gm_active=bool(raw_gm_event.get('active',False)) and gm_created>=SERVER_STARTED_AT
    gm_event={'id':max(0,safe_int(raw_gm_event.get('id') or 0)),'type':'gift-media' if raw_gm_event.get('type')=='gift-media' else '', 'active':gm_active,'ruleId':str(raw_gm_event.get('ruleId') or '')[:80], 'ruleName':str(raw_gm_event.get('ruleName') or '')[:60], 'giftName':str(raw_gm_event.get('giftName') or '')[:120], 'senderName':str(raw_gm_event.get('senderName') or '')[:80], 'count':max(1,min(1000000,safe_int(raw_gm_event.get('count',1)))), 'imageUrl':str(raw_gm_event.get('imageUrl') or '')[:2000], 'videoUrl':str(raw_gm_event.get('videoUrl') or '')[:2000], 'audioUrl':str(raw_gm_event.get('audioUrl') or '')[:2000], 'audioVolume':max(0,min(100,safe_int(raw_gm_event.get('audioVolume',75)))), 'videoVolume':max(0,min(100,safe_int(raw_gm_event.get('videoVolume',75)))), 'width':max(80,min(3840,safe_int(raw_gm_event.get('width',800)))), 'height':max(60,min(2160,safe_int(raw_gm_event.get('height',450)))), 'duration':max(0,min(600,safe_int(raw_gm_event.get('duration',6)))), 'createdAt':gm_created}
    merged['giftMedia']={'rules':gm_rules,'queue':[x for x in (raw_gift_media.get('queue') or []) if isinstance(x,dict)][:100] if gm_active else [],'event':gm_event}
    changed = False
    raw_card_defaults = merged.get('cardDefaults') if isinstance(merged.get('cardDefaults'), dict) else {}
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
        'scrollStyle': raw_wall.get('scrollStyle') if raw_wall.get('scrollStyle') in ('page','continuous','single','fade','slide','static') else 'page',
        'scrollSpeed': max(5, min(300, safe_int(raw_wall.get('scrollSpeed', 40), 40))),
        'loop': raw_wall.get('loop', True) is not False,
        'newestFirst': raw_wall.get('newestFirst', True) is not False,
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
    legacy_win_sound_volume=max(0,min(100,safe_int(raw_win.get('soundVolume',75),75)))
    merged['winCounter']={'fontFamily':raw_win.get('fontFamily') if raw_win.get('fontFamily') in ('global','system','yuGothic','meiryo','gothic','serif','mono') else 'global','title':str(raw_win.get('title','現在'))[:60],'currentWin':max(-999999,min(999999,safe_int(raw_win.get('currentWin') or 0))),'goalWin':max(1,min(999999,safe_int(raw_win.get('goalWin') or 10))),'shortcutAdd':str(raw_win.get('shortcutAdd') or '').upper(),'shortcutSub':str(raw_win.get('shortcutSub') or '').upper(),'giftRules':win_gift_rules,'cardBg':valid_hex(raw_win.get('cardBg')),'cardBorder':valid_hex(raw_win.get('cardBorder')),'cardTextColor':valid_hex(raw_win.get('cardTextColor')),'cardOpacity':max(-1,min(100,safe_int(raw_win.get('cardOpacity',-1)))),'positiveTextColor':valid_hex(raw_win.get('positiveTextColor')),'negativeTextColor':valid_hex(raw_win.get('negativeTextColor')) or '#ff4055','goalTextColor':valid_hex(raw_win.get('goalTextColor')),'titleSize':max(12,min(120,safe_int(raw_win.get('titleSize',30),30))),'valueSize':max(20,min(180,safe_int(raw_win.get('valueSize',76),76))),'imageUrl':str(raw_win.get('imageUrl') or '')[:240],'imageName':str(raw_win.get('imageName') or '')[:120],'imageSize':max(20,min(240,safe_int(raw_win.get('imageSize') or 64))),'imageEnabled':raw_win.get('imageEnabled',True) is not False,'soundEnabled':bool(raw_win.get('soundEnabled',False)),'addSoundUrl':str(raw_win.get('addSoundUrl') or '')[:2000],'addSoundName':str(raw_win.get('addSoundName') or '')[:120],'addSoundVolume':max(0,min(100,safe_int(raw_win.get('addSoundVolume',legacy_win_sound_volume),legacy_win_sound_volume))),'subSoundUrl':str(raw_win.get('subSoundUrl') or '')[:2000],'subSoundName':str(raw_win.get('subSoundName') or '')[:120],'subSoundVolume':max(0,min(100,safe_int(raw_win.get('subSoundVolume',legacy_win_sound_volume),legacy_win_sound_volume))),'goalSoundUrl':str(raw_win.get('goalSoundUrl') or '')[:2000],'goalSoundName':str(raw_win.get('goalSoundName') or '')[:120],'goalSoundVolume':max(0,min(100,safe_int(raw_win.get('goalSoundVolume',legacy_win_sound_volume),legacy_win_sound_volume))),'soundVolume':legacy_win_sound_volume}
    raw_bridge = merged.get('minecraftBridge') if isinstance(merged.get('minecraftBridge'), dict) else {}
    marker = str(raw_bridge.get('marker') or 'bedrock_win').strip()[:80]
    if not marker:
        marker = 'bedrock_win'
    merged['minecraftBridge'] = {
        'enabled': bool(raw_bridge.get('enabled', False)),
        'logPath': clean_local_path(raw_bridge.get('logPath'))[:1000],
        'marker': marker,
    }
    raw_gta_bridge = merged.get('gtaBridge') if isinstance(merged.get('gtaBridge'), dict) else {}
    gta_marker = str(raw_gta_bridge.get('marker') or 'Sent WebSocket message: {"type":"win"').strip()[:160]
    if not gta_marker:
        gta_marker = 'Sent WebSocket message: {"type":"win"'
    merged['gtaBridge'] = {
        'enabled': bool(raw_gta_bridge.get('enabled', False)),
        'logPath': clean_local_path(raw_gta_bridge.get('logPath'))[:1000],
        'marker': gta_marker,
        'winAmount': max(1, min(999999, safe_int(raw_gta_bridge.get('winAmount', 1), 1))),
        'loseEnabled': raw_gta_bridge.get('loseEnabled', True) is not False,
        'loseMarker': str(raw_gta_bridge.get('loseMarker') or 'Sent WebSocket message: {"type":"lose"').strip()[:160] or 'Sent WebSocket message: {"type":"lose"',
        'loseAmount': max(1, min(999999, safe_int(raw_gta_bridge.get('loseAmount', 1), 1))),
    }
    raw_gacha = merged.get('gacha') if isinstance(merged.get('gacha'), dict) else {}
    patterns = []
    for index, item in enumerate(raw_gacha.get('patterns') or []):
        if not isinstance(item, dict):
            continue
        raw_text_roles=item.get('textRoles') if isinstance(item.get('textRoles'),dict) else {}
        text_roles={}
        for role in ('pattern','sender','start','startQuestion','spinState','spinStatus','spinNumber','resultState','continueState','upperEntryState','resultWin','roundTotal','setCount','choiceResult','choice','endResult','endState','finalTotal'):
            source=raw_text_roles.get(role) if isinstance(raw_text_roles.get(role),dict) else (raw_text_roles.get('resultState') if role in ('continueState','upperEntryState') and isinstance(raw_text_roles.get('resultState'),dict) else {})
            text_roles[role]={'enabled':source.get('enabled',True) is not False,'text':str(source.get('text') or '')[:120],'colorEnabled':bool(source.get('colorEnabled',False)),'color':valid_hex(source.get('color')) or '#ffffff','size':max(12,min(400,safe_int(source.get('size',0),0))) if source.get('size') else 0,'fontFamily':source.get('fontFamily') if source.get('fontFamily') in ('global','system','native','yuGothic','meiryo','gothic','serif','mono') else 'global','mode':'image' if source.get('mode')=='image' else 'text','imageUrl':str(source.get('imageUrl') or '')[:2000],'imageName':str(source.get('imageName') or '')[:120],'imageSize':max(20,min(600,safe_int(source.get('imageSize',120),120))),'positionEnabled':bool(source.get('positionEnabled',False)),'x':max(0,min(100,safe_float(source.get('x',50),50))),'y':max(0,min(100,safe_float(source.get('y',50),50)))}
        low = max(-9999, min(9999, safe_int(item.get('minWin') or 0)))
        high = max(-9999, min(9999, safe_int(item.get('maxWin') or 0)))
        outcomes=[]
        for outcome in item.get('outcomes',[])[:50] if isinstance(item.get('outcomes',[]),list) else []:
            if isinstance(outcome,dict):
                outcomes.append({'value':max(-9999,min(9999,safe_int(outcome.get('value') or 0))),'probability':max(0,min(100000,safe_int(outcome.get('probability') or 0))),'spinImageUrl':str(outcome.get('spinImageUrl') or '')[:2000],'spinImageName':str(outcome.get('spinImageName') or '')[:120],'spinImageSize':max(40,min(1200,safe_int(outcome.get('spinImageSize',item.get('spinNumberImageSize',760)),760))),'spinTextEnabled':outcome.get('spinTextEnabled',True) is not False,'spinText':str(outcome.get('spinText') or '')[:120],'spinTextColor':valid_hex(outcome.get('spinTextColor')) or '#ffffff','spinTextSize':max(0,min(600,safe_int(outcome.get('spinTextSize',0),0))),'spinFontFamily':outcome.get('spinFontFamily') if outcome.get('spinFontFamily') in ('global','system','native','yuGothic','meiryo','gothic','serif','mono') else 'global','resultImageUrl':str(outcome.get('resultImageUrl') or '')[:2000],'resultImageName':str(outcome.get('resultImageName') or '')[:120],'resultImageSize':max(40,min(1200,safe_int(outcome.get('resultImageSize',760),760))),'resultTextEnabled':outcome.get('resultTextEnabled',True) is not False,'resultText':str(outcome.get('resultText') or '')[:120],'resultTextColor':valid_hex(outcome.get('resultTextColor')) or '#ffffff','resultTextSize':max(0,min(600,safe_int(outcome.get('resultTextSize',0),0))),'resultFontFamily':outcome.get('resultFontFamily') if outcome.get('resultFontFamily') in ('global','system','native','yuGothic','meiryo','gothic','serif','mono') else 'global'})
                if not valid_hex(outcome.get('spinTextColor')): outcomes[-1]['spinTextColor']=''
                if not valid_hex(outcome.get('resultTextColor')): outcomes[-1]['resultTextColor']=''
        upper_outcomes=[]
        for outcome in item.get('upperOutcomes',[])[:50] if isinstance(item.get('upperOutcomes',[]),list) else []:
            if isinstance(outcome,dict):
                upper_outcomes.append({'value':max(-9999,min(9999,safe_int(outcome.get('value') or 0))),'probability':max(0,min(100000,safe_int(outcome.get('probability') or 0))),'spinImageUrl':str(outcome.get('spinImageUrl') or '')[:2000],'spinImageName':str(outcome.get('spinImageName') or '')[:120],'spinImageSize':max(40,min(1200,safe_int(outcome.get('spinImageSize',item.get('spinNumberImageSize',760)),760))),'spinTextEnabled':outcome.get('spinTextEnabled',True) is not False,'spinText':str(outcome.get('spinText') or '')[:120],'spinTextColor':valid_hex(outcome.get('spinTextColor')) or '#ffffff','spinTextSize':max(0,min(600,safe_int(outcome.get('spinTextSize',0),0))),'spinFontFamily':outcome.get('spinFontFamily') if outcome.get('spinFontFamily') in ('global','system','native','yuGothic','meiryo','gothic','serif','mono') else 'global','resultImageUrl':str(outcome.get('resultImageUrl') or '')[:2000],'resultImageName':str(outcome.get('resultImageName') or '')[:120],'resultImageSize':max(40,min(1200,safe_int(outcome.get('resultImageSize',760),760))),'resultTextEnabled':outcome.get('resultTextEnabled',True) is not False,'resultText':str(outcome.get('resultText') or '')[:120],'resultTextColor':valid_hex(outcome.get('resultTextColor')) or '#ffffff','resultTextSize':max(0,min(600,safe_int(outcome.get('resultTextSize',0),0))),'resultFontFamily':outcome.get('resultFontFamily') if outcome.get('resultFontFamily') in ('global','system','native','yuGothic','meiryo','gothic','serif','mono') else 'global'})
                if not valid_hex(outcome.get('spinTextColor')): upper_outcomes[-1]['spinTextColor']=''
                if not valid_hex(outcome.get('resultTextColor')): upper_outcomes[-1]['resultTextColor']=''
        pattern_opacity=safe_int(item.get('cardOpacity',raw_gacha.get('cardOpacity',94)))
        raw_element_layout=item.get('elementLayout') if isinstance(item.get('elementLayout'),dict) else {}
        element_layout={key:max(0,min(100,safe_int(raw_element_layout.get(key,default),default))) for key,default in (('patternX',50),('patternY',8),('senderX',50),('senderY',18),('resultX',50),('resultY',50),('stateX',50),('stateY',75),('totalX',50),('totalY',88))} if raw_element_layout else {}
        preview_scenes=('start','normal-spin','preAlert1','preAlert2','preAlert3','result','continue','upper-entry','upper-spin','upper-continue','end')
        preview_text_fields=('fontFamily','patternTextColor','patternTextSize','setCountTextColor','setCountTextSize','setCountFontFamily','showPatternText','senderTextColor','senderTextSize','showSenderText','spinNumberTextColor','spinNumberTextSize','showSpinNumberText','resultTextColor','resultTextSize','showResultText','stateTextColor','stateTextSize','showStateText','spinStatusTextColor','spinStatusTextSize','showSpinStatusText','roundTotalTextColor','roundTotalTextSize','showRoundTotalText','startTextColor','startTextSize','showStartText','finalTotalTextColor','finalTotalTextSize','showFinalTotalText','showChoiceText','choiceTextColor','choiceTextSize')
        preview_color_fields={'patternTextColor','setCountTextColor','senderTextColor','spinNumberTextColor','resultTextColor','stateTextColor','spinStatusTextColor','roundTotalTextColor','startTextColor','finalTotalTextColor','choiceTextColor'}
        preview_size_fields={'patternTextSize','setCountTextSize','senderTextSize','spinNumberTextSize','resultTextSize','stateTextSize','spinStatusTextSize','roundTotalTextSize','startTextSize','finalTotalTextSize','choiceTextSize'}
        raw_preview_styles=item.get('previewSceneStyles') if isinstance(item.get('previewSceneStyles'),dict) else {}
        preview_scene_styles={}
        for scene in preview_scenes:
            raw_style=raw_preview_styles.get(scene) if isinstance(raw_preview_styles.get(scene),dict) else {}
            clean_style={}
            for key in preview_text_fields:
                if key in ('fontFamily','setCountFontFamily'):
                    if raw_style.get(key) in ('global','system','native','yuGothic','meiryo','gothic','serif','mono'): clean_style[key]=raw_style[key]
                elif key in preview_color_fields:
                    color=valid_hex(raw_style.get(key))
                    if color: clean_style[key]=color
                elif key in preview_size_fields:
                    if key in raw_style: clean_style[key]=max(14,min(400,safe_int(raw_style.get(key),40)))
                elif key in raw_style:
                    clean_style[key]=raw_style.get(key) is not False
            preview_scene_styles[scene]=clean_style
        raw_preview_positions=item.get('previewScenePositions') if isinstance(item.get('previewScenePositions'),dict) else {}
        preview_scene_positions={}
        for scene in preview_scenes:
            raw_positions=raw_preview_positions.get(scene) if isinstance(raw_preview_positions.get(scene),dict) else {}
            clean_positions={}
            for key in ('pattern','sender','setCount','result','state','total'):
                point=raw_positions.get(key) if isinstance(raw_positions.get(key),dict) else None
                if point is not None:
                    clean_positions[key]={'x':max(0,min(100,safe_float(point.get('x',50),50))),'y':max(0,min(100,safe_float(point.get('y',50),50)))}
            preview_scene_positions[scene]=clean_positions
        raw_legacy_positions=item.get('previewPositions') if isinstance(item.get('previewPositions'),dict) else {}
        preview_positions={}
        for key in ('pattern','sender','setCount','result','state','total'):
            point=raw_legacy_positions.get(key) if isinstance(raw_legacy_positions.get(key),dict) else None
            if point is not None: preview_positions[key]={'x':max(0,min(100,safe_float(point.get('x',50),50))),'y':max(0,min(100,safe_float(point.get('y',50),50)))}
        raw_alerts=item.get('preAlerts') if isinstance(item.get('preAlerts'),list) else []
        if not raw_alerts:
            raw_alerts=[{'enabled':item.get('preAlertEnabled',False),'onContinue':item.get('preAlertOnContinue',False),'onUpper':item.get('preAlertOnUpper',False),'minWin':item.get('preAlertMinWin',0),'timing':item.get('preAlertTiming','before-result'),'text':item.get('preAlertText','チャンス！'),'seconds':item.get('preAlertSeconds',1.2),'color':item.get('preAlertColor','#ffe05b'),'volume':item.get('preAlertVolume',75),'animationUrl':item.get('preAlertAnimationUrl',''),'animationName':item.get('preAlertAnimationName',''),'videoVolume':item.get('preAlertVideoVolume',75),'showText':True,'textSize':56}]
        pre_alerts=[]
        for alert_index in range(3):
            alert=raw_alerts[alert_index] if alert_index<len(raw_alerts) and isinstance(raw_alerts[alert_index],dict) else {}
            pre_alerts.append({'standardSoundEnabled':alert.get('standardSoundEnabled',True) is not False,'enabled':bool(alert.get('enabled',False)),'displayMode':alert.get('displayMode') if alert.get('displayMode') in ('full','sound-only','sound-text') else 'full','onContinue':bool(alert.get('onContinue',False)),'onUpper':bool(alert.get('onUpper',False)),'minWin':max(0,min(999999,safe_int(alert.get('minWin',0)))),'continueChance':max(0,min(100,safe_int(alert.get('continueChance',100),100))),'upperChance':max(0,min(100,safe_int(alert.get('upperChance',100),100))),'winChance':max(0,min(100,safe_int(alert.get('winChance',100),100))),'timing':alert.get('timing') if alert.get('timing') in ('result-only','spin-start','before-result') else 'before-result','text':str(alert.get('text') or 'チャンス！')[:80],'showText':alert.get('showText',True) is not False,'textSize':max(14,min(300,safe_int(alert.get('textSize',56),56))),'seconds':max(.2,min(300,safe_float(alert.get('textSeconds',alert.get('seconds',1.2)),1.2))),'textSeconds':max(.2,min(300,safe_float(alert.get('textSeconds',alert.get('seconds',1.2)),1.2))),'mediaSeconds':max(0,min(600,safe_float(alert.get('mediaSeconds',0),0))),'color':valid_hex(alert.get('color')) or '#ffe05b','volume':max(0,min(100,safe_int(alert.get('volume',75)))),'animationUrl':str(alert.get('animationUrl') or '')[:2000],'animationName':str(alert.get('animationName') or '')[:120],'audioUrl':str(alert.get('audioUrl') or '')[:2000],'audioName':str(alert.get('audioName') or '')[:120],'audioVolume':max(0,min(100,safe_int(alert.get('audioVolume',75)))),'audioSeconds':max(0,min(600,safe_float(alert.get('audioSeconds',0),0))),'videoVolume':max(0,min(100,safe_int(alert.get('videoVolume',75))))})
        patterns.append({
            'id':str(item.get('id') or f'gacha-pattern-{index+1}'), 'name':str(item.get('name') or f'パターン{index+1}')[:60], 'giftName':str(item.get('giftName') or '').strip(), 'textRoles':text_roles,
            'minWin':min(low,high), 'maxWin':max(low,high), 'outcomeMode':'weighted' if item.get('outcomeMode')=='weighted' else 'range', 'outcomes':outcomes,
            'winSign':item.get('winSign') if item.get('winSign') in ('plus','minus','both') else 'both', 'mode':'single' if item.get('mode',raw_gacha.get('mode','continue'))=='single' else 'continue',
            'continuationRate':max(0,min(100,safe_int(item.get('continuationRate',raw_gacha.get('continuationRate',70))))),
            'upperAtEnabled':bool(item.get('upperAtEnabled',False)),
            'upperAtEntryRate':max(0,min(100,safe_int(item.get('upperAtEntryRate',5)))),
            'upperAtContinuationRate':max(0,min(100,safe_int(item.get('upperAtContinuationRate',80)))),
            'upperSpinSeconds':max(.2,min(30,safe_float(item.get('upperSpinSeconds',item.get('spinSeconds',raw_gacha.get('spinSeconds',5))),5))),
            'upperOutcomeMode':'weighted' if item.get('upperOutcomeMode')=='weighted' else 'range',
            'upperMinWin':max(-9999,min(9999,safe_int(item.get('upperMinWin',item.get('minWin',1)),1))),
            'upperMaxWin':max(-9999,min(9999,safe_int(item.get('upperMaxWin',item.get('maxWin',10)),10))),
            'upperOutcomes':upper_outcomes,
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
            'startEffectEnabled':item.get('startEffectEnabled',True) is not False,
            'startDefaultSoundEnabled':item.get('startDefaultSoundEnabled',True) is not False,
            'startDefaultSoundUrl':str(item.get('startDefaultSoundUrl') or '')[:2000], 'startDefaultSoundName':str(item.get('startDefaultSoundName') or '')[:120],
            'startDefaultSoundVolume':max(0,min(100,safe_int(item.get('startDefaultSoundVolume',item.get('soundVolume',80)),80))),
            'startAnimationUrl':str(item.get('startAnimationUrl') or '')[:2000], 'startAnimationName':str(item.get('startAnimationName') or '')[:120],
            'startAudioUrl':str(item.get('startAudioUrl') or '')[:2000], 'startAudioName':str(item.get('startAudioName') or '')[:120],
            'startSeconds':max(1,min(30,safe_int(item.get('startSeconds',2),2))), 'startAudioVolume':max(0,min(100,safe_int(item.get('startAudioVolume',80),80))), 'startVideoAudioEnabled':bool(item.get('startVideoAudioEnabled',True)), 'startVideoVolume':max(0,min(100,safe_int(item.get('startVideoVolume',75),75))),
            'hitOnNormalContinue':bool(item.get('hitOnNormalContinue',True)), 'hitOnUpperEntry':bool(item.get('hitOnUpperEntry',True)), 'hitOnUpperContinue':bool(item.get('hitOnUpperContinue',True)), 'hitOnSingleHit':bool(item.get('hitOnSingleHit',True)), 'hitConditionMode':'win' if item.get('hitConditionMode')=='win' else 'flow', 'hitWinMode':'at-least' if item.get('hitWinMode')=='at-least' else 'exact', 'hitWinValue':max(0,min(999999,safe_int(item.get('hitWinValue',100),100))),
            'hitAnimationUrl':str(item.get('hitAnimationUrl') or '')[:2000], 'hitAnimationName':str(item.get('hitAnimationName') or '')[:120],
            'hitAudioUrl':str(item.get('hitAudioUrl') or '')[:2000], 'hitAudioName':str(item.get('hitAudioName') or '')[:120],
            'hitSeconds':max(1,min(30,safe_int(item.get('hitSeconds',2),2))), 'hitAudioVolume':max(0,min(100,safe_int(item.get('hitAudioVolume',80),80))), 'hitVideoAudioEnabled':bool(item.get('hitVideoAudioEnabled',True)), 'hitVideoVolume':max(0,min(100,safe_int(item.get('hitVideoVolume',75),75))),
            'missAnimationUrl':str(item.get('missAnimationUrl') or '')[:2000], 'missAnimationName':str(item.get('missAnimationName') or '')[:120],
            'missAudioUrl':str(item.get('missAudioUrl') or '')[:2000], 'missAudioName':str(item.get('missAudioName') or '')[:120],
            'missSeconds':max(1,min(30,safe_int(item.get('missSeconds',2),2))), 'missAudioVolume':max(0,min(100,safe_int(item.get('missAudioVolume',80),80))), 'missVideoAudioEnabled':bool(item.get('missVideoAudioEnabled',True)), 'missVideoVolume':max(0,min(100,safe_int(item.get('missVideoVolume',75),75))),
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
            'spinNumberTextColor':valid_hex(item.get('spinNumberTextColor')) or valid_hex(item.get('slotNumberColor')) or '#ffffff', 'spinNumberTextSize':max(14,min(400,safe_int(item.get('spinNumberTextSize',item.get('slotNumberSize',130))))),
            'startTextColor':valid_hex(item.get('startTextColor')) or '#ffffff', 'startTextSize':max(14,min(400,safe_int(item.get('startTextSize',48)))),
            'resultTextColor':valid_hex(item.get('resultTextColor')) or '#ffffff', 'resultTextSize':max(14,min(400,safe_int(item.get('resultTextSize',130)))),
            'roundTotalTextColor':valid_hex(item.get('roundTotalTextColor')) or '#ffffff', 'roundTotalTextSize':max(14,min(400,safe_int(item.get('roundTotalTextSize',32)))),
            'finalTotalTextColor':valid_hex(item.get('finalTotalTextColor')) or '#ffffff', 'finalTotalTextSize':max(14,min(400,safe_int(item.get('finalTotalTextSize',48)))),
            'patternTextColor':valid_hex(item.get('patternTextColor')) or '#ffffff', 'patternTextSize':max(18,min(400,safe_int(item.get('patternTextSize',40)))),
            'senderTextColor':valid_hex(item.get('senderTextColor')) or '#ffe9a6', 'senderTextSize':max(14,min(400,safe_int(item.get('senderTextSize',32)))),
            'setCountTextColor':valid_hex(item.get('setCountTextColor')) or '#ffffff', 'setCountTextSize':max(14,min(400,safe_int(item.get('setCountTextSize',32)))), 'setCountFontFamily':item.get('setCountFontFamily') if item.get('setCountFontFamily') in ('global','system','native','yuGothic','meiryo','gothic','serif','mono') else 'global', 'showSetCountAlways':item.get('showSetCountAlways',True) is not False,
            'choiceTextColor':valid_hex(item.get('choiceTextColor')) or '#ffe9a6', 'choiceTextSize':max(14,min(400,safe_int(item.get('choiceTextSize',34)))),
            'showPatternText':item.get('showPatternText',True) is not False, 'showSenderText':item.get('showSenderText',True) is not False,
            'showSpinNumberText':item.get('showSpinNumberText',True) is not False, 'showResultText':item.get('showResultText',True) is not False, 'showStateText':item.get('showStateText',True) is not False, 'showSpinStatusText':item.get('showSpinStatusText',True) is not False,
            'showStartText':item.get('showStartText',item.get('showTotalText',True)) is not False, 'showRoundTotalText':item.get('showRoundTotalText',item.get('showTotalText',True)) is not False, 'showFinalTotalText':item.get('showFinalTotalText',item.get('showTotalText',True)) is not False, 'showTotalText':True, 'showChoiceText':item.get('showChoiceText',True) is not False,
            'effectStyle':item.get('effectStyle',raw_gacha.get('effectStyle','card')) if item.get('effectStyle',raw_gacha.get('effectStyle','card')) in ('card','fullscreen-slot') else 'card',
            'elementLayout':element_layout, 'previewSceneStyles':preview_scene_styles, 'previewScenePositions':preview_scene_positions, 'previewPositions':preview_positions,
            'preAlerts':pre_alerts, 'preAlertEnabled':bool(item.get('preAlertEnabled',False)), 'preAlertOnContinue':bool(item.get('preAlertOnContinue',False)), 'preAlertOnUpper':bool(item.get('preAlertOnUpper',False)), 'preAlertMinWin':max(0,min(999999,safe_int(item.get('preAlertMinWin',0)))), 'preAlertTiming':item.get('preAlertTiming') if item.get('preAlertTiming') in ('result-only','spin-start','before-result') else 'before-result', 'preAlertText':str(item.get('preAlertText') or 'チャンス！')[:80], 'preAlertSeconds':max(0.2,min(5,safe_float(item.get('preAlertSeconds',1.2),1.2))), 'preAlertColor':valid_hex(item.get('preAlertColor')) or '#ffe05b', 'preAlertVolume':max(0,min(100,safe_int(item.get('preAlertVolume',75)))), 'preAlertAnimationUrl':str(item.get('preAlertAnimationUrl') or '')[:2000], 'preAlertAnimationName':str(item.get('preAlertAnimationName') or '')[:120], 'preAlertVideoVolume':max(0,min(100,safe_int(item.get('preAlertVideoVolume',75)))),
            'spinSeconds':max(.2,min(30,safe_float(item.get('spinSeconds',raw_gacha.get('spinSeconds',5)),5))),
            'soundVolume':max(0,min(100,safe_int(item.get('soundVolume',raw_gacha.get('soundVolume',65))))),
            'standardBeepEnabled':item.get('standardBeepEnabled',True) is not False,
            'standardResultSoundEnabled':item.get('standardResultSoundEnabled',True) is not False,
            'resultSoundEnabled':item.get('resultSoundEnabled',True) is not False,
            'resultDisplaySeconds':max(0.5,min(30,safe_float(item.get('resultDisplaySeconds',2),2))),
            'spinSoundUrl':str(item.get('spinSoundUrl') or '')[:2000], 'spinSoundName':str(item.get('spinSoundName') or '')[:120],
            'secondaryAudioUrl':str(item.get('secondaryAudioUrl') or '')[:2000], 'secondaryAudioName':str(item.get('secondaryAudioName') or '')[:120], 'secondaryAudioVolume':max(0,min(100,safe_int(item.get('secondaryAudioVolume',75),75))), 'secondaryAudioLoop':bool(item.get('secondaryAudioLoop',False)), 'secondaryAudioDelay':max(0,min(30,safe_float(item.get('secondaryAudioDelay',0),0))),
            'spinCandidateMode':'custom' if item.get('spinCandidateMode')=='custom' else 'outcomes', 'spinCandidates':[max(-9999,min(9999,safe_int(x))) for x in (item.get('spinCandidates') or [])[:100] if str(x).strip().lstrip('-').isdigit()], 'spinNumberImageSize':max(40,min(1200,safe_int(item.get('spinNumberImageSize',760),760))),
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
            'stateTextColor':valid_hex(item.get('stateTextColor')) or valid_hex(item.get('cardTextColor')) or '#ffe9a6', 'stateTextSize':max(14,min(400,safe_int(item.get('stateTextSize',30)))), 'spinStatusTextColor':valid_hex(item.get('spinStatusTextColor')) or '#ffe9a6', 'spinStatusTextSize':max(14,min(400,safe_int(item.get('spinStatusTextSize',28)))),
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
        'spinSeconds':max(.2,min(30,safe_float(raw_gacha.get('spinSeconds',5),5))),
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
        'historyScrollDirection':raw_gacha.get('historyScrollDirection') if raw_gacha.get('historyScrollDirection') in ('vertical','horizontal') else 'vertical',
        'continueRankLimit':max(1,min(10,safe_int(raw_gacha.get('continueRankLimit',10),10))), 'continueRankTextSize':max(14,min(96,safe_int(raw_gacha.get('continueRankTextSize',28),28))), 'continueRankScrollDirection':raw_gacha.get('continueRankScrollDirection') if raw_gacha.get('continueRankScrollDirection') in ('vertical','horizontal') else 'vertical',
        'winRankLimit':max(1,min(10,safe_int(raw_gacha.get('winRankLimit',10),10))), 'winRankTextSize':max(14,min(96,safe_int(raw_gacha.get('winRankTextSize',28),28))), 'winRankScrollDirection':raw_gacha.get('winRankScrollDirection') if raw_gacha.get('winRankScrollDirection') in ('vertical','horizontal') else 'vertical', 'rankingLayoutDirection':raw_gacha.get('rankingLayoutDirection') if raw_gacha.get('rankingLayoutDirection') in ('vertical','horizontal') else 'vertical',
        'continueRankLimit':max(1,min(10,safe_int(raw_gacha.get('continueRankLimit',10),10))), 'continueRankTextSize':max(14,min(96,safe_int(raw_gacha.get('continueRankTextSize',28),28))), 'continueRankScrollDirection':raw_gacha.get('continueRankScrollDirection') if raw_gacha.get('continueRankScrollDirection') in ('vertical','horizontal') else 'vertical',
        'winRankLimit':max(1,min(10,safe_int(raw_gacha.get('winRankLimit',10),10))), 'winRankTextSize':max(14,min(96,safe_int(raw_gacha.get('winRankTextSize',28),28))), 'winRankScrollDirection':raw_gacha.get('winRankScrollDirection') if raw_gacha.get('winRankScrollDirection') in ('vertical','horizontal') else 'vertical', 'rankingLayoutDirection':raw_gacha.get('rankingLayoutDirection') if raw_gacha.get('rankingLayoutDirection') in ('vertical','horizontal') else 'vertical',
        'history':[{'id':max(0,safe_int(item.get('id') or 0)),'senderName':str(item.get('senderName') or '')[:80],'patternName':str(item.get('patternName') or '')[:60],'result':max(-999999,min(999999,safe_int(item.get('result') or 0))),'continueCount':max(0,safe_int(item.get('continueCount') or 0)),'createdAt':max(0,safe_float(item.get('createdAt') or 0))} for item in (raw_gacha.get('history') or []) if isinstance(item,dict)][:200],
        'queue':[x for x in (raw_gacha.get('queue') or []) if isinstance(x,dict)][:100],
        'event':{'id':max(0,safe_int(raw_event.get('id') or 0)), 'type':str(raw_event.get('type') or ''), 'active':event_active, 'isTest':bool(raw_event.get('isTest',False)), 'mode':'single' if raw_event.get('mode')=='single' else 'continue', 'winSign':raw_event.get('winSign') if raw_event.get('winSign') in ('plus','minus','both') else 'plus', 'choice':raw_event.get('choice') if raw_event.get('choice') in ('plus','minus') else '', 'choiceReady':bool(raw_event.get('choiceReady',False)), 'patternId':str(raw_event.get('patternId') or ''), 'patternName':str(raw_event.get('patternName') or ''), 'effectStyle':'fullscreen-slot' if raw_event.get('effectStyle')=='fullscreen-slot' else 'card', 'textRoles':copy.deepcopy(raw_event.get('textRoles')) if isinstance(raw_event.get('textRoles'),dict) else {}, 'outcomes':copy.deepcopy(raw_event.get('outcomes')) if isinstance(raw_event.get('outcomes'),list) else [], 'upperOutcomes':copy.deepcopy(raw_event.get('upperOutcomes')) if isinstance(raw_event.get('upperOutcomes'),list) else [], 'spinNumberImageSize':max(40,min(1200,safe_int(raw_event.get('spinNumberImageSize',760),760))), 'rounds':raw_event.get('rounds') if isinstance(raw_event.get('rounds'),list) else [], 'appliedRounds':[safe_int(x) for x in raw_event.get('appliedRounds',[]) if str(x).isdigit()], 'total':max(-999999,min(999999,safe_int(raw_event.get('total') or 0))), 'currentWin':max(-999999,min(999999,safe_int(raw_event.get('currentWin') or 0))), 'giftName':str(raw_event.get('giftName') or ''), 'senderName':str(raw_event.get('senderName') or '')[:80], 'createdAt':event_created_at},
    }
    raw_pachinko = merged.get('pachinkoGacha') if isinstance(merged.get('pachinkoGacha'),dict) else {}
    pachinko_patterns=[]
    for index,item in enumerate((raw_pachinko.get('patterns') or [])[:50]):
        if not isinstance(item,dict): continue
        raw_text_roles=item.get('textRoles') if isinstance(item.get('textRoles'),dict) else {}
        text_roles={}
        for role in ('pattern','sender','preAlertState','spinState','spinNumber','progress','resultState','resultNumber','reachState','hitState','missState','czState','timeShortState','atState','upperState','luckyTriggerState','continueState','endState','resultWin','setCount','total'):
            source=raw_text_roles.get(role) if isinstance(raw_text_roles.get(role),dict) else (raw_text_roles.get('resultState') if role in ('reachState','hitState','missState','czState','timeShortState','atState','upperState','luckyTriggerState','continueState','endState') and isinstance(raw_text_roles.get('resultState'),dict) else {})
            text_roles[role]={'enabled':source.get('enabled',True) is not False,'text':str(source.get('text') or '')[:120],'colorEnabled':bool(source.get('colorEnabled',False)),'color':valid_hex(source.get('color')) or '#ffffff','size':max(12,min(400,safe_int(source.get('size',0),0))) if source.get('size') else 0,'fontFamily':source.get('fontFamily') if source.get('fontFamily') in ('global','system','native','yuGothic','meiryo','gothic','serif','mono') else 'global','mode':'image' if source.get('mode')=='image' else 'text','imageUrl':str(source.get('imageUrl') or '')[:2000],'imageName':str(source.get('imageName') or '')[:120],'imageSize':max(20,min(600,safe_int(source.get('imageSize',120),120))),'positionEnabled':bool(source.get('positionEnabled',False)),'x':max(0,min(100,safe_float(source.get('x',50),50))),'y':max(0,min(100,safe_float(source.get('y',50),50)))}
        media={}
        for stage in ('spin','reach','cz','hit','at','upper','lt','end','stop','preAlert1','preAlert2','preAlert3')+pachinko_boundary_stages():
            for kind in ('AnimationUrl','AnimationName','AudioUrl','AudioName'):
                key=stage+kind
                media[key]=str(item.get(key) or '')[:2000 if key.endswith('Url') else 120]
            media[stage+'AudioVolume']=max(0,min(100,safe_int(item.get(stage+'AudioVolume',75),75)))
            media[stage+'VideoVolume']=max(0,min(100,safe_int(item.get(stage+'VideoVolume',item.get(stage+'AudioVolume',75)),75)))
            if stage.endswith(('Enter','Exit')): media[stage+'Enabled']=item.get(stage+'Enabled',False) is True
            # Rotation duration and result/media display duration are independent.
            duration_key='spinDisplaySeconds' if stage=='spin' else stage+'Seconds'
            media[duration_key]=max(.2,min(120,safe_float(item.get(duration_key,3),3)))
        at_spins=max(1,min(10000,safe_int(item.get('atSpins',10),10)))
        at_den=max(1,min(1000000,safe_int(item.get('atHitDenominator',1000),1000)))
        at_legacy_rate=max(0,min(100,safe_int(item.get('atContinuationRate',80),80)))/100
        at_default_num=round((1-(1-at_legacy_rate)**(1/at_spins))*at_den)
        upper_spins=max(1,min(10000,safe_int(item.get('upperSpins',10),10)))
        upper_den=max(1,min(1000000,safe_int(item.get('upperHitDenominator',1000),1000)))
        upper_legacy_rate=max(0,min(100,safe_int(item.get('upperContinuationRate',90),90)))/100
        upper_default_num=round((1-(1-upper_legacy_rate)**(1/upper_spins))*upper_den)
        raw_prealerts=item.get('preAlerts') if isinstance(item.get('preAlerts'),list) else []
        prealerts=[]
        for alert_index in range(3):
            alert=raw_prealerts[alert_index] if alert_index<len(raw_prealerts) and isinstance(raw_prealerts[alert_index],dict) else {}
            prealerts.append({'enabled':bool(alert.get('enabled',False)),'condition':alert.get('condition') if alert.get('condition') in ('any','hit','miss','cz-success','cz-fail','at','upper','lt') else 'any','chance':max(0,min(100,safe_int(alert.get('chance',100),100))),'timing':alert.get('timing') if alert.get('timing') in ('spin-start','during-spin','before-result') else 'before-result','displayMode':alert.get('displayMode') if alert.get('displayMode') in ('full','sound-only','sound-text') else 'full','text':str(alert.get('text') or 'チャンス！')[:80],'showText':alert.get('showText',True) is not False,'textSize':max(14,min(300,safe_int(alert.get('textSize',56),56))),'textSeconds':max(.2,min(120,safe_float(alert.get('textSeconds',1.2),1.2))),'mediaSeconds':max(0,min(120,safe_float(alert.get('mediaSeconds',0),0))),'color':valid_hex(alert.get('color')) or '#ffe05b','audioSeconds':max(0,min(120,safe_float(alert.get('audioSeconds',0),0))),'audioVolume':max(0,min(100,safe_int(alert.get('audioVolume',item.get(f'preAlert{alert_index+1}AudioVolume',75)),75))),'videoVolume':max(0,min(100,safe_int(alert.get('videoVolume',75),75))),'animationUrl':media.get(f'preAlert{alert_index+1}AnimationUrl',''),'animationName':media.get(f'preAlert{alert_index+1}AnimationName',''),'audioUrl':media.get(f'preAlert{alert_index+1}AudioUrl',''),'audioName':media.get(f'preAlert{alert_index+1}AudioName','')})
        raw_digits=item.get('digitSettings') if isinstance(item.get('digitSettings'),list) else []
        digit_settings=[]
        for digit in range(10):
            source=raw_digits[digit] if digit<len(raw_digits) and isinstance(raw_digits[digit],dict) else {}
            digit_settings.append({'text':str(source.get('text') if source.get('text') is not None else str(digit))[:8],'fontFamily':source.get('fontFamily') if source.get('fontFamily') in ('global','system','native','yuGothic','meiryo','gothic','serif','mono') else 'global','color':valid_hex(source.get('color')) or '#ffffff','size':max(14,min(400,safe_int(source.get('size',130),130))),'imageUrl':str(source.get('imageUrl') or '')[:2000],'imageName':str(source.get('imageName') or '')[:120],'imageSize':max(20,min(1200,safe_int(source.get('imageSize',130),130)) )})
        pachinko_patterns.append({
            'id':str(item.get('id') or f'pachinko-pattern-{index+1}')[:80], 'name':str(item.get('name') or f'パチンコ{index+1}')[:60], 'enabled':item.get('enabled',True) is not False, 'giftName':str(item.get('giftName') or '').strip()[:120],
            'spinsPerGift':max(1,min(10000,safe_int(item.get('spinsPerGift',10),10))), 'hitNumerator':max(1,min(1000000,safe_int(item.get('hitNumerator',1),1))), 'hitDenominator':max(1,min(1000000,safe_int(item.get('hitDenominator',199),199))), 'spinSeconds':max(.05,min(30,safe_float(item.get('spinSeconds',.8),.8))), 'testPlaybackSpeed':safe_float(item.get('testPlaybackSpeed',1),1) if safe_float(item.get('testPlaybackSpeed',1),1) in (1,.5,.2) else 1,
            'reachMissChance':max(0,min(100,safe_float(item.get('reachMissChance',15),15))),
            'spinBeepEnabled':item.get('spinBeepEnabled',True) is not False, 'spinBeepAudioUrl':str(item.get('spinBeepAudioUrl') or '')[:2000], 'spinBeepAudioName':str(item.get('spinBeepAudioName') or '')[:120], 'spinBeepVolume':max(0,min(100,safe_int(item.get('spinBeepVolume',35),35))),
            'baseWin':max(0,min(999999,safe_int(item.get('baseWin',10),10))), 'czEnabled':bool(item.get('czEnabled',False)), 'czRate':max(0,min(100,safe_int(item.get('czRate',50),50))),
            'timeShortEnabled':bool(item.get('timeShortEnabled',False)), 'timeShortSpins':max(0,min(10000,safe_int(item.get('timeShortSpins',50),50))), 'timeShortHitDenominator':max(1,min(1000000,safe_int(item.get('timeShortHitDenominator',99),99))), 'timeShortSpinSeconds':max(.05,min(30,safe_float(item.get('timeShortSpinSeconds',.8),.8))), 'reachEnabled':item.get('reachEnabled',True) is not False,
            'atEnabled':item.get('atEnabled',True) is not False, 'atEntryRate':max(0,min(100,safe_int(item.get('atEntryRate',50),50))), 'atSpins':at_spins, 'atHitNumerator':max(0,min(at_den,safe_int(item.get('atHitNumerator',at_default_num),at_default_num))), 'atHitDenominator':at_den, 'atSpinSeconds':max(.05,min(30,safe_float(item.get('atSpinSeconds',.8),.8))), 'atMinWin':max(0,min(999999,safe_int(item.get('atMinWin',5),5))), 'atMaxWin':max(0,min(999999,safe_int(item.get('atMaxWin',20),20))),
            'upperEnabled':bool(item.get('upperEnabled',False)), 'upperEntryRate':max(0,min(100,safe_int(item.get('upperEntryRate',10),10))), 'upperSpins':upper_spins, 'upperHitNumerator':max(0,min(upper_den,safe_int(item.get('upperHitNumerator',upper_default_num),upper_default_num))), 'upperHitDenominator':upper_den, 'upperSpinSeconds':max(.05,min(30,safe_float(item.get('upperSpinSeconds',.8),.8))), 'upperMinWin':max(0,min(999999,safe_int(item.get('upperMinWin',20),20))), 'upperMaxWin':max(0,min(999999,safe_int(item.get('upperMaxWin',50),50))),
            'luckyTriggerEnabled':bool(item.get('luckyTriggerEnabled',False)), 'luckyTriggerRate':max(0,min(100,safe_int(item.get('luckyTriggerRate',5),5))), 'luckyTriggerContinuationRate':max(0,min(100,safe_int(item.get('luckyTriggerContinuationRate',95),95))), 'luckyTriggerSpinSeconds':max(.05,min(30,safe_float(item.get('luckyTriggerSpinSeconds',.8),.8))), 'luckyTriggerMinWin':max(0,min(999999,safe_int(item.get('luckyTriggerMinWin',50),50))), 'luckyTriggerMaxWin':max(0,min(999999,safe_int(item.get('luckyTriggerMaxWin',100),100))),
            'effectStyle':'fullscreen' if item.get('effectStyle')=='fullscreen' else 'card', 'cardBg':valid_hex(item.get('cardBg')) or '#120b18', 'accentColor':valid_hex(item.get('accentColor')) or '#ff3d66', 'textColor':valid_hex(item.get('textColor')) or '#ffffff', 'fontSize':max(18,min(300,safe_int(item.get('fontSize',64),64))), 'textRoles':text_roles, 'preAlerts':prealerts, 'digitSettings':digit_settings, **media
        })
        configured=pachinko_patterns[-1]
        configured['winSign']=item.get('winSign') if item.get('winSign') in ('plus','minus','both') else 'plus'
        # Keep the legacy stage-level and per-alert audio volumes consistent.
        # Older saves/players used preAlertNAudioVolume; the editor uses preAlerts.
        for alert_index,alert in enumerate(prealerts):
            configured[f'preAlert{alert_index+1}AudioVolume']=alert['audioVolume']
        for digit,settings in enumerate(digit_settings):
            source=raw_digits[digit] if digit<len(raw_digits) and isinstance(raw_digits[digit],dict) else {}
            settings['enabled']=source.get('enabled',True) is not False
        # At least two symbols are needed to depict a miss without triple digits.
        if sum(x['enabled'] for x in digit_settings)<2:
            for settings in digit_settings:
                if sum(x['enabled'] for x in digit_settings)>=2: break
                settings['enabled']=True
        for prefix in ('normal','timeShort','at','upper','luckyTrigger'):
            configured[prefix+'WinOutcomes']=normalize_pachinko_payouts(item.get(prefix+'WinOutcomes'))
            configured[prefix+'WinMode']=item.get(prefix+'WinMode') if item.get(prefix+'WinMode') in ('legacy','weighted') else ('weighted' if configured[prefix+'WinOutcomes'] else 'legacy')
        for prefix,default_rate in (('at',80),('upper',90),('luckyTrigger',95)):
            configured[prefix+'Mode']=item.get(prefix+'Mode') if item.get(prefix+'Mode') in ('st','continue') else ('continue' if prefix=='luckyTrigger' else 'st')
            configured[prefix+'ContinuationRate']=max(0,min(100,safe_float(item.get(prefix+'ContinuationRate',default_rate),default_rate)))
            configured[prefix+'EndMissEnabled']=item.get(prefix+'EndMissEnabled',False) is True
            configured[prefix+'ContinueMissEnabled']=item.get(prefix+'ContinueMissEnabled',False) is True
            configured[prefix+'ContinueMissChance']=max(0,min(100,safe_float(item.get(prefix+'ContinueMissChance',20),20)))
        configured['luckyTriggerSpins']=max(1,min(10000,safe_int(item.get('luckyTriggerSpins',10),10)))
        configured['luckyTriggerHitDenominator']=max(1,min(1000000,safe_int(item.get('luckyTriggerHitDenominator',1000),1000)))
        configured['luckyTriggerHitNumerator']=max(0,min(configured['luckyTriggerHitDenominator'],safe_int(item.get('luckyTriggerHitNumerator',259),259)))
        configured['timeShortDisplaySeconds']=max(.2,min(120,safe_float(item.get('timeShortDisplaySeconds',item.get('stopSeconds',3)),3)))
        for prefix,stage in (('at','at'),('upper','upper'),('luckyTrigger','lt')):
            configured[prefix+'ResultSeconds']=max(.2,min(120,safe_float(item.get(prefix+'ResultSeconds',item.get(stage+'Seconds',3)),3)))
    raw_p_event=raw_pachinko.get('event') if isinstance(raw_pachinko.get('event'),dict) else {}
    p_created=max(0,safe_float(raw_p_event.get('createdAt') or 0));p_active=bool(raw_p_event.get('active',False)) and p_created>=SERVER_STARTED_AT
    merged['pachinkoGacha']={'patterns':pachinko_patterns,'queue':[x for x in (raw_pachinko.get('queue') or []) if isinstance(x,dict)][:100],'history':[x for x in (raw_pachinko.get('history') or []) if isinstance(x,dict)][:200],'event':{'id':max(0,safe_int(raw_p_event.get('id') or 0)),'type':'pachinko-gacha' if raw_p_event.get('type')=='pachinko-gacha' else '','active':p_active,'isTest':bool(raw_p_event.get('isTest',False)),'patternId':str(raw_p_event.get('patternId') or '')[:80],'patternName':str(raw_p_event.get('patternName') or '')[:60],'senderName':str(raw_p_event.get('senderName') or '')[:80],'spins':max(0,safe_int(raw_p_event.get('spins') or 0)),'hitSpin':max(0,safe_int(raw_p_event.get('hitSpin') or 0)),'timeShortSpins':max(0,min(10000,safe_int(raw_p_event.get('timeShortSpins',0),0))),'timeShortHitSpin':max(0,min(10000,safe_int(raw_p_event.get('timeShortHitSpin',0),0))),'route':str(raw_p_event.get('route') or '')[:30],'preAlertIndex':max(-1,min(2,safe_int(raw_p_event.get('preAlertIndex',-1),-1))),'preAlertTiming':raw_p_event.get('preAlertTiming') if raw_p_event.get('preAlertTiming') in ('spin-start','during-spin','before-result') else 'before-result','rounds':raw_p_event.get('rounds') if isinstance(raw_p_event.get('rounds'),list) else [],'total':max(0,min(999999,safe_int(raw_p_event.get('total') or 0))),'createdAt':p_created}}

    for key in ('initialWin','timeShortWin'):
        if key in raw_p_event:
            merged['pachinkoGacha']['event'][key]=max(0,min(999999,safe_int(raw_p_event[key],0)))
    for key in ('czUsed','czSuccess'):
        if key in raw_p_event: merged['pachinkoGacha']['event'][key]=bool(raw_p_event[key])
    p_event=merged['pachinkoGacha']['event']
    p_event.update(winSign=raw_p_event.get('winSign') if raw_p_event.get('winSign') in ('plus','minus','both') else 'plus',
                   choice=raw_p_event.get('choice') if raw_p_event.get('choice') in ('plus','minus') else '',
                   choiceReady=bool(raw_p_event.get('choiceReady',False)),winApplied=bool(raw_p_event.get('winApplied',False)))
    for field in ('shortcutChoicePlus','shortcutChoiceMinus'):
        merged['pachinkoGacha'][field]=str(raw_pachinko.get(field) or '').upper()[:100]

    # Store one independent WIN counter + WIN gacha snapshot per game profile.
    # Older saves are migrated into a single profile without changing values.
    raw_profiles = data.get('winProfiles') if isinstance(data.get('winProfiles'), list) else []
    active_profile_id = str(data.get('activeWinProfileId') or '')[:80]
    profiles = []
    seen_profile_ids = set()
    profiles_missing_other = set()
    for index, item in enumerate(raw_profiles[:50]):
        if not isinstance(item, dict):
            continue
        profile_id = str(item.get('id') or f'win-profile-{index + 1}')[:80]
        if profile_id in seen_profile_ids:
            profile_id = f'{profile_id}-{index + 1}'
        seen_profile_ids.add(profile_id)
        if not isinstance(item.get('otherGacha'), dict):
            profiles_missing_other.add(profile_id)
        profiles.append({
            'id': profile_id,
            'name': str(item.get('name') or f'プロファイル{index + 1}')[:40],
            'enabled': item.get('enabled', True) is not False,
            'winCounter': item.get('winCounter') if isinstance(item.get('winCounter'), dict) else {},
            'gacha': item.get('gacha') if isinstance(item.get('gacha'), dict) else {},
            'otherGacha': item.get('otherGacha') if isinstance(item.get('otherGacha'), dict) else {},
        })
    if not profiles:
        profiles = [{'id':'win-profile-default','name':'標準','enabled':True,'winCounter':copy.deepcopy(merged['winCounter']),'gacha':copy.deepcopy(merged['gacha']),'otherGacha':copy.deepcopy(merged['otherGacha'])}]
        active_profile_id = profiles[0]['id']
    active_profile = next((item for item in profiles if item['id'] == active_profile_id and item['enabled']), None)
    if active_profile is None:
        active_profile = next((item for item in profiles if item['enabled']), profiles[0])
        active_profile['enabled'] = True
        active_profile_id = active_profile['id']
    # Only the selected/active profile is running. Migrate legacy global Other Gacha
    # settings into the active profile once, then restore that profile's own settings.
    for profile in profiles:
        profile['enabled'] = profile['id'] == active_profile_id
    if active_profile_id in profiles_missing_other:
        # One-time migration: the old app stored Other Gacha globally.
        active_profile['otherGacha'] = copy.deepcopy(merged['otherGacha'])
    else:
        merged['otherGacha'] = copy.deepcopy(active_profile.get('otherGacha') or {})
        # Do not revive an animation or queued gift from an earlier server session.
        profile_other = merged['otherGacha']
        if not isinstance(profile_other, dict):
            profile_other = {}
        profile_event = profile_other.get('event') if isinstance(profile_other.get('event'), dict) else {}
        profile_event_created = max(0, safe_float(profile_event.get('createdAt') or 0))
        profile_event_active = bool(profile_event.get('active', False)) and profile_event_created >= SERVER_STARTED_AT
        profile_event['active'] = profile_event_active
        profile_other['event'] = profile_event
        profile_other['queue'] = [x for x in (profile_other.get('queue') or []) if isinstance(x, dict)][:100] if profile_event_active else []
        merged['otherGacha'] = profile_other
    active_profile['winCounter'] = copy.deepcopy(merged['winCounter'])
    active_profile['gacha'] = copy.deepcopy(merged['gacha'])
    active_profile['otherGacha'] = copy.deepcopy(merged['otherGacha'])
    merged['winProfiles'] = profiles
    merged['activeWinProfileId'] = active_profile_id
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
    if merged.get('winProfiles') != data.get('winProfiles') or merged.get('activeWinProfileId') != data.get('activeWinProfileId'):
        changed = True
    if merged.get('minecraftBridge') != data.get('minecraftBridge', DEFAULT['minecraftBridge']):
        changed = True
    if merged.get('gtaBridge') != data.get('gtaBridge', DEFAULT['gtaBridge']):
        changed = True
    if merged.get('tiktokUsername') != data.get('tiktokUsername', ''):
        changed = True
    if merged.get('timer') != data.get('timer', DEFAULT['timer']):
        changed = True
    if merged.get('smokingTimer') != data.get('smokingTimer', DEFAULT['smokingTimer']):
        changed = True
    if merged.get('winProfiles') != data.get('winProfiles') or merged.get('activeWinProfileId') != data.get('activeWinProfileId'):
        changed = True
    if merged.get('gacha') != data.get('gacha', DEFAULT['gacha']):
        changed = True
    if merged.get('otherGacha') != data.get('otherGacha', DEFAULT['otherGacha']):
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

def read_overlay_state(kind):
    """Small, consistent playback snapshots; never expose profiles/history to renderers."""
    def signature():
        try:
            stat = STATE.stat()
            return (stat.st_mtime_ns, stat.st_ctime_ns, stat.st_size)
        except OSError:
            return None
    with OVERLAY_SNAPSHOT_LOCK:
        cache = OVERLAY_SNAPSHOT_CACHE
        current_signature = signature()
        if cache['state'] is None or cache['signature'] != current_signature or time.monotonic() - cache['at'] >= .2:
            cache['state'] = read_state()
            # If a writer races us after read_state releases STATE_LOCK, keep the
            # earlier signature so the next request invalidates this snapshot.
            cache['signature'] = current_signature
            cache['at'] = time.monotonic()
        state = cache['state']
        common = ('fontFamily', 'accent', 'panelColor', 'panelOpacity', 'textColor', 'gaugeColor',
                  'textGlowEnabled', 'textGlowColor', 'textGlowStrength', 'cardDefaults',
                  'textOutlineEnabled', 'textOutlineColor', 'textOutlineWidth',
                  'textBackgroundEnabled', 'textBackgroundColor', 'textBackgroundOpacity')
        result = {key: state[key] for key in common if key in state}
        if kind == 'win':
            result['winCounter'] = {key: value for key, value in state['winCounter'].items()
                                    if key != 'giftRules' and not key.startswith('shortcut')}
            result['textEffects'] = {'win': state.get('textEffects', {}).get('win', {})}
        elif kind == 'gacha':
            gacha = state['gacha']
            event = gacha.get('event', {})
            pattern = next((p for p in gacha.get('patterns', [])
                            if (event.get('patternId') and p.get('id') == event['patternId'])
                            or (not event.get('patternId') and p.get('name') == event.get('patternName'))), None)
            result['gacha'] = {key: value for key, value in gacha.items()
                               if key not in ('patterns', 'queue', 'history')}
            result['gacha']['patterns'] = [pattern] if pattern else []
            effect_key = 'gacha:' + str(event.get('patternId') or '')
            result['textEffects'] = {effect_key: state.get('textEffects', {}).get(effect_key, {})}
        elif kind == 'pachinko':
            machine=state['pachinkoGacha'];event=machine.get('event',{})
            pattern=next((p for p in machine.get('patterns',[]) if p.get('id')==event.get('patternId')),None)
            result['pachinkoGacha']={'event':event,'patterns':[pattern] if pattern else []}
        else:
            raise ValueError('Unknown overlay snapshot')
        return copy.deepcopy(result)

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
        elif action['type'] == 'pachinkoChoice':
            choose_pachinko_sign_in_state(data,action['choice'])
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

def sync_active_profile_other_gacha(data):
    """Keep server-side Other Gacha changes in the active profile snapshot.

    Other Gacha belongs to each game profile.  Upload/test/complete requests
    mutate the live top-level value directly, so copy that value into the
    active profile before normalize_state restores the profile snapshot.
    """
    active_id = str(data.get('activeWinProfileId') or '')
    profiles = data.get('winProfiles') if isinstance(data.get('winProfiles'), list) else []
    active = next((item for item in profiles if isinstance(item, dict) and str(item.get('id') or '') == active_id), None)
    if active is None:
        active = next((item for item in profiles if isinstance(item, dict) and item.get('enabled', True)), None)
    if active is not None:
        active['otherGacha'] = copy.deepcopy(data.get('otherGacha') or {})

def run_other_gacha_draw(data, pattern, sender_name='テスト'):
    other=data['otherGacha']; rounds=[]
    outcomes=pattern.get('outcomes') or []
    if not outcomes: return False
    for _ in range(50):
        outcome=random.choices(outcomes,weights=[max(1,int(x.get('probability') or 1)) for x in outcomes],k=1)[0]
        continued=pattern.get('mode')=='continue' and random.random()*100 < max(0,min(100,int(pattern.get('continuationRate',70))))
        rounds.append({'label':str(outcome.get('label') or '')[:100], 'continued':continued})
        if not continued: break
    used=[int(other.get('event',{}).get('id') or 0)]+[int(x.get('id') or 0) for x in other.get('queue',[]) if isinstance(x,dict)]
    event={'id':max(used,default=0)+1,'type':'other-gacha','active':False,'patternId':pattern['id'],'patternName':pattern['name'],'rounds':rounds,'outcomes':[{'label':x['label']} for x in outcomes],'spinSeconds':pattern.get('spinSeconds',5),'effectStyle':pattern.get('effectStyle','slot'),'resultColor':pattern.get('resultColor','#fff'),'resultSize':pattern.get('resultSize',100),'background':pattern.get('background','#17151c'),'opacity':pattern.get('opacity',90),'layout':copy.deepcopy(pattern.get('layout',{})),'sceneLayouts':copy.deepcopy(pattern.get('sceneLayouts',{})),'sceneStyles':copy.deepcopy(pattern.get('sceneStyles',{})),'animationUrl':pattern.get('animationUrl',''),'audioUrl':pattern.get('audioUrl',''),'audioVolume':pattern.get('audioVolume',75),'resultAudioUrl':pattern.get('resultAudioUrl',''),'resultAudioVolume':pattern.get('resultAudioVolume',80),'videoAudioEnabled':pattern.get('videoAudioEnabled',True),'videoVolume':pattern.get('videoVolume',75),'senderName':str(sender_name or '')[:80],'createdAt':time.time()}
    if other.get('event',{}).get('active'): other.setdefault('queue',[]).append(event)
    else: event['active']=True;other['event']=event
    sync_active_profile_other_gacha(data)
    return True

def complete_other_gacha_event(event_id):
    with STATE_LOCK:
        try: data=json.loads(STATE.read_text(encoding='utf-8'))
        except Exception: data=copy.deepcopy(DEFAULT)
        data,_=normalize_state(data);other=data['otherGacha'];event=other['event']
        if int(event.get('id') or 0)!=event_id or not event.get('active'): return False
        event['active']=False;queue=other.setdefault('queue',[])
        if queue:
            next_event=queue.pop(0);next_event['active']=True;next_event['createdAt']=time.time();other['event']=next_event
        sync_active_profile_other_gacha(data)
        STATE.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
        return True

def normalize_pachinko_payouts(rows):
    return [{'value':max(0,min(999999,safe_int(row.get('value',0),0))),
             'probability':max(0,min(100,safe_float(row.get('probability',0),0)))}
            for row in (rows if isinstance(rows,list) else [])[:100] if isinstance(row,dict)]

def pachinko_payout(pattern, prefix, minimum, maximum=None):
    rows=[] if pattern.get(prefix+'WinMode')=='legacy' else [row for row in normalize_pachinko_payouts(pattern.get(prefix+'WinOutcomes')) if row['probability']>0]
    if rows:
        return random.choices([row['value'] for row in rows],weights=[row['probability'] for row in rows],k=1)[0]
    lo,hi=sorted((max(0,int(minimum)),max(0,int(maximum if maximum is not None else minimum))))
    return random.randint(lo,hi)

def run_pachinko_draw(data, pattern, sender_name='テスト', is_test=False, test_pre_alert_index=None):
    machine=data['pachinkoGacha'];spins=max(1,int(pattern.get('spinsPerGift',10)));den=max(1,int(pattern.get('hitDenominator',199)));num=max(1,min(den,int(pattern.get('hitNumerator',1))))
    hit_spin=0
    for spin in range(1,spins+1):
        if random.randint(1,den)<=num: hit_spin=spin;break
    route='miss';rounds=[];total=0;initial_win=0;time_short_win=0;short_spins=0;time_short_hit_spin=0
    if hit_spin:
        route='hit';initial_win=pachinko_payout(pattern,'normal',pattern.get('baseWin',10));total=initial_win
        cz_success=True
        if pattern.get('czEnabled'):
            cz_success=random.random()*100<float(pattern.get('czRate',50));route='cz-success' if cz_success else 'cz-fail'
        if cz_success and pattern.get('atEnabled') and random.random()*100<float(pattern.get('atEntryRate',50)):
            route='at';phase='at';guard=0
            while guard<1000:
                guard+=1
                prefix={'at':'at','upper':'upper','lt':'luckyTrigger'}[phase]
                mode=pattern.get(prefix+'Mode','continue' if phase=='lt' else 'st')
                defaults={'at':(5,20,155,80),'upper':(20,50,206,90),'lt':(50,100,259,95)}[phase]
                lo,hi=sorted((int(pattern.get(prefix+'MinWin',defaults[0])),int(pattern.get(prefix+'MaxWin',defaults[1]))))
                phase_spins=1 if mode=='continue' else max(1,min(10000,int(pattern.get(prefix+'Spins',10))))
                hit_den=max(1,int(pattern.get(prefix+'HitDenominator',1000)))
                hit_num=max(0,min(hit_den,int(pattern.get(prefix+'HitNumerator',defaults[2]))))
                phase_hit_spin=1 if mode=='continue' else 0
                if mode!='continue':
                    for phase_spin in range(1,phase_spins+1):
                        if random.randint(1,hit_den)<=hit_num:
                            phase_hit_spin=phase_spin
                            break
                if phase_hit_spin:
                    win=pachinko_payout(pattern,prefix,lo,hi)
                    continued=(random.random()*100<float(pattern.get(prefix+'ContinuationRate',defaults[3]))) if mode=='continue' else True
                    result_kind='win'
                    if mode=='continue':
                        if not continued and pattern.get(prefix+'EndMissEnabled',False):
                            win=0;phase_hit_spin=0;result_kind='end-miss'
                        elif continued and pattern.get(prefix+'ContinueMissEnabled',False) and random.random()*100<float(pattern.get(prefix+'ContinueMissChance',20)):
                            win=0;phase_hit_spin=0;result_kind='continue-miss'
                    total=min(999999,total+win)
                else:
                    win=0
                    continued=False
                    result_kind='end-miss'
                next_phase=phase
                if continued and phase_hit_spin and phase=='at' and pattern.get('upperEnabled') and random.random()*100<float(pattern.get('upperEntryRate',10)): next_phase='upper'
                if continued and phase_hit_spin and phase in ('at','upper') and pattern.get('luckyTriggerEnabled') and random.random()*100<float(pattern.get('luckyTriggerRate',5)): next_phase='lt'
                rounds.append({'phase':phase,'mode':mode,'resultKind':result_kind,'win':win,'total':total,'continued':continued,'nextPhase':next_phase,'spins':phase_spins,'hitSpin':phase_hit_spin})
                if not continued or guard>=1000: break
                phase=next_phase
        elif pattern.get('timeShortEnabled'):
            route='time-short';short_spins=max(0,int(pattern.get('timeShortSpins',50)));short_den=max(1,int(pattern.get('timeShortHitDenominator',99)));time_short_hit_spin=0
            for spin in range(1,short_spins+1):
                if random.randint(1,short_den)==1:
                    route='time-short-hit';time_short_hit_spin=spin;time_short_win=pachinko_payout(pattern,'timeShort',pattern.get('baseWin',10));total=min(999999,total+time_short_win);break
        else:
            short_spins=0;time_short_hit_spin=0
    def prealert_matches(alert):
        if not alert.get('enabled'): return False
        condition=alert.get('condition','any')
        if condition=='hit' and not hit_spin: return False
        if condition=='miss' and hit_spin: return False
        if condition=='cz-success' and route!='cz-success': return False
        if condition=='cz-fail' and route!='cz-fail': return False
        if condition=='at' and not any(r.get('phase')=='at' for r in rounds): return False
        if condition=='upper' and not any(r.get('phase')=='upper' for r in rounds): return False
        if condition=='lt' and not any(r.get('phase')=='lt' for r in rounds): return False
        return random.random()*100 < max(0,min(100,int(alert.get('chance',100))))
    matching_alerts=[index for index,alert in enumerate(pattern.get('preAlerts',[])[:3]) if prealert_matches(alert)]
    if is_test and test_pre_alert_index is not None and 0 <= safe_int(test_pre_alert_index,-1) < min(3,len(pattern.get('preAlerts',[]))):
        # Dedicated preview: force the selected alert without changing live chance/condition rules.
        prealert_index=safe_int(test_pre_alert_index,-1)
    else:
        prealert_index=random.choice(matching_alerts) if matching_alerts else -1
    prealert=pattern.get('preAlerts',[{}])[prealert_index] if prealert_index>=0 else {}
    ids=[safe_int(machine.get('event',{}).get('id') or 0)]+[safe_int(x.get('id') or 0) for x in machine.get('queue',[]) if isinstance(x,dict)]
    event={'id':max(ids,default=0)+1,'type':'pachinko-gacha','active':False,'isTest':bool(is_test),'patternId':pattern['id'],'patternName':pattern['name'],'senderName':str(sender_name or '')[:80],'spins':spins,'hitSpin':hit_spin,'timeShortSpins':short_spins if hit_spin and pattern.get('timeShortEnabled') and not rounds else 0,'timeShortHitSpin':time_short_hit_spin if hit_spin and pattern.get('timeShortEnabled') and not rounds else 0,'route':route,'rounds':rounds,'total':total,'preAlertIndex':prealert_index,'preAlertTiming':prealert.get('timing','before-result') if prealert_index>=0 else 'before-result','createdAt':time.time()}
    event.update(initialWin=initial_win,timeShortWin=time_short_win)
    event.update(czUsed=bool(hit_spin and pattern.get('czEnabled')),czSuccess=bool(hit_spin and pattern.get('czEnabled') and cz_success))
    event.update(winSign=pattern.get('winSign') if pattern.get('winSign') in ('plus','minus','both') else 'plus',choice='',choiceReady=False,winApplied=False)
    if machine.get('event',{}).get('active'): machine.setdefault('queue',[]).append(event)
    else: event['active']=True;machine['event']=event
    return True

def build_pachinko_preview(pattern):
    """Generate the real lottery flow in isolated memory, never enqueue or award."""
    sandbox=copy.deepcopy(DEFAULT)
    sandbox['pachinkoGacha']={'patterns':[pattern],'queue':[],'history':[],'event':{}}
    sandbox,_=normalize_state(sandbox)
    normalized=sandbox['pachinkoGacha']['patterns'][0]
    run_pachinko_draw(sandbox,normalized,'プレビュー',is_test=True)
    event=sandbox['pachinkoGacha']['event'];event['preview']=True
    return {'ok':True,'pattern':normalized,'event':event}

def skip_pachinko_event(event_id,scope='current',created_at=None,expected_queue=None):
    """Explicit skip only: preserve WIN/history and reject stale current IDs."""
    with STATE_LOCK:
        try: data=json.loads(STATE.read_text(encoding='utf-8'))
        except Exception: return False
        data,_=normalize_state(data);machine=data['pachinkoGacha'];event=machine['event'];pending=machine.setdefault('queue',[])
        if scope=='waiting':
            index=next((i for i,e in enumerate(pending) if safe_int(e.get('id'))==event_id),None)
            if index is None: return False
            if created_at is not None and safe_float(pending[index].get('createdAt'))!=safe_float(created_at): return False
            pending.pop(index)
        elif scope=='queue':
            if not pending or not isinstance(expected_queue,list): return False
            tokens={(safe_int(e.get('id')),safe_float(e.get('createdAt'))) for e in expected_queue if isinstance(e,dict)}
            remaining=[e for e in pending if (safe_int(e.get('id')),safe_float(e.get('createdAt'))) not in tokens]
            if len(remaining)==len(pending): return False
            pending[:]=remaining
        elif scope=='current':
            if not event.get('active') or safe_int(event.get('id'))!=event_id: return False
            if created_at is not None and safe_float(event.get('createdAt'))!=safe_float(created_at): return False
            event['active']=False
            if pending:
                following=pending.pop(0);following['active']=True;following['createdAt']=time.time();machine['event']=following
        else: return False
        STATE.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
        return True

def pachinko_signed_total(event):
    sign=event.get('choice') if event.get('winSign')=='both' else event.get('winSign','plus')
    return abs(safe_int(event.get('total')))*(-1 if sign=='minus' else 1)

def record_pachinko_history(data,event):
    history=data['pachinkoGacha'].setdefault('history',[])
    if event.get('isTest') or any(safe_int(row.get('id'))==safe_int(event.get('id')) and safe_float(row.get('eventCreatedAt',-1))==safe_float(event.get('createdAt')) for row in history): return
    history.insert(0,{'id':event['id'],'senderName':event.get('senderName',''),'patternName':event.get('patternName',''),'route':event.get('route',''),'total':pachinko_signed_total(event),'winSign':event.get('winSign','plus'),'choice':event.get('choice',''),'eventCreatedAt':event.get('createdAt',0),'createdAt':time.time()})
    del history[200:]

def choose_pachinko_sign_in_state(data,choice):
    event=data['pachinkoGacha']['event']
    if choice not in ('plus','minus') or event.get('type')!='pachinko-gacha' or not event.get('active') or event.get('winSign')!='both' or not event.get('choiceReady') or event.get('choice') or event.get('winApplied'): return False
    event['choice']=choice
    if not event.get('isTest'):
        win=data['winCounter'];win['currentWin']=max(-999999,min(999999,win['currentWin']+pachinko_signed_total(event)))
    event['winApplied']=True
    record_pachinko_history(data,event)
    return True

def pachinko_choice_action(event_id,choice=None,created_at=None):
    with STATE_LOCK:
        try: data=json.loads(STATE.read_text(encoding='utf-8'))
        except Exception: return False
        data,_=normalize_state(data);event=data['pachinkoGacha']['event']
        if safe_int(event.get('id'))!=event_id or not event.get('active') or event.get('winSign')!='both': return False
        if created_at is not None and safe_float(event.get('createdAt'))!=safe_float(created_at): return False
        if choice is None: event['choiceReady']=True
        elif not choose_pachinko_sign_in_state(data,choice): return False
        STATE.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
        return True

def complete_pachinko_event(event_id):
    with STATE_LOCK:
        try: data=json.loads(STATE.read_text(encoding='utf-8'))
        except Exception: data=copy.deepcopy(DEFAULT)
        data,_=normalize_state(data);machine=data['pachinkoGacha'];event=machine['event']
        if safe_int(event.get('id') or 0)!=safe_int(event_id) or not event.get('active'): return False
        if event.get('winSign')=='both' and not event.get('choice'): return False
        if not event.get('isTest'):
            if not event.get('winApplied'): data['winCounter']['currentWin']=max(-999999,min(999999,data['winCounter']['currentWin']+pachinko_signed_total(event)))
            record_pachinko_history(data,event)
        event['active']=False;queue=machine.setdefault('queue',[])
        if queue:
            nxt=queue.pop(0);nxt['active']=True;nxt['createdAt']=time.time();machine['event']=nxt
        STATE.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8');return True

def queue_gift_media_event(data, rule, gift_name, sender_name='', count=1):
    media=data['giftMedia']; current=media.get('event') or {}; queued=media.setdefault('queue',[])
    used=[safe_int(current.get('id') or 0)]+[safe_int(x.get('id') or 0) for x in queued if isinstance(x,dict)]
    event={'id':max(used,default=0)+1,'type':'gift-media','active':False,'ruleId':rule['id'],'ruleName':rule.get('name','ギフト演出'),'giftName':str(gift_name or rule.get('giftName') or '')[:120],'senderName':str(sender_name or '')[:80],'count':max(1,safe_int(count,1)),'imageUrl':rule.get('imageUrl',''),'videoUrl':rule.get('videoUrl',''),'audioUrl':rule.get('audioUrl',''),'audioVolume':rule.get('audioVolume',75),'videoVolume':rule.get('videoVolume',75),'width':rule.get('width',800),'height':rule.get('height',450),'duration':rule.get('duration',6),'createdAt':time.time()}
    if current.get('active'): queued.append(event)
    else: event['active']=True;media['event']=event
    return True

def complete_gift_media_event(event_id):
    with STATE_LOCK:
        try: data=json.loads(STATE.read_text(encoding='utf-8'))
        except Exception: data=copy.deepcopy(DEFAULT)
        data,_=normalize_state(data);media=data['giftMedia'];event=media['event']
        if safe_int(event.get('id') or 0)!=event_id or not event.get('active'): return False
        event['active']=False;pending=media.setdefault('queue',[])
        if pending:
            next_event=pending.pop(0);next_event['active']=True;next_event['createdAt']=time.time();media['event']=next_event
        STATE.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
        return True

def run_gacha_draw(data, pattern, gift_name='テスト', sender_name='', is_test=False):
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
    # No fixed SET ceiling: keep drawing until the continuation lottery fails.
    # A true 100% rate can never finish, so only that case gets an emergency
    # guard to keep the app and LIVE Studio responsive.
    set_count=0
    while True:
        set_count+=1
        is_upper=phase=='upper'
        outcome_source=pattern.get('upperOutcomes',[]) if is_upper and pattern.get('upperOutcomeMode')=='weighted' else pattern.get('outcomes',[])
        outcome_mode=pattern.get('upperOutcomeMode') if is_upper else pattern.get('outcomeMode')
        fixed_outcomes=[item for item in outcome_source if isinstance(item,dict)] if outcome_mode=='weighted' else []
        weighted=[item for item in fixed_outcomes if int(item.get('probability') or 0)>0]
        # Fixed-number mode must never fall back to the min/max range. If every
        # probability is temporarily zero, draw equally from the configured
        # fixed values; if no value exists, safely return 0 WIN.
        fixed_pool=weighted or fixed_outcomes
        picked=(random.choices(weighted,weights=[item['probability'] for item in weighted],k=1)[0] if weighted else random.choice(fixed_pool) if fixed_pool else {'value':0}) if outcome_mode=='weighted' else None
        if outcome_mode=='weighted':
            delta=abs(int(picked.get('value') or 0))
        elif is_upper:
            upper_low,upper_high=sorted((abs(int(pattern.get('upperMinWin',magnitude_low))),abs(int(pattern.get('upperMaxWin',magnitude_high)))))
            delta=random.randint(upper_low,upper_high)
        else:
            delta=random.randint(low,high)
        if sign=='minus': delta=-abs(delta)
        elif sign in ('plus','both'): delta=abs(delta)
        total=max(-999999,min(999999,total+delta)); earned=max(-999999,min(999999,earned+delta))
        active_rate=upper_rate if phase=='upper' else rate
        keep_going=(mode=='continue' and random.random()*100 < active_rate)
        if active_rate>=100 and set_count>=1000:
            keep_going=False
        enter_upper=bool(keep_going and phase=='normal' and upper_enabled and random.random()*100 < upper_enter_rate)
        configured_candidates=pattern.get('spinCandidates') if pattern.get('spinCandidateMode')=='custom' else []
        if outcome_mode=='weighted':
            candidate_items=weighted or fixed_outcomes
            source_candidates=list(dict.fromkeys(abs(int(item.get('value') or 0)) for item in candidate_items))
        else:
            candidate_low,candidate_high=(upper_low,upper_high) if is_upper else (magnitude_low,magnitude_high)
            source_candidates=list(range(candidate_low,candidate_high+1))[:100]
        spin_candidates=configured_candidates or source_candidates or [abs(delta)]
        rounds.append({'delta':delta,'total':earned,'currentWin':total,'continued':keep_going,'phase':phase,'upperEntered':enter_upper,'spinSeconds':float(pattern.get('upperSpinSeconds',pattern.get('spinSeconds',5))) if is_upper else float(pattern.get('spinSeconds',5)),'spinCandidates':spin_candidates[:100],'spinImageUrl':str((picked or {}).get('spinImageUrl') or ''),'spinImageSize':max(40,min(1200,safe_int((picked or {}).get('spinImageSize',pattern.get('spinNumberImageSize',760)),760))),'spinTextEnabled':(picked or {}).get('spinTextEnabled',True) is not False,'spinText':str((picked or {}).get('spinText') or ''),'spinTextColor':valid_hex((picked or {}).get('spinTextColor')) or '#ffffff','spinTextSize':max(0,min(600,safe_int((picked or {}).get('spinTextSize',0),0))),'spinFontFamily':(picked or {}).get('spinFontFamily') if (picked or {}).get('spinFontFamily') in ('global','system','native','yuGothic','meiryo','gothic','serif','mono') else 'global','resultImageUrl':str((picked or {}).get('resultImageUrl') or ''),'resultImageSize':max(40,min(1200,safe_int((picked or {}).get('resultImageSize',760),760))),'resultTextEnabled':(picked or {}).get('resultTextEnabled',True) is not False,'resultText':str((picked or {}).get('resultText') or ''),'resultTextColor':valid_hex((picked or {}).get('resultTextColor')) or '#ffffff','resultTextSize':max(0,min(600,safe_int((picked or {}).get('resultTextSize',0),0))),'resultFontFamily':(picked or {}).get('resultFontFamily') if (picked or {}).get('resultFontFamily') in ('global','system','native','yuGothic','meiryo','gothic','serif','mono') else 'global'})
        if not valid_hex((picked or {}).get('spinTextColor')): rounds[-1]['spinTextColor']=''
        if not valid_hex((picked or {}).get('resultTextColor')): rounds[-1]['resultTextColor']=''
        if not keep_going: break
        if enter_upper: phase='upper'
    used_ids=[int(gacha.get('event',{}).get('id') or 0)]+[int(x.get('id') or 0) for x in gacha.get('queue',[]) if isinstance(x,dict)]
    event={'id':max(used_ids,default=0)+1,'type':'gacha','active':False,'isTest':bool(is_test),'mode':mode,'winSign':sign,'choice':'','choiceReady':False,'patternId':pattern['id'],'patternName':pattern['name'],'effectStyle':'fullscreen-slot' if pattern.get('effectStyle')=='fullscreen-slot' else 'card','textRoles':copy.deepcopy(pattern.get('textRoles') or {}),'outcomes':copy.deepcopy(pattern.get('outcomes') or []),'upperOutcomes':copy.deepcopy(pattern.get('upperOutcomes') or []),'spinNumberImageSize':max(40,min(1200,safe_int(pattern.get('spinNumberImageSize',760),760))),'rounds':rounds,'appliedRounds':[],'total':earned,'currentWin':total,'giftName':gift_name,'senderName':str(sender_name or '')[:80],'createdAt':time.time()}
    queue=gacha.setdefault('queue',[])
    if gacha.get('event',{}).get('active'):
        queue.append(event)
    elif queue:
        next_event=queue.pop(0);next_event['active']=True;next_event['createdAt']=time.time()
        gacha['event']=next_event
        queue.append(event)
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
        if event.get('type') == 'gacha' and not event.get('isTest') and not any(int(item.get('id') or 0)==event_id for item in gacha.get('history', [])):
            result=int(event.get('total') or 0)
            if event.get('winSign') == 'both':
                result= -abs(result) if event.get('choice') == 'minus' else abs(result)
            gacha.setdefault('history', []).insert(0, {'id':event_id,'senderName':str(event.get('senderName') or 'ゲスト')[:80],'patternName':str(event.get('patternName') or 'WINガチャ')[:60],'result':result,'continueCount':sum(1 for item in event.get('rounds',[]) if isinstance(item,dict) and item.get('continued') is True),'createdAt':max(0,float(event.get('createdAt') or time.time()))})
            gacha['history']=gacha['history'][:200]
        event['active']=False
        queue=gacha.setdefault('queue',[])
        if queue:
            next_event=queue.pop(0); next_event['active']=True; next_event['createdAt']=time.time()
            gacha['event']=next_event
        STATE.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
        return True

def skip_gacha_event(event_id):
    """Release a stuck active draw without applying it to WIN or history."""
    with STATE_LOCK:
        try:
            data=json.loads(STATE.read_text(encoding='utf-8'))
        except Exception:
            data=copy.deepcopy(DEFAULT)
        data,_=normalize_state(data)
        gacha=data['gacha'];event=gacha['event']
        queue=gacha.setdefault('queue',[])
        if event.get('active'):
            if int(event.get('id') or 0)!=event_id:
                return False
            event['active']=False
        elif not queue:
            return False
        if queue:
            next_event=queue.pop(0);next_event['active']=True;next_event['createdAt']=time.time()
            gacha['event']=next_event
        STATE.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
        return True

def choose_gacha_sign_in_state(data, choice):
    event=data['gacha']['event']
    if event.get('type')!='gacha' or event.get('winSign')!='both' or not event.get('choiceReady') or event.get('choice'):
        return False
    choice='minus' if choice=='minus' else 'plus'; amount=abs(int(event.get('total') or 0))
    delta=-amount if choice=='minus' else amount
    win=data['winCounter']
    if not event.get('isTest'):
        win['currentWin']=max(-999999,min(999999,win['currentWin']+delta))
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
        win=data['winCounter']
        if not event.get('isTest'):
            win['currentWin']=max(-999999,min(999999,win['currentWin']+delta))
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
        other_pattern=next((p for p in data['otherGacha']['patterns'] if p['enabled'] and p['giftName'] and normalize_gift_name(p['giftName'])==name),None)
        pachinko_pattern=next((p for p in data['pachinkoGacha']['patterns'] if p['enabled'] and p['giftName'] and normalize_gift_name(p['giftName'])==name),None)
        media_rule=next((r for r in data['giftMedia']['rules'] if r.get('enabled',True) and r['giftName'] and normalize_gift_name(r['giftName'])==name and (r.get('imageUrl') or r.get('videoUrl') or r.get('audioUrl'))),None)
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
        if other_pattern:
            run_other_gacha_draw(data,other_pattern,sender_name)
            matched=True
        if pachinko_pattern:
            run_pachinko_draw(data,pachinko_pattern,sender_name)
            matched=True
        if media_rule:
            queue_gift_media_event(data,media_rule,gift_name,sender_name,count)
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
        WM_HOTKEY = 0x0312
        WM_KEYDOWN, WM_SYSKEYDOWN = 0x0100, 0x0104
        WM_KEYUP, WM_SYSKEYUP = 0x0101, 0x0105
        KEY_FLAGS = 0x8000
        KEY_PRESSED = 0x0001
        MOD_NOREPEAT = 0x4000
        PM_REMOVE = 0x0001
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
        register_hot_key = user32.RegisterHotKey
        register_hot_key.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
        register_hot_key.restype = wintypes.BOOL
        unregister_hot_key = user32.UnregisterHotKey
        unregister_hot_key.argtypes = [wintypes.HWND, ctypes.c_int]
        unregister_hot_key.restype = wintypes.BOOL
        peek_message = user32.PeekMessageW
        peek_message.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT, wintypes.UINT]
        peek_message.restype = wintypes.BOOL
        get_module_handle = kernel32.GetModuleHandleW
        get_module_handle.argtypes = [wintypes.LPCWSTR]
        get_module_handle.restype = ctypes.c_void_p
        action_map = {}
        actions_lock = threading.Lock()
        action_queue = queue.Queue()
        pressed = set()
        last_triggered = {}
        trigger_lock = threading.Lock()
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
            pachinko=data.get('pachinkoGacha',{})
            for field,choice in (('shortcutChoicePlus','plus'),('shortcutChoiceMinus','minus')):
                binding=str(pachinko.get(field) or '').upper()
                if binding and binding not in desired: desired[binding]={'type':'pachinkoChoice','choice':choice}
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
        def trigger_action(binding, action):
            # The low-level hook and the polling fallback can see the same
            # physical key press. Keep one action per press while still
            # allowing a deliberate second press shortly afterwards.
            now = time.monotonic()
            with trigger_lock:
                if now - last_triggered.get(binding, 0) < .22:
                    return
                last_triggered[binding] = now
            with HOTKEY_STATUS_LOCK:
                HOTKEY_STATUS['lastInputAt'] = time.time()
            action_queue.put_nowait(action)
        def polling_worker():
            # Some full-screen games do not deliver low-level hook events to
            # a background app. GetAsyncKeyState provides a second path that
            # continues to work while GTA has focus.
            down = set()
            while True:
                try:
                    with actions_lock:
                        bindings = list(action_map.items())
                    mods = modifiers_down()
                    current = set()
                    for binding, action in bindings:
                        required_mods, key = binding
                        key_state = get_async(key)
                        if mods == required_mods and key_state & (KEY_FLAGS | KEY_PRESSED):
                            current.add(binding)
                            if binding not in down:
                                trigger_action(binding, action)
                    down = current
                    with HOTKEY_STATUS_LOCK:
                        HOTKEY_STATUS['pollingAlive'] = True
                except Exception as error:
                    print(f'Global shortcut polling error: {error}')
                time.sleep(.02)
        def registered_hotkey_worker():
            # RegisterHotKey is handled by Windows itself and is less likely to
            # be swallowed by a full-screen game. Hook and polling stay active
            # as fallbacks for combinations Windows refuses to register.
            registered = {}
            registered_bindings = set()
            msg = wintypes.MSG()
            peek_message(ctypes.byref(msg), None, 0, 0, PM_REMOVE)
            while True:
                try:
                    with actions_lock:
                        snapshot = dict(action_map)
                    wanted = set(snapshot)
                    if wanted != registered_bindings:
                        for hotkey_id in list(registered):
                            unregister_hot_key(None, hotkey_id)
                        registered.clear()
                        failures = 0
                        for hotkey_id, binding in enumerate(sorted(wanted), 1):
                            modifiers, key = binding
                            if register_hot_key(None, hotkey_id, modifiers | MOD_NOREPEAT, key):
                                registered[hotkey_id] = (binding, snapshot[binding])
                            else:
                                failures += 1
                        registered_bindings = wanted
                        with HOTKEY_STATUS_LOCK:
                            HOTKEY_STATUS['registered'] = len(registered)
                            HOTKEY_STATUS['registrationFailures'] = failures
                    else:
                        for hotkey_id, (binding, _) in list(registered.items()):
                            if binding in snapshot:
                                registered[hotkey_id] = (binding, snapshot[binding])
                    while peek_message(ctypes.byref(msg), None, WM_HOTKEY, WM_HOTKEY, PM_REMOVE):
                        item = registered.get(int(msg.wParam))
                        if item:
                            trigger_action(item[0], item[1])
                    with HOTKEY_STATUS_LOCK:
                        HOTKEY_STATUS['registeredMonitorAlive'] = True
                except Exception as error:
                    with HOTKEY_STATUS_LOCK:
                        HOTKEY_STATUS['registeredMonitorAlive'] = False
                    print(f'Windows registered shortcut error: {error}')
                time.sleep(.03)
        refresh_actions()
        threading.Thread(target=refresh_worker, daemon=True).start()
        threading.Thread(target=action_worker, daemon=True).start()
        threading.Thread(target=polling_worker, daemon=True).start()
        threading.Thread(target=registered_hotkey_worker, daemon=True).start()
        @HOOKPROC
        def keyboard_proc(n_code, w_param, l_param):
            if n_code >= 0:
                try:
                    key = ctypes.cast(l_param, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents.vkCode
                    if w_param in (WM_KEYUP, WM_SYSKEYUP):
                        pressed.discard(key)
                    elif w_param in (WM_KEYDOWN, WM_SYSKEYDOWN) and key not in pressed:
                        pressed.add(key)
                        binding = (modifiers_down(), key)
                        with actions_lock:
                            action = action_map.get(binding)
                        if action:
                            trigger_action(binding, action)
                except Exception as error:
                    print(f'Global shortcut error: {error}')
            return call_next(None, n_code, w_param, l_param)
        hook = user32.SetWindowsHookExW(WH_KEYBOARD_LL, keyboard_proc, get_module_handle(None), 0)
        if not hook:
            error = ctypes.get_last_error()
            with HOTKEY_STATUS_LOCK:
                HOTKEY_STATUS.update(active=True, message=f'ゲーム対応ショートカット監視中（システム登録＋直接監視／Windowsエラー {error}）')
            print(f'Global shortcut hook could not start (Windows error {error}); registered hotkeys and direct polling remain active.')
            return
        with HOTKEY_STATUS_LOCK:
            HOTKEY_STATUS.update(active=True, message='ゲーム対応グローバルショートカット監視中（三重監視）', hookAlive=True)
        print('Global keyboard shortcuts are active (registered hotkeys + hook + direct polling).')
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

def get_minecraft_watch_status():
    with MINECRAFT_WATCH_LOCK:
        status = dict(MINECRAFT_WATCH_STATUS)
    config = read_state().get('minecraftBridge', {})
    clean_path = clean_local_path(config.get('logPath'))
    path = Path(clean_path).expanduser() if clean_path else None
    exists = bool(path and path.is_file())
    status.update({'enabled': bool(config.get('enabled')), 'logPath': str(path or ''), 'fileExists': exists})
    if not config.get('enabled'):
        status.update({'status': 'stopped', 'message': 'ログ連携はオフです'})
    elif not path:
        status.update({'status': 'waiting', 'message': 'ログファイルの場所を入力してください'})
    elif not exists and status.get('status') != 'error':
        status.update({'status': 'waiting', 'message': 'ログファイルが見つかりません。logs/latest.log の場所を確認してください'})
    return status

def minecraft_log_watcher():
    """Tail the configured local server log and add one WIN per marker line.

    The first observation of a file starts at EOF, so old log entries never
    change the score. On rotation/truncation, the new file is read from its
    beginning so fresh events are not missed.
    """
    watched_path = None
    watched_marker = None
    file_id = None
    offset = 0
    carry = b''
    while True:
        try:
            config = read_state().get('minecraftBridge', {})
            enabled = bool(config.get('enabled'))
            path_text = clean_local_path(config.get('logPath'))
            marker = str(config.get('marker') or 'bedrock_win').strip()
            if not enabled or not path_text:
                watched_path = None; watched_marker = None; file_id = None; offset = 0; carry = b''
                with MINECRAFT_WATCH_LOCK:
                    MINECRAFT_WATCH_STATUS.update(status='stopped' if not enabled else 'waiting', message='ログ連携はオフです' if not enabled else 'ログファイルの場所を入力してください')
                time.sleep(1)
                continue
            path = Path(path_text).expanduser()
            if not path.is_file():
                with MINECRAFT_WATCH_LOCK:
                    MINECRAFT_WATCH_STATUS.update(status='waiting', message='ログファイルが見つかりません。logs/latest.log の場所を確認してください')
                time.sleep(1)
                continue
            stat = path.stat()
            current_id = (stat.st_dev, stat.st_ino)
            if path_text != watched_path or marker.casefold() != str(watched_marker or '').casefold():
                watched_path, watched_marker, file_id = path_text, marker, current_id
                offset, carry = stat.st_size, b''  # skip historical entries on activation/config changes
            elif current_id != file_id or stat.st_size < offset:
                file_id, offset, carry = current_id, 0, b''
            with path.open('rb') as logfile:
                logfile.seek(offset)
                chunk = logfile.read(1024 * 1024)
                offset = logfile.tell()
            with MINECRAFT_WATCH_LOCK:
                received = int(MINECRAFT_WATCH_STATUS.get('winsReceived', 0))
                suffix = f'（成功検知 {received} 回）' if received else ''
                MINECRAFT_WATCH_STATUS.update(status='watching', message='Minecraftログを監視中' + suffix, logPath=path_text)
            if chunk:
                parts = (carry + chunk).split(b'\n')
                carry = parts.pop() if parts else b''
                marker_folded = marker.casefold()
                matches = 0
                for line in parts:
                    try:
                        if marker_folded and marker_folded in line.decode('utf-8', errors='ignore').casefold():
                            matches += 1
                    except Exception:
                        continue
                for _ in range(matches):
                    with STATE_LOCK:
                        try:
                            raw = json.loads(STATE.read_text(encoding='utf-8'))
                        except Exception:
                            raw = copy.deepcopy(DEFAULT)
                        data, _ = normalize_state(raw)
                        win = data['winCounter']
                        win['currentWin'] = max(-999999, min(999999, win['currentWin'] + 1))
                        STATE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
                    with MINECRAFT_WATCH_LOCK:
                        MINECRAFT_WATCH_STATUS['lastEventAt'] = time.time()
                        MINECRAFT_WATCH_STATUS['winsReceived'] = int(MINECRAFT_WATCH_STATUS.get('winsReceived', 0)) + 1
                        MINECRAFT_WATCH_STATUS['message'] = f'成功検知 {MINECRAFT_WATCH_STATUS["winsReceived"]} 回'
            time.sleep(0.5)
        except Exception as error:
            with MINECRAFT_WATCH_LOCK:
                MINECRAFT_WATCH_STATUS.update(status='error', message='ログ監視エラー: ' + str(error)[:160])
            time.sleep(2)

def get_gta_watch_status():
    with GTA_WATCH_LOCK:
        status = dict(GTA_WATCH_STATUS)
    config = read_state().get('gtaBridge', {})
    clean_path = clean_local_path(config.get('logPath'))
    path = Path(clean_path).expanduser() if clean_path else None
    exists = bool(path and path.is_file())
    status.update({'enabled': bool(config.get('enabled')), 'logPath': str(path or ''), 'fileExists': exists,
                   'winAmount': max(1, safe_int(config.get('winAmount', 1), 1)),
                   'loseEnabled': config.get('loseEnabled', True) is not False,
                   'loseAmount': max(1, safe_int(config.get('loseAmount', 1), 1))})
    if not config.get('enabled'):
        status.update({'status': 'stopped', 'message': 'GTA連携はオフです'})
    elif not path:
        status.update({'status': 'waiting', 'message': 'GTAWebhook.log の場所を入力してください'})
    elif not exists and status.get('status') != 'error':
        status.update({'status': 'waiting', 'message': 'ログファイルが見つかりません。GTAVWebhook.log の場所を確認してください'})
    return status

def gta_log_watcher():
    """Tail GTAVWebhook.log and apply the configured WIN amount for each new marker line."""
    watched_path = None
    watched_marker = None
    file_id = None
    offset = 0
    carry = b''
    while True:
        try:
            config = read_state().get('gtaBridge', {})
            enabled = bool(config.get('enabled'))
            path_text = clean_local_path(config.get('logPath'))
            marker = str(config.get('marker') or 'Sent WebSocket message: {"type":"win"').strip()
            win_amount = max(1, min(999999, safe_int(config.get('winAmount', 1), 1)))
            lose_enabled = config.get('loseEnabled', True) is not False
            lose_marker = str(config.get('loseMarker') or 'Sent WebSocket message: {"type":"lose"').strip()
            lose_amount = max(1, min(999999, safe_int(config.get('loseAmount', 1), 1)))
            if not enabled or not path_text:
                watched_path = None; watched_marker = None; file_id = None; offset = 0; carry = b''
                with GTA_WATCH_LOCK:
                    GTA_WATCH_STATUS.update(status='stopped' if not enabled else 'waiting', message='GTA連携はオフです' if not enabled else 'GTAWebhook.log の場所を入力してください')
                time.sleep(1)
                continue
            path = Path(path_text).expanduser()
            if not path.is_file():
                with GTA_WATCH_LOCK:
                    GTA_WATCH_STATUS.update(status='waiting', message='ログファイルが見つかりません。GTAVWebhook.log の場所を確認してください')
                time.sleep(1)
                continue
            stat = path.stat()
            current_id = (stat.st_dev, stat.st_ino)
            marker_key = marker.casefold() + '\0' + lose_marker.casefold()
            if path_text != watched_path or marker_key != str(watched_marker or ''):
                watched_path, watched_marker, file_id = path_text, marker_key, current_id
                offset, carry = stat.st_size, b''  # ignore old events when first connecting or changing the marker
            elif current_id != file_id or stat.st_size < offset:
                file_id, offset, carry = current_id, 0, b''
            with path.open('rb') as logfile:
                logfile.seek(offset)
                chunk = logfile.read(1024 * 1024)
                offset = logfile.tell()
            with GTA_WATCH_LOCK:
                received = int(GTA_WATCH_STATUS.get('eventsReceived', 0))
                loss_text = f' / デス時 -{lose_amount} WIN' if lose_enabled else ''
                GTA_WATCH_STATUS.update(status='watching', message=f'GTAログ監視中（検知 {received} 回・WIN +{win_amount}{loss_text}）', logPath=path_text)
            if chunk:
                parts = (carry + chunk).split(b'\n')
                carry = parts.pop() if parts else b''
                marker_folded = marker.casefold()
                lose_marker_folded = lose_marker.casefold()
                events = []
                for line in parts:
                    line_folded = line.decode('utf-8', errors='ignore').casefold()
                    if marker_folded and marker_folded in line_folded:
                        events.append(win_amount)
                    elif lose_enabled and lose_marker_folded and lose_marker_folded in line_folded:
                        events.append(-lose_amount)
                for delta in events:
                    with STATE_LOCK:
                        try:
                            raw = json.loads(STATE.read_text(encoding='utf-8'))
                        except Exception:
                            raw = copy.deepcopy(DEFAULT)
                        data, _ = normalize_state(raw)
                        win = data['winCounter']
                        win['currentWin'] = max(-999999, min(999999, win['currentWin'] + delta))
                        STATE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
                    with GTA_WATCH_LOCK:
                        GTA_WATCH_STATUS['lastEventAt'] = time.time()
                        GTA_WATCH_STATUS['eventsReceived'] = int(GTA_WATCH_STATUS.get('eventsReceived', 0)) + 1
                        event_text = f'+{win_amount} WIN' if delta > 0 else f'-{lose_amount} WIN'
                        GTA_WATCH_STATUS['message'] = f'GTA {"WIN" if delta > 0 else "デス"}検知 {GTA_WATCH_STATUS["eventsReceived"]} 回（{event_text}）'
            time.sleep(0.5)
        except Exception as error:
            with GTA_WATCH_LOCK:
                GTA_WATCH_STATUS.update(status='error', message='GTAログ監視エラー: ' + str(error)[:160])
            time.sleep(2)

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
        if self.path in ('/api/overlay/win', '/api/overlay/gacha', '/api/overlay/pachinko'):
            kind = self.path.rsplit('/', 1)[-1]
            body = json.dumps(read_overlay_state(kind), ensure_ascii=False, separators=(',', ':')).encode('utf-8')
            self.send_response(200); self.send_header('Content-Type', 'application/json; charset=utf-8'); self.send_header('Cache-Control', 'no-store'); self.send_header('Content-Length', str(len(body))); self.end_headers(); self.wfile.write(body); return
        if self.path == '/api/network':
            body = json.dumps({'host': LAN_IP, 'baseUrl': f'http://{LAN_IP}:8765/', 'localBaseUrl': 'http://127.0.0.1:8765/', 'appVersion': APP_VERSION}, ensure_ascii=False).encode('utf-8')
            self.send_response(200); self.send_header('Content-Type','application/json; charset=utf-8'); self.send_header('Cache-Control','no-store'); self.send_header('Content-Length',str(len(body))); self.end_headers(); self.wfile.write(body); return
        if self.path == '/api/state':
            body = json.dumps(read_state(), ensure_ascii=False).encode('utf-8')
            self.send_response(200); self.send_header('Content-Type','application/json; charset=utf-8'); self.send_header('Cache-Control','no-store'); self.send_header('Content-Length',str(len(body))); self.end_headers(); self.wfile.write(body); return
        if self.path == '/api/tiktok/status':
            body = json.dumps(get_tiktok_status(), ensure_ascii=False).encode('utf-8')
            self.send_response(200); self.send_header('Content-Type','application/json; charset=utf-8'); self.send_header('Cache-Control','no-store'); self.send_header('Content-Length',str(len(body))); self.end_headers(); self.wfile.write(body); return
        if self.path == '/api/hotkeys/status':
            body = json.dumps(get_hotkey_status(), ensure_ascii=False).encode('utf-8')
            self.send_response(200); self.send_header('Content-Type','application/json; charset=utf-8'); self.send_header('Cache-Control','no-store'); self.send_header('Content-Length',str(len(body))); self.end_headers(); self.wfile.write(body); return
        if self.path == '/api/minecraft/status':
            body = json.dumps(get_minecraft_watch_status(), ensure_ascii=False).encode('utf-8')
            self.send_response(200); self.send_header('Content-Type','application/json; charset=utf-8'); self.send_header('Cache-Control','no-store'); self.send_header('Content-Length',str(len(body))); self.end_headers(); self.wfile.write(body); return
        if self.path == '/api/gta/status':
            body = json.dumps(get_gta_watch_status(), ensure_ascii=False).encode('utf-8')
            self.send_response(200); self.send_header('Content-Type','application/json; charset=utf-8'); self.send_header('Cache-Control','no-store'); self.send_header('Content-Length',str(len(body))); self.end_headers(); self.wfile.write(body); return
        if self.path == '/api/tiktok/gifts':
            with TIKTOK_GIFT_CATALOG_LOCK:
                gifts = copy.deepcopy(TIKTOK_GIFT_CATALOG)
            status = get_tiktok_status()
            body = json.dumps({'gifts': gifts, 'connected': status.get('status') == 'connected', 'enabled': status.get('enabled', False)}, ensure_ascii=False).encode('utf-8')
            self.send_response(200); self.send_header('Content-Type','application/json; charset=utf-8'); self.send_header('Cache-Control','no-store'); self.send_header('Content-Length',str(len(body))); self.end_headers(); self.wfile.write(body); return
        return super().do_GET()
    def do_POST(self):
        if self.path not in ('/api/state', '/api/giftwall/reset-display', '/api/giftwall/restore-display', '/api/tiktok/connect', '/api/tiktok/toggle', '/api/gift/test', '/api/smoking-audio', '/api/win-image', '/api/win-sound', '/api/gacha-audio', '/api/gacha-result-audio', '/api/gacha-animation', '/api/gacha-outcome-media', '/api/gacha-media-clear', '/api/gacha-end-audio', '/api/gacha-end-animation', '/api/gacha/test', '/api/gacha/apply-round', '/api/gacha/choose-sign', '/api/gacha/choice-ready', '/api/gacha/complete', '/api/gacha/skip-stuck', '/api/text-role-image', '/api/pachinko/test', '/api/pachinko/preview', '/api/pachinko/skip', '/api/pachinko/complete', '/api/pachinko/choice-ready', '/api/pachinko/choose-sign', '/api/pachinko/media', '/api/pachinko/digit-image', '/api/smoking-gacha-animation', '/api/smoking-gacha-audio', '/api/smoking-gacha-result-audio', '/api/smoking-gacha/test', '/api/smoking-gacha/choice-ready', '/api/smoking-gacha/choose-sign', '/api/smoking-gacha/complete', '/api/other-gacha/test', '/api/other-gacha/complete', '/api/other-gacha-media', '/api/gift-media/upload', '/api/gift-media/test', '/api/gift-media/complete'):
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
                    if isinstance(data.get('otherGacha'),dict):
                        live_other=current.get('otherGacha',{})
                        data['otherGacha']['event']=copy.deepcopy(live_other.get('event',{}))
                        data['otherGacha']['queue']=copy.deepcopy(live_other.get('queue',[]))
                    if isinstance(data.get('pachinkoGacha'),dict):
                        live_pachinko=current.get('pachinkoGacha',{})
                        data['pachinkoGacha']['event']=copy.deepcopy(live_pachinko.get('event',{}))
                        data['pachinkoGacha']['queue']=copy.deepcopy(live_pachinko.get('queue',[]))
                        data['pachinkoGacha']['history']=copy.deepcopy(live_pachinko.get('history',[]))
                    if isinstance(data.get('giftMedia'),dict):
                        live_media=current.get('giftMedia',{})
                        data['giftMedia']['event']=copy.deepcopy(live_media.get('event',{}))
                        data['giftMedia']['queue']=copy.deepcopy(live_media.get('queue',[]))
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
            elif self.path == '/api/win-sound':
                if self.client_address[0] not in ('127.0.0.1','::1'): self.send_error(403); return
                kind=str(data.get('kind') or '')
                if kind not in ('add','sub','goal'): raise ValueError('音源の種類を確認してください')
                state=read_state();url_key=kind+'SoundUrl';name_key=kind+'SoundName'
                if bool(data.get('clear')):
                    state['winCounter'][url_key]='';state['winCounter'][name_key]=''
                else:
                    match=re.fullmatch(r'data:audio/(wav|x-wav|mpeg|mp3|ogg|mp4|m4a|aac|webm);base64,([A-Za-z0-9+/=]+)',str(data.get('dataUrl') or ''))
                    if not match: raise ValueError('MP3、WAV、OGG、M4A、AAC、WebM形式の音源を選択してください')
                    raw=base64.b64decode(match.group(2),validate=True)
                    if not raw or len(raw)>15*1024*1024: raise ValueError('音源は15MB以下にしてください')
                    ext={'mpeg':'mp3','mp4':'m4a','m4a':'m4a','x-wav':'wav'}.get(match.group(1),match.group(1));filename=f'win_counter_{kind}.{ext}';(ROOT/filename).write_bytes(raw)
                    state['winCounter'][url_key]='/'+filename+'?v='+str(safe_int(time.time()*1000));state['winCounter'][name_key]=Path(str(data.get('name') or filename)).name[:120];state['winCounter']['soundEnabled']=True
                write_state(state);result={'ok':True,'winCounter':read_state()['winCounter']}
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
                stage_prefixes = {'spinEffect':'gacha_spin_effect_','secondary':'gacha_secondary_audio_','startCue':'gacha_start_cue_','start':'gacha_start_audio_','hit':'gacha_hit_audio_','miss':'gacha_miss_audio_','upperEntry':'gacha_upper_entry_audio_','upperAT':'gacha_upper_audio_','normalContinue':'gacha_continue_audio_','upperContinue':'gacha_upper_continue_audio_','preAlert1':'gacha_prealert1_audio_','preAlert2':'gacha_prealert2_audio_','preAlert3':'gacha_prealert3_audio_'}
                prefix = stage_prefixes.get(stage, 'gacha_audio_')
                filename = (prefix + safe_id if safe_id else prefix.rstrip('_')) + '.' + ext
                (ROOT / filename).write_bytes(raw)
                state = read_state()
                pattern = next((item for item in state['gacha']['patterns'] if item['id'] == pattern_id), None) if pattern_id else None
                target = pattern if pattern is not None else state['gacha']
                alert_match = re.fullmatch(r'preAlert([123])', stage)
                if alert_match and pattern is not None:
                    alert_index = int(alert_match.group(1)) - 1
                    while len(pattern.setdefault('preAlerts', [])) < 3: pattern['preAlerts'].append({})
                    target = pattern['preAlerts'][alert_index]
                url_key = 'audioUrl' if alert_match and pattern is not None else {'spinEffect':'spinSoundUrl','secondary':'secondaryAudioUrl','startCue':'startDefaultSoundUrl','start':'startAudioUrl','hit':'hitAudioUrl','miss':'missAudioUrl','upperEntry':'upperEntryAudioUrl','upperAT':'upperAtAudioUrl','normalContinue':'continueAudioUrl','upperContinue':'upperContinueAudioUrl'}.get(stage, 'audioUrl')
                name_key = 'audioName' if alert_match and pattern is not None else {'spinEffect':'spinSoundName','secondary':'secondaryAudioName','startCue':'startDefaultSoundName','start':'startAudioName','hit':'hitAudioName','miss':'missAudioName','upperEntry':'upperEntryAudioName','upperAT':'upperAtAudioName','normalContinue':'continueAudioName','upperContinue':'upperContinueAudioName'}.get(stage, 'audioName')
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
                stage_prefixes = {'start':'gacha_start_animation_','hit':'gacha_hit_animation_','miss':'gacha_miss_animation_','upperEntry':'gacha_upper_entry_animation_','upperAT':'gacha_upper_animation_','normalContinue':'gacha_continue_animation_','upperContinue':'gacha_upper_continue_animation_','preAlert':'gacha_prealert_animation_','preAlert1':'gacha_prealert1_animation_','preAlert2':'gacha_prealert2_animation_','preAlert3':'gacha_prealert3_animation_'}
                prefix = stage_prefixes.get(stage, 'gacha_animation_')
                filename=(prefix + safe_id if safe_id else prefix.rstrip('_'))+'.'+ext
                (ROOT/filename).write_bytes(raw)
                state=read_state();pattern=next((item for item in state['gacha']['patterns'] if item['id']==pattern_id),None) if pattern_id else None;target=pattern if pattern is not None else state['gacha'];url_key={'start':'startAnimationUrl','hit':'hitAnimationUrl','miss':'missAnimationUrl','upperEntry':'upperEntryAnimationUrl','upperAT':'upperAtAnimationUrl','normalContinue':'continueAnimationUrl','upperContinue':'upperContinueAnimationUrl','preAlert':'preAlertAnimationUrl'}.get(stage,'animationUrl');name_key={'start':'startAnimationName','hit':'hitAnimationName','miss':'missAnimationName','upperEntry':'upperEntryAnimationName','upperAT':'upperAtAnimationName','normalContinue':'continueAnimationName','upperContinue':'upperContinueAnimationName','preAlert':'preAlertAnimationName'}.get(stage,'animationName')
                alert_match=re.fullmatch(r'preAlert([123])',stage)
                if alert_match and pattern is not None:
                    alert_index=int(alert_match.group(1))-1
                    while len(pattern.setdefault('preAlerts',[]))<3: pattern['preAlerts'].append({})
                    alert=pattern['preAlerts'][alert_index];url_key='animationUrl';name_key='animationName';target=alert
                target[url_key]='/'+filename+'?v='+str(safe_int(time.time()*1000));target[name_key]=Path(str(data.get('name') or filename)).name[:120];write_state(state)
                result={'ok':True,'gacha':read_state()['gacha']}
            elif self.path == '/api/gacha-outcome-media':
                if self.client_address[0] not in ('127.0.0.1','::1'): self.send_error(403); return
                state=read_state();pattern=next((x for x in state['gacha']['patterns'] if x['id']==str(data.get('patternId') or '')),None)
                if not pattern: raise ValueError('保存先のWINガチャが見つかりません')
                upper=bool(data.get('upper'));items=pattern.get('upperOutcomes' if upper else 'outcomes') or [];index=safe_int(data.get('index'),-1);role=str(data.get('role') or '')
                if index<0 or index>=len(items) or role not in ('spin','result'): raise ValueError('数字素材の保存先を確認してください')
                item=items[index];url_key=role+'ImageUrl';name_key=role+'ImageName'
                if bool(data.get('clear')): item[url_key]='';item[name_key]=''
                else:
                    match=re.fullmatch(r'data:image/(gif|png|jpeg|webp);base64,([A-Za-z0-9+/=]+)',str(data.get('dataUrl') or ''))
                    if not match: raise ValueError('PNG、JPG、WebP、GIF形式の画像を選択してください')
                    raw=base64.b64decode(match.group(2),validate=True)
                    if not raw or len(raw)>15*1024*1024: raise ValueError('数字画像は15MB以下にしてください')
                    ext={'jpeg':'jpg'}.get(match.group(1),match.group(1));safe_id=re.sub(r'[^A-Za-z0-9_-]','_',pattern['id'])[:60];filename=f'gacha_{"upper_" if upper else ""}{role}_number_{safe_id}_{index}.{ext}';(ROOT/filename).write_bytes(raw)
                    item[url_key]='/'+filename+'?v='+str(safe_int(time.time()*1000));item[name_key]=Path(str(data.get('name') or filename)).name[:120]
                write_state(state);result={'ok':True,'gacha':read_state()['gacha']}
            elif self.path == '/api/gacha/test':
                if self.client_address[0] not in ('127.0.0.1', '::1'):
                    self.send_error(403); return
                state=read_state();pattern=next((x for x in state['gacha']['patterns'] if x['id']==str(data.get('patternId') or '')),None)
                if not pattern:
                    raise ValueError('テストするパターンを選べません')
                current_event=state['gacha'].get('event',{})
                was_active=bool(current_event.get('active'))
                # Tests use the same FIFO queue as real gift-triggered spins. Never
                # replace an active test: that can make consecutive tests overlap.
                run_gacha_draw(state,pattern,'テスト','テスト',is_test=True)
                queue_position=len(state['gacha'].get('queue',[])) if was_active else 0
                write_state(state);result={'ok':True,'queued':was_active,'queuePosition':queue_position}
            elif self.path == '/api/text-role-image':
                if self.client_address[0] not in ('127.0.0.1','::1'): self.send_error(403); return
                scope=str(data.get('scope') or '');pattern_id=str(data.get('patternId') or '');role=str(data.get('role') or '')
                allowed={'gacha':('pattern','sender','start','startQuestion','spinState','spinStatus','spinNumber','resultState','continueState','upperEntryState','resultWin','roundTotal','setCount','choiceResult','choice','endResult','endState','finalTotal'),'pachinko':('pattern','sender','spinState','spinNumber','progress','resultState','resultNumber','reachState','hitState','missState','czState','timeShortState','atState','upperState','luckyTriggerState','continueState','endState','resultWin','setCount','total')}
                if scope not in allowed or role not in allowed[scope]: raise ValueError('文字画像の設定先を確認してください')
                state=read_state();collection=state['gacha']['patterns'] if scope=='gacha' else state['pachinkoGacha']['patterns'];pattern=next((x for x in collection if x['id']==pattern_id),None)
                if not pattern: raise ValueError('設定先のガチャパターンが見つかりません')
                target=pattern.setdefault('textRoles',{}).setdefault(role,{})
                if bool(data.get('clear')): target['imageUrl']='';target['imageName']='';target['mode']='text'
                else:
                    match=re.fullmatch(r'data:image/(gif|png|jpeg|webp);base64,([A-Za-z0-9+/=]+)',str(data.get('dataUrl') or ''))
                    if not match: raise ValueError('GIF、PNG、JPG、WebP形式の画像を選択してください')
                    raw=base64.b64decode(match.group(2),validate=True)
                    if not raw or len(raw)>15*1024*1024: raise ValueError('文字画像は15MB以下にしてください')
                    ext={'jpeg':'jpg'}.get(match.group(1),match.group(1));safe_id=re.sub(r'[^A-Za-z0-9_-]','_',pattern_id)[:60];filename=f'{scope}_text_{safe_id}_{role}.{ext}';(ROOT/filename).write_bytes(raw);target['imageUrl']='/'+filename+'?v='+str(safe_int(time.time()*1000));target['imageName']=Path(str(data.get('name') or filename)).name[:120];target['mode']='image'
                write_state(state);fresh=read_state();result={'ok':True,'gacha':fresh['gacha'],'pachinkoGacha':fresh['pachinkoGacha']}
            elif self.path == '/api/pachinko/test':
                if self.client_address[0] not in ('127.0.0.1','::1'): self.send_error(403); return
                state=read_state();pattern=next((x for x in state['pachinkoGacha']['patterns'] if x['id']==str(data.get('patternId') or '')),None)
                if not pattern: raise ValueError('テストするパチンコガチャが見つかりません')
                if not pattern.get('enabled',True): raise ValueError('停止中のパターンです')
                requested_alert=data.get('preAlertIndex')
                test_alert_index=None if requested_alert is None else safe_int(requested_alert,-1)
                if test_alert_index is not None and not 0<=test_alert_index<3: raise ValueError('先バレパターンを確認してください')
                run_pachinko_draw(state,pattern,'テスト',is_test=True,test_pre_alert_index=test_alert_index);write_state(state);result={'ok':True,'pachinkoGacha':read_state()['pachinkoGacha']}
            elif self.path == '/api/pachinko/preview':
                if self.client_address[0] not in ('127.0.0.1','::1'): self.send_error(403); return
                pattern=data.get('pattern')
                if not isinstance(pattern,dict): raise ValueError('プレビューするパターンを確認してください')
                result=build_pachinko_preview(pattern)
            elif self.path == '/api/pachinko/skip':
                if self.client_address[0] not in ('127.0.0.1','::1'): self.send_error(403); return
                result={'ok':skip_pachinko_event(safe_int(data.get('eventId'),0),str(data.get('scope') or 'current'),data.get('createdAt'),data.get('events'))}
                result['pachinkoGacha']=read_state()['pachinkoGacha']
            elif self.path == '/api/pachinko/complete':
                result={'ok':complete_pachinko_event(safe_int(data.get('eventId') or 0))}
            elif self.path in ('/api/pachinko/choice-ready','/api/pachinko/choose-sign'):
                choice=None if self.path.endswith('/choice-ready') else str(data.get('choice') or '')
                result={'ok':pachinko_choice_action(safe_int(data.get('eventId'),0),choice,data.get('createdAt'))}
                result['pachinkoGacha']=read_state()['pachinkoGacha']
            elif self.path == '/api/pachinko/digit-image':
                if self.client_address[0] not in ('127.0.0.1','::1'): self.send_error(403); return
                state=read_state();pattern=next((x for x in state['pachinkoGacha']['patterns'] if x['id']==str(data.get('patternId') or '')),None)
                if not pattern: raise ValueError('保存先のパチンコガチャが見つかりません')
                digit=safe_int(data.get('digit'),-1)
                if digit<0 or digit>9: raise ValueError('数字画像の対象を確認してください')
                pattern.setdefault('digitSettings',[{'text':str(i),'fontFamily':'global','color':'#ffffff','size':130,'imageUrl':'','imageName':'','imageSize':130} for i in range(10)])
                target_digit=pattern['digitSettings'][digit]
                if bool(data.get('clear')): target_digit['imageUrl']='';target_digit['imageName']=''
                else:
                    match=re.fullmatch(r'data:image/(png|jpeg|webp|gif);base64,([A-Za-z0-9+/=]+)',str(data.get('dataUrl') or ''))
                    if not match: raise ValueError('PNG、JPG、WebP、GIF形式にしてください')
                    raw=base64.b64decode(match.group(2),validate=True)
                    if not raw or len(raw)>15*1024*1024: raise ValueError('数字画像は15MB以下にしてください')
                    ext={'jpeg':'jpg'}.get(match.group(1),match.group(1));safe_id=re.sub(r'[^A-Za-z0-9_-]','_',pattern['id'])[:60];filename=f'pachinko_digit{digit}_{safe_id}.{ext}';(ROOT/filename).write_bytes(raw);target_digit['imageUrl']='/'+filename+'?v='+str(safe_int(time.time()*1000));target_digit['imageName']=Path(str(data.get('name') or filename)).name[:120]
                write_state(state);result={'ok':True,'pachinkoGacha':read_state()['pachinkoGacha']}
            elif self.path == '/api/pachinko/media':
                if self.client_address[0] not in ('127.0.0.1','::1'): self.send_error(403); return
                state=read_state();pattern=next((x for x in state['pachinkoGacha']['patterns'] if x['id']==str(data.get('patternId') or '')),None)
                if not pattern: raise ValueError('保存先のパチンコガチャが見つかりません')
                stage=str(data.get('stage') or '');kind=str(data.get('kind') or '')
                if stage not in ('spin','reach','cz','hit','at','upper','lt','end','stop','spinBeep','preAlert1','preAlert2','preAlert3')+pachinko_boundary_stages() or kind not in ('animation','audio'): raise ValueError('演出の種類を確認してください')
                url_key=stage+('AnimationUrl' if kind=='animation' else 'AudioUrl');name_key=stage+('AnimationName' if kind=='animation' else 'AudioName')
                if bool(data.get('clear')): pattern[url_key]='';pattern[name_key]=''
                elif kind=='animation':
                    match=re.fullmatch(r'data:(image/(gif|png|jpeg|webp)|video/(mp4|webm));base64,([A-Za-z0-9+/=]+)',str(data.get('dataUrl') or ''))
                    if not match: raise ValueError('GIF、PNG、JPG、WebP、MP4、WebM形式にしてください')
                    raw=base64.b64decode(match.group(4),validate=True)
                    if not raw or len(raw)>30*1024*1024: raise ValueError('演出素材は30MB以下にしてください')
                    ext={'jpeg':'jpg'}.get(match.group(2) or match.group(3),match.group(2) or match.group(3));safe_id=re.sub(r'[^A-Za-z0-9_-]','_',pattern['id'])[:60];filename=f'pachinko_{stage}_{safe_id}.{ext}';(ROOT/filename).write_bytes(raw);pattern[url_key]='/'+filename+'?v='+str(safe_int(time.time()*1000));pattern[name_key]=Path(str(data.get('name') or filename)).name[:120]
                else:
                    match=re.fullmatch(r'data:audio/(wav|x-wav|mpeg|mp3|ogg|mp4|m4a|aac|webm);base64,([A-Za-z0-9+/=]+)',str(data.get('dataUrl') or ''))
                    if not match: raise ValueError('対応する音源形式を選択してください')
                    raw=base64.b64decode(match.group(2),validate=True)
                    if not raw or len(raw)>15*1024*1024: raise ValueError('音源は15MB以下にしてください')
                    ext={'mpeg':'mp3','mp4':'m4a','m4a':'m4a','x-wav':'wav'}.get(match.group(1),match.group(1));safe_id=re.sub(r'[^A-Za-z0-9_-]','_',pattern['id'])[:60];filename=f'pachinko_{stage}_audio_{safe_id}.{ext}';(ROOT/filename).write_bytes(raw);pattern[url_key]='/'+filename+'?v='+str(safe_int(time.time()*1000));pattern[name_key]=Path(str(data.get('name') or filename)).name[:120]
                write_state(state);result={'ok':True,'pachinkoGacha':read_state()['pachinkoGacha']}
            elif self.path == '/api/gift-media/upload':
                if self.client_address[0] not in ('127.0.0.1','::1'): self.send_error(403); return
                state=read_state();rule=next((x for x in state['giftMedia']['rules'] if x['id']==str(data.get('ruleId') or '')),None)
                if not rule: raise ValueError('保存先のギフトパターンが見つかりません')
                kind=str(data.get('kind') or '')
                if kind in ('image','video'):
                    match=re.fullmatch(r'data:(image/(gif|png|jpeg|webp)|video/(mp4|webm));base64,([A-Za-z0-9+/=]+)',str(data.get('dataUrl') or ''))
                    if not match: raise ValueError('GIF、PNG、JPG、WebP、MP4、WebM形式にしてください')
                    mime=match.group(1)
                    if (kind=='image' and not mime.startswith('image/')) or (kind=='video' and not mime.startswith('video/')): raise ValueError('選んだ素材の種類が設定欄と異なります')
                    raw=base64.b64decode(match.group(4),validate=True)
                    if not raw or len(raw)>30*1024*1024: raise ValueError('画像・動画は30MB以下にしてください')
                    ext={'jpeg':'jpg'}.get(match.group(2) or match.group(3),match.group(2) or match.group(3))
                elif kind=='audio':
                    match=re.fullmatch(r'data:audio/(wav|x-wav|mpeg|mp3|ogg|mp4|m4a|aac|webm);base64,([A-Za-z0-9+/=]+)',str(data.get('dataUrl') or ''))
                    if not match: raise ValueError('MP3、WAV、OGG、M4A、AAC、WebM形式の音源を選択してください')
                    raw=base64.b64decode(match.group(2),validate=True)
                    if not raw or len(raw)>15*1024*1024: raise ValueError('音源は15MB以下にしてください')
                    ext={'mpeg':'mp3','mp4':'m4a','m4a':'m4a','x-wav':'wav'}.get(match.group(1),match.group(1))
                else: raise ValueError('素材の種類を確認してください')
                safe_id=re.sub(r'[^A-Za-z0-9_-]','_',rule['id'])[:80];filename=f'gift_media_{safe_id}_{kind}.{ext}';(ROOT/filename).write_bytes(raw)
                rule[kind+'Url']='/'+filename+'?v='+str(safe_int(time.time()*1000));rule[kind+'Name']=Path(str(data.get('name') or filename)).name[:120]
                write_state(state);result={'ok':True,'giftMedia':read_state()['giftMedia']}
            elif self.path == '/api/gift-media/test':
                if self.client_address[0] not in ('127.0.0.1','::1'): self.send_error(403); return
                state=read_state();rule=next((x for x in state['giftMedia']['rules'] if x['id']==str(data.get('ruleId') or '')),None)
                if not rule: raise ValueError('テストするギフトパターンを選べません')
                if not rule.get('enabled',True): raise ValueError('停止中のパターンはテストできません。再開してください')
                if not (rule.get('imageUrl') or rule.get('videoUrl') or rule.get('audioUrl')): raise ValueError('先に画像・動画・音源のいずれかを登録してください')
                queue_gift_media_event(state,rule,rule.get('giftName') or 'テストギフト','テスト',1);write_state(state);result={'ok':True}
            elif self.path == '/api/gift-media/complete':
                result={'ok':complete_gift_media_event(safe_int(data.get('eventId') or 0))}
            elif self.path == '/api/other-gacha/test':
                if self.client_address[0] not in ('127.0.0.1','::1'): self.send_error(403); return
                state=read_state();pattern=next((x for x in state['otherGacha']['patterns'] if x['id']==str(data.get('patternId') or '')),None)
                if not pattern: raise ValueError('テストするその他ガチャを選べません')
                if not pattern['enabled']: raise ValueError('停止中のパターンはテストできません。再開してからお試しください')
                if not run_other_gacha_draw(state,pattern,'テスト'): raise ValueError('結果を1件以上登録してください')
                write_state(state);result={'ok':True}
            elif self.path == '/api/other-gacha-media':
                if self.client_address[0] not in ('127.0.0.1','::1'): self.send_error(403); return
                state=read_state();pattern=next((x for x in state['otherGacha']['patterns'] if x['id']==str(data.get('patternId') or '')),None)
                if not pattern: raise ValueError('保存先のその他ガチャパターンが見つかりません')
                kind=str(data.get('type') or '')
                if kind=='animation':
                    match=re.fullmatch(r'data:(image/(gif|png|jpeg|webp)|video/(mp4|webm));base64,([A-Za-z0-9+/=]+)',str(data.get('dataUrl') or ''))
                    if not match: raise ValueError('GIF、PNG、JPG、WebP、MP4、WebM形式にしてください')
                    raw=base64.b64decode(match.group(4),validate=True)
                    if not raw or len(raw)>30*1024*1024: raise ValueError('演出素材は30MB以下にしてください')
                    ext={'jpeg':'jpg'}.get(match.group(2) or match.group(3),match.group(2) or match.group(3))
                elif kind in ('audio','resultAudio'):
                    match=re.fullmatch(r'data:audio/(wav|x-wav|mpeg|mp3|ogg|mp4|m4a|aac|webm);base64,([A-Za-z0-9+/=]+)',str(data.get('dataUrl') or ''))
                    if not match: raise ValueError('対応する音源形式を選択してください')
                    raw=base64.b64decode(match.group(2),validate=True)
                    if not raw or len(raw)>15*1024*1024: raise ValueError('音源は15MB以下にしてください')
                    ext={'mpeg':'mp3','mp4':'m4a','m4a':'m4a','x-wav':'wav'}.get(match.group(1),match.group(1))
                else: raise ValueError('素材の種類を確認してください')
                safe_id=re.sub(r'[^A-Za-z0-9_-]','_',pattern['id'])[:80];filename=f'other_gacha_{kind}_{safe_id}.{ext}';(ROOT/filename).write_bytes(raw)
                pattern[kind+'Url']='/'+filename+'?v='+str(safe_int(time.time()*1000));pattern[kind+'Name']=Path(str(data.get('name') or filename)).name[:120]
                sync_active_profile_other_gacha(state)
                write_state(state);result={'ok':True,'otherGacha':read_state()['otherGacha']}
            elif self.path == '/api/other-gacha/complete':
                result={'ok':complete_other_gacha_event(int(data.get('eventId') or 0))}
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
            elif self.path == '/api/gacha/skip-stuck':
                if self.client_address[0] not in ('127.0.0.1','::1'):
                    self.send_error(403); return
                result={'ok':skip_gacha_event(int(data.get('eventId') or 0))}
            elif self.path == '/api/gacha-media-clear':
                if self.client_address[0] not in ('127.0.0.1','::1'):
                    self.send_error(403); return
                pattern_id=str(data.get('patternId') or '')
                stage=str(data.get('stage') or '')
                kind=str(data.get('kind') or '')
                media_keys={
                    ('start','animation'):('startAnimationUrl','startAnimationName'),
                    ('start','audio'):('startAudioUrl','startAudioName'),
                    ('startCue','audio'):('startDefaultSoundUrl','startDefaultSoundName'),
                    ('hit','animation'):('hitAnimationUrl','hitAnimationName'),
                    ('hit','audio'):('hitAudioUrl','hitAudioName'),
                    ('miss','animation'):('missAnimationUrl','missAnimationName'),
                    ('miss','audio'):('missAudioUrl','missAudioName'),
                }
                keys=media_keys.get((stage,kind))
                if not keys:
                    raise ValueError('解除する演出素材を特定できません')
                state=read_state()
                pattern=next((item for item in state['gacha']['patterns'] if item['id']==pattern_id),None)
                if pattern is None:
                    raise ValueError('解除するガチャパターンが見つかりません')
                pattern[keys[0]]='';pattern[keys[1]]=''
                write_state(state)
                result={'ok':True,'gacha':read_state()['gacha']}
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
    # Several sources reconnect together when LIVE Studio adds or restores a scene.
    request_queue_size = 64
    # Allow the app to be reopened immediately after it was closed.  Windows
    # can otherwise keep port 8765 reserved briefly and make the browser show
    # an error page even though the desktop window opened normally.
    allow_reuse_address = True

def run_desktop_app(server):
    import tkinter as tk
    from tkinter import messagebox

    control_url = f'http://127.0.0.1:8765/control.html?build={APP_VERSION}'
    overlay_url = f'http://{LAN_IP}:8765/overlay.html?build=6625'
    window = tk.Tk()
    window.title('Live Overlay Studio')
    try:
        window.iconbitmap(str(SOURCE_ROOT / 'app_icon.ico'))
    except Exception:
        pass
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
    global MINECRAFT_WATCH_THREAD, GTA_WATCH_THREAD
    if MINECRAFT_WATCH_THREAD is None or not MINECRAFT_WATCH_THREAD.is_alive():
        MINECRAFT_WATCH_THREAD = threading.Thread(target=minecraft_log_watcher, daemon=True)
        MINECRAFT_WATCH_THREAD.start()
    if GTA_WATCH_THREAD is None or not GTA_WATCH_THREAD.is_alive():
        GTA_WATCH_THREAD = threading.Thread(target=gta_log_watcher, daemon=True)
        GTA_WATCH_THREAD.start()
    try:
        # LIVE Studio may isolate browser sources from the Windows loopback
        # interface. Listen on the PC network interface as well so its browser
        # source can reach the same local overlay through the LAN IPv4 address.
        server = LocalThreadingHTTPServer(('0.0.0.0', 8765), Handler)
    except OSError:
        # A second launch should focus the already running app instead of failing.
        webbrowser.open(f'http://127.0.0.1:8765/control.html?build={APP_VERSION}')
        return
    if FROZEN_APP and os.name == 'nt':
        run_desktop_app(server)
        return
    if os.name == 'nt':
        threading.Timer(1.5, lambda: webbrowser.open(f'http://127.0.0.1:8765/control.html?build={APP_VERSION}')).start()
    print(f'Live Overlay Studio v{APP_VERSION} running: http://127.0.0.1:8765/control.html?build={APP_VERSION}')
    print(f'Overlay source: http://{LAN_IP}:8765/overlay.html?build=6625')
    server.serve_forever()

if __name__ == '__main__':
    main()
