import datetime
import json
import logging
import os
import random
import re
import string
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Optional, Union

data_path = Path("data")
data_path.mkdir(exist_ok=True)
cache_path = Path("cache")
cache_path.mkdir(exist_ok=True)
Path("debug").mkdir(exist_ok=True)


import numpy as np
from fuzzywuzzy import process as fzwzprocess
from maa.context import Context
from maa.custom_action import CustomAction, CustomRecognitionResult
from maa.custom_recognition import CustomRecognition
from maa.define import RectType
from maa.agent.agent_server import AgentServer
from minitouchpy import (
    MNT,
    MNTEvATive7LogEventData,
    MNTEvent,
    MNTEventData,
    MNTServerCommunicateType,
)

import player
from api import BestdoriAPI
from chart import Chart, PlayRecord
from util import *

OFFSET = {"up": 0, "down": 0, "move": 0, "wait": 0.0, "interval": 0.0}
PHOTOGATE_LATENCY = 30
DEFAULT_MOVE_SLICE_SIZE = 10
MAX_FAILED_TIMES = 10
CMD_SLICE_SIZE = 100

current_player: player.Player = None
current_orientation: int = 0
mnt: MNT = None
adb_path: Path | None = None
device_address: str | None = None
all_songs: dict = BestdoriAPI.get_song_list()
all_song_name_indexes: dict[str, str] = {
    list(filter(lambda title: title is not None, sinfo["musicTitle"]))[0]: sid
    for sid, sinfo in all_songs.items()
}
current_song_name: str = None
current_song_id: str = None
current_chart: Chart = None
play_failed_times: int = 0
callback_data: dict = {}
callback_data_lock = threading.Lock()
current_difficulty = "hard"


def reset_callback_data():
    global callback_data
    callback_data = {
        "wait": {"total": 0, "total_offset": 0.0},
        "move": {"uncommited": 0, "total": 0, "total_offset": 0.0},
        "up": {"uncommited": 0, "total": 0, "total_offset": 0.0},
        "down": {"uncommited": 0, "total": 0, "total_offset": 0.0},
        "interval": {"total": 0, "total_offset": 0.0},
        "last_cmd_endtime": -1,
    }


reset_callback_data()


def check_song_available(name, id_, difficulty):
    if name.startswith("[FULL]"):
        return False

    lastmatched = PlayRecord.get_or_none(chart_id=id_, difficulty=difficulty)
    if lastmatched:
        if not lastmatched.succeed:
            return True

    return True


@AgentServer.custom_recognition("SongRecognition")
class SongRecognition(CustomRecognition):
    def analyze(
        self, context: Context, argv: CustomRecognition.AnalyzeArg
    ) -> Union[CustomRecognition.AnalyzeResult, Optional[RectType]]:

        roi = [200, 332, 368, 29]

        def match(model=None):
            pplname = "_ocrsong_" + "".join(random.choices(string.ascii_lowercase, k=7))
            pipeline = {
                pplname: {
                    "recognition": "OCR",
                    "only_rec": True,
                    "roi": roi,
                },
            }
            if model != None:
                pipeline[pplname]["model"] = model
            try:
                song_fuzzyname = context.run_recognition(
                    pplname,
                    argv.image,
                    pipeline,
                ).best_result.text
            except:
                song_fuzzyname = ""
            return fuzzy_match_song(song_fuzzyname)

        jpmatch = match("ppocr_v3/ja_jp")
        commonmatch = match()  # , "ppocr_v4/zh_cn")
        logging.debug(
            "Match result with ppocr_v3/ja_jp: {}, Match result with default: {}".format(
                jpmatch, commonmatch
            )
        )
        result = sorted([jpmatch, commonmatch], key=lambda x: x[1], reverse=True)
        if all([r[1] < 50 for r in result]):
            return CustomRecognition.AnalyzeResult(None, "")
        result_music_name = result[0][0]

        params = json.loads(argv.custom_recognition_param or "{}")
        global current_difficulty
        current_difficulty = params.get("difficulty", "hard")

        if not check_song_available(
            result_music_name, all_song_name_indexes[result_music_name], current_difficulty
        ):
            return CustomRecognition.AnalyzeResult(None, "")

        return CustomRecognition.AnalyzeResult(roi, result_music_name)


