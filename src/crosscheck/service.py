"""Process isolation, provenance, honest statuses and offline report export."""
import html
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from .contract import input_spec,digest,main_hash
from .compare import compare

LABELS={'PASS':'通过','WARN':'偏差需关注','FAIL':'不通过','ERROR':'执行异常','PARTIAL':'部分覆盖','CONSISTENT_WITHIN_SCOPE':'已覆盖项目一致','NEEDS_REVIEW':'存在偏差或方案不满足限值，需检查'}


def rule_audit(main,b):
    c=main['input'];rows=[]
    def add(id,status,text):rows.append(dict(id=id,status=status,message=text))
    deflection=main['structural_verification']['checks']['deflection']
    add('DEFLECTION','PASS' if deflection.get('rule_version')=='frequent_no_impact_eta_theta_B0' else 'FAIL',
        '挠度采用频遇活载、不含冲击、长期系数、0.95EcI0刚度；I0按最终等效钢筋方案计算。')
    add('TENDON_ANGLE','PASS' if main['prestress'].get('angle_basis')=='absolute_depth' else 'FAIL',
        '钢束转角须由实际钢束深度求导，不能由相对变化形心的偏心距求导。')
    add('STRAND_GRADE','PASS' if abs(c['strand_fpk_mpa']-1860)<1e-8 else 'FAIL',
        '本版承载力表按1860级钢绞线；其他强度等级不允许沿用同一设计强度宣称已核对。')
    add('LOSS_FLOOR','WARN' if b['tendon']['floor_used'] else 'PASS',
        '损失应力下限截断已触发，需检查损失假设。' if b['tendon']['floor_used'] else '损失应力下限截断未触发。')
    add('LOSS_HISTORY','PARTIAL','收缩、徐变、松弛采用输入的课程简化参数；未验证逐龄期耦合模型。')
    add('CONSTRUCTION_HISTORY','PARTIAL','独立计算P1/P2静定悬臂；合龙与成桥记录属于成桥状态，未建立节段激活、合龙锁定及全历史继承。')
    add('SHEAR_DIRECTION','PASS' if main['structural_verification']['checks']['shear'].get('tendon_direction_checked') else 'FAIL',
        '抗剪按剪力两分支分别计入有符号的钢束竖向分量。')
    return rows


