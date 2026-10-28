"""Per-media duration settings survive normalization and repeated saves."""
import copy
from pathlib import Path
import sys
import tempfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1] if Path(__file__).parent.name=='tests' else Path(__file__).parent))
import server as app

state=copy.deepcopy(app.DEFAULT)
state['pachinkoGacha']['patterns']=[{'id':'p','hitAudioUrl':'/existing.mp3','preAlerts':[{'audioSeconds':7,'mediaSeconds':9}]}]
data,_=app.normalize_state(state)
p=data['pachinkoGacha']['patterns'][0]
assert p['preAlert1AudioSeconds']==7 and p['preAlerts'][0]['mediaSeconds']==9
assert p['hitImageSeconds']==0 and p['hitVideoSeconds']==0 and p['hitAudioSeconds']==0
stages=('spin','reach','cz','hit','at','upper','lt','end','stop','preAlert1','preAlert2','preAlert3')+app.pachinko_boundary_stages()+app.pachinko_phase_media_stages()
for stage in stages:
    for kind,value in [('Image',1.2),('Video',8.5),('Audio',4.3)]:p[stage+kind+'Seconds']=value
p['spinBeepAudioSeconds']=2.5
p['hitImageSeconds']=-3;p['upperVideoSeconds']=1000
with tempfile.TemporaryDirectory() as folder:
    app.ROOT=Path(folder);app.STATE=app.ROOT/'state.json'
    for _ in range(2):
        app.write_state(data);data=app.read_state()
    saved=data['pachinkoGacha']['patterns'][0]
    for stage in stages:
        assert saved[stage+'AudioSeconds']==4.3
        assert saved[stage+'ImageSeconds']==(0 if stage=='hit' else 1.2)
        assert saved[stage+'VideoSeconds']==(600 if stage=='upper' else 8.5)
    assert saved['spinBeepAudioSeconds']==2.5
    assert saved['hitAudioUrl']=='/existing.mp3'
print('PASS: all stage duration round trips, decimal values, bounds, legacy pre-alert durations and existing media retained')