@AgentServer.custom_recognition("LiveBoostEnoughRecognition")
class LiveBoostEnoughRecognition(CustomRecognition):
    def analyze(
        self, context: Context, argv: CustomRecognition.AnalyzeArg
    ) -> Union[CustomRecognition.AnalyzeResult, Optional[RectType]]:
        # roi = [970, 29, 39, 21]
        roi = [979, 30, 61, 20]

        pipeline = {
            "live_boost_enough_ocr": {
                "recognition": "OCR",
                "only_rec": True,
                "roi": roi,
            },
        }
        live_boost = context.run_recognition(
            "live_boost_enough_ocr",
            argv.image,
            pipeline,
        ).best_result.text

        logging.debug("Live boost rec result: {}".format(live_boost))
        pattern = r"^\s*(\d+)\s*/"
        match = re.match(pattern, live_boost.replace(" ", ""))

        if match:
            try:
                live_boost = int(match.group(1))
            except:
                live_boost = -1
        else:
            live_boost = -1

        logging.debug("Live boost: {}".format(live_boost))
        return CustomRecognition.AnalyzeResult(roi, str(live_boost))


@AgentServer.custom_action("HandleLiveBoost")
class HandleLiveBoost(CustomAction):
    def run(self, context: Context, argv: CustomAction.RunArg):
        liveboost = int(argv.reco_detail.best_result.detail)
        params = json.loads(argv.custom_action_param or "{}")
        minimum = int(params.get("minimum", 1))
        if liveboost < minimum:
            logging.debug("Live boost not enough, ready to exit")
            context.run_action("close_app")
            context.run_action("stop")
        return CustomAction.RunResult(True)


@AgentServer.custom_recognition("PlayResultRecognition")
class PlayResultRecognition(CustomRecognition):
    def analyze(
        self, context: Context, argv: CustomRecognition.AnalyzeArg
    ) -> Union[CustomRecognition.AnalyzeResult, Optional[RectType]]:

        types = {
            "score": {
                "roi": [1028, 192, 144, 35],
            },
            "maxcombo": {
                "roi": [1009, 391, 91, 28],
            },
            "perfect": {
                "roi": [829, 282, 90, 28],
            },
            "great": {
                "roi": [828, 322, 91, 27],
            },
            "good": {
                "roi": [829, 363, 91, 27],
            },
            "bad": {
                "roi": [829, 401, 90, 27],
            },
            "miss": {
                "roi": [830, 438, 91, 28],
            },
            "fast": {
                "roi": [1088, 283, 90, 27],
            },
            "slow": {
                "roi": [1088, 323, 91, 28],
            },
        }
        result = {type_: {} for type_ in types.keys()}
        pipeline = {
            f"_PlayResultRecognition_ocr_{type_}": {
                "recognition": "OCR",
                "only_rec": True,
                "roi": type_value["roi"],
            }
            for type_, type_value in types.items()
        }
        for type_, _ in types.items():
            try:
                ocrtext = context.run_recognition(
                    f"_PlayResultRecognition_ocr_{type_}",
                    argv.image,
                    pipeline,
                ).best_result.text
                type_result = int(ocrtext)
            except:
                type_result = -1
            result[type_] = type_result

        logging.debug("Play result: {}".format(result))
        return CustomRecognition.AnalyzeResult([0, 0, 0, 0], json.dumps(result))


@AgentServer.custom_action("SavePlayResult")
class SavePlayResult(CustomAction):
    def run(self, context: Context, argv: CustomAction.RunArg):
        try:
            global current_song_id, play_failed_times
            succeed: bool = json.loads(argv.custom_action_param).get("succeed")
            if succeed:
                playresult = argv.reco_detail.best_result.detail
                if isinstance(playresult, str):
                    playresult = json.loads(argv.reco_detail.best_result.detail)
            else:
                play_failed_times += 1
                playresult = {}
            PlayRecord.create(
                play_time=int(time.time()),
                play_offset=OFFSET,
                result=playresult,
                succeed=succeed,
                chart_id=current_song_id,
                difficulty=current_difficulty,
            )
            if play_failed_times >= MAX_FAILED_TIMES:
                logging.error("Failed attempts exceed max failed times")
                context.run_action("close_app")
                context.run_action("stop")
            return CustomAction.RunResult(True)
        except Exception as e:
            logging.error(f"Failed to save play result: {e}")
            return CustomAction.RunResult(False)


