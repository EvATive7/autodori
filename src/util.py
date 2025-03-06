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
TIME_BETWEEN_FIRSTNOTE_DETECTED_TO_LANE = 30
WAITSTART_THRESHOLD = 0.8
SLICE_SIZE = 30


def actions_to_MNTcmd(commands, actions, resolution, touch_offset, move_offset):
    builder = CommandBuilder()

    def append(command_to_append, action=None):
        commands.append(
            {
                "command": command_to_append,
                "action": action,
            }
        )

    def round_tuple(target):
        return tuple(round(x) for x in target)

    offset = 0

    # classification
    actions_grouped = []
    for action in actions:
        time_ = action["time"]
        if len(actions_grouped) != 0:
            last_time = actions_grouped[-1]["time"]
        else:
            last_time = -1
        if last_time != time_:
            actions_grouped.append({"time": time_, "actions": [action]})
        else:
            actions_grouped[-1]["actions"].append(action)

    rounded_loss = 0.0

    # append
    for i1, actions_group in enumerate(actions_grouped):
        time_ = actions_group["time"]

        for _, action in enumerate(actions_group["actions"]):
            action_type = action["type"]
            finger = action["finger"]

            if action_type == "down":
                offset += touch_offset
                append(
                    builder.down(
                        finger,
                        *androidxy_to_MNTxy(round_tuple(action["pos"]), resolution),
                        100,
                    ),
                    action,
                )
            elif action_type == "move":
                offset += move_offset
                append(
                    builder.move(
                        finger,
                        *androidxy_to_MNTxy(round_tuple(action["to"]), resolution),
                        100,
                    ),
                    action,
                )

            elif action_type == "up":
                append(builder.up(finger), action)

        append(builder.commit())

        if i1 == len(actions_grouped) - 1:
            append(builder.wait(2000))
            append(builder.commit())
        else:
            next_actiongroup = actions_grouped[i1 + 1]
            nexttime = next_actiongroup["time"]
            wait_for = nexttime - time_
            if offset != 0 and all(
                [action["type"] == "down" for action in next_actiongroup["actions"]]
            ):
                min_ = min(wait_for, offset)
                wait_for -= min_
                offset -= min_

            if abs(rounded_loss) > 0.1 and all(
                [action["type"] == "down" for action in next_actiongroup["actions"]]
            ):
                if rounded_loss > 0:
                    wait_for += rounded_loss
                else:
                    rounded_loss_abs = abs(rounded_loss)
                    if wait_for < rounded_loss_abs:
                        wait_for = wait_for - wait_for
                        rounded_loss += wait_for
                    else:
                        wait_for += rounded_loss
                        rounded_loss = rounded_loss - rounded_loss

            rounded_waitfor = round(wait_for)
            rounded_loss += wait_for - rounded_waitfor
            if rounded_waitfor > 0.01:
                append(builder.wait(rounded_waitfor))
                append(builder.commit())
    return builder


