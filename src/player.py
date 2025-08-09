import mumuipc
import ldipc
from pathlib import Path


class Player:
    def __init__(self, type_: str, path: Path, index: int, package_name: str) -> None:
        self.type = type_
        self.package_name = package_name
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
                    self.package_name
                )
            if self.display_id != -1:
                return self.player.ipc_capture_display(self.display_id)[:, :, :3]
            else:
                return self.player.capture()
        else:
            return self.player.capture()