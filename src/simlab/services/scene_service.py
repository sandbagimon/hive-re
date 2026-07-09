from __future__ import annotations

import copy
import re
from typing import Any

from simlab.models.actor import Actor, ActorType
from simlab.models.scene import Scene
from simlab.models.transform import Transform

_ACTOR_ID_RE = re.compile(r"^actor_(\d{3})$")


class SceneService:
    """Manage the in-memory scene state used by the desktop UI."""

    def __init__(self, scene: Scene | None = None) -> None:
        self.scene = scene or Scene()

    def new_scene(self, name: str = "Untitled Scene") -> Scene:
        self.scene = Scene(name=name)
        return self.scene

    def add_actor(
        self,
        name: str,
        actor_type: ActorType = "object",
        asset_id: str = "",
        transform: Transform | None = None,
        properties: dict[str, Any] | None = None,
    ) -> Actor:
        actor = Actor(
            id=self._next_actor_id(),
            name=name,
            type=actor_type,
            asset_id=asset_id,
            transform=transform or Transform(),
            properties=copy.deepcopy(properties or {}),
        )
        self.scene.actors.append(actor)
        return actor

    def remove_actor(self, actor_id: str) -> bool:
        before = len(self.scene.actors)
        self.scene.actors = [actor for actor in self.scene.actors if actor.id != actor_id]
        return len(self.scene.actors) != before

    def rename_actor(self, actor_id: str, name: str) -> Actor:
        actor = self._require_actor(actor_id)
        actor.name = name
        return actor

    def update_transform(self, actor_id: str, transform: Transform) -> Actor:
        actor = self._require_actor(actor_id)
        actor.transform = transform
        return actor

    def update_actor_properties(self, actor_id: str, properties: dict[str, Any]) -> Actor:
        actor = self._require_actor(actor_id)
        actor.properties.update(properties)
        return actor

    def get_actor(self, actor_id: str) -> Actor | None:
        return next((actor for actor in self.scene.actors if actor.id == actor_id), None)

    def list_actors(self) -> list[Actor]:
        return list(self.scene.actors)

    def _require_actor(self, actor_id: str) -> Actor:
        actor = self.get_actor(actor_id)
        if actor is None:
            msg = f"Actor not found: {actor_id}"
            raise KeyError(msg)
        return actor

    def _next_actor_id(self) -> str:
        highest = 0
        for actor in self.scene.actors:
            match = _ACTOR_ID_RE.match(actor.id)
            if match:
                highest = max(highest, int(match.group(1)))
        return f"actor_{highest + 1:03d}"