def notes_to_actions(notes: list[dict], screen_resolution: tuple[int, int]):
    def get_lane_position(lane: int) -> tuple[int, int]:
        lane_config = runtime_info["lane"][screen_resolution]
        return (
            lane_config["start_x"] + (lane + 0.5) * lane_config["w"],
            lane_config["h"],
        )

    actions = []
    available_fingers = [
        {
            "id": i,
            "occupied_time": [],
        }
        for i in range(1, 6)
    ]

    def get_finger(from_time, to_time) -> int:
        for finger in available_fingers:
            if any(
                [
                    occupied_from <= from_time <= occupied_to
                    for occupied_from, occupied_to in finger["occupied_time"]
                ]
            ):
                continue
            else:
                finger["occupied_time"].append((from_time, to_time))
                return finger["id"]
        return None

    def add_tap(notedata, from_time, duration, pos):
        finger = get_finger(from_time, from_time + duration)
        actions.extend(
            [
                {
                    "finger": finger,
                    "type": "down",
                    "time": from_time,
                    "pos": pos,
                    "note": notedata,
                },
                {
                    "finger": finger,
                    "type": "up",
                    "time": from_time + duration,
                    "note": notedata,
                },
            ]
        )

    def split_number(num, part_size):
        result = []
        cur = 0
        while True:
            if num - cur > part_size:
                result.append((cur, part_size))
                cur += part_size
            else:
                result.append((cur, num - cur))
                break
        return result

    def add_smooth_move(
        note,
        finger,
        from_time,
        duration,
        from_,
        to,
        slice_size=SLICE_SIZE,
        down=True,
        up=True,
    ):
        to_time = from_time + duration
        from_x, from_y = from_
        to_x, to_y = to
        slices = split_number(duration, slice_size)
        x_size = (to_x - from_x) / duration
        y_size = (to_y - from_y) / duration

        result = []
        if down:
            result.append(
                {
                    "finger": finger,
                    "type": "down",
                    "time": from_time,
                    "pos": from_,
                    "note": note,
                }
            )
        for i, (cur_slice_start, cur_slice_size) in enumerate(slices):
            result.append(
                {
                    "finger": finger,
                    "type": "move",
                    "time": 0.00001 + from_time + cur_slice_start,
                    "to": (
                        from_x + x_size * (cur_slice_size + cur_slice_start),
                        from_y + y_size * (cur_slice_size + cur_slice_start),
                    ),
                    "note": note,
                }
            )
        if up:
            result.append(
                {
                    "finger": finger,
                    "type": "up",
                    "time": to_time,
                    "note": note,
                },
            )
        actions.extend(result)

    for note in notes:
        note_data = note
        note_type = note_data["type"]

        if note_type == "Single":
            time_ = note_data["time"]
            from_lane = note_data["lane"]
            pos = get_lane_position(from_lane)

            if note_data.get("flick"):
                finger = get_finger(time_, time_ + 80)
                add_smooth_move(
                    note_data, finger, time_, 80, pos, (pos[0], pos[1] - 300)
                )
            else:
                add_tap(note_data, time_, 50, pos)

        elif note_type == "Directional":
            time_ = note_data["time"]
            fromlane = note_data["lane"]
            width = note_data["width"]
            direction = note_data["direction"]
            if direction == "Right":
                tolane = fromlane + width
            else:
                tolane = fromlane - width
            finger = get_finger(time_, time_ + 80)

            add_smooth_move(
                note_data,
                finger,
                time_,
                80,
                get_lane_position(fromlane),
                get_lane_position(tolane),
            )
        elif note_type in ["Long", "Slide"]:
            from_lane = note_data["connections"][0]["lane"]
            from_pos = get_lane_position(from_lane)
            from_time = note_data["connections"][0]["time"]
            to_time = note_data["connections"][-1]["time"]

            end_flick = note_data["connections"][-1].get("flick")
            if end_flick:
                finger_end_time = to_time + 80
            else:
                finger_end_time = to_time
            finger = get_finger(
                from_time,
                finger_end_time,
            )
            actions.append(
                {
                    "finger": finger,
                    "type": "down",
                    "time": from_time,
                    "pos": from_pos,
                    "note": note_data,
                }
            )

            end_pos = None

            for i, connection in enumerate(note_data["connections"]):
                if i != len(note_data["connections"]) - 1:
                    next_connection = note_data["connections"][i + 1]
                    if connection["lane"] != next_connection["lane"]:
                        add_smooth_move(
                            note_data,
                            finger,
                            connection["time"],
                            next_connection["time"] - connection["time"],
                            get_lane_position(connection["lane"]),
                            get_lane_position(next_connection["lane"]),
                            down=False,
                            up=False,
                        )
                else:
                    end_pos = get_lane_position(connection["lane"])

            if end_flick:
                add_smooth_move(
                    note_data,
                    finger,
                    to_time,
                    80,
                    end_pos,
                    (end_pos[0], end_pos[1] - 300),
                    down=False,
                    up=False,
                )
            actions.append(
                {
                    "finger": finger,
                    "type": "up",
                    "time": finger_end_time,
                    "note": note_data,
                }
            )
        else:
            logging.warning(f"notes_to_actions: Unknown type: {note_type}")

    actions.sort(key=lambda x: x["time"])
    return actions


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