@AgentServer.custom_action("Play")
class Play(CustomAction):
    def run(self, context: Context, argv: CustomAction.RunArg):
        try:
            if mnt is None:
                init_player_and_mnt()
            play_song()
            return CustomAction.RunResult(True)
        except Exception as e:
            logging.error(f"Failed when play song: {e}", stack_info=True)
            return CustomAction.RunResult(False)


@AgentServer.custom_action("SaveSong")
class SaveSong(CustomAction):
    def run(self, context: Context, argv: CustomAction.RunArg):
        name: CustomRecognitionResult = argv.reco_detail.best_result.detail
        save_song(name)
        return CustomAction.RunResult(True)


def fuzzy_match_song(name):
    return fzwzprocess.extractOne(name, list(all_song_name_indexes.keys()))


def _get_orientation():
    """
    0, 1, 2, 3
    0: 0°
    1: 90°
    2: 180°
    3: 270°
    """
    try:
        command_list = [
            str(adb_path),
            "-s",
            device_address,
            "shell",
            "dumpsys input|grep SurfaceOrientation",
        ]

        logging.debug(
            "get SurfaceOrientation command: {}".format(" ".join(command_list))
        )
        output = subprocess.check_output(command_list, text=True)
        match = re.search(r"SurfaceOrientation:\s*(\d+)", output)
        orientation = int(match.group(1))
        logging.debug("SurfaceOrientation: {}".format(orientation))
        return orientation
    except Exception as e:
        logging.error(f"Failed to get SurfaceOrientation: {e}")
        return 0


def save_song(name):
    global current_song_name, current_song_id, current_chart, current_orientation
    current_song_name = name
    current_song_id = all_song_name_indexes[current_song_name]
    current_chart = Chart((current_song_id, current_difficulty), current_song_name)
    current_chart.notes_to_actions(current_player.resolution, DEFAULT_MOVE_SLICE_SIZE)
    current_orientation = _get_orientation()
    current_chart.actions_to_MNTcmd(
        (mnt.max_x, mnt.max_y), current_orientation, OFFSET, CMD_SLICE_SIZE
    )
    logging.debug("Save song: {}".format(name))


def play_song():
    logging.info("Start play")
    reset_callback_data()

    def _get_wait_time():
        wait_for = 0.0
        index = current_chart.actions_to_cmd_index
        for action in current_chart.actions[index - CMD_SLICE_SIZE : index]:
            if action["type"] == "wait":
                wait_for += action["length"]
        return wait_for

    def _adjust_offset():
        global callback_data
        total_cost = 0.0
        for type_ in ["up", "down", "move", "wait", "interval"]:
            type_data = callback_data[type_]
            total = type_data["total"]
            if total != 0:
                total_cost += type_data["total_offset"] - OFFSET[type_] * total
                OFFSET[type_] = type_data["total_offset"] / total

        current_chart._a2c_offset += total_cost
        logging.debug("Adjust offset: {}".format(OFFSET))
        logging.debug("Adjust _actions_to_cmd_offset: {}".format(total_cost))

    wait_first_note()

    while True:
        current_chart.command_builder.publish(mnt, block=False)
        wait_time = _get_wait_time()
        time.sleep(max(0, wait_time - 3) / 1000)

        index = current_chart.actions_to_cmd_index
        if current_chart.actions[index : index + CMD_SLICE_SIZE]:
            with callback_data_lock:
                _adjust_offset()
                reset_callback_data()
            current_chart.actions_to_MNTcmd(
                (mnt.max_x, mnt.max_y), current_orientation, OFFSET, CMD_SLICE_SIZE
            )
        else:
            break
    time.sleep(2)


