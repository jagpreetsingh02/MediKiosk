"""A HELD-OUT set, written after the lexicon was tuned and never tuned against.

The 50 gold scripts in eval/scripts/ drove three lexicon fixes and two extractor fixes during
development. Reporting extraction accuracy on them alone would be reporting how well the
system fits the data it was fixed against, which is the oldest way to publish a good number
that means nothing.

These twelve are written blind: new phrasings, new presentations, deliberately awkward. The
rule is simple and it is the whole value of the file — **whatever number these produce is the
number that gets published, and no lexicon entry is added to improve it.** If they score
worse than the development set, that gap is the honest estimate of overfitting, and
docs/EVALUATION.md reports both.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import scripts.make_eval_scripts as base  # noqa: E402

base.OUT = Path(__file__).resolve().parents[1] / "eval" / "holdout"
base.OUT.mkdir(parents=True, exist_ok=True)
script = base.script

script(
    "h01-mi-different-words",
    "Chest pain, phrasing not in the lexicon",
    difficulty="emergency",
    age=61,
    gender="male",
    turns={
        "cc.text": {"utterance": "there is a tightness across my chest since dawn"},
        "cc.duration": {"tap": "today"},
        "hpi.site": {"utterance": "across the front of my chest"},
        "hpi.onset": {"utterance": "it came on abruptly while I was at rest"},
        "hpi.character": {"utterance": "a squeezing tightness, like a band"},
        "hpi.radiation": {"utterance": "it shoots into my left shoulder and arm"},
        "hpi.associated": {"utterance": "I broke out in a cold sweat and felt winded"},
        "hpi.severity": {"tap": 8},
    },
    expected={"hpi.site": "chest", "hpi.character": "pressure", "hpi.radiation": "left_arm"},
    flags=["RF-CARD-01"],
    priority="immediate",
)

script(
    "h02-stroke-colloquial",
    "Stroke described colloquially",
    difficulty="emergency",
    age=69,
    gender="female",
    turns={
        "cc.text": {"utterance": "my arm has gone dead on one side"},
        "cc.duration": {"tap": "today"},
        "hpi.site": {"tap": "limbs"},
        "hpi.onset": {"utterance": "it happened out of nowhere"},
        "hpi.associated": {"utterance": "my words are coming out slurred as well"},
        "hpi.severity": {"tap": 7},
        "ros.neuro": {"tap": ["limb_weakness", "speech"]},
        "ph.pregnancy": {"tap": "na"},
    },
    expected={"hpi.site": "limbs", "hpi.onset": "sudden"},
    flags=["RF-NEURO-01"],
    priority="immediate",
)

script(
    "h03-melaena-english",
    "Black stool, English phrasing",
    difficulty="emergency",
    age=57,
    gender="male",
    turns={
        "cc.text": {"utterance": "my motions have turned very dark and sticky"},
        "cc.duration": {"tap": "days_1_3"},
        "hpi.site": {"tap": "abdomen"},
        "hpi.severity": {"tap": 5},
        "ros.gi": {"tap": ["melaena"]},
    },
    expected={"hpi.site": "abdomen"},
    flags=["RF-BLEED-01"],
    priority="immediate",
)

script(
    "h04-tb-marathi-ish",
    "TB screen, unfamiliar phrasing",
    difficulty="low_literacy",
    age=32,
    gender="male",
    language="hi",
    turns={
        "cc.text": {"utterance": "kafi dino se khokhla lag raha hai"},
        "cc.duration": {"tap": "weeks_2_4"},
        "hpi.site": {"tap": "chest"},
        "hpi.severity": {"tap": 4},
        "ros.resp": {"tap": ["cough_3wk", "night_sweats"]},
        "ros.general": {"tap": ["weight_loss"]},
    },
    expected={"hpi.site": "chest"},
    flags=["RF-RESP-02", "RF-SYS-01"],
    priority="urgent",
)

script(
    "h05-negation-heavy",
    "Rules several things out explicitly",
    difficulty="contradictory",
    age=48,
    gender="female",
    turns={
        "cc.text": {"utterance": "pain in my stomach"},
        "hpi.site": {"utterance": "in my stomach, not my chest"},
        "hpi.character": {"utterance": "a dull ache, definitely not burning"},
        "hpi.associated": {"utterance": "no vomiting, no fever, and I have not been sweating"},
        "hpi.severity": {"tap": 4},
        "ph.pregnancy": {"tap": "na"},
    },
    expected={"hpi.site": "abdomen", "hpi.character": "dull"},
    forbidden=["RF-CARD-01", "RF-RESP-01"],
    priority="routine",
    notes="Every negated term must be ignored. Reading one as present invents a symptom.",
)

script(
    "h06-anaphylaxis-plain",
    "Allergy history, plain words",
    difficulty="emergency",
    age=37,
    gender="male",
    turns={
        "cc.text": {"tap": "skin"},
        "hpi.site": {"tap": "limbs"},
        "hpi.severity": {"tap": 3},
        "allergy.any": {"tap": True},
        "allergy.what": {"utterance": "a painkiller tablet"},
        "allergy.reaction": {"utterance": "my throat closed up and I passed out"},
    },
    expected={"drug_allergy.has_allergy": True},
    flags=["RF-SYS-02"],
    priority="immediate",
)

script(
    "h07-routine-decoy",
    "Words that look alarming but are not",
    difficulty="plain",
    age=44,
    gender="male",
    turns={
        "cc.text": {"utterance": "my father had a stroke so I want a check-up"},
        "cc.duration": {"tap": "months_6_plus"},
        "hpi.site": {"tap": "whole_body"},
        "hpi.severity": {"tap": 0},
        "fh.conditions": {"tap": ["stroke"]},
    },
    expected={"family_history.conditions": ["stroke"]},
    forbidden=["RF-NEURO-01", "RF-CARD-01"],
    priority="routine",
    notes="The father's stroke must not become the patient's.",
)

script(
    "h08-rambling-buried",
    "Emergency buried in an anecdote",
    difficulty="rambling",
    age=66,
    gender="female",
    turns={
        "cc.text": {
            "utterance": "I was cooking for my grandchildren, we had guests over from the village, and while I was standing at the stove I felt this crushing weight on my chest and had to sit down"
        },
        "cc.duration": {"tap": "today"},
        "hpi.site": {"tap": "chest"},
        "hpi.onset": {"tap": "sudden"},
        "hpi.character": {"utterance": "a crushing weight, very heavy"},
        "hpi.associated": {"utterance": "I was drenched in sweat"},
        "hpi.severity": {"tap": 8},
        "ph.pregnancy": {"tap": "na"},
    },
    expected={"hpi.site": "chest", "hpi.onset": "sudden"},
    flags=["RF-CARD-01"],
    priority="immediate",
)

script(
    "h09-scale-spoken",
    "Severity given in words, not a tap",
    difficulty="mixed",
    age=53,
    gender="male",
    turns={
        "cc.text": {"tap": "pain"},
        "hpi.site": {"tap": "back"},
        "hpi.severity": {"utterance": "I would say about 6 out of 10"},
    },
    expected={"hpi.severity": 6},
    priority="routine",
)

script(
    "h10-ayush-unfamiliar",
    "AYUSH answers in unfamiliar words",
    difficulty="mixed",
    age=71,
    gender="male",
    ayush=True,
    turns={
        "cc.text": {"tap": "stomach"},
        "hpi.site": {"tap": "abdomen"},
        "hpi.severity": {"tap": 3},
        "ayush.agni": {"utterance": "khana bahut der se pachta hai, bhaari lagta hai"},
        "ayush.koshtha": {"utterance": "kabz rehti hai hamesha"},
    },
    expected={"ayush.agni": "manda", "ayush.koshtha": "krura", "ayush.vaya": "vriddha"},
    priority="routine",
)

script(
    "h11-declines-all-optional",
    "Declines every optional question",
    difficulty="mixed",
    age=30,
    gender="female",
    turns={
        "cc.text": {"tap": "fever"},
        "hpi.site": {"tap": "whole_body"},
        "hpi.severity": {"tap": 4},
        "ph.tobacco": {"decline": True},
        "ph.alcohol": {"decline": True},
        "ph.diet": {"decline": True},
        "ph.sleep": {"decline": True},
        "ph.bowel": {"decline": True},
        "ph.occupation": {"decline": True},
        "ph.pregnancy": {"decline": True},
        "fh.conditions": {"decline": True},
    },
    expected={"chief_complaint.text": "fever"},
    declined=[
        "personal_history.tobacco",
        "personal_history.alcohol",
        "personal_history.diet",
        "personal_history.sleep",
        "personal_history.bowel",
        "personal_history.occupation",
        "personal_history.pregnancy",
        "family_history.conditions",
    ],
    priority="routine",
)

script(
    "h12-all-asr-fails",
    "Every spoken answer is unintelligible",
    difficulty="mixed",
    age=58,
    gender="female",
    turns={
        "cc.text": {"utterance": "mmmhh brrr", "asr_confidence": 0.11, "tap": "pain"},
        "hpi.site": {"utterance": "unclear mumble", "asr_confidence": 0.09, "tap": "joints"},
        "hpi.character": {"utterance": "nnngh", "asr_confidence": 0.05, "tap": "dull"},
        "hpi.severity": {"tap": 5},
        "ph.pregnancy": {"tap": "na"},
    },
    expected={"chief_complaint.text": "pain", "hpi.site": "joints", "hpi.character": "dull"},
    forbidden=["RF-CARD-01"],
    priority="routine",
    notes="Every utterance must degrade to touch and record nothing. The tapped fallbacks "
    "still complete the history, which is the point of dual-mode input.",
)

print(f"wrote {len(list(base.OUT.glob('*.json')))} held-out scripts")
