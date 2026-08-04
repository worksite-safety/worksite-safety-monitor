"""The one home for every magic number `aiModule.py` scatters through its 547 lines.

The original tunes itself in nine unrelated places: `sport_list` at the top of the file
(lines 20-45), `conf=0.8` and `conf=0.6` inside the two model calls (291, 293), the
`> 0.6` keypoint-visibility gates (321, 358), the `> 160` upright gate (322),
`timedelta(minutes=3)` in the FALL branch (437), the broker address in a module-level
`KafkaProducer(...)` (16), the camera source in two near-identical `Args` classes
(203, 212) and `'output_image.jpg'` in the display branch (523). Retuning a site means
editing Python, and every value the editor misses stays wrong without saying so.

`load_config` gives those numbers one home and three layers -- built-in defaults, an
optional YAML file, then an injected environment mapping -- each overriding the last.
Two properties matter more than the layering:

* **Nothing is guessed.** An unrecognised key raises, in the file and in the environment
  alike. A loader that ignores what it does not recognise turns `WSM_KAFKA__BOOTSTRAP_SERVER`
  -- singular, a typo -- into a rig that runs for weeks publishing to `localhost` while
  the dashboard stays empty and nothing anywhere logs a word.
* **Nothing is touched.** Loading resolves no paths and opens no weights, so the unit
  suite runs on a machine with neither a 50 MB `best.pt` nor a camera.

`env` is a parameter, never `os.environ`, so every test below states its whole
environment inline and no test can leak one into the next through the process.

The gesture table is where this module also stops carrying three defects forward: dead
configuration indexed off the ears (`test_no_gesture_references_ear_keypoints`), a gesture
whose name and numbers came from different entries
(`test_default_gestures_are_arms_up_and_front_bend`), and an upright precondition measured
over keypoints no gate ever checked (`test_angle_indices_are_subset_of_visibility_indices`).
"""
from __future__ import annotations

import textwrap
from dataclasses import FrozenInstanceError, fields, is_dataclass, replace
from pathlib import Path
from typing import Any

import pytest
import yaml
from worksite_detector.config import Config, GestureSpec, load_config
from worksite_detector.events import EventType

DETECTOR_ROOT = Path(__file__).resolve().parents[1]

# Shipped documentation. `test_shipped_example_yaml_equals_defaults` is what stops it
# from drifting into fiction, so it is a source file of this test as much as of the app.
EXAMPLE_YAML = DETECTOR_ROOT / "config.example.yaml"

ENV_PREFIX = "WSM_"

# A valid gesture, with fields replaced so each test shows only what it varies. Values
# are ARMS_UP's, from sport_list['armsUp'] (aiModule.py lines 21-28) and the visibility
# gate that guards it (line 358: row[11], row[5], row[7] / row[12], row[6], row[8]).
GESTURE_KWARGS: dict[str, Any] = {
    "event_type": EventType.ARMS_UP,
    "left_points_idx": (11, 5, 7),
    "right_points_idx": (12, 6, 8),
    "left_visibility_idx": (5, 7, 11),
    "right_visibility_idx": (6, 8, 12),
    "maintaining": 30.0,
    "relaxing": 140.0,
    "requires_upright": False,
}

# Every default, with the line of `aiModule.py` it was lifted from. `ppe_grace_ms` is the
# one value with no line to cite: the original had no grace window at all, which is why its
# PPE windows fragmented (tests/data/baseline/PROVENANCE.md, tests/test_ppe_rules.py).
DEFAULT_VALUES: list[tuple[str, Any, str]] = [
    ("thresholds.pose_confidence", 0.8, "line 291, model(frame, conf=0.8)"),
    ("thresholds.ppe_confidence", 0.6, "line 293, model2.predict(..., conf=0.6)"),
    ("thresholds.keypoint_visibility", 0.6, "lines 321 and 358, row[i] > 0.6"),
    ("thresholds.fall_cooldown_ms", 180_000, "line 437, timedelta(minutes=3)"),
    ("thresholds.ppe_grace_ms", 1500, "the PPE window merge tolerance"),
    ("kafka.bootstrap_servers", "localhost:9092", "line 16, KafkaProducer(...)"),
    ("kafka.topic", "rawEvents", "lines 351/391/450, producer.send('rawEvents', ...)"),
    ("camera.source", "0", "lines 203 and 212, self.input = '0'"),
    ("camera.name", "0", "line 344, cameraName: args.input"),
    ("upright.angle_degrees", 160.0, "line 322, calculate_angle(...) > 160"),
    ("upright.left_idx", (11, 13, 15), "line 319, right = [11, 13, 15], read at line 322"),
    ("upright.right_idx", (12, 14, 16), "line 318, left = [12, 14, 16], read at line 322"),
    ("output.annotated_frame_path", Path("output_image.jpg"), "line 523, 'output_image.jpg'"),
]

