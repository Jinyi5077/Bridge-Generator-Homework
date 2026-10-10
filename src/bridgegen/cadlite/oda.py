from pathlib import Path
import os,sys,shutil,subprocess,tempfile,json,math
from collections import Counter
import ezdxf


def find_oda(explicit=''):
    candidates=[]
    if explicit:
        target=Path(explicit).expanduser()
        if not target.is_file() or target.name.lower() not in ('odafileconverter.exe','odafileconverter'):
            raise ValueError('指定的ODA路径必须是已存在的ODAFileConverter可执行文件')
        return target.resolve()
    if os.environ.get('ODA_FILE_CONVERTER'):
        target=Path(os.environ['ODA_FILE_CONVERTER'])
        if target.is_file() and target.name.lower() in ('odafileconverter.exe','odafileconverter'):candidates.append(target)
    exe=shutil.which('ODAFileConverter')
    if exe:candidates.append(Path(exe))
    root=Path(sys.executable).parent if getattr(sys,'frozen',False) else Path(__file__).resolve().parents[1]
    for folder in [root/'tools'/'oda',Path('D:/APPS/ODA'),Path('C:/Program Files/ODA'),Path('C:/Program Files (x86)/ODA')]:
        if folder.is_dir():candidates.extend(folder.rglob('ODAFileConverter.exe'))
    return next((p.resolve() for p in candidates if p.is_file()),None)


def check_roundtrip(before,after):
    """Reject conversion that silently changes drafting semantics."""
    def fail(message):raise RuntimeError('DWG回转检查：'+message)
    def close(a,b):return math.isclose(float(a),float(b),rel_tol=1e-8,abs_tol=1e-5)
    if before.units!=after.units:fail('模型单位发生变化')
    for name in ['CN_FS','ISO_NUM']:
        a=before.styles.get(name);b=after.styles.get(name)
        if Path(a.dxf.font).name.lower()!=Path(b.dxf.font).name.lower() or not close(a.dxf.width,b.dxf.width):fail('字体或字宽发生变化：'+name)
    for layer in before.layers:
        if layer.dxf.name.startswith(('B-','P-')):
            b=after.layers.get(layer.dxf.name)
            if (layer.dxf.lineweight,layer.dxf.linetype.upper(),layer.dxf.plot)!=(b.dxf.lineweight,b.dxf.linetype.upper(),b.dxf.plot):fail('图层打印属性变化：'+layer.dxf.name)
    for name in ['B-CENTER','B-HIDDEN']:
        a=before.linetypes.get(name).simplified_line_pattern();b=after.linetypes.get(name).simplified_line_pattern()
        if len(a)!=len(b) or not all(close(x,y) for x,y in zip(a,b)):fail('线型间隔发生变化')
    dims0=list(before.modelspace().query('DIMENSION'));dims1=list(after.modelspace().query('DIMENSION'))
    if len(dims0)!=len(dims1):fail('原生尺寸标注数量发生变化')
    dimensions=[]
    for a,b in zip(dims0,dims1):
        if not close(a.get_measurement(),b.get_measurement()):fail('尺寸测量值发生变化')
        if b.dxf.text not in ('','<>'):fail('尺寸被替换为固定文字')
        da=a.get_dim_style();db=b.get_dim_style()
        if da.dxf.dimtxsty.upper()!=db.dxf.dimtxsty.upper():fail('尺寸字体样式发生变化')
        for key in ['dimscale','dimtxt','dimasz','dimlfac','dimlwd','dimlwe']:
            if not close(getattr(da.dxf,key),getattr(db.dxf,key)):fail('尺寸样式发生变化：'+key)
        dimensions.append(round(float(b.get_measurement()),6))
    def texts(d):
        return Counter((l.name,e.dxftype(),e.dxf.text,e.dxf.style,round(e.dxf.height,5),round(e.dxf.width,5))
                       for l in d.layouts for e in l.query('TEXT'))
    if texts(before)!=texts(after):fail('文字内容、字体、字高或字宽发生变化')
    for l in before.layouts:
        other=after.layouts.get(l.name)
        if Counter(e.dxftype() for e in l if e.dxftype()!='VIEWPORT')!=Counter(e.dxftype() for e in other if e.dxftype()!='VIEWPORT'):fail('实体类型或数量发生变化：'+l.name)
        if l.name=='Model':continue
        for key in ['paper_width','paper_height','scale_numerator','scale_denominator']:
            if not close(getattr(l.dxf,key),getattr(other.dxf,key)):fail('图幅或打印比例发生变化')
        if (other.dxf.plot_layout_flags & 128)==0:fail('打印线宽未启用')
        av=[v for v in l.query('VIEWPORT') if v.dxf.id>1];bv=[v for v in other.query('VIEWPORT') if v.dxf.id>1]
        if len(av)!=len(bv) or not all(close(a.get_scale(),b.get_scale()) for a,b in zip(av,bv)):fail('视口比例发生变化')
    for a,b in zip(before.modelspace().query('HATCH'),after.modelspace().query('HATCH')):
        if a.dxf.hatch_style!=b.dxf.hatch_style or len(a.paths)!=len(b.paths):fail('剖面空腔边界发生变化')
    return dict(dimensions=len(dimensions),measurements_mm=dimensions,fonts_preserved=True,
        layer_lineweights_preserved=True,linetypes_preserved=True,text_preserved=True,
        paper_and_viewport_scales_preserved=True,hatch_boundaries_preserved=True)


