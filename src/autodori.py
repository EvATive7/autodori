import argparse
import json
import logging
import random
import string
import sys
import time
from pathlib import Path
from typing import Optional, Union

data_path = Path("data")
data_path.mkdir(exist_ok=True)
cache_path = Path("cache")
cache_path.mkdir(exist_ok=True)
config_path = Path("data/config.yml")
if not config_path.exists():
    config_path.touch()
    config_path.write_text("{}", encoding="utf-8")


import numpy as np
from fuzzywuzzy import process as fzwzprocess
from maa.context import Context
from maa.controller import AdbController
from maa.custom_action import CustomAction, CustomRecognitionResult
from maa.custom_recognition import CustomRecognition
from maa.define import RectType
from maa.resource import Resource
from maa.tasker import Tasker
from maa.toolkit import AdbDevice, Toolkit
from minitouchpy.connection import MNTConnection, MNTServer

import mumuextras
from api import BestdoriAPI
from chart import Chart, PlayRecord
from util import *

LIVEBOOST_COST = 1
DIFFICULTY = "hard"
DEFAULT_MOVE_OFFSET = 0.15
DEFAULT_DOWN_OFFSET = 0.15
PHOTOGATE_LATENCY = 30
DEFAULT_MOVE_SLICE_SIZE = 30
MAX_FAILED_TIMES = 10

maaresource = Resource()
maatasker = Tasker()
maacontroller: AdbController = None
device: AdbDevice = None
player: mumuextras.MuMuPlayer = None
mnt_server: MNTServer = None
mnt_connection: MNTConnection = None
all_songs: dict = BestdoriAPI.get_song_list()
all_song_name_indexes: dict[str, str] = {
    list(filter(lambda title: title is not None, sinfo["musicTitle"]))[0]: sid
    for sid, sinfo in all_songs.items()
}
current_song_name: str = None
current_song_id: str = None
current_chart: Chart = None
play_failed_times: int = 0


def check_song_available(name, id_, difficulty):
    if name.startswith("[FULL]"):
        return False

    lastmatched = PlayRecord.get_or_none(chart_id=id_, difficulty=difficulty)
    if lastmatched:
        if not lastmatched.succeed:
            return False

    return True


@maaresource.custom_recognition("SongRecognition")
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

        if not check_song_available(
            result_music_name, all_song_name_indexes[result_music_name], DIFFICULTY
        ):
            return CustomRecognition.AnalyzeResult(None, "")

        return CustomRecognition.AnalyzeResult(roi, result_music_name)


@maaresource.custom_recognition("LiveBoostEnoughRecognition")
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
        live_boost = live_boost.replace("/10", "")

        try:
            live_boost = int(live_boost)
        except:
            live_boost = -1

        logging.debug("Live boost: {}".format(live_boost))

        if live_boost < LIVEBOOST_COST:
            return CustomRecognition.AnalyzeResult(None, "")
        else:
            return CustomRecognition.AnalyzeResult(roi, str(live_boost))


@maaresource.custom_recognition("PlayResultRecognition")
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


@maaresource.custom_action("SavePlayResult")
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
                play_offset={
                    "move": DEFAULT_MOVE_OFFSET,
                    "down": DEFAULT_DOWN_OFFSET,
                },
                result=playresult,
                succeed=succeed,
                chart_id=current_song_id,
                difficulty=DIFFICULTY,
            )
            if play_failed_times >= MAX_FAILED_TIMES:
                context.run_action("close_app")
            return CustomAction.RunResult(True)
        except Exception as e:
            logging.error(f"Failed to save play result: {e}")
            return CustomAction.RunResult(False)


@maaresource.custom_action("Play")
class Play(CustomAction):
    def run(self, context: Context, argv: CustomAction.RunArg):
        try:
            play_song()
            return CustomAction.RunResult(True)
        except:
            return CustomAction.RunResult(False)


@maaresource.custom_action("SaveSong")
class SaveSong(CustomAction):
    def run(self, context: Context, argv: CustomAction.RunArg):
        name: CustomRecognitionResult = argv.reco_detail.best_result.detail
        save_song(name)
        logging.debug("Save song: {}".format(name))
        return CustomAction.RunResult(True)


