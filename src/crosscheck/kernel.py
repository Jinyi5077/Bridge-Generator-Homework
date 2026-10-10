"""Independent calculation entry point; receives inputs and accepted design only."""
import math
import numpy as np
from .section import SectionModel
from .force import ForceBeam, quadrature
from . import rules


def plain(obj):
    if isinstance(obj,np.ndarray): return plain(obj.tolist())
    if isinstance(obj,np.generic): return plain(obj.item())
    if isinstance(obj,float) and not math.isfinite(obj): raise ValueError('复核产生非有限数值')
    if isinstance(obj,dict): return {k:plain(v) for k,v in obj.items()}
    if isinstance(obj,(list,tuple)): return [plain(v) for v in obj]
    return obj


def tendon(model, scheme):
    """Losses for the fixed equivalent scheme, not a new tendon design."""
    c=model.c; px=np.array(scheme['x_m'])*1000
    sec=model.array(px);depth=np.array(scheme['absolute_depth_m'])*1000
    e=depth-sec['y']
    # Physical ordinate controls tendon angle. Eccentricity is relative to a
    # moving centroid and must not be differentiated to obtain physical slope.
    angle=np.arctan(np.gradient(depth,px))
    anchors=np.array(scheme['anchors_m'])*1000
    sj=c['strand_fpk_mpa']*c['jacking_stress_ratio'];sf=np.zeros_like(px)
    for start,end in zip(anchors[:-1],anchors[1:]):
        ids=np.flatnonzero((px>=start-1e-5)&(px<=end+1e-5))
        if len(ids)<2: raise ValueError('张拉分区缺少节点')
        turns=np.r_[0.,np.cumsum(abs(np.diff(angle[ids])))]
        left=sj*np.exp(-c['friction_mu']*turns-c['wobble_k_per_m']*(px[ids]-start)/1000)
        right=sj*np.exp(-c['friction_mu']*(turns[-1]-turns)-c['wobble_k_per_m']*(end-px[ids])/1000)
        sf[ids]=np.maximum(sf[ids],np.maximum(left,right))
    anch_loss=c['strand_E_mpa']*c['anchorage_slip_mm']/max(np.diff(anchors))
    raw_anchor=sf-anch_loss;sa=np.maximum(raw_anchor,.25*sj)
    si=sa*(1-c['elastic_shortening_ratio'])
    raw_eff=si-c['strand_E_mpa']*c['shrinkage_strain']-sj*(c['creep_loss_ratio']+c['relaxation_loss_ratio'])
    se=np.maximum(raw_eff,.20*sj)
    counts=np.array(scheme['active_counts'])
    if np.any(counts < 1) or np.any(counts != np.round(counts)): raise ValueError('钢束数量必须为正整数')
    area=counts*c['strands_per_tendon']*c['strand_area_mm2']
    return dict(x=px,e=e,depth=depth,area=area,immediate=si*area,effective=se*area,
                sigma_friction=sf,sigma_immediate=si,sigma_effective=se,
                floor_used=bool(np.any(raw_anchor < .25*sj)|np.any(raw_eff < .20*sj)))


def capacity(model,x,sec,upper,steel,depth,ap):
    c=model.c;fcd=rules.CONCRETE[c['concrete']][3]
    ys=sec['bottom']-max(80.,c['prestress_cover']*650) if upper else sec['top']+max(80.,c['prestress_cover']*650)
    tp=rules.FPD*ap if (depth>sec['y'] if upper else depth<sec['y']) else 0.
    ts=rules.FSD*steel;target=ts+tp
    lo,hi=0.,sec['bottom']-sec['top']
    if fcd*sec['A'] < target: return 0.,1.
    for _ in range(35):
        mid=(lo+hi)/2
        if fcd*model.compressed(x,mid,upper)[0]<target:lo=mid
        else:hi=mid
    _,yc=model.compressed(x,hi,upper)
    cap=ts*abs(ys-yc)+tp*abs(depth-yc)
    fy=(ts*ys+tp*depth)/target
    edge=sec['top'] if upper else sec['bottom']
    return cap/1e6,hi/max(abs(fy-edge),1e-8)