# The hip -> knee -> ankle chain the upright precondition is measured over, in COCO order
# (aiModule.py line 322, via the `left`/`right` locals at 318-319 -- which are swapped
# relative to COCO, harmlessly there because the callee averaged both sides).
#
# These live in the same config section as the angle they are measured for. In the original
# the threshold (line 322) and the chain it reads (318-319) were three lines apart and still
# drifted from the gate above them (321); at a section apart they would drift again.
UPRIGHT_LEFT_IDX = (11, 13, 15)
UPRIGHT_RIGHT_IDX = (12, 14, 16)

# The two surviving gestures, field by field. ARMS_UP is sport_list['armsUp'] (lines 21-28)
# gated by line 358; FRONT_BEND carries sport_list['bending']'s numbers (lines 29-36) because
# that is the entry the original actually read while emitting the name FRONT_BEND
# (`main()` binds args = Args2(), whose sport is 'bending' -- lines 211, 227, 324-325).
# `requires_upright` is the `> 160` gate at line 322, which stands between the visibility
# check and the bend angle -- and nowhere else.
#
# Visibility is compared as a set, not a tuple: the order of a gate is meaningless, whereas
# the order of a points chain is the angle's end-vertex-end and is pinned exactly.
# FRONT_BEND's gate is the union of its own chain and the upright chain it depends on --
# see test_angle_indices_are_subset_of_visibility_indices for why that union is mandatory.
EXPECTED_GESTURES: dict[EventType, dict[str, Any]] = {
    EventType.ARMS_UP: {
        "left_points_idx": (11, 5, 7),
        "right_points_idx": (12, 6, 8),
        "left_visibility_idx": {5, 7, 11},
        "right_visibility_idx": {6, 8, 12},
        "maintaining": 30.0,
        "relaxing": 140.0,
        "requires_upright": False,
    },
    EventType.FRONT_BEND: {
        "left_points_idx": (5, 11, 13),
        "right_points_idx": (6, 12, 14),
        "left_visibility_idx": {5, 11, 13, 15},
        "right_visibility_idx": {6, 12, 14, 16},
        "maintaining": 130.0,
        "relaxing": 160.0,
        "requires_upright": True,
    },
}


# --------------------------------------------------------------------------- helpers


def _defaults() -> Config:
    """The configuration of a machine with no config file and no environment."""
    return load_config(None, {})


