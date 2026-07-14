import agent

FUZZYSONGNAME = "寄る辺のSunny,Sunny"

agent.current_difficulty = "expert"
agent.OFFSET = {"up": 0, "down": 0, "move": 0, "wait": 0.0, "interval": 0.0}
agent.PHOTOGATE_LATENCY = 30
agent.DEFAULT_MOVE_SLICE_SIZE = 20
agent.CMD_SLICE_SIZE = 100

agent.configure_log()
agent.init_player_and_mnt()
agent.save_song(agent.fuzzy_match_song(FUZZYSONGNAME)[0])
agent.current_chart.dump_debug_config()
agent.play_song()  # Please interrupt the function. After entering the live interface, resume execution
agent.mnt.stop()
exit()
