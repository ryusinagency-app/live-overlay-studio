import random
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from slot_machine import (apply_spin, build_event, choose_sign, complete_event,
                          default_pattern, normalize_slot_machine, JST)


def check_multiple_gifts_and_combo_spin_budget():
    legacy = normalize_slot_machine({'patterns': [{'giftName': 'バラ', 'giftSpins': 1}]})['patterns'][0]
    assert legacy['giftRules'] == [{'id': 'slot-gift-1', 'giftId': '', 'giftName': 'バラ', 'spins': 1}]
    pattern = normalize_slot_machine({'patterns': [{
        'giftRules': [
            {'id': 'rose', 'giftId': '5655', 'giftName': 'バラ', 'spins': 1},
            {'id': 'heart', 'giftId': '1234', 'giftName': 'ハンドハート', 'spins': 50},
        ],
        'hitDenominator': 1_000_000,
        'replayEnabled': False,
        'smallRoles': [],
    }]})['patterns'][0]
    assert [(row['giftName'], row['spins']) for row in pattern['giftRules']] == [('バラ', 1), ('ハンドハート', 50)]
    assert [row['giftId'] for row in pattern['giftRules']] == ['5655', '1234']
    event = build_event(pattern, 'ハンドハート', 'テスト', initial_spins=150)
    assert event['initialSpins'] == 150 and len(event['spins']) == 150


def check_gift_spins_and_hit_continuation():
    pattern = default_pattern()
    pattern.update({'giftSpins': 5, 'hitDenominator': 1, 'sign': 'both'})
    event = build_event(pattern, 'バラ', 'りゅーしん')
    assert len(event['spins']) == 5
    assert all(spin['kind'] == 'hit' for spin in event['spins'])
    state = {'slotMachine': {'patterns': [pattern], 'queue': [], 'history': [], 'event': event},
             'winCounter': {'currentWin': 10}}
    for index in range(5):
        assert apply_spin(state, event['id'], index)
    assert state['winCounter']['currentWin'] == 10
    assert state['slotMachine']['event']['choiceReady']
    assert choose_sign(state, event['id'], 'minus')
    assert state['winCounter']['currentWin'] == -490
    assert complete_event(state, event['id'])


def check_small_role_bonus_and_normalization():
    pattern = default_pattern()
    pattern.update({'giftSpins': 1, 'hitDenominator': 1_000_000, 'replayEnabled': False})
    pattern['smallRoles'] = [{'id': 'grape', 'name': 'ブドウ', 'enabled': True,
                              'probability': 100, 'symbolText': 'G',
                              'addSpinsEnabled': True, 'addSpins': 1,
                              'addWinEnabled': False, 'win': 0,
                              'effectSeconds': 4.7}]
    normalized = normalize_slot_machine({'patterns': [pattern]})['patterns'][0]
    assert normalized['smallRoles'][0]['effectSeconds'] == 4.7
    random.seed(3)
    event = build_event(normalized, 'テスト', 'テスト')
    assert len(event['spins']) == 21
    assert all(spin['addedSpins'] == 1 for spin in event['spins'][:-1])
    assert event['spins'][-1]['addedSpins'] == 0
    assert all(spin['effectSeconds'] == 4.7 for spin in event['spins'])


