# © Copyright 2024 Mikołaj Kuranowski
# SPDX-License-Identifier: GPL-3.0-or-later

import bz2
import gzip
import io
import lzma
import struct
import xml.sax
import xml.sax.xmlreader
import zlib
from dataclasses import dataclass, field
from sys import intern
from typing import IO, Dict, Iterable, List, Literal, Optional, Sequence, Tuple, Union

from ..protocols import Position
from .pbf import fileformat_pb2, osmformat_pb2

FILE_FORMAT_T = Optional[Literal["xml", "gz", "bz2", "pbf"]]
"""Type of the ``format`` argument of :py:func:`read_features`.

Useful when passing this argument forward from custom functions.
"""

DEFAULT_FILE_FORMAT = None
"""Default value for the ``format`` argument of :py:func:`read_features`.

Useful when passing this argument forward from custom functions.
"""

DEFAULT_CHUNK_SIZE = io.DEFAULT_BUFFER_SIZE
"""Default value for ``chunk_size`` argument of :py:func:`read_features`,
`io.DEFAULT_BUFFER_SIZE <https://docs.python.org/3/library/io.html#io.DEFAULT_BUFFER_SIZE>`_.

Useful when passing this argument forward from custom functions.
"""


@dataclass
class Node:
    """Node represents a single `OpenStreetMap node <https://wiki.openstreetmap.org/wiki/Node>`_."""

    id: int
    position: Position
    tags: Dict[str, str] = field(default_factory=dict)


@dataclass
class Way:
    """Way represents a single `OpenStreetMap way <https://wiki.openstreetmap.org/wiki/Way>`_."""

    id: int
    nodes: List[int] = field(default_factory=list)
    tags: Dict[str, str] = field(default_factory=dict)

    def is_closed(self) -> bool:
        return bool(self.nodes) and self.nodes[0] == self.nodes[-1]


@dataclass
class RelationMember:
    """RelationMember represents a single member of a
    `OpenStreetMap relation <https://wiki.openstreetmap.org/wiki/Relation>`_.
    """

    type: Literal["node", "way", "relation"]
    ref: int
    role: str


@dataclass
class Relation:
    """Relation represents a single `OpenStreetMap relation <https://wiki.openstreetmap.org/wiki/Relation>`_."""

    id: int
    members: List[RelationMember] = field(default_factory=list)
    tags: Dict[str, str] = field(default_factory=dict)


Feature = Union[Node, Way, Relation]
"""Feature represents a single `OpenStreetMap feature <https://wiki.openstreetmap.org/wiki/Map_features>`_:
a :py:class:`Node`, :py:class:`Way` or :py:class:`Relation`.
"""


class _OSMContentHandler(xml.sax.ContentHandler):
    def __init__(self) -> None:
        super().__init__()
        self.ready_features: List[Feature] = []
        self.current_feature: Optional[Feature] = None

    def startElement(self, name: str, attrs: "xml.sax.xmlreader.AttributesImpl") -> None:
        if name == "node":
            self.current_feature = Node(
                id=int(attrs["id"]),
                position=(float(attrs["lat"]), float(attrs["lon"])),
            )

        elif name == "way":
            self.current_feature = Way(id=int(attrs["id"]))

        elif name == "relation":
            self.current_feature = Relation(id=int(attrs["id"]))

        elif name == "tag":
            if self.current_feature:
                self.current_feature.tags[attrs["k"]] = attrs["v"]

        elif name == "nd":
            if isinstance(self.current_feature, Way):
                self.current_feature.nodes.append(int(attrs["ref"]))

        elif name == "member":
            # fmt: off
            if (
                isinstance(self.current_feature, Relation)
                and attrs["type"] in ("node", "way", "relation")
            ):
                # fmt: on
                self.current_feature.members.append(
                    RelationMember(
                        type=intern(attrs["type"]),  # type: ignore
                        ref=int(attrs["ref"]),
                        role=attrs.get("role", ""),
                    ),
                )

    def endElement(self, name: str) -> None:
        if name in ("node", "way", "relation") and self.current_feature:
            self.ready_features.append(self.current_feature)
            self.current_feature = None


def _read_features_from_xml(
    buf: Union[IO[bytes], IO[str]],
    chunk_size: int = io.DEFAULT_BUFFER_SIZE,
) -> Iterable[Feature]:
    """read_features_from_xml generates :py:obj:`Feature` instances from an
    `OSM XML <https://wiki.openstreetmap.org/wiki/OSM_XML>`_ file."""

    parser = xml.sax.make_parser()
    if not isinstance(parser, xml.sax.xmlreader.IncrementalParser):
        raise RuntimeError(
            "expected xml.sax.make_parser() to return an IncrementalParser, but got "
            + type(parser).__qualname__
        )
    handler = _OSMContentHandler()
    parser.setContentHandler(handler)

    while data := buf.read(chunk_size):
        parser.feed(data)  # type: ignore

        if handler.ready_features:
            yield from handler.ready_features
            handler.ready_features.clear()

    parser.close()  # type: ignore
    if handler.ready_features:
        yield from handler.ready_features


