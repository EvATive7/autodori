import json
import logging
from pathlib import Path

from fuzzywuzzy import process as fzwzprocess
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

    def __init__(self, id_and_difficulty: tuple[str, str] = None):
        id_, difficulty = id_and_difficulty
        self.name = f"{id_}-{difficulty}"
        self._chart_data = BestdoriAPI.get_chart(id_, difficulty)
        self._logger = logging.getLogger(self.name)
        self._bpms = []
        self.time_chart = []
        self._total = len(self._chart_data)
        self._chart_to_time_chart()

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

    def _chart_to_time_chart(self):
        index = -1

        def get_index():
            nonlocal index
            index += 1
            return index

        for _, note in enumerate(self._chart_data):
            note_type = note["type"]

            if note_type == "BPM":
                bpm = note["bpm"]
                beat = note["beat"]
                note["index"] = get_index()
                self._bpms.append((bpm, beat))
            elif note_type in ["Single", "Directional"]:
                note["time"] = self._beat_to_time(note["beat"])
                note["index"] = get_index()
                self.time_chart.append(note)
            elif note_type in ["Slide", "Long"]:
                for connection in note["connections"]:
                    connection["time"] = self._beat_to_time(connection["beat"])
                    connection["index"] = get_index()
                self.time_chart.append(note)
            else:
                self._logger.warning(
                    f"_chart_to_time_chart: Unknown type: {note_type}, Skipped"
                )
        self._logger.debug(
            f"_chart_to_time_chart: Succeed: {len(self.time_chart)} notes"
        )
