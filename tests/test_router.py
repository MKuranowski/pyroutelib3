import pyroutelib3
import math

# Graph, which is checked:
#
#   (2)   (2)   (2)
# 1─────2─────3─────4
#       └─────5─────┘
#         (1)   (1)
#
# For test_mandatory, 1-2-3 is a mandatory move
# For test_forbidden, 1-2-5 is a forbidde move

def prepare_router():
    r = pyroutelib3.Router("car")
    r.localFile = True
    r.distance = math.dist

    r.rnodes[1] = (1, 1)
    r.rnodes[2] = (2, 1)
    r.rnodes[3] = (3, 1)
    r.rnodes[4] = (4, 1)
    r.rnodes[5] = (3, 0)

    r.routing[1] = {2: 2}
    r.routing[2] = {1: 2, 3: 2, 5: 1}
    r.routing[3] = {2: 2, 4: 2}
    r.routing[4] = {3: 2, 5: 2}
    r.routing[5] = {2: 1, 4: 1}

    return r

def test_basic():
    r = prepare_router()

    s, n = r.doRoute(1, 4)

    assert s == "success"
    assert n == [1, 2, 5, 4]

def test_mandatory():
    r = prepare_router()
    r.mandatoryMoves[(1, 2)] = [3]

    s, n = r.doRoute(1, 4)

    assert s == "success"
    assert n == [1, 2, 3, 4]

def test_forbidden():
    r = prepare_router()
    r.forbiddenMoves[(1, 2, 5)] = [[1, 2, 5]]

    s, n = r.doRoute(1, 4)

    assert s == "success"
    assert n == [1, 2, 3, 4]

# Test shortest-is-not-best
#
#     5     1
#  7─────8─────9
#  │     │     │
#  │4    │3    │1
#  │  2  │  4  │
#  4─────5─────6
#  │     │     │
#  │6    │5    │1
#  │  1  │  2  │
#  1─────2─────3
#

def test_shortest_not_optimal():
    r = pyroutelib3.Router("car")
    r.localFile = True
    r.distance = math.dist

    # Nodes
    r.rnodes[1] = (0, 0)
    r.rnodes[2] = (1, 0)
    r.rnodes[3] = (2, 0)
    r.rnodes[4] = (0, 1)
    r.rnodes[5] = (1, 1)
    r.rnodes[6] = (2, 1)
    r.rnodes[7] = (0, 2)
    r.rnodes[8] = (1, 2)
    r.rnodes[9] = (2, 2)

    # Edges
    r.routing[1] = {2: 1, 4: 6}
    r.routing[2] = {1: 1, 3: 2, 5: 5}
    r.routing[3] = {2: 2, 6: 1}
    r.routing[4] = {1: 6, 5: 2, 7: 4}
    r.routing[5] = {2: 5, 4: 2, 6: 4, 8: 3}
    r.routing[6] = {3: 1, 5: 4, 9: 1}
    r.routing[7] = {4: 4, 8: 5,}
    r.routing[8] = {5: 3, 7: 5, 9: 1}
    r.routing[9] = {6: 1, 8: 1}

    # do the route
    s, n = r.doRoute(1, 8)
    assert s == "success"
    assert n == [1, 2, 3, 6, 9, 8]
