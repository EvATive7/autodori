import json
import logging
import time
from pathlib import Path

from minitouchpy import CommandBuilder
from peewee import *
from playhouse.sqlite_ext import JSONField

import util
from api import BestdoriAPI
import yaml


class PlayRecord(Model):
    class Meta:
        database = SqliteDatabase("data/play_records.db")

    play_time = TimestampField()
    play_offset = JSONField()
    chart_id = CharField()
    difficulty = CharField()
    succeed = BooleanField()
    result = JSONField()


PlayRecord.create_table(safe=True)


class Chart:
    def __init__(self, id_and_difficulty: tuple[str, str] = None, song_name=None):
        self._id_, self._difficulty = id_and_difficulty
        self._song_name = song_name
        self._chart_name = f"{self._id_}-{self._difficulty}"
        self._chart_data = BestdoriAPI.get_chart(self._id_, self._difficulty)
        self._logger = logging.getLogger(self._chart_name)
        self._bpms = []
        self.actions = []
        self._commands = []
        self._total = len(self._chart_data)
        self._process_time_chart()

        self.actions_to_cmd_index = 0
        self._actions_to_cmd_offset = 0
        self._actions_to_cmd_rounded_loss = 0.0

    def _beat_to_time(self, beat: float) -> float:
        if not self._bpms:
            return 0

        def _get_time_for_section(
            bpm: float, previous_bpm_beat: float, current_bpm_beat: float
        ) -> float:
            return (current_bpm_beat - previous_bpm_beat) * (60.0 / bpm) if bpm else 0

        time_ = 0.0

        previous_bpm_beat = 0.0
        current_bpm = 0.0

        for bpm, bpm_beat in self._bpms:
            if bpm_beat > beat:
                break
            time_ += _get_time_for_section(current_bpm, previous_bpm_beat, bpm_beat)
            previous_bpm_beat = bpm_beat
            current_bpm = bpm

        time_ += _get_time_for_section(current_bpm, previous_bpm_beat, beat)

        return time_ * 1000

    def _process_time_chart(self):
        checkpoint_index = -1
        note_index = -1

        def get_checkpoint_index():
            nonlocal checkpoint_index
            checkpoint_index += 1
            return checkpoint_index

        def get_note_index():
            nonlocal note_index
            note_index += 1
            return note_index

        for _, note in enumerate(self._chart_data):
            note_type = note["type"]

            if note_type == "BPM":
                bpm = note["bpm"]
                beat = note["beat"]
                self._bpms.append((bpm, beat))
            elif note_type in ["Single", "Directional"]:
                note["time"] = self._beat_to_time(note["beat"])
                note["checkpoint_index"] = get_checkpoint_index()
                note["index"] = get_note_index()
            elif note_type in ["Slide", "Long"]:
                note["index"] = get_note_index()
                for connection in note["connections"]:
                    connection["time"] = self._beat_to_time(connection["beat"])
                    if not connection.get("hidden", False):
                        connection["checkpoint_index"] = get_checkpoint_index()
            else:
                self._logger.warning(
                    f"_chart_to_time_chart: Unknown type: {note_type}, Skipped"
                )
        self._logger.debug(
            f"_chart_to_time_chart: Succeed: {len(self._chart_data)} notes"
        )

    def notes_to_actions(
        self,
        screen_resolution: tuple[int, int],
        default_move_slice_size,
    ):
        notes: list[dict] = self._chart_data

        def get_lane_position(lane: int) -> tuple[int, int]:
            lane_config = util.get_runtime_info(screen_resolution)["lane"]
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

        def add_tap(note_index, from_time, duration, pos):
            finger = get_finger(from_time, from_time + duration)
            actions.extend(
                [
                    {
                        "finger": finger,
                        "type": "down",
                        "time": from_time,
                        "pos": pos,
                        "note": note_index,
                    },
                    {
                        "finger": finger,
                        "type": "up",
                        "time": from_time + duration,
                        "note": note_index,
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
            note_index,
            finger,
            from_time,
            duration,
            from_,
            to,
            slice_size=default_move_slice_size,
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
                        "note": note_index,
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
                        "note": note_index,
                    }
                )
            if up:
                result.append(
                    {
                        "finger": finger,
                        "type": "up",
                        "time": to_time,
                        "note": note_index,
                    },
                )
            actions.extend(result)

        for note in notes:
            note_data = note
            note_type = note_data["type"]
            note_index = note_data.get("index", None)

            if note_type == "Single":
                time_ = note_data["time"]
                from_lane = note_data["lane"]
                pos = get_lane_position(from_lane)

                if note_data.get("flick"):
                    finger = get_finger(time_, time_ + 80)
                    add_smooth_move(
                        note_index, finger, time_, 80, pos, (pos[0], pos[1] - 300)
                    )
                else:
                    add_tap(note_index, time_, 50, pos)

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
                    note_index,
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
                        "note": note_index,
                    }
                )

                end_pos = None

                for i, connection in enumerate(note_data["connections"]):
                    if i != len(note_data["connections"]) - 1:
                        next_connection = note_data["connections"][i + 1]
                        if connection["lane"] != next_connection["lane"]:
                            add_smooth_move(
                                note_index,
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
                        note_index,
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
                        "note": note_index,
                    }
                )
            else:
                logging.warning(f"notes_to_actions: Unknown type: {note_type}")

        actions.sort(key=lambda x: x["time"])
        actions: list[dict]

        actions_with_wait: list[dict] = []
        for i, action in enumerate(actions):
            actions_with_wait.append(action)
            if i != len(actions) - 1:
                current_time = action["time"]
                next_time = actions[i + 1]["time"]

                if next_time - current_time > 0.001:
                    actions_with_wait.append(
                        {
                            "type": "wait",
                            "time": current_time,
                            "length": next_time - current_time,
                        }
                    )
            else:
                pass

        [
            action.setdefault("index", index)
            for index, action in enumerate(actions_with_wait)
        ]
        self.actions = actions_with_wait

    def actions_to_MNTcmd(self, resolution, offset_info, size=50):
        self.command_builder = CommandBuilder()
        builder = self.command_builder
        actions = self.actions[
            self.actions_to_cmd_index : self.actions_to_cmd_index + size
        ]
        commands = self._commands

        up_offset = offset_info.get("up", 0)
        down_offset = offset_info.get("down", 0)
        move_offset = offset_info.get("move", 0)
        wait_offset = offset_info.get("wait", 0)
        interval_offset = offset_info.get("interval", 0)

        def append(command_to_append, action=None):
            commands.append(
                {
                    "command": command_to_append,
                    "action": action,
                }
            )

        def round_tuple(target):
            return tuple(round(x) for x in target)

        # append
        for i, action in enumerate(actions):
            action_type = action["type"]
            action_index = action["index"]

            self._actions_to_cmd_offset += interval_offset

            if action_type == "down":
                self._actions_to_cmd_offset += down_offset
                finger = action["finger"]
                append(
                    builder.down(
                        finger,
                        *util.androidxy_to_MNTxy(
                            round_tuple(action["pos"]), resolution
                        ),
                        0,
                    ),
                    action_index,
                )
            elif action_type == "move":
                self._actions_to_cmd_offset += move_offset
                finger = action["finger"]
                append(
                    builder.move(
                        finger,
                        *util.androidxy_to_MNTxy(round_tuple(action["to"]), resolution),
                        0,
                    ),
                    action_index,
                )

            elif action_type == "up":
                self._actions_to_cmd_offset += up_offset
                finger = action["finger"]
                append(builder.up(finger), action_index)

            elif action_type == "wait":
                self._actions_to_cmd_offset += wait_offset
                wait_for = action["length"]

                if self._actions_to_cmd_offset != 0:
                    adjust = min(wait_for, self._actions_to_cmd_offset, 2)
                    wait_for -= adjust
                    self._actions_to_cmd_offset -= adjust

                # TODO: clearer
                if self._actions_to_cmd_rounded_loss > 0:
                    wait_for += self._actions_to_cmd_rounded_loss
                    self._actions_to_cmd_rounded_loss -= (
                        self._actions_to_cmd_rounded_loss
                    )
                else:
                    rounded_loss_abs = abs(self._actions_to_cmd_rounded_loss)
                    if wait_for < rounded_loss_abs:
                        wait_for = 0
                        self._actions_to_cmd_rounded_loss += wait_for
                    else:
                        wait_for += self._actions_to_cmd_rounded_loss
                        self._actions_to_cmd_rounded_loss = 0

                rounded_waitfor = round(wait_for)
                self._actions_to_cmd_rounded_loss += wait_for - rounded_waitfor
                if rounded_waitfor > 0.01:
                    append(builder.commit())
                    append(builder.wait(rounded_waitfor))

        self.actions_to_cmd_index += size

    def dump_debug_config(self):
        dump_path = Path("debug/dump")
        dump_path.mkdir(parents=True, exist_ok=True)
        (
            dump_path / f"{self._song_name}-{self._difficulty}-{time.time()}.yml"
        ).write_text(
            yaml.safe_dump(
                {
                    "song_name": self._song_name,
                    "song_id": self._id_,
                    "chart": self._chart_data,
                    "actions": self.actions,
                    "commands": self._commands,
                },
                sort_keys=False,
                allow_unicode=True,
                indent=2,
            ),
            "utf-8",
        )
