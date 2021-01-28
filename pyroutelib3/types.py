# ---------------------------------------------------------------------------
# Loading OSM data and doing routing with it
# ---------------------------------------------------------------------------
# Copyright 2007, Oliver White
# Modifications: Copyright 2017-2021, Mikolaj Kuranowski -
# Based on https://github.com/gaulinmp/pyroutelib2
# ---------------------------------------------------------------------------
# This file is part of pyroutelib3.
#
# pyroutelib3 is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# pyroutelib3 is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with pyroutelib3. If not, see <http://www.gnu.org/licenses/>.
# ---------------------------------------------------------------------------
# Changelog:
#  2020-10-23  MK   Refactor code
# ---------------------------------------------------------------------------

"""Contains default routing types (aka profiles)"""

from typing import Any, Mapping, Sequence
from typing_extensions import TypedDict
import collections.abc

from .err import InvalidTypeDescription


class TypeDescription(TypedDict):
    name: str
    weights: Mapping[str, float]
    access: Sequence[str]


def validate_type(in_type: Mapping[str, Any]) -> TypeDescription:
    """Validates if incoming 'type' dictionary conforms to TypeDescription"""
    # Check if all keys are there
    missing_keys = {"name", "weights", "access"}.difference(in_type.keys())
    if missing_keys:
        missing_keys = ", ".join(repr(i) for i in sorted(missing_keys))
        raise InvalidTypeDescription("Provided type description is missing some keys: "
                                     + missing_keys)

    # Check in_type['name']
    if not isinstance(in_type["name"], str):
        got_type = type(in_type["name"]).__name__
        raise InvalidTypeDescription(f"Value of type['name'] should be str, not {got_type}")

    # Check in_type['weights']
    if not isinstance(in_type["weights"], collections.abc.Mapping):
        got_type = type(in_type["weights"]).__name__
        raise InvalidTypeDescription(
            "Value of type['weights'] should be an instance of collections.abc.Mapping "
            f"(e.g. a dict), but {got_type} was provided"
        )

    # Check in_type['access']
    if not isinstance(in_type["access"], collections.abc.Sequence):
        got_type = type(in_type["access"]).__name__
        raise InvalidTypeDescription(
            "Value of type['access'] should be an instance of collections.abc.Sequence "
            f"(e.g. a list), but {got_type} was provided"
        )

    return in_type  # type: ignore


TYPES: Mapping[str, TypeDescription] = {
    "car": {
        "name": "motorcar",
        "weights": {
            "motorway": 10, "trunk": 10, "primary": 2, "secondary": 1.5, "tertiary": 1,
            "unclassified": 1, "residential": 0.7, "living_street": 0.5, "track": 0.5,
            "service": 0.5,
        },
        "access": ["access", "vehicle", "motor_vehicle", "motorcar"]},
    "bus": {
        "name": "bus",
        "weights": {
            "motorway": 10, "trunk": 10, "primary": 2, "secondary": 1.5, "tertiary": 1,
            "unclassified": 1, "residential": 0.8, "track": 0.3, "service": 0.9,
        },
        "access": ["access", "vehicle", "motor_vehicle", "psv", "bus"]},
    "cycle": {
        "name": "bicycle",
        "weights": {
            "trunk": 0.05, "primary": 0.3, "secondary": 0.9, "tertiary": 1,
            "unclassified": 1, "cycleway": 2, "residential": 2.5, "living_street": 1,
            "track": 1, "service": 1, "bridleway": 0.8, "footway": 0.8, "steps": 0.5, "path": 1,
        },
        "access": ["access", "vehicle", "bicycle"]},
    "horse": {
        "name": "horse",
        "weights": {
            "primary": 0.05, "secondary": 0.15, "tertiary": 0.3, "unclassified": 1,
            "residential": 1, "living_street": 1, "track": 1.5, "service": 1,
            "bridleway": 5, "path": 1.5,
        },
        "access": ["access", "horse"]},
    "foot": {
        "name": "foot",
        "weights": {
            "trunk": 0.3, "primary": 0.6, "secondary": 0.95, "tertiary": 1,
            "unclassified": 1, "residential": 1, "living_street": 1, "track": 1, "service": 1,
            "bridleway": 1, "footway": 1.2, "path": 1.2, "steps": 1.15,
        },
        "access": ["access", "foot"]},
    "tram": {
        "name": "tram",
        "weights": {"tram": 1, "light_rail": 1},
        "access": ["access"]},
    "train": {
        "name": "train",
        "weights": {"rail": 1, "light_rail": 1, "subway": 1, "narrow_guage": 1},
        "access": ["access"]}
}
