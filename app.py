from flask import Flask, render_template, render_template_string, request, \
    make_response, jsonify, session, redirect, url_for
from flask.ext.session import Session
from folium import Map, Icon, Marker, Circle
from overpy import Overpass
from math import cos, sin, atan2, sqrt, pi
from datetime import datetime
from functools import lru_cache
from uuid import uuid4
from os import path


app = Flask(__name__)
app.debug = False
settings = {
    "SECRET_KEY": 'H475GGH58H4DG374H9GY48THT85'
}
app.config.update(settings)
Session(app)


@app.route('/')
def index():
    session['sid'] = str(uuid4())
    return render_template("index.html")


@app.route('/unsupported')
def unavailable():
    return render_template_string("<h1>Geolocation feature does not work on this platform</h1>")


@app.route('/track', methods=['POST'])
def track():
    session['lat1'], session['lon1'], session['dist'] = request.get_json().values()
    return make_response(jsonify({}))


@lru_cache
def create_markers(distance, lat, lon):
    def calcDist(lat2, lon2):
        lat1 = session['lat1']
        lon1 = session['lon1']
        phi1, phi2 = lat1 * pi / 180, lat2 * pi / 180
        phi_diff = (lat2 - lat1) * pi / 180
        lambda_diff = (lon2 - lon1) * pi / 180
        a = sin(phi_diff / 2) ** 2 + cos(phi1) * cos(phi2) * sin(lambda_diff / 2) ** 2
        c = 2 * atan2(sqrt(a), sqrt(1 - a))
        return round(6371 * c, 2)

    results = Overpass().query(f"""
        node(around: {distance * 1000}, {lat}, {lon})
        ["amenity"~"restaurant|food"]
        ["name"];
        out body;
    """)
    details = []

    for node in results.nodes:
        nodeLat = float(node.lat)
        nodeLon = float(node.lon)
        detail = {
            "id": f"est{node.id}",
            "lat": nodeLat,
            "lon": nodeLon,
            "name": node.tags["name"],
            "type": node.tags["amenity"],
            "distance": calcDist(nodeLat, nodeLon)
        }

        ids = [["street", "addr:street"], ["opening hours", "opening_hours"], ["cuisine", "cuisine"],
               ["takeaway", "takeaway"], ["outdoor seating", "outdoor_seating"], ["internet access", "internet_access"]]

        for key, val in ids:
            try:
                detail[key] = node.tags[val]
            except KeyError:
                continue
        details.append(detail)

    return sorted(details, key=lambda k: k['distance'])


@app.route('/showMap')
def showMap():
    try:
        lat1, lon1, dist = session['lat1'], session['lon1'], session['dist']
    except KeyError:
        return redirect("/")

    latDiff = (360 / 40075) * dist
    lonDiff = (360 / (cos(lat1) * 40075))
    bounds = [[lat1 - latDiff, lon1 - lonDiff],
              [lat1 + latDiff, lon1 + lonDiff]]

    mainMap = Map(location=[lat1, lon1],
                  min_lat=bounds[0][0], min_lon=bounds[0][1],
                  max_lat=bounds[1][0], max_lon=bounds[1][1],
                  zoom_start=11)

    Marker(location=[lat1, lon1],
           tooltip="You are here",
           icon=Icon(color="red", icon="user")
           ).add_to(mainMap)

    Circle(location=(lat1, lon1),
           radius=dist * 1000).add_to(mainMap)

    details = create_markers(dist, lat1, lon1)

    for detail in details:
        if detail["type"] == "restaurant":
            icon = "cutlery"
        else:
            icon = "shopping-basket"
        Marker(location=[detail["lat"], detail["lon"]],
               tooltip=f"{detail['name']}",
               icon=Icon(color="blue", icon=icon, prefix="fa")
               ).add_to(mainMap)
        
    session["map"] = mainMap.get_root().render()
    return render_template("tracker.html", details=details)


@app.route('/map')
def embedMap():
    return render_template_string(session.get("map","not set"))


if __name__ == '__main__':
    app.run()
