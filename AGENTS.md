## Repository Rules

- Use English for all repository content. The only exception is `README.md`.
- Use Conventional Commits for every commit message.
- If `AGENTS.md.local` exists, read it first.
- This project uses [MaaXYZ/MFAAvalonia](https://github.com/MaaXYZ/MFAAvalonia) for its GUI and [MaaXYZ/MaaFramework](https://github.com/MaaXYZ/MaaFramework) as its framework; consult their documentation and source code whenever anything is uncertain.
- Python dependencies and the virtual environment are managed with uv. Use uv rather than system Python or pip when installing dependencies and running project commands.

## Project Structure

- `assets/interface.json` is the Maa Project Interface. It defines the GUI-facing tasks, options, controllers, resources, translations, and Agent executable.
- `assets/interface_*.json` contains the interface translations. `assets/resource/` contains Maa pipelines, images, OCR models, and other automation resources.
- `src/agent.py` is the Python Agent Server. It implements custom Maa actions and recognitions, manages the emulator-specific runtime, and performs the live automation logic. Its runtime files are stored under `.autodori-agent-data/`.
- `build.py` assembles the final application. `dist/` contains the runnable MFAAvalonia directory and release archive.

## Architecture and Packaging

- MFAAvalonia is the GUI host. It reads `interface.json`, renders task settings, loads `assets/resource/`, creates the Maa controller, and starts the Agent executable configured by `agent.child_exec`.
- The Agent and GUI communicate through MaaFramework's Agent Server protocol. GUI options become pipeline overrides; when the pipeline reaches a custom action or recognition, MaaFramework invokes the corresponding Python Agent implementation.
- Keep control flow in Maa resource pipelines where possible. Use the Agent only for logic that requires code, such as emulator IPC, minitouch input, custom recognition, stateful limits, or data persistence.
- During packaging, `build.py` uses PyInstaller to build `src/agent.py` into the one-file `autodori-agent.exe`. The Agent bundles MaaFramework Python binaries, MaaAgentBinary, and the minitouch asset, then is copied to `agent/autodori-agent.exe` in the GUI project.
- `build.py` downloads and extracts the pinned MFAAvalonia release, overlays the Project Interface, translations, resources, and Agent executable, then writes both the runnable directory and the versioned `autodori-<version>-win-x64.zip` archive.
