import bz2
import gzip
import io
import xml.sax
import xml.sax.xmlreader
from dataclasses import dataclass, field
from sys import intern
from typing import IO, Dict, Iterable, List, Literal, Optional, Tuple, Union

from ..protocols import Position


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


def read_features_from_xml(
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


def read_features(
    buf: IO[bytes],
    format: Optional[Literal["xml", "gz", "bz2"]] = None,
    chunk_size: int = io.DEFAULT_BUFFER_SIZE,
) -> Iterable[Feature]:
    """read_features_from_xml generates :py:obj:`Feature` instances from a possibly-compressed
    `OSM XML <https://wiki.openstreetmap.org/wiki/OSM_XML>`_ file.

    If ``format`` is not provided, this function will check if ``buf.name`` endswith
    ``.gz`` or ``.bz2`` to determine whether the provided buffer needs to be decompressed.
    If the compression format cannot be determined, assumes that data will be uncompressed.
    """
    if format == "gz" or (format is None and buf.name.endswith(".gz")):
        with gzip.open(buf, mode="rb") as decompressed_buffer:
            yield from read_features_from_xml(decompressed_buffer, chunk_size)  # type: ignore
    elif format == "bz2" or (format is None and buf.name.endswith(".bz2")):
        with bz2.open(buf, mode="rb") as decompressed_buffer:
            yield from read_features_from_xml(decompressed_buffer, chunk_size)
    else:
        yield from read_features_from_xml(buf, chunk_size)


def collect_all_features(
    buf: IO[bytes],
    format: Optional[Literal["xml", "gz", "bz2"]] = None,
    chunk_size: int = io.DEFAULT_BUFFER_SIZE,
) -> Tuple[List[Node], List[Way], List[Relation]]:
    """collect_all_features reads all :py:obj:`Feature` instances from a possibly-compressed
    `OSM XML <https://wiki.openstreetmap.org/wiki/OSM_XML>`_ file.

    If ``format`` is not provided, this function will check if ``buf.name`` endswith
    ``.gz`` or ``.bz2`` to determine whether the provided buffer needs to be decompressed.
    If the compression format cannot be determined, assumes that data will be uncompressed.
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
