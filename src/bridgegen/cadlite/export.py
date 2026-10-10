from pathlib import Path
import hashlib
import json
import os
from .drafting import CN_FONT, NUM_FONT, LAYERS, render_cad_pdf
from .sheets import make_scenes,NAMES
from .geometry import Geometry
from .oda import convert

def check_fonts():
    font_root=Path(os.environ.get('WINDIR','C:/Windows'))/'Fonts'
    missing=[n for n in (CN_FONT,NUM_FONT) if not (font_root/n).is_file()]
    if missing:raise ValueError('缺少制图字体：'+','.join(missing)+'；请先安装字体，禁止静默替换')
    return {'CN_FS':str(font_root/CN_FONT),'ISO_NUM':str(font_root/NUM_FONT)}

def export(request,out,no_dwg=False,preview=False,oda='',progress=print):
    out=Path(out).resolve()
    if out.exists() and any(out.iterdir()):raise ValueError('成果目录必须为空，避免混入旧DWG')
    fonts=check_fonts()
    scenes=make_scenes(request)  # reject invalid custom geometry before writing files
    out.mkdir(parents=True,exist_ok=True);dxf=out/'CAD_DXF';dxf.mkdir()
    (out/'绘图指令_规范化.json').write_text(json.dumps(request,ensure_ascii=False,indent=2),encoding='utf-8')
    audits=[]
    for key,scene in scenes:
        name=NAMES[key];progress('绘制 '+name)
        audits.append(scene.save(dxf/(name+'.dxf')))
    if no_dwg:dwg={'status':'disabled','message':'按运行选项跳过DWG转换','files':[]}
    else:
        progress('调用ODA转换DWG并回转检查')
        dwg=convert(dxf,out/'CAD_DWG',oda)
    if preview:
        pdf=out/'CAD_PDF';pdf.mkdir()
        src=out/'CAD_回转检查' if dwg['status']=='ok' else dxf
        for path in src.glob('*.dxf'):
            progress('生成预览 '+path.stem)
            render_cad_pdf(path,pdf/(path.stem+'.pdf'))
    g=Geometry(request['bridge'])
    report={'drawing_version':'1.2.0','instruction_schema':request['schema'],
            'geometry':{'spans_m':g.spans.tolist(),'width_m':g.width,'total_width_m':g.total_width,
                        'lanes':request['bridge']['lanes'],'layout':request['bridge']['layout'],
                        'deck_count':g.deck_count,'lanes_per_deck':g.lanes_per_deck,
                        'midspan_section':g.section(g.left_side+g.main/2),'pier_section':g.section(g.left_side)},
            'fonts':fonts,'lineweights_mm':sorted({w/100 for w,_ in LAYERS.values()}),
            'sheets':audits,'dwg':dwg,'geometry_status':'validated',
            'calculation_status':'NOT_PERFORMED_BY_CAD_SCRIPT',
            'note':'几何与制图检查不代表结构承载力验算；下部结构、支座及节段为课程构造示意。',
            'passed':dwg['status'] in ('ok','disabled')}
    (out/'制图检查.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    files=[{'path':p.relative_to(out).as_posix(),'bytes':p.stat().st_size,
            'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(out.rglob('*')) if p.is_file()]
    (out/'生成清单.json').write_text(json.dumps({'files':files,'dwg_status':dwg['status']},ensure_ascii=False,indent=2),encoding='utf-8')
    progress(dwg['message']);return report
