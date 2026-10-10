import unittest
import numpy as np
from bridgegen.fem import Beam, envelope
from bridgegen.config import validate, section_suggestions, span_suggestions
from bridgegen.design import analyse
from bridgegen.design import _transverse_cases, _apply_transverse
from bridgegen.geometry import Geometry
from bridgegen.code_profiles import DEFAULT_PROFILE, get_profile
from bridgegen.state import DesignState


class MechanicsTests(unittest.TestCase):
    def setUp(self):
        self.L=20.;self.EI=3e7;self.x=np.linspace(0,self.L,21)
        self.b=Beam(self.x,self.EI,[0,self.L])

    def test_uniform_simply_supported(self):
        q=30.;r=self.b.distributed(-q)
        self.assertAlmostEqual(max(r['M']),q*self.L**2/8,places=5)
        self.assertAlmostEqual(-r['u'][20],5*q*self.L**4/(384*self.EI),places=9)
        np.testing.assert_allclose(r['R'],q*self.L/2,rtol=1e-9)

    def test_midspan_point_load(self):
        F=np.zeros(self.b.nd);F[20]=-100.
        r=self.b.solve(F)
        self.assertAlmostEqual(max(r['M']),100*self.L/4,places=5)
        self.assertAlmostEqual(-r['u'][20],100*self.L**3/(48*self.EI),places=9)

    def test_two_equal_spans(self):
        b=Beam(np.linspace(0,40,41),self.EI,[0,20,40]);q=30.
        r=b.distributed(-q)
        self.assertAlmostEqual(min(r['M']),-q*20**2/8,places=4)
        np.testing.assert_allclose(r['R'],[3*q*20/8,5*q*20/4,3*q*20/8],rtol=1e-8)

    def test_lane_envelope_and_shear_peak(self):
        il=self.b.influences()
        lo,hi=envelope(il['M'],il['weights'],10.5,360)
        self.assertAlmostEqual(max(hi),10.5*20**2/8+360*20/4,places=4)
        vlow,vhigh=envelope(il['V'],il['weights'],10.5,432)
        self.assertAlmostEqual(vhigh[0],10.5*20/2+432,delta=.001)
        self.assertLess(max(abs(lo)),1e-5)

    def test_constant_prestress_simply_supported(self):
        r=self.b.initial_moment(lambda x:np.zeros_like(x)-1000.)
        np.testing.assert_allclose(r['secondary_M'],0,atol=1e-6)
        np.testing.assert_allclose(r['M'],-1000.,atol=1e-6)
        self.assertGreater(r['u'][20],0)

    def test_support_reaction_for_load_on_support(self):
        F=np.zeros(self.b.nd);F[0]=-100.
        r=self.b.solve(F)
        np.testing.assert_allclose(r['R'],[100.,0.],atol=1e-10)
        np.testing.assert_allclose(r['M'],0,atol=1e-10)

    def test_invalid_inputs(self):
        for raw in [{'main_span':49},{'main_span':151},{'lanes':3.5},{'lanes':True},
                    {'lanes':2,'layout':'separated'},{'lanes':6,'layout':'single'},
                    {'mesh_length':float('nan')},
                    {'height_mid':1},{'cells':5},{'unknown':1},{'auto_resize':'false'}]:
            with self.subTest(raw=raw):
                with self.assertRaises(ValueError):validate(raw)


class SchemeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.result=analyse({})

    def test_default_request_and_balance(self):
        r=self.result
        self.assertEqual(r['input']['lanes'],4)
        self.assertEqual(r['geometry']['spans'],[60.,100.,60.])
        self.assertLess(r['verification']['force_balance_error_kn'],1e-4)
        self.assertFalse(r['complete_code_compliance'])
        self.assertEqual(len(r['candidates']),11)
        quarter=next(v for v in r['controls'] if v['name']=='主跨四分点')
        self.assertAlmostEqual(quarter['x'],85.)

    def test_symmetry(self):
        a=self.result['analysis']
        np.testing.assert_allclose(a['M_dead'],a['M_dead'][::-1],rtol=1e-6,atol=.01)
        np.testing.assert_allclose(a['V_dead'],-np.array(a['V_dead'][::-1]),rtol=1e-6,atol=.01)

    def test_scope_and_decks(self):
        r=self.result
        self.assertIn('prestress',r)
        self.assertIn('construction_stages',r)
        self.assertIn('structural_verification',r)
        self.assertEqual(r['geometry']['deck_count'],2)
        self.assertEqual(r['geometry']['width'],9.)
        self.assertEqual(r['geometry']['total_width'],19.)
        self.assertEqual(r['loads']['traffic']['effective_lanes'],2.)
        self.assertAlmostEqual(r['quantities']['concrete_total_m3'],2*r['quantities']['concrete_per_deck_m3'])
        self.assertTrue(all(len(v)==len(r['analysis']['x']) for v in r['analysis'].values()))

    def test_80_and_120_m(self):
        for span in [80.,120.]:
            r=analyse({'main_span':span})
            self.assertAlmostEqual(r['geometry']['total_length'],2.2*span)
            self.assertAlmostEqual(r['geometry']['height_mid'],2.8*span/100)
            self.assertAlmostEqual(r['geometry']['height_pier'],5.8*span/100)
            self.assertLess(r['verification']['force_balance_error_kn'],1e-4)
            self.assertTrue(np.isfinite(np.array(r['analysis']['M_uls_max'])).all())

    def test_mesh_convergence(self):
        fine=analyse({'mesh_length':1.})
        for key in ['M_uls_max','M_uls_min','V_uls']:
            a=np.max(np.abs(self.result['analysis'][key]));b=np.max(np.abs(fine['analysis'][key]))
            self.assertLess(abs(a-b)/b,.02,key)

    def test_v011_traceability_and_displacement(self):
        r=self.result;a=r['analysis']
        self.assertEqual(r['version'],'0.12.0')
        self.assertEqual(r['status_code'],'COURSE_SCOPE_COMPLETE')
        self.assertTrue(r['course_scope_complete'])
        self.assertFalse(r['complete_code_compliance'])
        self.assertEqual(r['state_schema'],'bridgegen.design_state.v0.12')
        self.assertIn('out_of_course_scope',r)
        self.assertEqual(r['code_profile']['id'],'JTG_D60_2015_JTG_3362_2018')
        self.assertEqual({v['id'] for v in r['load_cases']},
                         {'G1_SELF','G2_PAVEMENT','G2_BARRIER','G2_OTHER','Q_TRAFFIC',
                          'P_PRESTRESS','C_FORM_TRAVELER'})
        self.assertEqual({v['id'] for v in r['combinations']},
                         {'ULS_BASIC','SLS_STANDARD','SLS_FREQUENT','SLS_QUASI_PERMANENT'})
        cases=r['loads']['traffic']['transverse_cases']
        self.assertEqual(len(cases),3)
        self.assertEqual(cases[-1]['active_lanes'],[1,2])
        self.assertAlmostEqual(cases[-1]['resultant_eccentricity_m'],0.)
        for key in ['deflection_dead','deflection_live_min','deflection_live_max',
                    'deflection_uls_min','deflection_uls_max',
                    'deflection_standard_min','deflection_standard_max']:
            self.assertEqual(len(a[key]),len(a['x']))
            self.assertTrue(np.isfinite(a[key]).all())
        expected=1000*max(np.max(np.abs(a['deflection_standard_total_min'])),
                          np.max(np.abs(a['deflection_standard_total_max'])))
        self.assertAlmostEqual(r['verification']['max_standard_deflection_mm'],expected)
        origins={v['name']:v['origin'] for v in r['input_audit']}
        self.assertEqual(origins['main_span'],'程序默认')
        changed=analyse({'main_span':90})
        self.assertEqual(next(v for v in changed['input_audit'] if v['name']=='main_span')['origin'],'用户输入')

    def test_span_matching_manual_asymmetry_and_v09_trace(self):
        suggestion=span_suggestions(120,.625)
        self.assertEqual(suggestion['arrangement'],[75.,120.,75.])
        automatic=analyse({'main_span':120.,'side_span_ratio':.625})
        self.assertEqual(automatic['geometry']['spans'],[75.,120.,75.])
        self.assertTrue(automatic['geometry']['is_symmetric'])
        manual=analyse({'side_span_mode':'manual','left_side_span':55.,
                        'main_span':100.,'right_side_span':65.})
        self.assertEqual(manual['geometry']['spans'],[55.,100.,65.])
        self.assertFalse(manual['geometry']['is_symmetric'])
        self.assertLess(manual['verification']['force_balance_error_kn'],1e-4)
        self.assertTrue(np.isfinite(np.asarray(manual['analysis']['M_uls_max'])).all())
        required={'id','chapter','name','input','formula','intermediate','result',
                  'unit','source','result_path'}
        self.assertGreater(len(manual['calculation_trace']),20)
        self.assertTrue(all(required <= set(row) for row in manual['calculation_trace']))
        self.assertEqual([row['id'] for row in manual['sensitivity']],
                         ['BASE','G_PLUS_5','Q_PLUS_5'])
        self.assertGreater(manual['sensitivity'][1]['moment_change_ratio'],0.)
        self.assertGreater(manual['sensitivity'][2]['moment_change_ratio'],0.)

    def test_span_section_suggestions_are_editable_and_valid(self):
        for span in [50.,80.,100.,120.,150.]:
            suggestion=section_suggestions(span)
            self.assertEqual(suggestion['height_reference_span'],span)
            self.assertLess(suggestion['height_mid'],suggestion['height_pier'])
            parameters={k:v for k,v in suggestion.items() if k!='suggestion_basis'}
            parameters['main_span']=span
            result=analyse(parameters)
            self.assertIn(result['status_code'],{'COURSE_SCOPE_COMPLETE','COURSE_SCOPE_FAILED'})
            if 80<=span<=120:
                self.assertEqual(result['status_code'],'COURSE_SCOPE_COMPLETE')
                self.assertTrue(result['structural_verification']['summary']['all_named_checks_pass'])
            self.assertGreaterEqual(result['geometry']['height_mid'],1.8)
            self.assertLess(result['verification']['force_balance_error_kn'],1e-4)

    def test_prestress_quantity_losses_and_effects(self):
        r=self.result;p=r['prestress'];a=r['analysis'];profile=p['profile']
        end_rule=p['end_anchor_rule']
        self.assertEqual(end_rule['mode'],'auto_kern')
        self.assertTrue(np.all(np.asarray(end_rule['eccentricity_m'])<=np.asarray(end_rule['kern_upper_m'])+1e-9))
        self.assertTrue(np.all(np.asarray(end_rule['eccentricity_m'])>=np.asarray(end_rule['kern_lower_m'])-1e-9))
        self.assertIn('P_END_KERN',{row['id'] for row in r['calculation_records']})
        self.assertEqual(p['strand_count']%p['strands_per_tendon'],0)
        self.assertEqual(p['tendon_count']*p['strands_per_tendon'],p['strand_count'])
        self.assertGreaterEqual(p['minimum_force_margin_kn'],-1e-6)
        self.assertTrue(np.all(np.asarray(profile['sigma_effective']) < p['jacking_stress_mpa']))
        self.assertGreater(p['loss_summary']['total_mpa_mean'],0)
        np.testing.assert_allclose(np.asarray(a['M_prestress_primary'])+
                                   np.asarray(a['M_prestress_secondary']),
                                   np.asarray(a['M_prestress_total']),rtol=1e-9,atol=1e-6)
        e=np.asarray(profile['eccentricity'])
        self.assertTrue(np.all(e <= np.asarray(profile['lower_eccentricity_limit'])+1e-9))
        self.assertTrue(np.all(e >= -np.asarray(profile['upper_eccentricity_limit'])-1e-9))
        np.testing.assert_allclose(e,e[::-1],rtol=1e-7,atol=1e-7)

    def test_construction_stages_are_monotonic_and_finite(self):
        cs=self.result['construction_stages'];stages=cs['stages']
        self.assertEqual([v['pier_id'] for v in cs['piers']],['P1','P2'])
        self.assertIn(cs['governing_pier_id'],{'P1','P2'})
        self.assertTrue(all(len(v['stages'])==len(stages) for v in cs['piers']))
        cantilever=[v for v in stages if v['stage_id'].startswith('C') and v['stage_id']!='CLOSE']
        lengths=[v['active_length_each_side_m'] for v in cantilever]
        self.assertEqual(lengths,sorted(lengths))
        tendons=[v['activated_tendons'] for v in cantilever]
        self.assertEqual(tendons,sorted(tendons))
        self.assertFalse(np.allclose(np.asarray(tendons)/cantilever[-1]['total_tendons'],
                                     np.asarray(lengths)/lengths[-1]))
        self.assertEqual(len(cantilever),cs['segment_stage_count'])
        self.assertEqual(stages[-1]['stage_id'],'SERVICE')
        for row in stages:
            self.assertIn(row['governing_pier_id'],{'P1','P2'})
            self.assertEqual(set(row['pier_results']),{'P1','P2'})
            for key in ['net_root_moment_knm','top_stress_mpa','bottom_stress_mpa','tip_deflection_mm']:
                self.assertTrue(np.isfinite(row[key]))

    def test_stress_formula_reproduction(self):
        r=self.result;a=r['analysis'];j=len(a['x'])//2
        P=a['prestress_force_effective'][j];A=a['area'][j];e=a['tendon_eccentricity'][j]
        W=a['section_modulus_top'][j];M=a['M_standard_max'][j]+a['M_prestress_secondary'][j]
        expected=(P/A-P*e/W+M/W)/1000
        self.assertAlmostEqual(a['stress_top_standard_max'][j],expected,places=8)

    def test_controlling_combination_is_reproducible(self):
        r=self.result;a=r['analysis'];t=r['loads']['traffic'];j=len(a['x'])//2
        self.assertAlmostEqual(a['M_standard_max'][j],
            a['M_dead1'][j]+a['M_dead2'][j]+(1+t['impact'])*a['M_live_max'][j])
        for control in r['controls']:
            for key in ['M_min','M_max','V_min','V_max','W_min','W_max']:
                trace=control['governing'][key]
                self.assertEqual(trace['combination_id'],'ULS_BASIC')
                self.assertTrue(0 <= trace['point_load_x_m'] <= r['geometry']['total_length'])
                self.assertIn(trace['transverse_case'],
                              {'Q_LANE_1','Q_LANE_2','Q_LANE_1_2'})

    def test_named_verifications_and_reinforcement(self):
        r=self.result;v=r['structural_verification'];a=r['analysis']
        self.assertEqual(v['summary']['total'],6)
        self.assertTrue(v['summary']['all_named_checks_pass'])
        self.assertTrue(all(item['status']=='PASS' for item in v['checks'].values()))
        self.assertEqual(v['reinforcement']['top_bar_count']%2,0)
        self.assertEqual(v['reinforcement']['bottom_bar_count']%2,0)
        self.assertLessEqual(max(a['flexural_utilization_positive']),1.0)
        self.assertLessEqual(max(a['flexural_utilization_negative']),1.0)
        self.assertLessEqual(max(a['shear_utilization']),1.0)
        self.assertAlmostEqual(
            a['deflection_standard_total_min'][10],
            a['deflection_standard_min'][10]+a['deflection_prestress'][10])

    def test_section_dependent_tendon_area(self):
        p=self.result['prestress']['profile']
        counts=np.asarray(p['active_tendon_count'])
        self.assertGreater(counts.max(),counts.min())
        np.testing.assert_allclose(counts,counts[::-1])
        self.assertGreater(self.result['prestress']['loss_summary']['effective_ratio_min'],0.60)

    def test_design_state_freezes_top_level_payload(self):
        state=DesignState.freeze('x','COURSE_SCOPE_COMPLETE',{'a':1})
        with self.assertRaises(TypeError):state.payload['a']=2


