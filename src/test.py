import autodori
from autodori import (
    configure_log,
    fuzzy_match_song,
    init_maa,
    init_player_and_mnt,
    play_song,
    save_song,
)

autodori.DIFFICULTY = "expert"
autodori.OFFSET = {"up": 0, "down": 0, "move": 0, "wait": 0.0, "interval": 0.0}
autodori.PHOTOGATE_LATENCY = 30
autodori.DEFAULT_MOVE_SLICE_SIZE = 20
autodori.CMD_SLICE_SIZE = 100

FUZZYSONGNAME = "Ringing Bloom"

songname, _ = fuzzy_match_song(FUZZYSONGNAME)
configure_log()
init_maa()
init_player_and_mnt()
save_song(songname)
autodori.current_chart.dump_debug_config()
play_song()  # Please interrupt the function. After entering the performance interface, resume execution
autodori.mnt.stop()
exit()
