# © Copyright 2024 Mikołaj Kuranowski
# SPDX-License-Identifier: GPL-3.0-or-later

from unittest import TestCase

from .distance import euclidean_distance, haversine_earth_distance, taxicab_distance


class TestEuclideanDistance(TestCase):
    def test(self) -> None:
        self.assertAlmostEqual(
            euclidean_distance((-1.0, 0.5), (4.0, 3.12)),
            5.644856065,
        )


class TestTaxicabDistance(TestCase):
    def test(self) -> None:
        self.assertAlmostEqual(
            taxicab_distance((-1.0, 0.5), (4.0, 3.12)),
            7.62,
        )


class TestHaversineEarthDistance(TestCase):
    CENTRUM = (52.23024, 21.01062)
    STADION = (52.23852, 21.0446)
    FALENICA = (52.16125, 21.21147)

    def test_centrum_stadion(self):
        self.assertAlmostEqual(
            haversine_earth_distance(self.CENTRUM, self.STADION),
            2.49045686,
        )

    def test_centrum_falenica(self):
        self.assertAlmostEqual(
            haversine_earth_distance(self.CENTRUM, self.FALENICA),
            15.69257588,
        )