def _yaml_file(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "wsm.yaml"
    path.write_text(textwrap.dedent(text).lstrip("\n"), encoding="utf-8")
    return path


def _flat(obj: Any, prefix: str = "") -> dict[str, Any]:
    """Every scalar in a nested config, keyed by its dotted path.

    Lets a test say "this one value changed and nothing else did" as a single dict
    comparison, which is the only way to catch a loader that overrides the field it was
    asked to and quietly resets a neighbour to its default.
    """
    flattened: dict[str, Any] = {}
    for field in fields(obj):
        value = getattr(obj, field.name)
        key = f"{prefix}{field.name}"
        if is_dataclass(value) and not isinstance(value, type):
            flattened.update(_flat(value, f"{key}."))
        else:
            flattened[key] = value
    return flattened


def _sections(config: Config) -> dict[str, Any]:
    """The nested dataclasses hanging off `Config`, by attribute name."""
    return {
        field.name: getattr(config, field.name)
        for field in fields(config)
        if is_dataclass(getattr(config, field.name))
        and not isinstance(getattr(config, field.name), type)
    }


def _by_type(config: Config) -> dict[EventType, GestureSpec]:
    return {spec.event_type: spec for spec in config.gestures}


def _spec(**overrides: Any) -> GestureSpec:
    return GestureSpec(**{**GESTURE_KWARGS, **overrides})


# -------------------------------------------------------------------------- defaults


@pytest.mark.parametrize(
    ("key", "expected", "source"), DEFAULT_VALUES, ids=[row[0] for row in DEFAULT_VALUES]
)
def test_defaults_without_file(key: str, expected: Any, source: str) -> None:
    # A default that drifts from the original silently changes what the rewrite detects:
    # a pose confidence of 0.6 admits poses the baseline rejected, and every differential
    # comparison against tests/data/baseline then measures the wrong thing.
    flattened = _flat(_defaults())

    assert key in flattened, (
        f"no config field {key!r}; the value at {source} has nowhere to live, so it is "
        f"still hardcoded somewhere. Known fields: {sorted(flattened)}"
    )
    assert flattened[key] == expected, f"{key} must default to {expected!r} ({source})"

    if key.endswith("_ms"):
        # Milliseconds reach the engine as `Long startTime` / `Integer timePeriod`; a float
        # here is truncated by Jackson without complaint (see tests/test_events.py).
        assert type(flattened[key]) is int, (
            f"{key} is {type(flattened[key]).__name__}; millisecond fields must be int"
        )


def test_shipped_example_yaml_equals_defaults() -> None:
    # Documentation that disagrees with the code is worse than none: an operator copies
    # config.example.yaml, changes one line, and silently retunes everything else it lists.
    # Equality against the built-in defaults is what makes that drift impossible.
    assert EXAMPLE_YAML.is_file(), (
        f"{EXAMPLE_YAML} does not exist. The loader must ship a documented example, and "
        f"this test is the only thing keeping it honest."
    )

    document = yaml.safe_load(EXAMPLE_YAML.read_text(encoding="utf-8"))
    assert isinstance(document, dict), f"{EXAMPLE_YAML.name} must parse to a mapping"

    defaults = _defaults()
    for name, section in _sections(defaults).items():
        assert name in document, f"{EXAMPLE_YAML.name} documents no {name!r} section"
        expected_keys = {field.name for field in fields(section)}
        assert set(document[name]) == expected_keys, (
            f"{EXAMPLE_YAML.name} section {name!r} lists {sorted(document[name])}, but the "
            f"section has {sorted(expected_keys)}. An undocumented knob is an unusable one."
        )

    assert load_config(EXAMPLE_YAML, {}) == defaults, (
        f"{EXAMPLE_YAML.name} parses but disagrees with the built-in defaults"
    )


# -------------------------------------------------------------------------- layering


def test_yaml_partially_overrides_defaults(tmp_path: Path) -> None:
    # Deep merge, not replace: a site that pins one threshold must not lose the other five.
    # A `defaults | yaml` at the top level wipes every sibling key in the section it touches.
    path = _yaml_file(
        tmp_path,
        """
        thresholds:
          pose_confidence: 0.55
        """,
    )

    actual = _flat(load_config(path, {}))
    expected = _flat(_defaults())

    assert actual.pop("thresholds.pose_confidence") == 0.55
    assert expected.pop("thresholds.pose_confidence") == 0.8
    assert actual == expected, (
        "a YAML file naming one threshold changed something else as well: "
        f"{ {k: (expected[k], v) for k, v in actual.items() if expected[k] != v} }"
    )


def test_env_beats_yaml_beats_default(tmp_path: Path) -> None:
    # The precedence the deployment relies on: the image ships a YAML, the orchestrator
    # overrides one value per site. Reversed, a redeploy silently reverts the site's value.
    path = _yaml_file(
        tmp_path,
        """
        thresholds:
          pose_confidence: 0.55
        kafka:
          topic: fromYaml
        """,
    )

    config = load_config(path, {f"{ENV_PREFIX}THRESHOLDS__POSE_CONFIDENCE": "0.31"})

    assert config.thresholds.pose_confidence == 0.31, "env must win over the file"
    assert config.kafka.topic == "fromYaml", "the file must win over the built-in default"
    assert config.thresholds.ppe_confidence == 0.6, "an untouched field must keep its default"


@pytest.mark.parametrize(
    "env_key",
    [
        "WSM_THRESHOLDS__POSE_CONFIDENCE",
        "wsm_thresholds__pose_confidence",
        "Wsm_Thresholds__Pose_Confidence",
    ],
    ids=["upper", "lower", "mixed"],
)
def test_double_underscore_nests_and_key_is_case_insensitive(env_key: str) -> None:
    # `__` is the only nesting marker, and case is not part of the name. Getting either
    # wrong produces no error -- just a config that ignored the override it was handed,
    # which is indistinguishable from the override having worked until the site misbehaves.
    actual = _flat(load_config(None, {env_key: "0.3"}))
    expected = _flat(_defaults())

    assert actual.pop("thresholds.pose_confidence") == 0.3, (
        f"{env_key} did not reach thresholds.pose_confidence"
    )
    expected.pop("thresholds.pose_confidence")
    assert actual == expected, f"{env_key} also changed something it does not name"


@pytest.mark.parametrize(
    ("env_key", "raw", "key", "expected", "expected_type"),
    [
        ("WSM_THRESHOLDS__POSE_CONFIDENCE", "0.3", "thresholds.pose_confidence", 0.3, float),
        ("WSM_THRESHOLDS__FALL_COOLDOWN_MS", "1500", "thresholds.fall_cooldown_ms", 1500, int),
        (
            "WSM_OUTPUT__WRITE_ANNOTATED_FRAME",
            "true",
            "output.write_annotated_frame",
            True,
            bool,
        ),
        (
            "WSM_OUTPUT__WRITE_ANNOTATED_FRAME",
            "false",
            "output.write_annotated_frame",
            False,
            bool,
        ),
    ],
    ids=["float", "int", "bool_true", "bool_false"],
)
def test_env_value_type_coercion(
    env_key: str, raw: str, key: str, expected: Any, expected_type: type
) -> None:
    # The environment only carries strings. Uncoerced, `"0.3" > 0.6` raises TypeError in the
    # frame loop and `bool("false")` is True -- the second is the dangerous one, because it
    # turns an operator's attempt to switch something off into switching it on.
    value = _flat(load_config(None, {env_key: raw}))[key]

    assert value == expected
    assert type(value) is expected_type, (
        f"{env_key}={raw!r} produced {type(value).__name__}; {key} must be {expected_type.__name__}"
    )


@pytest.mark.parametrize(
    ("env_key", "raw"),
    [
        ("WSM_THRESHOLDS__POSE_CONFIDENCE", "banana"),
        ("WSM_THRESHOLDS__FALL_COOLDOWN_MS", "three minutes"),
    ],
    ids=["float_field", "int_field"],
)
def test_env_value_type_coercion_error_names_the_key(env_key: str, raw: str) -> None:
    # An unparseable value must fail at startup, naming the variable, rather than at the
    # first comparison inside the frame loop where the traceback names only `>`.
    with pytest.raises(ValueError) as excinfo:
        load_config(None, {env_key: raw})

    leaf = env_key.removeprefix(ENV_PREFIX).split("__")[-1].lower()
    assert leaf in str(excinfo.value).lower(), (
        f"raised on {env_key}={raw!r} but the message was {str(excinfo.value)!r}; it must "
        f"name the offending key ({leaf}) or the operator cannot tell which of a dozen "
        f"WSM_ variables they mistyped"
    )


@pytest.mark.parametrize(
    ("env_key", "why"),
    [
        ("WSM_KAFKA__BOOTSTRAP_SERVER", "singular: the field is bootstrap_servers"),
        ("WSM_KAFKA__TOPICS", "plural: the field is topic"),
        ("WSM_THRESHOLDS__POSE_CONFIDNCE", "transposed letters"),
        ("WSM_CAMERAS__SOURCE", "unknown section"),
        ("WSM_TOPIC", "no section at all"),
        ("WSM_THRESHOLDS__POSE_CONFIDENCE__EXTRA", "nested past a leaf"),
    ],
    ids=[
        "singular_server",
        "plural_topics",
        "typo_leaf",
        "unknown_section",
        "no_section",
        "too_deep",
    ],
)
def test_unknown_prefixed_env_key_raises(env_key: str, why: str) -> None:
    # The highest-value test in this file. A WSM_-prefixed variable is an operator stating
    # an intent; ignoring one they misspelled is how a rig runs for weeks pointed at the
    # wrong broker, publishing into the void, with nothing failing and nothing logged.
    with pytest.raises(ValueError) as excinfo:
        load_config(None, {env_key: "whatever"})

    message = str(excinfo.value).lower()
    dotted = env_key.removeprefix(ENV_PREFIX).lower().replace("__", ".")
    assert env_key.lower() in message or dotted in message, (
        f"{env_key} ({why}) raised, but the message {str(excinfo.value)!r} names neither "
        f"{env_key} nor {dotted}, so the operator still has to guess which variable is wrong"
    )


@pytest.mark.parametrize(
    ("document", "offender"),
    [
        ("kafkaa:\n  topic: rawEvents\n", "kafkaa"),
        ("kafka:\n  bootstrap_server: localhost:9092\n", "bootstrap_server"),
        ("thresholds:\n  pose_confidnce: 0.8\n", "pose_confidnce"),
        ("output:\n  image_path: out.jpg\n", "image_path"),
    ],
    ids=["unknown_section", "singular_server", "typo_leaf", "engine_spelling"],
)
def test_unknown_yaml_key_raises(tmp_path: Path, document: str, offender: str) -> None:
    # Same failure mode as the env typo, one layer down: a key YAML accepts but the loader
    # does not recognise is a setting the operator believes is in force and is not.
    with pytest.raises(ValueError) as excinfo:
        load_config(_yaml_file(tmp_path, document), {})

    assert offender.lower() in str(excinfo.value).lower(), (
        f"raised on {document!r} but the message {str(excinfo.value)!r} does not name "
        f"{offender!r}"
    )


def test_unprefixed_env_ignored() -> None:
    # The process environment is full of other people's variables. Reading an unprefixed
    # PATH or KAFKA__X either crashes the loader or, worse, applies it -- and CI's PATH
    # would then reconfigure the detector.
    env = {
        "PATH": "/usr/bin:/bin",
        "KAFKA__X": "y",
        "THRESHOLDS__POSE_CONFIDENCE": "0.1",
        "HOME": "/root",
    }

    assert load_config(None, env) == _defaults(), (
        "an unprefixed variable changed the configuration"
    )


# -------------------------------------------------------------------------- gestures


def test_default_gestures_are_arms_up_and_front_bend() -> None:
    # Encodes the decision to delete `frontbending` (aiModule.py lines 37-44): it is dead --
    # `Args2.sport` is 'bending', so lines 324-325 never read it -- and reviving it would be
    # worse than deleting it, because the visibility gate at line 321 checks 5/11/13 while
    # 'frontbending' angles over 3/11/13, leaving an ungated keypoint in the angle.
    # FRONT_BEND therefore keeps 'bending''s numbers, which is what the baseline recorded.
    gestures = _defaults().gestures

    assert isinstance(gestures, tuple), (
        f"gestures is a {type(gestures).__name__}; a frozen Config with a mutable gesture "
        f"list can still be retuned at runtime by any caller that holds it"
    )
    assert {spec.event_type for spec in gestures} == set(EXPECTED_GESTURES)
    assert len(gestures) == 2, f"expected exactly two gestures, got {len(gestures)}"

    by_type = _by_type(_defaults())
    for event_type, expected in EXPECTED_GESTURES.items():
        spec = by_type[event_type]
        actual = {
            name: set(getattr(spec, name)) if isinstance(want, set) else getattr(spec, name)
            for name, want in expected.items()
        }
        assert actual == expected, f"{event_type.value} is misconfigured"


def test_no_gesture_references_ear_keypoints() -> None:
    # Keypoints 3 and 4 are the ears. `frontbending` measured a bend from them, which is
    # anatomically meaningless; this is the structural check that it never comes back,
    # whether by restoring the entry or by mistyping 13 as 3 in a YAML file.
    for spec in _defaults().gestures:
        indices = (
            set(spec.left_points_idx)
            | set(spec.right_points_idx)
            | set(spec.left_visibility_idx)
            | set(spec.right_visibility_idx)
        )
        assert not indices & {3, 4}, (
            f"{spec.event_type.value} references ear keypoints {sorted(indices & {3, 4})}; "
            f"no bend or reach angle is measured from the ears"
        )


def test_upright_chain_indices_include_the_ankles() -> None:
    # The upright precondition -- the thing that stops a seated worker being counted as
    # bending -- is measured over hip, knee and ankle (line 322), while the gate one line
    # above checks 5/11/13 and 12/6/14. Ankle confidence at 15/16 is checked nowhere in the
    # file, so the check that depends entirely on the ankles routinely ran on YOLO's (0, 0)
    # sentinel. Naming the chain in the config is what gives the gate something to cover.
    #
    # `upright.angle_degrees` is 160 and FRONT_BEND's `relaxing` is also 160; they are
    # unrelated numbers that the original happened to spell the same. Keeping them in
    # different sections is what stops a retune of one from being read as a retune of both.
    config = _defaults()

    assert config.upright.left_idx == UPRIGHT_LEFT_IDX
    assert config.upright.right_idx == UPRIGHT_RIGHT_IDX
    assert config.upright.angle_degrees == 160.0

    for side, chain in (("left", config.upright.left_idx), ("right", config.upright.right_idx)):
        hip, knee, ankle = chain
        assert (knee, ankle) == (hip + 2, hip + 4), (
            f"the {side} upright chain {chain} is not a COCO hip -> knee -> ankle triple; "
            f"COCO numbers them 11/13/15 (left) and 12/14/16 (right), two apart, in that order"
        )
        assert ankle in {15, 16}, f"the {side} upright chain must end at an ankle, not {ankle}"

    assert not set(config.upright.left_idx) & set(config.upright.right_idx), (
        "the two upright chains share a keypoint, so they are not mirrored sides"
    )


@pytest.mark.parametrize("side", ["left", "right"], ids=["left", "right"])
def test_angle_indices_are_subset_of_visibility_indices(side: str) -> None:
    # An angle computed from a keypoint whose visibility was never checked is an angle over
    # YOLO's (0, 0) sentinel -- exactly the halved-measurement bug tests/test_geometry.py
    # exists to kill, arriving through configuration instead of through code.
    config = _defaults()
    upright = set(getattr(config.upright, f"{side}_idx"))

    for spec in config.gestures:
        points = set(getattr(spec, f"{side}_points_idx"))
        visible = set(getattr(spec, f"{side}_visibility_idx"))
        assert points <= visible, (
            f"{spec.event_type.value} {side} angle uses {sorted(points - visible)}, which "
            f"the visibility gate {sorted(visible)} never checks"
        )
        if spec.requires_upright:
            # The original's exact defect: gate one chain, measure another.
            assert upright <= visible, (
                f"{spec.event_type.value} requires an upright check measured over "
                f"{sorted(upright)}, but its {side} gate {sorted(visible)} never checks "
                f"{sorted(upright - visible)}"
            )

    with pytest.raises(ValueError):
        # The same must be unconfigurable, not merely absent from the defaults.
        _spec(**{f"{side}_visibility_idx": (6, 8)})

    ungated_upright = _spec(
        event_type=EventType.FRONT_BEND,
        left_points_idx=(5, 11, 13),
        right_points_idx=(6, 12, 14),
        left_visibility_idx=(5, 11, 13),
        right_visibility_idx=(6, 12, 14),
        maintaining=130.0,
        relaxing=160.0,
        requires_upright=True,
    )
    with pytest.raises(ValueError):
        # Valid on its own terms -- its own chain is gated -- but it asks for an upright
        # check whose ankles nobody checks. Only Config knows the upright chain, so this
        # rule belongs in Config's validation, not in GestureSpec's.
        replace(config, gestures=(ungated_upright,))


@pytest.mark.parametrize(
    ("maintaining", "relaxing"),
    [(170.0, 100.0), (140.0, 140.0), (30.0, 30.0)],
    ids=["inverted", "equal_high", "equal_low"],
)
def test_maintaining_must_be_strictly_below_relaxing(maintaining: float, relaxing: float) -> None:
    # An empty hysteresis band latches the state machine: `angle < maintaining` arms it and
    # `angle > relaxing` can never release it, so no gesture ever completes. Not theoretical
    # -- replaying the original over real footage emitted zero events across 986 frames.
    with pytest.raises(ValueError):
        _spec(maintaining=maintaining, relaxing=relaxing)

    # And the sane band still constructs, so the check is a band test rather than a ban.
    assert _spec(maintaining=30.0, relaxing=140.0).relaxing == 140.0


def test_requires_upright_is_per_gesture() -> None:
    # The `> 160` upright gate (line 322) guards the bend only; ARMS_UP is measured
    # regardless of posture (line 358 has no such gate). Hoisting the flag onto the config
    # as one global switch would either gate ARMS_UP behind a posture it never required or
    # stop gating FRONT_BEND, doubling its event rate on anyone bending sideways.
    by_type = _by_type(_defaults())

    assert by_type[EventType.FRONT_BEND].requires_upright is True
    assert by_type[EventType.ARMS_UP].requires_upright is False

    assert "requires_upright" in {field.name for field in fields(GestureSpec)}
    config = _defaults()
    assert not hasattr(config, "requires_upright"), "requires_upright must not be global"
    for name, section in _sections(config).items():
        assert not hasattr(section, "requires_upright"), (
            f"requires_upright is on config.{name}; it is a property of one gesture"
        )


# ------------------------------------------------------------------------------ misc


def test_camera_name_defaults_to_source(tmp_path: Path) -> None:
    # The original sent `cameraName: args.input` (line 344), so every event on a default rig
    # is labelled "0". Defaulting the name to anything else renames every camera in MongoDB
    # at once and orphans the history the dashboard groups by name.
    assert _defaults().camera.name == "0"
    assert _defaults().camera.name == _defaults().camera.source

    derived = load_config(_yaml_file(tmp_path, 'camera:\n  source: "rtsp://gate/1"\n'), {})
    assert derived.camera.name == "rtsp://gate/1"

    named = load_config(
        _yaml_file(tmp_path, 'camera:\n  source: "rtsp://gate/1"\n  name: gate-north\n'), {}
    )
    assert named.camera.name == "gate-north"
    assert named.camera.source == "rtsp://gate/1"


def test_load_does_not_touch_the_filesystem_for_weights(tmp_path: Path) -> None:
    # Loading must not stat, resolve or open a weight file. Validating them here would put
    # a 75 MB download between CI and every test in this suite, and would fail on the
    # workstation that configures a path the detector host can see and the runner cannot.
    path = _yaml_file(
        tmp_path,
        """
        models:
          pose_weights: weights/nowhere/yolov8s-pose.pt
          ppe_weights: weights/nowhere/best.pt
        """,
    )

    config = load_config(path, {})

    assert config.models.pose_weights == Path("weights/nowhere/yolov8s-pose.pt")
    assert config.models.ppe_weights == Path("weights/nowhere/best.pt")
    assert not config.models.ppe_weights.exists(), "the fixture path must stay nonexistent"


def test_config_is_frozen() -> None:
    # The config is read on every frame by several rule objects at once. One mutable field
    # means a rule can retune the pipeline mid-run, and the resulting event stream is not
    # reproducible from the config that was loaded -- which the baseline diff depends on.
    config = _defaults()

    with pytest.raises(FrozenInstanceError):
        config.thresholds = None  # type: ignore[misc]

    for name, section in _sections(config).items():
        first = fields(section)[0].name
        with pytest.raises(FrozenInstanceError, match=first):
            setattr(section, first, None)
        assert name  # the section name is only here to make the failure readable

    with pytest.raises(FrozenInstanceError):
        config.gestures[0].maintaining = 1.0  # type: ignore[misc]
