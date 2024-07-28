# © Copyright 2024 Mikołaj Kuranowski
# SPDX-License-Identifier: GPL-3.0-or-later

from unittest import TestCase

from .distance import euclidean_distance
from .router import StepLimitExceeded, find_route, find_route_without_turn_around
from .simple_graph import SimpleExternalNode, SimpleGraph, SimpleNode


class TestFindRoute(TestCase):
    def test_simple(self) -> None:
        #  (20)  (20)  (20)
        # 1─────2─────3─────4
        #       └─────5─────┘
        #        (10)   (10)
        g = SimpleGraph(
            nodes={
                1: SimpleNode(1, (1, 1)),
                2: SimpleNode(2, (2, 1)),
                3: SimpleNode(3, (3, 1)),
                4: SimpleNode(4, (4, 1)),
                5: SimpleNode(5, (3, 0)),
            },
            edges={
                1: {2: 20},
                2: {1: 20, 3: 20, 5: 10},
                3: {2: 20, 4: 20},
                4: {3: 20, 5: 10},
                5: {2: 10, 4: 10},
            },
        )

        self.assertListEqual(
            find_route(g, 1, 4, distance=euclidean_distance),
            [1, 2, 5, 4],
        )

    def test_shortest_not_optimal(self) -> None:
        #     50    10
        #  7─────8─────9
        #  │     │     │
        #  │40   │30   │10
        #  │ 20  │ 40  │
        #  4─────5─────6
        #  │     │     │
        #  │60   │50   │10
        #  │ 10  │ 20  │
        #  1─────2─────3
        g = SimpleGraph(
            nodes={
                1: SimpleNode(1, (0, 0)),
                2: SimpleNode(2, (1, 0)),
                3: SimpleNode(3, (2, 0)),
                4: SimpleNode(4, (0, 1)),
                5: SimpleNode(5, (1, 1)),
                6: SimpleNode(6, (2, 1)),
                7: SimpleNode(7, (0, 2)),
                8: SimpleNode(8, (1, 2)),
                9: SimpleNode(9, (2, 2)),
            },
            edges={
                1: {2: 10, 4: 60},
                2: {1: 10, 3: 20, 5: 50},
                3: {2: 20, 6: 10},
                4: {1: 60, 5: 20, 7: 40},
                5: {2: 50, 4: 20, 6: 40, 8: 30},
                6: {3: 10, 5: 40, 9: 10},
                7: {4: 40, 8: 50},
                8: {5: 30, 7: 50, 9: 10},
                9: {6: 10, 8: 10},
            },
        )

        self.assertListEqual(
            find_route(g, 1, 8, distance=euclidean_distance),
            [1, 2, 3, 6, 9, 8],
        )

    def test_step_limit(self) -> None:
        #  (20)  (20)  (20)
        # 1─────2─────3─────4
        #       └─────5─────┘
        #        (10)   (10)
        g = SimpleGraph(
            nodes={
                1: SimpleNode(1, (1, 1)),
                2: SimpleNode(2, (2, 1)),
                3: SimpleNode(3, (3, 1)),
                4: SimpleNode(4, (4, 1)),
                5: SimpleNode(5, (3, 0)),
            },
            edges={
                1: {2: 20},
                2: {1: 20, 3: 20, 5: 10},
                3: {2: 20, 4: 20},
                4: {3: 20, 5: 10},
                5: {2: 10, 4: 10},
            },
        )

        with self.assertRaises(StepLimitExceeded):
            find_route(g, 1, 4, distance=euclidean_distance, step_limit=2)


class TestFindRouteWithoutTurnAround(TestCase):
    def test(self) -> None:
        # 1
        # │
        # │10
        # │ 10
        # 2─────4
        # │     │
        # │10   │100
        # │ 10  │
        # 3─────5
        # mandatory 1-2-4
        g = SimpleGraph(
            nodes={
                1: SimpleExternalNode.with_same_external_id(1, (0, 2)),
                2: SimpleExternalNode.with_same_external_id(2, (0, 1)),
                20: SimpleExternalNode(20, (0, 1), external_id=2),
                3: SimpleExternalNode.with_same_external_id(3, (0, 0)),
                4: SimpleExternalNode.with_same_external_id(4, (1, 1)),
                5: SimpleExternalNode.with_same_external_id(5, (1, 0)),
            },
            edges={
                1: {20: 10},
                2: {1: 10, 3: 10, 4: 10},
                20: {4: 10},
                3: {2: 10, 5: 10},
                4: {2: 10, 5: 100},
                5: {3: 10, 4: 100},
            },
        )

        self.assertListEqual(
            find_route(g, 1, 3, distance=euclidean_distance),
            [1, 20, 4, 2, 3],
        )

        self.assertListEqual(
            find_route_without_turn_around(g, 1, 3, distance=euclidean_distance),
            [1, 20, 4, 5, 3],
        )

    def test_step_limit(self) -> None:
        #  (20)  (20)  (20)
        # 1─────2─────3─────4
        #       └─────5─────┘
        #        (10)   (10)
        g = SimpleGraph(
            nodes={
                1: SimpleExternalNode.with_same_external_id(1, (1, 1)),
                2: SimpleExternalNode.with_same_external_id(2, (2, 1)),
                3: SimpleExternalNode.with_same_external_id(3, (3, 1)),
                4: SimpleExternalNode.with_same_external_id(4, (4, 1)),
                5: SimpleExternalNode.with_same_external_id(5, (3, 0)),
            },
            edges={
                1: {2: 20},
                2: {1: 20, 3: 20, 5: 10},
                3: {2: 20, 4: 20},
                4: {3: 20, 5: 10},
                5: {2: 10, 4: 10},
            },
        )

        with self.assertRaises(StepLimitExceeded):
            find_route_without_turn_around(g, 1, 4, distance=euclidean_distance, step_limit=2)
