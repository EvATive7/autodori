import json
from pathlib import Path

# 偏移量存储文件路径
LATENCY_FILE = Path("data/latency.json")
# 难度排序
DIFFICULTY_ORDER = {
    "easy": 0,
    "normal": 1,
    "hard": 2,
    "expert": 3,
    "special": 4,
}

# 内存缓存，避免频繁读取文件
_latency_cache = {}

def load_offsets() -> dict:
    """
    从 LATENCY_FILE 加载所有偏移数据到内存缓存，并返回缓存字典。
    若文件不存在，则返回空字典。
    """
    global _latency_cache
    if LATENCY_FILE.exists():
        try:
            with open(LATENCY_FILE, "r", encoding="utf-8") as f:
                _latency_cache = json.load(f)
        except (json.JSONDecodeError, OSError):
            # 若文件损坏，重置为空
            _latency_cache = {}
    else:
        _latency_cache = {}
    return _latency_cache

def save_offset(song_id: str, difficulty: str, new_offset: int) -> None:
    """
    保存指定歌曲和难度的偏移值到文件。
    """
    global _latency_cache
    if not _latency_cache:
        load_offsets()
    
    key = f"{song_id}_{difficulty}"
    # 更新缓存
    _latency_cache[key] = new_offset
    
    # 确保 data 目录存在
    LATENCY_FILE.parent.mkdir(parents=True, exist_ok=True)

    # 排序
    sorted_items = dict(
        sorted(
            _latency_cache.items(),
            key=lambda item: (
                int(item[0].split("_")[0]),                # ID 转为数字排序
                DIFFICULTY_ORDER.get(item[0].split("_")[1], 99)  # 难度按映射排序
            )
        )
    )
    # 写入文件
    with open(LATENCY_FILE, "w", encoding="utf-8") as f:
        json.dump(sorted_items, f, ensure_ascii=False, indent=2)

def get_offset(song_id: str, difficulty: str) -> int:
    """
    获取指定歌曲和难度的偏移值。
    """
    global _latency_cache
    # 若缓存为空，则加载
    if not _latency_cache:
        load_offsets()
    key = f"{song_id}_{difficulty}"
    return _latency_cache.get(key, 0)