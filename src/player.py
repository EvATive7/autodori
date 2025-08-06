import mumuipc
import ldipc


class Player:
    def __init__(self, type_: str, path: str, index: int) -> None:
        self.type = type_
        self.display_id = -1
        if type_ == "mumu":
            self.player = mumuipc.MuMuPlayer(path, index)
        else:
            self.player = ldipc.LDPlayer(path, index)

    @property
    def resolution(self):
        return self.player.resolution

    def ipc_capture_display(self):
        if self.type == "mumu":
            if self.display_id == -1:
                self.display_id = self.player.ipc_get_display_id(
                    "jp.co.craftegg.band"
                )
            # RGBA -> RGB
            return self.player.ipc_capture_display(self.display_id)[:, :, :3]
        else:
            # RGB
            return self.player.capture()
