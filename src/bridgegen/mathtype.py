"""Small, explicit MTEF v5 authoring subset; genuine Equation.DSMT4 OLE objects.

Specification: https://docs.wiris.com/en_US/mathtype-mtef-v5-mathtype-40-and-later
One syntax tree drives both the editable MTEF and its display preview.
"""
import struct, uuid, re, io
from pathlib import Path
from lxml import etree
from docx.opc.part import Part
from docx.opc.packuri import PackURI
from docx.shared import Pt

COMMANDS={'alpha':'α','gamma':'γ','mu':'μ','rho':'ρ','tau':'τ','pi':'π','omega':'ω','eta':'η','Delta':'Δ','xi':'ξ','phi':'φ','Omega':'Ω',
          'sigma':'σ','theta':'θ','delta':'δ','int':'∫','sum':'∑','times':'×','cdot':'·','leq':'≤','geq':'≥','in':'∈','approx':'≈'}

def parse(source):
    tokens=re.findall(r'\\[a-zA-Z]+|\\.|.',source)
    pos=0
    def group():
        nonlocal pos
        out=[]
        while pos<len(tokens):
            t=tokens[pos];pos+=1
            if t=='}':break
            if t=='{':out.extend(group());continue
            if t in ('_','^'):
                value=atom();base=out.pop() if out else ('text','')
                if base[0]=='script':base=(base[0],base[1],value if t=='_' else base[2],value if t=='^' else base[3])
                else:base=('script',base,value if t=='_' else [],value if t=='^' else [])
                out.append(base);continue
            if t=='\\frac':out.append(('frac',atom(),atom()))
            elif t=='\\sqrt':out.append(('sqrt',atom()))
            elif t in ('\\mathrm','\\operatorname','\\text'):out.append(('roman',atom()))
            elif t in ('\\max','\\min','\\exp'):out.append(('roman',[('text',t[1:])]))
            elif t in ('\\left','\\right'):continue
            elif t in ('\\,','\\;','\\ '):out.append(('text',' '))
            elif t=='\\quad':out.append(('text','  '))
            elif t.startswith('\\'):
                if t[1:] not in COMMANDS:raise ValueError('Unsupported formula command '+t)
                out.append(('text',COMMANDS[t[1:]]))
            else:out.append(('text',t))
        return out
    def atom():
        nonlocal pos
        if pos>=len(tokens):raise ValueError('Missing formula argument')
        if tokens[pos]=='{':pos+=1;return group()
        t=tokens[pos];pos+=1
        return [('text',COMMANDS.get(t[1:],t) if t.startswith('\\') else t)]
    return group()

def mtef(source):
    def line(nodes):return b'\x01\x00'+emit(nodes)+b'\0' if nodes else b'\x01\x01'
    def emit(nodes,roman=False):
        out=b''
        for node in nodes:
            kind=node[0]
            if kind=='text':
                for ch in node[1]:
                    if ch=='-':ch='−'
                    face=1 if roman else (3 if ch.isalpha() and ord(ch)<0x2000 else 8 if ch.isdigit() else 6)
                    out+=bytes([2,0,128+face])+struct.pack('<H',ord(ch))
            elif kind=='roman':out+=emit(node[1],True)
            elif kind=='frac':out+=bytes([3,0,11,0,0])+line(node[1])+line(node[2])+b'\0'
            elif kind=='sqrt':out+=bytes([3,0,10,0,0])+line(node[1])+b'\x0b\x01\x01\0\x0a'
            elif kind=='script':
                out+=emit([node[1]],roman)
                sub,sup=node[2:];selector=29 if sub and sup else 27 if sub else 28
                out+=bytes([3,0,selector,0,0,11])+line(sub)+line(sup)+b'\0\x0a'
        return out
    # All alphabetic and number styles use Times New Roman. Chinese is kept in prose.
    header=bytes([5,1,0,6,0])+b'DSMT6\0\0'
    fonts=b'\x11\x01Times New Roman\0\x11\x01SimSun\0'
    sizes=bytes.fromhex('08212f458f442f4150f4100f475f4150f21f')
    styles=bytes([12])+b''.join(bytes([2 if i==12 else 1,2 if i in (3,4) else 1 if i==7 else 0]) for i in range(1,13))
    return header+fonts+b'\x12\0'+sizes+b'\0'+styles+b'\x0a\x01\0'+emit(parse(source))+b'\0\0'