class ExtendedRangeTests(unittest.TestCase):
    def test_metadata_and_elevation_inputs_do_not_invent_site_levels(self):
        cfg=validate({})
        self.assertEqual(cfg['elevation_mode'],'relative')
        self.assertEqual(cfg['deck_elevation'],0.)
        self.assertEqual(cfg['designer_name'],'')
        self.assertEqual(cfg['student_id'],'')
        with self.assertRaisesRegex(ValueError,'用户明确填写'):
            validate({'elevation_mode':'absolute'})
        absolute=validate({'elevation_mode':'absolute','deck_elevation':-12.5,
            'longitudinal_slope':.02,'designer_name':' 张三 ','student_id':'202608',
            'institution':'某大学','class_name':'桥梁1班','supervisor':'李老师',
            'drawing_date':'2026-10-09'})
        self.assertEqual(absolute['designer_name'],'张三')
        geometry=Geometry(absolute)
        self.assertAlmostEqual(float(geometry.deck_top_elevation(geometry.length/2)),-12.5)
        np.testing.assert_allclose(geometry.deck_top_elevation([0,geometry.length]),[-14.7,-10.3])
        for raw in ({'elevation_mode':'invented'},{'deck_elevation':float('nan')},
                    {'longitudinal_slope':.061},{'student_id':1234},
                    {'designer_name':'第一行\n第二行'},{'designer_name':'名'*17},
                    {'student_id':'8'*33},{'drawing_date':'2026年10月09日'}):
            with self.subTest(raw=raw):
                with self.assertRaises(ValueError):validate(raw)

    def test_150_m_span_matching_and_live_load_boundary(self):
        self.assertEqual(span_suggestions(150,.8)['arrangement'],[120.,150.,120.])
        for lanes in (2,4,6):
            suggestion=section_suggestions(150,lanes)
            self.assertEqual(suggestion['height_reference_span'],150.)
            self.assertEqual(suggestion['height_mid'],4.2)
            self.assertEqual(suggestion['height_pier'],8.7)
            result=analyse({'main_span':150.,'lanes':lanes})
            traffic=result['loads']['traffic']
            self.assertEqual(result['version'],'0.12.0')
            self.assertEqual(traffic['qk'],10.5)
            self.assertEqual(traffic['pk'],360.)
            self.assertEqual(traffic['controlling_span_m'],150.)
            self.assertEqual(traffic['longitudinal_factor'],1.)
            self.assertLess(result['verification']['force_balance_error_kn'],1e-4)
            self.assertTrue(np.isfinite(np.asarray(result['analysis']['M_uls_min'])).all())
            if lanes==6:
                # Independent force-method checking confirms that signed
                # tendon shear leaves this initial scheme underreinforced.
                self.assertEqual(result['status_code'],'COURSE_SCOPE_FAILED')
                self.assertEqual(result['structural_verification']['checks']['shear']['status'],'FAIL')
            else:self.assertEqual(result['status_code'],'COURSE_SCOPE_COMPLETE')
            self.assertEqual(result['input']['stirrup_diameter_mm'],20. if lanes==6 else 18.)

    def test_explicit_end_eccentricity_is_preserved_and_can_fail_crack_check(self):
        with self.assertRaisesRegex(ValueError,'保护层'):
            validate({'main_span':150.,'prestress_end_eccentricity_m':12.})
        result=analyse({'main_span':150.,'lanes':2,'prestress_end_eccentricity_m':2.2})
        end_rule=result['prestress']['end_anchor_rule']
        self.assertEqual(end_rule['mode'],'user_explicit')
        self.assertEqual(end_rule['eccentricity_m'],[2.2,2.2])
        self.assertEqual(result['input']['prestress_end_eccentricity_m'],2.2)
        self.assertEqual(result['status_code'],'COURSE_SCOPE_FAILED')
        self.assertEqual(result['structural_verification']['checks']['crack_resistance']['status'],'FAIL')

    def test_new_range_initial_values_keep_explicit_underreinforcement(self):
        suggested=validate({'main_span':150.,'lanes':4})
        self.assertEqual(suggested['web_mid'],.6)
        self.assertEqual(suggested['web_pier'],.9)
        self.assertEqual(suggested['stirrup_diameter_mm'],18.)
        legacy={"main_span":150.,"lanes":6,"top_thickness":.3,"tip_thickness":.2,
                "bottom_mid":.28,"bottom_pier":.7,"web_mid":.75,"web_pier":1.12,
                "stirrup_diameter_mm":18.,"top_haunch_horizontal":.7,
                "top_haunch_vertical":.25,"bottom_chamfer_horizontal":.6,
                "bottom_chamfer_vertical":.3}
        self.assertEqual(validate(legacy)['stirrup_diameter_mm'],18.)
        result=analyse(legacy)
        self.assertEqual(result['status_code'],'COURSE_SCOPE_FAILED')
        self.assertEqual(result['structural_verification']['checks']['shear']['status'],'FAIL')

    def test_span_lane_geometry_matrix_and_short_span_floor(self):
        for span in [50.,80.,120.,150.]:
            for lanes in [2,4,6]:
                with self.subTest(span=span,lanes=lanes):
                    cfg=validate({'main_span':span,'lanes':lanes})
                    geometry=Geometry(cfg)
                    decks=1 if lanes==2 else 2
                    self.assertEqual(cfg['layout'],'single' if lanes==2 else 'separated')
                    self.assertEqual(geometry.deck_count,decks)
                    self.assertEqual(geometry.lanes_per_deck,lanes//decks)
                    self.assertEqual(geometry.width,(lanes//decks)*3.5+2.)
                    self.assertEqual(geometry.total_width,decks*geometry.width+(decks-1))
                    self.assertEqual(list(geometry.spans),[.6*span,span,.6*span])
                    mid=geometry.section(geometry.left_side+span/2)
                    self.assertAlmostEqual(mid['h'],max(1.8,.028*span))
                    self.assertGreater(mid['A'],0)
                    self.assertGreater(mid['I'],0)

    def test_three_lane_subsets_and_code_factors(self):
        profile=get_profile(DEFAULT_PROFILE)
        for lanes, count, multiplier in [(2,3,2.),(4,3,2.),(6,7,2.34)]:
            with self.subTest(lanes=lanes):
                cfg=validate({'lanes':lanes})
                cases=_transverse_cases(cfg,Geometry(cfg),profile)
                self.assertEqual(len(cases),count)
                self.assertAlmostEqual(max(row['vertical_multiplier'] for row in cases),multiplier)
                factors={len(row['active_lanes']):row['lane_factor'] for row in cases}
                self.assertEqual(factors[1],1.20)
                self.assertEqual(factors[2],1.00)
                if lanes==6:
                    self.assertEqual(factors[3],.78)
                    self.assertEqual(cases[-1]['active_lanes'],[1,2,3])
                    self.assertEqual(cases[-1]['lane_centres_m'],[-3.5,0.,3.5])
                low,high,*_=_apply_transverse(np.array([-100.]),np.array([100.]),cases)
                self.assertAlmostEqual(low[0],-100*multiplier)
                self.assertAlmostEqual(high[0],100*multiplier)

    def test_vehicle_positions_follow_unequal_edge_margins(self):
        cfg=validate({'lanes':6,'inner_margin':.5,'outer_margin':1.5})
        cases=_transverse_cases(cfg,Geometry(cfg),get_profile(DEFAULT_PROFILE))
        self.assertEqual(cases[-1]['lane_centres_m'],[-4.,-.5,3.])
        self.assertEqual(cases[0]['name'],'内侧车道')
        self.assertEqual(cases[2]['name'],'外侧车道')

    def test_three_lane_initial_webs_and_stirrups_are_visible_and_editable(self):
        suggestions=section_suggestions(120,6)
        self.assertEqual(suggestions['web_mid'],.71)
        self.assertEqual(suggestions['web_pier'],1.05)
        self.assertEqual(suggestions['stirrup_diameter_mm'],18.)
        defaults=validate({'main_span':120.,'lanes':6})
        self.assertEqual(defaults['web_mid'],suggestions['web_mid'])
        self.assertEqual(defaults['web_pier'],suggestions['web_pier'])
        self.assertEqual(defaults['stirrup_diameter_mm'],18.)
        explicit=validate({'main_span':120.,'lanes':6,'web_mid':.55,
                           'web_pier':.8,'stirrup_diameter_mm':16.})
        self.assertEqual(explicit['web_mid'],.55)
        self.assertEqual(explicit['web_pier'],.8)
        self.assertEqual(explicit['stirrup_diameter_mm'],16.)
        four=validate({'main_span':120.,'lanes':4})
        self.assertEqual(four['web_mid'],.55)
        self.assertEqual(four['web_pier'],.8)
        self.assertEqual(four['stirrup_diameter_mm'],16.)

    def test_explicit_underreinforced_three_lane_box_keeps_failed_shear(self):
        result=analyse({'main_span':120.,'lanes':6,'web_mid':.55,
                        'web_pier':.8,'stirrup_diameter_mm':16.})
        self.assertEqual(result['status_code'],'COURSE_SCOPE_FAILED')
        self.assertEqual(result['structural_verification']['checks']['shear']['status'],'FAIL')
        self.assertGreater(result['structural_verification']['checks']['shear']['max_utilization'],1.)
        self.assertFalse(result['course_scope_complete'])

    def test_automatic_spans_replace_stale_manual_values(self):
        cfg=validate({'main_span':50.,'left_side_span':999.,'right_side_span':999.})
        self.assertEqual(cfg['left_side_span'],30.)
        self.assertEqual(cfg['right_side_span'],30.)
        self.assertEqual(span_suggestions(50,.5)['arrangement'],[25.,50.,25.])
        with self.assertRaises(ValueError):
            validate({'main_span':50.,'side_span_mode':'manual','left_side_span':20.,'right_side_span':30.})

    def test_actual_pier_height_exceeds_floor_limited_mid_height(self):
        with self.assertRaisesRegex(ValueError,'实际墩顶梁高'):
            validate({'main_span':50.,'height_pier':3.5,'top_thickness':.26,
                'top_haunch_vertical':.1,'bottom_mid':.22,'bottom_pier':.26,
                'bottom_chamfer_vertical':.1,'cross_slope':0.})

    def test_full_calculation_for_new_span_and_lane_modes(self):
        for span,lanes in [(50.,2),(50.,4),(50.,6),(120.,6)]:
            with self.subTest(span=span,lanes=lanes):
                result=analyse({'main_span':span,'lanes':lanes})
                geometry=result['geometry']
                self.assertEqual(geometry['deck_count'],1 if lanes==2 else 2)
                self.assertEqual(geometry['lanes_per_deck'],2 if lanes!=6 else 3)
                self.assertLess(result['verification']['force_balance_error_kn'],1e-4)
                for field in ['M_uls_max','M_uls_min','V_uls','deflection_standard_total_min']:
                    self.assertTrue(np.isfinite(np.asarray(result['analysis'][field])).all())
                self.assertAlmostEqual(result['quantities']['concrete_total_m3'],
                    geometry['deck_count']*result['quantities']['concrete_per_deck_m3'])
                self.assertEqual(len(result['loads']['traffic']['transverse_cases']),7 if lanes==6 else 3)
                if span==120 and lanes==6:
                    self.assertEqual(result['status_code'],'COURSE_SCOPE_FAILED')
                    self.assertEqual(result['structural_verification']['checks']['shear']['status'],'FAIL')
                else:self.assertEqual(result['status_code'],'COURSE_SCOPE_COMPLETE')


if __name__=='__main__':unittest.main(verbosity=2)
