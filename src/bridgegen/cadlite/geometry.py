"""Single-cell deck geometry for a single or two separated carriageways.

All lengths are metres. The solid is the outer polygon less the actual chamfered
void, so plotted outlines and longitudinal A/I/self-weight share one geometry.
"""
import numpy as np


def _moments(points):
    p = np.asarray(points, dtype=float)
    x, y = p[:, 0], p[:, 1]
    xn, yn = np.roll(x, -1), np.roll(y, -1)
    cross = x*yn-xn*y
    area = 0.5*np.sum(cross)
    cy = np.sum((y+yn)*cross)/(6*area)
    ix0 = np.sum((y*y+y*yn+yn*yn)*cross)/12
    direction = 1 if area > 0 else -1
    return direction*area, cy, direction*ix0


def _clip_horizontal(points, level, keep_above):
    """Clip a polygon in the depth coordinate against a horizontal line."""
    result = []
    if not points:
        return result
    for start, end in zip(points, points[1:]+points[:1]):
        inside_start = start[1] <= level if keep_above else start[1] >= level
        inside_end = end[1] <= level if keep_above else end[1] >= level
        if inside_start:
            result.append(start)
        if inside_start != inside_end:
            dy = end[1]-start[1]
            if abs(dy) > 1e-12:
                ratio = (level-start[1])/dy
                result.append((start[0]+ratio*(end[0]-start[0]), level))
    return result


def _polygon_width(points, level):
    intersections = []
    for start, end in zip(points, points[1:]+points[:1]):
        y1, y2 = start[1], end[1]
        if (y1 <= level < y2) or (y2 <= level < y1):
            ratio = (level-y1)/(y2-y1)
            intersections.append(start[0]+ratio*(end[0]-start[0]))
    intersections.sort()
    return sum(intersections[i+1]-intersections[i]
               for i in range(0, len(intersections)-1, 2))


