# Spectral Slice Movies Implementation Plan

> **For agentic workers:** Implement this approved plan inline, task by task; use a separate code reviewer after implementation.

**Goal:** Export scientifically consistent MP4 slice sequences from PL/Reflection workspaces.

**Architecture:** A Qt-independent movie module takes a measured-coordinate cut factory and renders existing Megasweep plots to an FFmpeg pipe. A worker adapts the existing extraction pipeline; a Qt dialog collects validated sequence/playback options. Existing display controls supply batch and movie view settings.

**Tech Stack:** Python, NumPy, Matplotlib Agg, PySide6, imageio-ffmpeg.

**Spec:** `docs/superpowers/specs/2026-09-30-spectral-slice-movies-design.md`

## Global Constraints

- Python >=3.10; imageio-ffmpeg>=0.5,<1 is the only new dependency.
- Keep source measurements, existing exports and pre-existing uncommitted changes.
- Use Megasweep slice plotting and processing for movie frames.
- Only Spectral Slices is visible for optical slicing; preserve legacy recipe compatibility.

## Task 1: Movie engine

Files: create `spectral_movie.py`, `tests/test_spectral_movie.py`; modify `requirements.txt`.

Interface: `MovieOptions`, `select_values(values, first, last, stride)`, `timeline(count, options)`, `resolve_sequence_view(cut_factory, values, ranges, color_mode, colors)`, `render_frame(cut, view, options)`, `export_movie(cut_factory, values, destination, options, ranges, colors, metadata, progress, cancel)`.

- [x] Write tests with irregular literal coordinates, forward/reverse/pingpong timing, global/manual/per-frame color behavior, fixed layout, real MP4 decoding, cancellation and numbered outputs.
- [x] Run `.venv/Scripts/python.exe -m unittest tests.test_spectral_movie -v` and confirm missing feature failures.
- [x] Implement input validation, fixed views, Agg frame rendering, streamed FFmpeg encoding, full decode validation, cleanup and paired provenance publication.
- [x] Rerun the movie tests until all pass.

## Task 2: Shared batch display and axis selection

Files: modify `ui/spectral_slices.py`, `ui/workers.py`, `tests/test_spectral_slices_ui.py`.

Interface: `BatchLineWorker(..., display_ranges=None, color_settings=None)`; panel sends its current range/color recipes. Already transformed inputs use `x`/`y` extraction with actual labels and no redundant selector, while raw gates retain D/E conversion.

- [x] Write integration tests proving exported batch figures respect manual limits and CSVs remain complete, and loaded D/E controls avoid duplicate choices.
- [x] Run the new UI tests and confirm expected failures.
- [x] Implement optional batch view settings, unified auto ranges and nonduplicated loaded-axis choices without changing legacy callers.
- [x] Run spectral slices, session-memory and batch regressions.

## Task 3: Movie controls and lifecycle

Files: create `ui/spectral_movie.py`; modify `ui/workers.py`, `ui/spectral_slices.py`; create `tests/test_spectral_movie_ui.py`.

Interface: `SpectralMovieDialog(values, axis_label, ranges, colors, recipe, parent)`, `configuration()`; `SpectralMovieWorker` adapts extraction and owns a cancellation event. Panel owns an independent progress dialog and persists options.

- [x] Write tests for inclusive selection, preview duration, invalid inputs, settings restoration, real PL/Reflection export provenance and cancellation while the panel is disabled.
- [x] Confirm missing-feature failures, then implement native Qt controls, inline validation, export entry, progress/cancel and worker callbacks.
- [x] Run movie UI and workspace/session regressions; render the dialog at 100%/150% scale for layout inspection.

## Task 4: Documentation, review and final verification

Files: update `README.md`; review the complete worktree changes.

- [x] Document range inheritance, color modes, playback settings, output paths and dependency installation.
- [x] Run `.venv/Scripts/python.exe -m unittest discover -s tests` and `git diff --check`.
- [x] Request a read-only reviewer subagent against the design and current diff; fix material findings with focused regression tests.
- [x] Report verification evidence and practical limitations. Leave changes available in the workspace without automatically committing user edits.

Verification: full suite passed 164 tests; an additional default-label bounds regression and all 13 movie-engine tests passed afterwards. Independent read-only review cleared the material findings. Dialog layout inspected at 100%/150% in light/dark styles using application-loaded Segoe UI for the offscreen font environment. Existing Matplotlib/Qt deprecation warnings remain unrelated to this change.
