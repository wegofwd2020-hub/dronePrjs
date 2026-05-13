"""Build Gazebo SDF 1.10 worlds from closedSpace warehouse maps.

The mission planner derives waypoints from the same :class:`Map`; the
world builder gives the tier-2 simulator a matching environment so what
the drone sees in Gazebo lines up with what the plan expects.

Geometry conventions (mirroring ``docs/map-schema.md`` §2):

* Map frame is right-handed, ``+x`` east, ``+y`` north, ``+z`` up.
  SDF's default world frame matches, so no remapping.
* Each rack becomes one static box: front face sits at
  ``aisle.width_m / 2`` perpendicular to the centerline on the rack's
  side; the box extends outward by :data:`RACK_DEPTH_M` and upward to
  cover the highest declared level plus :data:`RACK_TOP_BUFFER_M`.
* No-go zones become tall static boxes spanning the polygon's
  axis-aligned bounding box from ``z_min`` to ``z_max``. v1 supports
  axis-aligned no-go polygons only; the reference fixture's only zone
  is a 0.2 m × 0.2 m support column, which fits.
* The ground plane covers the coverage polygon's axis-aligned bounding
  box. v1 supports rectangular coverage polygons only and asserts so.
* The takeoff pad becomes a thin red cylinder for visual reference; it
  has no collision (the drone arms there).

Determinism: pure function. Same :class:`Map` → byte-identical SDF.
Rack ordering follows declared order (aisles → sides west→east /
south→north → racks by ``position_along``).
"""
from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

from closedSpace.map import load as load_map
from closedSpace.map.types import Aisle, Map, NoGoZone, Point2D, Rack, SideName, TakeoffPad

#: Perpendicular depth of a modeled rack (aisle face → back). The
#: schema does not carry rack depth — it only constrains the front face
#: position. 0.4 m is a typical industrial-shelf depth; collision in
#: Gazebo only cares about the front face under normal capture poses.
RACK_DEPTH_M: float = 0.4

#: Extra height above the highest declared level so the rack box visibly
#: tops the topmost shelf. Keeps the visual sane without affecting the
#: drone's flight envelope (planner caps z at MAX_FLIGHT_ALTITUDE_M).
RACK_TOP_BUFFER_M: float = 0.3

#: Visual radius of the takeoff-pad marker disk. The actual pad's
#: physical radius (``TakeoffPad.radius_m``) is what the operator
#: enforces — this is just a marker.
_TAKEOFF_MARKER_THICKNESS_M: float = 0.02

#: Floating-point format used throughout. Six decimals is well below
#: any sensor noise floor and keeps generated SDF reproducible across
#: platforms (no platform-dependent ``repr(float)`` drift).
_FMT: str = "{:.6f}"


def _f(value: float) -> str:
    return _FMT.format(value)


def _aisle_direction_and_length(aisle: Aisle) -> tuple[float, float, float]:
    """Return ``(dx, dy, length)`` for ``aisle``'s centerline unit vector.

    The centerline is non-degenerate by construction (validator rejects
    zero-length aisles), so the division is safe.
    """
    sx, sy = aisle.centerline.start.x, aisle.centerline.start.y
    ex, ey = aisle.centerline.end.x, aisle.centerline.end.y
    raw_dx, raw_dy = ex - sx, ey - sy
    length = math.hypot(raw_dx, raw_dy)
    return raw_dx / length, raw_dy / length, length


def _perpendicular_for_side(dx: float, dy: float, side: SideName) -> tuple[float, float]:
    """Return the unit perpendicular pointing toward ``side`` of the aisle.

    Standing at the centerline looking along ``+d`` (start→end):

    * left-hand perpendicular is ``(-dy, dx)`` — corresponds to ``west``
      for a north-pointing aisle and ``south`` for an east-pointing one.
    * right-hand perpendicular is ``(dy, -dx)`` — ``east`` / ``north``.

    Mismatches (e.g. a ``north`` side declared on a north-south aisle)
    are caught by the map validator, not here.
    """
    if side in ("west", "south"):
        return -dy, dx
    return dy, -dx


def _rack_pose_and_size(
    aisle: Aisle, rack: Rack, side: SideName
) -> tuple[float, float, float, float, float, float, float]:
    """Compute ``(cx, cy, cz, yaw, sx, sy, sz)`` for the rack's SDF box.

    ``cx, cy, cz`` is the box centroid; ``yaw`` rotates the box so its
    local ``+x`` axis aligns with the aisle centerline direction
    (``length_m`` extent along the aisle, ``RACK_DEPTH_M`` perpendicular,
    height up).
    """
    dx, dy, _ = _aisle_direction_and_length(aisle)
    perp_x, perp_y = _perpendicular_for_side(dx, dy, side)

    start = aisle.centerline.start
    along_x = start.x + rack.position_along * dx
    along_y = start.y + rack.position_along * dy

    half_width = aisle.width_m / 2.0
    face_x = along_x + half_width * perp_x
    face_y = along_y + half_width * perp_y

    box_center_x = face_x + (RACK_DEPTH_M / 2.0) * perp_x
    box_center_y = face_y + (RACK_DEPTH_M / 2.0) * perp_y

    top_height = max(level.height_m for level in rack.levels) + RACK_TOP_BUFFER_M
    box_center_z = top_height / 2.0

    yaw = math.atan2(dy, dx)
    return box_center_x, box_center_y, box_center_z, yaw, rack.length_m, RACK_DEPTH_M, top_height