class PBFError(ValueError):
    """Exception raised by :py:func:`read_features` on invalid
    `OSM PBF <https://wiki.openstreetmap.org/wiki/PBF_Format>`_ encoding."""

    pass


@dataclass
class _PBFParser:
    buffer: IO[bytes]

    granularity: int = 100
    lat_offset: int = 0
    lon_offset: int = 0
    date_granularity: int = 1000
    string_table: List[str] = field(default_factory=list)

    def parse(self) -> Iterable[Feature]:
        self._read_and_check_header_blob()
        while blob := self._read_data_blob():
            yield from self._parse_data_blob(blob)

    def _read_blob_header(self, type: str) -> Optional[fileformat_pb2.BlobHeader]:
        header_len_bytes = self.buffer.read(4)
        if len(header_len_bytes) == 0:
            return None
        elif len(header_len_bytes) != 4:
            raise PBFError("Unexpected EOF when trying to read BlobHeader length")

        header_len: int = struct.unpack("!L", header_len_bytes)[0]
        blob_header = fileformat_pb2.BlobHeader()
        blob_header.ParseFromString(self.buffer.read(header_len))

        if blob_header.type != type:
            raise PBFError(
                f"Expected a BlobHeader with type={type!r}, but got {blob_header.type!r}"
            )

        return blob_header

    def _read_blob(self, blob_len: int) -> bytes:
        blob = fileformat_pb2.Blob()
        blob.ParseFromString(self.buffer.read(blob_len))

        if blob.HasField("raw"):
            return blob.raw
        elif blob.HasField("zlib_data"):
            return zlib.decompress(blob.zlib_data)
        elif blob.HasField("lzma_data"):
            return lzma.decompress(blob.lzma_data)
        elif blob.HasField("OBSOLETE_bzip2_data"):
            return bz2.decompress(blob.OBSOLETE_bzip2_data)
        elif blob.HasField("lz4_data"):
            raise PBFError("Blob uses unsupported compression, LZ4")
        elif blob.HasField("zstd_data"):
            raise PBFError("Blob uses unsupported compression, ZSTD")

        raise PBFError("Blob has no data or uses an unsupported compression")

    def _read_and_check_header_blob(self) -> None:
        blob_header = self._read_blob_header("OSMHeader")
        if blob_header is None:
            raise PBFError("OSMHeader blob missing - is the file empty?")

        header = osmformat_pb2.HeaderBlock()
        header.ParseFromString(self._read_blob(blob_header.datasize))

        unknown_required_features = set(header.required_features) - {"OsmSchema-V0.6", "DenseNodes"}
        if unknown_required_features:
            raise PBFError(
                "HeaderBlock requests unsupported features: "
                + ", ".join(sorted(unknown_required_features))
            )

    def _read_data_blob(self) -> Optional[bytes]:
        blob_header = self._read_blob_header("OSMData")
        if blob_header is None:
            return None
        return self._read_blob(blob_header.datasize)

    def _parse_data_blob(self, blob: bytes) -> Iterable[Feature]:
        primitive_block = osmformat_pb2.PrimitiveBlock()
        primitive_block.ParseFromString(blob)

        self.granularity = primitive_block.granularity
        self.lat_offset = primitive_block.lat_offset
        self.lon_offset = primitive_block.lon_offset
        self.date_granularity = primitive_block.date_granularity
        self.string_table = [s.decode("utf-8") for s in primitive_block.stringtable.s]

        for primitive_group in primitive_block.primitivegroup:
            yield from self._parse_primitive_group(primitive_group)

    def _parse_primitive_group(
        self,
        primitive_group: osmformat_pb2.PrimitiveGroup,
    ) -> Iterable[Feature]:
        yield from map(self._parse_node, primitive_group.nodes)
        if primitive_group.HasField("dense"):
            yield from self._parse_dense_nodes(primitive_group.dense)
        yield from map(self._parse_way, primitive_group.ways)
        yield from map(self._parse_relation, primitive_group.relations)

    def _parse_node(self, node: osmformat_pb2.Node) -> Node:
        return Node(
            id=node.id,
            position=(self._parse_lat(node.lat), self._parse_lon(node.lon)),
            tags=self._parse_tags(node.keys, node.vals),
        )

    def _parse_dense_nodes(self, dense_nodes: osmformat_pb2.DenseNodes) -> Iterable[Node]:
        if dense_nodes.keys_vals:
            for id, lat, lon, tags in zip(
                self._decode_deltas(dense_nodes.id),
                self._decode_deltas(dense_nodes.lat),
                self._decode_deltas(dense_nodes.lon),
                self._parse_dense_tags(dense_nodes.keys_vals),
                # strict=True,  # TODO: Backport zip with strict=True
            ):
                yield Node(
                    id=id,
                    position=(self._parse_lat(lat), self._parse_lon(lon)),
                    tags=tags,
                )
        else:
            for id, lat, lon in zip(
                self._decode_deltas(dense_nodes.id),
                self._decode_deltas(dense_nodes.lat),
                self._decode_deltas(dense_nodes.lon),
                # strict=True  # TODO: Backport zip with strict=True,
            ):
                yield Node(
                    id=id,
                    position=(self._parse_lat(lat), self._parse_lon(lon)),
                )

    def _parse_way(self, way: osmformat_pb2.Way) -> Way:
        return Way(
            id=way.id,
            nodes=list(self._decode_deltas(way.refs)),
            tags=self._parse_tags(way.keys, way.vals),
        )

    def _parse_relation(self, relation: osmformat_pb2.Relation) -> Relation:
        return Relation(
            id=relation.id,
            members=[
                RelationMember(
                    type=self._parse_member_type(member_type),
                    ref=member_id,
                    role=self.string_table[role_idx],
                )
                for role_idx, member_id, member_type in zip(
                    relation.roles_sid,
                    self._decode_deltas(relation.memids),
                    relation.types,
                    # strict=True,  # TODO: Backport zip with strict=True
                )
            ],
            tags=self._parse_tags(relation.keys, relation.vals),
        )

    def _parse_tags(self, keys: Iterable[int], values: Iterable[int]) -> Dict[str, str]:
        return {
            self.string_table[k]: self.string_table[v]
            for k, v in zip(keys, values)
            # TODO: Backport zip with strict=True
        }

    def _parse_lat(self, lat: int) -> float:
        return 1e-9 * (self.lat_offset + (self.granularity * lat))

    def _parse_lon(self, lon: int) -> float:
        return 1e-9 * (self.lon_offset + (self.granularity * lon))

    def _decode_deltas(self, deltas: Iterable[int]) -> Iterable[int]:
        value = 0
        for delta in deltas:
            value += delta
            yield value

    def _parse_dense_tags(self, string_indices: Sequence[int]) -> Iterable[Dict[str, str]]:
        idx = 0
        last = len(string_indices)
        while idx < last:
            tags: Dict[str, str] = {}
            while string_indices[idx] != 0:
                k_idx = string_indices[idx]
                v_idx = string_indices[idx + 1]
                tags[self.string_table[k_idx]] = self.string_table[v_idx]
                idx += 2
            yield tags
            idx += 1

    @staticmethod
    def _parse_member_type(
        t: osmformat_pb2.Relation.MemberType,
    ) -> Literal["node", "way", "relation"]:
        return ("node", "way", "relation")[t]


