# © Copyright 2024 Mikołaj Kuranowski
# SPDX-License-Identifier: GPL-3.0-or-later

from unittest import TestCase

from .kd import KDTree
from .simple_graph import SimpleNode


class TestKDTree(TestCase):
    def test(self) -> None:
        tree = KDTree[SimpleNode].build(
            [
                SimpleNode(1, (1.0, 1.0)),
                SimpleNode(2, (1.0, 5.0)),
                SimpleNode(3, (3.0, 9.0)),
                SimpleNode(4, (4.0, 3.0)),
                SimpleNode(5, (4.0, 7.0)),
                SimpleNode(6, (6.0, 3.0)),
                SimpleNode(7, (7.0, 1.0)),
                SimpleNode(8, (8.0, 5.0)),
                SimpleNode(9, (8.0, 9.0)),
            ]
        )
        self.assertIsNotNone(tree)
        assert tree is not None  # for type checker

        self.assertEqual(tree.find_nearest_neighbor((2.0, 2.0)).id, 1)
        self.assertEqual(tree.find_nearest_neighbor((5.0, 3.0)).id, 4)
        self.assertEqual(tree.find_nearest_neighbor((5.0, 8.0)).id, 5)
        self.assertEqual(tree.find_nearest_neighbor((9.0, 6.0)).id, 8)
