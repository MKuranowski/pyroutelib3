from pathlib import Path
from unittest import TestCase

from .osm_graph import OSM_PROFILE_CAR, OSMGraph, OSMHighwayProfile

FIXTURES_DIR = Path(__file__).with_name("fixtures")

TEST_HIGHWAY_PROFILE = OSMHighwayProfile(
    "cat",
    {"footway": 1.0, "path": 2.0},
    ["access", "cat"],
)


class TestOSMHighwayProfile(TestCase):
    def test_way_penalty(self) -> None:
        self.assertEqual(TEST_HIGHWAY_PROFILE.way_penalty({"highway": "footway"}), 1.0)
        self.assertEqual(TEST_HIGHWAY_PROFILE.way_penalty({"highway": "path"}), 2.0)
        self.assertIsNone(TEST_HIGHWAY_PROFILE.way_penalty({"highway": "motorway"}))
        self.assertIsNone(
            TEST_HIGHWAY_PROFILE.way_penalty({"highway": "motorway", "access": "no"})
        )
        self.assertEqual(
            TEST_HIGHWAY_PROFILE.way_penalty(
                {"highway": "footway", "access": "private", "cat": "yes"},
            ),
            1.0,
        )

    def test_way_direction(self) -> None:
        self.assertTupleEqual(
            TEST_HIGHWAY_PROFILE.way_direction({"highway": "footway"}),
            (True, True),
        )
        self.assertTupleEqual(
            TEST_HIGHWAY_PROFILE.way_direction({"highway": "footway", "oneway": "yes"}),
            (True, False),
        )
        self.assertTupleEqual(
            TEST_HIGHWAY_PROFILE.way_direction({"highway": "footway", "oneway": "-1"}),
            (False, True),
        )
        self.assertTupleEqual(
            TEST_HIGHWAY_PROFILE.way_direction({"highway": "motorway_link"}),
            (True, False),
        )
        self.assertTupleEqual(
            TEST_HIGHWAY_PROFILE.way_direction({"highway": "footway", "junction": "roundabout"}),
            (True, False),
        )
        self.assertTupleEqual(
            TEST_HIGHWAY_PROFILE.way_direction({"highway": "motorway_link", "oneway": "no"}),
            (True, True),
        )
        self.assertTupleEqual(
            TEST_HIGHWAY_PROFILE.way_direction(
                {"highway": "footway", "junction": "roundabout", "oneway": "-1"},
            ),
            (False, True),
        )

    def test_is_exempted(self) -> None:
        self.assertFalse(TEST_HIGHWAY_PROFILE.is_exempted({}))
        self.assertFalse(TEST_HIGHWAY_PROFILE.is_exempted({"except": "bus"}))
        self.assertTrue(TEST_HIGHWAY_PROFILE.is_exempted({"except": "cat"}))
        self.assertTrue(TEST_HIGHWAY_PROFILE.is_exempted({"except": "bus;cat"}))


class TestOSMGraph(TestCase):
    def assertEdge(self, g: OSMGraph, from_: int, to: int) -> None:
        self.assertIn(to, g.data[from_].edges)

    def assertNoEdge(self, g: OSMGraph, from_: int, to: int) -> None:
        self.assertNotIn(to, g.data[from_].edges)

    def test_simple_graph(self) -> None:
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
        with (FIXTURES_DIR / "simple_graph.osm").open(mode="rb") as f:
            g = OSMGraph.from_file(OSM_PROFILE_CAR, f)

        # Check the loaded amount of nodes
        self.assertEqual(len(g.data), 12)

        # Check edge costs
        self.assertAlmostEqual(g.data[-1].edges[-2], 1.4035, places=3)
        self.assertEqual(g.data[-1].edges[-2], g.data[-2].edges[-1])
        self.assertAlmostEqual(g.data[-62].edges[-7], 2.0385, places=3)

        # Check oneway handling: -4 → -3 → -5 → -7 → -4
        self.assertEdge(g, -4, -3)
        self.assertEdge(g, -3, -5)
        self.assertEdge(g, -5, -7)
        self.assertEdge(g, -7, -4)
        self.assertNoEdge(g, -4, -7)
        self.assertNoEdge(g, -3, -4)
        self.assertNoEdge(g, -5, -3)
        self.assertNoEdge(g, -7, -5)

        # Check roundabout handling: -60 → -61 → -62 → -63 → -60
        self.assertEdge(g, -60, -61)
        self.assertEdge(g, -61, -62)
        self.assertEdge(g, -62, -63)
        self.assertEdge(g, -63, -60)
        self.assertNoEdge(g, -60, -63)
        self.assertNoEdge(g, -61, -60)
        self.assertNoEdge(g, -62, -61)
        self.assertNoEdge(g, -63, -62)

        # Check access tag handling: -2 ↔ -61 has motor_vehicle=no
        self.assertNoEdge(g, -2, -61)
        self.assertNoEdge(g, -61, -2)

        # Check turn restriction -200: no -8 → -7 → -3
        # TODO: Re-enable checks when turn restrictions are handled
        # self.assertNoEdge(g, -8, -7)
        # phantom_nodes = [id for id in g.data[-8].edges if g.data[id].osm_id == -7]
        # self.assertEqual(len(phantom_nodes), 1)
        # phantom_node = phantom_nodes[0]
        # self.assertEdge(g, -8, phantom_node)
        # self.assertNoEdge(g, phantom_node, -3)

        # Check turn restriction with except=car, -201: no -7 → -3 → -5
        self.assertEdge(g, -7, -3)
        self.assertEdge(g, -3, -5)

        # Check turn restriction: only -1 → -2 → -3
        # TODO: Re-enable checks when turn restrictions are handled
        # self.assertNoEdge(g, -1, -2)
        # phantom_nodes = [id for id in g.data[-1].edges if g.data[id].osm_id == -2]
        # self.assertEqual(len(phantom_nodes), 1)
        # phantom_node = phantom_nodes[0]
        # self.assertEdge(g, -1, phantom_node)
        # self.assertSetEqual(set(g.data[phantom_node].edges.keys()), {-3})
