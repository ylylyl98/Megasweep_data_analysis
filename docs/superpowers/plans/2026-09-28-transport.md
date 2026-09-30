# Transport mode implementation plan

**Goal:** Load scalar transport CSVs alongside PL/Reflection and display channel maps and cuts.
**Architecture:** A dedicated scalar loader and Transport widget reuse the map/export helpers and existing window/session infrastructure. Optical processing remains independent.
**Tech stack:** Python, pandas, NumPy, PySide6, Matplotlib.
**Spec:** Approved conversation design, amended by the user: selectors come from actual headers; do not hardcode Doping/Vds/Ids_X defaults.

## Constraints
- Never change source CSV/metadata; accept the optional units row and partial scans.
- Header-derived X/Y/channel choices, explicit selection when ambiguous.
- Preserve pass/direction information; never silently average duplicate coordinates.
- Persist choices per file; export only on explicit action.

## Tasks
- [x] Core (`transport_analysis.py`, `tests/test_transport.py`): test units-row parsing, numeric header choices, metadata grid completion, direction/pass filtering, duplicate rejection and both cut directions; run failing tests, implement, rerun.
- [x] UI (`ui/transport.py`, `ui/main_window.py`, `ui/session_memory.py`, `tests/test_transport_ui.py`): test real window load, header-derived selectors, map/cut rendering, exports and saved settings; implement Transport mode routing, controls and session integration.
- [x] Verification: run the full unittest suite, load both supplied CSVs read-only, render and inspect the Transport UI, review diff and document usage in README.

## Approved workspace-tab extension
The user requested separate PL/Reflection/Transport tabs, separate sidebars and plots,
and splitting MainWindow using `D:/Insturment control v3/PySide6_Data_plot` as a reference.
Its shell/workspace and feature-controller separation guides this change.

- [x] Extract shared widgets/styles, optical layout builders, reflection preview logic,
  and plot-result callbacks into focused modules. Keep numerical workers unchanged.
- [x] Convert the existing analysis controller to an embeddable MeasurementWorkspace,
  fixed to its mode in the application. Each instance owns its state, worker, sidebar,
  plots and caches. MainWindow owns only the three-tab shell and coordinated closing.
- [x] Namespace per-file memory by workspace mode, reading compatible old recipes as
  a fallback. A recipe must never switch another tab's mode or overwrite its settings.
- [x] Test simultaneous PL/Reflection loading, Transport plots retained across tab
  switches, separate settings for the same source file, and closing while workers run.
- [x] Re-run optical/transport regressions and inspect the new shell using actual data.

## Verification result
- Full unittest suite: 88 tests passed.
- Both supplied Transport CSVs loaded read-only; full scan reached 1111 measured points on an 11 × 101 grid.
- Map/cut PNG and CSV exports verified in a temporary output directory.
- Rendered and inspected the tab shell, Transport map and cut.
- Independent review found no remaining blocking issues.
