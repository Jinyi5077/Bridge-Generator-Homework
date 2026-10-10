"""Validate AI input as drawing data, with no execution of embedded code."""
import json
import math
from pathlib import Path
from .geometry import Geometry

SCHEMA = 'bridgecad.instructions.v1'
GEOMETRY_DEFAULTS = {
    'project_name':'四车道分离式连续箱梁课程设计',
    'designer_name':'','student_id':'','institution':'','class_name':'',
    'supervisor':'','drawing_date':'','elevation_mode':'relative',
    'deck_elevation':0.,'longitudinal_slope':0.,
    'lanes':4,'layout':'auto',
    'main_span':100.,'side_span_mode':'auto_ratio','side_span_ratio':.6,
    'left_side_span':60.,'right_side_span':60.,'lane_width':3.5,
    'barrier_width':.5,'deck_gap':1.,'inner_margin':.5,'outer_margin':.5,
    'cantilever_width':2.,'height_reference_span':100.,'height_mid':2.8,
    'height_pier':5.8,'height_curve_exponent':1.8,'cross_slope':.02,
    'top_thickness':.30,'tip_thickness':.20,'top_haunch_horizontal':.70,
    'top_haunch_vertical':.25,'bottom_mid':.28,'bottom_pier':.70,
    'bottom_chamfer_horizontal':.60,'bottom_chamfer_vertical':.30,
    'web_mid':.55,'web_pier':.80,'concrete':'C50','pavement_thickness':.10,
    'pier_height':15.,'pile_length':25.,'segment_length':5.,
}
DRAWING_DEFAULTS = {
    'sheets':['general','midspan','pier'],'barrier_height':1.10,
    'bearing_height':.25,'zero_block_length':8.,'closure_length':2.,
    'longitudinal_slope':0.,'station_origin_m':0.,'station_prefix':'K',
    'show_segments':True,'show_substructure':True,'notes':[],
}
SHEETS = {'general','midspan','pier'}
ROLE_LAYERS = {'outline':'B-OUTLINE','cut':'B-CUT','detail':'B-DETAIL',
               'center':'B-CENTER','hidden':'B-HIDDEN','prestress':'B-PRESTRESS'}
OPS = {
    'line': {'start','end'}, 'polyline':{'points','closed'},
    'circle':{'center','radius'}, 'text':{'point','text','align','numeric'},
    'dimension':{'start','end','offset','vertical'},
    'leader':{'point','end','text'},
}

def number(value, name, lo=None, hi=None):
    if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value):
        raise ValueError(name+' 必须为有限数字')
    if lo is not None and value<lo or hi is not None and value>hi:
        raise ValueError(f'{name} 超出范围 [{lo}, {hi}]')
    return float(value)

def text(value,name,max_length=80):
    if not isinstance(value,str) or not value.strip() or len(value)>max_length or any(ord(c)<32 for c in value):
        raise ValueError(name+f' 必须为1～{max_length}字符的单行文字')
    return value

def keys(data, allowed, where):
    if not isinstance(data,dict):raise ValueError(where+' 必须是对象')
    unknown=set(data)-set(allowed)
    if unknown:raise ValueError(where+' 含不支持的字段：'+','.join(sorted(unknown)))

def point(value,where):
    if not isinstance(value,list) or len(value)!=2:raise ValueError(where+' 必须为[x,y]坐标')
    return [number(v,where,-2000,2000) for v in value]

