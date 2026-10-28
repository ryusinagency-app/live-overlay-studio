import copy
import random
import sys
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import slot_machine as slot

def check():
    base={'challengeEnabled':True,'challengeSpins':3,'challengeHitDenominator':2,'hitDenominator':199,'smallRoles':[],'replayEnabled':False,'sign':'both'}
    p=slot.normalize_pattern(base)
    sequence=iter([0,1,0,1,1,1,1]);denominators=[]
    def draw(d):denominators.append(d);return next(sequence)
    with patch('slot_machine.random.randrange',side_effect=draw):event=slot.build_event(p,'gift','sender',initial_spins=2)
    spins=event['spins']
    assert denominators==[199,2,2,2,2,2,199]
    assert [x['mode'] for x in spins]==['normal','challenge','challenge','challenge','challenge','challenge','normal']
    assert spins[0]['addedSpins']==3 and spins[2]['addedSpins']==2
    assert spins[2]['challengeRemaining']==3 and spins[3]['challengeGame']==1
    assert spins[5]['challengeEnded'] and spins[6]['mode']=='normal'
    state={'slotMachine':{'patterns':[p],'event':event,'queue':[],'history':[]},'winCounter':{'currentWin':10}}
    assert slot.visible_spin_count(event)==2
    assert slot.apply_spin(state,event['id'],0) and slot.visible_spin_count(event)==4
    assert slot.apply_spin(state,event['id'],1) and slot.visible_spin_count(event)==3
    assert slot.apply_spin(state,event['id'],2) and slot.visible_spin_count(event)==4
    for index in range(3,len(spins)):assert slot.apply_spin(state,event['id'],index)
    assert event['total']==200 and slot.visible_spin_count(event)==0
    assert event['choiceReady'] and slot.choose_sign(state,event['id'],'minus')
    assert state['winCounter']['currentWin']==-190
    assert not slot.choose_sign(state,event['id'],'plus')
    # OFF does not alter the RNG sequence or awarded games.
    for enabled in [False,None]:
        raw={**base,'giftSpins':7};raw.pop('challengeEnabled')
        if enabled is not None:raw['challengeEnabled']=enabled
        random.seed(14);a=slot.build_event(slot.normalize_pattern(raw),'g','u')
        random.seed(14);b=slot.build_event(slot.normalize_pattern({**raw,'challengeEnabled':False}),'g','u')
        assert a['spins']==b['spins'] and all(x['mode']!='challenge' for x in a['spins'])
    # AT ignores the stored normal-only flag, even after changing machine type.
    for enabled in [False,True]:
        random.seed(32);plan=slot.build_event(slot.normalize_pattern({**base,'machineType':'at','challengeEnabled':enabled,'atEnabled':True}),'g','u',is_test=True)
        if not enabled:original=plan['spins']
        else:assert plan['spins']==original
    # The window is granted in full even with one gift game and large windows.
    values=iter([0]+[1]*500)
    with patch('slot_machine.random.randrange',side_effect=lambda d:next(values)):
        large=slot.build_event(slot.normalize_pattern({**base,'challengeSpins':500}),'g','u',is_test=True)
    assert len(large['spins'])==501 and large['spins'][-1]['challengeEnded']
    # Repeated guaranteed hits remain bounded and never produce negative budgets.
    repeated=slot.build_event(slot.normalize_pattern({**base,'hitDenominator':1,'challengeHitDenominator':1}),'g','u',is_test=True)
    assert 1<len(repeated['spins'])<=20000 and all(x['addedSpins']>=0 for x in repeated['spins'])
    # All dedicated media controls survive old-state normalization.
    raw=copy.deepcopy(base)
    for scene in ['challenge','challengeEntry','challengeBigEffect']:
        raw.update({scene+'Url':'/a.mp4',scene+'AudioUrl':'/a.mp3',scene+'ImageSeconds':1.2,scene+'VideoSeconds':3.4,scene+'AudioSeconds':2.3,scene+'AudioVolume':37,scene+'VideoVolume':28,scene+'AudioLoop':False,scene+'VideoLoop':False})
    saved=slot.normalize_pattern(slot.normalize_pattern(raw))
    for scene in ['challenge','challengeEntry','challengeBigEffect']:
        for suffix in ['Url','AudioUrl','ImageSeconds','VideoSeconds','AudioSeconds','AudioVolume','VideoVolume','AudioLoop','VideoLoop']:assert saved[scene+suffix]==raw[scene+suffix]
    print('PASS challenge chain/reset, failed-window return, normal gift budget, signed WIN/idempotency, OFF/AT compatibility, full grants, safety bounds, media settings')

if __name__=='__main__':check()
