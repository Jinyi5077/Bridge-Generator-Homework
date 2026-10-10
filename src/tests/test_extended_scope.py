import unittest
from unittest.mock import patch
import numpy as np
from bridgegen.config import validate,section_suggestions,span_suggestions
from bridgegen.geometry import Geometry
from bridgegen.code_profiles import get_profile,DEFAULT_PROFILE,longitudinal_reduction
from bridgegen.design import analyse,_transverse_cases
from bridgegen.verification import _service_checks
from bridgegen.units import bridge_description
from bridgegen.cadlite.instructions import normalize,SCHEMA
from crosscheck import rules
from crosscheck.section import SectionModel


class ExtendedInputs(unittest.TestCase):
    def test_all_layouts_and_span_endpoints(self):
        for span in (50,150,150.01,180,220):
            for lanes in (2,3,4,6):
                with self.subTest(span=span,lanes=lanes):
                    c=validate({'main_span':span,'lanes':lanes})
                    a=Geometry(c);b=SectionModel(c)
                    decks=1 if lanes<=3 else 2
                    self.assertEqual(a.deck_count,decks)
                    self.assertEqual(b.decks,decks)
                    self.assertEqual(a.lanes_per_deck,lanes//decks)
                    self.assertAlmostEqual(a.width,b.B/1000)
                    self.assertEqual(a.total_width,decks*a.width+(decks-1)*c['deck_gap'])
                    self.assertAlmostEqual(a.section(a.left_side)['h'],.058*span,places=7)

    def test_220_m_reference_heights_and_manual_176_m_side_span(self):
        s=section_suggestions(220,3)
        c=validate({'main_span':220,'lanes':3,**{k:v for k,v in s.items() if k!='suggestion_basis'},
                    'side_span_mode':'manual','left_side_span':176,'right_side_span':110})
        self.assertEqual(span_suggestions(220,.8)['arrangement'],[176,220,176])
        self.assertEqual(Geometry(c).width,12.5)
        self.assertEqual(s['height_mid'],6.16)
        self.assertEqual(s['height_pier'],12.76)
        self.assertEqual(s['web_pier'],section_suggestions(220,6)['web_pier'])

    def test_new_out_of_range_and_inconsistent_layout_rejected(self):
        for raw in ({'main_span':220.01},{'main_span':49.99},{'lanes':3.1},{'lanes':True},
                    {'lanes':3,'layout':'separated'},{'main_span':220,'main_span_max':150},
                    {'main_span':220,'side_span_mode':'manual','left_side_span':176.1}):
            with self.subTest(raw=raw),self.assertRaises(ValueError):validate(raw)

    def test_three_lane_centres_and_seven_nonempty_cases(self):
        c=validate({'lanes':3});g=Geometry(c)
        cases=_transverse_cases(c,g,get_profile(DEFAULT_PROFILE))
        self.assertEqual(len(cases),7)
        self.assertEqual(cases[-1]['lane_centres_m'],[-3.5,0,3.5])
        self.assertEqual(cases[-1]['lane_factor'],.78)
        self.assertAlmostEqual(cases[-1]['vertical_multiplier'],2.34)
        self.assertEqual(cases[-1]['resultant_eccentricity_m'],0)
        self.assertEqual(bridge_description(c,{'deck_count':1,'lanes_per_deck':3})['arrangement'],
                         '单幅三车道、单箱单室')

    def test_cad_ai_instruction_supports_three_lanes_and_220(self):
        c=normalize(dict(schema=SCHEMA,units='m',bridge=dict(lanes=3,spans_m=[132,220,132])))
        self.assertEqual(c['bridge']['layout'],'single')
        self.assertEqual(c['bridge']['main_span'],220)
        self.assertEqual(c['bridge']['web_pier'],1.3)

    def test_independent_longitudinal_rule_boundaries(self):
        p=get_profile(DEFAULT_PROFILE)
        for span,factor in ((50,1.),(150,1.),(150.01,.97),(220,.97),(399.99,.97),
                            (400,.96),(600,.95),(800,.94),(1000,.93)):
            self.assertEqual(longitudinal_reduction(span,p),factor)
            self.assertEqual(rules.longitudinal(span*1000),factor)

    def test_end_roundoff_does_not_make_fractional_height_power_nan(self):
        g=Geometry(validate({'main_span':150.01,'lanes':3}))
        with np.errstate(invalid='raise'):
            for x in (np.nextafter(0.,-np.inf),np.nextafter(g.length,np.inf)):
                self.assertTrue(np.isfinite(g.factor(x)))
                self.assertEqual(float(g.factor(x)),0.)


class ExtendedEffects(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.single=analyse({'main_span':220,'lanes':3,'mesh_length':5})
        cls.separated=analyse({'main_span':220,'lanes':6,'mesh_length':5})

    def test_single_three_lanes_equals_one_deck_of_six_lanes(self):
        a,b=self.single,self.separated
        for key in ('M_dead','V_dead','M_live_min','M_live_max','V_live_min','V_live_max',
                    'deflection_live_min','deflection_live_max','prestress_force_effective'):
            np.testing.assert_allclose(a['analysis'][key],b['analysis'][key],rtol=1e-10,atol=1e-7)
        self.assertAlmostEqual(b['quantities']['concrete_total_m3'],2*a['quantities']['concrete_total_m3'])
        self.assertEqual(a['loads']['traffic']['longitudinal_factor'],.97)

    def test_longitudinal_factor_scales_all_live_effects_without_scaling_dead(self):
        original=get_profile(DEFAULT_PROFILE)
        for row in original['traffic']['longitudinal_reduction_intervals']:row['factor']=1.
        with patch('bridgegen.design.get_profile',return_value=original):
            unreduced=analyse({'main_span':220,'lanes':3,'mesh_length':5})
        a=self.single
        for kind in ('M','V','deflection'):
            for sign in ('min','max'):
                key=kind+'_live_'+sign
                np.testing.assert_allclose(a['analysis'][key],.97*np.asarray(unreduced['analysis'][key]),rtol=1e-10,atol=1e-8)
            np.testing.assert_allclose(a['analysis'][kind+'_dead'],unreduced['analysis'][kind+'_dead'],rtol=1e-10)
        for sign in ('min','max'):
            np.testing.assert_allclose(a['reactions']['live_'+sign],.97*np.asarray(unreduced['reactions']['live_'+sign]),rtol=1e-10,atol=1e-8)
        record=next(r for r in a['calculation_records'] if r['id']=='TRAFFIC_LONGITUDINAL')
        self.assertEqual(record['result'],.97)

    def test_service_deflection_reduces_with_fixed_accepted_steel_scheme(self):
        a=self.single;c=a['input'];g=Geometry(c)
        def run(factor):
            t={**a['loads']['traffic'],'longitudinal_factor':factor}
            return _service_checks(c,g,a['analysis'],a['material'],a['prestress'],t,
                                   a['structural_verification']['reinforcement'])['analysis_update']
        reduced=run(.97);unreduced=run(1.)
        for sign in ('min','max'):
            key='deflection_service_live_'+sign
            np.testing.assert_allclose(reduced[key],.97*unreduced[key],rtol=1e-10,atol=1e-10)


if __name__=='__main__':unittest.main()
