import copy
import random
import time


EMPTY_EVENT = {
    'id': 0, 'type': '', 'active': False, 'patternId': '', 'patternName': '',
    'senderName': '', 'avatarUrl': '', 'giftName': '', 'spins': [],
    'appliedSpins': 0, 'total': 0, 'choice': '', 'choiceReady': False,
    'winApplied': False, 'createdAt': 0,
}


def _int(value, default=0, low=None, high=None):
    try:
        result = int(float(value))
    except (TypeError, ValueError):
        result = default
    if low is not None:
        result = max(low, result)
    if high is not None:
        result = min(high, result)
    return result


def _float(value, default=0.0, low=None, high=None):
    try:
        result = float(value)
    except (TypeError, ValueError):
        result = default
    if low is not None:
        result = max(low, result)
    if high is not None:
        result = min(high, result)
    return result


def _media(value):
    text = str(value or '')
    return text[:2000] if text.startswith('/') else ''


def default_pattern(index=1):
    return {
        'id': f'slot-pattern-{index}', 'name': f'スロット{index}', 'enabled': True,
        'machineType': 'normal', 'giftName': '', 'giftSpins': 1,
        'sign': 'plus', 'hitDenominator': 199, 'replayEnabled': True,
        'spinSeconds': 1.8, 'stopInterval': .35, 'resultSeconds': 1.2,
        'hitNoticeSeconds': 2.0, 'hitAlignSeconds': 2.4,
        'bigEffectEnabled': True, 'bigEffectMode': 'visual-audio', 'bigEffectSeconds': 3.0,
        'monitorTextEnabled': True, 'spinText': '回転中', 'bonusText': 'BONUS!',
        'missText': 'はずれ', 'winResultText': '+{win} WIN',
        'monitorTextColor': '#ffffff', 'monitorTextSize': 70,
        'missSymbols': ['BAR', 'ベル', 'ブドウ', '7', 'チェリー'],
        'symbols': [
            {'id': 'symbol-bar', 'name': 'BAR', 'imageUrl': ''},
            {'id': 'symbol-bell', 'name': 'ベル', 'imageUrl': ''},
            {'id': 'symbol-grape', 'name': 'ブドウ', 'imageUrl': ''},
            {'id': 'symbol-seven', 'name': '7', 'imageUrl': ''},
            {'id': 'symbol-cherry', 'name': 'チェリー', 'imageUrl': ''},
        ],
        'bigSymbolText': '7', 'bigSymbolImageUrl': '', 'bigWin': 100,
        'payoutMode': 'fixed', 'payouts': [{'win': 100, 'weight': 100}],
        'smallRoles': [
            {'id': 'replay', 'name': 'リプレイ', 'enabled': True, 'probability': 14.0,
             'symbolText': 'REPLAY', 'symbolImageUrl': '', 'addSpinsEnabled': True,
             'addSpins': 1, 'addWinEnabled': False, 'win': 0,
             'animationUrl': '', 'audioUrl': '', 'audioVolume': 75, 'effectSeconds': 1.2},
            {'id': 'grape', 'name': 'ブドウ', 'enabled': True, 'probability': 12.0,
             'symbolText': 'ブドウ', 'symbolImageUrl': '', 'addSpinsEnabled': False,
             'addSpins': 3, 'addWinEnabled': False, 'win': 0,
             'animationUrl': '', 'audioUrl': '', 'audioVolume': 75, 'effectSeconds': 1.2},
        ],
        'atEnabled': False, 'atSpins': 30, 'atHitDenominator': 20,
        'atContinuationRate': 70, 'upperAtEnabled': False, 'upperAtChance': 10,
        'upperAtSpins': 50, 'upperAtHitDenominator': 10,
        'cabinetUrl': '', 'monitorUrl': '', 'gogoUrl': '', 'gogoAudioUrl': '',
        'startAudioUrl': '', 'spinAudioUrl': '', 'stopAudioUrl': '',
        'stop1AudioUrl': '', 'stop2AudioUrl': '', 'stop3AudioUrl': '',
        'bigEffectUrl': '', 'bigEffectAudioUrl': '', 'smallRoleAudioVolume': 75,
        'gogoAudioVolume': 80, 'startAudioVolume': 65, 'spinAudioVolume': 55, 'stopAudioVolume': 65,
        'stop1AudioVolume': 65, 'stop2AudioVolume': 65, 'stop3AudioVolume': 65,
        'bigEffectAudioVolume': 80, 'bigEffectVideoVolume': 70,
        'videoVolume': 70, 'background': '#08090d', 'accent': '#ffcf59',
        'textColor': '#ffffff', 'reelColor': '#f7f2df',
        'cabinetSize': 100, 'monitorSize': 100, 'gogoSize': 100,
        'symbolSize': 88, 'bigEffectSize': 100, 'defaultGogoEnabled': True,
    }


