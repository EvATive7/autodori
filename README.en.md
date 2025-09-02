<div align="center">

# autodori  

A BanG Dream! helper

![Pipeline](https://img.shields.io/badge/Pipeline-%23454545?logo=paddypower&logoColor=%23FFFFFF)  ![python](https://img.shields.io/badge/Python-3776AB?logo=python&logoColor=white)  
</div>

> Parts of this document are translated by machine or AI.

## ✨ Features

- [x] Auto-launch game and auto-play songs
- [x] Compatible with Windows, Mumu, Mumu V5, and LDPlayer emulators
- [x] Ultra-low performance overhead, low latency, and high accuracy
- [x] Usable with the Chinese server
- [ ] Auto-collect rewards and auto daily gacha x3
- [ ] Compatibility with Linux, macOS, and other emulators (awaiting other emulators to implement IPCAPI)
- [ ] Further accuracy and performance optimizations
- [ ] Support for Japanese and Global servers
- [x] Proof is in the pudding! 👇

![ ](./docs/achievements/六兆年.png)  
*SP 六兆年と一夜物語 AP*

![ ](./docs/achievements/火花.png)  
*EX ヒバナ-Reloaded- AP*

![ ](./docs/achievements/SENSENFUKOKU.png)  
*EX SENSENFUKOKU AP*

## 🛠 Usage

> [!NOTE]
> Discussion & Development QQ Group: 1044289381

> [!IMPORTANT]  
> Before using this script, please ensure the prerequisites:
>
> 1. Make sure your device and emulator have sufficient performance
> 1. Set the emulator resolution to a 16:9 value, recommended (1600, 900) or (1280, 720)
> 1. Song list should be “Normal”, it is recommended to clear song filters
> 1. In the game "Performance Settings", adjust the note speed to 8.0
> 1. In the game "Performance Effects · Volume Settings", disable "3D Cut-in Mode", and set "Action Mode" to "Light Mode"
> 1. For a better experience, you may enable "FAST/SLOW Display" and "Perfect Status Display" in "Performance Effects · Volume Settings"
> 1. Start the emulator and ensure adb functionality works properly

### For Regular Users

1. Download the latest version from [release](https://github.com/EvATive7/autodori/releases)  
2. Extract, then run `autodori.exe`
3. Run `autodori.exe -h` in command line to see more options
4. You can edit `data/config.yml` to change settings: [Config Example](./docs/config_eg/config.yml)

### If you need to fine-tune parameters, modify code for higher score / testing, or development, run from source  

 1. `git clone --recursive https://github.com/EvATive7/autodori`  
 2. `cd autodori`  
 3. `python -m venv .venv`  
 4. `.venv\Scripts\activate`  
 5. `pip install -r requirements.txt`
 6. Run `python build.py` (`build.py` will automatically organize and download necessary dependencies)

## ⚠️ Notes

1. It is recommended to use the latest version of Mumu emulator. It was tested less frequently on the lightning simulator and appeared to have performance issues.
1. The project is not complete yet and errors may occur. Welcome Issue and PR.

## 📝 Risks, use restrictions, disclaimers, licenses and copyrights

This project is intended solely as an assistant to help players enjoy the game and progression more easily. Using this project to disrupt fair play is strictly prohibited. Please respect the BanG Dream game environment and follow game rules.

Be aware that this project cannot be used for leaderboard boosting. Users attempting to boost scores are subject to secondary checks by BanG Dream. Running on emulators or using unconventional input methods are high-risk factors; using this project for leaderboard purposes almost certainly triggers bans.

This project is open-source and free, and commercial use or distribution by individuals or organizations is prohibited. If you find commercial misuse, please report it on relevant platforms and this repository.

The developers and this project are not responsible for any direct or indirect losses caused by use or inability to use this project. Users must evaluate and assume all risks themselves; the project and developers are not liable for user actions.

This project is open source under the GPLv3 license. Please follow the [project license](LICENSE) when modifying, copying, or distributing it.  
In addition to Python packages, this project directly includes, modifies, or distributes the following open source code, components, or binaries:

- [minitouch ver.EvATive7](https://github.com/EvATive7/minitouch) (Apache License 2.0)
- [MaaFramework](https://github.com/MaaXYZ/MaaFramework) (LGPLv3)

This project distributes the following proprietary dynamic link libraries. These are not part of the open source project and are not covered by the project license:

- msvcp140.dll  
- vcruntime140.dll  
