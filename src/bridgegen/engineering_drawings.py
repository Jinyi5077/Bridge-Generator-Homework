"""BridgeGenerator V0.11 adapter for the independent CAD engine."""
from pathlib import Path
import json
from .cadlite.drafting import Sheet,CN_FONT,NUM_FONT,LAYERS,REFERENCES,render_cad_pdf
from .cadlite.export import check_fonts
from .cadlite.instructions import from_result_data
from .cadlite.sheets import make_scenes as _make_scenes

def make_scenes(result):
    return [scene for _,scene in _make_scenes(from_result_data(result))]

def export_drawings(result,out):
    out=Path(out);out.mkdir(parents=True,exist_ok=True);check_fonts()
    dxf=out/'CAD_DXF';pdf=out/'CAD_PDF';dxf.mkdir(exist_ok=True);pdf.mkdir(exist_ok=True)
    audits=[]
    names=['01_总体立面图','02_跨中横断面图','03_墩顶横断面图']
    for scene,name in zip(make_scenes(result),names):
        path=dxf/(name+'.dxf');audits.append(scene.save(path));render_cad_pdf(path,pdf/(name+'.pdf'))
    (out/'制图检查.json').write_text(json.dumps({'drawing_version':'1.2.0','references':REFERENCES,
        'sheets':audits,'note':'一般构造图已优化；下部结构、支座与施工分段为示意，配筋和孔道详图另绘。'},
        ensure_ascii=False,indent=2),encoding='utf-8')
    return audits