def convert(dxfdir,dwgdir,explicit=''):
    dxfdir,dwgdir=Path(dxfdir),Path(dwgdir)
    oda=find_oda(explicit);dwgdir.mkdir(parents=True,exist_ok=True)
    if not oda:return dict(status='unavailable',message='未找到 ODA File Converter。本次保留完整 DXF 和 PDF，未生成 DWG。',files=[])
    # Run in isolated directories to prevent mixing old outputs with this run.
    with tempfile.TemporaryDirectory(prefix='bridge_dwg_') as tmp:
        root=Path(tmp);src=root/'in';dest=root/'out';back=root/'back'
        for f in [src,dest,back]:f.mkdir()
        originals=list(sorted(dxfdir.glob('*.dxf')))
        if not originals:return dict(status='failed',message='没有可转换的DXF图纸。',files=[])
        for i,p in enumerate(originals):shutil.copyfile(p,src/f'drawing_{i}.dxf')
        flags={'creationflags':subprocess.CREATE_NO_WINDOW} if os.name=='nt' else {}
        def run(inp,out,fmt,pattern):
            r=subprocess.run([str(oda),str(inp),str(out),'ACAD2018',fmt,'0','1',pattern],
                capture_output=True,timeout=180,**flags)
            if r.returncode:raise RuntimeError('ODA 返回码 '+str(r.returncode))
        try:
            run(src,dest,'DWG','*.dxf');run(dest,back,'DXF','*.dwg')
            files=[]
            for i,original in enumerate(originals):
                dwg=dest/f'drawing_{i}.dwg';roundtrip=back/f'drawing_{i}.dxf'
                if not dwg.exists() or dwg.stat().st_size<128:raise RuntimeError('ODA未输出有效DWG')
                if dwg.read_bytes()[:6]!=b'AC1032':raise RuntimeError('DWG版本标识不符')
                check=ezdxf.readfile(roundtrip);audit=check.audit()
                if audit.has_errors:raise RuntimeError('DWG回转校验发现DXF错误')
                checks=check_roundtrip(ezdxf.readfile(original),check)
                files.append(dict(file=original.stem+'.dwg',bytes=dwg.stat().st_size,
                    roundtrip_entities=len(check.modelspace()),audit_errors=len(audit.errors),checks=checks))
            verified=dwgdir.parent/'CAD_回转检查';verified.mkdir(exist_ok=True)
            for i,original in enumerate(originals):
                shutil.copyfile(dest/f'drawing_{i}.dwg',dwgdir/(original.stem+'.dwg'))
                shutil.copyfile(back/f'drawing_{i}.dxf',verified/original.name)
            return dict(status='ok',message=f'已生成{len(files)}张DWG；尺寸、字体、线宽、线型及打印比例均通过回转检查。',oda=str(oda),files=files)
        except (OSError,subprocess.SubprocessError,RuntimeError,ezdxf.DXFError) as exc:
            return dict(status='failed',message='DWG转换失败: '+str(exc),files=[])
