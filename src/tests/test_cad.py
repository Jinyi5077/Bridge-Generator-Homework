"""Integration checks for drawing semantics and corruption detection."""
import tempfile,unittest
from pathlib import Path
import ezdxf
from bridgegen.config import DEFAULT
from bridgegen.design import analyse
from bridgegen.engineering_drawings import make_scenes
from bridgegen.dwg import check_roundtrip


class DrawingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result=analyse(dict(DEFAULT))

    def test_actual_dimensions_layouts_and_holes(self):
        with tempfile.TemporaryDirectory() as tmp:
            for sheet in make_scenes(self.result):
                p=Path(tmp)/(sheet.number+'.dxf');audit=sheet.save(p)
                self.assertGreaterEqual(audit['dimensions'],7)
                doc=ezdxf.readfile(p);layout=doc.layouts.get('出图')
                self.assertTrue(layout.dxf.plot_layout_flags & 128)
                self.assertFalse(layout.dxf.plot_layout_flags & 64)
                for dim in doc.modelspace().query('DIMENSION'):
                    self.assertIn(dim.dxf.text,('','<>'))
                for hatch in doc.modelspace().query('HATCH'):
                    self.assertEqual(hatch.dxf.hatch_style,0)
                    self.assertIn(len(hatch.paths),(1,DEFAULT['cells']+1))
                self.assertEqual(doc.styles.get('CN_FS').dxf.width,.7)
                self.assertEqual(doc.layers.get('B-CUT').dxf.lineweight,50)
                self.assertEqual(doc.layers.get('B-DIM').dxf.lineweight,13)
                self.assertEqual(doc.layers.get('B-PRESTRESS').dxf.lineweight,25)
                self.assertEqual(doc.layers.get('B-REBAR').dxf.lineweight,25)
                if sheet.number=='01':
                    self.assertGreater(len(doc.modelspace().query('LWPOLYLINE[layer=="B-PRESTRESS"]')),0)
                else:
                    self.assertGreater(len(doc.modelspace().query('CIRCLE[layer=="B-PRESTRESS"]')),0)

    def test_roundtrip_validator_rejects_font_substitution(self):
        a=make_scenes(self.result)[1].d;b=make_scenes(self.result)[1].d
        b.styles.get('CN_FS').dxf.font='arial.ttf'
        with self.assertRaisesRegex(RuntimeError,'字体'):check_roundtrip(a,b)

    def test_roundtrip_validator_rejects_dimension_override(self):
        a=make_scenes(self.result)[1].d;b=make_scenes(self.result)[1].d
        b.modelspace().query('DIMENSION')[0].dxf.text='99999'
        with self.assertRaisesRegex(RuntimeError,'固定文字'):check_roundtrip(a,b)

    def test_user_span_range(self):
        with tempfile.TemporaryDirectory() as tmp:
            for span in (50.,150.):
                result=analyse({'main_span':span,'lanes':6,'designer_name':'绘图测试','student_id':'001'})
                for sheet in make_scenes(result):sheet.save(Path(tmp)/(str(span)+'_'+sheet.number+'.dxf'))


if __name__=='__main__':unittest.main()
