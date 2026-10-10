"""Three course sheets with engineering-style views and true mm dimensions."""
import math
import numpy as np
from .drafting import Sheet
from .geometry import Geometry
from .instructions import ROLE_LAYERS

NAMES={'general':'01_桥型总体布置图','midspan':'02_跨中横断面图','pier':'03_墩顶横断面图'}

def deck_centers(g):
    return [0.] if g.deck_count==1 else [-(g.width+g.c['deck_gap'])/2,(g.width+g.c['deck_gap'])/2]

def deck_label(g,deck):
    return (('单幅双向' if g.lanes_per_deck==2 else '单幅') if g.deck_count==1 else ('左幅' if deck==0 else '右幅'))+f'（{g.lanes_per_deck}车道）'

def choose_scale(options,condition):
    result=next((v for v in options if condition(v)),None)
    if result is None:raise ValueError('几何尺寸超出A3绘图模板可容纳范围；请检查梁高、板厚或下部示意参数')
    return result

def station(x, drawing):
    total=x+drawing['station_origin_m']
    km=int(total//1000);m=total-km*1000
    return f'{drawing["station_prefix"]}{km}+{m:07.3f}'

def groups(g,drawing,cfg):
    """Segment limits are geometry diagrams, not a construction calculation."""
    half_zero=drawing['zero_block_length']/2
    half_closure=drawing['closure_length']/2
    reach=g.main/2-half_closure
    points={0.,g.length,g.left_side+g.main/2-half_closure,g.left_side+g.main/2+half_closure}
    for pier in g.supports[1:3]:
        points.update([pier-half_zero,pier+half_zero])
        for sign in (-1,1):
            dist=half_zero
            while dist<reach-1e-8:
                points.add(pier+sign*dist)
                dist=min(dist+cfg['segment_length'],reach)
            points.add(pier+sign*reach)
    return sorted(x for x in points if 0<=x<=g.length)

def add_substructure(sc,g,c,d,pos):
    S=1000/sc.scale
    for j,x in enumerate(g.supports):
        h=g.section(x)['h'];top=-h-d['bearing_height']
        # A pair of bearings in plan is represented by one visible bearing in elevation.
        sc.rect(pos(x-.6,-h-d['bearing_height'])[0],pos(x,-h-d['bearing_height'])[1],1.2*S,d['bearing_height']*S,'B-DETAIL')
        if j in (0,3):
            height=min(c['pier_height']*.4,6.)
            side=-1 if j==0 else 1
            pts=[pos(x-1.5,top),pos(x+1.5,top),pos(x+1.5,top-height),pos(x-1.5,top-height)]
            sc.poly(pts,True,'B-PIER')
            # Backwall and abutment stem, distinct from the main piers.
            sc.line(pos(x+side*1.2,top),pos(x+side*1.2,.6),'B-PIER')
            sc.line(pos(x+side*1.8,top),pos(x+side*1.8,.6),'B-PIER')
            base=top-height
        else:
            base=top-c['pier_height']
            pts=[pos(x-2.4,top),pos(x+2.4,top),pos(x+1.5,top-2),pos(x+1.5,base),
                 pos(x-1.5,base),pos(x-1.5,top-2)]
            sc.poly(pts,True,'B-PIER')
        sc.rect(pos(x-4,base-2)[0],pos(x,base-2)[1],8*S,2*S,'B-PIER')
        for shift in (-2.5,0,2.5):
            sc.rect(pos(x+shift-.65,base-2-c['pile_length'])[0],
                    pos(x,base-2-c['pile_length'])[1],1.3*S,c['pile_length']*S,'B-PIER')
        sc.line(pos(x,4),pos(x,base-3-c['pile_length']),'B-CENTER')

def general(request):
    c,d=request['bridge'],request['drawing'];g=Geometry(c)
    depth=max(g.section(x)['h']+d['bearing_height']+c['pier_height']+2+c['pile_length'] for x in g.supports)
    grade=d['longitudinal_slope']
    scale=choose_scale((500,1000,2000),lambda v:g.length*1000/v<=334 and
                      (depth+abs(grade)*g.length)*1000/v<=70 and g.total_width*1000/v<=36)
    sc=Sheet('桥型总体布置图',scale,'01');S=1000/scale
    mid=215.25;x0=mid-g.length*S/2;baseline=235
    def pos(x,z=0):return (x0+x*S,baseline+(z+grade*(x-g.length/2))*S)
    sc.transforms={'elevation':pos,'plan':lambda x,y:(x0+x*S,117+y*S)}
    xx=np.unique(np.r_[np.linspace(0,g.length,601),g.supports]);hh=g.section(xx)['h']
    sc.poly([pos(x) for x in xx]+[pos(x,-h) for x,h in zip(xx[::-1],hh[::-1])],True)
    sc.line(pos(0,c['pavement_thickness']),pos(g.length,c['pavement_thickness']),'B-DETAIL')
    if request['prestress']:
        p=request['prestress'];sc.poly([pos(x,-z) for x,z in zip(p['x'],p['depth_from_top'])],layer='B-PRESTRESS')
        xm=g.left_side+g.main/2;dep=float(np.interp(xm,p['x'],p['depth_from_top']))
        sc.leader(pos(xm,-dep),(pos(xm)[0]+12,baseline-20),'等效钢束合力线')
    if d['show_segments']:
        for x in groups(g,d,c)[1:-1]:
            sc.line(pos(x),pos(x,-g.section(x)['h']),'B-DETAIL')
        for x in g.supports[1:3]:
            sc.text(pos(x)[0],pos(x)[1]+10,'0号块',3.5,'center')
        center=g.left_side+g.main/2
        sc.text(pos(center)[0],pos(center)[1]+10,'主跨合龙段',3.5,'center')
        if g.main*S>=80:
            for a,b in ((g.left_side,g.left_side+g.main/2),(g.left_side+g.main/2,g.supports[2])):
                sc.text(pos((a+b)/2)[0],pos((a+b)/2)[1]+10,'悬浇梁段',3.5,'center')
        sc.text(pos(g.left_side/3)[0],pos(g.left_side/3)[1]+10,'边跨现浇区',3.5,'center')
    # Longitudinal diaphragm outlines are intentionally hidden lines; no invented manhole sizes.
    for x in g.supports[1:3]:
        for delta in (-.75,.75):
            sc.line(pos(x+delta,-c['top_thickness']),pos(x+delta,-g.section(x+delta)['h']+c['bottom_pier']),'B-HIDDEN')
    if d['show_substructure']:add_substructure(sc,g,c,d,pos)
    else:
        for x in g.supports:sc.line(pos(x,3),pos(x,-g.section(x)['h']-4),'B-CENTER')
    for j,x in enumerate(g.supports):
        sc.text(pos(x)[0],165,('A0','P1','P2','A3')[j],3.5,'center',numeric=True)
        sc.text(pos(x)[0],158,station(x,d),3.5,'center',numeric=True)
        if j<3:sc.dim(pos(x),pos(g.supports[j+1]),254)
    sc.dim(pos(0),pos(g.length),264)
    sc.view_title(mid,278,'单幅立面图',scale)
    for x,off in ((g.left_side+g.main/2,7),(g.left_side,-9)):
        h=g.section(x)['h'];sc.dim(pos(x,-h),pos(x),pos(x)[0]+off,True)
    # Elevations are at the structural slab centre line, measured from the
    # user-selected datum at the full bridge midpoint. No terrain is invented.
    def elevation_mark(x,z=0,above=True):
        X,Y=pos(x,z);ey=Y+2 if above else Y-3
        sc.poly([(X,Y),(X-1.3,ey),(X+1.3,ey)],True,'B-DETAIL')
        sc.line((X-1.3,ey),(X+17,ey),'B-DETAIL')
        value=c['deck_elevation']+grade*(x-g.length/2)+z
        sc.text(X+3,ey+1,value.__format__('+.3f' if c['elevation_mode']=='relative' else '.3f'),3.5,numeric=True)
    for x in (*g.supports,g.left_side+g.main/2):elevation_mark(float(x))
    for x in g.supports[1:3]:elevation_mark(float(x),-float(g.section(x)['h']),False)
    low=math.floor((c['deck_elevation']-depth-abs(grade)*g.length/2)/10)*10
    high=math.ceil((c['deck_elevation']+abs(grade)*g.length/2)/10)*10
    for value in np.arange(low,high+.1,10):
        yy=baseline+(value-c['deck_elevation'])*S
        sc.line((25,yy),(28,yy),'B-DETAIL')
        sc.text(29,yy,value.__format__('g'),2.5,numeric=True)
    sc.line((25,baseline+(low-c['deck_elevation'])*S),(25,baseline+(high-c['deck_elevation'])*S),'B-DETAIL')
    sc.text(25,baseline+(low-c['deck_elevation'])*S-6,'高程(m)',2.5)
    py=117;centers=deck_centers(g)
    for deck,center in enumerate(centers):
        sc.rect(x0,py+(center-g.width/2)*S,g.length*S,g.width*S)
        for offset in (-g.box_width/2,g.box_width/2):
            sc.line((x0,py+(center+offset)*S),(x0+g.length*S,py+(center+offset)*S),'B-HIDDEN')
        sc.line((x0-3,py+center*S),(x0+g.length*S+3,py+center*S),'B-CENTER')
        mirror=-1 if g.deck_count==2 and deck==0 else 1
        lane_start=-g.width/2+c['barrier_width']+c['inner_margin']
        for lane in range(g.lanes_per_deck+1):
            offset=lane_start+lane*c['lane_width']
            sc.line((x0,py+(center+mirror*offset)*S),(x0+g.length*S,py+(center+mirror*offset)*S),'B-DETAIL')
        for lane in range(g.lanes_per_deck):
            # The two-lane single deck is bidirectional. The three-lane single
            # deck uses the same direction convention as one three-lane half.
            direction=(-1 if lane==0 else 1) if g.deck_count==1 and g.lanes_per_deck==2 else mirror
            x=x0+g.length*S*.72
            yy=py+(center+mirror*(lane_start+(lane+.5)*c['lane_width']))*S
            sc.line((x-6*direction,yy),(x+6*direction,yy),'B-DETAIL')
            sc.poly([(x+3*direction,yy+1.5),(x+6*direction,yy),(x+3*direction,yy-1.5)],layer='B-DETAIL')
    for x in g.supports:
        sc.line((x0+x*S,py-g.total_width*S/2-4),(x0+x*S,py+g.total_width*S/2+4),'B-CENTER')
    sc.dim((x0+g.length*S,py-g.total_width*S/2),(x0+g.length*S,py+g.total_width*S/2),x0+g.length*S+10,True)
    for label,x in [('A',g.left_side+g.main/2),('B',g.left_side)]:
        X=x0+x*S
        # Two short, heavy cutting marks as in the Word reference. The centre
        # line supplies the section location without a solid line across traffic.
        for sign in (-1,1):
            yy=py+sign*(g.total_width*S/2+4)
            sc.poly([(X,yy-sign*3),(X,yy),(X-3,yy)],layer='B-CUT')
            sc.text(X-4,yy,label,3.5,'right',numeric=True)
    plan_title=f'单幅{"双向" if g.lanes_per_deck==2 else ""}平面图（{g.lanes_per_deck}车道）' if g.deck_count==1 else f'分离式双幅平面图（每幅{g.lanes_per_deck}车道）'
    sc.view_title(mid,146,plan_title,scale)
    rows=[('跨径组合 / m',f'{g.left_side:g} + {g.main:g} + {g.right_side:g}'),
          ('单幅宽 / 全桥宽 / m',f'{g.width:g} / {g.total_width:g}'+('（含幅间净距）' if g.deck_count==2 else '（单幅）')),
          ('跨中 / 墩顶梁高 / m',f'{g.section(g.left_side+g.main/2)["h"]:.3f} / {g.section(g.left_side)["h"]:.3f}'),
          ('构造 / 混凝土','各幅单箱单室 / '+c['concrete']),
          ('曲线指数 / 纵坡',f'{c["height_curve_exponent"]:g} / {grade*100:g}%')]
    for i,(name,value) in enumerate(rows):
        y=85-i*8;sc.rect(27,y-3,205,8,'P-GRID',True);sc.line((115,y-3),(115,y+5),'P-GRID',True)
        sc.text(30,y,name,3.,paper=True);sc.text(118,y,value,3.,paper=True)
    notes=[
        '注：尺寸单位mm；桩号、梁高参数单位m。',
        f'1. {c["lanes"]}车道'+(f'单幅{"双向" if g.lanes_per_deck==2 else ""}，单箱单室。' if g.deck_count==1 else f'分离式，每幅{g.lanes_per_deck}车道、单箱单室。'),
        '2. 梁高、底板及腹板厚度随纵向位置变化。',
        '3. 节段线为悬浇分段示意；施工分段应另行确定。',
        '4. 横隔板虚线仅示位置；人孔和锚固细部另绘。',
        '5. 下部结构及支座为示意，不表示已完成详设。',
        ('6. 仅表示已提供的等效钢束合力线，不作孔道详图。' if request['prestress'] else '6. 未提供钢束坐标，未绘制钢束或配筋。'),
    ]+d['notes']
    for i,line in enumerate(notes):sc.text(245,96-i*4.3,line,2.5,paper=True)
    datum='相对高程' if c['elevation_mode']=='relative' else '用户输入的绝对高程'
    sc.text(27,41,datum+'：全桥中点结构顶板中心线为 '+f'{c["deck_elevation"]:.3f} m。',2.5,paper=True)
    sc.text(27,35,'高程标注为梁体控制点；下部示意不代替地形或基础设计。',2.5,paper=True)
    sc.text(27,29,'纵坡用于布置图；纵向计算模型仍采用水平平面梁。',2.5,paper=True)
    sc.frame({'input':c});return sc

def details(sc,c,sec):
    """Separate 1:20 viewports preserve real geometry in the enlarged details."""
    tt,tb,tw=sec['tt'],sec['tb'],sec['tw']
    uh,uv=c['top_haunch_horizontal'],c['top_haunch_vertical']
    bh,bv=c['bottom_chamfer_horizontal'],c['bottom_chamfer_vertical'];slope=c['cross_slope']
    upper_scale=choose_scale((20,50,100),lambda v:(uh+.35+tw)*1000/v<=90 and (tt+uv+.35)*1000/v<=50)
    view=sc.subview(upper_scale,(85,57),(110,72));S=1000/upper_scale
    cx=(uh+.35-tw)/2;cy=-(tt+uv+.35)/2
    def p(x,z):return ((x-cx)*S,(z-cy)*S)
    outer=[p(-tw,tw*slope),p(uh+.35,-slope*(uh+.35)),p(uh+.35,-tt-slope*(uh+.35)),
           p(uh,-tt-slope*uh),p(0,-tt-uv),p(0,-tt-uv-.35),p(-tw,-tt-uv-.35)]
    view.hatch(outer,[]);view.poly(outer,True,'B-CUT')
    view.dim(p(0,-tt-uv),p(uh,-tt-uv),p(0,-tt-uv-.35)[1]-7)
    view.line(p(0,-tt),p(uh,-tt),'B-DETAIL')
    view.dim(p(0,-tt),p(0,-tt-uv),p(uh+.35,0)[0]+7,True)
    sc.text(85,99,'上加腋详图  1:'+str(upper_scale),3.5,'center',paper=True)
    lower_scale=choose_scale((20,50,100),lambda v:(bh+.35+tw)*1000/v<=90 and (tb+bv+.25)*1000/v<=50)
    view=sc.subview(lower_scale,(209,57),(110,72));S=1000/lower_scale
    cx=(bh+.35-tw)/2;cy=(bv+.25-tb)/2
    def p(x,z):return ((x-cx)*S,(z-cy)*S)
    outer=[p(-tw,bv+.25),p(0,bv+.25),p(0,bv),p(bh,0),p(bh+.35,0),p(bh+.35,-tb),p(-tw,-tb)]
    view.hatch(outer,[]);view.poly(outer,True,'B-CUT')
    view.line(p(0,0),p(bh,0),'B-DETAIL')
    view.dim(p(0,0),p(bh,0),p(0,bv+.25)[1]+6)
    view.dim(p(0,0),p(0,bv),p(bh+.35,0)[0]+7,True)
    sc.text(209,99,'下倒角详图  1:'+str(lower_scale),3.5,'center',paper=True)

def cross_section(request,pier=False):
    c,d=request['bridge'],request['drawing'];g=Geometry(c)
    x=g.left_side if pier else g.left_side+g.main/2
    sec=g.section(x);h,tt,tb,tw=[sec[k] for k in ('h','tt','tb','tw')]
    scale=choose_scale((50,100,200),lambda v:g.total_width*1000/v<=322 and h*1000/v<=87)
    title='墩顶横断面图' if pier else '跨中横断面图'
    sc=Sheet(title,scale,'03' if pier else '02');S=1000/scale;cy=194 if scale==50 else 202;mid=215.25
    centers=deck_centers(g);B,b=g.width,g.box_width
    outer,holes=g.outlines(x);sc.transforms={}
    def whole(x,z=0):return (mid+x*S,cy+z*S)
    for deck,center in enumerate(centers):
        mirror=-1 if g.deck_count==2 and deck==0 else 1
        def cv(p,center=center,mirror=mirror):return whole(center+mirror*p[0],p[1])
        sc.transforms['single' if g.deck_count==1 else ('left' if deck==0 else 'right')]=lambda x,z,cv=cv:cv((x,z))
        sc.hatch([cv(p) for p in outer],[[cv(p) for p in ring] for ring in holes])
        sc.poly([cv(p) for p in outer],True,'B-CUT')
        for ring in holes:sc.poly([cv(p) for p in ring],True,'B-CUT')
        def top(local):return -c['cross_slope']*local
        # Pavement follows the same cross slope as the structural top slab.
        road_start=-B/2+c['barrier_width'];road_end=B/2-c['barrier_width']
        pavement=[(road_start,top(road_start)),(road_end,top(road_end)),
                  (road_end,top(road_end)+c['pavement_thickness']),
                  (road_start,top(road_start)+c['pavement_thickness'])]
        sc.poly([cv(p) for p in pavement],True,'B-DETAIL')
        for edge in (-1,1):
            lo=-B/2 if edge==-1 else B/2-c['barrier_width'];hi=lo+c['barrier_width']
            inset=c['barrier_width']*.2;H=d['barrier_height']
            pts=[(lo,top(lo)),(hi,top(hi)),(hi-inset,top(hi-inset)+H),(lo+inset,top(lo+inset)+H)]
            sc.poly([cv(p) for p in pts],True,'B-DETAIL')
        cx=whole(center)[0]
        sc.line((cx,243),(cx,cy-h*S-6),'B-CENTER')
        sc.text(cx,251,deck_label(g,deck),3.5,'center')
        sc.dim(cv((-B/2,0)),cv((B/2,0)),244)
        lane_start=road_start+c['inner_margin']
        limits=[-B/2,road_start]+[lane_start+i*c['lane_width'] for i in range(g.lanes_per_deck+1)]+[road_end,B/2]
        for index,(a,z) in enumerate(zip(limits[:-1],limits[1:])):
            if z-a>1e-8:
                rise=(2.0 if index%2 else 7.0) if (z-a)*S<8 else None
                sc.dim(cv((a,0)),cv((z,0)),233,text_rise=rise)
        for a,z in ((-B/2,-b/2),(-b/2,b/2),(b/2,B/2)):sc.dim(cv((a,0)),cv((z,0)),222)
        bottom=cy-h*S
        for a,z in zip([-b/2,-b/2+tw,b/2-tw],[-b/2+tw,b/2-tw,b/2]):
            sc.dim(cv((a,-h)),cv((z,-h)),bottom-6)
        sc.dim(cv((-b/2,-h)),cv((b/2,-h)),bottom-13)
        sc.dim(cv((0,-h)),cv((0,0)),cx+mirror*(B*S/2+10),True)
        sc.dim(cv((0,-h)),cv((0,-h+tb)),cx+mirror*16,True)
        sc.dim(cv((0,-tt)),cv((0,0)),cx-mirror*16,True)
        sc.text(cx,cy-h*S*.55,'单箱单室',3.5,'center')
        # Grade arrow follows the downward transverse slope of each mirrored deck.
        a=cv((-.9,.8));z=cv((.9,.8-c['cross_slope']*1.8))
        sc.line(a,z,'B-DETAIL');sign=mirror
        sc.poly([(z[0]-sign*2,z[1]+.7),z,(z[0]-sign*2,z[1]-.7)],layer='B-DETAIL')
        sc.text((a[0]+z[0])/2,(a[1]+z[1])/2+2,f'{c["cross_slope"]*100:g}%',2.5,'center',numeric=True)
        if request['prestress']:
            p=request['prestress'];dep=float(np.interp(x,p['x'],p['depth_from_top']))
            tip=cv((0,-dep));sc.circle(tip,.6,'B-PRESTRESS')
            # Keep the caption inside the clear void, away from slab outlines
            # and the lower width dimension chain.
            caption_y=bottom+tb*S+8 if dep>h*.5 else cy-tt*S-15
            sc.leader(tip,(tip[0]+mirror*15,caption_y),'等效合力点')
    if g.deck_count==2:
        sc.dim(whole(-g.total_width/2),whole(g.total_width/2),267)
        sc.dim(whole(-c['deck_gap']/2),whole(c['deck_gap']/2),257)
    label='B-B 墩顶加厚标准截面（横隔板外侧）' if pier else 'A-A 主跨跨中标准截面'
    sc.view_title(mid,280,label,scale)
    details(sc,c,sec)
    notes=[
        '注：尺寸单位mm；定位桩号 '+station(x,d)+'。',
        f'1. 顶板厚{tt*1000:.0f}，底板厚{tb*1000:.0f}，腹板厚{tw*1000:.0f}。',
        '2. 斜线为混凝土剖切区；空腔不填充。',
        f'3. '+('两幅镜像；' if g.deck_count==2 else '单幅；')+f'顶板横坡{c["cross_slope"]*100:g}%，梁底横向水平。',
        f'4. 铺装厚{c["pavement_thickness"]*1000:g}；护栏仅作外形示意。',
        '5. 局部详图仅放大构造，几何与主断面一致。',
        ('6. 横隔板人孔、预应力锚固和钢筋详图另绘。' if pier else '6. 本图为一般构造图；不表示逐根钢筋或孔道布置。'),
    ]+d['notes']
    for i,line in enumerate(notes):sc.text(275,97-i*4.3,line,2.5,paper=True)
    sc.frame({'input':c});return sc

def custom_commands(scene,commands):
    for cmd in commands:
        view=scene.transforms[cmd['view']]
        def p(key):return view(*cmd[key])
        def check(q):
            if not 20.5<=q[0]<=scene.W-10 or not 50<=q[1]<=scene.H-10:
                raise ValueError('自定义图元超出图框内容区；请调整坐标：'+str(cmd))
        for key in ('start','end','center','point'):
            if key in cmd:check(p(key))
        op=cmd['op'];layer=ROLE_LAYERS[cmd.get('role','detail')]
        if op=='line':scene.line(p('start'),p('end'),layer)
        elif op=='polyline':
            pts=[view(*pt) for pt in cmd['points']]
            for q in pts:check(q)
            scene.poly(pts,cmd.get('closed',False),layer)
        elif op=='circle':
            center=p('center');radius=cmd['radius']*1000/scene.scale
            check((center[0]-radius,center[1]-radius));check((center[0]+radius,center[1]+radius))
            scene.circle(center,radius,layer)
        elif op=='text':scene.text(*p('point'),cmd['text'],align=cmd.get('align','left'),numeric=cmd.get('numeric',False))
        elif op=='leader':scene.leader(p('point'),p('end'),cmd['text'])
        elif op=='dimension':
            vertical=cmd.get('vertical',False)
            offset=view(cmd['offset'],0)[0] if vertical else view(0,cmd['offset'])[1]
            a,b=p('start'),p('end')
            check((offset,a[1]) if vertical else (a[0],offset))
            scene.dim(a,b,offset,vertical)

def make_scenes(request):
    result=[]
    for key in request['drawing']['sheets']:
        scene=general(request) if key=='general' else cross_section(request,key=='pier')
        custom_commands(scene,[c for c in request['commands'] if c['sheet']==key])
        result.append((key,scene))
    return result
