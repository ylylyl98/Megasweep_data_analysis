import threading
import unittest
from unittest.mock import patch
import numpy as np

from spectral_movie import MovieOptions, resolve_sequence_view
from tests.test_spectral_movie import cut


class SpectralPreviewTests(unittest.TestCase):
    def test_shared_statistics_extract_once_and_reuse_across_color_changes(self):
        from spectral_preview import SpectralPreviewSession
        calls = []
        def factory(value):
            calls.append(value)
            return cut(value)
        session = SpectralPreviewSession(factory)
        self.addCleanup(session.close)
        options = MovieOptions(width=420, height=288)
        with patch('spectral_movie.find_ffmpeg', side_effect=AssertionError('Preview must not encode')):
            first = session.prepare([0., 1., 2.], options, {}, {})
            self.assertEqual(calls, [0., 1., 2.])
            self.assertEqual(first['view']['clim'], resolve_sequence_view(cut, [0., 1., 2.])['clim'])
            second = session.prepare([0., 1., 2.], MovieOptions(width=420, height=288,
                                     color_mode='manual'), {}, dict(min=-5, max=10))
            self.assertEqual(calls, [0., 1., 2.])
            self.assertEqual(second['view']['clim'], (-5., 10.))
            session.prepare([1., 2.], options, {}, {})
            self.assertEqual(calls, [0., 1., 2.])

    def test_preview_bounds_resolution_and_cut_cache_memory(self):
        from spectral_preview import SpectralPreviewSession
        session = SpectralPreviewSession(cut, cut_budget=100)
        self.addCleanup(session.close)
        result = session.prepare([0., 1.], MovieOptions(width=2800, height=1920), {}, {})
        self.assertEqual(result['image'].shape, (658, 960, 3))
        self.assertLessEqual(session.cut_bytes, 100)

    def test_cancellation_does_not_return_prepared_frames(self):
        from spectral_preview import SpectralPreviewSession
        from spectral_movie import MovieCancelled
        cancel = threading.Event()
        cancel.set()
        session = SpectralPreviewSession(cut)
        self.addCleanup(session.close)
        with self.assertRaises(MovieCancelled):
            session.prepare([0.], MovieOptions(), {}, {}, cancel=cancel)

    def test_cut_cache_counts_all_arrays_and_does_not_retain_larger_backing_buffers(self):
        from spectral_preview import SpectralPreviewSession
        def factory(value):
            result = cut(value)
            raw = np.zeros((20, 4))
            result.update(spectra=raw[:, 2:], energy=np.arange(2.),
                          axis_values=np.arange(20.), x_sel=np.arange(20.), y_sel=np.arange(20.))
            return result
        session = SpectralPreviewSession(factory, cut_budget=1000)
        self.addCleanup(session.close)
        session.get_cut(0.)
        session.get_cut(1.)
        retained = sum(array.nbytes for cached, _ in session.cuts.values()
                       for array in cached.values() if isinstance(array, np.ndarray))
        self.assertEqual(session.cut_bytes, retained)
        self.assertLessEqual(retained, 1000)
        for cached, _ in session.cuts.values():
            self.assertTrue(cached['spectra'].flags.owndata)

    def test_rendered_images_survive_memory_eviction_and_timing_changes(self):
        from spectral_preview import SpectralPreviewSession
        from dataclasses import replace
        session = SpectralPreviewSession(cut, cut_budget=100)
        self.addCleanup(session.close)
        options = MovieOptions(width=420, height=288)
        view = resolve_sequence_view(cut, [0., 1.])
        with patch('spectral_preview.render_frame', wraps=__import__('spectral_movie').render_frame) as render:
            first = session.frame(0., view, options)
            session.frame(1., view, options)
            with patch.object(session, 'cut_factory', side_effect=AssertionError('Use rendered cache')):
                again = session.frame(0., view, replace(options, hold=.5, speed=2, crf=25))
            self.assertTrue(np.array_equal(first, again))
            self.assertEqual(render.call_count, 2)
            session.frame(0., dict(view, clim=(-20., 100.)), options)
            self.assertEqual(render.call_count, 3)
        cache_path = session.frame_directory.name
        session.close()
        from pathlib import Path
        self.assertFalse(Path(cache_path).exists())

    def test_disk_image_cache_stays_within_budget(self):
        from spectral_preview import SpectralPreviewSession
        session = SpectralPreviewSession(cut, frame_budget=1)
        self.addCleanup(session.close)
        session.prepare([0., 1.], MovieOptions(width=420, height=288), {}, {})
        self.assertEqual(session.frame_bytes, 0)
        self.assertEqual(list(__import__('pathlib').Path(session.frame_directory.name).iterdir()), [])
