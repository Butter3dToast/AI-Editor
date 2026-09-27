"""Marker keys that OBS catches for us (manual chapter 7.4a).

Why: Windows lets a game switch off other programs' hotkeys while it's in
front, and League of Legends does -- on the creator's first League stream with
the Companion, Numpad + only worked after alt-tabbing out. OBS's own hotkeys
keep working in games, so the key is bound in OBS instead.

How: a scene called "AI-Editor markers" holds two empty 1x1 sources. The
creator binds OBS's "Show 'Mark moment'" hotkey to Numpad + (and "Show 'Mark
Short'" to Numpad -). Pressing it switches the source on; OBS tells the
Companion; the Companion logs the marker and switches the source off again,
ready for the next press. The scene is never put on air, so viewers can't see
or hear any of it, and no keyboard code of ours is involved at all.
"""

from __future__ import annotations

from typing import Any

from ..logging_setup import get_logger
from .obs import ObsClient, ObsRequestFailed

log = get_logger(__name__)

MARKER_SCENE = "AI-Editor markers"
MARKER_SOURCES = {"moment": "Mark moment", "short": "Mark Short"}

# An empty, fully transparent 1x1 colour: nothing to see even if the scene
# were ever shown by mistake.
_EMPTY = {"color": 0, "width": 1, "height": 1}


def _colour_kind(client: ObsClient) -> str:
    kinds = client.request("GetInputKindList", {"unversioned": False}).get("inputKinds", [])
    for kind in ("color_source_v3", "color_source_v2", "color_source"):
        if kind in kinds:
            return kind
    return next((k for k in kinds if k.startswith("color_source")), "color_source_v3")


def _scene_names(client: ObsClient) -> list[str]:
    return [s.get("sceneName") for s in client.request("GetSceneList").get("scenes", [])]


def _item_id(client: ObsClient, source: str) -> int | None:
    try:
        data = client.request("GetSceneItemId", {"sceneName": MARKER_SCENE, "sourceName": source})
    except ObsRequestFailed:
        return None
    return int(data["sceneItemId"])


def set_up(client: ObsClient) -> list[str]:
    """Create the marker scene and its two sources, if missing. Returns what was added.

    Safe to run again: anything already there is left as it is.
    """
    added: list[str] = []
    if MARKER_SCENE not in _scene_names(client):
        client.request("CreateScene", {"sceneName": MARKER_SCENE})
        added.append(f'scene "{MARKER_SCENE}"')
    existing = {i.get("inputName") for i in client.request("GetInputList").get("inputs", [])}
    kind = None
    for source in MARKER_SOURCES.values():
        if _item_id(client, source) is not None:
            continue
        if source in existing:
            # The source exists (say it was dragged out of the scene): put it back.
            client.request("CreateSceneItem", {"sceneName": MARKER_SCENE, "sourceName": source,
                                               "sceneItemEnabled": False})
        else:
            kind = kind or _colour_kind(client)
            client.request("CreateInput", {"sceneName": MARKER_SCENE, "inputName": source,
                                           "inputKind": kind, "inputSettings": dict(_EMPTY),
                                           "sceneItemEnabled": False})
        added.append(f'source "{source}"')
    for item in find(client).values():
        client.request("SetSceneItemEnabled", {"sceneName": MARKER_SCENE, "sceneItemId": item,
                                               "sceneItemEnabled": False})
    return added


def find(client: ObsClient) -> dict[str, int]:
    """{"moment": scene item id, ...} for the marker sources that exist. Empty if not set up."""
    if MARKER_SCENE not in _scene_names(client):
        return {}
    found = {}
    for name, source in MARKER_SOURCES.items():
        item = _item_id(client, source)
        if item is not None:
            found[name] = item
    return found


def pressed(event: dict[str, Any], items: dict[str, int]) -> str | None:
    """Which marker a SceneItemEnableStateChanged event is, if it's a press."""
    if event.get("sceneName") != MARKER_SCENE or not event.get("sceneItemEnabled"):
        return None  # another scene, or us switching it back off
    item = event.get("sceneItemId")
    return next((name for name, found in items.items() if found == item), None)


def rearm(client: ObsClient, item: int) -> None:
    """Switch the source back off, so the next press is a change OBS reports."""
    client.request("SetSceneItemEnabled", {"sceneName": MARKER_SCENE, "sceneItemId": item,
                                           "sceneItemEnabled": False})
