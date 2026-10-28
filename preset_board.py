"""Static gift instruction boards; independent of playback queues and histories."""
import math
import re

def number(value, default, low, high):
    try:
        value=float(value)
        if not math.isfinite(value):raise ValueError()
    except (TypeError,ValueError,OverflowError):value=default
    return float(max(low,min(high,value)))

def image_url(value):
    text=str(value or '')[:2000]
    return text if (text.startswith('/') and not text.startswith('//')) or text.startswith(('https://','http://')) else ''

def normalize_presets(raw):
    raw=raw if isinstance(raw,dict) else {}
    boards=[]
    sources=raw.get('boards') if isinstance(raw.get('boards'),list) else []
    for i,source in enumerate(sources[:20]):
        if not isinstance(source,dict):continue
        color=lambda key,default: str(source.get(key)) if re.fullmatch(r'#[0-9a-fA-F]{6}',str(source.get(key) or '')) else default
        rows=[]
        items=source.get('items') if isinstance(source.get('items'),list) else []
        for j,row in enumerate(items[:100]):
            if not isinstance(row,dict):continue
            rows.append({'id':str(row.get('id') or f'item-{j+1}')[:80],
                         'giftId':str(row.get('giftId') or '')[:120],
                         'giftName':str(row.get('giftName') or '')[:120],
                         'giftImageUrl':image_url(row.get('giftImageUrl')),
                         'imageUrl':image_url(row.get('imageUrl')),'imageName':str(row.get('imageName') or '')[:120],
                         'description':str(row.get('description') or '')[:500],
                         'enabled':row.get('enabled',True) is not False})
        boards.append({'id':str(source.get('id') or f'preset-{i+1}')[:80],
                       'name':str(source.get('name') or f'プリセット{i+1}')[:60],
                       'style':source.get('style') if source.get('style') in ('simple','neon','warm') else 'simple',
                       'columns':int(number(source.get('columns'),4,1,12)),
                       'gap':number(source.get('gap'),6,0,100),'cardWidth':number(source.get('cardWidth'),150,60,1000),
                       'cardHeight':number(source.get('cardHeight'),150,60,1000),
                       'imageSize':number(source.get('imageSize'),58,16,500),
                       'fontSize':number(source.get('fontSize'),20,10,150),
                       'fontFamily':source.get('fontFamily') if source.get('fontFamily') in ('system','yuGothic','meiryo','serif','gothic','mono') else 'system',
                       'background':color('background','#17151c'),'accent':color('accent','#ffb338'),
                       'textColor':color('textColor','#ffffff'),'opacity':number(source.get('opacity'),90,0,100),
                       'transparent':source.get('transparent',False) is True,
                       'radius':number(source.get('radius'),12,0,100),
                       'outline':source.get('outline',True) is not False,
                       'customCss':str(source.get('customCss') or '')[:20000],
                       'items':rows})
    return {'boards':boards}
