# Swastra — the two-minute demo

Read `docs/DEMO-DAY.md` the morning of. This file is the script itself.

**Live:** https://medi-kiosk-fe.vercel.app

---

## Before you stand up — 3 minutes of warm-up

Do this **~2 minutes before** you present, not the night before.

```bash
# 1. Wake the backend. Free tier sleeps after 15 minutes idle; the first request
#    after a sleep takes 30–60 seconds and looks like a hang.
curl https://medikiosk-api-docker.onrender.com/about

# 2. Confirm you are on the real database. This must say true.
curl -s https://medikiosk-api-docker.onrender.com/about | grep -o '"isSupabase":[a-z]*'
```

Then, in the browser you will present from:

1. Open **https://medi-kiosk-fe.vercel.app** and press **Try demo**. Wait for the violet
   `DEMO — SYNTHETIC DATA` bar.
2. Go to the brief and **click one document-sourced line**. The first evidence crop
   rasterises a PDF page server-side and took **4.8 s** measured on the free tier. It is
   cached afterwards. Do this now so the one the audience watches is instant.
3. Press **Reset demo**. You are now warm and back at a clean starting state.

**Checklist before you speak**

- [ ] `/about` returned 200 quickly (not a 40-second wait)
- [ ] `"isSupabase":true`
- [ ] the demo bar is visible
- [ ] one evidence crop has been opened once
- [ ] Reset pressed — starting state is clean

---

## The script — under two minutes

> Times are the pace to aim for, not a countdown. If you have longer, the labs trend and the
> contradictions panel are the next two things worth showing.

### 0:00 — "No account, no app, no typing." *(15s)*

Open the hero. Press **Try demo**.

Say: *"A patient walks up to a kiosk. There is no login, no app to install. This record is
synthetic and the banner says so on every screen — that is not a demo shortcut, it is a
boundary the database enforces."*

While it builds (real OCR and real speech recognition are running), that sentence covers it.

### 0:20 — The catch. **This is the strongest beat.** *(35s)*

Go to the brief. Find **AMLODIPINE SMG** in *Medicines on the patient's papers*. Click it.

Say: *"The prescription says AMLODIPINE **5MG**. The OCR read **SMG** — a five taken for an
S. Look at the confidence: **0.94**. The engine is not unsure. It is confident and wrong."*

Point at the cropped page region beside it.

> **The line that lands:** *"Every system that routes 'uncertain' readings to a human lets
> this one through. Only a person comparing the reading against the source catches it — and
> 5mg and 10mg amlodipine are both ordinary doses, so a misread digit is a different
> prescription, not a typo."*

### 0:55 — What changed? *(25s)*

Scroll to **What changed?** at the top of the brief.

Say: *"This patient was here before. Six things are new, six are unchanged, and it names the
visit it compared against — the 20th of August 2025. No score, no ranking. A recorded feature
is present in one visit and not the other; that is the whole test."*

Point at **Same as before**: *"That column is the one clinicians ask for. A complaint in its
third visit is the most useful thing on a follow-up screen, and it is invisible if you only
show differences."*

### 1:20 — Click-to-source. *(25s)*

Click a **spoken** line — *"burning pain in my stomach for about a week"*.

Say: *"That is the transcript, with the recognition confidence the engine actually gave it.
Not a number we chose — where no engine measured one, this says 'not measured' rather than
showing a zero."*

Then click a **document** line: *"And this opens the exact region of the page it was read
from. Every clinical line on this screen carries the source it came from. If a line has no
evidence, it does not appear at all."*

### 1:45 — The two reports. *(15s)*

Press **Download doctor's report** and **Download my copy**.

Say: *"Both rendered server-side from the same payload — real selectable text, not a
screenshot. Every page carries the demo marking and a footer saying this is a
pre-consultation history and **not a diagnosis**. The patient's copy has no internal
identifiers in it at all."*

### 2:00 — Reset

Press **Reset demo** → **Yes, reset**. Back to an identical starting state for the next
person.

---

## If something goes wrong

### The backend cold-started mid-demo

You will see **"Waking the server… this can take up to a minute on first load."**

Say, without apologising: *"That is the free hosting tier waking up — the product is telling
you honestly what it is doing rather than showing a spinner that looks like a crash. It is
the same message a patient would get."*

Then keep talking through the architecture until it clears. It will.

### The venue network blocks port 5432

Symptom: the backend cannot reach Supabase at all. Check first:

```bash
python3 -c "import socket; socket.create_connection(('portquiz.net', 5432), timeout=8)"
```

A `TimeoutError` means 5432 is blocked and **no** Supabase endpoint will work — not the
pooler either. Switch to the local database:

```bash
make demo-local-up                     # Postgres 17 on 5433, migrated
DEMO_LOCAL_DB=true make demo           # start the stack against it
```

**What you will see, and what to say:** a rose hazard-striped bar reading
`LOCAL DEMO DATABASE — Running on a local Postgres (127.0.0.1:5433), not Supabase.`

It is deliberate. Say so: *"That bar is there so nobody can present local data as the hosted
project by accident. The application refuses to start on a silent fallback."*

Everything in the script above still works. Guest mode, OCR, the brief, both PDFs — all of it
runs locally.

### Something else broke

The demo is not the only artefact. `docs/EVALUATION.md` reports the held-out numbers,
`/about` lists every invariant and every mocked component by name, and `make e2e` runs the
whole path including this script's route as `gate5.mjs`.

---

## Questions you will be asked

**"Is this a real ABDM integration?"**
No, and it never claims to be. The identity path is a **mock** ABHA issuer, labelled as mock
in `/about`, in the token itself, and in an amber bar on screen. Scope was set by the problem
statement.

**"Does it diagnose?"**
No. Invariant 1, and there is a test that fails the build if any endpoint returns an
assessment, a differential or a probability. Every number on the brief is a recorded
measurement or arithmetic between recorded measurements.

**"Where does the demo data come from?"**
It is generated by the same code path a real upload takes — real Tesseract over a real
fixture, real Vosk over a real WAV. The audio is synthetic (macOS `say`); the recognition is
not, and `data/fixtures/audio/*.json` records exactly which is which.

**"Could a demo record contaminate a real patient's history?"**
No, and it is enforced in the query layer rather than by convention. See
`app/modules/encounter/cohort.py`. The boundary is symmetric — the direction that matters is
a *clinician* being shown a "similar previous visit" that was invented for a conference — and
`tests/test_synthetic_boundary.py` builds two clinically identical patients on opposite sides
to prove it.
