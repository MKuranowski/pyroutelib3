# © Copyright 2024 Mikołaj Kuranowski
# SPDX-License-Identifier: GPL-3.0-or-later

from logging import getLogger
from math import asinh, atan, degrees, pi, radians, sinh, tan
from os import PathLike
from pathlib import Path
from time import time
from typing import IO, Any, Callable, ContextManager, Iterable, Set, Tuple, Union
from urllib.request import urlretrieve

from filelock import FileLock
from typing_extensions import Self

from ..protocols import Position
from .graph import Graph, GraphNode
from .profile import Profile
from .reader import DEFAULT_CHUNK_SIZE, DEFAULT_FILE_FORMAT, FILE_FORMAT_T, Feature, read_features

logger = getLogger("pyroutelib3.osm.LiveGraph")


class LiveGraph(Graph):
    """LiveGraph extends the :py:class:`osm.Graph` by automatically downloading
    data from the OpenStreetMap API in `tiles <https://wiki.openstreetmap.org/wiki/Slippy_map_tilenames>`_.

    Tiles downloads can be triggered by :py:meth:`find_nearest_node` and :py:meth:`get_edges`.

    The inherited ``from_file`` and ``from_features`` methods should not be used.

    Usage of this class is discouraged, it is much more wise to use :py:class:`osm.Graph` directly
    with `OSM data extracts <https://download.geofabrik.de/>`_, further filtered
    with `osmosis <https://wiki.openstreetmap.org/wiki/Osmosis>`. Example command::

        osmosis \\
            --read-pbf-fast south-korea-latest.osm.pbf \\
            --bounding-box top=35.3207 left=128.8298 bottom=35.0303 right=129.1608 \\
            --tag-filter accept-ways 'highway=*' \\
            --tag-filter accept-relations 'type=restriction' \\
            --used-node \\
            --write-pbf south-korea-trimmed-simplified.osm.pbf
    """

    tile_cache_directory: Path
    """tile_cache_directory is the directory where downloaded tiles are stored.
    Defaults to "tilecache" in current directory. If missing, this directory (and its parents)
    are created.
    """

    tile_expiry_seconds: int
    """Tiles are re-downloaded if older than tile_expiry_seconds. Defaults to 30 days."""

    tile_zoom: int
    """How large should the downloaded tiles be? See https://wiki.openstreetmap.org/wiki/Zoom_levels.
    Note that the OSM API rejects requests with too much data with "400 Bad Request" - if that is
    the case, increase the zoom level.
    """

    osm_api_url: str
    """Format string used for generating URLs with tile data. Must have
    ``left``, ``bottom``, ``right`` and ``top`` placeholders."""

    file_lock: Callable[[Path], ContextManager[Any]]
    """Context manager used to ensure tiles are not downloaded simultaneously.
    Useful if multiple LiveGraphs use the same tile cache directory at the same time.
    Defaults to `filelock.FileLock <https://py-filelock.readthedocs.io/en/latest/api.html#filelock.FileLock>`_.
    """

    _downloaded_tiles: Set[Tuple[int, int]]

    def __init__(
        self,
        profile: Profile,
        tile_cache_directory: Union[str, "PathLike[str]"] = "tilecache",
        tile_expiry_seconds: int = 60 * 60 * 24 * 30,
        tile_zoom: int = 15,
        osm_api_url: str = "https://api.openstreetmap.org/api/0.6/map?bbox={left},{bottom},{right},{top}",
        file_lock: Callable[[Path], ContextManager[Any]] = FileLock,
    ) -> None:
        super().__init__(profile)
        self.tile_cache_directory = Path(tile_cache_directory)
        self.tile_expiry_seconds = tile_expiry_seconds
        self.tile_zoom = tile_zoom
        self.osm_api_url = osm_api_url
        self.file_lock = file_lock
        self._downloaded_tiles = set()

    def find_nearest_node(self, position: Position) -> GraphNode:
        self.load_tile_around(position)
        return super().find_nearest_node(position)

    def get_edges(self, id: int) -> Iterable[Tuple[int, float]]:
        self.load_tile_around(self.nodes[id].position)
        return super().get_edges(id)

    def load_tile_around(self, position: Position) -> None:
        """Ensures the tile in which ``position`` falls is loaded into the graph.

        If that tile is loaded, this function does nothing.

        If that tile is cached (present in :py:attr:`tile_cache_directory`) and reasonably
        up-to-date (as defined by :py:attr:`tile_expiry_seconds`) it is simply loaded.

        Otherwise, this function downloads the tile before loading it.
        """

        tile = _lat_lon_to_tile(position[0], position[1], self.tile_zoom)
        if tile in self._downloaded_tiles:
            return

        self._downloaded_tiles.add(tile)
        tile_directory = self.get_tile_directory(tile)
        tile_directory.mkdir(parents=True, exist_ok=True)
        tile_file = tile_directory / "data.osm"
        tile_lock = tile_directory / "lock"

        with self.file_lock(tile_lock):
            if not self.has_up_to_date_tile(tile_file):
                self.download_tile(tile, tile_file)
            self.load_tile(tile, tile_file)

    def get_tile_directory(self, tile: Tuple[int, int]) -> Path:
        """Returns the directory in which the provided ``tile`` data should be stored."""
        return self.tile_cache_directory / str(self.tile_zoom) / str(tile[0]) / str(tile[1])

    def has_up_to_date_tile(self, tile_file: Path) -> bool:
        """Checks if a tile stored at the provided path is reasonably up-to-date
        (as defined by :py:attr:`tile_expiry_seconds`). If the provided file doesn't exist,
        returns ``False``.
        """
        try:
            downloaded_seconds_ago = time() - tile_file.stat().st_mtime
            return downloaded_seconds_ago < self.tile_expiry_seconds
        except FileNotFoundError:
            return False

    def download_tile(self, tile: Tuple[int, int], tile_file: Path) -> None:
        """Downloads the provided tile (using :py:attr:`osm_api_url`) to the provided path."""
        logger.info("Downloading tile x=%d y=%d zoom=%d", tile[0], tile[1], self.tile_zoom)
        left, bottom, right, top = _tile_boundary(tile[0], tile[1], self.tile_zoom)
        url = self.osm_api_url.format(left=left, bottom=bottom, right=right, top=top)
        urlretrieve(url, tile_file)

    def load_tile(self, tile: Tuple[int, int], tile_file: Path) -> None:
        """Loads the provided tile into the graph."""
        logger.info("Loading tile x=%d y=%d zoom=%d", tile[0], tile[1], self.tile_zoom)
        with tile_file.open("rb") as f:
            self.add_features(read_features(f, format="xml"))

    @classmethod
    def from_file(
        cls,
        profile: Profile,
        buf: IO[bytes],
        format: FILE_FORMAT_T = DEFAULT_FILE_FORMAT,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
    ) -> Self:
        raise RuntimeError("pyroutelib3.osm.LiveGraph.from_file is not supported")

    @classmethod
    def from_features(cls, profile: Profile, features: Iterable[Feature]) -> Self:
        raise RuntimeError("pyroutelib3.osm.LiveGraph.from_features is not supported")


def _lat_lon_to_tile(lat: float, lon: float, zoom: int) -> Tuple[int, int]:
    n = float(2**zoom)
    x = n * ((lon + 180.0) / 360.0)
    y = (1.0 - asinh(tan(radians(lat))) / pi) / 2.0 * n
    return int(x), int(y)


def _tile_boundary(x: int, y: int, zoom: int) -> Tuple[float, float, float, float]:
    n = float(2**zoom)

    longitude_side = 360.0 / n
    left = x * longitude_side - 180.0
    right = left + longitude_side

    top = _mercator_to_lat(pi * (1 - 2 * (y * (1 / n))))
    bottom = _mercator_to_lat(pi * (1 - 2 * ((y + 1) * (1 / n))))

    return left, bottom, right, top


def _mercator_to_lat(x: float) -> float:
    return degrees(atan(sinh(x)))
