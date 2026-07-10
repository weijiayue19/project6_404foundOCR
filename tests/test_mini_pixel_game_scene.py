from src.gui.main_window import MainWindow
from src.gui.pixel_theme import MiniPixelGameScene


def test_mini_game_score_uses_unbounded_distance_and_three_digit_counts() -> None:
    scene = MiniPixelGameScene.__new__(MiniPixelGameScene)
    scene._distance_meters = 1007.9
    scene._trees_skipped = 2
    scene._tree_crashes = 1003
    scene._birds_hit = -4

    assert scene._compact_score_text() == "1007/002/999/000"


def test_mini_game_bird_obstacle_uses_compact_altitudes() -> None:
    class _Rng:
        def random(self):
            return 0.0

        def uniform(self, start, _end):
            return start

        def choice(self, values):
            return values[-1]

    scene = MiniPixelGameScene.__new__(MiniPixelGameScene)
    scene._rng = _Rng()
    scene._next_obstacle_id = 12

    obstacle = scene._make_obstacle(320.0)

    assert obstacle == (320.0, 1, 12, "bird", MiniPixelGameScene.BIRD_ALTITUDES[-1])


def test_mini_game_defaults_to_manual_idle_motion() -> None:
    assert MiniPixelGameScene.RUN_SPEEDS["idle"] == 0.0


def test_main_window_reuses_mini_game_window(monkeypatch) -> None:
    created = []

    class _WindowStub:
        def __init__(self, root):
            self.root = root
            self.show_count = 0
            created.append(self)

        def show(self):
            self.show_count += 1

    monkeypatch.setattr("src.gui.main_window.MiniPixelGameWindow", _WindowStub)
    window = MainWindow.__new__(MainWindow)
    window.root = object()
    window._mini_pixel_game_window = None

    window.open_mini_pixel_game_window()
    window.open_mini_pixel_game_window()

    assert len(created) == 1
    assert created[0].show_count == 2


def test_mini_game_window_run_and_jump_delegate_to_scene() -> None:
    class _SceneStub:
        def __init__(self):
            self.boosts = 0
            self.jumps = 0

        def boost(self):
            self.boosts += 1

        def manual_jump(self):
            self.jumps += 1

    from src.gui.mini_game_window import MiniPixelGameWindow

    window = MiniPixelGameWindow.__new__(MiniPixelGameWindow)
    window.scene = _SceneStub()

    assert window._run() == "break"
    assert window._jump() == "break"
    assert window.scene.boosts == 1
    assert window.scene.jumps == 1
