"""Embedded, cached slice playback; MP4 encoding is reserved for export."""
from bisect import bisect_right
from collections import OrderedDict
import math
import time

from PySide6.QtCore import QSignalBlocker, Qt, QTimer, Signal, Slot
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QProgressBar,
                               QPushButton, QSizePolicy, QSlider, QVBoxLayout, QWidget)

from spectral_movie import MovieOptions, timeline
from spectral_preview import preview_dimensions


class VideoFrameLabel(QLabel):
    def __init__(self):
        super().__init__()
        self.setProperty('class', 'videoPreview')
        self.setAlignment(Qt.AlignCenter)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Expanding)
        self._frame = QPixmap()

    def set_image(self, image):
        if not image.isNull():
            self._frame = QPixmap.fromImage(image)
            self._scale_frame()

    def _scale_frame(self):
        if not self._frame.isNull():
            self.setPixmap(self._frame.scaled(self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._scale_frame()


class MoviePreviewWidget(QWidget):
    busy_changed = Signal(bool)
    job_changed = Signal(bool)
    idle = Signal()
    frame_requested = Signal(object)

    def __init__(self, poster=None, parent=None):
        super().__init__(parent)
        self.session = self.view = self.configuration = None
        self.ready = self.generating = self.working = False
        self._cancel = None
        self._cancelled = self._disposed = False
        self._playing = False
        self._revision = 0
        self.frames = OrderedDict()
        self.cache_bytes = 0
        self.cache_budget = 32 * 1024 * 1024
        self.position_ms = self.duration_ms = 0
        self.displayed_value = None
        self._segments, self._ends = [], []
        self._timer = QTimer(self)
        self._timer.setInterval(20)
        self._timer.timeout.connect(self._advance)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.status = QLabel('Current slice · click Preview for playback.' if poster is not None
                             else 'Click Preview for slice playback.')
        self.status.setWordWrap(True)
        self.status.setProperty('fluentRole', 'caption')
        layout.addWidget(self.status)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.hide()
        layout.addWidget(self.progress)
        self.video = VideoFrameLabel()
        self.video.setMinimumSize(280, 200)
        if poster is not None:
            self.video.set_image(poster)
        else:
            self.video.setText('Slice preview will appear here')
        layout.addWidget(self.video, 1)
        self.play_btn, self.restart_btn = QPushButton('Play'), QPushButton('Restart')
        self.seek = QSlider(Qt.Horizontal)
        self.seek.setAccessibleName('Preview playback position')
        self.seek.setRange(0, 0)
        self.time_label = QLabel('0.00 / 0.00 s')
        row = QHBoxLayout()
        for control in (self.play_btn, self.restart_btn, self.seek, self.time_label):
            row.addWidget(control)
        layout.addLayout(row)
        self.cancel_btn = QPushButton('Cancel preview preparation')
        self.cancel_btn.clicked.connect(self.cancel_generation)
        self.cancel_btn.hide()
        layout.addWidget(self.cancel_btn)
        self._set_playback_enabled(False)
        self.play_btn.clicked.connect(self.toggle_playback)
        self.restart_btn.clicked.connect(self.restart)
        self.seek.valueChanged.connect(self.set_position)

    @staticmethod
    def _visual_key(config):
        options = config['options']
        colors = config.get('colors', {})
        ranges = config.get('ranges', {})
        bounds = tuple((axis, ranges.get(axis, {}).get('auto', True),
                        None if ranges.get(axis, {}).get('auto', True)
                        else (ranges[axis]['min'], ranges[axis]['max'])) for axis in ('x', 'y'))
        return (tuple(config['values']), options['color_mode'],
                (colors.get('min'), colors.get('max')) if options['color_mode'] == 'manual' else None, bounds)

    def begin(self, configuration=None):
        if self.working:
            return
        self.pause()
        self.ready = False
        self._revision += 1
        self._clear_frames()
        self.configuration = configuration
        self.generating = self.working = True
        self._cancelled = False
        self.status.setText('Preparing shared ranges and colors · showing a still slice…')
        self.progress.setRange(0, 0)
        self.progress.show()
        self.cancel_btn.setEnabled(True)
        self.cancel_btn.show()
        self._set_playback_enabled(False)
        self.busy_changed.emit(True)
        self.job_changed.emit(True)

    def bind_worker(self, worker, thread):
        self._cancel = worker.cancel
        worker.movie_progress.connect(self.update_progress, Qt.QueuedConnection)
        worker.error.connect(self.generation_error, Qt.QueuedConnection)
        thread.finished.connect(self.generation_finished)

    def bind_frame_worker(self, worker, thread):
        self.working = True
        self._cancel = worker.cancel
        self.job_changed.emit(True)
        worker.error.connect(self.frame_error, Qt.QueuedConnection)
        thread.finished.connect(self.frame_finished)

    @Slot(int, int, str)
    def update_progress(self, current, total, message):
        if not self._cancelled:
            self.progress.setRange(0, total)
            self.progress.setValue(current)
            self.status.setText('Preparing preview · ' + message + '. Playback starts when ready.')

    @Slot(object)
    def movie_ready(self, payload):
        if self._cancelled or payload.get('cancelled'):
            return
        self.session, self.view = payload['session'], payload['view']
        self.options = MovieOptions(**payload['options'])
        self.ready = True
        self._cache_image(payload['value'], self._image(payload['image']))
        self._set_timeline()
        self._set_playback_enabled(True)
        self.restart()

    @staticmethod
    def _image(pixels):
        height, width, _ = pixels.shape
        return QImage(pixels.data, width, height, pixels.strides[0], QImage.Format_RGB888).copy()

    def _cache_image(self, value, image):
        key = (self._revision, value)
        previous = self.frames.pop(key, None)
        if previous is not None:
            self.cache_bytes -= previous.sizeInBytes()
        size = image.sizeInBytes()
        while self.frames and self.cache_bytes + size > self.cache_budget:
            _, previous = self.frames.popitem(last=False)
            self.cache_bytes -= previous.sizeInBytes()
        if size <= self.cache_budget:
            self.frames[key] = image
            self.cache_bytes += size
        return image

    def _clear_frames(self):
        self.frames.clear()
        self.cache_bytes = 0
        self.displayed_value = None

    @Slot(object)
    def frame_ready(self, payload):
        if payload.get('cancelled') or payload['revision'] != self._revision or not self.ready:
            return
        image = self._cache_image(payload['value'], self._image(payload['image']))
        if self._target_value() == payload['value']:
            self.video.set_image(image)
            self.displayed_value = payload['value']
            self.status.setText(self._playback_status)
            if self._playing:
                self._clock_start = time.monotonic() - self.position_ms / 1000

    @Slot(str)
    def generation_error(self, message):
        self.status.setText('Preview failed: ' + message.strip().splitlines()[-1])
        self.status.setToolTip(message)

    @Slot(str)
    def frame_error(self, message):
        self.pause()
        self.ready = False
        self._set_playback_enabled(False)
        self.generation_error(message)

    @Slot()
    def generation_finished(self):
        self.generating = self.working = False
        self._cancel = None
        self.progress.hide()
        self.cancel_btn.hide()
        if self._cancelled:
            self.invalidate()
            self.status.setText('Preview cancelled. Adjust settings or click Preview again.')
        self.busy_changed.emit(False)
        self.job_changed.emit(False)
        self.idle.emit()
        if self.ready:
            self._show_position()

    @Slot()
    def frame_finished(self):
        self.working = False
        self._cancel = None
        if self._cancelled:
            self.invalidate()
        self.job_changed.emit(False)
        self.idle.emit()
        if self.ready:
            self._show_position()

    @Slot()
    def cancel_generation(self):
        if self.working:
            self._cancelled = True
            self.pause()
            if self._cancel is not None:
                self._cancel.set()
            self.status.setText('Cancelling preview preparation…')
            self.cancel_btn.setEnabled(False)

    def invalidate(self):
        self.pause()
        if self._cancel is not None:
            self._cancel.set()
        self.ready = False
        self._revision += 1
        self._clear_frames()
        self._set_playback_enabled(False)
        self.status.setText('Settings changed · click Preview to update colors or slice selection.')

    def apply_configuration(self, configuration):
        if not self.ready:
            return False
        if self._visual_key(configuration) != self._visual_key(self.configuration):
            self.invalidate()
            return False
        if configuration != self.configuration:
            old_dimensions = preview_dimensions(self.options)
            self.configuration = configuration
            self.options = MovieOptions(**configuration['options'])
            if old_dimensions != preview_dimensions(self.options):
                self._revision += 1
                self._clear_frames()
            playing = self._playing
            self._set_timeline()
            self.set_position(0)
            if playing:
                self._clock_start = time.monotonic()
        return True

    def _set_timeline(self):
        self._segments = timeline(len(self.view['values']), self.options)
        self._ends = []
        total = 0
        for _, count in self._segments:
            total += count
            self._ends.append(total)
        self.duration_ms = round(total / self.options.fps * 1000)
        with QSignalBlocker(self.seek):
            self.seek.setRange(0, min(self.duration_ms, 2147483647))
        self._playback_status = (f"Preview · {len(self.view['values'])} slices · {total / self.options.fps:.2f} s"
                                + (f" · {len(self.view['skipped'])} slices skipped" if self.view['skipped'] else ''))
        self.status.setText(self._playback_status)

    def _target_value(self):
        frame = min(self._ends[-1] - 1, int(self.position_ms * self.options.fps / 1000))
        segment = bisect_right(self._ends, frame)
        return self.view['values'][self._segments[segment][0]]

    def _show_position(self):
        if not self.ready or self._disposed:
            return
        value = self._target_value()
        if self.displayed_value == value:
            return
        key = (self._revision, value)
        if key in self.frames:
            if self.displayed_value != value:
                self.video.set_image(self.frames[key])
                self.displayed_value = value
            self.frames.move_to_end(key)
        elif not self.working:
            self.status.setText(self._playback_status + ' · Loading slice image…')
            self.frame_requested.emit(dict(session=self.session, value=value, view=self.view,
                                           options=vars(self.options), revision=self._revision))

    @Slot(int)
    def set_position(self, position):
        self.position_ms = min(max(0, position), self.duration_ms)
        if self._playing:
            self._clock_start = time.monotonic() - self.position_ms / 1000
        with QSignalBlocker(self.seek):
            self.seek.setValue(self.position_ms)
        self.time_label.setText(f'{self.position_ms / 1000:.2f} / {self.duration_ms / 1000:.2f} s')
        self._show_position()

    def _advance(self):
        if not self.ready or not self._playing:
            return
        now = time.monotonic()
        if self.working or self.displayed_value != self._target_value():
            # Loading time must not consume a slice's playback time.
            self._clock_start = now - self.position_ms / 1000
            return
        frame = min(self._ends[-1] - 1, int(self.position_ms * self.options.fps / 1000))
        segment = bisect_right(self._ends, frame)
        boundary = math.ceil(self._ends[segment] / self.options.fps * 1000)
        # Even a delayed GUI timer must visit the next slice before advancing.
        position = min(round((now - self._clock_start) * 1000), boundary)
        self.set_position(position)
        if position >= self.duration_ms:
            self.pause()

    def pause(self):
        self._playing = False
        self._timer.stop()
        self.play_btn.setText('Play')

    @Slot()
    def toggle_playback(self):
        if self._playing:
            self.pause()
        elif self.ready:
            if self.position_ms >= self.duration_ms:
                self.set_position(0)
            self._playing = True
            self._clock_start = time.monotonic() - self.position_ms / 1000
            self._timer.start()
            self.play_btn.setText('Pause')

    @Slot()
    def restart(self):
        if self.ready:
            self.pause()
            self.set_position(0)
            self.toggle_playback()

    def dispose(self):
        self.pause()
        self._disposed = True
        self.ready = False
        if self.session is not None:
            self.session.close()
        self.session = self.view = None
        self._clear_frames()

    def _set_playback_enabled(self, enabled):
        for control in (self.play_btn, self.restart_btn, self.seek):
            control.setEnabled(enabled)
