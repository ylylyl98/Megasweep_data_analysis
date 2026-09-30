# Transport axis suggestions implementation plan

**Goal:** Suggest Transport coordinates from validated metadata or measured scan structure, explain the suggestion, and support one-dimensional sweeps.
**Approved design:** Conversation of 2026-09-29: metadata axis_fast/axis_slow first, plot_x_axis determines orientation when valid; otherwise inspect varying non-signal columns and grids. Ambiguous cases remain manual. A single scan coordinate uses a curve. User selections remain overridable and saved per file.
**Architecture:** Pure inference in transport_axes.py, scalar curve extraction in transport_analysis.py, and selection/presentation integration in ui/transport.py. Loading workers compute suggestions; numerical analysis remains separate from Qt.

- [x] Add failing tests for metadata orientation, stale metadata, missing slow-axis variation in partial acquisitions, fallback grid detection, linked gates, ambiguity and 1D curves.
- [x] Implement suggestions with reasons, exclude signals/readbacks/recording columns from fallback inference, and reject ambiguous candidate pairs.
- [x] Add failing UI tests for suggestions, saved/manual priority, explicit reapply, 1D plotting/export and session restore.
- [x] Integrate inference explanation and 2D/1D controls; preserve pass/direction traces and existing map/cut workflows.
- [x] Validate with the user's actual CSVs, full regression tests and an independent code review; update README.

## Verification
- 100 regression tests passed.
- Actual supplied metadata files suggest X=Doping / Y=Vds, including the 5-point partial scan.
- The metadata-free file with equivalent Vtg/Vbg/Doping coordinates remains ambiguous and lists candidates.
- Rendered and inspected suggested-axis maps and one-dimensional forward/reverse curves.
- Independent review found no actionable blockers.