def normalize_pattern(raw, index=1):
    raw = raw if isinstance(raw, dict) else {}
    base = default_pattern(index)
    result = {**base, **raw}
    result['id'] = str(raw.get('id') or base['id'])[:80]
    result['name'] = str(raw.get('name') or base['name'])[:60]
    result['enabled'] = raw.get('enabled', True) is not False
    result['machineType'] = 'at' if raw.get('machineType') == 'at' else 'normal'
    result['giftName'] = str(raw.get('giftName') or '').strip()[:120]
    result['giftSpins'] = _int(raw.get('giftSpins'), 1, 1, 10000)
    result['sign'] = raw.get('sign') if raw.get('sign') in ('plus', 'minus', 'both') else 'plus'
    result['hitDenominator'] = _int(raw.get('hitDenominator'), 199, 1, 1000000)
    result['replayEnabled'] = raw.get('replayEnabled', True) is not False
    for key, default, low, high in (
        ('spinSeconds', 1.8, .2, 30), ('stopInterval', .35, .05, 5),
        ('resultSeconds', 1.2, .1, 30), ('hitNoticeSeconds', 2, .1, 30),
        ('hitAlignSeconds', 2.4, .3, 30), ('bigEffectSeconds', 3, .1, 60),
    ):
        result[key] = _float(raw.get(key), default, low, high)
    result['bigSymbolText'] = str(raw.get('bigSymbolText') or '7')[:30]
    result['bigEffectMode'] = 'audio-only' if raw.get('bigEffectMode') == 'audio-only' else 'visual-audio'
    result['monitorTextEnabled'] = raw.get('monitorTextEnabled', True) is not False
    for key, default in (('spinText', '回転中'), ('bonusText', 'BONUS!'),
                         ('missText', 'はずれ'), ('winResultText', '+{win} WIN')):
        value = raw.get(key)
        result[key] = str(default if value is None else value)[:120]
    result['monitorTextSize'] = _int(raw.get('monitorTextSize'), 70, 10, 300)
    result['bigWin'] = _int(raw.get('bigWin'), 100, 0, 999999)
    result['payoutMode'] = 'weighted' if raw.get('payoutMode') == 'weighted' else 'fixed'
    payouts = []
    for row in (raw.get('payouts') or [])[:100]:
        if isinstance(row, dict):
            payouts.append({'win': _int(row.get('win'), 0, 0, 999999),
                            'weight': _int(row.get('weight'), 0, 0, 1000000)})
    result['payouts'] = payouts or copy.deepcopy(base['payouts'])
    symbols = [str(x or '')[:30] for x in (raw.get('missSymbols') or []) if str(x or '').strip()]
    result['missSymbols'] = symbols[:30] or copy.deepcopy(base['missSymbols'])
    symbol_rows=[]
    for symbol_index,row in enumerate((raw.get('symbols') or [])):
        if not isinstance(row,dict): continue
        symbol_rows.append({'id':str(row.get('id') or f'symbol-{symbol_index+1}')[:80],
                            'name':str(row.get('name') or f'図柄{symbol_index+1}')[:30],
                            'imageUrl':_media(row.get('imageUrl'))})
    if not symbol_rows:
        symbol_rows=[{'id':f'symbol-{i+1}','name':name,'imageUrl':''} for i,name in enumerate(result['missSymbols'])]
    result['symbols']=symbol_rows[:50]
    roles = []
    for role_index, role in enumerate((raw.get('smallRoles') or [])[:50]):
        if not isinstance(role, dict):
            continue
        rid = str(role.get('id') or f'role-{role_index + 1}')[:80]
        is_replay = rid == 'replay'
        roles.append({
            'id': rid, 'name': str(role.get('name') or f'小役{role_index + 1}')[:60],
            'enabled': role.get('enabled', True) is not False,
            'probability': _float(role.get('probability'), 0, 0, 100),
            'symbolText': str(role.get('symbolText') or role.get('name') or '小役')[:30],
            'symbolImageUrl': _media(role.get('symbolImageUrl')),
            'addSpinsEnabled': bool(role.get('addSpinsEnabled', is_replay)),
            'addSpins': _int(role.get('addSpins'), 1 if is_replay else 0, 0, 10000),
            'addWinEnabled': bool(role.get('addWinEnabled', False)),
            'win': _int(role.get('win'), 0, 0, 999999),
            'animationUrl': _media(role.get('animationUrl')),
            'audioUrl': _media(role.get('audioUrl')),
            'audioVolume': _int(role.get('audioVolume'), 75, 0, 100),
            'effectSeconds': _float(role.get('effectSeconds'), result['resultSeconds'], .1, 60),
        })
    result['smallRoles'] = roles or copy.deepcopy(base['smallRoles'])
    if not result['replayEnabled']:
        for role in result['smallRoles']:
            if role['id'] == 'replay':
                role['enabled'] = False
    for key, default, low, high in (
        ('atSpins', 30, 1, 10000), ('atHitDenominator', 20, 1, 1000000),
        ('atContinuationRate', 70, 0, 100), ('upperAtChance', 10, 0, 100),
        ('upperAtSpins', 50, 1, 10000), ('upperAtHitDenominator', 10, 1, 1000000),
        ('smallRoleAudioVolume', 75, 0, 100), ('gogoAudioVolume', 80, 0, 100),
        ('startAudioVolume', 65, 0, 100), ('spinAudioVolume', 55, 0, 100), ('stopAudioVolume', 65, 0, 100),
        ('stop1AudioVolume', 65, 0, 100), ('stop2AudioVolume', 65, 0, 100),
        ('stop3AudioVolume', 65, 0, 100), ('bigEffectAudioVolume', 80, 0, 100),
        ('bigEffectVideoVolume', 70, 0, 100),
        ('videoVolume', 70, 0, 100),
        ('cabinetSize', 100, 10, 200), ('monitorSize', 100, 10, 200),
        ('gogoSize', 100, 10, 200), ('symbolSize', 88, 10, 150),
        ('bigEffectSize', 100, 10, 200),
    ):
        result[key] = _int(raw.get(key), default, low, high)
    result['atEnabled'] = bool(raw.get('atEnabled', result['machineType'] == 'at'))
    result['upperAtEnabled'] = bool(raw.get('upperAtEnabled', False))
    result['defaultGogoEnabled'] = raw.get('defaultGogoEnabled', True) is not False
    result['bigEffectEnabled'] = raw.get('bigEffectEnabled', True) is not False
    for key in ('bigSymbolImageUrl', 'cabinetUrl', 'monitorUrl', 'gogoUrl',
                'gogoAudioUrl', 'startAudioUrl', 'spinAudioUrl', 'stopAudioUrl',
                'stop1AudioUrl', 'stop2AudioUrl', 'stop3AudioUrl',
                'bigEffectUrl', 'bigEffectAudioUrl'):
        result[key] = _media(raw.get(key))
    for key, default in (('background', '#08090d'), ('accent', '#ffcf59'),
                         ('textColor', '#ffffff'), ('reelColor', '#f7f2df'),
                         ('monitorTextColor', '#ffffff')):
        value = str(raw.get(key) or '')
        result[key] = value.lower() if len(value) == 7 and value.startswith('#') else default
    return result


