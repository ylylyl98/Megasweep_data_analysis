import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import time
import json
import unittest
from unittest.mock import patch
import numpy as np

from PySide6.QtCore import QTimer, Qt
from PySide6.QtTest import QTest
from PySide6.QtGui import QImage, QColor
from PySide6.QtWidgets import QApplication

from tests.test_session_memory import SessionMemoryFixture
from ui.spectral_movie import SpectralMovieDialog


class PreviewButtonTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_preview_requests_valid_settings_and_keeps_poster_visible(self):
        poster = QImage(420, 288, QImage.Format_RGB32)
        poster.fill(QColor('white'))
        dialog = SpectralMovieDialog([0, 1], 'Bias', poster=poster)
        self.addCleanup(dialog.close)
        dialog.show()
        self.app.processEvents()
        requests = []
        dialog.preview_requested.connect(requests.append)
        dialog.preview_btn.click()
        self.assertEqual(requests[0]['values'], [0., 1.])
        self.assertIs(dialog.preview.window(), dialog)
        self.assertFalse(dialog.preview.video.pixmap().isNull())
        self.assertFalse(dialog.export_btn.isEnabled())
        dialog.preview.generation_finished()
        dialog.first_combo.setCurrentIndex(1)
        dialog.last_combo.setCurrentIndex(0)
        self.assertFalse(dialog.preview_btn.isEnabled())

    def test_enter_confirms_parameters_without_exporting(self):
        dialog = SpectralMovieDialog([0, 1], 'Bias')
        self.addCleanup(dialog.close)
        dialog.show()
        self.app.processEvents()
        accepted = []
        dialog.accepted.connect(lambda: accepted.append(True))
        dialog.hold_spin.setFocus()
        dialog.hold_spin.lineEdit().selectAll()
        QTest.keyClicks(dialog.hold_spin.lineEdit(), '0.75')
        QTest.keyClick(dialog.hold_spin.lineEdit(), Qt.Key_Return)
        self.assertAlmostEqual(dialog.hold_spin.value(), .75)
        self.assertEqual(accepted, [])
        self.assertTrue(dialog.isVisible())
        dialog.color_combo.setCurrentIndex(dialog.color_combo.findData('manual'))
        dialog.vmin_edit.setText('-10')
        dialog.vmin_edit.setFocus()
        QTest.keyClick(dialog.vmin_edit, Qt.Key_Enter)
        self.assertEqual(accepted, [])
        dialog.range_controls.modes['x'].setCurrentIndex(dialog.range_controls.modes['x'].findData(False))
        lower, upper = dialog.range_controls.controls['x'][1:]
        lower.setText('1.2')
        upper.setText('1.3')
        upper.setFocus()
        QTest.keyClick(upper, Qt.Key_Return)
        self.assertEqual(accepted, [])
        self.assertEqual(dialog.configuration()['ranges']['x'], dict(auto=False, min=1.2, max=1.3))
        for widget in (dialog, dialog.preview_btn, dialog.export_btn):
            widget.setFocus()
            for key in (Qt.Key_Return, Qt.Key_Enter):
                QTest.keyClick(widget, key)
                self.assertEqual(accepted, [])
        QTest.mouseClick(dialog.export_btn, Qt.LeftButton)
        self.assertEqual(accepted, [True])

    def test_playback_waits_for_missing_images_and_visits_every_slice(self):
        from spectral_movie import MovieOptions
        from ui.movie_preview import MoviePreviewWidget
        preview = MoviePreviewWidget()
        self.addCleanup(preview.dispose)
        options = MovieOptions(hold=.1, fps=10)
        preview.configuration = dict(values=[0., 1., 2., 3.], options=vars(options), colors={})
        pixels = np.zeros((10, 10, 3), dtype=np.uint8)
        requests = []
        def request(payload):
            requests.append(payload)
            preview.working = True
        preview.frame_requested.connect(request)
        with patch('ui.movie_preview.time.monotonic', return_value=0.) as now:
            from types import SimpleNamespace
            preview.movie_ready(dict(session=SimpleNamespace(close=lambda: None), view=dict(values=[0., 1., 2., 3.], skipped=[]),
                                     options=vars(options), value=0., image=pixels))
            preview._timer.stop()
            shown = [preview.displayed_value]
            for index in (1, 2, 3):
                now.return_value += .5  # A slow paint/event loop must not skip slices.
                preview._advance()
                self.assertEqual(requests[-1]['value'], float(index))
                self.assertEqual(preview.position_ms, index * 100)
                now.return_value += .5  # Simulate slow rendering while the timer keeps ticking.
                preview._advance()
                self.assertEqual(preview.position_ms, index * 100)
                self.assertTrue(preview._playing)
                preview.frame_ready(dict(value=float(index), image=pixels, revision=preview._revision))
                preview.frame_finished()
                shown.append(preview.displayed_value)
            now.return_value += .5
            preview._advance()
            self.assertEqual(shown, [0., 1., 2., 3.])
            self.assertFalse(preview._playing)


