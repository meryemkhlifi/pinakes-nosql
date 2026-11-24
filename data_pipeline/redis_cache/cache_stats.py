"""Print the cache statistics (for the report): hit ratio = hits / (hits + misses).

python -m data_pipeline.redis_cache.cache_stats
python -m data_pipeline.redis_cache.cache_stats --top 10    # also the most read works
"""

import argparse

from redis.exceptions import RedisError

from backend.app.db import redis as redis_db


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--top", type=int, default=0)
    args = ap.parse_args()
    try:
        stats = redis_db.cache_stats()
        print(f"hits={stats['hits']} misses={stats['misses']} hit_ratio={stats['hit_ratio']}")
        for work_id, views in redis_db.top_works(args.top) if args.top else []:
            print(f"  {views:5}  {work_id}")
    except RedisError:
        raise SystemExit("Redis is not reachable. Is stack A running?")


if __name__ == "__main__":
    main()
