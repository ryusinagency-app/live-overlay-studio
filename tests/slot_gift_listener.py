import copy
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import server


def check_slot_gift_id_matching():
    original_state = server.STATE
    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            server.STATE = Path(temp_dir) / 'state.json'
            state = copy.deepcopy(server.DEFAULT)
            pattern = state['slotMachine']['patterns'][0]
            pattern.update({
                'id': 'slot-id-test',
                'name': 'ID照合テスト',
                'enabled': True,
                'hitDenominator': 1_000_000,
                'replayEnabled': False,
                'smallRoles': [],
                # Deliberately use a name which does not match the incoming
                # language.  The stable TikTok gift ID must still trigger it.
                'giftRules': [{'id': 'gift-rule', 'giftId': '5655', 'giftName': 'バラ', 'spins': 2}],
            })
            server.STATE.write_text(json.dumps(state, ensure_ascii=False), encoding='utf-8')

            matched = server.process_gift_event(
                'Rose', 3, '配信者', {'id': '5655', 'name': 'Rose', 'price': 1}
            )
            saved = json.loads(server.STATE.read_text(encoding='utf-8'))
            event = saved['slotMachine']['event']
            assert matched
            assert event['active'] and event['patternId'] == 'slot-id-test'
            assert event['initialSpins'] == 6 and len(event['spins']) == 6
    finally:
        server.STATE = original_state


if __name__ == '__main__':
    check_slot_gift_id_matching()
    print('PASS slot gift listener: stable gift ID matching and combo spins')