def normalize(data):
    keys(data,{'schema','units','bridge','drawing','commands','prestress'},'指令')
    if data.get('schema')!=SCHEMA:raise ValueError('schema 必须为 '+SCHEMA)
    if data.get('units')!='m':raise ValueError('输入长度单位必须明确写为 m；成图模型统一为 mm')
    supplied=data.get('bridge',{})
    keys(supplied,GEOMETRY_DEFAULTS.keys() | {'spans_m'},'bridge')
    c={**GEOMETRY_DEFAULTS,**supplied}
    if 'spans_m' in supplied:
        if any(k in supplied for k in ('main_span','left_side_span','right_side_span','side_span_mode','side_span_ratio')):
            raise ValueError('spans_m 与其他跨径字段不可同时提供')
        spans=c.pop('spans_m')
        if not isinstance(spans,list) or len(spans)!=3:raise ValueError('spans_m 必须为[左边跨,主跨,右边跨]')
        c.update(left_side_span=number(spans[0],'左边跨',10,200),main_span=number(spans[1],'主跨',50,150),
                 right_side_span=number(spans[2],'右边跨',10,200),side_span_mode='manual')
    for k,v in c.items():
        if isinstance(GEOMETRY_DEFAULTS[k],str):continue
        if k in ('deck_elevation','longitudinal_slope'):continue
        number(v,k,0 if k in ('inner_margin','outer_margin','cross_slope','pavement_thickness') else .001,200)
    number(c['main_span'],'main_span',50,150)
    for k,max_length in {'designer_name':16,'student_id':32,'institution':44,'class_name':24,'supervisor':28,'drawing_date':10}.items():
        value=c[k]
        if not isinstance(value,str) or len(value)>max_length or any(ord(ch)<32 for ch in value):
            raise ValueError(k+f' 必须为不超过{max_length}字符的单行文字')
        c[k]=value.strip()
    if c['elevation_mode'] not in ('relative','absolute'):
        raise ValueError('elevation_mode 必须为 relative 或 absolute')
    number(c['deck_elevation'],'deck_elevation',-1000,10000)
    number(c['longitudinal_slope'],'longitudinal_slope',-.06,.06)
    if c['elevation_mode']=='absolute' and 'deck_elevation' not in supplied:
        raise ValueError('绝对高程模式必须明确提供deck_elevation，禁止补造工程高程')
    if isinstance(c['lanes'],bool) or c['lanes'] not in (2,4,6):
        raise ValueError('lanes 必须是总车道数2、4或6')
    c['lanes']=int(c['lanes'])
    layout='single' if c['lanes']==2 else 'separated'
    if c['layout'] not in ('auto',layout):
        raise ValueError('2车道采用single单幅双向，4/6车道采用separated分离两幅；也可使用auto')
    c['layout']=layout
    if 'project_name' not in supplied:
        c['project_name']=f'{c["lanes"]}车道'+('单幅双向' if layout=='single' else '分离式')+'连续箱梁课程设计'
    number(c['side_span_ratio'],'side_span_ratio',.5,.8)
    if c['side_span_mode']=='auto_ratio':
        derived=c['main_span']*c['side_span_ratio']
        if any(k in supplied and not math.isclose(c[k],derived,rel_tol=1e-9,abs_tol=1e-9)
               for k in ('left_side_span','right_side_span')):
            raise ValueError('自动模式中的边跨与比例不一致；独立边跨请改用manual')
        c['left_side_span']=c['right_side_span']=derived
    elif c['side_span_mode']!='manual':raise ValueError('side_span_mode 必须为 auto_ratio 或 manual')
    for k in ('left_side_span','right_side_span'):
        if not .4<=c[k]/c['main_span']<=.9:raise ValueError(k+' 与主跨比例须在0.4～0.9之间')
    # These are the original course generator's span-dependent starting values,
    # rather than fixed plate thicknesses for every span. Explicit values win.
    span=c['main_span']
    guesses={'top_thickness':.26+.0004*span,'bottom_mid':.24+.0004*span,
             'bottom_pier':.50+.002*span,'web_mid':.45+.001*span,'web_pier':.60+.002*span,
             'top_haunch_horizontal':.60+.001*span,'top_haunch_vertical':.20+.0005*span,
             'bottom_chamfer_horizontal':.50+.001*span,'bottom_chamfer_vertical':.25+.0005*span}
    # Wider three-lane decks use a course-design starting web width, shared
    # with the calculator. This is an initial guess, not a code coefficient.
    if c['lanes']==6:
        for k in ('web_mid','web_pier'):guesses[k]*=1.25
    for k,v in guesses.items():
        if k not in supplied:c[k]=round(v,2)
    text(c['project_name'],'project_name',60)
    if c['concrete'] not in {'C40','C45','C50','C55','C60'}:raise ValueError('不支持的混凝土等级')
    number(c['cross_slope'],'cross_slope',0,.06)
    number(c['segment_length'],'segment_length',2,8)
    limits={'height_reference_span':(40,150),'height_mid':(1.8,7),'height_pier':(2,12),
            'barrier_width':(.3,1),'deck_gap':(.2,5),'cantilever_width':(.8,3),
            'inner_margin':(0,4),'outer_margin':(0,4),'top_thickness':(.22,.7),
            'tip_thickness':(.15,.5),'top_haunch_horizontal':(.1,2),'top_haunch_vertical':(.05,.7),
            'bottom_chamfer_horizontal':(.1,1.5),'bottom_chamfer_vertical':(.05,.8),
            'bottom_mid':(.2,.8),'bottom_pier':(.25,1.5),'web_mid':(.3,1.2),'web_pier':(.35,1.5),
            'pier_height':(4,40),'pile_length':(5,60),'pavement_thickness':(0,.3)}
    for k,(lo,hi) in limits.items():number(c[k],k,lo,hi)
    number(c['lane_width'],'lane_width',3,4)
    number(c['height_curve_exponent'],'height_curve_exponent',1.2,2.5)
    if c['height_pier']<=c['height_mid']:raise ValueError('参考墩顶梁高必须大于参考跨中梁高')
    if c['bottom_pier']<c['bottom_mid'] or c['web_pier']<c['web_mid']:
        raise ValueError('墩顶底板和腹板厚度不可小于跨中')
    g=Geometry(c)
    if g.section(g.left_side)['h']<=g.section(g.left_side+g.main/2)['h']:
        raise ValueError('缩放后墩顶梁高须大于跨中构造下限1.8 m；请调整梁高参考值')
    if g.box_width<=2*max(c['web_mid'],c['web_pier']):raise ValueError('箱体净宽不足')
    for k in ('top_haunch_horizontal','bottom_chamfer_horizontal'):
        if 2*c[k]>=g.box_width-2*max(c['web_mid'],c['web_pier']):raise ValueError(k+' 导致倒角重叠')
    for i in range(101):g.section(g.length*i/100)
    supplied_drawing=data.get('drawing',{})
    keys(supplied_drawing,DRAWING_DEFAULTS,'drawing')
    d={**DRAWING_DEFAULTS,**supplied_drawing}
    if 'longitudinal_slope' in supplied_drawing and 'longitudinal_slope' in supplied and not math.isclose(d['longitudinal_slope'],c['longitudinal_slope'],abs_tol=1e-12):
        raise ValueError('bridge和drawing中的纵坡不一致')
    if 'longitudinal_slope' not in supplied_drawing:d['longitudinal_slope']=c['longitudinal_slope']
    else:c['longitudinal_slope']=d['longitudinal_slope']
    if not isinstance(d['sheets'],list) or not d['sheets'] or set(d['sheets'])-SHEETS or len(set(d['sheets']))!=len(d['sheets']):
        raise ValueError('sheets 必须是 general/midspan/pier 的非空且不重复列表')
    for k in ('barrier_height','bearing_height','zero_block_length','closure_length'):
        number(d[k],k,.05,20)
    if d['zero_block_length']+d['closure_length']>=c['main_span']/2:raise ValueError('0号块和合龙段长度不合理')
    number(d['longitudinal_slope'],'longitudinal_slope',-.06,.06)
    number(d['station_origin_m'],'station_origin_m',0,1000000)
    text(d['station_prefix'],'station_prefix',8)
    for k in ('show_segments','show_substructure'):
        if not isinstance(d[k],bool):raise ValueError(k+' 必须是布尔值')
    if not isinstance(d['notes'],list) or len(d['notes'])>4:raise ValueError('额外说明最多4行')
    d['notes']=[text(v,'notes',48) for v in d['notes']]
    commands=data.get('commands',[])
    if not isinstance(commands,list) or len(commands)>300:raise ValueError('commands 必须为列表，最多300条')
    for command in commands:
        if not isinstance(command,dict) or command.get('op') not in OPS:raise ValueError('不支持的绘图操作')
        op=command['op'];keys(command,{'op','sheet','view','role'} | OPS[op],'command')
        if command.get('sheet') not in d['sheets']:raise ValueError('command 引用了未生成的sheet')
        section_views={'single'} if g.deck_count==1 else {'left','right'}
        expected={'general':{'elevation','plan'},'midspan':section_views,'pier':section_views}
        if command.get('view') not in expected[command['sheet']]:raise ValueError('command.view 与sheet不匹配')
        if command.get('role','detail') not in ROLE_LAYERS:raise ValueError('role 不支持；字体和线宽由内置规范控制')
        for k in ('point','start','end','center'):
            if k in command:point(command[k],k)
        required={'line':{'start','end'},'polyline':{'points'},'circle':{'center','radius'},
                  'text':{'point','text'},'dimension':{'start','end','offset'},'leader':{'point','end','text'}}[op]
        if not required<=command.keys():raise ValueError(op+' 缺少必需字段')
        if op=='polyline':
            if not isinstance(command['points'],list) or not 2<=len(command['points'])<=2000:raise ValueError('polyline顶点数量不合理')
            for p in command['points']:point(p,'polyline.point')
            if command.get('closed') and len(command['points'])<3:raise ValueError('闭合多段线至少需要3点')
        for k in ('closed','vertical','numeric'):
            if k in command and not isinstance(command[k],bool):raise ValueError(k+' 必须为布尔值')
        if op=='circle':number(command['radius'],'radius',.001,100)
        if op=='dimension':number(command['offset'],'offset',-2000,2000)
        if op in ('text','leader'):text(command['text'],'command.text',48)
        if command.get('align','left') not in {'left','center','right'}:raise ValueError('不支持的对齐方式')
    prestress=data.get('prestress')
    if prestress is not None:
        keys(prestress,{'source','x','depth_from_top'},'prestress')
        text(prestress.get('source'),'prestress.source',200)
        xs,ys=prestress.get('x'),prestress.get('depth_from_top')
        if not isinstance(xs,list) or not isinstance(ys,list) or not 2<=len(xs)==len(ys)<=2000:raise ValueError('钢束线坐标必须等长且至少2点')
        for i,(x,y) in enumerate(zip(xs,ys)):
            number(x,'prestress.x',0,g.length);number(y,'prestress.depth',.001,g.section(x)['h']-.001)
            if i and x<=xs[i-1]:raise ValueError('钢束纵向坐标必须严格递增')
        if abs(xs[0])>1e-8 or abs(xs[-1]-g.length)>1e-8:raise ValueError('钢束线必须覆盖整桥支承长度')
    return {'schema':SCHEMA,'units':'m','bridge':c,'drawing':d,'commands':commands,'prestress':prestress}

