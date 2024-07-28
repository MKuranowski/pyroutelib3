# © Copyright 2024 Mikołaj Kuranowski
# SPDX-License-Identifier: GPL-3.0-or-later

# pyright: reportPrivateUsage=false

import os
import time
from io import BytesIO
from math import isclose
from pathlib import Path
from shutil import copy
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, urlparse

from ..router import find_route
from .live_graph import LiveGraph
from .profile import CarProfile

FIXTURES_DIR = Path(__file__).with_name("test_fixtures")

# tile_base.osm data contains basic OSM data spread across 2 tiles:
# tile_1.osm, x=27686 y=14099 z=15, left=124.16748046875 bottom=24.327076540018638
#    right=124.178466796875 top=24.33708698241049
# tile_2.osm, x=27687 y=14099 z=15, left=124.178466796875 bottom=24.327076540018638
#    right=124.189453125 top=24.33708698241049
#
# To generate the two tile files run:
# osmosis --rx tile_base.osm --bb x1=$TILE_X y1=$TILE_Y zoom=15 completeWays=true --wx tile_$N.osm


def mock_urlretrieve(url: str, filename: Path) -> None:
    query = parse_qs(urlparse(url).query)
    left, bottom, right, top = map(float, query["bbox"][0].split(","))

    if not isclose(bottom, 24.327076540018638) or not isclose(top, 24.33708698241049):
        raise ValueError("unknown tile")

    if isclose(left, 124.16748046875) and isclose(right, 124.178466796875):
        copy(FIXTURES_DIR / "tile_1.osm", filename)
    elif isclose(left, 124.178466796875) and isclose(right, 124.189453125):
        copy(FIXTURES_DIR / "tile_2.osm", filename)
    else:
        raise ValueError("unknown tile")


class TestLiveGraph(TestCase):

    @patch("pyroutelib3.osm.live_graph.urlretrieve", side_effect=mock_urlretrieve)
    def test(self, urlretrieve_mock: MagicMock) -> None:
        with TemporaryDirectory() as temp_dir_name:
            temp_dir = Path(temp_dir_name)
            g = LiveGraph(CarProfile(), tile_cache_directory=temp_dir)

            start = g.find_nearest_node((24.33163, 124.1718)).id
            self.assertEqual(start, -25358)
            self.assertSetEqual(g._downloaded_tiles, {(27686, 14099)})

            end = g.find_nearest_node((24.33178, 124.18346)).id
            self.assertEqual(end, -25418)
            self.assertSetEqual(g._downloaded_tiles, {(27686, 14099), (27687, 14099)})

            r = find_route(g, start, end)
            self.assertEqual(r[0], start)
            self.assertEqual(r[-1], end)

        self.assertEqual(urlretrieve_mock.call_count, 2)
        urlretrieve_mock.assert_any_call(
            "https://api.openstreetmap.org/api/0.6/map?bbox=124.16748046875,24.327076540018638,124.178466796875,24.33708698241049",
            temp_dir / "15" / "27686" / "14099" / "data.osm",
        )
        urlretrieve_mock.assert_any_call(
            "https://api.openstreetmap.org/api/0.6/map?bbox=124.178466796875,24.327076540018638,124.189453125,24.33708698241049",
            temp_dir / "15" / "27687" / "14099" / "data.osm",
        )

    @patch("pyroutelib3.osm.live_graph.urlretrieve", side_effect=mock_urlretrieve)
    def test_re_downloads_expired(self, urlretrieve_mock: MagicMock) -> None:
        with TemporaryDirectory() as temp_dir_name:
            temp_dir = Path(temp_dir_name)
            tile_dir = temp_dir / "15" / "27686" / "14099"
            tile_dir.mkdir(parents=True)
            tile_file = tile_dir / "data.osm"
            tile_file.touch()
            now = time.time()
            forty_days_ago = now - 40 * 24 * 60 * 60
            os.utime(tile_file, (forty_days_ago, forty_days_ago))
            time.sleep(0.01)  # required for the modification time to propagate

            g = LiveGraph(CarProfile(), tile_cache_directory=temp_dir)
            start = g.find_nearest_node((24.33163, 124.1718)).id
            self.assertEqual(start, -25358)
            self.assertSetEqual(g._downloaded_tiles, {(27686, 14099)})

            self.assertGreaterEqual(tile_file.stat().st_mtime, now)
            urlretrieve_mock.assert_called_once_with(
                "https://api.openstreetmap.org/api/0.6/map?bbox=124.16748046875,24.327076540018638,124.178466796875,24.33708698241049",
                temp_dir / "15" / "27686" / "14099" / "data.osm",
            )

    @patch("pyroutelib3.osm.live_graph.urlretrieve", side_effect=mock_urlretrieve)
    def test_skips_not_expired(self, urlretrieve_mock: MagicMock) -> None:
        with TemporaryDirectory() as temp_dir_name:
            temp_dir = Path(temp_dir_name)
            tile_dir = temp_dir / "15" / "27686" / "14099"
            tile_dir.mkdir(parents=True)
            tile_file = tile_dir / "data.osm"
            copy(FIXTURES_DIR / "tile_1.osm", tile_file)
            now = time.time()
            two_hours_ago = now - 2 * 60 * 60
            os.utime(tile_file, (two_hours_ago, two_hours_ago))
            time.sleep(0.01)  # required for the modification time to propagate

            g = LiveGraph(CarProfile(), tile_cache_directory=temp_dir)
            start = g.find_nearest_node((24.33163, 124.1718)).id
            self.assertEqual(start, -25358)
            self.assertSetEqual(g._downloaded_tiles, {(27686, 14099)})

            self.assertAlmostEqual(tile_file.stat().st_mtime, two_hours_ago)
            urlretrieve_mock.assert_not_called()

    def test_from_file(self) -> None:
        with self.assertRaises(RuntimeError):
            LiveGraph.from_file(CarProfile(), BytesIO(), "xml")

    def test_from_features(self) -> None:
        with self.assertRaises(RuntimeError):
            LiveGraph.from_features(CarProfile(), [])
