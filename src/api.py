import logging

import requests
from diskcache import Cache


class BestdoriAPI:
    base = "https://bestdori.com/api"
    logger = logging.getLogger("BestdoriAPI")
    cache = Cache("cache")

    @staticmethod
    def _set_cache(name, data, expire):
        BestdoriAPI.cache.set(name, data, expire=expire)
        BestdoriAPI.logger.info(f"Cache set for {name}")
        return data

    @staticmethod
    def _get_cache(name):
        data = BestdoriAPI.cache.get(name)
        if data is None:
            BestdoriAPI.logger.info(f"Cache not found for {name}")
        else:
            BestdoriAPI.logger.info(f"Cache hit for {name}")
        return data

    @staticmethod
    def get_song_list():
        if cache_ := BestdoriAPI._get_cache("allsongs"):
            return cache_
        else:
            response = requests.get(BestdoriAPI.base + "/songs/all.5.json").json()
            return BestdoriAPI._set_cache(
                "allsongs",
                response,
                expire=3600 * 1,
            )

    @staticmethod
    def get_chart(song_id: str, difficulty: str):
        cacheid = f"{song_id}-{difficulty}"
        if cache_ := BestdoriAPI._get_cache(cacheid):
            return cache_
        else:
            response = requests.get(
                BestdoriAPI.base + f"/charts/{song_id}/{difficulty}.json"
            ).json()
            return BestdoriAPI._set_cache(
                cacheid,
                response,
                expire=None,
            )


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    songlist = BestdoriAPI.get_song_list()
    chart = BestdoriAPI.get_chart(1, "easy")
    pass