def normalize_slot_machine(raw, server_started_at=0):
    raw = raw if isinstance(raw, dict) else {}
    patterns = [normalize_pattern(row, i + 1) for i, row in enumerate(raw.get('patterns') or [])]
    if not patterns:
        patterns = [default_pattern()]
    event = raw.get('event') if isinstance(raw.get('event'), dict) else {}
    created = _float(event.get('createdAt'), 0, 0)
    active = bool(event.get('active')) and created >= server_started_at
    cleaned_event = copy.deepcopy(event) if active else copy.deepcopy(EMPTY_EVENT)
    if active:
        cleaned_event['spins'] = [x for x in (event.get('spins') or []) if isinstance(x, dict)][:20000]
        cleaned_event['appliedSpins'] = _int(event.get('appliedSpins'), 0, 0, len(cleaned_event['spins']))
        cleaned_event['total'] = _int(event.get('total'), 0, 0, 999999999)
    queue = [x for x in (raw.get('queue') or []) if isinstance(x, dict)][:200] if active else []
    return {'patterns': patterns, 'queue': queue, 'history': [x for x in (raw.get('history') or []) if isinstance(x, dict)][:200],
            'shortcutChoicePlus': str(raw.get('shortcutChoicePlus') or 'CTRL+ALT+6').upper()[:80],
            'shortcutChoiceMinus': str(raw.get('shortcutChoiceMinus') or 'CTRL+ALT+SHIFT+6').upper()[:80],
            'event': cleaned_event}


