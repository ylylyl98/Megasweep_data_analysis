# Automatic plot updates implementation plan

> Execute in the current session, preserving the existing uncommitted work. The user approved the design in chat with “改进”.

**Goal:** Give the current plot consistent automatic updates, retain manual updates, keep the previous plot visible, and prevent exporting stale results.

**Architecture:** A shared Qt control owns a single-shot debounce timer and Auto Update / Update Now controls. Transport uses it for maps and cuts; optical maps and slices use the existing workspace worker, resume pending updates after cleanup, and validate request signatures before publishing results. Hidden views calculate on entry, and hidden measurement workspaces remain idle.

**Tech stack:** Python, PySide6, Matplotlib, unittest. No new dependencies.

**Constraints:** Numeric edits commit on Enter/focus loss. Display ranges and colors remain immediate. CSV loading, Refresh All, batch exports and movie preparation/encoding stay explicit. Save choices in the existing per-file recipes. Timers stop when closing or replacing data.

## Tasks

- [x] Add integration tests in `tests/test_auto_update.py`, using real CSV fixtures and Qt event processing: automatic map/cut/slice updates, manual mode, invalid input, retained figures, hidden views and outdated worker results. Run `python -m unittest tests.test_auto_update -v` and confirm missing behavior fails.
- [x] Create `ui/auto_update.py` with `AutoUpdateControls(callback, can_update, delay, parent)`, exposing `checkbox`, `button`, `request()`, `cancel()`, `resume()` and `update_now()`. A stopped timer must never invoke the callback. Repeated requests coalesce; busy work remains pending until resumed.
- [x] Integrate Transport maps/cuts in `ui/transport.py`. Mark results stale without clearing the canvas; compute only valid selections; retain fixed cut selections through map refresh; prevent stale exports and keep automatic refresh from switching the selected tab. Persist both checkbox choices in `recipe()`.
- [x] Integrate optical maps through `ui/optical_layout.py` and `ui/measurement_workspace.py`. Schedule only the current view, validate prerequisites and file identity, resume after worker cleanup, discard obsolete payloads before rendering, preserve stale figures and disable exports. Stop automatic scheduling during session restoration and on close.
- [x] Integrate slices in `ui/spectral_slices.py`: selection changes invalidate exports while retaining the figure; editable values commit on editingFinished; coordinate, tolerance and processing changes coalesce; request signatures include the selected value and tolerance; automatic completion must not navigate away from the user's selected view. Persist the checkbox in the slice recipe.
- [x] Align existing RC preview updates with a manual/automatic choice in `ui/reflection_workflow.py`; keep first preview explicit and preserve raw/background behavior. Add toolbar export validity in `ui/widgets.py` so old plots cannot bypass the sidebar export guard.
- [x] Stop timers for inactive top-level measurement tabs and on application close in `ui/main_window.py`; restore pending current-view updates on activation. Update `README.md` with automatic/manual behavior and the distinction from reading new CSV points.
- [x] Run focused UI suites, then `python -m unittest discover -s tests -v`. Request an independent code review, fix significant findings, and verify the final changes.

## Verification

- Full unittest discovery: 220 tests passed (160.035 s).
- Independent review: no remaining Critical or Important findings; the minor explicit-navigation regression was fixed and tested.
- Light/dark Qt screenshots and narrow-sidebar layout reviewed.
- `git diff --check` passed; pre-existing line-ending notices remain.
- Installed the existing declared dependency `imageio-ffmpeg==0.6.0` for movie tests.
