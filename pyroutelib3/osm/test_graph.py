# © Copyright 2024 Mikołaj Kuranowski
# SPDX-License-Identifier: GPL-3.0-or-later

# pyright: reportPrivateUsage=false

from pathlib import Path
from unittest import TestCase

from . import reader
from .graph import Graph, GraphNode, _GraphBuilder, _GraphChange
from .profile import CarProfile

FIXTURES_DIR = Path(__file__).with_name("test_fixtures")


class TestCaseWithEdges(TestCase):
    def assertEdge(self, g: Graph, from_: int, to: int) -> None:
        self.assertIn(to, g.edges.get(from_, {}))

    def assertNoEdge(self, g: Graph, from_: int, to: int) -> None:
        self.assertNotIn(to, g.edges.get(from_, {}))


class TestGraph(TestCaseWithEdges):
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
            g = Graph.from_file(CarProfile(), f)

        # Check the loaded amount of nodes
        self.assertEqual(len(g.nodes), 14)

        # Check edge costs
        self.assertAlmostEqual(g.edges[-62][-7], 2.0385, places=3)
        self.assertEqual(g.edges[-7][-62], g.edges[-62][-7])
        self.assertAlmostEqual(g.edges[-2][-1], 1.4035, places=3)

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
        self.assertNoEdge(g, -8, -7)
        phantom_nodes = [id for id in g.edges[-8] if g.nodes[id].external_id == -7]
        self.assertEqual(len(phantom_nodes), 1)
        phantom_node = phantom_nodes[0]
        self.assertEdge(g, -8, phantom_node)
        self.assertNoEdge(g, phantom_node, -3)

        # Check turn restriction with except=car, -201: no -7 → -3 → -5
        self.assertEdge(g, -7, -3)
        self.assertEdge(g, -3, -5)

        # Check turn restriction: only -1 → -2 → -3
        self.assertNoEdge(g, -1, -2)
        phantom_nodes = [id for id in g.edges[-1] if g.nodes[id].external_id == -2]
        self.assertEqual(len(phantom_nodes), 1)
        phantom_node = phantom_nodes[0]
        self.assertEdge(g, -1, phantom_node)
        self.assertSetEqual(set(g.edges[phantom_node]), {-3})


