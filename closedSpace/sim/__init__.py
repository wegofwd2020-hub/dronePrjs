"""closedSpace.sim — domain-side glue for the tier-2 simulator.

The Protocol implementations themselves live in ``engine.sim_gazebo`` (a
cross-domain concern). This package owns the *closedSpace-specific*
inputs to that simulator — primarily the SDF world builder, which
turns a parsed warehouse :class:`closedSpace.map.types.Map` into the
Gazebo world a mission flies through.

Dependency direction: closedSpace → engine artifacts (writes into
``engine/sim_gazebo/worlds/``). Engine code does not import this
package; ISC-36 (no domain bleed) is preserved.
"""
from __future__ import annotations