def wait_first_note():
    last_color = None
    waited_frames = 0
    info = get_runtime_info(current_player.resolution)["wait_first"]
    from_row, to_row = info["from"], info["to"]
    freezed = False

    while True:
        try:
            screen = current_player.ipc_capture_display()
            cur_color, _ = get_color_eval_in_range(screen, from_row, to_row)

            if last_color is not None:
                change_score = np.sum(cur_color[0:3] - last_color[0:3])
                logging.debug(f"Picture changed: {change_score}")
                if change_score > 3:
                    if freezed:
                        logging.debug(
                            f"The first note falls between {from_row}-{to_row}"
                        )
                        time.sleep(PHOTOGATE_LATENCY / 1000)
                        break
                else:
                    if not freezed:
                        waited_frames += 1

                if not freezed and waited_frames >= 200:
                    freezed = True
                    logging.debug("Picture freezed, waiting for the first note...")

            last_color = cur_color
        except Exception as e:
            logging.error(f"Failed to get screen: {e}")


def mnt_callback(event: MNTEvent, data: MNTEventData):
    global callback_data
    if event == MNTEvent.EVATIVE7_LOG:
        data: MNTEvATive7LogEventData = data

        cmd = data.cmd
        cost = data.cost

        cmd_type = cmd.split(" ")[0]

        callback_data_lock.acquire()

        if (last_cmd_endtime := callback_data.get("last_cmd_endtime")) != -1:
            callback_data["interval"]["total"] += 1
            callback_data["interval"]["total_offset"] += (
                data.start_time - last_cmd_endtime
            )
        callback_data["last_cmd_endtime"] = data.end_time
        if cmd_type in ["w"]:
            callback_data["wait"]["total"] += 1
            callback_data["wait"]["total_offset"] += cost - int(cmd.split(" ")[-1])
        elif cmd_type in ["u", "d", "m"]:
            type_ = {
                "u": "up",
                "d": "down",
                "m": "move",
            }[cmd_type]
            callback_data[type_]["uncommited"] += 1
            callback_data[type_]["total"] += 1
            callback_data[type_]["total_offset"] += cost
        elif cmd_type in ["c"]:
            total_uncommited = 0
            for type_ in ["up", "down", "move"]:
                total_uncommited += callback_data[type_]["uncommited"]

            if total_uncommited != 0:
                for type_ in ["up", "down", "move"]:
                    callback_data[type_]["total_offset"] += cost * (
                        callback_data[type_]["uncommited"] / total_uncommited
                    )
                    callback_data[type_]["uncommited"] = 0
        callback_data_lock.release()


def init_player_and_mnt():
    """Initialize minitouch from the device selected by the GUI.

    AUTODORI_DEVICE must contain the selected ADB endpoint and the emulator
    metadata required by the player IPC implementation.
    """
    global adb_path, current_player, device_address, mnt

    raw_device = os.environ.get("AUTODORI_DEVICE")
    if not raw_device:
        raise RuntimeError("AUTODORI_DEVICE was not provided by the GUI")

    device = json.loads(raw_device)
    adb_path = Path(device["adb_path"])
    device_address = device["address"]
    current_player = player.Player(
        device["player"]["type"], Path(device["player"]["path"]), device["player"]["index"]
    )
    mnt = MNT(
        device_address,
        type_="EvATive7",
        communicate_type=MNTServerCommunicateType.STDIO,
        mnt_asset_path=Path("./assets/minitouch_EvATive7"),
        callback=mnt_callback,
        adb_executor=str(adb_path.absolute()),
    )

    logging.info("Mumu and MNT inited.")


def configure_log():
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s[%(levelname)s][%(name)s] %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(
                "debug/autodori-{}.log".format(
                    datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
                ),
                mode="w",
                encoding="utf-8",
            ),
        ],
    )


def main():
    configure_log()
    if len(sys.argv) != 2:
        raise SystemExit("Usage: autodori-agent <socket_id>")

    if not AgentServer.start_up(sys.argv[1]):
        raise SystemExit("Failed to start the Agent Server")

    try:
        AgentServer.join()
    finally:
        if mnt is not None:
            mnt.stop()
        AgentServer.shut_down()


if __name__ == "__main__":
    main()
