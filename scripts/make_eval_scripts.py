"""Author the 50 gold patient scripts.

The *content* of every script — each utterance, each expected slot, each expected rule id —
is written by hand below. What is shared is only the boilerplate tail of routine answers that
every script needs in order to reach the end of the interview, because repeating twenty-five
identical "no" answers fifty times would obscure the part that matters.

`BASE` is that tail. Each script overrides the turns that make it distinctive.
"""
from __future__ import annotations

import json
import pathlib
from typing import Any

OUT = pathlib.Path(__file__).resolve().parents[1] / "eval" / "scripts"
OUT.mkdir(parents=True, exist_ok=True)

#: The unremarkable answers. Overridden per script wherever the patient is not unremarkable.
BASE: dict[str, Any] = {
    "cc.duration": {"tap": "weeks_2_4"},
    "hpi.onset": {"tap": "gradual"},
    "hpi.character": {"tap": "dull"},
    "hpi.radiation": {"tap": "none"},
    "hpi.associated": {"tap": ["none"]},
    "hpi.timing": {"tap": "intermittent"},
    "hpi.exacerbating": {"tap": ["better_rest"]},
    "hpi.severity": {"tap": 4},
    "pmh.conditions": {"tap": ["none"]},
    "pmh.hospitalised": {"tap": False},
    "psh.any": {"tap": False},
    "med.taking": {"tap": False},
    "med.ayush_taking": {"tap": False},
    "allergy.any": {"tap": False},
    "fh.conditions": {"tap": ["none"]},
    "ph.tobacco": {"tap": "never"},
    "ph.alcohol": {"tap": "never"},
    "ph.diet": {"tap": "veg"},
    "ph.sleep": {"tap": "good"},
    "ph.bowel": {"tap": "regular"},
    "ph.occupation": {"tap": "home"},
    "ph.pregnancy": {"tap": "na"},
    "ros.cardio": {"tap": ["none"]},
    "ros.resp": {"tap": ["none"]},
    "ros.gi": {"tap": ["none"]},
    "ros.neuro": {"tap": ["none"]},
    "ros.gu": {"tap": ["none"]},
    "ros.msk": {"tap": ["none"]},
    "ros.general": {"tap": ["none"]},
}

AYUSH_TAIL: dict[str, Any] = {
    "ayush.prakriti_build": {"tap": "medium_warm"},
    "ayush.vikriti": {"tap": "burning_acid"},
    "ayush.sara": {"tap": "madhyama"},
    "ayush.samhanana": {"tap": "madhyama"},
    "ayush.pramana": {"tap": "madhyama"},
    "ayush.satmya": {"tap": "madhyama"},
    "ayush.sattva": {"tap": "madhyama"},
    "ayush.ahara_shakti": {"tap": "madhyama"},
    "ayush.vyayama_shakti": {"tap": "madhyama"},
    "ayush.agni": {"tap": "sama"},
    "ayush.koshtha": {"tap": "madhya"},
    "ayush.vihara": {"tap": "moderate"},
    "ayush.nidra": {"tap": "sound"},
}

#: Question order, so the emitted turn list matches the machine's walk.
ORDER = [
    "cc.text", "cc.duration", "hpi.site", "hpi.onset", "hpi.character", "hpi.radiation",
    "hpi.associated", "hpi.timing", "hpi.exacerbating", "hpi.severity",
    "pmh.conditions", "pmh.hospitalised", "pmh.hospital_reason",
    "psh.any", "psh.which", "psh.year",
    "med.taking", "med.list", "med.ayush_taking",
    "allergy.any", "allergy.what", "allergy.reaction",
    "fh.conditions",
    "ph.tobacco", "ph.alcohol", "ph.diet", "ph.sleep", "ph.bowel", "ph.occupation",
    "ph.pregnancy",
    "ros.cardio", "ros.resp", "ros.gi", "ros.neuro", "ros.gu", "ros.msk", "ros.general",
    *AYUSH_TAIL,
]


