import pyroutelib3
import shutil
import os


def test_live():
    # Clear tilescache
    if os.path.isdir("tilescache"):
        shutil.rmtree("tilescache")

    # Do some routing - a car test
    r = pyroutelib3.Router("car")
    a, b = r.findNode(52.240712, 21.025801), r.findNode(52.2462868, 21.0123011)
    s, _ = r.doRoute(a, b)

    assert s == "success"
    assert len(r.routing) < 15_000

    # Do some routing - a bus test
    r = pyroutelib3.Router("bus")
    a, b = r.findNode(52.240712, 21.025801), r.findNode(52.2462868, 21.0123011)
    s, _ = r.doRoute(a, b)

    assert s == "success"
    assert len(r.routing) < 7500

    # Do some routing - a tram test
    r = pyroutelib3.Router("tram")
    a, b = r.findNode(52.244585, 21.084751), r.findNode(52.225889, 20.996075)
    s, _ = r.doRoute(a, b)

    assert s == "success"
    assert len(r.routing) < 1500

    # Count up the number of tiles
    count = 0
    for (_, _, fnames) in os.walk("tilescache"):
        for f in fnames:
            if f == "data.osm":
                count += 1

    assert count < 30
