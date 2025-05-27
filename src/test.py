import autodori

FUZZYSONGNAME = "寄る辺のSunny,Sunny"

autodori.DIFFICULTY = "expert"
autodori.OFFSET = {"up": 0, "down": 0, "move": 0, "wait": 0.0, "interval": 0.0}
autodori.PHOTOGATE_LATENCY = 30
autodori.DEFAULT_MOVE_SLICE_SIZE = 20
autodori.CMD_SLICE_SIZE = 100

autodori.configure_log()
autodori.init_maa()
autodori.init_player_and_mnt()
autodori.save_song(autodori.fuzzy_match_song(FUZZYSONGNAME)[0])
autodori.current_chart.dump_debug_config()
autodori.play_song()  # Please interrupt the function. After entering the live interface, resume execution
autodori.mnt.stop()
exit()