def check_image_catalog_sizes_and_test_completion():
    pattern = default_pattern()
    pattern.update({'giftSpins': 1, 'hitDenominator': 1, 'sign': 'both',
                    'cabinetSize': 135, 'monitorSize': 80, 'gogoSize': 120,
                    'gogoX': 22, 'gogoY': 84, 'gogoWidth': 640, 'gogoHeight': 360,
                    'symbolSize': 73, 'defaultGogoEnabled': False,
                    'bigEffectEnabled': True, 'bigEffectSeconds': 4.5,
                    'bigEffectMode': 'audio-only',
                    'bigEffectSize': 125, 'bigEffectUrl': '/slot_big.mp4',
                    'bigEffectAudioUrl': '/slot_big.mp3',
                    'monitorTextEnabled': False, 'spinText': '抽選中',
                    'bonusText': '光った！', 'missText': '残念',
                    'winResultText': '{win}枚獲得', 'monitorTextColor': '#12ab34',
                    'monitorTextSize': 88,
                    'stop1AudioUrl': '/slot_stop1.mp3',
                    'stop2AudioUrl': '/slot_stop2.mp3',
                    'stop3AudioUrl': '/slot_stop3.mp3',
                    'symbols': [{'id': 'red-seven', 'name': '赤7', 'imageUrl': '/slot_seven.png'}]})
    normalized = normalize_slot_machine({'patterns': [pattern]})['patterns'][0]
    assert normalized['symbols'][0]['imageUrl'] == '/slot_seven.png'
    assert (normalized['cabinetSize'], normalized['monitorSize'], normalized['gogoSize'],
            normalized['symbolSize'], normalized['defaultGogoEnabled']) == (135, 80, 120, 73, False)
    assert (normalized['gogoX'], normalized['gogoY'], normalized['gogoWidth'],
            normalized['gogoHeight']) == (22, 84, 640, 360)
    assert (normalized['bigEffectEnabled'], normalized['bigEffectSeconds'], normalized['bigEffectSize']) == (True, 4.5, 125)
    assert normalized['bigEffectMode'] == 'audio-only'
    assert (normalized['monitorTextEnabled'], normalized['spinText'], normalized['bonusText'],
            normalized['missText'], normalized['winResultText']) == (False, '抽選中', '光った！', '残念', '{win}枚獲得')
    assert (normalized['monitorTextColor'], normalized['monitorTextSize']) == ('#12ab34', 88)
    assert normalized['bigEffectUrl'] == '/slot_big.mp4'
    assert [normalized[f'stop{i}AudioUrl'] for i in range(1, 4)] == [f'/slot_stop{i}.mp3' for i in range(1, 4)]
    event = build_event(normalized, 'テスト', 'テスト', is_test=True)
    state = {'slotMachine': {'patterns': [normalized], 'queue': [], 'history': [], 'event': event},
             'winCounter': {'currentWin': 10}}
    assert apply_spin(state, event['id'], 0)
    assert state['slotMachine']['event']['choiceReady']
    assert choose_sign(state, event['id'], 'plus')
    assert state['winCounter']['currentWin'] == 10
    assert complete_event(state, event['id'])
    assert not state['slotMachine']['event']['active']


def check_choice_only_for_win_and_queue_gap():
    pattern = default_pattern()
    pattern.update({'giftSpins': 1, 'hitDenominator': 1_000_000,
                    'replayEnabled': False, 'sign': 'both'})
    pattern['smallRoles'] = []
    event = build_event(pattern, 'はずれ', 'A', is_test=True)
    queued = build_event({**pattern, 'hitDenominator': 1}, '当たり', 'B', is_test=True)
    state = {'slotMachine': {'patterns': [pattern], 'queue': [queued], 'history': [], 'event': event},
             'winCounter': {'currentWin': 10}}
    assert apply_spin(state, event['id'], 0)
    assert event['total'] == 0 and not event['choiceReady'] and not event['choice']
    assert complete_event(state, event['id'])
    promoted = state['slotMachine']['event']
    assert promoted['id'] == queued['id'] and promoted['active']
    assert promoted['startAfter'] > time.time()

    winning = build_event({**pattern, 'hitDenominator': 1, 'bigWin': 25}, '当たり', 'C', is_test=True)
    state['slotMachine']['event'] = winning
    assert apply_spin(state, winning['id'], 0)
    assert winning['total'] == 25 and winning['choiceReady'] and not winning['choice']
    assert not complete_event(state, winning['id'])


