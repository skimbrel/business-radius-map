import json
import sys
import time

from lxml import etree
from pykml.factory import KML_ElementMaker as KML
import requests

import kmlcircle

APP_TOKEN = 's1kVVl7BIHNpLzkhz9WirUXYY'
CHUNK_SIZE = 1000
DATA_URL = 'http://data.sfgov.org/resource/dg5s-2n6f'
GEOCODER_URL = 'http://maps.googleapis.com/maps/api/geocode/json'
ADDRESS_FORMAT = '{street}, San Francisco, CA {zipcode}'
RADIUS = 22.86  # 75 feet in meters
CIRCLE_SEGMENTS = 20  # An okay approximation.


def get_businesses(data_url):
    business_list = []

    has_more = True
    offset = 0
    while has_more:
        # Retrieve objects from the SODA resource in chunks.
        response = requests.get(
            DATA_URL,
            params={
                '$limit': CHUNK_SIZE,
                '$offset': offset,
                '$$app_token': APP_TOKEN,
            },
        )

        if response.status_code == 200:
            decoded_list = json.loads(response.content)
            if len(decoded_list) < CHUNK_SIZE:
                has_more = False
            else:
                offset += CHUNK_SIZE
            business_list.extend(decoded_list)
        elif response.status_code == 202:
            # Socrata said it was taking too long. Sleep a bit and rerun this
            # request to get the eventual result.
            time.sleep(5)

    return business_list


def geocode(street, zipcode):
    response = requests.get(
        GEOCODER_URL,
        params={
            'sensor': 'false',
            'address': ADDRESS_FORMAT.format(street=street, zipcode=zipcode),
        },
    )
    if response.ok:
        decoded = json.loads(response.content)
        if decoded['status'] == 'OK':
            location = decoded['results'][0]['geometry']['location']
            return location['lat'], location['lng']
    else:
        return None


def generate_placemark(name, lat, lng, radius, num_segments):
    '''Generate a placemark with an approximated circle given by `radius`
    (in meters) and centered on lat/lng.'''
    try:
        point_seq = kmlcircle.spoints(
            float(lng),
            float(lat),
            radius,
            num_segments,
        )
    except TypeError:
        import ipdb; ipdb.set_trace()
    coordinates = KML.coordinates(
        '\n'.join('{}, {}'.format(*p) for p in point_seq)
    )

    return KML.Placemark(
        KML.Name(name),
        KML.Polygon(
            KML.outerBoundaryIs(
                KML.LinearRing(coordinates),
            ),
        ),
    )


def build_kml(location_seq):
    placemark_list = []
    for name, lat, lng in location_seq:
        pm = generate_placemark(name, lat, lng, RADIUS, CIRCLE_SEGMENTS)
        placemark_list.append(pm)

    return KML.kml(KML.Document(*placemark_list))


def map_businesses(outfile):
    business_list = get_businesses(DATA_URL)
    location_list = []
    for idx, biz in enumerate(business_list):
        if idx % 100 == 0:
            print idx
        if 'location' in biz and not biz['location']['needs_recoding']:
            location_list.append(
                (
                    biz['dba_name'],
                    biz['location']['latitude'],
                    biz['location']['longitude'],
                ),
            )
        else:
            if 'business_address' in biz and 'business_zip' in biz:
                location = geocode(biz['business_address'], biz['business_zip'])
                if location is not None:
                    location_list.append(
                        (biz['dba_name'], location[0], location[1]),
                    )

    kml = build_kml(location_list)
    with open(outfile, 'w') as output:
        output.write(etree.tostring(kml, pretty_print=True))


if __name__ == '__main__':
    outfile = sys.argv[1]
    map_businesses(outfile)
