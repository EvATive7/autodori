<div align="center">

# Autodori  

邦多利小助手 | 📘 [English Version](./README.en.md)

![Pipeline](https://img.shields.io/badge/Pipeline-%23454545?logo=paddypower&logoColor=%23FFFFFF)  ![python](https://img.shields.io/badge/Python-3776AB?logo=python&logoColor=white)  

</div>

## ✨ 功能

- [x] 自动启动游戏、自动清火
- [x] Windows、Mumu、雷电模拟器兼容
- [x] 优化的性能、低延迟、高精度
- [x] 国服可用
- [ ] 自动收取奖励、自动每日三抽
- [ ] Linux和Mac兼容、其它模拟器兼容（等待其它模拟器实现IPCAPI）
- [ ] 更高的精度和性能优化
- [ ] 日服和全球服支持
- [x] 战绩可查！👇

![ ](./docs/achievements/六兆年.png)  
*sp六兆年AP*

![ ](./docs/achievements/火花.png)  
*红火花AP*

![ ](./docs/achievements/SENSENFUKOKU.png)  
*红SENSENFUKOKU AP*

## 🛠 使用方法

> [!IMPORTANT]  
> 在使用此脚本之前，请确保前置条件：
>
> 1. 确保设备和模拟器性能足够
> 1. 将模拟器分辨率设置为一个16:9的值，推荐(1600,900)或(1280,720)
> 1. 选曲列表“正常”，建议清空歌曲筛选器
> 1. 在游戏“演出设定”中，将流速调整为8.0
> 1. 在游戏“演出效果·音量设定”中，关闭“3D切入模式”，并将“动作模式”改为“轻量模式”
> 1. 为了更好的体验，可以在游戏“演出效果·音量设定”中，启用“FAST/SLOW表示”和“Perfect状态显示”
> 1. 使用adb连接到模拟器

1. 从[release](https://github.com/EvATive7/autodori/releases)下载最新版  
2. 解压，并运行`autodori.exe`
3. 使用命令行`autodori.exe -h`可以查看更多选项
4. 你可以修改 `data/config.yml` 来更改配置：[配置文件示例](./docs/config_eg/config.yml)

> [!NOTE]  
> 如果你懂代码 / 需要自行调参或修改代码以获得更好的效果 / 凹分 / 需要测试、开发，请从源码运行：  
>
> 1. `git clone --recursive https://github.com/EvATive7/autodori`  
> 2. `cd autodori`  
> 3. `python -m venv .venv`  
> 4. `.venv\Scripts\activate`  
> 5. `pip install -r requirements.txt`
> 6. 执行`python build.py`（`build.py`会自动整理和下载必要的依赖项）

## ⚠️ 注意

1. 推荐使用最新版本的Mumu模拟器。在雷电模拟器上测试次数较少，且其似乎存在性能问题。
1. 脚本尚不完善，可能发生错误。欢迎Issue和PR。

## 📝 许可证和版权

本项目在GPLv3许可下开放源代码，修改、复制、分发本项目请遵守[项目许可证](LICENSE)。  
除了python包外，本项目还直接引用、修改或分发了以下开源代码、组件或二进制：

- [minitouch ver.EvATive7](https://github.com/EvATive7/minitouch)（Apache License 2.0）
- [MaaFramework](https://github.com/MaaXYZ/MaaFramework)（LGPLv3）
- [MaaYYS/build.py](https://github.com/TanyaShue/MaaYYs)（MIT）

本项目分发了以下闭源动态链接库，这些动态链接库并非本项目的开源部分，也不受本项目许可证的约束：

- msvcp140.dll
- vcruntime140.dll
