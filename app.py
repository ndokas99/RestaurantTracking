from flask import Flask, render_template, render_template_string, request, \
    make_response, jsonify, session, redirect, url_for
from sqlalchemy.exc import IntegrityError
from flask_sqlalchemy import SQLAlchemy
from flask_apscheduler import APScheduler
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
    "SECRET_KEY": 'H475GGH58H4DG374H9GY48THT85',
    "SQLALCHEMY_DATABASE_URI": 'sqlite:///session.db',
    "SQLALCHEMY_TRACK_MODIFICATIONS": False,
}
app.config.update(settings)
db = SQLAlchemy(app)
scheduler = APScheduler(app=app)


class Session(db.Model):
    sessionId = db.Column(db.Text, primary_key=True)
    sessionMap = db.Column(db.Text, unique=True, nullable=True)
    sessionTime = db.Column(db.DateTime(timezone=True), nullable=True)


@app.route('/')
def index():
    try:
        if Session.query.filter_by(sessionId=session['sid']).first():
            return render_template("index.html")
        else:
            raise KeyError
    except KeyError:
        session['sid'] = str(uuid4())
        try:
            user = Session(sessionId=session['sid'], sessionTime=datetime.now())
            db.session.add(user)
            db.session.commit()
            return render_template("index.html")
        except IntegrityError:
            del session['sid']
            return url_for('index')


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

    try:
        user = Session.query.filter_by(sessionId=session['sid']).first()
        user.sessionMap = mainMap.get_root().render()
        db.session.commit()
    except AttributeError:
        return redirect('/')

    return render_template("tracker.html", details=details)


@app.route('/map')
def embedMap():
    try:
        user = Session.query.filter_by(sessionId=session['sid']).first()
        return render_template_string(user.sessionMap)
    except (KeyError, TypeError, AttributeError):
        return redirect('/', 500)


def create_database():
    if not path.exists("session.db"):
        db.create_all(app=app)


def clearOldSession():
    for data in Session.query.all():
        seconds = (datetime.now() - data.sessionTime).seconds
        if seconds > 1800:
            Session.query.filter_by(sessionId=data.sessionId).delete()
            db.session.commit()
    with db.engine.begin() as conn:
        conn.execute('vacuum')


create_database()
scheduler.add_job('DBMaintainer', clearOldSession, trigger='interval', seconds=300)
scheduler.start()


if __name__ == '__main__':
    app.run()
