import json
import logging
import statistics
import time
from io import StringIO
from pathlib import Path

import numpy as np
import yaml
from minitouchpy import CommandBuilder
from PIL import Image


def get_runtime_info(resolution: tuple[int, int]):
    x_zoom_multiple = resolution[0] / 1280
    y_zoom_multiple = resolution[1] / 720

    def get_rounded_int_x(origin):
        return int(round(origin * x_zoom_multiple, 0))

    def get_rounded_int_y(origin):
        return int(round(origin * y_zoom_multiple, 0))

    return {
        "lane": {
            "w": get_rounded_int_x(147),
            "start_x": get_rounded_int_x(127),
            "h": get_rounded_int_y(590),
        },
        "wait_first": {
            "from": get_rounded_int_y(510),
            "to": get_rounded_int_y(535),
        },
    }


def display_cmds(commands):
    for cmd in commands:
        command: str = cmd["command"]
        log = command
        if command.startswith("w"):
            time.sleep(float(command.split(" ")[1]) / 1000)
        action = cmd.get("action")
        if action:
            log += f"({action['note']['index']})"
        logging.debug(log)


def get_color_eval_in_range(image_array, start_row, end_row):
    avg_color = np.zeros(3)
    std_color = np.zeros(3)

    for row_index in range(start_row, end_row + 1):
        avg_color_row, std_color_row = evaluate_row_color(image_array, row_index)
        avg_color += np.array(avg_color_row)
        std_color += np.array(std_color_row)

    avg_color /= end_row - start_row + 1
    std_color /= end_row - start_row + 1

    return avg_color, std_color


def evaluate_row_color(image_array, row_index):
    """
    评估图像中某一行的颜色（仅RGB）。
    :param image_array: 输入图像，应为 (height, width, 3) 的 numpy 数组
    :param row_index: 要评估的行索引
    :return: 返回该行的平均颜色 (R, G, B) 和标准差
    """
    row_data = image_array[row_index, :, :]  # 形状为 (width, 3)

    # 分离出 R、G、B 通道
    r, g, b = row_data[:, 0], row_data[:, 1], row_data[:, 2]

    avg_color = (np.mean(r), np.mean(g), np.mean(b))
    std_color = (np.std(r), np.std(g), np.std(b))

    return avg_color, std_color


def resolution_to_xformat(resolution: tuple[int, int]):
    resolution_x, resolution_y = resolution
    return f"{resolution_x}x{resolution_y}"


def androidxy_to_MNTxy(android, mnt_resolution: tuple[int, int], orientation: int):
    android_x, android_y = android
    resolution_x, resolution_y = mnt_resolution

    list_ = [-1] * 4
    list_[orientation] = android_x
    list_[orientation + 1] = android_y
    for i in range(len(list_)):
        if list_[i] == -1:
            if i == 0:
                list_[0] = resolution_x - list_[2]
            elif i == 1:
                list_[1] = resolution_y - list_[3]
            elif i == 2:
                list_[2] = resolution_x - list_[0]
            elif i == 3:
                list_[3] = resolution_y - list_[1]

    return (int(list_[0]), int(list_[1]))


def generate_function_call_str(function, args, kwargs):
    args_str = ", ".join(repr(arg) for arg in args)
    kwargs_str = ", ".join(f"{key}={repr(value)}" for key, value in kwargs.items())
    all_args_str = ", ".join(filter(None, [args_str, kwargs_str]))
    return f"{function.__name__}({all_args_str})"


class TestSpeedTimer:
    def __init__(self, test_function, args=(), kwargs={}):
        self.test_function = test_function
        self.args = args
        self.kwargs = kwargs
        self.execution_times = []
        self.result = None

    def do(self, count=5):
        for _ in range(count):
            start_time = time.time()
            try:
                self.result = self.test_function(*self.args, **self.kwargs)
            except Exception as e:
                self.result = e
            end_time = time.time()
            self.execution_times.append(end_time - start_time)

        self.print_stats(count)
        return self.result

    def print_stats(self, count):
        if self.execution_times:
            avg_time = statistics.mean(self.execution_times)
            median_time = statistics.median(self.execution_times)
            variance = (
                statistics.variance(self.execution_times)
                if len(self.execution_times) > 1
                else 0
            )
            stddev = (
                statistics.stdev(self.execution_times)
                if len(self.execution_times) > 1
                else 0
            )

            print(
                f"Speed test for: {generate_function_call_str(self.test_function, self.args,self.kwargs)}"
            )
            print("===========================")
            print(f"Total Tests: {count}")
            print(f"Average Time: {avg_time * 1000:.6f} ms")
            print(f"Median Time: {median_time * 1000:.6f} ms")
            print(f"Variance: {variance * 1000**2:.6f} ms^2")
            print(f"Standard Deviation: {stddev * 1000:.6f} ms")
            print(f"Min Time: {min(self.execution_times) * 1000:.6f} ms")
            print(f"Max Time: {max(self.execution_times) * 1000:.6f} ms")
