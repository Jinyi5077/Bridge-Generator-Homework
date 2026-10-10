"""Adapter boundary: transmit inputs and accepted design, never A's effects."""
import hashlib
import json
import uuid


def digest(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode('utf-8')).hexdigest()


def input_spec(result):
    p=result['prestress']['profile']; rr=result['structural_verification']['reinforcement']
    stages=[]
    for pier in result['construction_stages']['piers']:
        for row in pier['stages']:
            if row['stage_id'] in ('CLOSE','SERVICE'):continue
            stages.append(dict(pier_id=pier['pier_id'],stage_id=row['stage_id'],length_m=row['active_length_each_side_m'],activated_count=row['activated_tendons']))
    spec=dict(schema='crosscheck.input.1',run_id=uuid.uuid4().hex,input=result['input'],
              scheme=dict(x_m=p['x'],absolute_depth_m=p['depth_from_top'],active_counts=p['active_tendon_count'],anchors_m=p['jacking_region_anchors'],
                          reinforcement=dict(top_count=rr['top_bar_count'],bottom_count=rr['bottom_bar_count'],stirrup_spacing_mm=result['structural_verification']['checks']['shear']['stirrup']['spacing_mm']),stages=stages),
              queries=dict(x_m=result['analysis']['x'],side=[1 if i%2==0 else -1 for i in range(len(result['analysis']['x']))]))
    # JSON round-trip severs all references into the mutable main result.
    return json.loads(json.dumps(spec,allow_nan=False))


def main_hash(result):
    return digest({k:result[k] for k in ('version','input','analysis','reactions','prestress','construction_stages','structural_verification')})