class MoviePreviewTests(SessionMemoryFixture, unittest.TestCase):
    def make_preview(self):
        window = self.window()
        self.load(window, self.csv)
        panel = window.spectral_slices_panel
        panel.extract()
        self.wait_idle(window)
        dialog = SpectralMovieDialog([0, 1], 'Bias', parent=window)
        dialog.width_spin.setValue(420)
        dialog.height_spin.setValue(288)
        dialog.hold_spin.setValue(.2)
        dialog.fps_spin.setValue(10)
        dialog.preview_requested.connect(lambda config: panel.start_movie_preview(dialog.preview, config))
        dialog.preview.frame_requested.connect(lambda request: panel._preview_frame(dialog.preview, request))
        dialog.show()
        self.addCleanup(dialog.close)
        return window, panel, dialog

    def prepare(self, window, dialog):
        with patch('ui.workers.export_movie', side_effect=AssertionError('Preview must never encode MP4')):
            dialog.preview_btn.click()
            self.wait_idle(window)
        dialog.preview.pause()
        self.assertTrue(dialog.preview.ready)

    def test_preview_renders_real_pixels_with_export_view_without_encoding(self):
        window, panel, dialog = self.make_preview()
        panel.ranges.restore(dict(x=dict(auto=False, min=1.2, max=1.3),
                                  y=dict(auto=False, min=-.1, max=1.1)))
        dialog.range_controls.restore(panel.ranges.recipe())
        self.prepare(window, dialog)
        preview = dialog.preview
        self.assertEqual(preview.view['xlim'], (1.2, 1.3))
        self.assertFalse(preview.video.pixmap().isNull())
        self.assertEqual(preview.duration_ms, 400)
        self.assertEqual(list(self.root.rglob('*.mp4')), [])
        self.assertFalse(hasattr(preview, 'player'), 'Interactive preview should play images directly')
        preview.seek.setValue(300)
        self.wait_idle(window)
        self.assertEqual(preview.position_ms, 300)
        self.assertEqual(preview.displayed_value, 1.)

    def test_playback_quality_and_resolution_changes_do_not_prepare_sequence_again(self):
        window, panel, dialog = self.make_preview()
        self.prepare(window, dialog)
        session = dialog.preview.session
        requests = []
        dialog.preview_requested.connect(requests.append)
        with patch.object(session, 'prepare', side_effect=AssertionError('Timing must reuse the sequence')):
            dialog.hold_spin.setValue(.4)
            self.assertEqual(dialog.preview.duration_ms, 800)
            dialog.speed_spin.setValue(2)
            self.assertEqual(dialog.preview.duration_ms, 400)
            dialog.crf_spin.setValue(22)
            dialog.direction_combo.setCurrentIndex(dialog.direction_combo.findData('reverse'))
            self.wait_idle(window)
            self.assertEqual(dialog.preview.displayed_value, 1.)
            dialog.preview.pause()
            dialog.width_spin.setValue(840)
            dialog.height_spin.setValue(576)
            self.wait_idle(window)
            dialog.preview_btn.click()
            dialog.preview.pause()
            self.wait_idle(window)
        self.assertEqual(requests, [])
        self.assertTrue(dialog.preview.ready)

    def test_color_change_reuses_statistics_and_spectral_data(self):
        window, panel, dialog = self.make_preview()
        self.prepare(window, dialog)
        session = dialog.preview.session
        with patch.object(session, 'cut_factory', side_effect=AssertionError('Reuse already calculated spectra')):
            dialog.color_combo.setCurrentIndex(dialog.color_combo.findData('manual'))
            dialog.vmin_edit.setText('-10')
            dialog.vmax_edit.setText('100')
            self.assertFalse(dialog.preview.ready)
            self.assertIn('Settings changed', dialog.preview.status.text())
            self.prepare(window, dialog)
        self.assertEqual(dialog.preview.view['clim'], (-10., 100.))
        self.assertIs(dialog.preview.session, session)

    def test_slow_rendering_visits_all_slices_and_replay_uses_disk_images(self):
        import spectral_preview
        window, panel, dialog = self.make_preview()
        self.prepare(window, dialog)
        preview = dialog.preview
        dialog.hold_spin.setValue(.1)
        dialog.direction_combo.setCurrentIndex(dialog.direction_combo.findData('pingpong'))
        dialog.repeats_spin.setValue(2)
        preview.cache_budget = 1  # Force every revisited image out of the GUI cache.
        preview._clear_frames()
        render_frame = spectral_preview.render_frame
        def slow_render(*args):
            time.sleep(.25)
            return render_frame(*args)
        with patch('spectral_preview.render_frame', side_effect=slow_render) as render:
            for _ in range(2):
                preview.restart()
                observed = []
                deadline = time.monotonic() + 8
                while (preview._playing or preview.working) and time.monotonic() < deadline:
                    self.app.processEvents()
                    value = preview.displayed_value
                    if value is not None and (not observed or observed[-1] != value):
                        observed.append(value)
                    time.sleep(.005)
                self.assertFalse(preview._playing)
                self.assertEqual(observed, [0., 1., 0., 1., 0.])
                self.assertEqual(preview.position_ms, 600)
            self.assertEqual(render.call_count, 1)  # Slice0 was rendered during preparation.

    def test_close_during_preparation_cancels_and_waits_for_worker(self):
        window, panel, dialog = self.make_preview()
        dialog.preview_btn.click()
        dialog.close()
        self.assertTrue(dialog.isVisible())
        self.wait_idle(window)
        self.assertFalse(dialog.isVisible())
        self.assertEqual(list(self.root.rglob('*.mp4')), [])

    def test_cancel_preparation_keeps_settings_open_for_retry(self):
        window, panel, dialog = self.make_preview()
        dialog.preview_btn.click()
        dialog.preview.cancel_btn.click()
        self.wait_idle(window)
        self.assertTrue(dialog.isVisible())
        self.assertTrue(dialog.export_btn.isEnabled())
        self.assertIn('cancelled', dialog.preview.status.text())
        self.prepare(window, dialog)

    def test_failure_stays_visible_and_frame_cache_is_bounded(self):
        window, panel, dialog = self.make_preview()
        dialog.range_controls.restore(dict(x=dict(auto=False, min=100, max=101)))
        dialog.preview_btn.click()
        self.wait_idle(window)
        self.assertIn('No finite signal', dialog.preview.status.text())
        self.assertFalse(dialog.preview.play_btn.isEnabled())
        dialog.range_controls.restore({})
        self.prepare(window, dialog)
        preview = dialog.preview
        preview.cache_budget = 100
        preview._cache_image(99., QImage(420, 288, QImage.Format_RGB32))
        self.assertLessEqual(preview.cache_bytes, 100)

    def test_independent_movie_range_changes_update_preview_export_and_keep_png(self):
        window, panel, dialog = self.make_preview()
        panel.ranges.restore(dict(x=dict(auto=False, min=1.2, max=1.3),
                                  y=dict(auto=False, min=0., max=1.)))
        png_before = panel.ranges.recipe()
        panel.colors.auto.setChecked(False)
        panel.colors.lower.setText('0')
        panel.colors.upper.setText('100')
        panel.colors.upper.editingFinished.emit()
        png_colors_before = panel.colors.recipe()
        dialog.range_controls.restore(dict(x=dict(auto=False, min=1.16, max=1.32),
                                           y=dict(auto=False, min=-.2, max=1.2)))
        dialog.color_combo.setCurrentIndex(dialog.color_combo.findData('manual'))
        dialog.vmin_edit.setText('-5')
        dialog.vmax_edit.setText('80')
        self.prepare(window, dialog)
        self.assertEqual(dialog.preview.view['xlim'], (1.16, 1.32))
        self.assertEqual(dialog.preview.view['ylim'], (-.2, 1.2))
        self.assertEqual(dialog.preview.view['clim'], (-5., 80.))
        session = dialog.preview.session
        dialog.range_controls.controls['x'][1].setText('1.18')
        dialog.range_controls.controls['x'][2].editingFinished.emit()
        self.assertFalse(dialog.preview.ready)
        with patch.object(session, 'cut_factory', side_effect=AssertionError('Reuse calculated cuts')):
            self.prepare(window, dialog)
        self.assertEqual(dialog.preview.view['xlim'], (1.18, 1.32))
        panel.start_movie(dialog.configuration())
        self.wait_idle(window)
        info = json.loads(next(self.root.rglob('*.settings.json')).read_text(encoding='utf-8'))
        self.assertEqual(info['view']['xlim'], [1.18, 1.32])
        self.assertEqual(info['view']['clim'], [-5., 80.])
        self.assertEqual(panel.ranges.recipe(), png_before)
        self.assertEqual(panel.colors.recipe(), png_colors_before)
        self.assertEqual(list(self.root.rglob('*.png')), [])
        self.assertEqual(panel._movie_recipe['ranges']['x'], dict(auto=False, min=1.18, max=1.32))

    def test_export_while_uncached_frame_is_rendering_waits_then_keeps_new_timing(self):
        from PySide6.QtWidgets import QDialog
        window, panel, dialog = self.make_preview()
        self.prepare(window, dialog)
        dialog.hold_spin.setValue(.4)
        dialog.preview.seek.setValue(600)
        self.assertTrue(dialog.preview.working)
        dialog.export_btn.click()
        self.wait_idle(window)
        self.assertEqual(dialog.result(), QDialog.Accepted)
        panel.start_movie(dialog.configuration())
        self.wait_idle(window)
        info = json.loads(next(self.root.rglob('*.settings.json')).read_text(encoding='utf-8'))
        self.assertEqual(info['options']['hold'], .4)
        self.assertEqual(info['duration_s'], .8)

    def test_actual_create_dialog_uses_one_window_and_live_timing(self):
        window = self.window()
        self.load(window, self.csv)
        panel = window.spectral_slices_panel
        panel.extract()
        self.wait_idle(window)
        errors, observed = [], []
        timer = QTimer()
        timer.setInterval(20)
        deadline = time.monotonic() + 15
        def advance():
            modal = self.app.activeModalWidget()
            if not isinstance(modal, SpectralMovieDialog):
                return
            try:
                if errors or time.monotonic() > deadline:
                    timer.stop()
                    modal.reject()
                    if not errors:
                        errors.append('Preview did not become ready')
                    return
                self.assertIs(modal.preview.window(), modal)
                if not observed:
                    modal.width_spin.setValue(420)
                    modal.height_spin.setValue(288)
                    observed.append('requested')
                    modal.preview_btn.click()
                elif modal.preview.ready and not modal.preview.working:
                    modal.preview.pause()
                    modal.hold_spin.setValue(.5)
                    self.assertEqual(modal.preview.duration_ms, 1000)
                    modal.range_controls.modes['x'].setCurrentIndex(modal.range_controls.modes['x'].findData(False))
                    modal.range_controls.controls['x'][1].setText('1.2')
                    modal.range_controls.controls['x'][2].setText('1.3')
                    modal.range_controls.controls['x'][2].editingFinished.emit()
                    timer.stop()
                    modal.reject()
            except Exception as exc:
                errors.append(str(exc))
                modal.reject()
        timer.timeout.connect(advance)
        timer.start()
        panel.create_movie()
        timer.stop()
        self.wait_idle(window)
        self.assertEqual(errors, [])
        self.assertEqual(list(self.root.rglob('*.mp4')), [])
        self.assertEqual(panel._movie_recipe['ranges']['x'], dict(auto=False, min=1.2, max=1.3))