def export_report(report,folder):
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    (folder/'交叉复核报告.json').write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    esc=lambda t:html.escape(str(t))
    rows=report.get('comparisons',[])
    table=''.join('<tr class="'+r['status'].lower()+'"><td>'+esc(r['field'])+'</td><td>'+esc(LABELS.get(r['status'],r['status']))+'</td><td>'+esc(r.get('x_m','—'))+'</td><td>'+esc(r.get('main','—'))+'</td><td>'+esc(r.get('independent','—'))+'</td><td>'+esc(r.get('absolute_error',r.get('message','—')))+'</td><td>'+esc(r.get('unit',''))+'</td></tr>' for r in rows)
    rules=''.join('<li><b>'+esc(r['id'])+' · '+esc(LABELS.get(r['status'],r['status']))+'</b>：'+esc(r['message'])+'</li>' for r in report.get('rules',[]))
    checks=''.join('<li>'+esc(k)+'：'+('通过' if v else '不通过')+'</li>' for k,v in report.get('independent_checks',{}).items())
    conv=''.join('<li>'+esc(r['field'])+'：变化 '+format(r['relative_change']*100,'.5f')+'%，限值 '+format(r['limit']*100,'.2f')+'% · '+r['status']+'</li>' for r in report.get('convergence',[]))
    doc='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>内置交叉复核报告</title><style>
    body{font:15px/1.7 "宋体",SimSun,serif;color:#193c48;background:#fff0d6;margin:32px auto;max-width:1250px;padding:0 20px}h1,h2{font-family:"Microsoft YaHei",sans-serif}section{background:white;border-radius:12px;padding:22px;margin:18px 0}table{border-collapse:collapse;width:100%;font:13px "Times New Roman",SimSun,serif}td,th{border:1px solid #c8d5d9;padding:7px;text-align:left;word-break:break-all}th{background:#48c6f0}.fail,.error{background:#ffd9c5}.warn{background:#fff0d6}code{overflow-wrap:anywhere}.banner{border-left:6px solid #ff8a3d}button{padding:8px;margin-bottom:15px}@media print{body{background:white;margin:0}.hide{display:none}}
    </style><h1>内置交叉验证 · '''+esc(report['status'])+'''</h1><section class="banner"><p>'''+esc(report['message'])+'''</p><p>主程序：位移法有限元；独立程序：释放内支点的力法＋虚功积分＋柔度特征值。统一物理参数、固定最终钢束与钢筋方案。</p><p>覆盖范围：纵向平面梁、简化预应力、静定悬臂与具名截面验算。横向、空间、局部、下部结构、逐龄期和合龙全过程未验证。</p></section><section><h2>版本、快照与执行</h2><pre>'''+esc(json.dumps(report.get('provenance',{}),ensure_ascii=False,indent=2))+'''</pre><p>执行：'''+esc(report.get('execution_status'))+'；数值：'+esc(report.get('numerical_status'))+'；规则：'+esc(report.get('rule_status'))+'；方案：'+esc(report.get('design_status'))+'；覆盖：'+esc(report.get('coverage_status'))+'''</p></section><section><h2>规则检查</h2><ul>'''+rules+'''</ul><h2>固定方案的独立验算</h2><ul>'''+checks+'''</ul><h2>独立网格收敛</h2><ul>'''+conv+'''</ul></section><section><h2>逐项差异</h2><p>判据：绝对误差 ≤ 绝对容差＋相对容差×max(|A|,|B|)。WARN超过通过阈值，FAIL超过失败阈值；近零值按绝对容差判断。阈值、控制点和两侧剪力标记见JSON。</p><button class="hide" onclick="document.querySelectorAll('tbody tr').forEach(r=>r.hidden=this.dataset.on!=='1' &amp;&amp; r.className==='pass');this.dataset.on=this.dataset.on==='1'?'0':'1'">切换显示差异</button><div style="overflow:auto"><table><thead><tr><th>项目</th><th>状态</th><th>x/m</th><th>主程序</th><th>独立程序</th><th>绝对差</th><th>单位</th></tr></thead><tbody>'''+table+'''</tbody></table></div></section></html>'''
    (folder/'交叉复核报告.html').write_text(doc,encoding='utf-8')


def run_crosscheck(result,folder,progress=lambda t:None,timeout=600):
    started=time.perf_counter();before=main_hash(result);spec=input_spec(result)
    work=Path(folder)/'交叉复核'/spec['run_id'];work.mkdir(parents=True,exist_ok=False)
    source=work/'独立输入.json';target=work/'独立输出.json'
    source.write_text(json.dumps(spec,ensure_ascii=False,allow_nan=False),encoding='utf-8')
    (work/'主程序快照.json').write_text(json.dumps(result,ensure_ascii=False,allow_nan=False),encoding='utf-8')
    progress('启动独立进程：力法、截面扫描与两级网格收敛复核')
    provenance=dict(run_id=spec['run_id'],main_version=result['version'],checker_version='1.1.0',input_hash=digest(spec),main_numeric_hash=before,
                    kernel_method='force_method_virtual_work_flexibility_eigenvalue',unit_system='N/mm/MPa',started_at=__import__('datetime').datetime.now().isoformat(timespec='seconds'))
    kernel_root=Path(__file__).parent
    provenance['kernel_hashes']={p.name:__import__('hashlib').sha256(p.read_bytes()).hexdigest() for p in kernel_root.glob('*.py')}
    if not provenance['kernel_hashes'] and (kernel_root/'source_manifest.json').is_file():
        provenance['kernel_hashes']=json.loads((kernel_root/'source_manifest.json').read_text(encoding='utf-8'))
    try:
        if getattr(sys,'frozen',False):cmd=[sys.executable,'--crosscheck-worker',str(source),str(target)]
        else:cmd=[sys.executable,str(Path(__file__).resolve().parents[1]/'app.py'),'--crosscheck-worker',str(source),str(target)]
        env=dict(os.environ);env['PYTHONPATH']=os.pathsep.join(str(p) for p in sys.path if p)
        env.update(OPENBLAS_NUM_THREADS='2',OMP_NUM_THREADS='2',MKL_NUM_THREADS='2')
        done=subprocess.run(cmd,env=env,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=timeout,
                            creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        if done.returncode!=0:raise RuntimeError('独立计算进程失败：'+done.stderr[-1800:])
        payload=json.loads(target.read_text(encoding='utf-8'))
        if payload['worker_pid']==os.getpid() or payload['main_modules_loaded']:
            raise ValueError('独立进程隔离检查失败')
        if payload['run_id']!=spec['run_id'] or payload['input_hash']!=digest(spec):raise ValueError('独立结果快照与本次输入不符')
        if main_hash(result)!=before:raise ValueError('复核期间主结果发生变化')
        b=payload['result'];rows=compare(result,b);rules=rule_audit(result,b)
        provenance['worker_pid']=payload['worker_pid'];provenance['main_modules_loaded']=payload['main_modules_loaded']
        converged=all(r['status']=='PASS' for r in payload['convergence'])
        residual_ok=b['numerical']['force_balance_kn']<1e-6 and b['numerical']['compatibility_mm']<.0001
        numerical='FAIL' if not converged or not residual_ok or any(r['status'] in ('FAIL','ERROR') for r in rows) else ('WARN' if any(r['status']=='WARN' for r in rows) else 'PASS')
        rule='FAIL' if any(r['status']=='FAIL' for r in rules) else ('WARN' if any(r['status']=='WARN' for r in rules) else 'PARTIAL')
        design='PASS' if all(b['checks'].values()) else 'FAIL'
        status='CONSISTENT_WITHIN_SCOPE' if numerical=='PASS' and rule=='PARTIAL' and design=='PASS' else 'NEEDS_REVIEW'
        report=dict(schema='crosscheck.report.1',status=status,execution_status='PASS',numerical_status=numerical,rule_status=rule,design_status=design,coverage_status='PARTIAL',
                    message=LABELS[status]+'；仅覆盖课程纵向模型。简化损失和静定悬臂不等同于全历史工程复核。',
                    comparisons=rows,rules=rules,convergence=payload['convergence'],benchmarks=payload['benchmarks'],independent_checks=b['checks'],span_checks=b['span_checks'],
                    invariants=b['numerical'],provenance=provenance,elapsed_seconds=time.perf_counter()-started)
        report['counts']={s:sum(r['status']==s for r in rows) for s in ('PASS','WARN','FAIL','ERROR')}
        progress(f"独立复核完成：{report['counts']['PASS']}项一致，{report['counts']['WARN']}项提示，{report['counts']['FAIL']}项差异")
    except (Exception,) as exc:
        report=dict(schema='crosscheck.report.1',status='ERROR',execution_status='ERROR',numerical_status='ERROR',rule_status='NOT_RUN',design_status='NOT_RUN',coverage_status='PARTIAL',message=str(exc),
                    comparisons=[],rules=[],convergence=[],independent_checks={},counts=dict(PASS=0,WARN=0,FAIL=0,ERROR=1),provenance=provenance,elapsed_seconds=time.perf_counter()-started)
        progress('独立复核未完成：'+str(exc))
    report['report_path']=(work/'交叉复核报告.html').relative_to(Path(folder)).as_posix()
    report['json_path']=(work/'交叉复核报告.json').relative_to(Path(folder)).as_posix()
    export_report(report,work)
    return report