def _weighted_payout(pattern):
    if pattern.get('payoutMode') != 'weighted':
        return pattern['bigWin']
    rows = [x for x in pattern['payouts'] if x['weight'] > 0]
    total = sum(x['weight'] for x in rows)
    if not total:
        return pattern['bigWin']
    pick = random.uniform(0, total)
    upto = 0
    for row in rows:
        upto += row['weight']
        if pick <= upto:
            return row['win']
    return rows[-1]['win']


def _miss_reels(pattern):
    symbols = pattern.get('symbols') or [{'name':x,'imageUrl':''} for x in pattern['missSymbols']]
    picked = [random.choice(symbols) for _ in range(3)]
    if len(symbols)>1 and picked[0]['id'] == picked[1]['id'] == picked[2]['id']:
        current=next((i for i,x in enumerate(symbols) if x['id']==picked[2]['id']),0)
        picked[2]=symbols[(current+1)%len(symbols)]
    return [x['name'] for x in picked],[x.get('imageUrl','') for x in picked]


def build_event(pattern, gift_name, sender_name, avatar_url='', is_test=False):
    budget = pattern['giftSpins']
    max_spins = min(20000, max(budget, budget * 20, budget + 20))
    mode = 'normal'
    spins = []
    safety = 0
    while budget > 0 and safety < max_spins:
        safety += 1
        budget -= 1
        denominator = pattern['hitDenominator']
        if mode == 'at':
            denominator = pattern['atHitDenominator']
        elif mode == 'upper':
            denominator = pattern['upperAtHitDenominator']
        hit = random.randrange(denominator) == 0
        if hit:
            win = _weighted_payout(pattern)
            symbol = pattern['bigSymbolText']
            spins.append({'kind': 'hit', 'roleName': '大当たり', 'reels': [symbol] * 3,
                          'symbolImageUrl': pattern['bigSymbolImageUrl'], 'win': win,
                          'addedSpins': 0, 'mode': mode})
            if pattern['machineType'] == 'at' and pattern['atEnabled']:
                if mode == 'normal':
                    mode = 'upper' if pattern['upperAtEnabled'] and random.random() * 100 < pattern['upperAtChance'] else 'at'
                    requested = pattern['upperAtSpins'] if mode == 'upper' else pattern['atSpins']
                    added = min(requested, max(0, max_spins - len(spins) - budget))
                    budget += added
                    spins[-1]['addedSpins'] = added
                elif random.random() * 100 < pattern['atContinuationRate']:
                    requested = pattern['upperAtSpins'] if mode == 'upper' else pattern['atSpins']
                    added = min(requested, max(0, max_spins - len(spins) - budget))
                    budget += added
                    spins[-1]['addedSpins'] = added
            continue
        roles = [x for x in pattern['smallRoles'] if x['enabled'] and x['probability'] > 0]
        pick = random.random() * 100
        chosen = None
        upto = 0
        for role in roles:
            upto += role['probability']
            if pick < upto:
                chosen = role
                break
        if chosen:
            requested = chosen['addSpins'] if chosen['addSpinsEnabled'] else 0
            added = min(requested, max(0, max_spins - len(spins) - 1 - budget))
            budget += added
            symbol = chosen['symbolText']
            spins.append({'kind': 'replay' if chosen['id'] == 'replay' else 'small',
                          'roleId': chosen['id'], 'roleName': chosen['name'],
                          'reels': [symbol] * 3, 'symbolImageUrl': chosen['symbolImageUrl'],
                          'animationUrl': chosen['animationUrl'], 'audioUrl': chosen['audioUrl'],
                          'audioVolume': chosen['audioVolume'],
                          'effectSeconds': chosen['effectSeconds'],
                          'win': chosen['win'] if chosen['addWinEnabled'] else 0,
                          'addedSpins': added, 'mode': mode})
        else:
            reel_text,reel_images=_miss_reels(pattern)
            spins.append({'kind': 'miss', 'roleName': 'はずれ', 'reels': reel_text,
                          'reelImages':reel_images, 'symbolImageUrl': '', 'win': 0, 'addedSpins': 0, 'mode': mode})
    now = time.time()
    return {
        'id': int(now * 1000), 'type': 'slot', 'active': True,
        'patternId': pattern['id'], 'patternName': pattern['name'],
        'senderName': str(sender_name or 'ゲスト')[:80], 'avatarUrl': str(avatar_url or '')[:2000],
        'giftName': str(gift_name or '')[:120], 'initialSpins': pattern['giftSpins'],
        'spins': spins, 'appliedSpins': 0, 'total': 0, 'choice': '',
        'choiceReady': False, 'winApplied': False, 'sign': pattern['sign'],
        'pattern': copy.deepcopy(pattern), 'isTest': bool(is_test), 'createdAt': now,
    }


