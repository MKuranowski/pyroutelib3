import pyroutelib3
import io

def test_distance():
    warsaw = (52.2298, 21.0118)
    johanesburg = (-26.2023, 28.0436)
    tokyo = (35.6895, 139.6917)

    distance_jo = pyroutelib3.Datastore.distance(warsaw, johanesburg)
    distance_to = pyroutelib3.Datastore.distance(warsaw, tokyo)

    assert 8748 < distance_jo < 8749, "incorrect haversine implementation"
    assert 8578 < distance_to < 8579, "incorrect haversine implementation"

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

    assert len(r.rnodes) == 12, "incorrect amount of nodes in Graph"

    # cost  -1 -2: ~104.051
    assert 0.1403 < r.routing[-1][-2] < 0.1404, "invalid cost calculation"
    assert r.routing[-1][-2] == r.routing[-2][-1], "cost different in 2 ways"

    # cost -62 -7: ~204.08
    assert 0.2038 < r.routing[-62][-7] < 0.2039, "cost calculation invalid"

    # oneway:  -4 →  -3 →  -5 →  -7 →  -4
    assert -3 in r.routing[-4], "invalid oneway handling"
    assert -5 in r.routing[-3], "invalid oneway handling"
    assert -7 in r.routing[-5], "invalid oneway handling"
    assert -4 in r.routing[-7], "invalid oneway handling"

    assert -7 not in r.routing[-4], "invalid oneway handling"
    assert -5 not in r.routing[-7], "invalid oneway handling"
    assert -3 not in r.routing[-5], "invalid oneway handling"
    assert -4 not in r.routing[-3], "invalid oneway handling"

    # roundabout: -60 → -61 → -62 → -63 → -60
    assert -61 in r.routing[-60], "invalid oneway handling"
    assert -62 in r.routing[-61], "invalid oneway handling"
    assert -63 in r.routing[-62], "invalid oneway handling"
    assert -60 in r.routing[-63], "invalid oneway handling"

    assert -60 not in r.routing[-61], "invalid oneway handling"
    assert -61 not in r.routing[-62], "invalid oneway handling"
    assert -62 not in r.routing[-63], "invalid oneway handling"
    assert -63 not in r.routing[-60], "invalid oneway handling"

    # -2 ↔ -61 motor_vehicle=no
    assert -2 not in r.routing[-61], "invalid access tag handling"
    assert -61 not in r.routing[-2], "invalid access tag handling"

    # no -8 -7 -3 (-200)
    assert (-8, -7, -3) in r.forbiddenMoves, "invlaid no_* restriction handling"

    # no -7 -3 -5 (-201) except car
    assert (-7, -3, -5) not in r.forbiddenMoves, "invalid except=* in restrictions handling"

    # only -1 -2 -3 (-201)
    assert r.mandatoryMoves[(-1, -2)] == [-3], "invalid only_* restriction handling"
