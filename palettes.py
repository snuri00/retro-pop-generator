"""Nagai-leaning palettes used to pull a generation back onto a fixed colour set."""

from __future__ import annotations

PALETTES: dict[str, list[str]] = {
    "noon": [
        "#0A3F86", "#0F5AA8", "#1E7ABF", "#3D9BD6", "#79C2E4", "#B9DCEF",
        "#EAF6FC", "#FFFFFF", "#1B7FC4", "#0E5E9C", "#22A7DA", "#8FE0F2",
        "#F2D9D2", "#E0BEB8", "#C79A90", "#F0E5CE", "#3D9E42", "#2F7F35",
        "#1E6B3A", "#12492A", "#8E4A3C", "#5C2B22", "#E2603F", "#F5C451",
        "#2E6E96", "#0A1A2E",
    ],
    "golden": [
        "#0E3F80", "#1D5391", "#3F77B4", "#78A2C8", "#F2A868", "#FDE2AC",
        "#FFF3E2", "#FFFFFF", "#1F6FA8", "#124F7F", "#2E9FC4", "#FFD79B",
        "#F5DFBC", "#DDBE96", "#C09B72", "#FFF0D8", "#3B8C4A", "#2C6B50",
        "#17402F", "#123324", "#A57F52", "#6B4E32", "#D9553B", "#F0B84C",
        "#3A5F80", "#14263D",
    ],
    "sunset": [
        "#152560", "#2E3576", "#5E4890", "#8E5A8C", "#E8633F", "#FFC46B",
        "#FFD9B0", "#FFF1D8", "#1E4E82", "#12305C", "#2A78A4", "#FFB273",
        "#E8C49E", "#C79877", "#A6785C", "#FFDDB4", "#2F6B4A", "#27523F",
        "#152F26", "#0D1F19", "#7E5C3E", "#4A3524", "#C4402F", "#F09A3C",
        "#F0A45C", "#0E1636",
    ],
    "dusk": [
        "#07132F", "#101F45", "#22355F", "#42406C", "#6E4372", "#A85F6A",
        "#D07E62", "#FFD9A0", "#123055", "#0A1E3A", "#1B5578", "#7FB6CC",
        "#B99A8A", "#8E7365", "#6E5850", "#D9B49C", "#24503F", "#1C3B34",
        "#0E211E", "#08130F", "#5A4433", "#33261D", "#B04434", "#E0724F",
        "#FFD98C", "#040A1A",
    ],
}

PALETTE_NAMES = list(PALETTES)


def _hex_to_rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)


def palette_rgb(name: str) -> list[tuple[int, int, int]]:
    return [_hex_to_rgb(c) for c in PALETTES[name]]