def _coverage_extent(polygon: tuple[Point2D, ...]) -> tuple[float, float, float, float]:
    """Return ``(xmin, ymin, xmax, ymax)`` of the coverage polygon."""
    xs = [p.x for p in polygon]
    ys = [p.y for p in polygon]
    return min(xs), min(ys), max(xs), max(ys)


def _no_go_extent(zone: NoGoZone) -> tuple[float, float, float, float]:
    xs = [p.x for p in zone.polygon]
    ys = [p.y for p in zone.polygon]
    return min(xs), min(ys), max(xs), max(ys)


# ---------------------------------------------------------------------------
# SDF fragment builders. Each returns a string with a trailing newline so
# the caller can simply concatenate.
# ---------------------------------------------------------------------------

def _header(warehouse_id: str) -> str:
    return (
        '<?xml version="1.0"?>\n'
        '<sdf version="1.10">\n'
        f'  <world name="{warehouse_id}">\n'
        '    <physics name="1ms" type="ignored">\n'
        '      <max_step_size>0.001</max_step_size>\n'
        '      <real_time_factor>1.0</real_time_factor>\n'
        '    </physics>\n'
        '    <plugin filename="gz-sim-physics-system"\n'
        '            name="gz::sim::systems::Physics"/>\n'
        '    <plugin filename="gz-sim-user-commands-system"\n'
        '            name="gz::sim::systems::UserCommands"/>\n'
        '    <plugin filename="gz-sim-scene-broadcaster-system"\n'
        '            name="gz::sim::systems::SceneBroadcaster"/>\n'
        '    <plugin filename="gz-sim-sensors-system"\n'
        '            name="gz::sim::systems::Sensors">\n'
        '      <render_engine>ogre2</render_engine>\n'
        '    </plugin>\n'
        '    <light type="directional" name="sun">\n'
        '      <cast_shadows>true</cast_shadows>\n'
        '      <pose>0 0 10 0 0 0</pose>\n'
        '      <diffuse>0.8 0.8 0.8 1</diffuse>\n'
        '      <specular>0.2 0.2 0.2 1</specular>\n'
        '      <direction>-0.5 0.1 -0.9</direction>\n'
        '    </light>\n'
    )


def _ground_plane(polygon: tuple[Point2D, ...]) -> str:
    """Static ground covering the coverage polygon's bounding box."""
    xmin, ymin, xmax, ymax = _coverage_extent(polygon)
    cx, cy = (xmin + xmax) / 2.0, (ymin + ymax) / 2.0
    sx, sy = xmax - xmin, ymax - ymin
    return (
        '    <model name="ground_plane">\n'
        '      <static>true</static>\n'
        f'      <pose>{_f(cx)} {_f(cy)} 0 0 0 0</pose>\n'
        '      <link name="link">\n'
        '        <collision name="collision">\n'
        f'          <geometry><box><size>{_f(sx)} {_f(sy)} 0.01</size></box></geometry>\n'
        '          <pose>0 0 -0.005 0 0 0</pose>\n'
        '        </collision>\n'
        '        <visual name="visual">\n'
        f'          <geometry><box><size>{_f(sx)} {_f(sy)} 0.01</size></box></geometry>\n'
        '          <pose>0 0 -0.005 0 0 0</pose>\n'
        '          <material>\n'
        '            <ambient>0.3 0.3 0.3 1</ambient>\n'
        '            <diffuse>0.5 0.5 0.5 1</diffuse>\n'
        '          </material>\n'
        '        </visual>\n'
        '      </link>\n'
        '    </model>\n'
    )


def _rack_model(aisle: Aisle, rack: Rack, side: SideName) -> str:
    cx, cy, cz, yaw, sx, sy, sz = _rack_pose_and_size(aisle, rack, side)
    name = f"rack_{rack.id}"
    return (
        f'    <model name="{name}">\n'
        '      <static>true</static>\n'
        f'      <pose>{_f(cx)} {_f(cy)} {_f(cz)} 0 0 {_f(yaw)}</pose>\n'
        '      <link name="link">\n'
        '        <collision name="collision">\n'
        f'          <geometry><box><size>{_f(sx)} {_f(sy)} {_f(sz)}</size></box></geometry>\n'
        '        </collision>\n'
        '        <visual name="visual">\n'
        f'          <geometry><box><size>{_f(sx)} {_f(sy)} {_f(sz)}</size></box></geometry>\n'
        '          <material>\n'
        '            <ambient>0.4 0.25 0.1 1</ambient>\n'
        '            <diffuse>0.6 0.4 0.2 1</diffuse>\n'
        '          </material>\n'
        '        </visual>\n'
        '      </link>\n'
        '    </model>\n'
    )


