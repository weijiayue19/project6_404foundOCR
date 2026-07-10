from src.gui.pixel_theme import ERROR, INK, PixelScene


def test_bird_collision_hits_bird_without_dino_crash():
    scene = PixelScene.__new__(PixelScene)
    scene._manual_drive = True
    scene.obstacles = [(130.0, 0, 7, "bird", 116)]
    scene._cleared_obstacle_ids = set()
    scene._crash_ticks = 0
    scene._bird_hit_ticks = {}
    scene._boost_ticks = 9
    scene._manual_action_ticks = 11
    scene._manual_jump_lift_px = 80.0
    scene._manual_jump_velocity = 4.0
    scene._manual_jump_count = 1
    scene._manual_jump_lift = lambda _height: 92

    PixelScene._update_user_action_feedback(scene, 420, 260)

    assert scene._crash_ticks == 0
    assert scene._bird_hit_ticks == {7: PixelScene.BIRD_HIT_RED_TICKS}
    assert scene._cleared_obstacle_ids == {7}
    assert scene._birds_hit == 1
    assert scene._boost_ticks == 9
    assert scene._manual_action_ticks == 11
    assert scene._manual_jump_lift_px == 80.0
    assert scene._manual_jump_velocity == 4.0
    assert scene._manual_jump_count == 1


def test_hit_bird_draws_red_and_rebounds_backward():
    scene = PixelScene.__new__(PixelScene)
    scene.obstacles = [(130.0, 0, 7, "bird", 116)]
    scene._bird_hit_ticks = {7: PixelScene.BIRD_HIT_RED_TICKS - 4}
    scene.frame = 0
    drawn = []

    def draw_bird(x, y, p, *, wing_up, color=INK):
        drawn.append(
            {
                "x": x,
                "y": y,
                "p": p,
                "wing_up": wing_up,
                "color": color,
            }
        )

    scene._draw_bird = draw_bird
    scene._draw_cactus = lambda *_args, **_kwargs: None

    PixelScene._draw_scene_obstacles(scene, 420, 155, 5)

    assert len(drawn) == 1
    assert drawn[0]["x"] > 130
    assert drawn[0]["y"] == 39
    assert drawn[0]["p"] == 3
    assert drawn[0]["wing_up"] is False
    assert drawn[0]["color"] == ERROR


def test_distance_stat_accumulates_forward_motion_only():
    scene = PixelScene.__new__(PixelScene)
    scene.world_speed = 10.0

    PixelScene._update_distance_stat(scene)
    scene.world_speed = -5.0
    PixelScene._update_distance_stat(scene)

    assert abs(scene._distance_meters - 1.8) < 0.0001


def test_tree_skip_stat_counts_each_cactus_once():
    scene = PixelScene.__new__(PixelScene)
    scene.obstacles = [
        (128.0, 0, 4, "cactus", 0),
        (128.0, 0, 5, "bird", 116),
    ]
    scene._cleared_obstacle_ids = set()

    PixelScene._mark_tree_clear(scene, 130, 5, 44)
    PixelScene._mark_tree_clear(scene, 130, 5, 44)

    assert scene._trees_skipped == 1
    assert scene._cleared_obstacle_ids == {4}


def test_collision_stats_count_once_per_obstacle():
    scene = PixelScene.__new__(PixelScene)
    scene.obstacles = [(130.0, 0, 4, "cactus", 0)]
    scene._bird_hit_ticks = {}
    scene._cleared_obstacle_ids = set()
    scene._boost_ticks = 6
    scene._manual_action_ticks = 8
    scene._manual_jump_lift_px = 20.0
    scene._manual_jump_velocity = 1.5
    scene._manual_jump_count = 1
    scene._random_initial_obstacle_gap = lambda: 64.0

    PixelScene._trigger_crash(scene, 4)
    PixelScene._record_tree_crash(scene, 4)
    PixelScene._trigger_bird_hit(scene, 7)
    PixelScene._trigger_bird_hit(scene, 7)

    assert scene._tree_crashes == 1
    assert scene._birds_hit == 1
    assert scene._bird_hit_ticks == {7: PixelScene.BIRD_HIT_RED_TICKS}
