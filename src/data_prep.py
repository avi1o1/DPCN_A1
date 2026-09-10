"""
Data preparation for the Opinion Network Formation assignment.

Loads the raw survey CSV, maps the Likert-scale text responses to numeric
scores, categorises each question into one of the four survey topics
(Technology / Education / Ethics / Environment), and writes cleaned,
analysis-ready artefacts to `data/`.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RAW_CSV = ROOT / "data" / "survey_data.csv"
CLEAN_SCORES_CSV = ROOT / "data" / "cleaned_scores.csv"
QUESTION_META_JSON = ROOT / "data" / "question_meta.json"

# Likert text -> numeric score. "No Comments" is treated as missing (no opinion given).
LIKERT_MAP = {
    "Strongly Disagree": -2,
    "Disagree": -1,
    "Neutral": 0,
    "Agree": 1,
    "Strongly Agree": 2,
    "No Comments": np.nan,
}

TOPIC_NAMES = {
    "T": "Technology",
    "E": "Education",
    "S": "Ethics",
    "V": "Environment",
}


def load_raw() -> pd.DataFrame:
    df = pd.read_csv(RAW_CSV)
    df.columns = [c.strip() for c in df.columns]
    return df


def question_columns(df: pd.DataFrame) -> list[str]:
    return [c for c in df.columns if c[0] in TOPIC_NAMES and c[1:3].isdigit()]


def build_question_meta(cols: list[str]) -> dict:
    meta = {}
    for c in cols:
        code = c.split(".")[0].strip()
        topic_letter = code[0]
        meta[code] = {
            "topic": TOPIC_NAMES[topic_letter],
            "text": c.split(".", 1)[1].strip(),
        }
    return meta


def clean() -> tuple[pd.DataFrame, dict]:
    df = load_raw()
    id_col = df.columns[0]
    q_cols = question_columns(df)
    meta = build_question_meta(q_cols)

    scores = df[q_cols].apply(lambda s: s.map(LIKERT_MAP))
    scores.columns = [
        c.split(".")[0].strip() for c in q_cols
    ]  # e.g. "T01" instead of the full question text
    q_cols = list(scores.columns)
    scores.insert(0, "respondent_id", df[id_col].astype(str))

    # Drop respondents who answered fewer than half the questions (e.g. dropped-out rows).
    min_answers = len(q_cols) // 2
    answered = scores[q_cols].notna().sum(axis=1)
    scores = scores[answered >= min_answers].reset_index(drop=True)

    ROOT.joinpath("data").mkdir(exist_ok=True)
    scores.to_csv(CLEAN_SCORES_CSV, index=False)
    QUESTION_META_JSON.write_text(json.dumps(meta, indent=2))

    return scores, meta


if __name__ == "__main__":
    scores, meta = clean()
    n_resp, n_q = scores.shape[0], len(meta)
    missing_rate = scores.drop(columns="respondent_id").isna().mean().mean()
    print(f"Respondents kept: {n_resp}")
    print(f"Questions: {n_q}")
    print(f"Overall missing-answer rate: {missing_rate:.2%}")
    print(f"Wrote {CLEAN_SCORES_CSV} and {QUESTION_META_JSON}")
