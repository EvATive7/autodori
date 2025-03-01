import ctypes
import logging
from ctypes import wintypes
from pathlib import Path

import numpy as np
import yaml

import util

DISPLAY_ID = 0


class MuMuPlayer:
    def __init__(self, path: Path, index):
        _path = path
        _dll_path = path / "shell" / "sdk" / "external_renderer_ipc.dll"

        self._path = str(path.absolute())
        self._dll_path = str(_dll_path.absolute())
        self._index = index

        self._init_dll(self._dll_path)

        self._handle = None
        self.resolution = None
        self.ipc_connect()
        self.ipc_capture_display(DISPLAY_ID)  # 预热截图

    def _init_dll(self, library_path):
        self.dll = ctypes.CDLL(library_path)

        self.dll.nemu_connect.argtypes = [wintypes.LPCWSTR, ctypes.c_int]
        self.dll.nemu_connect.restype = ctypes.c_int

        self.dll.nemu_disconnect.argtypes = [ctypes.c_int]
        self.dll.nemu_disconnect.restype = None

        self.dll.nemu_get_display_id.argtypes = [
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
        ]
        self.dll.nemu_get_display_id.restype = ctypes.c_int

        self.dll.nemu_capture_display.argtypes = [
            ctypes.c_int,
            ctypes.c_uint,
            ctypes.c_int,
            ctypes.POINTER(ctypes.c_int),
            ctypes.POINTER(ctypes.c_int),
            ctypes.POINTER(ctypes.c_ubyte),
        ]
        self.dll.nemu_capture_display.restype = ctypes.c_int

        self.dll.nemu_input_text.argtypes = [
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_char_p,
        ]
        self.dll.nemu_input_text.restype = ctypes.c_int

        self.dll.nemu_input_event_touch_down.argtypes = [
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
        ]
        self.dll.nemu_input_event_touch_down.restype = ctypes.c_int

        self.dll.nemu_input_event_touch_up.argtypes = [ctypes.c_int, ctypes.c_int]
        self.dll.nemu_input_event_touch_up.restype = ctypes.c_int

        self.dll.nemu_input_event_key_down.argtypes = [
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
        ]
        self.dll.nemu_input_event_key_down.restype = ctypes.c_int

        self.dll.nemu_input_event_key_up.argtypes = [
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
        ]
        self.dll.nemu_input_event_key_up.restype = ctypes.c_int

        self.dll.nemu_input_event_finger_touch_down.argtypes = [
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
        ]
        self.dll.nemu_input_event_finger_touch_down.restype = ctypes.c_int

        self.dll.nemu_input_event_finger_touch_up.argtypes = [
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
        ]
        self.dll.nemu_input_event_finger_touch_up.restype = ctypes.c_int

    def ipc_connect(self):
        """Connect to the emulator."""
        self._handle = self.dll.nemu_connect(self._path, self._index)
        return self._handle > 0

    def ipc_disconnect(self):
        """Disconnect from the emulator."""
        if self._handle is not None:
            self.dll.nemu_disconnect(self._handle)
            self._handle = None

    def ipc_get_display_id(self, pkg, app_index=0):
        """Get display id for the package."""
        pkg = pkg.encode("utf-8")
        return self.dll.nemu_get_display_id(self._handle, pkg, app_index)

    def ipc_capture_display(self, display_id):
        """Capture the display pixels."""
        if not self.resolution:
            buffer_size = 0
        else:
            buffer_size = self.resolution[0] * self.resolution[1] * 4

        width = ctypes.c_int(0)
        height = ctypes.c_int(0)
        pixels = (ctypes.c_ubyte * buffer_size)()
        capture_result = self.dll.nemu_capture_display(
            self._handle,
            display_id,
            buffer_size,
            ctypes.byref(width),
            ctypes.byref(height),
            pixels,
        )

        if capture_result == 0:
            if not self.resolution:
                self.resolution = (width.value, height.value)
                return None
            else:
                pixels = np.frombuffer(pixels, dtype=np.uint8)
                pixel_data = util.vflip(pixels, *self.resolution)
                return pixel_data
        else:
            return None

    def ipc_input_text(self, text):
        """Send text input to the emulator."""
        return self.dll.nemu_input_text(self._handle, len(text), text.encode("utf-8"))

    def ipc_input_event_touch_down(self, display_id, x, y):
        """Simulate touch down event."""
        return self.dll.nemu_input_event_touch_down(self._handle, display_id, x, y)

    def ipc_input_event_touch_up(self, display_id):
        """Simulate touch up event."""
        return self.dll.nemu_input_event_touch_up(self._handle, display_id)

    def ipc_input_event_key_down(self, display_id, key_code):
        """Simulate key down event."""
        return self.dll.nemu_input_event_key_down(self._handle, display_id, key_code)

    def ipc_input_event_key_up(self, display_id, key_code):
        """Simulate key up event."""
        return self.dll.nemu_input_event_key_up(self._handle, display_id, key_code)

    def ipc_input_event_finger_touch_down(self, display_id, finger_id, x, y):
        """Simulate multi-touch finger press down."""
        return self.dll.nemu_input_event_finger_touch_down(
            self._handle, display_id, finger_id, int(x), int(y)
        )

    def ipc_input_event_finger_touch_up(self, display_id, finger_id):
        """Simulate multi-touch finger press up."""
        return self.dll.nemu_input_event_finger_touch_up(
            self._handle, display_id, finger_id
        )
