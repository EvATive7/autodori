import hashlib
import json
import threading
import time
import tkinter as tk
from pathlib import Path
from time import sleep
from types import NoneType
from typing import Callable

import numpy as np
from PIL import Image, ImageTk

from mumuextras import PLAYER
import mumuextras
from util import MNTxy_to_androidxy, to_image


class SimulatorWindow:
    def __init__(self, width=1280, height=720):
        self.width = width
        self.height = height
        self.root = tk.Tk()
        self.root.title("Touch Simulator")

        self.canvas = tk.Canvas(self.root, width=self.width, height=self.height)
        self.canvas.pack()

        self.touch_data = (
            {}
        )  # Store touch commands and use the dictionary with contact as the key
        self.background_image_id = None

    def reset(self):
        """
        Reset all touch events
        """
        # print("Resetting touch events")
        self.canvas.delete("all")
        self.touch_data.clear()

    def touch_down(self, contact, x, y, pressure):
        """
        Handling touch down events
        """
        R = 30
        if contact not in self.touch_data:
            self.touch_data[contact] = self.canvas.create_oval(
                x - R, y - R, x + R, y + R, fill="red", outline="red"
            )

    def touch_move(self, contact, x, y, pressure):
        """
        Handling touch move events
        """

        R = 30
        if contact in self.touch_data:
            self.canvas.coords(self.touch_data[contact], x - R, y - R, x + R, y + R)

    def touch_up(self, contact):
        """
        Handle touch up events
        """
        if contact in self.touch_data:
            self.canvas.delete(self.touch_data[contact])
            del self.touch_data[contact]

    def update_image(self, image):
        """
        Update the image of the canvas (always at bottom layer)
        """

        photo = self._np_to_tkphoto(image)

        if self.background_image_id:
            self.canvas.delete(self.background_image_id)
        self.background_image_id = self.canvas.create_image(
            0, 0, image=photo, anchor=tk.NW
        )
        self.canvas.image = photo
        self.canvas.lower(self.background_image_id)

    def _np_to_tkphoto(self, np_array: np.ndarray):
        """
        Convert a numpy array to an image usable by tkinter
        """
        image = to_image(np_array, (1280, 720))
        return ImageTk.PhotoImage(image)

    def run(self):
        """
        launch window
        """
        self.root.mainloop()

    def destroy(self):
        """
        destroy window
        """
        self.root.destroy()


def parse_command(window: SimulatorWindow, command: str, resolution):
    """
    Parse and process every touch command
    """
    parts = command.split()
    if not parts:
        return

    action = parts[0]
    if action == "d":  # touch down
        contact, x, y, pressure = (
            int(parts[1]),
            float(parts[2]),
            float(parts[3]),
            int(parts[4]),
        )
        x, y = MNTxy_to_androidxy((x, y), resolution)
        window.touch_down(contact, x, y, pressure)
    elif action == "m":  # touch move
        contact, x, y, pressure = (
            int(parts[1]),
            float(parts[2]),
            float(parts[3]),
            int(parts[4]),
        )
        x, y = MNTxy_to_androidxy((x, y), resolution)
        window.touch_move(contact, x, y, pressure)
    elif action == "u":  # touch up
        contact = int(parts[1])
        window.touch_up(contact)
    elif action == "w":  # waiting
        wait_time = float(parts[1])
        sleep(wait_time / 1000)  # Convert to seconds
    else:
        pass


def update_cmd_worker(commands, window: SimulatorWindow):
    for cmd in commands:
        start_time = time.time()
        parse_command(window, cmd, PLAYER.resolution)
        end_time = time.time()
        print(f"Command {cmd} took {end_time - start_time:.4f} seconds")


def _start(commands, update_image_worker: Callable[[SimulatorWindow], NoneType]):
    window = SimulatorWindow()
    touch_thread = threading.Thread(target=update_cmd_worker, args=(commands, window))
    touch_thread.daemon = True
    touch_thread.start()

    image_thread = threading.Thread(target=update_image_worker, args=(window,))
    image_thread.daemon = True
    image_thread.start()

    window.run()


def launch_simulator(commands, player):
    def update_image_worker(window: SimulatorWindow):

        image = player.ipc_capture_display(mumuextras.DISPLAY_ID)
        window.update_image(image)
        window.root.after(20, update_image_worker, window)
        # time.sleep(1000 / 1000)

    _start([cmd["command"] for cmd in commands], update_image_worker)