def calculate(spec, step=2000.):
    if spec.get('schema')!='crosscheck.input.1': raise ValueError('复核输入版本无效')
    if set(spec)-{'schema','run_id','input','scheme','queries'}: raise ValueError('复核内核拒绝未授权结果字段')
    c=spec['input'];scheme=spec['scheme'];model=SectionModel(c)
    if not 50<=c['main_span']<=220 or c['lanes'] not in (2,3,4,6): raise ValueError('复核参数范围无效')
    if c['rebar_grade']!='HRB400':raise ValueError('复核不支持该钢筋等级')
    E,fck,ftk,fcd,ftd,fcu=rules.CONCRETE[c['concrete']]
    x=np.array(spec['queries']['x_m'])*1000;sides=np.array(spec['queries']['side'])
    own=np.unique(np.concatenate([np.linspace(a,b,41) for a,b in zip(model.supports[:-1],model.supports[1:])]))
    # Compare the requested coordinates, then also inspect an independent grid.
    allx=np.r_[x,own];allside=np.r_[sides,np.ones(len(own))];n=len(x)
    sec=model.array(allx)
    beam=ForceBeam(model.supports,lambda t:E*model.array(t)['I'],step,
                   extra_breaks=[(model.supports[1]+model.supports[2])/2])
    q1=lambda t:model.array(t)['A']*c['concrete_weight']*1e-6
    q2=(model.B-2000*c['barrier_width'])*c['pavement_thickness']*c['pavement_weight']/1000+c['barrier_line_load']+c['other_dead_load']
    g1=beam.distributed(allx,q1,allside);g2=beam.distributed(allx,lambda t:np.full_like(t,q2),allside)
    freq=beam.frequency(lambda t:(q1(t)+q2)/9806.65,step=6000.)
    mu=rules.impact(freq)
    lane=max(i*rules.LANE_REDUCTION[i] for i in range(1,model.lanes+1))
    longitudinal=rules.longitudinal(np.max(np.diff(model.supports)))
    # Moving-load integration includes section/support cuts; point extrema are
    # sampled on both sides of each cut. These are independent load positions.
    cuts=np.unique(np.r_[model.supports,allx]);lx,lw=quadrature(cuts,step,4)
    eps=.01
    endpoint=np.unique(np.clip(np.r_[cuts,cuts-eps,cuts+eps],0,beam.L))
    loads=np.r_[lx,endpoint];weights=np.r_[lw,np.zeros(len(endpoint))]
    il=beam.influence(allx,loads,allside)
    a=dict(x=allx/1000,height=sec['h']/1000,area=sec['A']/1e6,inertia=sec['I']/1e12,
           section_modulus_top=sec['Wt']/1e9,section_modulus_bottom=sec['Wb']/1e9)
    live={};trace={};reactions={}
    conversions={'M':1e6,'V':1000.,'W':-1000.,'R':1000.}
    for kind,eta in il.items():
        pk=rules.PK*(rules.SHEAR_POINT_FACTOR if kind in ('V','R') else 1.)
        pos=np.maximum(eta,0)@weights;neg=np.minimum(eta,0)@weights
        high=(rules.QK*pos+pk*np.maximum(eta.max(axis=1),0))*lane*longitudinal
        low=(rules.QK*neg+pk*np.minimum(eta.min(axis=1),0))*lane*longitudinal
        factor=conversions[kind]
        if factor<0:lo,hi=high/factor,low/factor
        else:lo,hi=low/factor,high/factor
        live[kind]=(lo,hi)
        prefix='deflection' if kind=='W' else kind
        dest=reactions if kind=='R' else a
        dest[prefix+'_dead1']=g1[kind]/factor;dest[prefix+'_dead2']=g2[kind]/factor
        dest[prefix+'_dead']=(g1[kind]+g2[kind])/factor
        dest[prefix+'_live_min']=lo;dest[prefix+'_live_max']=hi
        trace[kind]=dict(positive_area=pos,negative_area=neg,eta_max=eta.max(axis=1),eta_min=eta.min(axis=1))
        for name,(gammas,qf,impact,importance) in rules.COMBINATIONS.items():
            values=[]
            for g_1 in gammas:
                for g_2 in gammas:
                    for l in (lo,hi):
                        values.append((g_1*g1[kind]/factor+g_2*g2[kind]/factor+qf*(1+mu if impact else 1)*l)*(c['importance_factor'] if importance else 1))
            dest[prefix+'_'+name+'_min']=np.min(values,axis=0)
            dest[prefix+'_'+name+'_max']=np.max(values,axis=0)
    p=tendon(model,scheme);sx=p['x']
    interp=lambda key:np.interp(allx,sx,p[key])
    e=interp('e');pi=interp('immediate');pe=interp('effective');ap=interp('area')
    pri=-p['immediate']*p['e'];pre=-p['effective']*p['e']
    imm=beam.initial_moment(allx,lambda t:np.interp(t,sx,pri))
    eff=beam.initial_moment(allx,lambda t:np.interp(t,sx,pre))
    a.update(tendon_eccentricity=e/1000,prestress_force_immediate=pi/1000,
             prestress_force_effective=pe/1000,prestress_area_active_mm2=ap,
             M_prestress_primary=eff['primary']/1e6,M_prestress_secondary=eff['secondary']/1e6,
             M_prestress_total=eff['total']/1e6,deflection_prestress=-eff['W']/1000)
    def stresses(force, secondary, external):
        m=external*1e6+secondary-force*e
        return force/sec['A']+m/sec['Wt'],force/sec['A']-m/sec['Wb']
    a['stress_top_transfer'],a['stress_bottom_transfer']=stresses(pi,imm['secondary'],a['M_dead1'])
    for combo in ('standard','frequent','quasi'):
        for branch in ('min','max'):
            a['stress_top_'+combo+'_'+branch],a['stress_bottom_'+combo+'_'+branch]=stresses(pe,eff['secondary'],a['M_'+combo+'_'+branch])
    reinforcement=scheme['reinforcement'];bar=math.pi*c['longitudinal_bar_diameter_mm']**2/4
    area_top=reinforcement['top_count']*bar;area_bottom=reinforcement['bottom_count']*bar
    caps={True:[],False:[]};ratios={True:[],False:[]}
    for i,t in enumerate(allx):
        row={k:v[i] for k,v in sec.items()}
        for upper,steel in ((True,area_bottom),(False,area_top)):
            cap,ratio=capacity(model,t,row,upper,steel,interp('depth')[i],ap[i])
            caps[upper].append(cap);ratios[upper].append(ratio)
    for upper,name in ((True,'positive'),(False,'negative')):
        cap=np.array(caps[upper]);demand=np.maximum(a['M_uls_max'],0) if upper else np.maximum(-a['M_uls_min'],0)
        a['flexural_capacity_'+name]=cap
        # Positive demand with zero capacity is an explicit design failure.
        a['flexural_utilization_'+name]=np.divide(demand,cap,out=np.where(demand>1e-6,1e12,0.),where=cap>1e-9)
    b=2*sec['tw'];h0=sec['bottom']-sec['top']-max(100.,c['prestress_cover']*650)
    asv=2*c['stirrup_legs_per_web']*math.pi*c['stirrup_diameter_mm']**2/4
    spacing=reinforcement['stirrup_spacing_mm'];rho_sv=asv/(spacing*b)
    rho=np.minimum(100*(area_top+area_bottom+ap)/(b*h0),2.5)
    v_cs=.45*.9*1.1*b*h0*np.sqrt((2+.6*rho)*math.sqrt(fcu)*rho_sv*rules.FSD)
    angle=np.arctan(np.gradient(p['depth'],sx));vertical=.75*rules.FPD*ap*np.sin(np.interp(allx,sx,angle))
    # Favorable tendon vertical component depends on the shear direction.
    vmin=a['V_uls_min']*1000;vmax=a['V_uls_max']*1000
    effective_demand=np.maximum(abs(vmin-vertical),abs(vmax-vertical))
    a['shear_capacity']=v_cs/1000
    a['shear_utilization']=effective_demand/np.maximum(v_cs,1e-9)
    web=.51*math.sqrt(fcu)*b*h0
    a['web_dimension_utilization']=np.maximum(abs(vmin),abs(vmax))/web
    vfreq=np.maximum(abs(a['V_frequent_min']),abs(a['V_frequent_max']))*1000
    tau=vfreq*sec['Q']/(sec['I']*sec['b']);sigma=pe/sec['A']
    a['principal_tensile_stress_frequent']=np.sqrt((sigma/2)**2+tau**2)-sigma/2
    a['web_shear_stress_frequent']=tau
    edge=max(0.,max(float(np.max(-a[k])) for k in a if k.startswith('stress_') and '_frequent_' in k))
    comp=max(float(np.max(a[k])) for k in a if k.startswith('stress_') and '_standard_' in k)
    # Independent transformed uncracked section. EcI0 accounts for embedded
    # rebar and strand via (n-1)A and centroid shift; local steel I is neglected.
    cover=max(80.,c['prestress_cover']*650)
    def i0(t):
        s=model.array(t);d=np.interp(t,sx,p['depth']);pa=np.interp(t,sx,p['area'])
        nt=200000/E-1;np_=c['strand_E_mpa']/E-1
        yt=s['top']+cover;yb=s['bottom']-cover
        total=s['A']+nt*(area_top+area_bottom)+np_*pa
        y0=(s['A']*s['y']+nt*area_top*yt+nt*area_bottom*yb+np_*pa*d)/total
        return s['I']+s['A']*(s['y']-y0)**2+nt*(area_top*(yt-y0)**2+area_bottom*(yb-y0)**2)+np_*pa*(d-y0)**2
    service_beam=ForceBeam(model.supports,lambda t:.95*E*i0(t),step,extra_breaks=sx)
    wil=service_beam.influence(allx,loads,allside)['W']
    slo=(rules.QK*(np.maximum(wil,0)@weights)+rules.PK*np.maximum(wil.max(axis=1),0))*lane/-1000
    shi=(rules.QK*(np.minimum(wil,0)@weights)+rules.PK*np.minimum(wil.min(axis=1),0))*lane/-1000
    eta_theta=1.45-(fcu-40)*.10/40
    a['deflection_service_live_min']=slo*longitudinal*.7*eta_theta
    a['deflection_service_live_max']=shi*longitudinal*.7*eta_theta
    span_checks=[]
    for num,(start,end) in enumerate(zip(model.supports[:-1],model.supports[1:]),1):
        mask=(allx>=start)&(allx<=end)
        mm=max(float(np.max(abs(a['deflection_service_live_min'][mask]))),float(np.max(abs(a['deflection_service_live_max'][mask]))))*1000
        span_checks.append(dict(span=num,maximum_mm=mm,limit_mm=(end-start)/600,utilization=mm/((end-start)/600)))
    checks=dict(
        flexure=all(np.max(a['flexural_utilization_'+name])<=1 and np.all(np.array(ratios[upper])[np.maximum(a['M_uls_max'],0)>1e-6 if upper else np.maximum(-a['M_uls_min'],0)>1e-6]<=.38+1e-9) for upper,name in ((True,'positive'),(False,'negative'))),
        shear=bool(np.max(a['shear_utilization'])<=1 and np.max(a['web_dimension_utilization'])<=1),
        crack_resistance=bool(edge<=(0 if c['prestress_class']=='full' else .5*ftk)+1e-9 and np.max(a['principal_tensile_stress_frequent'])<=(.4 if c['prestress_class']=='full' else .5)*ftk),
        concrete_stress=comp<=.5*fck,
        deflection=all(r['utilization']<=1 for r in span_checks))
    stages=[]
    for row in scheme['stages']:
        pier=model.supports[1 if row['pier_id']=='P1' else 2];direction=1 if row['pier_id']=='P1' else -1
        length=row['length_m']*1000
        s,w=quadrature([0.,length],min(step,1000.),6);q=q1(pier+direction*s)
        Ptrav=c['form_traveler_load']*1000
        M=-np.sum(w*q*s)-Ptrav*length;V=np.sum(w*q)+Ptrav
        ts,tw=quadrature([0.,length],min(step,1000.),6)
        tailmoment=-(np.maximum(s[None,:]-ts[:,None],0)@(w*q))-Ptrav*(length-ts)
        defl=np.sum(tw*tailmoment*(-(length-ts))/(E*model.array(pier+direction*ts)['I']))
        seci=model.at(pier);pp=np.interp(pier,sx,p['immediate'])
        total_count=np.interp(pier,sx,scheme['active_counts']);pf=pp/total_count*row['activated_count'];ep=np.interp(pier,sx,p['e'])
        top=pf/seci['A']+(M-pf*ep)/seci['Wt'];bottom=pf/seci['A']-(M-pf*ep)/seci['Wb']
        stages.append(dict(pier_id=row['pier_id'],stage_id=row['stage_id'],external_root_moment_knm=M/1e6,root_shear_kn=V/1000,tip_deflection_mm=defl,prestress_force_kn=pf/1000,top_stress_mpa=top,bottom_stress_mpa=bottom))
    checks['temporary_concrete_stress']=all(max(s['top_stress_mpa'],s['bottom_stress_mpa'])<=.8*fck for s in stages)
    p_sec=model.array(model.supports)
    compat=max(abs(imm['compatibility']),abs(eff['compatibility']))
    return plain(dict(analysis={k:v[:n] for k,v in a.items()},own_grid={k:v[n:] for k,v in a.items()},
                      reactions=reactions,traffic=dict(frequency_hz=freq,impact=mu,effective_lanes=lane,longitudinal_factor=longitudinal,qk=rules.QK,pk=rules.PK/1000),
                      geometry=dict(width=model.B/1000,deck_count=model.decks,lanes_per_deck=model.lanes,supports=model.supports/1000),
                      loads=dict(dead2=q2,dead1_weight=float(np.sum(q1(beam.qx)*beam.qw)/1000)),
                      stages=stages,checks=checks,span_checks=span_checks,
                      numerical=dict(force_balance_kn=max(abs(g1['balance']),abs(g2['balance']))/1000,compatibility_mm=compat,condition=beam.condition),
                      tendon=dict(sigma_friction=p['sigma_friction'],sigma_immediate=p['sigma_immediate'],sigma_effective=p['sigma_effective'],floor_used=p['floor_used']),
                      sources=rules.SOURCES,step_mm=step))
