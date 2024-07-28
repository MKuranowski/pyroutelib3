# © Copyright 2024 Mikołaj Kuranowski
# SPDX-License-Identifier: GPL-3.0-or-later

from dataclasses import dataclass
from operator import itemgetter
from typing import Any, Dict
from unittest import TestCase

from .nx import ExternalGraphAdaptor, GraphAdaptor


@dataclass
class NxDiGraphMock:
    nodes: Dict[int, Dict[str, Any]]
    adj: Dict[int, Dict[int, Dict[str, Any]]]


class TestNetworkxAdaptors(TestCase):
    def setUp(self) -> None:
        #  (20)  (20)  (20)
        # 1─────2─────3─────4
        #       └─────5─────┘
        #        (10)   (10)
        self.g = NxDiGraphMock(
            nodes={
                1: {"x": 1, "y": 1, "external_id": 101},
                2: {"x": 2, "y": 1, "external_id": 102},
                3: {"x": 3, "y": 1, "external_id": 103},
                4: {"x": 4, "y": 1, "external_id": 104},
                5: {"x": 3, "y": 0, "external_id": 105},
            },
            adj={
                1: {2: {"weight": 20}},
                2: {1: {"weight": 20}, 3: {"weight": 20}, 5: {"weight": 10}},
                3: {2: {"weight": 20}, 4: {"weight": 20}},
                4: {3: {"weight": 20}, 5: {"weight": 10}},
                5: {2: {"weight": 10}, 4: {"weight": 10}},
            },
        )

    def test_plain(self) -> None:
        a = GraphAdaptor(self.g, node_position_getter=itemgetter("x", "y"))

        n = a.get_node(3)
        self.assertEqual(n.id, 3)
        self.assertEqual(n.position, (3, 1))

        with self.assertRaises(KeyError):
            a.get_node(42)

        self.assertSetEqual(set(a.get_edges(2)), {(1, 20), (3, 20), (5, 10)})

    def test_external(self) -> None:
        a = ExternalGraphAdaptor(self.g, node_position_getter=itemgetter("x", "y"))

        n = a.get_node(3)
        self.assertEqual(n.id, 3)
        self.assertEqual(n.external_id, 103)
        self.assertEqual(n.position, (3, 1))

        with self.assertRaises(KeyError):
            a.get_node(42)

        self.assertSetEqual(set(a.get_edges(2)), {(1, 20), (3, 20), (5, 10)})
