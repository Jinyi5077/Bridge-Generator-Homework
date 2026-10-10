"""Standalone worker; executable and source mode use this same entry point."""
import json,os,sys
import time
from pathlib import Path
import numpy as np
from .contract import digest
from .kernel import calculate,plain


def convergence(coarse,fine):
    rows=[]
    for key in ('M_dead1','M_live_min','M_live_max','V_live_min','V_live_max','deflection_live_min','deflection_live_max','M_prestress_secondary','deflection_service_live_min'):
        a=np.asarray(coarse['analysis'][key]);b=np.asarray(fine['analysis'][key])
        scale=max(float(np.max(abs(b))),1e-10)
        error=float(np.max(abs(a-b)))/scale
        rows.append(dict(field=key,relative_change=error,limit=.001,status='PASS' if error<=.001 else 'FAIL'))
    a=coarse['traffic']['frequency_hz'];b=fine['traffic']['frequency_hz'];error=abs(a-b)/b
    rows.append(dict(field='frequency_hz',relative_change=error,limit=.002,status='PASS' if error<=.002 else 'FAIL'))
    return rows


def run(source,target):
    started=time.perf_counter();spec=json.loads(Path(source).read_text(encoding='utf-8'))
    if any(name.startswith('bridgegen') for name in sys.modules):
        raise RuntimeError('独立进程中检测到主引擎模块，拒绝执行复核')
    from .selftest import run as analytical_gates
    benchmarks=analytical_gates()
    coarse=calculate(spec,2000.);fine=calculate(spec,1000.);rows=convergence(coarse,fine)
    if any(r['status']=='FAIL' for r in rows):
        coarse=fine;fine=calculate(spec,500.);rows=convergence(coarse,fine)
    payload=dict(schema='crosscheck.output.1',run_id=spec['run_id'],input_hash=digest(spec),
                 seconds=time.perf_counter()-started,convergence=rows,result=fine,benchmarks=benchmarks,
                 worker_pid=os.getpid(),main_modules_loaded=[k for k in sys.modules if k.startswith('bridgegen')])
    Path(target).write_text(json.dumps(plain(payload),ensure_ascii=False,allow_nan=False),encoding='utf-8')
    return payload
