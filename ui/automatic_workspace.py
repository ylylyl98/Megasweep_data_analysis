"""Schedule updates for the visible optical view using the existing worker."""
import os


class AutomaticWorkspaceMixin:
    def _setup_auto_updates(self):
        self._auto_update_active = True
        self._auto_update_closed = False
        self._preview_stale = False
        self.workspace_tabs.currentChanged.connect(self._visible_view_changed)
        self.transport_panel.active = lambda: self._auto_update_active and not self._auto_update_closed
        for controls in (self.map_updates, self.preview_updates):
            controls.preference_changed.connect(self._schedule_session_save)
        for spin in (self.reflection_preview_vbg_spin, self.reflection_preview_vtg_spin):
            spin.valueChanged.connect(self._request_preview_update)

    def _auto_file_matches(self):
        return bool(self.state.csv_path) and os.path.normcase(os.path.abspath(self.csv_edit.text().strip())) == os.path.normcase(os.path.abspath(self.state.csv_path))

    def _auto_update_allowed(self):
        return (getattr(self, '_auto_update_active', False) and not self._auto_update_closed
                and not getattr(self, '_restoring_session', False) and self._thread is None
                and self.state.mode in {'PL', 'Reflection'} and self.state.data is not None
                and self._auto_file_matches())

    def _can_auto_map(self):
        if not self._auto_update_allowed() or self.workspace_tabs.currentWidget() is not self.maps_workspace:
            return False
        key = self._current_view_key()
        if not self._dirty_views.get(key, True) and self._current_map_figure() is not None:
            return False
        if key.endswith('_transformed') and self.state.data.get('axis_space') == 'generic':
            return False
        if key.startswith(('ibias_', 'resistance_')):
            return self.state.data.get('ibias_data') is not None and (
                not key.startswith('resistance_') or self.state.data.get('vbias_data') is not None)
        return self.int_min_spin.value() < self.int_max_spin.value() and self._background_ready_for_auto()

    def _background_ready_for_auto(self):
        if self.state.mode != 'Reflection':
            return True
        background = self.state.background_spectra
        return background is not None and len(background) == self.state.data['Intensity'].shape[1] and (
            not self.background_scale_check.isChecked() or self.state.background_scale_factor is not None)

    def _can_auto_preview(self):
        return (self._auto_update_allowed() and self.state.mode == 'Reflection'
                and self._reflection_preview_message is not None and self._background_ready_for_auto()
                and self.int_min_spin.value() < self.int_max_spin.value()
                and self.workspace_tabs.currentWidget() is self.line_workspace)

    def _request_map_update(self):
        if hasattr(self, 'map_updates'):
            self.map_updates.request()

    def _request_preview_update(self, *_):
        if hasattr(self, 'preview_updates') and self._reflection_preview_message is not None:
            self._preview_stale = True
            self.line_plot_tab.set_export_enabled(False)
            self.reflection_preview_status_label.setText('Preview settings changed; previous plot is out of date. Update Now to apply, or enable Auto Update.')
            self.preview_updates.request()

    def _resume_auto_updates(self):
        if not hasattr(self, '_auto_update_closed') or self._auto_update_closed:
            return
        for controls in (self.map_updates, self.preview_updates, self.spectral_slices_panel.updates,
                         self.transport_panel.map_updates, self.transport_panel.cut_updates):
            controls.resume()

    def _visible_view_changed(self, *_):
        if not hasattr(self, '_auto_update_closed') or self._auto_update_closed:
            return
        current = self.workspace_tabs.currentWidget()
        if current is self.maps_workspace:
            self._request_map_update()
        elif current is self.spectral_slices_panel:
            if self.spectral_slices_panel._stale:
                self.spectral_slices_panel.updates.request()
        self._resume_auto_updates()

    def set_auto_update_active(self, active):
        self._auto_update_active = bool(active)
        if active:
            self._visible_view_changed()
        else:
            for controls in (self.map_updates, self.preview_updates, self.spectral_slices_panel.updates,
                             self.transport_panel.map_updates, self.transport_panel.cut_updates):
                controls.timer.stop()

    def _stop_auto_updates(self):
        self._auto_update_closed = True
        self._cancel_auto_updates()

    def _cancel_auto_updates(self):
        for controls in (self.map_updates, self.preview_updates, self.spectral_slices_panel.updates,
                         self.transport_panel.map_updates, self.transport_panel.cut_updates):
            controls.cancel()
