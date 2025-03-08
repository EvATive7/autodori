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

runtime_info = {
    "lane": {
        (1280, 720): {
            "w": 147,
            "start_x": 127,
            "h": 590,
        }
    },
    "wait_first": {
        (1280, 720): {
            "from": 510,
            "to": 535,
        }
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
    """
    计算图像指定行范围内颜色的平均值和标准差。

    该函数通过遍历指定行范围（从start_row到end_row，包含边界行），调用util.evaluate_row_color函数
    计算每一行的颜色平均值和标准差，然后汇总计算整个范围内颜色的平均值和标准差。

    参数:
    image_array: 图像数组，表示图像像素颜色信息的二维数组。
    start_row: 起始行号，表示计算颜色评价的行开始索引。
    end_row: 结束行号，表示计算颜色评价的行结束索引。

    返回值:
    avg_color: 指定行范围内颜色的平均值。
    std_color: 指定行范围内颜色的标准差。
    """
    # 初始化颜色平均值和标准差数组，用于累加每行的结果
    avg_color = np.zeros(4)
    std_color = np.zeros(4)

    # 遍历指定行范围
    for row_index in range(start_row, end_row + 1):
        # 调用工具函数计算当前行的颜色平均值和标准差
        avg_color_row, std_color_row = evaluate_row_color(image_array, row_index)
        # 累加每行的颜色平均值和标准差
        avg_color += np.array(avg_color_row)
        std_color += np.array(std_color_row)

    # 计算指定行范围内颜色的平均值和标准差
    avg_color /= end_row - start_row + 1
    std_color /= end_row - start_row + 1

    # 返回计算结果
    return avg_color, std_color


def resolution_to_xformat(resolution: tuple[int, int]):
    resolution_x, resolution_y = resolution
    return f"{resolution_x}x{resolution_y}"


def androidxy_to_MNTxy(android, resolution):
    android_x, android_y = android
    resolution_x, resolution_y = resolution
    return (int(resolution_y - android_y), int(android_x))


def MNTxy_to_androidxy(mnt, resolution):
    mnt_x, mnt_y = mnt
    resolution_x, resolution_y = resolution
    return (int(mnt_y), int(resolution_y - mnt_x))


def evaluate_row_color(image_array, row_index):
    """
    评估图像中某一行的颜色。
    :param image_array: 输入的图像数据，应该是形状为 (height, width, 4) 的 numpy 数组
    :param row_index: 需要评估的行索引
    :return: 返回该行的平均颜色 (R, G, B, A) 和标准差
    """
    # 获取指定行的数据，形状为 (width, 4)，即该行的所有像素
    row_data = image_array[row_index, :, :]

    # 分离出不同的颜色通道
    r = row_data[:, 0]  # 红色通道
    g = row_data[:, 1]  # 绿色通道
    b = row_data[:, 2]  # 蓝色通道
    a = row_data[:, 3]  # alpha透明度通道

    # 计算每个通道的平均值和标准差
    avg_r = np.mean(r)
    avg_g = np.mean(g)
    avg_b = np.mean(b)
    avg_a = np.mean(a)

    std_r = np.std(r)
    std_g = np.std(g)
    std_b = np.std(b)
    std_a = np.std(a)

    avg_color = (avg_r, avg_g, avg_b, avg_a)
    std_color = (std_r, std_g, std_b, std_a)

    return avg_color, std_color


def vflip(pixel_data: np.ndarray, width, height):
    pixel_data = pixel_data.reshape((height, width, 4))
    pixel_data = pixel_data[::-1]
    return pixel_data


def to_image(pixels: np.ndarray, resolution: tuple[int, int]):
    image = Image.frombuffer("RGBA", resolution, bytes(pixels))
    return image


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