def compound(streams):
    """CFB v3, four small streams, correct mini-FAT and balanced directory tree."""
    FREE=0xffffffff;END=0xfffffffe;FAT=0xfffffffd
    items=sorted(streams.items(),key=lambda p:(len(p[0]),p[0].upper()))
    assert len(items)==4 and all(len(v)<4096 for _,v in items)
    mini=b'';mf=[];entries=[]
    for name,data in items:
        start=len(mf);count=(len(data)+63)//64
        mf.extend([start+i+1 if i<count-1 else END for i in range(count)])
        mini+=data.ljust(count*64,b'\0');entries.append((name,start,len(data)))
    nmini=(len(mini)+511)//512
    # Sector 0 FAT, 1-2 directory, 3 miniFAT, 4.. mini stream.
    fat=[FAT,2,END,END]+[5+i if i<nmini-1 else END for i in range(nmini)]
    def directory(name,typ,color,left,right,child,start,size,clsid=None):
        b=bytearray(128);s=(name+'\0').encode('utf-16le');b[:len(s)]=s
        struct.pack_into('<HBBIII',b,64,len(s),typ,color,left,right,child)
        if clsid:b[80:96]=uuid.UUID(clsid).bytes_le
        struct.pack_into('<IQ',b,116,start,size);return bytes(b)
    dirs=directory('Root Entry',5,1,FREE,FREE,3,4,len(mini),'0002CE03-0000-0000-C000-000000000046')
    for i,(name,start,size) in enumerate(entries,1):
        left,right,color={1:(FREE,FREE,0),2:(1,FREE,1),3:(2,4,1),4:(FREE,FREE,1)}[i]
        dirs+=directory(name,2,color,left,right,FREE,start,size)
    hdr=bytearray(512);hdr[:8]=bytes.fromhex('d0cf11e0a1b11ae1')
    struct.pack_into('<HHHHH',hdr,24,0x3e,3,0xfffe,9,6)
    struct.pack_into('<IIIIIIIII',hdr,40,0,1,1,0,4096,3,1,END,0)
    struct.pack_into('<109I',hdr,76,0,*([FREE]*108))
    return bytes(hdr)+struct.pack('<128I',*(fat+[FREE]*(128-len(fat))))+dirs.ljust(1024,b'\0')+struct.pack('<128I',*(mf+[FREE]*(128-len(mf))))+mini.ljust(nmini*512,b'\0')

def ole_bytes(source):
    data=mtef(source)
    import ctypes
    cf=ctypes.windll.user32.RegisterClipboardFormatW('MathType EF')
    native=struct.pack('<HIHIIIII',28,0x00020000,cf,len(data),0,0,0,0)+data
    comp=bytes.fromhex('0100feff030a0000ffffffff03ce020000000000c000000000000046')
    for s in [b'MathType 6.0 Equation\0',b'MathType EF\0',b'Equation.DSMT4\0']:comp+=struct.pack('<I',len(s))+s
    comp+=bytes.fromhex('f439b271000000000000000000000000')
    return compound({'\x01CompObj':comp,'\x01Ole':bytes.fromhex('0100000208000000000000000000000000000000'),
                     '\x03ObjInfo':bytes.fromhex('000003000100'),'Equation Native':native})

def preview(source,path):
    from matplotlib import rc_context
    from matplotlib.mathtext import math_to_image
    from matplotlib.font_manager import FontProperties
    from PIL import Image
    with rc_context({'mathtext.fontset':'custom','mathtext.rm':'Times New Roman',
                     'mathtext.it':'Times New Roman:italic','mathtext.bf':'Times New Roman:bold',
                     'mathtext.sf':'Times New Roman','mathtext.tt':'Times New Roman',
                     'mathtext.cal':'Times New Roman','mathtext.fallback':None}):
        math_to_image('$'+source.replace(r'\cdot','·')+'$',str(path),prop=FontProperties(size=12),dpi=288,format='png',color='black')
    with Image.open(path) as im:w,h=im.size
    return w/4,h/4

def add_equation(paragraph,source,path,index):
    w,h=preview(source,path)
    if w>380:raise ValueError(f'公式过宽，请拆行：{source}')
    part=paragraph.part
    blob=ole_bytes(source)
    embedded=Part(PackURI('/word/embeddings/equation%d.bin'%index),
                  'application/vnd.openxmlformats-officedocument.oleObject',blob,part.package)
    rid=part.relate_to(embedded,'http://schemas.openxmlformats.org/officeDocument/2006/relationships/oleObject')
    imagerid,_=part.get_or_add_image(str(path))
    ns={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main',
        'v':'urn:schemas-microsoft-com:vml','o':'urn:schemas-microsoft-com:office:office',
        'r':'http://schemas.openxmlformats.org/officeDocument/2006/relationships'}
    def el(tag,**attrs):
        prefix,local=tag.split(':');return etree.Element('{%s}%s'%(ns[prefix],local),**attrs)
    obj=el('w:object');shapeid='_x0000_i%d'%(2000+index)
    if index==1:
        st=el('v:shapetype',id='_x0000_t75',coordsize='21600,21600',filled='f',stroked='f')
        st.set('{'+ns['o']+'}spt','75');st.set('{'+ns['o']+'}preferrelative','t')
        obj.append(st)
    shape=el('v:shape',id=shapeid,type='#_x0000_t75',style=f'width:{w:.2f}pt;height:{h:.2f}pt')
    shape.set('{'+ns['o']+'}ole','t')
    img=el('v:imagedata');img.set('{'+ns['r']+'}id',imagerid);shape.append(img);obj.append(shape)
    ole=el('o:OLEObject',Type='Embed',ProgID='Equation.DSMT4',ShapeID=shapeid,DrawAspect='Content',ObjectID=str(1900000000+index))
    ole.set('{'+ns['r']+'}id',rid);obj.append(ole)
    paragraph.add_run()._r.append(obj)
    paragraph.paragraph_format.line_spacing=1.0
    return w,h
