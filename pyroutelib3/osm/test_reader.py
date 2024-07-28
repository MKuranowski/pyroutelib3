# © Copyright 2024 Mikołaj Kuranowski
# SPDX-License-Identifier: GPL-3.0-or-later

from pathlib import Path
from unittest import TestCase

from .reader import Node, Relation, RelationMember, Way, collect_all_features

FIXTURES_DIR = Path(__file__).with_name("test_fixtures")

SIMPLE_GRAPH_NODES = [
    Node(-1, (-2.73495245962, 2.83923666828), {"ref": "-1"}),
    Node(-2, (-2.73242793496, 2.83923765326), {"ref": "-2"}),
    Node(-61, (-2.72972768022, 2.83926371472), {"ref": "-61"}),
    Node(-62, (-2.72938616409, 2.83956383049), {"ref": "-62"}),
    Node(-63, (-2.72907392744, 2.83920771391), {"ref": "-63"}),
    Node(-60, (-2.72941544366, 2.83890759814), {"ref": "-60"}),
    Node(-3, (-2.73243462926, 2.84135576989), {"ref": "-3"}),
    Node(-7, (-2.72941089232, 2.84139901524), {"ref": "-7"}),
    Node(-8, (-2.72825076265, 2.84257281775), {"ref": "-8"}),
    Node(-4, (-2.73083636925, 2.84072562328), {"ref": "-4"}),
    Node(-9, (-2.72638097685, 2.83923674747), {"ref": "-9"}),
    Node(-5, (-2.73091659085, 2.84209711884), {"ref": "-5"}),
]

SIMPLE_GRAPH_WAYS = [
    Way(-100, [-1, -2], {"highway": "primary", "ref": "-100"}),
    Way(-107, [-2, -61], {"highway": "primary", "motor_vehicle": "no", "ref": "-107"}),
    Way(
        -108,
        [-63, -60, -61, -62, -63],
        {"highway": "primary", "junction": "roundabout", "ref": "-108"},
    ),
    Way(-101, [-2, -3], {"highway": "unclassified", "ref": "-101"}),
    Way(-102, [-3, -7], {"highway": "unclassified", "ref": "-102"}),
    Way(-109, [-7, -62], {"highway": "unclassified", "ref": "-109"}),
    Way(-110, [-8, -7], {"highway": "unclassified", "ref": "-110"}),
    Way(-105, [-7, -4], {"highway": "unclassified", "oneway": "yes", "ref": "-105"}),
    Way(-103, [-4, -3], {"highway": "motorway", "ref": "-103"}),
    Way(-111, [-63, -9], {"highway": "primary", "ref": "-111"}),
    Way(-104, [-3, -5], {"highway": "motorway", "ref": "-104"}),
    Way(-106, [-7, -5], {"highway": "unclassified", "oneway": "-1", "ref": "-106"}),
]

SIMPLE_GRAPH_RELATIONS = [
    Relation(
        -200,
        [
            RelationMember("way", -110, "from"),
            RelationMember("node", -7, "via"),
            RelationMember("way", -102, "to"),
        ],
        {"ref": "-200", "restriction": "no_left_turn", "type": "restriction"},
    ),
    Relation(
        -201,
        [
            RelationMember("way", -100, "from"),
            RelationMember("node", -2, "via"),
            RelationMember("way", -101, "to"),
        ],
        {"ref": "-201", "restriction": "only_right_turn", "type": "restriction"},
    ),
    Relation(
        -202,
        [
            RelationMember("way", -102, "from"),
            RelationMember("node", -3, "via"),
            RelationMember("way", -104, "to"),
        ],
        {
            "except": "motorcar",
            "ref": "-202",
            "restriction": "no_left_turn",
            "type": "restriction",
        },
    ),
]


class TestSimpleGraph(TestCase):
    def test_xml(self) -> None:
        with (FIXTURES_DIR / "simple_graph.osm").open("rb") as f:
            nodes, ways, relations = collect_all_features(f)

        self.assertListEqual(nodes, SIMPLE_GRAPH_NODES)
        self.assertListEqual(ways, SIMPLE_GRAPH_WAYS)
        self.assertListEqual(relations, SIMPLE_GRAPH_RELATIONS)

    def test_bz2(self) -> None:
        with (FIXTURES_DIR / "simple_graph.osm.bz2").open("rb") as f:
            nodes, ways, relations = collect_all_features(f)

        self.assertListEqual(nodes, SIMPLE_GRAPH_NODES)
        self.assertListEqual(ways, SIMPLE_GRAPH_WAYS)
        self.assertListEqual(relations, SIMPLE_GRAPH_RELATIONS)

    def test_gzip(self) -> None:
        with (FIXTURES_DIR / "simple_graph.osm.gz").open("rb") as f:
            nodes, ways, relations = collect_all_features(f)

        self.assertListEqual(nodes, SIMPLE_GRAPH_NODES)
        self.assertListEqual(ways, SIMPLE_GRAPH_WAYS)
        self.assertListEqual(relations, SIMPLE_GRAPH_RELATIONS)

    def test_pbf(self) -> None:
        with (FIXTURES_DIR / "simple_graph.osm.pbf").open("rb") as f:
            nodes, ways, relations = collect_all_features(f)

        self.assertEqual(len(nodes), len(SIMPLE_GRAPH_NODES))
        for got_node, expected_node in zip(nodes, SIMPLE_GRAPH_NODES):
            self.assertEqual(got_node.id, expected_node.id)
            self.assertAlmostEqual(got_node.position[0], expected_node.position[0], places=6)
            self.assertAlmostEqual(got_node.position[1], expected_node.position[1], places=6)
            self.assertDictEqual(got_node.tags, expected_node.tags)

        self.assertListEqual(ways, SIMPLE_GRAPH_WAYS)
        self.assertListEqual(relations, SIMPLE_GRAPH_RELATIONS)
