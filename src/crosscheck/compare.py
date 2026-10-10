"""The comparator can read A and B; the calculation kernel cannot read A."""
import numpy as np


def compare_array(field,a,b,unit,pass_rel,fail_rel,absolute,x=None):
    try:
        a=np.asarray(a,dtype=float);b=np.asarray(b,dtype=float)
        if a.shape!=b.shape or a.size==0 or not np.all(np.isfinite(a)) or not np.all(np.isfinite(b)):
            raise ValueError('维度不一致、空值或非有限数值')
        delta=abs(a-b);scale=np.maximum(abs(a),abs(b))
        pass_bound=absolute+pass_rel*scale;fail_bound=3*absolute+fail_rel*scale
        j=int(np.argmax(delta/np.maximum(pass_bound,1e-30)))
        status='FAIL' if np.any(delta>fail_bound) else ('WARN' if np.any(delta>pass_bound) else 'PASS')
        return dict(field=field,status=status,unit=unit,main=float(a.flat[j]),independent=float(b.flat[j]),
                    absolute_error=float(delta.flat[j]),relative_error=float(delta.flat[j]/max(scale.flat[j],1e-30)),
                    x_m=float(x[j]) if x is not None else None,index=j,
                    pass_relative=pass_rel,fail_relative=fail_rel,absolute_tolerance=absolute,
                    pass_limit_at_control=float(pass_bound.flat[j]),fail_limit_at_control=float(fail_bound.flat[j]))
    except (TypeError,ValueError) as exc:return dict(field=field,status='ERROR',message=str(exc),unit=unit)


def compare(main,b):
    a=main['analysis'];ind=b['analysis'];x=a['x'];rows=[]
    for key in ('height','area','inertia','section_modulus_top','section_modulus_bottom'):
        rows.append(compare_array(key,a.get(key),ind.get(key),{'height':'m','area':'m²','inertia':'m⁴'}.get(key,'m³'),.0005,.002,1e-10,x))
    required=[]
    for prefix in ('M','V','deflection'):
        required += [prefix+'_'+s for s in ('dead1','dead2','dead','live_min','live_max')]
        required += [prefix+'_'+combo+'_'+side for combo in ('uls','standard','frequent','quasi') for side in ('min','max')]
    required += ['prestress_force_immediate','prestress_force_effective','M_prestress_primary','M_prestress_secondary','M_prestress_total','deflection_prestress',
                 'deflection_service_live_min','deflection_service_live_max','stress_top_transfer','stress_bottom_transfer',
                 'flexural_capacity_positive','flexural_capacity_negative','flexural_utilization_positive','flexural_utilization_negative',
                 'shear_capacity','shear_utilization','web_dimension_utilization','principal_tensile_stress_frequent','web_shear_stress_frequent']
    required += [f'stress_{edge}_{combo}_{side}' for edge in ('top','bottom') for combo in ('standard','frequent','quasi') for side in ('min','max')]
    for key in sorted(set(required)):
        if key.startswith('M_') or key.startswith('flexural_capacity'):
            unit,ab='kN·m',1.;pr,fr=(.005,.02) if '_dead' in key else (.01,.03)
        elif key.startswith('V_') or key=='shear_capacity':unit,ab,pr,fr='kN',.1,.01,.03
        elif key.startswith('deflection'):unit,ab,pr,fr='m',.00005,.01,.03
        elif key.startswith('stress_') or key.endswith('_stress_frequent'):unit,ab,pr,fr='MPa',.02,.01,.03
        elif key.startswith('prestress_force'):unit,ab,pr,fr='kN',.1,.01,.03
        elif key.endswith('utilization') or '_utilization_' in key:unit,ab,pr,fr='1',.001,.01,.03
        else:continue
        rows.append(compare_array(key,a.get(key),ind.get(key),unit,pr,fr,ab,x))
    for key,value in b['reactions'].items():
        name=key.removeprefix('R_')
        rows.append(compare_array('reaction.'+name,main['reactions'].get(name),value,'kN',.005 if name.startswith('dead') else .01,.03,.1,main['reactions']['x']))
    for key in ('frequency_hz','impact','effective_lanes','qk','pk'):
        rows.append(compare_array('traffic.'+key,[main['loads']['traffic'].get(key)],[b['traffic'][key]],'Hz' if key=='frequency_hz' else '1',.01,.03,1e-8))
    for key in ('width','deck_count','lanes_per_deck'):
        rows.append(compare_array('geometry.'+key,[main['geometry'].get(key)],[b['geometry'][key]],'m' if key=='width' else '1',0,0,1e-8))
    rows.append(compare_array('dead2',[main['loads']['dead2']],[b['loads']['dead2']],'kN/m',.0005,.002,1e-8))
    for key in ('sigma_immediate','sigma_effective'):
        rows.append(compare_array('loss.'+key,main['prestress']['profile'].get(key),b['tendon'][key],'MPa',.01,.03,.02,main['prestress']['profile']['x']))
    ar={(p['pier_id'],r['stage_id']):r for p in main['construction_stages']['piers'] for r in p['stages']}
    for row in b['stages']:
        ident=(row['pier_id'],row['stage_id']);ref=ar.get(ident,{})
        for key in ('external_root_moment_knm','root_shear_kn','tip_deflection_mm','prestress_force_kn','top_stress_mpa','bottom_stress_mpa'):
            unit,ab=('kN·m',1.) if 'moment' in key else (('MPa',.02) if 'stress' in key else (('mm',.05) if 'deflection' in key else ('kN',.1)))
            rows.append(compare_array('.'.join((*ident,key)),[ref.get(key)],[row[key]],unit,.01,.03,ab))
    return rows
