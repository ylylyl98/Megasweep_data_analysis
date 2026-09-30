# Tab layout improvements

User authorized inspection and improvement of each measurement tab.

- Keep each workspace's data, plots, and settings independent.
- Give plots more height with an initially collapsed log; errors reveal it.
- Reduce control padding while preserving readable labels and focus states.
- Group optical transform/smoothing options separately from primary analysis.
- Align Transport selectors, collapse loaded data, hide map-only controls in curves.
- Recompute optical figure layout on canvas resize without changing export sizing.
- Verify minimum-size renders for all tabs, resizing, existing workflows and exports.

Completed: 103 unittest cases pass. Rendered all tabs at 1280×800 and
1440×960 with 100% and 150% scale, plus Transport curve mode and expanded
optical advanced/export sections at a 360px sidebar. Review found no blockers.
Optical plot host height at 1280×800 increased from 295 to 505px; Transport
from 464 to 650px. Existing library deprecation warnings remain; switching
hidden canvases can briefly emit Matplotlib's tight-layout margin warning,
but final visible renders and label-bounds checks pass.

Follow-up: related sidebar fields now share rows, with smaller card/control
spacing and a 360px default sidebar. Numeric editor widths respect native size
hints to preserve precision; groups wrap when necessary. Compact layouts were
rendered at 100%/150% and reviewed.

Mouse wheels no longer change spinbox values or combo selections, focused or
not; wheel input over editors scrolls the enclosing panel. Keyboard editing and
popup-list scrolling remain available. Full regression suite: 105 tests pass,
including two wheel behavior tests; the expanded popup test also passes alone.
