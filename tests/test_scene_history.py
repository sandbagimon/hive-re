from simlab.models.scene import Scene
from simlab.models.transform import Transform
from simlab.services.scene_history import SceneHistory
from simlab.services.scene_service import SceneService


def test_scene_history_tracks_dirty_saved_and_undo_redo() -> None:
    service = SceneService(Scene(name="History Test"))
    history = SceneHistory(service.scene)

    history.begin_change(service.scene)
    actor = service.add_actor("Box", asset_id="primitive_box")

    assert history.is_dirty(service.scene) is True
    assert history.can_undo() is True
    assert history.can_redo() is False

    restored = history.undo(service.scene)

    assert restored is not None
    assert restored.actors == []
    assert history.is_dirty(restored) is False
    assert history.can_redo() is True

    redone = history.redo(restored)

    assert redone is not None
    assert redone.actors[0].id == actor.id
    assert history.is_dirty(redone) is True

    history.mark_saved(redone)

    assert history.is_dirty(redone) is False


def test_scene_history_restores_transform_updates() -> None:
    service = SceneService(Scene())
    actor = service.add_actor("Box", asset_id="primitive_box")
    history = SceneHistory(service.scene)

    history.begin_change(service.scene)
    service.update_transform(actor.id, Transform(position=[1, 2, 3]))
    restored = history.undo(service.scene)

    assert restored is not None
    assert restored.actors[0].transform.position == [0.0, 0.0, 0.0]

    redone = history.redo(restored)

    assert redone is not None
    assert redone.actors[0].transform.position == [1.0, 2.0, 3.0]