class TestGraphBuilder(TestCaseWithEdges):
    def test_add_node(self) -> None:
        g = Graph(CarProfile())
        b = _GraphBuilder(g)
        b.add_node(reader.Node(1, (0.0, 0.0)))

        self.assertEqual(g.nodes[1], GraphNode(id=1, position=(0.0, 0.0), external_id=1))
        self.assertIn(1, b.unused_nodes)

    def test_add_node_duplicate(self) -> None:
        g = Graph(CarProfile())
        g.nodes[1] = GraphNode(id=1, position=(0.0, 0.0), external_id=1)
        b = _GraphBuilder(g)
        b.add_node(reader.Node(1, (0.1, 0.0)))

        self.assertEqual(g.nodes[1], GraphNode(id=1, position=(0.0, 0.0), external_id=1))
        self.assertNotIn(1, b.unused_nodes)

    def test_add_node_big_osm_id(self) -> None:
        g = Graph(CarProfile())
        b = _GraphBuilder(g)

        with self.assertRaises(ValueError):
            b.add_node(reader.Node(id=0x0010_0000_0000_0000, position=(0.0, 0.0)))

    def test_add_way(self) -> None:
        g = Graph(CarProfile())
        b = _GraphBuilder(g)
        b.add_features(
            [
                reader.Node(1, (0.0, 0.0)),
                reader.Node(2, (0.1, 0.0)),
                reader.Node(3, (0.2, 0.0)),
                reader.Way(10, [1, 2, 3], {"highway": "primary"}),
            ]
        )

        self.assertEdge(g, 1, 2)
        self.assertEdge(g, 2, 3)
        self.assertNoEdge(g, 1, 3)
        self.assertEdge(g, 3, 2)
        self.assertEdge(g, 2, 1)
        self.assertNoEdge(g, 3, 1)

        self.assertSetEqual(b.unused_nodes, set())
        self.assertListEqual(b.way_nodes[10], [1, 2, 3])

    def test_add_way_one_way(self) -> None:
        g = Graph(CarProfile())
        b = _GraphBuilder(g)
        b.add_features(
            [
                reader.Node(1, (0.0, 0.0)),
                reader.Node(2, (0.1, 0.0)),
                reader.Node(3, (0.2, 0.0)),
                reader.Way(10, [1, 2, 3], {"highway": "primary", "oneway": "yes"}),
            ]
        )

        self.assertEdge(g, 1, 2)
        self.assertEdge(g, 2, 3)
        self.assertNoEdge(g, 1, 3)
        self.assertNoEdge(g, 3, 2)
        self.assertNoEdge(g, 2, 1)
        self.assertNoEdge(g, 3, 1)

        self.assertSetEqual(b.unused_nodes, set())
        self.assertListEqual(b.way_nodes[10], [1, 2, 3])

    def test_add_way_not_routable(self) -> None:
        g = Graph(CarProfile())
        b = _GraphBuilder(g)
        b.add_features(
            [
                reader.Node(1, (0.0, 0.0)),
                reader.Node(2, (0.1, 0.0)),
                reader.Node(3, (0.2, 0.0)),
                reader.Way(10, [1, 2, 3], {"highway": "primary", "access": "no"}),
            ]
        )

        self.assertNoEdge(g, 1, 2)
        self.assertNoEdge(g, 2, 3)
        self.assertNoEdge(g, 1, 3)
        self.assertNoEdge(g, 3, 2)
        self.assertNoEdge(g, 2, 1)
        self.assertNoEdge(g, 3, 1)

        self.assertSetEqual(b.unused_nodes, {1, 2, 3})
        self.assertNotIn(10, b.way_nodes)

    def test_add_relation_prohibitory(self) -> None:
        #     4
        #     │
        # 1───2───3
        # no_left_turn: 1->2->4

        g = Graph(CarProfile())
        g._phantom_node_id_counter = 100

        b = _GraphBuilder(g)
        b.add_features(
            [
                reader.Node(1, (0.0, 0.0)),
                reader.Node(2, (0.1, 0.0)),
                reader.Node(3, (0.2, 0.0)),
                reader.Node(4, (0.1, 0.1)),
                reader.Way(10, [1, 2], {"highway": "primary"}),
                reader.Way(11, [2, 3], {"highway": "primary"}),
                reader.Way(12, [2, 4], {"highway": "primary"}),
                reader.Relation(
                    id=20,
                    members=[
                        reader.RelationMember("way", 10, "from"),
                        reader.RelationMember("node", 2, "via"),
                        reader.RelationMember("way", 12, "to"),
                    ],
                    tags={"type": "restriction", "restriction": "no_left_turn"},
                ),
            ]
        )

        self.assertNoEdge(g, 1, 2)
        self.assertEdge(g, 1, 101)

        self.assertEdge(g, 2, 1)
        self.assertEdge(g, 2, 3)
        self.assertEdge(g, 2, 4)

        self.assertEdge(g, 3, 2)
        self.assertEdge(g, 4, 2)

        self.assertEdge(g, 101, 1)
        self.assertNoEdge(g, 101, 2)
        self.assertEdge(g, 101, 3)
        self.assertNoEdge(g, 101, 4)

    def test_add_relation_prohibitory_not_applicable(self) -> None:
        #     4
        #     ↓
        # 1───2───3
        # no_left_turn: 1->2->4

        g = Graph(CarProfile())
        g._phantom_node_id_counter = 100

        b = _GraphBuilder(g)
        b.add_features(
            [
                reader.Node(1, (0.0, 0.0)),
                reader.Node(2, (0.1, 0.0)),
                reader.Node(3, (0.2, 0.0)),
                reader.Node(4, (0.1, 0.1)),
                reader.Way(10, [1, 2], {"highway": "primary"}),
                reader.Way(11, [2, 3], {"highway": "primary"}),
                reader.Way(12, [4, 2], {"highway": "primary", "oneway": "yes"}),
                reader.Relation(
                    id=20,
                    members=[
                        reader.RelationMember("way", 10, "from"),
                        reader.RelationMember("node", 2, "via"),
                        reader.RelationMember("way", 12, "to"),
                    ],
                    tags={"type": "restriction", "restriction": "no_left_turn"},
                ),
            ]
        )

        self.assertNotIn(101, g.nodes)
        self.assertEqual(g._phantom_node_id_counter, 100)

        self.assertEdge(g, 1, 2)

        self.assertEdge(g, 2, 1)
        self.assertEdge(g, 2, 3)
        self.assertNoEdge(g, 2, 4)

        self.assertEdge(g, 3, 2)
        self.assertEdge(g, 4, 2)

    def test_add_relation_two_prohibitory(self) -> None:
        #     4
        #     │
        # 1───2───3
        # no_left_turn: 1->2->4
        # no_right_turn: 4->2->1

        g = Graph(CarProfile())
        g._phantom_node_id_counter = 100

        b = _GraphBuilder(g)
        b.add_features(
            [
                reader.Node(1, (0.0, 0.0)),
                reader.Node(2, (0.1, 0.0)),
                reader.Node(3, (0.2, 0.0)),
                reader.Node(4, (0.1, 0.1)),
                reader.Way(10, [1, 2], {"highway": "primary"}),
                reader.Way(11, [2, 3], {"highway": "primary"}),
                reader.Way(12, [2, 4], {"highway": "primary"}),
                reader.Relation(
                    id=20,
                    members=[
                        reader.RelationMember("way", 10, "from"),
                        reader.RelationMember("node", 2, "via"),
                        reader.RelationMember("way", 12, "to"),
                    ],
                    tags={"type": "restriction", "restriction": "no_left_turn"},
                ),
                reader.Relation(
                    id=21,
                    members=[
                        reader.RelationMember("way", 12, "from"),
                        reader.RelationMember("node", 2, "via"),
                        reader.RelationMember("way", 10, "to"),
                    ],
                    tags={"type": "restriction", "restriction": "no_right_turn"},
                ),
            ]
        )

        self.assertNoEdge(g, 1, 2)
        self.assertEdge(g, 1, 101)

        self.assertEdge(g, 2, 1)
        self.assertEdge(g, 2, 3)
        self.assertEdge(g, 2, 4)

        self.assertEdge(g, 3, 2)

        self.assertNoEdge(g, 4, 2)
        self.assertEdge(g, 4, 102)

        self.assertEdge(g, 101, 1)
        self.assertEdge(g, 101, 3)
        self.assertNoEdge(g, 101, 4)

        self.assertNoEdge(g, 102, 1)
        self.assertNoEdge(g, 102, 2)
        self.assertEdge(g, 102, 3)
        self.assertEdge(g, 102, 4)

    def test_add_relation_two_prohibitory_with_same_activator(self) -> None:
        #     4
        #     │
        # 1───2───3
        #     │
        #     5
        # no_left_turn: 1->2->4
        # no_right_turn: 1->2->5

        g = Graph(CarProfile())
        g._phantom_node_id_counter = 100

        b = _GraphBuilder(g)
        b.add_features(
            [
                reader.Node(1, (0.0, 0.0)),
                reader.Node(2, (0.1, 0.0)),
                reader.Node(3, (0.2, 0.0)),
                reader.Node(4, (0.1, 0.1)),
                reader.Node(5, (0.1, -0.1)),
                reader.Way(10, [1, 2], {"highway": "primary"}),
                reader.Way(11, [2, 3], {"highway": "primary"}),
                reader.Way(12, [2, 4], {"highway": "primary"}),
                reader.Way(13, [2, 5], {"highway": "primary"}),
                reader.Relation(
                    id=20,
                    members=[
                        reader.RelationMember("way", 10, "from"),
                        reader.RelationMember("node", 2, "via"),
                        reader.RelationMember("way", 12, "to"),
                    ],
                    tags={"type": "restriction", "restriction": "no_left_turn"},
                ),
                reader.Relation(
                    id=21,
                    members=[
                        reader.RelationMember("way", 10, "from"),
                        reader.RelationMember("node", 2, "via"),
                        reader.RelationMember("way", 13, "to"),
                    ],
                    tags={"type": "restriction", "restriction": "no_right_turn"},
                ),
            ]
        )

        self.assertEqual(g._phantom_node_id_counter, 101)
        self.assertSetEqual(set(g.nodes), {1, 2, 3, 4, 5, 101})

        self.assertNoEdge(g, 1, 2)
        self.assertEdge(g, 1, 101)

        self.assertEdge(g, 2, 1)
        self.assertEdge(g, 2, 3)
        self.assertEdge(g, 2, 4)
        self.assertEdge(g, 2, 5)

        self.assertEdge(g, 3, 2)
        self.assertEdge(g, 4, 2)
        self.assertEdge(g, 5, 2)

        self.assertEdge(g, 101, 1)
        self.assertNoEdge(g, 101, 2)
        self.assertEdge(g, 101, 3)
        self.assertNoEdge(g, 101, 4)
        self.assertNoEdge(g, 101, 5)

    def test_add_relation_mandatory(self) -> None:
        #     4
        #     │
        # 1───2───3
        # only_straight_on: 1->2->3

        g = Graph(CarProfile())
        g._phantom_node_id_counter = 100

        b = _GraphBuilder(g)
        b.add_features(
            [
                reader.Node(1, (0.0, 0.0)),
                reader.Node(2, (0.1, 0.0)),
                reader.Node(3, (0.2, 0.0)),
                reader.Node(4, (0.1, 0.1)),
                reader.Way(10, [1, 2], {"highway": "primary"}),
                reader.Way(11, [2, 3], {"highway": "primary"}),
                reader.Way(12, [2, 4], {"highway": "primary"}),
                reader.Relation(
                    id=20,
                    members=[
                        reader.RelationMember("way", 10, "from"),
                        reader.RelationMember("node", 2, "via"),
                        reader.RelationMember("way", 11, "to"),
                    ],
                    tags={"type": "restriction", "restriction": "only_straight_on"},
                ),
            ]
        )

        self.assertNoEdge(g, 1, 2)
        self.assertEdge(g, 1, 101)

        self.assertEdge(g, 2, 1)
        self.assertEdge(g, 2, 3)
        self.assertEdge(g, 2, 4)

        self.assertEdge(g, 3, 2)
        self.assertEdge(g, 4, 2)

        self.assertNoEdge(g, 101, 1)
        self.assertNoEdge(g, 101, 2)
        self.assertEdge(g, 101, 3)
        self.assertNoEdge(g, 101, 4)

    def test_add_relation_mandatory_not_applicable(self) -> None:
        #     4
        #     ↓
        # 1───2───3
        # only_left_turn: 1->2->4

        g = Graph(CarProfile())
        g._phantom_node_id_counter = 100

        b = _GraphBuilder(g)
        b.add_features(
            [
                reader.Node(1, (0.0, 0.0)),
                reader.Node(2, (0.1, 0.0)),
                reader.Node(3, (0.2, 0.0)),
                reader.Node(4, (0.1, 0.1)),
                reader.Way(10, [1, 2], {"highway": "primary"}),
                reader.Way(11, [2, 3], {"highway": "primary"}),
                reader.Way(12, [4, 2], {"highway": "primary", "oneway": "yes"}),
                reader.Relation(
                    id=20,
                    members=[
                        reader.RelationMember("way", 10, "from"),
                        reader.RelationMember("node", 2, "via"),
                        reader.RelationMember("way", 12, "to"),
                    ],
                    tags={"type": "restriction", "restriction": "only_left_turn"},
                ),
            ]
        )

        self.assertNotIn(101, g.nodes)
        self.assertEqual(g._phantom_node_id_counter, 100)

        self.assertEdge(g, 1, 2)

        self.assertEdge(g, 2, 1)
        self.assertEdge(g, 2, 3)
        self.assertNoEdge(g, 2, 4)

        self.assertEdge(g, 3, 2)
        self.assertEdge(g, 4, 2)

    def test_add_relation_two_mandatory(self) -> None:
        #     4
        #     │
        # 1───2───3
        # only_straight_on: 1->2->3
        # only_left_turn: 4->2->3

        g = Graph(CarProfile())
        g._phantom_node_id_counter = 100

        b = _GraphBuilder(g)
        b.add_features(
            [
                reader.Node(1, (0.0, 0.0)),
                reader.Node(2, (0.1, 0.0)),
                reader.Node(3, (0.2, 0.0)),
                reader.Node(4, (0.1, 0.1)),
                reader.Way(10, [1, 2], {"highway": "primary"}),
                reader.Way(11, [2, 3], {"highway": "primary"}),
                reader.Way(12, [2, 4], {"highway": "primary"}),
                reader.Relation(
                    id=20,
                    members=[
                        reader.RelationMember("way", 10, "from"),
                        reader.RelationMember("node", 2, "via"),
                        reader.RelationMember("way", 11, "to"),
                    ],
                    tags={"type": "restriction", "restriction": "only_straight_on"},
                ),
                reader.Relation(
                    id=21,
                    members=[
                        reader.RelationMember("way", 12, "from"),
                        reader.RelationMember("node", 2, "via"),
                        reader.RelationMember("way", 11, "to"),
                    ],
                    tags={"type": "restriction", "restriction": "only_left_turn"},
                ),
            ]
        )

        self.assertNoEdge(g, 1, 2)
        self.assertEdge(g, 1, 101)

        self.assertEdge(g, 2, 1)
        self.assertEdge(g, 2, 3)
        self.assertEdge(g, 2, 4)

        self.assertEdge(g, 3, 2)

        self.assertNoEdge(g, 4, 2)
        self.assertEdge(g, 4, 102)

        self.assertNoEdge(g, 101, 1)
        self.assertEdge(g, 101, 3)
        self.assertNoEdge(g, 101, 4)

        self.assertNoEdge(g, 102, 1)
        self.assertNoEdge(g, 102, 2)
        self.assertEdge(g, 102, 3)
        self.assertNoEdge(g, 102, 4)

    def test_add_relation_two_conflicting_mandatory(self) -> None:
        #     4
        #     │
        # 1───2───3
        # only_straight_on: 1->2->3 (applied)
        # only_left_turn: 1->2->4 (ignored)

        g = Graph(CarProfile())
        g._phantom_node_id_counter = 100

        b = _GraphBuilder(g)
        b.add_features(
            [
                reader.Node(1, (0.0, 0.0)),
                reader.Node(2, (0.1, 0.0)),
                reader.Node(3, (0.2, 0.0)),
                reader.Node(4, (0.1, 0.1)),
                reader.Way(10, [1, 2], {"highway": "primary"}),
                reader.Way(11, [2, 3], {"highway": "primary"}),
                reader.Way(12, [2, 4], {"highway": "primary"}),
                reader.Relation(
                    id=20,
                    members=[
                        reader.RelationMember("way", 10, "from"),
                        reader.RelationMember("node", 2, "via"),
                        reader.RelationMember("way", 11, "to"),
                    ],
                    tags={"type": "restriction", "restriction": "only_straight_on"},
                ),
                reader.Relation(
                    id=21,
                    members=[
                        reader.RelationMember("way", 10, "from"),
                        reader.RelationMember("node", 2, "via"),
                        reader.RelationMember("way", 12, "to"),
                    ],
                    tags={"type": "restriction", "restriction": "only_left_turn"},
                ),
            ]
        )

        self.assertNoEdge(g, 1, 2)
        self.assertEdge(g, 1, 101)

        self.assertEdge(g, 2, 1)
        self.assertEdge(g, 2, 3)
        self.assertEdge(g, 2, 4)

        self.assertEdge(g, 3, 2)
        self.assertEdge(g, 4, 2)

        self.assertNoEdge(g, 101, 1)
        self.assertNoEdge(g, 101, 2)
        self.assertEdge(g, 101, 3)
        self.assertNoEdge(g, 101, 4)

    def test_add_relation_mandatory_and_prohibitory_with_same_activator(self) -> None:
        #     4
        #     │
        # 1───2───3
        # no_left_turn: 1->2->4
        # only_straight_on: 1->2->3

        g = Graph(CarProfile())
        g._phantom_node_id_counter = 100

        b = _GraphBuilder(g)
        b.add_features(
            [
                reader.Node(1, (0.0, 0.0)),
                reader.Node(2, (0.1, 0.0)),
                reader.Node(3, (0.2, 0.0)),
                reader.Node(4, (0.1, 0.1)),
                reader.Way(10, [1, 2], {"highway": "primary"}),
                reader.Way(11, [2, 3], {"highway": "primary"}),
                reader.Way(12, [2, 4], {"highway": "primary"}),
                reader.Relation(
                    id=20,
                    members=[
                        reader.RelationMember("way", 10, "from"),
                        reader.RelationMember("node", 2, "via"),
                        reader.RelationMember("way", 12, "to"),
                    ],
                    tags={"type": "restriction", "restriction": "no_left_turn"},
                ),
                reader.Relation(
                    id=21,
                    members=[
                        reader.RelationMember("way", 10, "from"),
                        reader.RelationMember("node", 2, "via"),
                        reader.RelationMember("way", 11, "to"),
                    ],
                    tags={"type": "restriction", "restriction": "only_straight_on"},
                ),
            ]
        )

        self.assertNoEdge(g, 1, 2)
        self.assertEdge(g, 1, 101)

        self.assertEdge(g, 2, 1)
        self.assertEdge(g, 2, 3)
        self.assertEdge(g, 2, 4)

        self.assertEdge(g, 3, 2)
        self.assertEdge(g, 4, 2)

        self.assertNoEdge(g, 101, 1)
        self.assertNoEdge(g, 101, 2)
        self.assertEdge(g, 101, 3)
        self.assertNoEdge(g, 101, 4)

    def test_add_relation_contained_within_another(self) -> None:
        #     5   6
        #     │   │
        # 1───2───3───4
        # no_left_turn: 1->2->3->6
        # only_straight_on: 1->2->3

        g = Graph(CarProfile())
        g._phantom_node_id_counter = 100

        b = _GraphBuilder(g)
        b.add_features(
            [
                reader.Node(1, (0.0, 0.0)),
                reader.Node(2, (0.1, 0.0)),
                reader.Node(3, (0.2, 0.0)),
                reader.Node(4, (0.3, 0.0)),
                reader.Node(5, (0.1, 0.1)),
                reader.Node(6, (0.2, 0.1)),
                reader.Way(10, [1, 2], {"highway": "primary"}),
                reader.Way(11, [2, 3], {"highway": "primary"}),
                reader.Way(12, [3, 4], {"highway": "primary"}),
                reader.Way(13, [2, 5], {"highway": "primary"}),
                reader.Way(14, [3, 6], {"highway": "primary"}),
                reader.Relation(
                    id=20,
                    members=[
                        reader.RelationMember("way", 10, "from"),
                        reader.RelationMember("way", 11, "via"),
                        reader.RelationMember("way", 14, "to"),
                    ],
                    tags={"type": "restriction", "restriction": "no_left_turn"},
                ),
                reader.Relation(
                    id=21,
                    members=[
                        reader.RelationMember("way", 10, "from"),
                        reader.RelationMember("node", 2, "via"),
                        reader.RelationMember("way", 11, "to"),
                    ],
                    tags={"type": "restriction", "restriction": "only_straight_on"},
                ),
            ]
        )

        self.assertEqual(g._phantom_node_id_counter, 102)
        self.assertSetEqual(set(g.nodes), {1, 2, 3, 4, 5, 6, 101, 102})

        self.assertNoEdge(g, 1, 2)
        self.assertEdge(g, 1, 101)

        self.assertEdge(g, 101, 102)
        self.assertNoEdge(g, 101, 1)
        self.assertNoEdge(g, 101, 3)
        self.assertNoEdge(g, 101, 5)

        self.assertEdge(g, 102, 2)
        self.assertEdge(g, 102, 4)
        self.assertNoEdge(g, 102, 6)

        self.assertEdge(g, 2, 1)
        self.assertEdge(g, 2, 3)
        self.assertEdge(g, 2, 5)

        self.assertEdge(g, 3, 2)
        self.assertEdge(g, 3, 4)
        self.assertEdge(g, 3, 6)

        self.assertEdge(g, 4, 3)
        self.assertEdge(g, 5, 2)
        self.assertEdge(g, 6, 3)

    def test_cleanup(self) -> None:
        g = Graph(CarProfile())
        b = _GraphBuilder(g)
        b.add_features(
            [
                reader.Node(1, (0.0, 0.0)),
                reader.Node(2, (0.1, 0.0)),
                reader.Node(3, (0.2, 0.0)),
                reader.Node(4, (0.2, 0.1)),
                reader.Node(5, (0.2, 0.1)),
                reader.Way(10, [1, 2, 3], {"highway": "primary"}),
            ]
        )

        self.assertSetEqual(set(g.nodes), {1, 2, 3, 4, 5})
        self.assertSetEqual(b.unused_nodes, {4, 5})

        b.cleanup()

        self.assertSetEqual(set(g.nodes), {1, 2, 3})