def _no_go_model(zone: NoGoZone) -> str:
    xmin, ymin, xmax, ymax = _no_go_extent(zone)
    cx, cy = (xmin + xmax) / 2.0, (ymin + ymax) / 2.0
    sx, sy = max(xmax - xmin, 0.05), max(ymax - ymin, 0.05)
    sz = zone.z_max - zone.z_min
    cz = (zone.z_min + zone.z_max) / 2.0
    name = f"no_go_{zone.id}"
    return (
        f'    <model name="{name}">\n'
        '      <static>true</static>\n'
        f'      <pose>{_f(cx)} {_f(cy)} {_f(cz)} 0 0 0</pose>\n'
        '      <link name="link">\n'
        '        <collision name="collision">\n'
        f'          <geometry><box><size>{_f(sx)} {_f(sy)} {_f(sz)}</size></box></geometry>\n'
        '        </collision>\n'
        '        <visual name="visual">\n'
        f'          <geometry><box><size>{_f(sx)} {_f(sy)} {_f(sz)}</size></box></geometry>\n'
        '          <material>\n'
        '            <ambient>0.5 0.5 0.5 1</ambient>\n'
        '            <diffuse>0.7 0.7 0.7 1</diffuse>\n'
        '          </material>\n'
        '        </visual>\n'
        '      </link>\n'
        '    </model>\n'
    )


def _takeoff_marker(pad: TakeoffPad) -> str:
    return (
        '    <model name="takeoff_pad_marker">\n'
        '      <static>true</static>\n'
        f'      <pose>{_f(pad.position.x)} {_f(pad.position.y)} '
        f'{_f(pad.position.z + _TAKEOFF_MARKER_THICKNESS_M / 2.0)} '
        f'0 0 {_f(math.radians(pad.yaw_deg))}</pose>\n'
        '      <link name="link">\n'
        '        <visual name="visual">\n'
        '          <geometry>\n'
        f'            <cylinder><radius>{_f(pad.radius_m)}</radius>'
        f'<length>{_f(_TAKEOFF_MARKER_THICKNESS_M)}</length></cylinder>\n'
        '          </geometry>\n'
        '          <material>\n'
        '            <ambient>0.8 0.1 0.1 1</ambient>\n'
        '            <diffuse>1.0 0.2 0.2 1</diffuse>\n'
        '          </material>\n'
        '        </visual>\n'
        '      </link>\n'
        '    </model>\n'
    )


def _footer() -> str:
    return '  </world>\n</sdf>\n'


def build_sdf(world_map: Map) -> str:
    """Return an SDF 1.10 world string for ``world_map``.

    Raises :class:`ValueError` if the coverage polygon is not a
    rectangle (v1 limitation; non-rectangular floors land in a later
    iteration once a fixture exercises them).
    """
    xs = sorted({p.x for p in world_map.coverage_polygon})
    ys = sorted({p.y for p in world_map.coverage_polygon})
    if not (len(xs) == 2 and len(ys) == 2 and len(world_map.coverage_polygon) == 4):
        raise ValueError(
            "world_builder v1 only supports axis-aligned rectangular "
            "coverage polygons; got vertices "
            f"{[(p.x, p.y) for p in world_map.coverage_polygon]}"
        )

    fragments: list[str] = [
        _header(world_map.warehouse_id),
        _ground_plane(world_map.coverage_polygon),
        _takeoff_marker(world_map.takeoff_pad),
    ]
    for aisle in world_map.aisles:
        for side_name in ("west", "east", "south", "north"):
            for rack in aisle.racks.get(side_name, ()):
                fragments.append(_rack_model(aisle, rack, side_name))
    for zone in world_map.no_go_zones:
        fragments.append(_no_go_model(zone))
    fragments.append(_footer())
    return "".join(fragments)


def _cli(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m closedSpace.sim.world_builder",
        description="Generate a Gazebo SDF world from a closedSpace map.",
    )
    parser.add_argument("map_path", type=Path, help="Path to the warehouse map YAML.")
    parser.add_argument(
        "out_path",
        type=Path,
        help="Where to write the .sdf file. Parent directory must exist.",
    )
    args = parser.parse_args(argv)

    if not args.out_path.parent.is_dir():
        raise FileNotFoundError(
            f"Output directory {args.out_path.parent} does not exist; "
            "create it before running."
        )
    sdf = build_sdf(load_map(args.map_path))
    args.out_path.write_text(sdf, encoding="utf-8")
    print(f"wrote {len(sdf)} bytes to {args.out_path}")
    return 0


if __name__ == "__main__":  # pragma: no cover - thin CLI wrapper
    sys.exit(_cli(sys.argv[1:]))