def run_slot_draw(state, pattern, gift_name='', sender_name='', avatar_url='', is_test=False):
    machine = state['slotMachine']
    event = build_event(pattern, gift_name, sender_name, avatar_url, is_test)
    if machine.get('event', {}).get('active'):
        machine.setdefault('queue', []).append(event)
    else:
        machine['event'] = event
    return event


def apply_spin(state, event_id, spin_index):
    event = state['slotMachine']['event']
    if not event.get('active') or _int(event.get('id')) != _int(event_id):
        return False
    index = _int(spin_index, -1)
    if index != _int(event.get('appliedSpins')) or not 0 <= index < len(event.get('spins') or []):
        return False
    spin = event['spins'][index]
    event['total'] = min(999999999, _int(event.get('total')) + _int(spin.get('win')))
    event['appliedSpins'] = index + 1
    if event['appliedSpins'] >= len(event['spins']):
        if event.get('sign') == 'both':
            event['choiceReady'] = True
        elif not event.get('isTest') and not event.get('winApplied'):
            delta = event['total'] * (-1 if event.get('sign') == 'minus' else 1)
            state['winCounter']['currentWin'] = max(-999999, min(999999, _int(state['winCounter'].get('currentWin')) + delta))
            event['winApplied'] = True
            event['choice'] = event.get('sign')
    return True


def choose_sign(state, event_id, choice):
    event = state['slotMachine']['event']
    if (not event.get('active') or _int(event.get('id')) != _int(event_id)
            or not event.get('choiceReady') or event.get('choice') or choice not in ('plus', 'minus')):
        return False
    event['choice'] = choice
    event['choiceReady'] = False
    if not event.get('isTest') and not event.get('winApplied'):
        delta = event['total'] * (-1 if choice == 'minus' else 1)
        state['winCounter']['currentWin'] = max(-999999, min(999999, _int(state['winCounter'].get('currentWin')) + delta))
        event['winApplied'] = True
    return True


def complete_event(state, event_id):
    machine = state['slotMachine']
    event = machine['event']
    if not event.get('active') or _int(event.get('id')) != _int(event_id):
        return False
    if _int(event.get('appliedSpins')) < len(event.get('spins') or []) or event.get('choiceReady'):
        return False
    if not event.get('isTest'):
        machine.setdefault('history', []).insert(0, {
            'senderName': event.get('senderName', ''), 'avatarUrl': event.get('avatarUrl', ''),
            'giftName': event.get('giftName', ''), 'patternName': event.get('patternName', ''),
            'spins': len(event.get('spins') or []), 'win': event.get('total', 0),
            'sign': event.get('choice') or event.get('sign', 'plus'), 'createdAt': time.time(),
        })
        machine['history'] = machine['history'][:200]
    machine['event'] = machine.setdefault('queue', []).pop(0) if machine.get('queue') else copy.deepcopy(EMPTY_EVENT)
    return True