class Geometry:
    def __init__(self, cfg, scale=1.0):
        self.c = cfg
        self.scale = scale
        self.main = cfg["main_span"]
        self.left_side = cfg["left_side_span"]
        self.right_side = cfg["right_side_span"]
        self.side = self.left_side
        self.is_symmetric = abs(self.left_side-self.right_side) < 1e-9
        self.spans = np.array([self.left_side, self.main, self.right_side])
        self.supports = np.r_[0.0, np.cumsum(self.spans)]
        self.length = float(self.supports[-1])
        self.deck_count = 1 if cfg.get("lanes", 4) == 2 else 2
        self.lanes_per_deck = cfg.get("lanes", 4)//self.deck_count
        self.width = self.lanes_per_deck*cfg["lane_width"]+2*cfg["barrier_width"]+cfg["inner_margin"]+cfg["outer_margin"]
        self.box_width = self.width-2*cfg["cantilever_width"]
        self.total_width = self.deck_count*self.width+(self.deck_count-1)*cfg["deck_gap"]
        self.webs = 2

    def factor(self, x):
        x = np.asarray(x)
        a, b = self.supports[1:3]
        p = self.c["height_curve_exponent"]
        return np.where(x < a, (x/a)**p,
                        np.where(x > b, ((self.length-x)/self.right_side)**p,
                                 (np.abs(x-(a+b)/2)/(self.main/2))**p))

    def _dimensions(self, x):
        c = self.c
        factor = float(np.clip(self.factor(x), 0, 1))
        ratio = self.main/c["height_reference_span"]
        # Retain the span ratio but prevent short-span starters from losing
        # the clear cavity between the slab haunches and lower chamfers.
        hm = max(1.8, c["height_mid"]*ratio)*self.scale
        hp = c["height_pier"]*ratio*self.scale
        return (hm+(hp-hm)*factor,
                c["bottom_mid"]+(c["bottom_pier"]-c["bottom_mid"])*factor,
                c["web_mid"]+(c["web_pier"]-c["web_mid"])*factor)

    def _polygons(self, x):
        c = self.c
        h, tb, tw = self._dimensions(x)
        B, b = self.width, self.box_width
        tt = c["top_thickness"]
        slope = c["cross_slope"]
        tip = c["tip_thickness"]
        uh = c["top_haunch_horizontal"]
        uv = c["top_haunch_vertical"]
        bh = c["bottom_chamfer_horizontal"]
        bv = c["bottom_chamfer_vertical"]
        top = lambda lateral: slope*lateral
        left, right = -b/2+tw, b/2-tw
        outer = [(-B/2, top(-B/2)), (B/2, top(B/2)),
                 (B/2, top(B/2)+tip), (b/2, top(b/2)+tt+uv),
                 (b/2, h), (-b/2, h),
                 (-b/2, top(-b/2)+tt+uv), (-B/2, top(-B/2)+tip)]
        void = [(left, top(left)+tt+uv),
                (left+uh, top(left+uh)+tt),
                (right-uh, top(right-uh)+tt),
                (right, top(right)+tt+uv),
                (right, h-tb-bv), (right-bh, h-tb),
                (left+bh, h-tb), (left, h-tb-bv)]
        if min(h-tb-bv-(top(left)+tt+uv),
               h-tb-bv-(top(right)+tt+uv)) <= 0.5:
            raise ValueError("箱室净高不足，倒角与顶底板发生冲突")
        return outer, void, h, tb, tw

    def _section_one(self, x):
        outer, void, h, tb, tw = self._polygons(float(x))
        ao, yo, io = _moments(outer)
        av, yv, iv = _moments(void)
        area = ao-av
        cy = (ao*yo-av*yv)/area
        inertia = io-iv-area*cy*cy
        top_y = min(p[1] for p in outer)
        bottom_y = max(p[1] for p in outer)
        if area <= 0 or inertia <= 0:
            raise ValueError("箱梁截面面积或惯性矩无效")
        return dict(h=h, tt=self.c["top_thickness"], tb=tb, tw=tw,
                    A=area, I=inertia, y=cy, top_y=top_y, bottom_y=bottom_y,
                    Wt=inertia/(cy-top_y), Wb=inertia/(bottom_y-cy))

    def compression_block(self, x, depth, top=True):
        """Return exact solid area and centroid of a rectangular stress block."""
        outer, void, *_ = self._polygons(float(x))
        top_y = min(p[1] for p in outer)
        bottom_y = max(p[1] for p in outer)
        level = top_y+depth if top else bottom_y-depth
        clipped_outer = _clip_horizontal(outer, level, top)
        clipped_void = _clip_horizontal(void, level, top)
        if len(clipped_outer) < 3:
            return 0.0, level
        ao, yo, _ = _moments(clipped_outer)
        if len(clipped_void) >= 3:
            av, yv, _ = _moments(clipped_void)
        else:
            av, yv = 0.0, 0.0
        area = ao-av
        centroid = (ao*yo-av*yv)/area if area > 1e-12 else level
        return area, centroid

    def shear_properties(self, x):
        """First moment and total material width at the gross-section centroid."""
        outer, void, *_ = self._polygons(float(x))
        section = self._section_one(float(x))
        cy = section["y"]
        area, centroid = self.compression_block(x, cy-section["top_y"], top=True)
        first_moment = area*(cy-centroid)
        width = _polygon_width(outer, cy)-_polygon_width(void, cy)
        return dict(Q=first_moment, b=max(width, 1e-6))

    def section(self, x):
        array = np.asarray(x)
        if array.ndim == 0:
            return self._section_one(float(array))
        rows = [self._section_one(value) for value in array.flat]
        return {key: np.array([row[key] for row in rows]).reshape(array.shape)
                for key in rows[0]}

    def mesh(self):
        xs = [0.0]
        for start, span in zip(self.supports[:-1], self.spans):
            n = max(8, int(np.ceil(span/self.c["mesh_length"])))
            # Include span quarter points exactly in the control-section table.
            n += (-n) % 4
            xs.extend(np.linspace(start, start+span, n+1)[1:])
        return np.array(xs)

    def outlines(self, x):
        outer, void, *_ = self._polygons(x)
        # DXF view uses upward-positive coordinates; section integration uses depth.
        return ([(a, -b) for a, b in outer],
                [[(a, -b) for a, b in void]])
