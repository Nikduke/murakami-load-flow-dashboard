"""Semantic channel discovery for PowerFactory result headers."""

from __future__ import annotations

from dataclasses import dataclass
import re
import unicodedata

from data_loader import CaseData, Channel


ROLE_DESCRIPTIONS: dict[str, tuple[str, ...]] = {
    "active_power": ("Active Power in MW",),
    "reactive_power": ("Reactive Power in Mvar",),
    "voltage": ("Voltage, Magnitude in p.u.",),
    "qmin": ("Lower limit of reactive power in Mvar",),
    "qmax": ("Upper limit of reactive power in Mvar",),
    "active_interchange": ("Active Power Interchange in MW",),
    "reactive_interchange": ("Reactive Power Interchange in Mvar",),
    "loading": ("Maximum Loading in %", "Max. Loading in %", "Loading in %"),
}


@dataclass(frozen=True)
class ChannelResolution:
    channel: Channel | None
    status: str
    message: str = ""


def normalise_description(description: str) -> str:
    normalized = unicodedata.normalize("NFKC", description).casefold()
    return " ".join(normalized.split())


def _object_channels(case: CaseData, object_name: str) -> tuple[Channel, ...]:
    return case.channels_for(object_name)


def _unitless_metric(description: str) -> str:
    return normalise_description(re.split(r"\s+in\s+", description, maxsplit=1, flags=re.IGNORECASE)[0])


def resolve_channel(case: CaseData, object_name: str, role: str) -> ChannelResolution:
    channels = _object_channels(case, object_name)
    descriptions = ROLE_DESCRIPTIONS.get(role)
    if descriptions:
        for expected in descriptions:
            matches = [
                channel
                for channel in channels
                if normalise_description(channel.metric_description) == normalise_description(expected)
            ]
            if len(matches) == 1:
                return ChannelResolution(matches[0], "found")
            if len(matches) > 1:
                positions = ", ".join(str(channel.column_position) for channel in matches)
                return ChannelResolution(
                    None,
                    "ambiguous",
                    f"`{object_name}` has duplicate `{expected}` channels at columns {positions}.",
                )

        expected_bases = {_unitless_metric(description) for description in descriptions}
        conflicts = [channel for channel in channels if _unitless_metric(channel.metric_description) in expected_bases]
        if conflicts:
            found = ", ".join(
                f"`{channel.metric_description}` at column {channel.column_position}" for channel in conflicts
            )
            wanted = " or ".join(f"`{description}`" for description in descriptions)
            return ChannelResolution(
                None,
                "unit_conflict",
                f"`{object_name}` has {found}; expected {wanted}.",
            )
        return ChannelResolution(None, "missing", f"`{object_name}` has no channel for `{role}`.")

    if role == "power_factor":
        matches = [
            channel
            for channel in channels
            if normalise_description(channel.metric_description).startswith("power factor")
        ]
        if len(matches) == 1:
            return ChannelResolution(matches[0], "found")
        if len(matches) > 1:
            positions = ", ".join(str(channel.column_position) for channel in matches)
            return ChannelResolution(
                None,
                "ambiguous",
                f"`{object_name}` has multiple power-factor channels at columns {positions}.",
            )
        return ChannelResolution(None, "missing", f"`{object_name}` has no power-factor channel.")

    return ChannelResolution(None, "unknown_role", f"Unknown channel role `{role}`.")


def _has_pair(case: CaseData, object_name: str, first: str, second: str) -> bool:
    return resolve_channel(case, object_name, first).status == "found" and resolve_channel(
        case, object_name, second
    ).status == "found"


def is_wtg_object_name(object_name: str) -> bool:
    """Match a WTG path segment, excluding cables whose names merely mention WTGs."""
    return any(re.match(r"(?i)^WTG(?:\b|\\)", segment.strip()) for segment in object_name.split("\\"))


def discover_wtg_objects(cases: list[CaseData] | tuple[CaseData, ...]) -> list[str]:
    names = {
        object_name
        for case in cases
        for object_name in case.object_names
        if is_wtg_object_name(object_name)
        and (_has_pair(case, object_name, "active_power", "reactive_power")
             or _has_pair(case, object_name, "active_power", "voltage"))
    }
    return sorted(names, key=lambda name: name.casefold())
def discover_loading_objects(cases: list[CaseData] | tuple[CaseData, ...]) -> list[str]:
    names = {
        object_name
        for case in cases
        for object_name in case.object_names
        if resolve_channel(case, object_name, "loading").status == "found"
    }
    return sorted(names, key=lambda name: name.casefold())


def discover_poc_objects(cases: list[CaseData] | tuple[CaseData, ...]) -> list[str]:
    names = {
        object_name
        for case in cases
        for object_name in case.object_names
        if _has_pair(case, object_name, "active_interchange", "reactive_interchange")
    }
    return sorted(names, key=lambda name: name.casefold())


def discover_power_factor_objects(cases: list[CaseData] | tuple[CaseData, ...]) -> list[str]:
    names = {
        object_name
        for case in cases
        for object_name in case.object_names
        if resolve_channel(case, object_name, "power_factor").status == "found"
    }
    return sorted(names, key=lambda name: name.casefold())
