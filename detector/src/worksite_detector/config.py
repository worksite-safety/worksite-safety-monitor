"""Every number the detector is tuned by, in one place, with three layers to set it from.

``aiModule.py`` tunes itself in nine unrelated places: the gesture table at the
top of the file, ``conf=0.8`` and ``conf=0.6`` inside the two model calls, the
``> 0.6`` keypoint-visibility gates, the ``> 160`` upright gate,
``timedelta(minutes=3)`` in the FALL branch, the broker address in a module-level
``KafkaProducer(...)``, the camera source in two near-identical ``Args`` classes
and ``'output_image.jpg'`` in the display branch. Retuning a site means editing
Python, and every value the editor misses stays wrong without saying so.

**The layers.** ``load_config`` resolves built-in defaults, then an optional YAML
file, then an injected environment mapping -- each overriding the last, and each
only where it speaks. A file naming one threshold leaves its four siblings at
their defaults; an environment naming one value leaves the file's other values
alone. That order is what a deployment relies on: the image ships a YAML and the
orchestrator overrides one value per site. Reversed, every redeploy would
silently revert the site's own setting.

**The environment scheme** is ``WSM_<SECTION>__<FIELD>`` -- the ``WSM_`` prefix,
then exactly one double underscore, as in ``WSM_KAFKA__BOOTSTRAP_SERVERS``. Case
is not part of the name. Anything without the prefix is ignored, because the
process environment is full of other people's variables and CI's ``PATH`` must
not reconfigure a detector. ``env`` is a parameter and never ``os.environ``, so a
caller -- a test especially -- states its whole environment inline and cannot
leak one into the next through the process.

**Unknown keys are fatal**, in the file and in the environment alike, and the
error names the offending key. This is the most valuable rule in the module. A
``WSM_``-prefixed variable is an operator stating an intent; a loader that
ignores the one they misspelled turns ``WSM_KAFKA__BOOTSTRAP_SERVER`` -- singular
-- into a rig that runs for weeks publishing to ``localhost``, with the dashboard
empty, nothing failing and nothing logged. Values are coerced to the declared
type for the same reason: the environment carries only strings, ``"0.3" > 0.6``
raises inside the frame loop rather than at startup, and ``bool("false")`` is
True, which turns an operator switching something off into switching it on.

**Nothing is touched.** Loading resolves no paths and opens no weights, so the
unit suite runs on a machine with neither a 50 MB ``best.pt`` nor a camera, and a
workstation may configure a path only the detector host can see.

Four decisions are encoded in the schema rather than left to a comment:

* **``upright`` is one section** -- the chain *and* the angle measured over it.
  In the original the threshold and the keypoints it reads sat three lines apart
  and had already drifted from the visibility gate above them: the code gated the
  shoulder-hip-knee chain and then measured hip-knee-ankle, so ankle visibility
  was never checked at all. The precondition that stops a seated worker counting
  as bending was computed from a limb nobody confirmed was there. ``Config``
  refuses a gesture whose gate does not cover the chain, which is a rule only
  ``Config`` can enforce -- a ``GestureSpec`` cannot see the upright section.
* **``maintaining`` must be strictly below ``relaxing``.** An empty hysteresis
  band latches the state machine: ``angle < maintaining`` arms it and
  ``angle > relaxing`` can never release it, so no gesture ever completes.
  Replaying the original over 986 frames of real footage emitted zero gesture
  events for exactly this reason.
* **``frontbending`` is deleted, not adopted.** The original's gesture table has
  three entries and the code emits ``FRONT_BEND`` while reading ``bending``,
  leaving ``frontbending`` dead. Reviving it would be worse than deleting it: it
  measures a bend from ear keypoints 3 and 4, whose visibility no gate checks, so
  it trades a dead entry for a live defect.
* **``ppe_grace_ms`` has no counterpart in the original at all.** It exists
  because PPE detections flicker -- on the baseline footage they fragment into 27
  runs, the longest 367 ms, and against the engine's 3-second threshold not one
  survives. Simplifying it away silently restores a detector that records
  nothing. See ``ppe_rules`` for how the default was measured.

Gestures themselves are code, not configuration. Everything an operator retunes
per site -- thresholds, camera, broker, weights, output, the upright gate -- is
layered; a gesture is a keypoint chain whose validity depends on another section,
and the two that survive are pinned exactly by the test suite. They stay here, in
one home, where they are read alongside the invariants that keep them honest.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, fields, is_dataclass
from pathlib import Path
from types import UnionType
from typing import Any, get_args, get_origin, get_type_hints

import yaml

from worksite_detector.events import EventType

# Prefix that marks an environment variable as ours, and the only nesting marker
# inside one. Two levels exactly: the schema is two levels deep and a third
# segment is a typo, not a deeper setting.
ENV_PREFIX = "WSM_"
_ENV_NESTING = "__"

# A COCO pose model reports 17 keypoints, indices 0-16. An index outside that
# range is an IndexError on the first frame, in production, at the site.
_MAX_KEYPOINT_INDEX = 16

_NONE_TYPE = type(None)
_TRUTHY = frozenset({"true", "yes", "on", "1"})
_FALSEY = frozenset({"false", "no", "off", "0"})


@dataclass(frozen=True, slots=True)
class GestureSpec:
    """One pose gesture: the joint it measures, the gate that guards it, its band.

    A gesture is counted when the measured angle first falls below ``maintaining``
    and then rises back above ``relaxing``. The two thresholds are a hysteresis
    band, not a pair of independent numbers, which is why they are validated
    against each other rather than one at a time.

    ``left_points_idx`` and ``right_points_idx`` are each one three-point chain in
    ``[end, vertex, end]`` order, as ``geometry.joint_angle`` takes them: the
    order is the angle's shape and is significant. The two ``*_visibility_idx``
    gates are sets in all but type -- their order means nothing -- and each must
    cover its own side's chain, because an angle measured from a keypoint whose
    confidence nobody checked is an angle over YOLO's ``(0, 0)`` "not found"
    sentinel, which reads as a real position and cannot be told from one.

    ``requires_upright`` is per gesture and deliberately not a global switch. The
    original's ``> 160`` posture gate stands in front of the bend and nowhere
    else; hoisting it onto the config would either gate ARMS_UP behind a posture
    it never required, or stop gating FRONT_BEND and double its rate on anyone
    bending sideways. The upright chain that flag refers to lives on ``Config``,
    so the rule tying the two together is enforced there.
    """

    event_type: EventType
    left_points_idx: tuple[int, int, int]
    right_points_idx: tuple[int, int, int]
    left_visibility_idx: tuple[int, ...]
    right_visibility_idx: tuple[int, ...]
    maintaining: float
    relaxing: float
    requires_upright: bool

    def __post_init__(self) -> None:
        if not 0.0 <= self.maintaining < self.relaxing <= 180.0:
            raise ValueError(
                f"{self.event_type.value} needs 0 <= maintaining < relaxing <= 180, got "
                f"maintaining={self.maintaining!r} and relaxing={self.relaxing!r}. The two "
                "are a hysteresis band: with no gap between them the gesture arms and can "
                "never release, so it is counted exactly never and nothing reports why."
            )

        for side in ("left", "right"):
            chain: tuple[int, ...] = getattr(self, f"{side}_points_idx")
            visible: tuple[int, ...] = getattr(self, f"{side}_visibility_idx")

            if len(chain) != 3:
                raise ValueError(
                    f"{self.event_type.value} {side}_points_idx is {chain}; an angle is "
                    "measured over exactly three keypoints, [end, vertex, end]."
                )
            if len(set(chain)) != 3:
                raise ValueError(
                    f"{self.event_type.value} {side}_points_idx repeats a keypoint in "
                    f"{chain}; a ray from the vertex to itself has no direction and no angle."
                )
            for index in (*chain, *visible):
                if not 0 <= index <= _MAX_KEYPOINT_INDEX:
                    raise ValueError(
                        f"{self.event_type.value} references keypoint {index} on the {side} "
                        f"side; a COCO pose has 17 keypoints, 0 to {_MAX_KEYPOINT_INDEX}."
                    )

            ungated = sorted(set(chain) - set(visible))
            if ungated:
                raise ValueError(
                    f"{self.event_type.value} measures its {side} angle over keypoints "
                    f"{ungated}, which its visibility gate {sorted(set(visible))} never "
                    "checks. A keypoint YOLO did not find arrives at (0, 0), which measures "
                    "as a real position, so the gate has to cover every point of the chain."
                )


# The two gestures that survive the rewrite, with the numbers the baseline
# recording was made against.
#
# COCO keypoint indices used below: 5/6 shoulders, 7/8 elbows, 11/12 hips, 13/14
# knees, 15/16 ankles -- odd on the left, even on the right.
#
# ARMS_UP is the original's 'armsUp' entry, gated as the original gated it.
# FRONT_BEND carries 'bending''s numbers because that is the entry the original
# actually read while emitting the name FRONT_BEND; its gate is the union of its
# own hip chain and the upright chain it depends on, which is the ankle coverage
# the original never had.
_DEFAULT_GESTURES: tuple[GestureSpec, ...] = (
    GestureSpec(
        event_type=EventType.ARMS_UP,
        left_points_idx=(11, 5, 7),
        right_points_idx=(12, 6, 8),
        left_visibility_idx=(5, 7, 11),
        right_visibility_idx=(6, 8, 12),
        maintaining=30.0,
        relaxing=140.0,
        requires_upright=False,
    ),
    GestureSpec(
        event_type=EventType.FRONT_BEND,
        left_points_idx=(5, 11, 13),
        right_points_idx=(6, 12, 14),
        left_visibility_idx=(5, 11, 13, 15),
        right_visibility_idx=(6, 12, 14, 16),
        maintaining=130.0,
        relaxing=160.0,
        requires_upright=True,
    ),
)


@dataclass(frozen=True, slots=True)
class ThresholdConfig:
    """The confidence gates and the two rate windows.

    The three confidences are fractions in [0, 1], the unit YOLO reports and the
    unit the engine's dashboard multiplies by 100 for display. The two durations
    are whole milliseconds, matching the ``Long startTime`` / ``Integer
    timePeriod`` the engine binds them to -- Jackson truncates a float into those
    without complaint, so the unit is in the name and the type is checked here.
    """

    pose_confidence: float = 0.8
    ppe_confidence: float = 0.6
    keypoint_visibility: float = 0.6
    fall_cooldown_ms: int = 180_000
    ppe_grace_ms: int = 1_500

    def __post_init__(self) -> None:
        for name in ("pose_confidence", "ppe_confidence", "keypoint_visibility"):
            fraction: float = getattr(self, name)
            if not 0.0 <= fraction <= 1.0:
                raise ValueError(
                    f"{name} must be a fraction in [0.0, 1.0], got {fraction!r}. Confidence "
                    "is a fraction everywhere in this pipeline: 80 is not 80 percent, it is "
                    "a gate no detection can clear, and the detector would then see nothing "
                    "and report nothing."
                )
        for name in ("fall_cooldown_ms", "ppe_grace_ms"):
            duration: int = getattr(self, name)
            if duration < 0:
                raise ValueError(
                    f"{name} must not be negative, got {duration}. A negative window "
                    "inverts the elapsed-time comparison it feeds instead of failing."
                )


@dataclass(frozen=True, slots=True)
class UprightConfig:
    """The posture precondition: a chain of keypoints and the angle across it.

    Kept as one unit because the two drifted apart in the original -- see the
    module docstring. ``angle_degrees`` is 160 and FRONT_BEND's ``relaxing`` is
    also 160; they are unrelated numbers the original happened to spell the same,
    and they live in different sections so that retuning one is not read as
    retuning both.
    """

    left_idx: tuple[int, int, int] = (11, 13, 15)
    right_idx: tuple[int, int, int] = (12, 14, 16)
    angle_degrees: float = 160.0

    def __post_init__(self) -> None:
        for side in ("left", "right"):
            chain: tuple[int, ...] = getattr(self, f"{side}_idx")
            if len(chain) != 3 or len(set(chain)) != 3:
                raise ValueError(
                    f"upright {side}_idx is {chain}; it must be three distinct keypoints, "
                    "[hip, knee, ankle], the chain the posture angle is measured over."
                )
            for index in chain:
                if not 0 <= index <= _MAX_KEYPOINT_INDEX:
                    raise ValueError(
                        f"upright {side}_idx references keypoint {index}; a COCO pose has "
                        f"17 keypoints, 0 to {_MAX_KEYPOINT_INDEX}."
                    )

        if set(self.left_idx) & set(self.right_idx):
            raise ValueError(
                f"the upright chains {self.left_idx} and {self.right_idx} share a keypoint, "
                "so they are not the two sides of one body; one of them is mistyped."
            )
        if not 0.0 <= self.angle_degrees <= 180.0:
            raise ValueError(
                f"upright angle_degrees must lie within [0.0, 180.0], got "
                f"{self.angle_degrees!r}; joint angles are unsigned and never exceed 180."
            )


@dataclass(frozen=True, slots=True)
class KafkaConfig:
    """Where events go.

    ``topic`` is half of a contract whose other half is the engine's
    ``@KafkaListener(topics = "rawEvents")``. Changing it on one side only
    publishes into the void, with no error on either side.
    """

    bootstrap_servers: str = "localhost:9092"
    topic: str = "rawEvents"

    def __post_init__(self) -> None:
        for name in ("bootstrap_servers", "topic"):
            value: str = getattr(self, name)
            if not value.strip():
                raise ValueError(f"kafka {name} must not be empty")


@dataclass(frozen=True, slots=True)
class CameraConfig:
    """What is watched, and what the events from it are called.

    ``name`` defaults to ``source`` because that is what the original sent
    (``cameraName: args.input``), so every event already in MongoDB from a default
    rig is labelled ``"0"``. Defaulting it to anything else would rename every
    camera at once and orphan the history the dashboard groups by name.
    """

    source: str = "0"
    name: str | None = None

    def __post_init__(self) -> None:
        if not self.source.strip():
            raise ValueError(
                "camera source must not be empty; it is a webcam index like '0', a video "
                "file path, or a stream URL."
            )
        if self.name is None:
            object.__setattr__(self, "name", self.source)
        elif not self.name.strip():
            raise ValueError(
                "camera name must not be empty; it is stored on every event and is how the "
                "dashboard attributes a violation to a site. Omit it to reuse the source."
            )


@dataclass(frozen=True, slots=True)
class ModelConfig:
    """Where the two sets of weights live.

    Nothing here is opened, resolved or stat-ed at load time; a path is a string
    of intent until the adapter that needs it runs. Relative paths are therefore
    resolved by the process working directory, which is also why the defaults are
    explicit about the directory: the original spelled the pose weights
    ``args.model`` and the PPE weights the bare literal ``"best.pt"``, two
    spellings of the same idea, both resolved against wherever the operator
    happened to be standing.
    """

    pose_weights: Path = Path("models/yolov8s-pose.pt")
    ppe_weights: Path = Path("models/best.pt")


@dataclass(frozen=True, slots=True)
class OutputConfig:
    """The annotated frame the web app polls as a "video stream".

    Not a stream: one file, overwritten in place every frame, served by the
    engine's ``EventController.getImage`` and polled by the browser.
    """

    annotated_frame_path: Path = Path("output_image.jpg")
    write_annotated_frame: bool = True


@dataclass(frozen=True, slots=True)
class Config:
    """The whole configuration of one detector process.

    Frozen throughout, sections included. The config is read on every frame by
    several rule objects at once, so one mutable field means any of them can
    retune the pipeline mid-run, and the resulting event stream is then not
    reproducible from the configuration that was loaded -- which is exactly what
    the baseline differential depends on. ``gestures`` is a tuple for the same
    reason: a list would let any caller holding the config append to it.
    """

    thresholds: ThresholdConfig = ThresholdConfig()
    upright: UprightConfig = UprightConfig()
    kafka: KafkaConfig = KafkaConfig()
    camera: CameraConfig = CameraConfig()
    models: ModelConfig = ModelConfig()
    output: OutputConfig = OutputConfig()
    gestures: tuple[GestureSpec, ...] = _DEFAULT_GESTURES

    def __post_init__(self) -> None:
        seen: set[EventType] = set()
        for spec in self.gestures:
            if spec.event_type in seen:
                raise ValueError(
                    f"{spec.event_type.value} is configured twice; each gesture is one "
                    "state machine, and a second entry silently doubles its event rate."
                )
            seen.add(spec.event_type)

            if spec.event_type.is_periodic:
                raise ValueError(
                    f"{spec.event_type.value} is a periodic event and cannot be a gesture: "
                    "it is published with a duration, which a gesture does not have."
                )
            if not spec.requires_upright:
                continue

            # The original's exact defect, made unconfigurable: gate one chain and
            # measure another. Only Config knows the upright chain, so only Config
            # can check that the gesture depending on it also gates it.
            for side in ("left", "right"):
                chain = set(getattr(self.upright, f"{side}_idx"))
                visible = set(getattr(spec, f"{side}_visibility_idx"))
                ungated = sorted(chain - visible)
                if ungated:
                    raise ValueError(
                        f"{spec.event_type.value} requires an upright check measured over "
                        f"{sorted(chain)}, but its {side} visibility gate "
                        f"{sorted(visible)} never checks {ungated}. The posture "
                        "precondition would then run on keypoints YOLO reported at (0, 0), "
                        "which is how a seated worker is counted as bending."
                    )


def _field_annotations(section: type) -> dict[str, Any]:
    """Resolved annotation of every field of a section dataclass."""
    hints = get_type_hints(section)
    return {spec.name: hints[spec.name] for spec in fields(section)}


def _discover_sections() -> dict[str, type]:
    """The configurable sections of ``Config``, by the name a key uses for them.

    Derived from ``Config`` itself rather than listed, so a new section is
    loadable, overridable and documented the moment it is declared -- a hand-kept
    list is one more thing that drifts, which is the failure this module exists
    to remove.
    """
    hints = get_type_hints(Config)
    return {
        spec.name: hints[spec.name]
        for spec in fields(Config)
        if isinstance(hints[spec.name], type) and is_dataclass(hints[spec.name])
    }


_SECTIONS: dict[str, type] = _discover_sections()
_SECTION_FIELDS: dict[str, dict[str, Any]] = {
    name: _field_annotations(section) for name, section in _SECTIONS.items()
}


def _annotation_of(section: str, leaf: str, label: str) -> Any:
    """The declared type of ``section.leaf``, or a ValueError naming the key.

    Both halves are refused separately so the message can say which half is
    wrong: an unknown section and an unknown field inside a known one are
    different mistakes and have different fixes.
    """
    if section not in _SECTION_FIELDS:
        raise ValueError(
            f"unknown configuration key {label!r}: there is no {section!r} section. "
            f"The sections are {sorted(_SECTION_FIELDS)}."
        )
    annotations = _SECTION_FIELDS[section]
    if leaf not in annotations:
        raise ValueError(
            f"unknown configuration key {label!r}: the {section!r} section has no "
            f"{leaf!r} setting. It has {sorted(annotations)}."
        )
    return annotations[leaf]


def _to_bool(raw: Any, label: str) -> bool:
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, str) and raw.strip().lower() in _TRUTHY:
        return True
    if isinstance(raw, str) and raw.strip().lower() in _FALSEY:
        return False
    raise ValueError(
        f"{label} must be true or false, got {raw!r}. It is spelled out rather than "
        "guessed because bool('false') is True, and an operator switching something off "
        "would be switching it on."
    )


def _to_int(raw: Any, label: str) -> int:
    if isinstance(raw, bool):
        raise ValueError(f"{label} must be a whole number, got the boolean {raw!r}")
    if isinstance(raw, int):
        return raw
    if isinstance(raw, str):
        try:
            return int(raw.strip())
        except ValueError:
            raise ValueError(f"{label} must be a whole number, got {raw!r}") from None
    raise ValueError(f"{label} must be a whole number, got {raw!r}")


def _to_float(raw: Any, label: str) -> float:
    if isinstance(raw, bool):
        raise ValueError(f"{label} must be a number, got the boolean {raw!r}")
    if isinstance(raw, (int, float)):
        return float(raw)
    if isinstance(raw, str):
        try:
            return float(raw.strip())
        except ValueError:
            raise ValueError(f"{label} must be a number, got {raw!r}") from None
    raise ValueError(f"{label} must be a number, got {raw!r}")


def _to_str(raw: Any, label: str) -> str:
    if isinstance(raw, str):
        return raw
    if isinstance(raw, bool):
        raise ValueError(f"{label} must be text, got the boolean {raw!r}")
    if isinstance(raw, (int, float)):
        # `camera: {source: 0}` is the natural way to write a webcam index in
        # YAML and arrives as an int; the detector wants the string the original
        # sent, because it is also the camera name stored on every event.
        return str(raw)
    raise ValueError(f"{label} must be text, got {raw!r}")


def _to_path(raw: Any, label: str) -> Path:
    if isinstance(raw, Path):
        return raw
    if isinstance(raw, str) and raw.strip():
        return Path(raw)
    raise ValueError(f"{label} must be a filesystem path, got {raw!r}")


def _to_tuple(raw: Any, annotation: Any, label: str) -> tuple[Any, ...]:
    args = get_args(annotation)
    variadic = len(args) == 2 and args[1] is Ellipsis
    item_annotation = args[0]

    if isinstance(raw, str):
        # The environment cannot carry a list, so a keypoint chain arrives as
        # "11,13,15". YAML carries a real list and arrives as one.
        items: list[Any] = [part.strip() for part in raw.split(",") if part.strip()]
    elif isinstance(raw, (list, tuple)):
        items = list(raw)
    else:
        raise ValueError(
            f"{label} must be a list of values, or a comma-separated string, got {raw!r}"
        )

    if not variadic and len(items) != len(args):
        raise ValueError(f"{label} must list exactly {len(args)} values, got {items}")
    return tuple(_coerce(item, item_annotation, f"{label}[{n}]") for n, item in enumerate(items))


def _coerce(raw: Any, annotation: Any, label: str) -> Any:
    """Convert one loaded value to the type its field declares.

    Driven by the dataclass annotation rather than by a table of field names, so
    a field cannot be added without its conversion, and the conversion cannot
    drift from the type the rest of the code will read.
    """
    if get_origin(annotation) is UnionType:
        # The only union in the schema is `str | None`, where None means "derive
        # it" -- so an explicit `null` in YAML has to survive to __post_init__.
        if raw is None:
            return None
        member = next(arg for arg in get_args(annotation) if arg is not _NONE_TYPE)
        return _coerce(raw, member, label)
    if get_origin(annotation) is tuple:
        return _to_tuple(raw, annotation, label)
    if annotation is bool:
        return _to_bool(raw, label)
    if annotation is int:
        return _to_int(raw, label)
    if annotation is float:
        return _to_float(raw, label)
    if annotation is Path:
        return _to_path(raw, label)
    return _to_str(raw, label)


def _read_yaml(path: Path) -> Mapping[str, Any]:
    """Parse the config file into a mapping of sections.

    Every failure here is a ValueError, including a YAML syntax error: one
    exception type for "your configuration is wrong" means the caller has one
    thing to catch and report at startup.
    """
    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ValueError(f"{path} is not valid YAML: {exc}") from exc

    if document is None:
        return {}
    if not isinstance(document, Mapping):
        raise ValueError(
            f"{path} must contain a mapping of sections, got {type(document).__name__}"
        )
    return document


def _merge_document(overrides: dict[str, dict[str, Any]], document: Mapping[str, Any]) -> None:
    """Apply a parsed YAML document over ``overrides``, one leaf at a time.

    Leaf by leaf rather than section by section: replacing whole sections would
    reset every sibling of the one setting the file names back to its default,
    which is a change the file did not ask for and does not mention.
    """
    for raw_section, leaves in document.items():
        section = str(raw_section)
        if section not in _SECTION_FIELDS:
            raise ValueError(
                f"unknown configuration section {section!r}. "
                f"The sections are {sorted(_SECTION_FIELDS)}."
            )
        if not isinstance(leaves, Mapping):
            raise ValueError(
                f"the {section!r} section must be a mapping of settings, got "
                f"{type(leaves).__name__}"
            )

        for raw_leaf, value in leaves.items():
            leaf = str(raw_leaf)
            label = f"{section}.{leaf}"
            annotation = _annotation_of(section, leaf, label)
            overrides.setdefault(section, {})[leaf] = _coerce(value, annotation, label)


def _merge_env(overrides: dict[str, dict[str, Any]], env: Mapping[str, str]) -> None:
    """Apply the ``WSM_``-prefixed variables of ``env`` over ``overrides``."""
    for name, value in env.items():
        if not name.upper().startswith(ENV_PREFIX):
            continue

        parts = name[len(ENV_PREFIX) :].lower().split(_ENV_NESTING)
        if len(parts) != 2 or not all(parts):
            raise ValueError(
                f"{name!r} does not name a setting. Environment overrides are spelled "
                f"{ENV_PREFIX}<SECTION>{_ENV_NESTING}<FIELD>, with exactly one "
                f"{_ENV_NESTING!r}: the schema is two levels deep, so a third segment is a "
                f"typo rather than a deeper setting. The sections are "
                f"{sorted(_SECTION_FIELDS)}."
            )

        section, leaf = parts
        label = f"{name} ({section}.{leaf})"
        annotation = _annotation_of(section, leaf, label)
        overrides.setdefault(section, {})[leaf] = _coerce(value, annotation, label)


def load_config(path: Path | str | None, env: Mapping[str, str]) -> Config:
    """Resolve the configuration from defaults, an optional file and an environment.

    ``path`` is a YAML file, or None for a machine that ships none. ``env`` is the
    environment to read ``WSM_``-prefixed overrides from -- normally
    ``os.environ``, passed in by the caller at the edge of the process, never read
    from here. Anything unprefixed in it is ignored.

    Nothing on the filesystem is consulted beyond ``path`` itself: the weights and
    the output frame are recorded as paths and are neither resolved nor opened.

    Raises:
        ValueError: If the file is not valid YAML or is not a mapping of
            sections; if any key -- in the file or ``WSM_``-prefixed in the
            environment -- names a section or setting that does not exist; if a
            value cannot be read as the type its field declares; or if the
            resolved configuration breaks one of the invariants documented on
            ``Config`` and ``GestureSpec``. Every message names the offending key,
            because the operator's next question is always which of a dozen
            settings they got wrong.
        FileNotFoundError: If ``path`` is given and does not exist. Silently
            falling back to defaults would start a detector that ignores the file
            the operator is looking at.
    """
    overrides: dict[str, dict[str, Any]] = {}
    if path is not None:
        _merge_document(overrides, _read_yaml(Path(path)))
    _merge_env(overrides, env)

    # Each section is built from its own defaults plus only the leaves that were
    # actually named, so an untouched setting keeps the default it declares.
    return Config(
        **{name: section(**overrides.get(name, {})) for name, section in _SECTIONS.items()}
    )