def script(
    sid: str,
    title: str,
    *,
    difficulty: str,
    age: int,
    gender: str,
    turns: dict[str, Any],
    expected: dict[str, Any],
    flags: list[str] | None = None,
    forbidden: list[str] | None = None,
    priority: str = "routine",
    language: str = "en",
    ayush: bool = False,
    declined: list[str] | None = None,
    notes: str = "",
) -> None:
    merged = {**BASE, **(AYUSH_TAIL if ayush else {}), **turns}
    ordered = [
        {"question_id": qid, **merged[qid]} for qid in ORDER if qid in merged
    ]
    payload = {
        "id": sid, "title": title, "language": language, "difficulty": difficulty,
        "ayush_mode": ayush,
        "demographics": {"age_years": age, "gender": gender},
        "turns": ordered,
        "expected": expected,
        "expected_red_flags": flags or [],
        "forbidden_red_flags": forbidden or [],
        "expected_priority": priority,
        "expected_declined": declined or [],
        "notes": notes,
    }
    (OUT / f"{sid}.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


# ═══════════════════════════════════════════════════════ EMERGENCIES (06–17)
# s01–s05 are authored individually in eval/scripts/ and are not regenerated here.

script("s06-thunderclap", "Thunderclap headache", difficulty="emergency", age=44, gender="female",
  turns={"cc.text": {"utterance": "the worst headache of my life started suddenly an hour ago"},
    "cc.duration": {"tap": "today"}, "hpi.site": {"tap": "head"}, "hpi.onset": {"tap": "sudden"},
    "hpi.character": {"tap": "throbbing"}, "hpi.severity": {"tap": 10},
    "hpi.associated": {"tap": ["vomiting"]},
    "ros.neuro": {"tap": ["thunderclap", "headache"]}},
  expected={"hpi.site": "head", "hpi.onset": "sudden", "hpi.severity": 10},
  flags=["RF-NEURO-02", "RF-PAIN-01"], priority="immediate")

script("s07-meningitis", "Fever with neck stiffness", difficulty="emergency", age=19, gender="male",
  turns={"cc.text": {"utterance": "high fever and my neck has become stiff"},
    "cc.duration": {"tap": "days_1_3"}, "hpi.site": {"tap": "head"},
    "hpi.associated": {"tap": ["fever", "vomiting"]}, "hpi.severity": {"tap": 8},
    "ros.neuro": {"tap": ["neck_stiff", "headache"]},
    "ros.general": {"tap": ["fever"]}},
  expected={"review_of_systems.neurological": ["neck_stiff", "headache"]},
  flags=["RF-NEURO-03"], priority="immediate")

script("s08-anaphylaxis-hx", "Anaphylaxis history before prescribing", difficulty="emergency",
  age=33, gender="female",
  turns={"cc.text": {"tap": "fever"}, "hpi.site": {"tap": "whole_body"},
    "allergy.any": {"tap": True},
    "allergy.what": {"utterance": "penicillin injection"},
    "allergy.reaction": {"utterance": "my face and lips swelled up and I could not breathe"},
    "ros.general": {"tap": ["fever"]}},
  expected={"drug_allergy.has_allergy": True, "drug_allergy.allergy_reaction": "swelling"},
  flags=["RF-SYS-02"], priority="immediate",
  notes="Must be visible before anything is prescribed today.")

script("s09-retention", "Complete urinary retention", difficulty="emergency", age=68, gender="male",
  turns={"cc.text": {"utterance": "I have not been able to pass urine since last night"},
    "cc.duration": {"tap": "today"}, "hpi.site": {"tap": "abdomen"},
    "hpi.severity": {"tap": 7}, "hpi.character": {"tap": "pressure"},
    "ros.gu": {"tap": ["retention", "nocturia"]}},
  expected={"review_of_systems.genitourinary": ["retention", "nocturia"]},
  flags=["RF-SYS-05"], priority="immediate")

script("s10-haematemesis", "Vomiting blood", difficulty="emergency", age=52, gender="male",
  turns={"cc.text": {"utterance": "I vomited and there was blood in it"},
    "cc.duration": {"tap": "today"}, "hpi.site": {"tap": "abdomen"},
    "hpi.associated": {"tap": ["vomiting", "dizziness"]}, "hpi.severity": {"tap": 7},
    "ph.alcohol": {"tap": "daily"},
    "ros.gi": {"tap": ["haematemesis", "vomiting"]}},
  expected={"review_of_systems.gastrointestinal": ["haematemesis", "vomiting"]},
  flags=["RF-BLEED-01", "RF-SYS-03"], priority="immediate")

script("s11-acute-abdomen", "Sudden severe abdominal pain", difficulty="emergency", age=41,
  gender="male",
  turns={"cc.text": {"utterance": "sudden very severe pain in my stomach two hours back"},
    "cc.duration": {"tap": "today"}, "hpi.site": {"tap": "abdomen"},
    "hpi.onset": {"tap": "sudden"}, "hpi.character": {"tap": "sharp"},
    "hpi.severity": {"tap": 9}, "hpi.associated": {"tap": ["vomiting", "sweating"]},
    "hpi.timing": {"tap": "constant"}},
  expected={"hpi.site": "abdomen", "hpi.onset": "sudden", "hpi.severity": 9},
  flags=["RF-ABDO-01", "RF-PAIN-01"], priority="immediate")

script("s12-pancreatitis", "Abdominal pain radiating to the back", difficulty="emergency", age=46,
  gender="male",
  turns={"cc.text": {"tap": "stomach"}, "hpi.site": {"tap": "abdomen"},
    "hpi.radiation": {"utterance": "it goes straight through to my back"},
    "hpi.character": {"tap": "sharp"}, "hpi.severity": {"tap": 8},
    "ph.alcohol": {"tap": "daily"}, "hpi.onset": {"tap": "sudden"},
    "hpi.associated": {"tap": ["vomiting"]}},
  expected={"hpi.radiation": "back", "hpi.site": "abdomen"},
  flags=["RF-ABDO-01", "RF-ABDO-02"], priority="immediate")

script("s13-orthopnoea", "Heart failure decompensation", difficulty="emergency", age=74,
  gender="female",
  turns={"cc.text": {"utterance": "I get breathless when I lie down and my feet are swollen"},
    "hpi.site": {"tap": "chest"}, "hpi.associated": {"tap": ["breathlessness"]},
    "hpi.severity": {"tap": 6}, "pmh.conditions": {"tap": ["heart", "hypertension"]},
    "ros.cardio": {"tap": ["orthopnoea", "ankle_swelling"]}},
  expected={"review_of_systems.cardiovascular": ["orthopnoea", "ankle_swelling"]},
  flags=["RF-CARD-03", "RF-RESP-01"], priority="immediate")

script("s14-haemoptysis-tb", "Cough with blood, TB screen", difficulty="emergency", age=29,
  gender="male",
  turns={"cc.text": {"utterance": "khansi teen hafte se hai aur balgam me khoon aa raha hai"},
    "cc.duration": {"tap": "weeks_2_4"}, "hpi.site": {"tap": "chest"},
    "hpi.associated": {"tap": ["weight_loss"]}, "hpi.severity": {"tap": 5},
    "ros.resp": {"tap": ["cough_3wk", "haemoptysis", "night_sweats"]},
    "ros.general": {"tap": ["weight_loss", "night_sweats"]}},
  expected={"chief_complaint.text": "cough",
    "review_of_systems.respiratory": ["cough_3wk", "haemoptysis", "night_sweats"]},
  flags=["RF-BLEED-02", "RF-RESP-02", "RF-SYS-01"], priority="urgent",
  notes="National TB obligation. Hinglish narration on the chief complaint.")

script("s15-dysphagia", "New difficulty swallowing", difficulty="emergency", age=63, gender="male",
  turns={"cc.text": {"utterance": "food gets stuck when I swallow"},
    "cc.duration": {"tap": "months_1_6"}, "hpi.site": {"tap": "throat"},
    "hpi.associated": {"tap": ["weight_loss"]}, "hpi.severity": {"tap": 5},
    "ph.tobacco": {"tap": "current_both"}, "ph.alcohol": {"tap": "daily"},
    "ros.gi": {"tap": ["swallowing", "weight_loss"]}},
  expected={"review_of_systems.gastrointestinal": ["swallowing", "weight_loss"]},
  flags=["RF-SYS-04", "RF-SYS-01"], priority="urgent")

script("s16-seizure", "First seizure", difficulty="emergency", age=24, gender="female",
  turns={"cc.text": {"utterance": "I had a fit yesterday, my family saw it"},
    "cc.duration": {"tap": "days_1_3"}, "hpi.site": {"tap": "head"},
    "hpi.onset": {"tap": "sudden"}, "hpi.severity": {"tap": 5},
    "ros.neuro": {"tap": ["fits"]}},
  expected={"review_of_systems.neurological": ["fits"]},
  flags=["RF-NEURO-04"], priority="urgent")

script("s17-haematuria", "Blood in the urine", difficulty="emergency", age=59, gender="male",
  turns={"cc.text": {"utterance": "there is blood coming in my urine"},
    "cc.duration": {"tap": "week_1"}, "hpi.site": {"tap": "abdomen"},
    "hpi.severity": {"tap": 3}, "ph.tobacco": {"tap": "current_smoke"},
    "ros.gu": {"tap": ["haematuria", "frequency"]}},
  expected={"review_of_systems.genitourinary": ["haematuria", "frequency"]},
  flags=["RF-BLEED-03"], priority="urgent")

# ═══════════════════════════════════════════════════════ ROUTINE (18–29)

script("s18-knee-oa", "Chronic knee pain", difficulty="plain", age=62, gender="female",
  turns={"cc.text": {"utterance": "my knees pain when I walk, since many months"},
    "cc.duration": {"tap": "months_6_plus"}, "hpi.site": {"tap": "joints"},
    "hpi.character": {"tap": "dull"}, "hpi.severity": {"tap": 5},
    "hpi.exacerbating": {"tap": ["worse_movement", "better_rest"]},
    "ros.msk": {"tap": ["joint_pain", "morning_stiffness"]}},
  expected={"chief_complaint.text": "pain", "hpi.site": "joints"},
  forbidden=["RF-CARD-01", "RF-NEURO-01", "RF-BLEED-01"], priority="routine")

script("s19-acidity", "Acidity", difficulty="plain", age=35, gender="male",
  turns={"cc.text": {"utterance": "burning in my stomach after eating"},
    "cc.duration": {"tap": "weeks_2_4"}, "hpi.site": {"tap": "abdomen"},
    "hpi.character": {"tap": "burning"}, "hpi.severity": {"tap": 4},
    "hpi.exacerbating": {"tap": ["worse_food"]}},
  expected={"hpi.character": "burning", "hpi.site": "abdomen"},
  forbidden=["RF-ABDO-01", "RF-BLEED-01"], priority="routine")

script("s20-routine-checkup", "Routine check-up, nothing wrong", difficulty="plain", age=40,
  gender="male",
  turns={"cc.text": {"tap": "checkup"}, "cc.duration": {"tap": "months_6_plus"},
    "hpi.site": {"tap": "whole_body"}, "hpi.severity": {"tap": 0}},
  expected={"chief_complaint.text": "checkup", "hpi.severity": 0},
  forbidden=["RF-CARD-01", "RF-PAIN-01", "RF-RESP-01"], priority="routine",
  notes="Everything normal. Must fire nothing at all.")

script("s21-migraine", "Migraine", difficulty="plain", age=31, gender="female",
  turns={"cc.text": {"utterance": "headache on one side with light bothering me"},
    "cc.duration": {"tap": "months_1_6"}, "hpi.site": {"tap": "head"},
    "hpi.character": {"tap": "throbbing"}, "hpi.onset": {"tap": "gradual"},
    "hpi.severity": {"tap": 6}, "hpi.timing": {"tap": "intermittent"},
    "ros.neuro": {"tap": ["headache"]}},
  expected={"hpi.site": "head", "hpi.character": "throbbing"},
  forbidden=["RF-NEURO-02"], priority="routine",
  notes="Headache WITHOUT thunderclap features. A rule that fires here is too loose.")

script("s22-diabetes-followup", "Diabetes follow-up", difficulty="plain", age=55, gender="male",
  turns={"cc.text": {"tap": "checkup"}, "hpi.site": {"tap": "whole_body"},
    "hpi.severity": {"tap": 1},
    "pmh.conditions": {"utterance": "I have sugar since ten years"},
    "med.taking": {"tap": True},
    "med.list": {"utterance": "metformin five hundred twice a day"},
    "ros.gu": {"tap": ["nocturia"]}},
  expected={"past_medical.conditions": ["diabetes"], "drug_allergy.taking_medicines": True},
  priority="routine")

script("s23-anaemia", "Tiredness and pallor", difficulty="plain", age=26, gender="female",
  turns={"cc.text": {"utterance": "I feel very weak and tired all the time"},
    "cc.duration": {"tap": "months_1_6"}, "hpi.site": {"tap": "whole_body"},
    "hpi.severity": {"tap": 4}, "ph.diet": {"tap": "veg"},
    "ros.general": {"tap": ["fatigue"]}},
  expected={"chief_complaint.text": "weakness"},
  forbidden=["RF-SYS-01"], priority="routine",
  notes="Fatigue WITHOUT weight loss. RF-SYS-01 must not fire on tiredness alone.")

script("s24-skin", "Itchy rash", difficulty="plain", age=22, gender="male",
  turns={"cc.text": {"tap": "skin"}, "cc.duration": {"tap": "week_1"},
    "hpi.site": {"tap": "limbs"}, "hpi.character": {"tap": "tingling"},
    "hpi.severity": {"tap": 3}, "ros.general": {"tap": ["rash"]}},
  expected={"chief_complaint.text": "skin"}, priority="routine")

script("s25-back-pain", "Mechanical low back pain", difficulty="plain", age=38, gender="male",
  turns={"cc.text": {"utterance": "pain in my lower back since I lifted a heavy sack"},
    "cc.duration": {"tap": "week_1"}, "hpi.site": {"tap": "back"},
    "hpi.onset": {"tap": "after_event"}, "hpi.character": {"tap": "dull"},
    "hpi.severity": {"tap": 5}, "hpi.exacerbating": {"tap": ["worse_movement", "better_rest"]},
    "ph.occupation": {"tap": "labour"}, "ros.msk": {"tap": ["back_pain"]}},
  expected={"hpi.site": "back", "hpi.onset": "after_event"},
  forbidden=["RF-ABDO-02"], priority="routine")

script("s26-hypothyroid", "Thyroid follow-up", difficulty="plain", age=43, gender="female",
  turns={"cc.text": {"tap": "weakness"}, "hpi.site": {"tap": "whole_body"},
    "hpi.severity": {"tap": 2}, "pmh.conditions": {"tap": ["thyroid"]},
    "med.taking": {"tap": True}, "med.list": {"utterance": "thyronorm fifty micrograms"},
    "ph.sleep": {"tap": "insufficient"}, "ph.bowel": {"tap": "constipated"}},
  expected={"past_medical.conditions": ["thyroid"]}, priority="routine")

script("s27-copd-stable", "Stable COPD", difficulty="plain", age=67, gender="male",
  turns={"cc.text": {"tap": "cough"}, "cc.duration": {"tap": "months_6_plus"},
    "hpi.site": {"tap": "chest"}, "hpi.severity": {"tap": 3},
    "pmh.conditions": {"tap": ["asthma"]}, "ph.tobacco": {"tap": "former"},
    "ros.resp": {"tap": ["cough", "wheeze"]}},
  expected={"review_of_systems.respiratory": ["cough", "wheeze"]},
  forbidden=["RF-RESP-02", "RF-BLEED-02"], priority="routine",
  notes="Chronic cough WITHOUT the 3-week + constitutional combination.")

script("s28-cataract", "Failing eyesight, gradual", difficulty="plain", age=70, gender="female",
  turns={"cc.text": {"utterance": "my eyesight has slowly become blurry over the last year"},
    "cc.duration": {"tap": "months_6_plus"}, "hpi.site": {"tap": "head"},
    "hpi.onset": {"tap": "gradual"}, "hpi.severity": {"tap": 3}},
  expected={"hpi.onset": "gradual"},
  forbidden=["RF-NEURO-01"], priority="routine",
  notes="GRADUAL vision change. RF-NEURO-01 covers sudden loss only.")

script("s29-constipation", "Constipation", difficulty="plain", age=48, gender="female",
  turns={"cc.text": {"tap": "stomach"}, "cc.duration": {"tap": "months_1_6"},
    "hpi.site": {"tap": "abdomen"}, "hpi.severity": {"tap": 3},
    "ph.bowel": {"tap": "constipated"}, "ph.diet": {"tap": "veg"}},
  expected={"personal_history.bowel": "constipated"}, priority="routine")


# ═══════════════════════════════════════════════════════ LOW LITERACY / HINGLISH (30–37)

script("s30-hinglish-chest", "Chest pain narrated in Hinglish", difficulty="low_literacy",
  age=57, gender="male", language="hi",
  turns={"cc.text": {"utterance": "mere chhaati mein bahut dard ho raha hai subah se"},
    "cc.duration": {"tap": "today"},
    "hpi.site": {"utterance": "yahan chhaati ke beech mein"},
    "hpi.onset": {"utterance": "bilkul achanak shuru hua tha"},
    "hpi.character": {"utterance": "aisa lagta hai jaise koi bhaari cheez rakhi ho"},
    "hpi.radiation": {"utterance": "baayen haath mein bhi jaata hai"},
    "hpi.associated": {"utterance": "thanda paseena aa raha tha aur saans phool rahi thi"},
    "hpi.severity": {"tap": 8},
    "pmh.conditions": {"utterance": "doctor ne kaha tha sugar hai aur bp bhi high rehta hai"},
    "ph.tobacco": {"utterance": "haan main bidi peeta hoon"}},
  expected={"chief_complaint.text": "pain", "hpi.site": "chest", "hpi.onset": "sudden",
    "hpi.character": "pressure", "hpi.radiation": "left_arm",
    "past_medical.conditions": ["diabetes", "hypertension"],
    "personal_history.tobacco": "current_smoke"},
  flags=["RF-CARD-01", "RF-RESP-01"], priority="immediate",
  notes="Every clinically load-bearing answer arrives as Hinglish narration, not a tap. "
        "Severity is 8, so RF-PAIN-01 (>=9) correctly does NOT fire — an earlier draft of "
        "this script expected it, and the eval caught the script being wrong, not the rule.")

script("s31-lowlit-gutka", "Tobacco described the way people describe it",
  difficulty="low_literacy", age=45, gender="male", language="hi",
  turns={"cc.text": {"utterance": "gale mein takleef hai"},
    "hpi.site": {"utterance": "gala"}, "hpi.severity": {"tap": 4},
    "ph.tobacco": {"utterance": "main gutka khata hoon din me chaar paanch baar"},
    "ph.alcohol": {"utterance": "kabhi kabhi peeta hoon"}},
  expected={"hpi.site": "throat", "personal_history.tobacco": "current_chew",
    "personal_history.alcohol": "occasional"},
  priority="routine",
  notes="Nobody says 'I chew tobacco'. They say gutka, khaini, zarda.")

script("s32-lowlit-melaena", "Black stool described in plain words",
  difficulty="low_literacy", age=53, gender="male", language="hi",
  turns={"cc.text": {"utterance": "pet mein dard hai"},
    "hpi.site": {"utterance": "pet"}, "hpi.severity": {"tap": 6},
    "ros.gi": {"utterance": "kala pakhana aa raha hai teen din se"}},
  expected={"hpi.site": "abdomen", "review_of_systems.gastrointestinal": ["melaena"]},
  flags=["RF-BLEED-01"], priority="immediate",
  notes="An emergency that only reaches the rules if the narration is understood.")

script("s33-lowlit-negation", "A firm no, phrased the long way", difficulty="low_literacy",
  age=60, gender="female", language="hi",
  turns={"cc.text": {"utterance": "kamzori lagti hai"},
    "hpi.site": {"utterance": "poore shareer mein"}, "hpi.severity": {"tap": 3},
    "med.taking": {"utterance": "nahin, main koi dawa nahin leti"},
    "ph.tobacco": {"utterance": "kabhi nahin, main tambaku nahin leti"}},
  expected={"hpi.site": "whole_body", "drug_allergy.taking_medicines": False,
    "personal_history.tobacco": "never"},
  priority="routine",
  notes="Reading this as a yes invents a medication list out of nothing.")

script("s34-lowlit-breathless", "Breathlessness in plain Hindi", difficulty="low_literacy",
  age=64, gender="female", language="hi",
  turns={"cc.text": {"utterance": "saans phoolti hai chalne par"},
    "hpi.site": {"utterance": "chhaati"}, "hpi.severity": {"tap": 6},
    "hpi.associated": {"utterance": "saans phool jaati hai aur chakkar bhi aata hai"},
    "hpi.exacerbating": {"utterance": "chalne se aur mehnat se badhta hai"}},
  expected={"hpi.site": "chest", "chief_complaint.text": "cough"},
  flags=["RF-RESP-01"], priority="immediate")

script("s35-lowlit-fever", "Long fever with sweats", difficulty="low_literacy", age=34,
  gender="male", language="hi",
  turns={"cc.text": {"utterance": "bukhar hai das din se"}, "cc.duration": {"tap": "weeks_2_4"},
    "hpi.site": {"utterance": "poore shareer mein"}, "hpi.severity": {"tap": 5},
    "ros.resp": {"utterance": "khansi bhi hai teen hafte se aur raat me paseena aata hai"},
    "ros.general": {"tap": ["fever_persistent", "weight_loss"]}},
  expected={"chief_complaint.text": "fever",
    "review_of_systems.respiratory": ["cough_3wk", "night_sweats"]},
  flags=["RF-RESP-02", "RF-SYS-01"], priority="urgent")

script("s36-lowlit-joint", "Joint pain, rural phrasing", difficulty="low_literacy", age=58,
  gender="female", language="hi",
  turns={"cc.text": {"utterance": "ghutno mein dard rehta hai"},
    "hpi.site": {"utterance": "jod, ghutna dono"}, "hpi.severity": {"tap": 5},
    "ph.occupation": {"tap": "farming"}, "ros.msk": {"tap": ["joint_pain", "walking_difficulty"]}},
  expected={"hpi.site": "joints", "chief_complaint.text": "pain"},
  forbidden=["RF-CARD-01"], priority="routine")

script("s37-lowlit-dizzy", "Dizziness and fainting", difficulty="low_literacy", age=72,
  gender="male", language="hi",
  turns={"cc.text": {"utterance": "chakkar aata hai aur ek baar gir gaya tha"},
    "hpi.site": {"utterance": "sar"}, "hpi.severity": {"tap": 6},
    "hpi.associated": {"utterance": "chakkar aa raha tha"},
    "ros.neuro": {"tap": ["fainting", "headache"]}},
  expected={"hpi.site": "head"},
  flags=["RF-SYS-03"], priority="urgent")

# ═══════════════════════════════════════════════════════ RAMBLING (38–42)

script("s38-rambling-elderly", "A long story with the symptom buried in it",
  difficulty="rambling", age=78, gender="female",
  turns={"cc.text": {"utterance": "well it started when my grandson came to visit, we had gone to the temple that day and it was very hot, and afterwards I felt this pain in my chest, my daughter said I should come but I said no it is nothing"},
    "cc.duration": {"tap": "days_1_3"},
    "hpi.site": {"utterance": "in my chest, here, where I showed you"},
    "hpi.onset": {"utterance": "slowly over a few days I think, it is hard to say"},
    "hpi.character": {"utterance": "a heavy feeling, like pressure, not sharp"},
    "hpi.associated": {"utterance": "some sweating, yes, cold sweating in the night"},
    "hpi.severity": {"tap": 6}},
  expected={"hpi.site": "chest", "hpi.character": "pressure", "hpi.onset": "gradual"},
  flags=["RF-CARD-01"], priority="immediate",
  notes="Length is the difficulty. The span recorded must be the six words that matter.")

script("s39-rambling-family", "Answers about a relative, not themselves", difficulty="rambling",
  age=50, gender="male",
  turns={"cc.text": {"utterance": "my brother had a heart attack last year and I am worried, but for me it is just this stomach problem"},
    "hpi.site": {"utterance": "my stomach"}, "hpi.severity": {"tap": 3},
    "hpi.character": {"tap": "burning"},
    "fh.conditions": {"tap": ["heart"]}},
  expected={"hpi.site": "abdomen", "family_history.conditions": ["heart"]},
  forbidden=["RF-CARD-01"], priority="routine",
  notes="The brother's heart attack must not become the patient's chest pain.")

script("s40-rambling-multiple", "Several complaints at once", difficulty="rambling", age=61,
  gender="female",
  turns={"cc.text": {"utterance": "my knees pain, and I have gas problem, and sometimes headache also, and my sleep is not good"},
    "hpi.site": {"tap": "joints"}, "hpi.severity": {"tap": 5},
    "ph.sleep": {"tap": "difficulty"}, "ros.msk": {"tap": ["joint_pain"]},
    "ros.neuro": {"tap": ["headache"]}},
  expected={"hpi.site": "joints", "personal_history.sleep": "difficulty"},
  priority="routine",
  notes="Multiple complaints; the chief one is whatever the patient names first.")

script("s41-rambling-treatment", "Recites their whole treatment history", difficulty="rambling",
  age=55, gender="male",
  turns={"cc.text": {"utterance": "I went to a doctor in the village, he gave some tablets, then I went to the town hospital, they did tests, then I took ayurvedic medicine also, and still this cough is there"},
    "cc.duration": {"tap": "months_1_6"}, "hpi.site": {"tap": "chest"},
    "hpi.severity": {"tap": 4}, "med.taking": {"tap": True},
    "med.ayush_taking": {"tap": True},
    "ros.resp": {"tap": ["cough", "cough_3wk"]},
    "ros.general": {"tap": ["weight_loss"]}},
  expected={"chief_complaint.text": "cough", "drug_allergy.ayush_medicines": True},
  flags=["RF-RESP-02", "RF-SYS-01"], priority="urgent")

script("s42-rambling-vague", "Cannot describe the problem at all", difficulty="rambling", age=44,
  gender="female",
  turns={"cc.text": {"utterance": "I just do not feel right, something is wrong but I cannot say what"},
    "hpi.site": {"tap": "whole_body"}, "hpi.severity": {"tap": 4},
    "hpi.character": {"tap": "dull"}},
  expected={"hpi.site": "whole_body"},
  priority="routine",
  notes="Genuinely unstructurable narration. Must be kept verbatim, not forced into a slot.")

# ═══════════════════════════════════════════════════════ CONTRADICTORY (43–46)

script("s43-contradiction-duration", "Contradicts themselves about duration",
  difficulty="contradictory", age=47, gender="male",
  turns={"cc.text": {"utterance": "pain in my chest for about three days"},
    "cc.duration": {"tap": "week_1"},
    "hpi.site": {"tap": "chest"}, "hpi.severity": {"tap": 6},
    "hpi.associated": {"tap": ["sweating"]}},
  expected={"chief_complaint.duration": "week_1", "hpi.site": "chest"},
  flags=["RF-CARD-01"], priority="immediate",
  notes="Both answers must survive: the latest as the value, the earlier as superseded.")

script("s44-contradiction-tobacco", "Says never, then admits occasionally",
  difficulty="contradictory", age=39, gender="male",
  turns={"cc.text": {"tap": "cough"}, "hpi.site": {"tap": "chest"},
    "hpi.severity": {"tap": 3},
    "ph.tobacco": {"utterance": "no I never smoke"},
    "ros.resp": {"tap": ["cough"]}},
  expected={"personal_history.tobacco": "never"},
  priority="routine",
  notes="A single recorded answer with its exact source. The physician resolves the rest.")

script("s45-contradiction-allergy", "Unsure about an allergy", difficulty="contradictory",
  age=52, gender="female",
  turns={"cc.text": {"tap": "fever"}, "hpi.site": {"tap": "whole_body"},
    "hpi.severity": {"tap": 4},
    "allergy.any": {"tap": True},
    "allergy.what": {"utterance": "some injection, I do not remember the name"},
    "allergy.reaction": {"tap": "rash"},
    "ros.general": {"tap": ["fever"]}},
  expected={"drug_allergy.has_allergy": True, "drug_allergy.allergy_reaction": "rash"},
  forbidden=["RF-SYS-02"], priority="routine",
  notes="Rash only. RF-SYS-02 is for airway compromise and must not fire here.")

script("s46-contradiction-severity", "Says it is nothing, rates it 9",
  difficulty="contradictory", age=66, gender="male",
  turns={"cc.text": {"utterance": "it is nothing really, just a small pain"},
    "hpi.site": {"tap": "abdomen"}, "hpi.severity": {"tap": 9},
    "hpi.onset": {"tap": "sudden"}, "hpi.character": {"tap": "sharp"}},
  expected={"hpi.severity": 9, "hpi.site": "abdomen"},
  flags=["RF-ABDO-01", "RF-PAIN-01"], priority="immediate",
  notes="The tapped 9 is the recorded fact. Stoicism must not lower a priority.")

# ═══════════════════════════════════════════════════════ DECLINE / AYUSH / MIXED (47–50)

script("s47-declines", "Declines several personal questions", difficulty="mixed", age=29,
  gender="female",
  turns={"cc.text": {"tap": "stomach"}, "hpi.site": {"tap": "abdomen"},
    "hpi.severity": {"tap": 4},
    "ph.alcohol": {"decline": True},
    "ph.pregnancy": {"decline": True},
    "ph.tobacco": {"decline": True}},
  expected={"hpi.site": "abdomen"},
  declined=["personal_history.alcohol", "personal_history.pregnancy",
    "personal_history.tobacco"],
  priority="routine",
  notes="Declining must record an absence, never a value, and never a 'no'.")

script("s48-ayush-vata", "AYUSH extended interview", difficulty="mixed", age=68, gender="male",
  ayush=True,
  turns={"cc.text": {"utterance": "gas and constipation, and my joints pain"},
    "hpi.site": {"tap": "abdomen"}, "hpi.severity": {"tap": 4},
    "ph.bowel": {"tap": "constipated"},
    "ayush.prakriti_build": {"tap": "thin_light"},
    "ayush.vikriti": {"tap": "dryness_gas"},
    "ayush.agni": {"tap": "vishama"},
    "ayush.koshtha": {"tap": "krura"},
    "ayush.vyayama_shakti": {"tap": "avara"}},
  expected={"ayush.prakriti_build": "thin_light", "ayush.vikriti": "dryness_gas",
    "ayush.agni": "vishama", "ayush.koshtha": "krura", "ayush.vaya": "vriddha"},
  priority="routine",
  notes="Vaya is DERIVED from age 68, never asked. Every AYUSH answer must carry a code.")

script("s49-ayush-hinglish", "AYUSH interview in Hinglish", difficulty="mixed", age=41,
  gender="female", language="hi", ayush=True,
  turns={"cc.text": {"utterance": "pet mein jalan rehti hai"},
    "hpi.site": {"utterance": "pet"}, "hpi.character": {"utterance": "jalan hoti hai"},
    "hpi.severity": {"tap": 5},
    "ayush.agni": {"utterance": "hamesha bhookh lagti hai, bahut tez"},
    "ayush.koshtha": {"utterance": "aasani se ho jata hai"},
    "ayush.vikriti": {"tap": "burning_acid"}},
  expected={"hpi.site": "abdomen", "hpi.character": "burning", "ayush.agni": "tikshna",
    "ayush.koshtha": "mridu", "ayush.vaya": "madhya"},
  priority="routine")

script("s50-noisy-asr", "Speech recognition fails on half the answers", difficulty="mixed",
  age=59, gender="male",
  turns={"cc.text": {"utterance": "chest pain", "asr_confidence": 0.31},
    "hpi.site": {"tap": "chest"},
    "hpi.onset": {"utterance": "suddenly", "asr_confidence": 0.18},
    "hpi.character": {"tap": "pressure"},
    "hpi.associated": {"tap": ["sweating"]},
    "hpi.severity": {"tap": 7}},
  expected={"hpi.site": "chest", "hpi.character": "pressure"},
  flags=["RF-CARD-01"], priority="immediate",
  notes="Low ASR confidence must degrade to touch and record NOTHING from those turns. "
        "The emergency must still be caught, because the tapped answers still arrive.")

print(f"wrote {len(list(OUT.glob('*.json')))} scripts total")