def fuzzy_match_song(name):
    return fzwzprocess.extractOne(name, list(all_song_name_indexes.keys()))


def save_song(name):
    global current_song_name, current_song_id, current_chart
    current_song_name = name
    current_song_id = all_song_name_indexes[current_song_name]
    current_chart = Chart((current_song_id, DIFFICULTY), current_song_name)
    current_chart.notes_to_actions(player.resolution, DEFAULT_MOVE_SLICE_SIZE)
    current_chart.actions_to_MNTcmd(
        player.resolution, DEFAULT_DOWN_OFFSET, DEFAULT_MOVE_OFFSET
    )


def play_song():
    logging.info("Start play")

    wait_first_note()
    current_chart.command_builder.publish(mnt_connection, block=True)


def wait_first_note():
    last_color = None
    waited_frames = 0
    info = get_runtime_info(player.resolution)["wait_first"]
    from_row, to_row = info["from"], info["to"]
    freezed = False

    display_id = player.ipc_get_display_id("com.bilibili.star.bili")
    while True:
        screen = player.ipc_capture_display(display_id)
        cur_color, _ = get_color_eval_in_range(screen, from_row, to_row)

        if last_color is not None:
            change_score = np.sum(cur_color[0:3] - last_color[0:3])
            logging.debug(f"Picture changed: {change_score}")
            if change_score > 3:
                if freezed:
                    logging.debug(f"The first note falls between {from_row}-{to_row}")
                    time.sleep(PHOTOGATE_LATENCY / 1000)
                    break
            else:
                if not freezed:
                    waited_frames += 1

            if not freezed and waited_frames >= 200:
                freezed = True
                logging.debug("Picture freezed, waiting for the first note...")

        last_color = cur_color


def init_maa():
    user_path = "./"
    resource_path = "assets/resource"

    res_job = maaresource.post_bundle(resource_path)
    res_job.wait()
    Toolkit.init_option(user_path)
    adb_devices = Toolkit.find_adb_devices()
    if not adb_devices:
        logging.fatal("No ADB device found.")
        sys.exit(1)

    global device, maacontroller
    _device = [
        device for device in adb_devices if "mumu" in device.config.get("extras", {})
    ]
    if not _device:
        logging.fatal("No supported devices were found.")
        sys.exit(1)
    else:
        device = _device[0]
    maacontroller = AdbController(
        adb_path=device.adb_path,
        address=device.address,
        screencap_methods=device.screencap_methods,
        input_methods=device.input_methods,
        config=device.config,
    )
    maacontroller.post_connection().wait()

    # tasker = Tasker(notification_handler=MyNotificationHandler())
    maatasker.bind(maaresource, maacontroller)

    if not maatasker.inited:
        logging.fatal("Failed to init MAA.")
        sys.exit(1)

    logging.info("MAA inited.")


def init_mumu_and_mnt():
    global player, mnt_connection, mnt_server

    extra_config = device.config["extras"]["mumu"]
    path = extra_config["path"]
    index = extra_config["index"]

    player = mumuextras.MuMuPlayer(Path(path), index)
    mnt_server = MNTServer(device.address)
    mnt_connection = MNTConnection(mnt_server)

    logging.info("Mumu and MNT inited.")


def main():
    logging.basicConfig(
        level=logging.DEBUG, format="%(asctime)s[%(levelname)s][%(name)s] %(message)s"
    )

    parser = argparse.ArgumentParser(
        description="AutoDori script with different modes."
    )
    parser.add_argument(
        "--mode",
        type=str,
        choices=["main"],
        help="Specify the mode to run",
        default="main",
    )
    args = parser.parse_args()

    if args.mode == "main":
        entry = "main"
    else:
        sys.exit(1)

    init_maa()
    init_mumu_and_mnt()

    maatasker.post_task(entry, {}).wait().get()

    mnt_connection.disconnect()
    mnt_server.stop()
    logging.debug("Ready to exit")
    sys.exit()


if __name__ == "__main__":
    main()