class TestGraphChange(TestCase):
    def setUp(self) -> None:
        #  (200) (200) (200)
        # 1─────2─────3─────4
        #       └─────5─────┘
        #        (100) (100)
        self.g = Graph(CarProfile())
        self.g.nodes = {
            1: GraphNode(id=1, position=(0.0, 0.0), external_id=1),
            2: GraphNode(id=2, position=(0.1, 0.0), external_id=2),
            3: GraphNode(id=3, position=(0.2, 0.0), external_id=3),
            4: GraphNode(id=4, position=(0.3, 0.0), external_id=4),
            5: GraphNode(id=5, position=(0.2, 0.1), external_id=5),
        }
        self.g.edges = {
            1: {2: 200.0},
            2: {1: 200.0, 3: 200.0, 5: 100.0},
            3: {2: 200.0, 4: 200.0},
            4: {3: 200.0, 5: 100.0},
            5: {2: 100.0, 4: 100.0},
        }

        self.g._phantom_node_id_counter = 10

    def test_restriction_as_cloned_nodes(self) -> None:
        change = _GraphChange(self.g)
        cloned = change.restriction_as_cloned_nodes([1, 2, 5])
        self.assertEqual(cloned, [1, 11, 5])
        self.assertDictEqual(change.new_nodes, {11: 2})
        self.assertDictEqual(change.edges_to_add, {1: {11: 200.0}})
        self.assertSetEqual(change.edges_to_remove, {(1, 2)})
        self.assertEqual(change.phantom_node_id_counter, 11)

    def test_restriction_as_cloned_nodes_reuses_inner_nodes(self) -> None:
        self.g.nodes[11] = GraphNode(id=11, position=(0.1, 0.0), external_id=2)
        del self.g.edges[1][2]
        self.g.edges[1][11] = 200.0
        self.g.edges[11] = {1: 200.0, 3: 200.0, 5: 100.0}

        change = _GraphChange(self.g)
        cloned = change.restriction_as_cloned_nodes([1, 2, 3])
        self.assertEqual(cloned, [1, 11, 3])
        self.assertDictEqual(change.new_nodes, {})
        self.assertDictEqual(change.edges_to_add, {})
        self.assertSetEqual(change.edges_to_remove, set())

    def test_restriction_as_cloned_nodes_reuses_last_nodes(self) -> None:
        self.g.nodes[11] = GraphNode(id=11, position=(0.1, 0.0), external_id=2)
        self.g.nodes[12] = GraphNode(id=12, position=(0.1, 0.0), external_id=3)
        del self.g.edges[1][2]
        self.g.edges[1][11] = 200.0
        self.g.edges[11] = {1: 200.0, 12: 200.0, 5: 100.0}
        self.g.edges[12] = {2: 200.0, 4: 200.0}

        change = _GraphChange(self.g)
        cloned = change.restriction_as_cloned_nodes([1, 2, 3])
        self.assertEqual(cloned, [1, 11, 12])
        self.assertDictEqual(change.new_nodes, {})
        self.assertDictEqual(change.edges_to_add, {})
        self.assertSetEqual(change.edges_to_remove, set())

    def test_restriction_as_cloned_nodes_missing_edge(self) -> None:
        change = _GraphChange(self.g)
        self.assertIsNone(change.restriction_as_cloned_nodes([1, 2, 6]))

    def test_apply(self) -> None:
        change = _GraphChange(self.g)
        change.new_nodes = {11: 2}
        change.edges_to_add = {1: {11: 200.0}}
        change.edges_to_remove = {(1, 2), (11, 5)}
        change.phantom_node_id_counter = 11
        change.apply()

        self.assertDictEqual(
            self.g.nodes,
            {
                1: GraphNode(id=1, position=(0.0, 0.0), external_id=1),
                2: GraphNode(id=2, position=(0.1, 0.0), external_id=2),
                3: GraphNode(id=3, position=(0.2, 0.0), external_id=3),
                4: GraphNode(id=4, position=(0.3, 0.0), external_id=4),
                5: GraphNode(id=5, position=(0.2, 0.1), external_id=5),
                11: GraphNode(id=11, position=(0.1, 0.0), external_id=2),
            },
        )
        self.assertDictEqual(
            self.g.edges,
            {
                1: {11: 200.0},
                2: {1: 200.0, 3: 200.0, 5: 100.0},
                3: {2: 200.0, 4: 200.0},
                4: {3: 200.0, 5: 100.0},
                5: {2: 100.0, 4: 100.0},
                11: {1: 200.0, 3: 200.0},
            },
        )
        self.assertEqual(self.g._phantom_node_id_counter, 11)

    def test_ensure_only_edge(self) -> None:
        change = _GraphChange(self.g)
        cloned = change.restriction_as_cloned_nodes([1, 2, 3, 4])
        self.assertEqual(cloned, [1, 11, 12, 4])
        change.ensure_only_edge(11, 12)
        change.ensure_only_edge(12, 4)
        change.apply()

        self.assertDictEqual(
            self.g.nodes,
            {
                1: GraphNode(id=1, position=(0.0, 0.0), external_id=1),
                2: GraphNode(id=2, position=(0.1, 0.0), external_id=2),
                3: GraphNode(id=3, position=(0.2, 0.0), external_id=3),
                4: GraphNode(id=4, position=(0.3, 0.0), external_id=4),
                5: GraphNode(id=5, position=(0.2, 0.1), external_id=5),
                11: GraphNode(id=11, position=(0.1, 0.0), external_id=2),
                12: GraphNode(id=12, position=(0.2, 0.0), external_id=3),
            },
        )
        self.assertDictEqual(
            self.g.edges,
            {
                1: {11: 200.0},
                2: {1: 200.0, 3: 200.0, 5: 100.0},
                3: {2: 200.0, 4: 200.0},
                4: {3: 200.0, 5: 100.0},
                5: {2: 100.0, 4: 100.0},
                11: {12: 200.0},
                12: {4: 200.0},
            },
        )
        self.assertEqual(self.g._phantom_node_id_counter, 12)
