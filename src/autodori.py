import json
import logging
import os
import random
import re
import string
import time
from pathlib import Path
from threading import Thread
from typing import Optional, Union

import numpy as np
from fuzzywuzzy import process as fzwzprocess
from maa.context import Context
from maa.controller import AdbController
from maa.custom_action import CustomAction, CustomRecognitionResult
from maa.custom_recognition import CustomRecognition
from maa.define import RectType
from maa.notification_handler import NotificationHandler, NotificationType
from maa.resource import Resource
from maa.tasker import Tasker
from maa.toolkit import AdbDevice, Toolkit
from minitouchpy import CommandBuilder, safe_connection
from minitouchpy.connection import MNTConnection, MNTServer

import mumuextras
from api import BestdoriAPI
from chart import Chart, PlayRecord
from util import *

Path("data").mkdir(exist_ok=True)
Path("cache").mkdir(exist_ok=True)

LIVEBOOST_COST = 3
DIFFICULTY = "hard"
DEFAULT_MOVE_OFFSET = 0.15
DEFAULT_DOWN_OFFSET = 0.0

maaresource = Resource()
maatasker = Tasker()
maacontroller: AdbController = None
device: AdbDevice = None
# player = mumuextras.PLAYER
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
current_cmd: CommandBuilder = None
commands = []


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
            song_fuzzyname = context.run_recognition(
                pplname,
                argv.image,
                pipeline,
            ).best_result.text
            return fzwzprocess.extractOne(
                song_fuzzyname, list(all_song_name_indexes.keys())
            )

        jpmatch = match("ppocr_v3/ja_jp")
        commonmatch = match()  # , "ppocr_v4/zh_cn")
        logging.debug(
            "Match result with ppocr_v3/ja_jp: {}, Match result with default: {}".format(
                jpmatch, commonmatch
            )
        )
        result = sorted([jpmatch, commonmatch], key=lambda x: x[1], reverse=True)
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
        roi = [970, 29, 39, 21]

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
            ocrtext = context.run_recognition(
                f"_PlayResultRecognition_ocr_{type_}",
                argv.image,
                pipeline,
            ).best_result.text
            try:
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
            global current_song_id
            succeed: bool = json.loads(argv.custom_action_param).get("succeed")
            if succeed:
                playresult = argv.reco_detail.best_result.detail
                if isinstance(playresult, str):
                    playresult = json.loads(argv.reco_detail.best_result.detail)
            else:
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
            return CustomAction.RunResult(True)
        except Exception as e:
            logging.error(f"Failed to save play result: {e}")
            return CustomAction.RunResult(False)


@maaresource.custom_action("Play")
class Play(CustomAction):
    def run(self, context: Context, argv: CustomAction.RunArg):
        try:
            global current_cmd
            play_song(current_cmd)
            return CustomAction.RunResult(True)
        except:
            return CustomAction.RunResult(False)


@maaresource.custom_action("SaveSong")
class SaveSong(CustomAction):
    def run(self, context: Context, argv: CustomAction.RunArg):
        global current_song_name, current_cmd, current_song_id
        reco_detail: CustomRecognitionResult = argv.reco_detail.best_result
        current_song_name = reco_detail.detail
        current_song_id = all_song_name_indexes[current_song_name]
        current_chart = Chart((current_song_id, DIFFICULTY))
        actions = notes_to_actions(current_chart.time_chart, player.resolution)
        current_cmd = actions_to_MNTcmd(
            commands,
            actions,
            player.resolution,
            DEFAULT_DOWN_OFFSET,
            DEFAULT_MOVE_OFFSET,
        )

        logging.debug("Save song name: {}".format(current_song_name))
        return CustomAction.RunResult(True)


def play_song(cmd: CommandBuilder):
    logging.info("Start play")

    wait_first_note()
    cmd.publish(mnt_connection, block=True)


def _async_publish_cmd(actions: list, connection: MNTConnection, resolution):
    action = None
    cur_time = 0

    def run_action(action):
        builder = CommandBuilder()
        action_type = action["type"]
        finger = action["finger"]

        if action_type == "down":
            player.ipc_input_event_finger_touch_down(
                mumuextras.DISPLAY_ID,
                finger,
                *androidxy_to_MNTxy(action["pos"], resolution),
            )
            print("down", finger, *androidxy_to_MNTxy(action["pos"], resolution))
            # builder.down(finger, *androidxy_to_MNTxy(action["pos"], resolution), 100)
        elif action_type == "move":
            pass
            # builder.move(finger, *androidxy_to_MNTxy(action["to"], resolution), 100)
        elif action_type == "up":
            player.ipc_input_event_finger_touch_up(mumuextras.DISPLAY_ID, finger)
            print("up", finger)

            # builder.up(finger)
        # builder.commit()
        # builder.publish(connection)

    while True:
        if not actions:
            break

        filtered_actions = list(
            filter(
                lambda action: int(action["time"] - 2553.19) == int(cur_time), actions
            )
        )
        for action in filtered_actions:
            thread = Thread(target=run_action, args=(action,))
            thread.start()

        cur_time += 1
        time.sleep(1 / 1000)

    time.sleep(10)


def wait_first_note():
    last_color = None
    waited_frames = 0
    info = runtime_info["wait_first"][player.resolution]
    from_row, to_row = info["from"], info["to"]

    while True:
        screen = player.ipc_capture_display(mumuextras.DISPLAY_ID)
        cur_color, _ = get_color_eval_in_range(screen, from_row, to_row)

        if last_color is not None:
            change_score = np.sum(cur_color[0:3] - last_color[0:3])
            if change_score > 3:
                if waited_frames < 200:
                    waited_frames = 0
                else:
                    logging.debug(f"The first note falls between {from_row}-{to_row}")
                    time.sleep(TIME_BETWEEN_FIRSTNOTE_DETECTED_TO_LANE / 1000)
                    break
            else:
                waited_frames += 1
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
        exit(1)

    global device, maacontroller
    _device = [
        device for device in adb_devices if "mumu" in device.config.get("extras", {})
    ]
    if not _device:
        logging.fatal("No supported devices were found.")
        exit(1)
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
        exit(1)

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
    entry = "main"
    init_maa()
    init_mumu_and_mnt()

    # entry = "save_playresult"
    # global current_song_id
    # current_song_id = "251"

    maatasker.post_task(
        entry,
        {
            "_test": {
                "recognition": "Custom",
                "custom_recognition": "SongRecognition",
                "action": "Custom",
                "custom_action": "Play",
                "roi": [201, 332, 367, 29],
            }
        },
    ).wait().get()

    exit()


if __name__ == "__main__":
    main()