def load(path):
    path=Path(path)
    if path.stat().st_size>1024*1024:raise ValueError('指令文件不能超过1 MB')
    return normalize(json.loads(path.read_text(encoding='utf-8-sig'),parse_constant=lambda v:(_ for _ in ()).throw(ValueError('无效数字：'+v))))

def from_result(path):
    data=json.loads(Path(path).read_text(encoding='utf-8-sig'))
    return from_result_data(data,Path(path).name)

def from_result_data(data,source='原桥梁生成器计算结果'):
    if not isinstance(data,dict) or 'input' not in data:raise ValueError('文件必须是生成器的设计结果.json')
    c={k:v for k,v in data['input'].items() if k in GEOMETRY_DEFAULTS}
    if c.get('side_span_mode')=='auto_ratio':
        c.pop('left_side_span',None);c.pop('right_side_span',None)
    command={'schema':SCHEMA,'units':'m','bridge':c}
    p=data.get('prestress',{}).get('profile')
    if p:command['prestress']={'source':'来自计算结果文件 '+source,
                              'x':p['x'],'depth_from_top':p['depth_from_top']}
    result=normalize(command)
    g=Geometry(result['bridge'])
    dims=data.get('geometry',{})
    for key,actual in [('width',g.width),('total_width',g.total_width),('deck_count',g.deck_count),
                       ('lanes_per_deck',g.lanes_per_deck),('height_mid',g.section(g.left_side+g.main/2)['h']),
                       ('height_pier',g.section(g.left_side)['h'])]:
        if key in dims and not math.isclose(dims[key],actual,rel_tol=1e-7,abs_tol=1e-7):
            raise ValueError('计算结果与输入几何不一致：'+key+'；禁止按不一致的数据出图')
    return result