def check_visible_reels_always_match_the_result():
    pattern = default_pattern()
    pattern.update({'giftSpins': 1, 'hitDenominator': 1_000_000, 'replayEnabled': False})
    # Different catalog IDs using the same visible asset must still count as the
    # same symbol, and a miss must be forced to look different.
    pattern['symbols'] = [
        {'id':'seven-a','name':'7A','imageUrl':'/same-seven.png'},
        {'id':'seven-b','name':'7B','imageUrl':'/same-seven.png'},
    ]
    pattern['smallRoles'] = []
    random.seed(4)
    miss = build_event(pattern, 'テスト', 'テスト')['spins'][0]
    visible = [image or text for image, text in zip(miss['reelImages'], miss['reels'])]
    assert miss['kind'] == 'miss' and len(set(visible)) > 1

    role_pattern = default_pattern()
    role_pattern.update({'giftSpins': 1, 'hitDenominator': 1_000_000, 'replayEnabled': False})
    role_pattern['smallRoles'] = [{'id':'bell','name':'ベル','enabled':True,'probability':100,
        'symbolText':'ベル','symbolImageUrl':'/bell.png','addSpinsEnabled':False,'addSpins':0,
        'addWinEnabled':False,'win':0,'animationUrl':'','audioUrl':'','audioVolume':75,'effectSeconds':1}]
    role = build_event(role_pattern, 'テスト', 'テスト')['spins'][0]
    assert role['kind'] == 'small' and role['reelImages'] == ['/bell.png'] * 3

    hit_pattern = default_pattern()
    hit_pattern.update({'giftSpins':1,'hitDenominator':1,'bigSymbolImageUrl':'/big-seven.png'})
    hit = build_event(hit_pattern, 'テスト', 'テスト')['spins'][0]
    assert hit['kind'] == 'hit' and hit['reelImages'] == ['/big-seven.png'] * 3
    pre_visible = [image or text for image, text in zip(hit['preReelImages'], hit['preReels'])]
    assert len(set(pre_visible)) > 1


def check_daily_stats_and_hit_reset():
    date_key = datetime.now(JST).date().isoformat()
    miss_pattern = default_pattern()
    miss_pattern.update({'id': 'stats-slot', 'name': '統計機', 'giftSpins': 1,
                         'hitDenominator': 1_000_000, 'replayEnabled': False, 'smallRoles': []})
    miss_event = build_event(miss_pattern, 'バラ', 'A')
    state = {'slotMachine': {'patterns': [miss_pattern], 'queue': [], 'history': [],
                             'statsByDate': {}, 'event': miss_event},
             'winCounter': {'currentWin': 0}}
    assert apply_spin(state, miss_event['id'], 0)
    row = state['slotMachine']['statsByDate'][date_key]['stats-slot']
    assert (row['currentSpins'], row['hitCount'], row['totalSpins']) == (1, 0, 1)

    hit_pattern = {**miss_pattern, 'hitDenominator': 1}
    hit_event = build_event(hit_pattern, 'ハンドハート', 'B')
    state['slotMachine']['event'] = hit_event
    assert apply_spin(state, hit_event['id'], 0)
    row = state['slotMachine']['statsByDate'][date_key]['stats-slot']
    assert (row['currentSpins'], row['hitCount'], row['totalSpins']) == (0, 1, 2)

    normalized = normalize_slot_machine({'patterns': [miss_pattern], 'statsByDate': state['slotMachine']['statsByDate']})
    assert normalized['statsByDate'][date_key]['stats-slot']['totalSpins'] == 2
    assert normalized['statsDate'] == date_key
    styled = normalize_slot_machine({'patterns': [{**miss_pattern, 'statsOverlay': {
        'showCurrent': False, 'showState': True, 'layout': 'vertical',
        'textColor': '#123456', 'valueSize': 72,
    }}]})['patterns'][0]['statsOverlay']
    assert not styled['showCurrent'] and styled['showState'] and styled['layout'] == 'vertical'
    assert styled['textColor'] == '#123456' and styled['valueSize'] == 72


if __name__ == '__main__':
    check_multiple_gifts_and_combo_spin_budget()
    check_gift_spins_and_hit_continuation()
    check_small_role_bonus_and_normalization()
    check_image_catalog_sizes_and_test_completion()
    check_choice_only_for_win_and_queue_gap()
    check_visible_reels_always_match_the_result()
    check_daily_stats_and_hit_reset()
    print('PASS slot rules: gifts, combo spins, reels, daily stats and signed WIN')
