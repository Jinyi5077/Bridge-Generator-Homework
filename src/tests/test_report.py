import unittest,tempfile,json
from pathlib import Path
from zipfile import ZipFile
from lxml import etree
import numpy as np
from bridgegen.config import DEFAULT
from bridgegen.design import analyse
from bridgegen.report import plots,export_report
from bridgegen.slides import export_slides
from bridgegen.course_book import book_pages,write_docx,write_pdf
from pypdf import PdfReader
import pdfplumber

class CalculationBookTests(unittest.TestCase):
    def test_cover_is_unnumbered_and_body_pages_restart_at_one(self):
        pages=[('封面',[('p','课程设计计算书')]),('第1章 模型',[('p','模型计算与作用效应。'*24)]*32),('第2章 结果',[('p','结果说明。')])]
        with tempfile.TemporaryDirectory() as td:
            out=Path(td);docx=out/'book.docx';pdf=out/'book.pdf'
            formulas=write_docx(pages,docx);write_pdf(pages,pdf,formulas)
            ns={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main','r':'http://schemas.openxmlformats.org/officeDocument/2006/relationships'}
            with ZipFile(docx) as z:
                doc=etree.fromstring(z.read('word/document.xml'))
                sections=doc.findall('.//w:sectPr',ns);self.assertEqual(len(sections),2)
                self.assertEqual(sections[1].find('w:pgNumType',ns).get('{'+ns['w']+'}start'),'1')
                footer_parts=[n for n in z.namelist() if n.startswith('word/footer') and n.endswith('.xml')]
                page_fields=[]
                for n in footer_parts:
                    root=etree.fromstring(z.read(n))
                    page_fields.extend(root.findall('.//w:instrText',ns))
                self.assertEqual([v.text.strip() for v in page_fields],['PAGE'])
                settings=etree.fromstring(z.read('word/settings.xml'))
                self.assertEqual(settings.find('w:updateFields',ns).get('{'+ns['w']+'}val'),'true')
                self.assertEqual(len(doc.findall('.//w:bookmarkStart',ns)),2)
            reader=PdfReader(pdf)
            self.assertGreater(len(reader.pages),3)
            self.assertEqual(reader.page_labels,['封面',*[str(i) for i in range(1,len(reader.pages))]])
            with pdfplumber.open(pdf) as rendered:
                for i,page in enumerate(rendered.pages):
                    footer=page.crop((0,page.height-65,page.width,page.height)).extract_text() or ''
                    self.assertEqual(footer.strip(),str(i) if i else '')
            self.assertEqual(reader.get_destination_page_number(reader.outline[0]),1)

    def test_report_inputs_and_influence_trace_reproduce_results(self):
        for span in [80,120]:
            c=dict(DEFAULT,main_span=span,pavement_thickness=.13,barrier_line_load=31.,other_dead_load=7.)
            r=analyse(c);d=r['calculation_details'];a=r['analysis'];t=r['loads']['traffic']
            self.assertAlmostEqual(r['loads']['dead2'],8*.13*24+31+7)
            self.assertAlmostEqual(d['dead1_weight'],r['quantities']['concrete_per_deck_m3']*26)
            self.assertAlmostEqual(d['dead2_weight'],r['loads']['dead2']*span*2.2)
            cases={v['id']:v for v in t['transverse_cases']}
            for trace in d['live_trace']:
                j=trace['station_index']
                for k in ['M','V']:
                    pk=t['pk']*(1.2 if k=='V' else 1)
                    for bound,area,eta in [('min','negative_area','eta_min'),('max','positive_area','eta_max')]:
                        factor=cases[trace[k]['transverse_case_'+bound]]['vertical_multiplier']
                        self.assertAlmostEqual(a[f'{k}_live_{bound}'][j],factor*(t['qk']*trace[k][area]+pk*trace[k][eta]),places=6)

    def test_two_and_six_lane_books_and_slides_use_actual_geometry_and_traffic(self):
        figs={key:'figure.png' for key in ['内力包络','位移包络','钢束与损失','施工阶段','验算利用率']}
        for lanes,arrangement,multiplier in [(2,'单幅双向两车道、单箱单室',2.),(6,'左右分离两幅，每幅三车道、单箱单室',2.34)]:
            r=analyse({'main_span':50,'lanes':lanes,'project_name':f'{lanes}车道参数化测试'})
            self.assertEqual(r['geometry']['deck_count'],1 if lanes==2 else 2)
            self.assertEqual(r['geometry']['lanes_per_deck'],2 if lanes==2 else 3)
            pages=book_pages(r,figs)
            text=str(pages)
            self.assertIn(arrangement,text)
            self.assertNotIn('每幅两车道' if lanes==6 else '左右分离两幅',text)
            self.assertIn('50～150 m',text)
            self.assertNotIn('均超过50 m',text)
            example=next(b[1] for title,blocks in pages for b in blocks if b[0]=='equation' and b[1].startswith('M_{Q,+}=') and 'times' in b[1])
            self.assertTrue(example.startswith(f'M_{{Q,+}}={multiplier:g}('))
            t=r['loads']['traffic'];cases={v['id']:v for v in t['transverse_cases']}
            for trace in r['calculation_details']['live_trace']:
                for k in ['M','V']:
                    pk=t['pk']*(t['shear_point_factor'] if k=='V' else 1.)
                    for bound,area,eta in [('min','negative_area','eta_min'),('max','positive_area','eta_max')]:
                        factor=cases[trace[k]['transverse_case_'+bound]]['vertical_multiplier']
                        self.assertAlmostEqual(r['analysis'][f'{k}_live_{bound}'][trace['station_index']],factor*(t['qk']*trace[k][area]+pk*trace[k][eta]),places=6)
            with tempfile.TemporaryDirectory() as td:
                path=Path(td)/'lanes.pptx';export_slides(r,path)
                with ZipFile(path) as z:
                    text=''.join(''.join(etree.fromstring(z.read(n)).itertext()) for n in z.namelist() if n.startswith('ppt/slides/slide') and n.endswith('.xml'))
                    self.assertIn(arrangement,text)
                    self.assertNotIn('两幅各两车道',text)
                    self.assertIn('未计冲击',text)
                    if lanes==6:
                        self.assertIn('3 × 0.78 = 2.34',text)
                        self.assertEqual(len(t['transverse_cases']),7)
    def test_docx_fonts_ole_and_only_calculated_chapters(self):
        r=analyse(DEFAULT)
        with tempfile.TemporaryDirectory() as td:
            out=Path(td);export_report(r,out,plots(r,out/'图表'))
            with ZipFile(out/'01_桥梁工程课程设计计算书.docx') as z:
                ns={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main','o':'urn:schemas-microsoft-com:office:office','m':'http://schemas.openxmlformats.org/officeDocument/2006/math'}
                doc=etree.fromstring(z.read('word/document.xml'))
                objects=doc.findall('.//o:OLEObject',ns);self.assertGreater(len(objects),39)
                self.assertTrue(all(o.get('ProgID')=='Equation.DSMT4' for o in objects));self.assertFalse(doc.findall('.//m:oMath',ns))
                for part in ['word/document.xml','word/styles.xml','word/footer1.xml']:
                    for f in etree.fromstring(z.read(part)).findall('.//w:rFonts',ns):
                        self.assertEqual(f.get('{'+ns['w']+'}eastAsia'),'宋体')
                        self.assertEqual(f.get('{'+ns['w']+'}ascii'),'Times New Roman')
                        self.assertEqual(f.get('{'+ns['w']+'}hAnsi'),'Times New Roman')
                for i in range(1,len(objects)+1):
                    data=z.read(f'word/embeddings/equation{i}.bin');self.assertTrue(data.startswith(bytes.fromhex('d0cf11e0a1b11ae1')))
                    self.assertIn(b'Equation.DSMT4',data);self.assertIn(b'Times New Roman',data)
                text=''.join(doc.itertext());self.assertNotIn('待完成',text);self.assertIn('预应力损失',text);self.assertIn('施工阶段',text);self.assertIn('一期恒载',text);self.assertIn('二期恒载',text)
                self.assertIn('横向车道工况',text);self.assertIn('竖向位移作用效应',text);self.assertIn('COURSE_SCOPE_COMPLETE',text)
                self.assertIn('课程设计范围说明',text);self.assertIn('OUT_OF_COURSE_SCOPE',text)
                self.assertIn('正截面抗弯承载力',text);self.assertIn('斜截面抗剪承载力',text)
                self.assertIn('抗裂验算',text);self.assertIn('建议预拱度',text)
                self.assertIn('计算追溯与参数敏感性',text);self.assertIn('恒载增加5%',text)
                self.assertIn('P1',text);self.assertIn('P2',text);self.assertIn('双主墩',text)

    def test_v09_presentation_is_23_pages_editable_and_sourced(self):
        r=analyse(DEFAULT)
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'report.pptx';export_slides(r,path)
            with ZipFile(path) as z:
                slides=[n for n in z.namelist() if n.startswith('ppt/slides/slide') and n.endswith('.xml')]
                charts=[n for n in z.namelist() if n.startswith('ppt/charts/chart') and n.endswith('.xml')]
                books=[n for n in z.namelist() if n.startswith('ppt/embeddings/') and n.endswith('.xlsx')]
                notes=[n for n in z.namelist() if n.startswith('ppt/notesSlides/notesSlide') and n.endswith('.xml')]
                self.assertEqual(len(slides),23)
                self.assertEqual(len(charts),8)
                self.assertEqual(len(books),8)
                self.assertEqual(len(notes),23)
                note_text=''.join(''.join(etree.fromstring(z.read(n)).itertext()) for n in notes)
                self.assertIn('数据来源',note_text);self.assertIn('讲解重点',note_text)
                self.assertIn('prestress.end_anchor_rule',note_text)
                self.assertIn(r['prestress']['end_anchor_rule']['mode'],note_text)
                slide_text=''.join(''.join(etree.fromstring(z.read(n)).itertext()) for n in slides)
                self.assertIn('双主墩对称悬臂施工模型',slide_text)
                self.assertIn('结论与局限',slide_text)
                self.assertIn('OUT_OF_COURSE_SCOPE',slide_text)
                for chart in charts:
                    content=z.read(chart)
                    self.assertNotRegex(content,br'<c:(?:axId|crossAx) val="-')
            r['structural_verification']['checks']['temporary_concrete_stress']['status']='FAIL'
            export_slides(r,path)
            with ZipFile(path) as z:
                slide_text=''.join(''.join(etree.fromstring(z.read(n)).itertext()) for n in z.namelist() if n.startswith('ppt/slides/slide') and n.endswith('.xml'))
                self.assertIn('短暂状况混凝土压应力验算判定为 FAIL',slide_text)
                self.assertNotIn('控制工况仍满足',slide_text)

if __name__=='__main__':unittest.main()
