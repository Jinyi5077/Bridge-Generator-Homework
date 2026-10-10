from pathlib import Path
import csv,json,hashlib
import pypdfium2 as pdfium
from .design import analyse
from .drawings import export_drawings
from .report import plots,export_report
from .slides import export_slides
from .dwg import convert


def build(config,out,progress=lambda s:None,no_dwg=False,drawings_only=False):
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    # A new empty output directory avoids presenting stale files as current results.
    if any(out.iterdir()):raise ValueError('成果目录必须为空，请选择新的输出目录')
    r=analyse(config,progress)
    from crosscheck.service import run_crosscheck
    r['crosscheck']=run_crosscheck(r,out,progress)
    r['status']+='；独立交叉验证：'+r['crosscheck']['status']
    (out/'输入参数.json').write_text(json.dumps(r['input'],ensure_ascii=False,indent=2),encoding='utf-8')
    (out/'输入与来源.json').write_text(json.dumps(r['input_audit'],ensure_ascii=False,indent=2),encoding='utf-8')
    (out/'规范配置.json').write_text(json.dumps(r['code_profile'],ensure_ascii=False,indent=2),encoding='utf-8')
    (out/'工况与组合.json').write_text(json.dumps(dict(load_cases=r['load_cases'],combinations=r['combinations']),ensure_ascii=False,indent=2),encoding='utf-8')
    (out/'计算记录.json').write_text(json.dumps(r['calculation_records'],ensure_ascii=False,indent=2),encoding='utf-8')
    trace_columns=['id','chapter','name','input','formula','intermediate','result','unit','source','result_path']
    with (out/'计算追溯表.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=trace_columns);w.writeheader()
        for row in r['calculation_trace']:
            w.writerow({key:(json.dumps(row[key],ensure_ascii=False,sort_keys=True)
                              if isinstance(row[key],(dict,list)) else row[key])
                        for key in trace_columns})
    if not drawings_only:
        progress('生成内力、位移、预应力损失和双主墩施工阶段图表')
        figs=plots(r,out/'图表')
    progress('生成三张 DXF 与 PDF 图纸')
    audits=export_drawings(r,out)
    if not drawings_only:
        progress('生成计算书与23页学术答辩 PPT')
        export_report(r,out,figs);export_slides(r,out/'03_设计汇报.pptx')
    if no_dwg:dwg=dict(status='disabled',message='按运行选项跳过DWG转换。',files=[])
    else:
        progress('转换 DWG 并执行回转检查')
        dwg=convert(out/'CAD_DXF',out/'CAD_DWG',r['input'].get('oda_path',''))
        if dwg['status']=='ok':
            from .engineering_drawings import render_cad_pdf
            progress('从DWG回转文件生成最终PDF，保持图纸与预览一致')
            for p in (out/'CAD_回转检查').glob('*.dxf'):
                render_cad_pdf(p,out/'CAD_PDF'/(p.stem+'.pdf'))
    r['exports']=dict(dxf=audits,dwg=dwg)
    (out/'设计结果.json').write_text(json.dumps(r,ensure_ascii=False,indent=2),encoding='utf-8')
    scope_text=(r['status']+'\n\n课程设计范围外（OUT_OF_COURSE_SCOPE）：\n'
                +'\n'.join(r['out_of_course_scope'])+'\n\n'+dwg['message'])
    (out/'计算范围说明.txt').write_text(scope_text,encoding='utf-8')
    a=r['analysis'];columns=[k for k,v in a.items() if isinstance(v,list) and len(v)==len(a['x'])]
    with (out/'计算数据.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.writer(f);w.writerow(columns);w.writerows(zip(*(a[k] for k in columns)))
    preview=out/'预览';preview.mkdir()
    for p in (out/'CAD_PDF').glob('*.pdf'):
        doc=pdfium.PdfDocument(str(p));page=doc[0];bmp=page.render(scale=1.5)
        bmp.to_pil().save(preview/(p.stem+'.png'));page.close();doc.close()
    write_manifest(r,out)
    progress('成果生成完成')
    return r


def write_manifest(r,out):
    files=[]
    for p in sorted(out.rglob('*')):
        if p.is_file() and p.name!='生成清单.json':files.append(dict(path=p.relative_to(out).as_posix(),bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()))
    (out/'生成清单.json').write_text(json.dumps(dict(status=r['status'],dwg=r['exports']['dwg'],crosscheck=r.get('crosscheck',{}).get('status'),files=files),ensure_ascii=False,indent=2),encoding='utf-8')
