import os
from scripts.pygpen.utils.io import read_json, write_json

HIGH_SCORE_PATH = os.path.join("config", "high_score.json")

def load_high_score():
    try:
        data = read_json(HIGH_SCORE_PATH)
        return int(data.get("high_score", 0))
    except (FileNotFoundError, ValueError, TypeError, KeyError):
        return 0

def save_high_score(score):
    write_json(HIGH_SCORE_PATH, {"high_score": score})
