
import geopandas
import json
from shapely.geometry import shape, Point, box
import shapely.speedups
from shapely.strtree import STRtree
import numpy

class PointInPolygon:
    def __init__(self, polygons=None, data=None):
        shapely.speedups.enable()
        self.original_polygons = list()
        self.polygons = polygons
        self.data = data
        self.poly_df = None
        self.polygon_sindex = None
        self.points = None
        self.point_sindex = None
        self.point_df = None
        self.poly_subdivide = True
        self.rindex = None
        self.shapely_index = None

    def make_datafame(self, type='polygon', data=None, crs={'init' :'epsg:4326'}):
        if type.lower() in ['polygon','polygons']:
            if self.data.size >0:
                gdf = geopandas.GeoDataFrame(geometry=self.polygons, data=self.data.tolist())
            else:
                gdf = geopandas.GeoDataFrame(geometry=self.polygons)
            self.polygon_sindex = gdf.sindex
            self.poly_df = gdf
        elif type.lower()in ['point','points']:
            gdf = geopandas.GeoDataFrame(geometry=self.points)
            self.point_sindex = gdf.sindex
            self.point_df = gdf
        gdf.crs = crs

    def make_polygons_geojson(self, geojson, id_column='ENAME',subdivide=True, division_threshold=.1):
        polygons = []
        with open(geojson, 'r') as f:
            js = json.load(f)
        for feature in js['features']:
            polygon = shape(feature['geometry'])
            self.original_polygons.append(polygon)
            if polygon.is_valid:
                if subdivide:
                    divided_polygons = self._divide_polygons(polygon, division_threshold)
                    for n, x in enumerate(divided_polygons):
                        name = '{}'.format(feature['properties'][id_column])
                        polygons.append([name, x])
                else:
                    self.poly_subdivide = False
                    name = feature['properties'][id_column]
                    polygons.append([name,polygon])
            else:
                print 'invalid poly {}'.format(feature)
        self.polygons = numpy.array([x[1] for x in polygons])
        self.data = numpy.array([x[0] for x in polygons])
        return self.polygons, self.data

    def add_points(self, latlongs):
        points = []
        if type(latlongs[0]) is list:
            for n in latlongs:
                point = Point(n[0], n[1])
                points.append(point)
        else:
            points.append(Point(latlongs[0], latlongs[1]))
        self.points = points
        return points

    def _divide_polygons(self, geometry, threshold):
        bounds = geometry.bounds
        xmin = int(bounds[0] // threshold)
        xmax = int(bounds[2] // threshold)
        ymin = int(bounds[1] // threshold)
        ymax = int(bounds[3] // threshold)
        ncols = int(xmax - xmin + 1)
        nrows = int(ymax - ymin + 1)
        result = []
        for i in range(xmin, xmax+1):
            for j in range(ymin, ymax+1):
                b = box(i*threshold, j*threshold, (i+1)*threshold, (j+1)*threshold)
                g = geometry.intersection(b)
                if g.is_empty:
                    continue
                result.append(g)
        return result

    def point_in_poly_gdf(self, x, y):
        possible_matches_index = list(self.polygon_sindex.intersection([x, y]))
        if not possible_matches_index:
            return None
        elif len(possible_matches_index)==1:
            precise_matches = self.poly_df.iloc[possible_matches_index]
        else:
            possible_matches = self.poly_df.iloc[possible_matches_index]
            precise_matches = possible_matches[possible_matches.intersects(Point(x, y))]
        if not precise_matches.empty:
            p = precise_matches.iloc[0][0]
        else:
            p = None
        return p

    def make_tree(self):
        from rtree import index
        idx = index.Index()
        count = -1
        for q in self.polygons:
            count += 1
            idx.insert(count, (q.bounds))
        self.rindex = idx
        return idx

    def point_on_polys_rtree(self,x,y):
        for idx in self.rindex.intersection((x, y)):
            if Point(x,y).within(self.polygons[idx]):
                return self.data[idx]

    def point_on_polys_shapely(self, x, y):
        pt = Point(x, y)
        result = self.shapely_index.query(pt)
        for x, poly in enumerate(result):
            if pt.within(poly):
                for x, p in enumerate(self.original_polygons):
                    if p.intersects(poly):
                        return self.data[x]

    def make_shapely_index(self):
        shapely_index = STRtree(self.polygons)
        self.shapely_index = shapely_index

    def spatial_join(self):
        return geopandas.sjoin(self.point_df, self.poly_df, how='inner', op='within')