import json
import logging
from pathlib import Path
import time
import util

from fuzzywuzzy import process as fzwzprocess
from minitouchpy import CommandBuilder
from peewee import *
from playhouse.sqlite_ext import JSONField

from api import BestdoriAPI


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
        self._actions = []
        self._commands = []
        self.command_builder = CommandBuilder()
        self._total = len(self._chart_data)
        self._process_time_chart()

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

    def actions_to_MNTcmd(self, resolution, touch_offset, move_offset):
        builder = self.command_builder
        actions = self._actions
        commands = self._commands

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

        # time sort
        for i, actions_group in enumerate(actions_grouped):
            if i + 1 == len(actions_grouped):
                wait_for = 2000
            else:
                next_actiongroup = actions_grouped[i + 1]
                next_time = next_actiongroup["time"]
                current_time = actions_group["time"]
                wait_for = next_time - current_time
            actions_group["wait_for"] = wait_for

        rounded_loss = 0.0

        # append
        for i1, actions_group in enumerate(actions_grouped):

            for _, action in enumerate(actions_group["actions"]):
                action_type = action["type"]
                action_index = action["index"]
                finger = action["finger"]

                if action_type == "down":
                    offset += touch_offset
                    append(
                        builder.down(
                            finger,
                            *util.androidxy_to_MNTxy(
                                round_tuple(action["pos"]), resolution
                            ),
                            100,
                        ),
                        action_index,
                    )
                elif action_type == "move":
                    offset += move_offset
                    append(
                        builder.move(
                            finger,
                            *util.androidxy_to_MNTxy(
                                round_tuple(action["to"]), resolution
                            ),
                            100,
                        ),
                        action_index,
                    )

                elif action_type == "up":
                    append(builder.up(finger), action_index)

            append(builder.commit())

            if i1 == len(actions_grouped) - 1:
                append(builder.wait(2000))
            else:
                next_actiongroup = actions_grouped[i1 + 1]
                wait_for = actions_group["wait_for"]
                if offset != 0 and all(
                    [action["type"] == "down" for action in next_actiongroup["actions"]]
                ):
                    min_ = min(wait_for, offset)
                    wait_for -= min_
                    offset -= min_

                if abs(rounded_loss) >= 1 and all(
                    [action["type"] == "down" for action in next_actiongroup["actions"]]
                ):
                    if rounded_loss > 0:
                        wait_for += rounded_loss
                        rounded_loss -= rounded_loss
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

    def notes_to_actions(
        self,
        screen_resolution: tuple[int, int],
        default_move_slice_size,
    ):
        notes: list[dict] = self._chart_data

        def get_lane_position(lane: int) -> tuple[int, int]:
            lane_config = util.runtime_info["lane"][screen_resolution]
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
        [action.setdefault("index", index) for index, action in enumerate(actions)]
        self._actions = actions

    def dump_debug_config(self):
        dump_path = Path("debug/dump")
        dump_path.mkdir(parents=True, exist_ok=True)
        (
            dump_path / f"{self._song_name}-{self._difficulty}-{time.time()}.json"
        ).write_text(
            json.dumps(
                {
                    "song_name": self._song_name,
                    "song_id": self._id_,
                    "chart": self._chart_data,
                    "actions": self._actions,
                    "commands": self._commands,
                },
                indent=4,
                ensure_ascii=False,
            ),
            "utf-8",
        )
