import unittest
from pathlib import Path


class UserInterfaceTests(unittest.TestCase):
    def test_project_controls_and_section_suggestion_route_are_present(self):
        root = Path(__file__).resolve().parents[1]
        html = (root / 'ui.html').read_text(encoding='utf-8')
        app = (root / 'app.py').read_text(encoding='utf-8')
        for element_id in [
            'newProject', 'saveProject', 'openProject', 'copyProject',
            'resumeProject', 'projectFile', 'suggest', 'advanced'
        ]:
            self.assertIn(f'id="{element_id}"', html)
        self.assertIn("bridgegen-v09-project", html)
        self.assertIn("side_span_mode", html)
        self.assertIn("left_side_span", html)
        self.assertIn("right_side_span", html)
        self.assertIn("/api/suggest", html)
        self.assertIn("if self.path=='/api/suggest'", app)
        self.assertIn("'version':'0.13.0'", app)
        self.assertIn("span_suggestions", app)

    def test_lane_selection_and_span_updates_follow_actual_layout(self):
        html=(Path(__file__).resolve().parents[1]/'ui.html').read_text(encoding='utf-8')
        self.assertIn("['lanes','全桥总车道数','select']",html)
        self.assertIn("lanes:[2,3,4,6]",html)
        self.assertIn("主跨（50～220）",html)
        self.assertIn("lanes<=3?1:2",html)
        self.assertIn("decks*w+(decks===2?num('deck_gap'):0)",html)
        self.assertIn("if(key==='main_span'||key==='lanes')queueSuggestions()",html)
        self.assertIn("post('/api/suggest',{main_span,side_span_ratio,lanes})",html)
        self.assertIn("if(suggestionTimer!==null||suggestionPromise)",html)
        self.assertIn("#fff0d6",html)
        self.assertIn("#48c6f0",html)
        self.assertIn("#ff8a3d",html)

    def test_author_and_elevation_inputs_are_present_and_required_on_run(self):
        root=Path(__file__).resolve().parents[1]
        html=(root/'ui.html').read_text(encoding='utf-8')
        app=(root/'app.py').read_text(encoding='utf-8')
        for key in ['designer_name','student_id','institution','class_name','supervisor','drawing_date','elevation_mode','deck_elevation','longitudinal_slope']:
            self.assertIn(key,html)
        self.assertLess(html.index("['绘图人信息'"),html.index("['基本尺寸'"))
        self.assertIn('require_drawing_identity(config)',app)
        from app import require_drawing_identity
        for c in [{},{'designer_name':'张三'},{'designer_name':' ','student_id':'123'}]:
            with self.assertRaises(ValueError):require_drawing_identity(c)
        require_drawing_identity({'designer_name':'张三','student_id':'123'})
        self.assertIn('不代表实测高程',html)


if __name__ == '__main__':
    unittest.main()