def read_features(
    buf: IO[bytes],
    format: FILE_FORMAT_T = DEFAULT_FILE_FORMAT,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
) -> Iterable[Feature]:
    """read_features_from_xml generates :py:obj:`Feature` instances from a possibly-compressed
    `OSM XML <https://wiki.openstreetmap.org/wiki/OSM_XML>`_ or a
    `OSM PBF <https://wiki.openstreetmap.org/wiki/PBF_Format>`_ file.

    If ``format`` is not provided, this function will check if ``buf.name`` ends with
    ``.gz`` or ``.bz2`` to determine whether the provided buffer needs to be decompressed,
    or ``.pbf`` to use the protocol buffer deserializer. If the file format cannot be
    determined, assumes that data will be in uncompressed XML format.

    The ``chunk_size`` argument controls the size of XML data chunks read from the XML stream,
    after decompression. Read calls to ``buf`` of ``chunk_size`` are only guaranteed for
    non-compressed XML files. Size of the read calls for gzip or bz2 compressed XML files
    depends on the inner workings of the ``gz`` and ``bz2`` modules, while for ``pbf`` files
    read calls can range from 4 bytes to 32 MiB, depending on the size of the object
    being deserialized.
    """
    if format == "gz" or (format is None and buf.name.endswith(".gz")):
        with gzip.open(buf, mode="rb") as decompressed_buffer:
            yield from _read_features_from_xml(decompressed_buffer, chunk_size)  # type: ignore
    elif format == "bz2" or (format is None and buf.name.endswith(".bz2")):
        with bz2.open(buf, mode="rb") as decompressed_buffer:
            yield from _read_features_from_xml(decompressed_buffer, chunk_size)
    elif format == "pbf" or (format is None and buf.name.endswith(".pbf")):
        yield from _PBFParser(buf).parse()
    else:
        yield from _read_features_from_xml(buf, chunk_size)


def collect_all_features(
    buf: IO[bytes],
    format: FILE_FORMAT_T = DEFAULT_FILE_FORMAT,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
) -> Tuple[List[Node], List[Way], List[Relation]]:
    """collect_all_features reads all :py:obj:`Feature` instances from a possibly-compressed
    `OSM XML <https://wiki.openstreetmap.org/wiki/OSM_XML>`_ or a
    `OSM PBF <https://wiki.openstreetmap.org/wiki/PBF_Format>`_ file.

    ``format`` and ``chunk_size`` are passed through to :py:func:`osm.reader.read_features`.
    """

    nodes: List[Node] = []
    ways: List[Way] = []
    relations: List[Relation] = []

    for feature in read_features(buf, format, chunk_size):
        if isinstance(feature, Node):
            nodes.append(feature)
        elif isinstance(feature, Way):
            ways.append(feature)
        else:
            relations.append(feature)

    return nodes, ways, relations
