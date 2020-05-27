import pyroutelib3
import io

def test_distance():
    warsaw = (52.2298, 21.0118)
    johanesburg = (-26.2023, 28.0436)
    tokyo = (35.6895, 139.6917)

    distance_jo = pyroutelib3.Datastore.distance(warsaw, johanesburg)
    distance_to = pyroutelib3.Datastore.distance(warsaw, tokyo)

    assert 8748 < distance_jo < 8749
    assert 8578 < distance_to < 8579

def test_processing():
    r = pyroutelib3.Router("car", "tests/simple_graph.osm", "xml")

    # The graph looks like this:
    #   9
    #   │         8
    #  ┌63┐       │
    # 60  62──────7
    #  └61┘      /│\
    #   │       4 │ 5
    #   │        \│/
    #   2─────────3
    #   │
    #   1

    assert len(r.rnodes) == 12

    # cost  -1 -2: ~104.051
    assert 0.1403 < r.routing[-1][-2] < 0.1404
    assert r.routing[-1][-2] == r.routing[-2][-1]

    # cost -62 -7: ~204.08
    assert 0.2038 < r.routing[-62][-7] < 0.2039

    # oneway:  -4 →  -3 →  -5 →  -7 →  -4
    assert -3 in r.routing[-4]
    assert -5 in r.routing[-3]
    assert -7 in r.routing[-5]
    assert -4 in r.routing[-7]

    assert -7 not in r.routing[-4]
    assert -5 not in r.routing[-7]
    assert -3 not in r.routing[-5]
    assert -4 not in r.routing[-3]

    # roundabout: -60 → -61 → -62 → -63 → -60
    assert -61 in r.routing[-60]
    assert -62 in r.routing[-61]
    assert -63 in r.routing[-62]
    assert -60 in r.routing[-63]

    assert -60 not in r.routing[-61]
    assert -61 not in r.routing[-62]
    assert -62 not in r.routing[-63]
    assert -63 not in r.routing[-60]

    # -2 ↔ -61 motor_vehicle=no
    assert -2 not in r.routing[-61]
    assert -61 not in r.routing[-2]

    #   no -8 -7 -3 (-200)
    assert (-8, -7, -3) in r.forbiddenMoves

    #   no -7 -3 -5 (-201) except car
    assert (-7, -3, -5) not in r.forbiddenMoves

    # only -1 -2 -3 (-201)
    assert r.mandatoryMoves[(-1, -2)] == [-3]
