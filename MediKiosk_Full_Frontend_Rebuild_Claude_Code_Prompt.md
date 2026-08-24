# MediKiosk — Full Frontend Rebuild Prompt for Claude Code

## Objective

Completely redesign and rebuild the **entire MediKiosk frontend from scratch**.

The current frontend is no longer the visual direction I want.

Create a **brand-new frontend experience** that feels:

- premium
- exotic
- futuristic
- elegant
- highly interactive
- visually memorable
- polished
- modern health-tech
- presentation-ready
- hackathon-winning

Do **not** make it look like:

- a government portal
- a hospital ERP
- a generic SaaS dashboard
- a chatbot
- ChatGPT
- WhatsApp
- a plain medical form
- a basic student project
- an outdated institutional website

The final product should feel like a **next-generation health-tech platform**.

---

# Important Boundaries

You may completely replace the current frontend visual implementation.

However:

- preserve working backend APIs
- preserve Supabase integration
- preserve OCR logic
- preserve voice logic
- preserve clinical state-machine logic
- preserve provenance
- preserve red-flag logic
- preserve physician confirmation
- preserve FHIR logic
- preserve existing data contracts wherever possible

Do not redesign backend architecture during this task unless a frontend requirement exposes a genuinely missing API.

Before deleting/replacing the current frontend:

1. create a safe git checkpoint/commit;
2. verify the current app can still be restored;
3. then rebuild the visual layer.

Preserve functionality, **not old styling**.

---

# Use the Connected Design Tools

Actively use the connected tools and skills available in Claude Code, including where useful:

- Figma MCP
- Motion MCP / Motion plugins
- Motion skills
- UI/UX Pro Max skill
- Higgsfield MCP
- Canva MCP
- Supabase MCP where frontend data structures need inspection
- Vercel MCP where deployment compatibility matters

Do not merely mention these tools.

Use them where they can materially improve:

- hierarchy
- interaction design
- animation
- transitions
- layout
- responsiveness
- component quality
- visual consistency
- premium feel

Do not give me a long design essay first.

Inspect the existing frontend structure, then start rebuilding.

---

# Core Product Principle

The frontend must communicate that MediKiosk is:

> A multilingual longitudinal clinical-memory and pre-consultation intake platform.

It must **not** visually communicate:

> AI chatbot asking medical questions.

The product should feel like an advanced digital health experience where:

```text
Patient Identity
→ Clinical Memory
→ New Visit
→ Guided Intake
→ Voice / Touch / Text
→ Previous Records
→ OCR
→ Timeline
→ Doctor Review
→ Longitudinal Health History
```

---

# Build a New Design System

Create a completely new design system for the product.

Define and consistently use:

- typography scale
- spacing scale
- border radius system
- elevation/depth system
- surface hierarchy
- color tokens
- semantic colors
- icon system
- button variants
- input variants
- cards
- badges
- chips
- tabs
- dropdowns
- segmented controls
- switches
- tooltips
- drawers
- modals
- sheets
- toast system
- warnings
- red flags
- success states
- error states
- empty states
- loading states
- skeleton loaders
- progress states
- document states
- microphone states
- OCR states
- TTS states

Use reusable primitives.

Do not create random one-off visual styles on every page.

---

# Visual Direction

The visual identity should feel premium and unique to MediKiosk.

Use modern visual techniques only where they improve the experience:

- layered surfaces
- refined gradients
- subtle depth
- glass effects where tasteful
- soft shadows
- blur
- visual hierarchy
- ambient background treatments
- polished icons
- premium micro-interactions
- animated state transitions
- smooth panel expansion
- smooth route transitions
- refined typography

Do not over-design.

Premium means:

> controlled, coherent, refined and intentional.

Not:

> flashy, noisy or overloaded.

---

# Motion and Interaction System

Motion should be a major part of the product.

Create a consistent motion system.

Use animation for:

- route transitions
- page entry
- page exit
- cards
- hover states
- button press
- button loading
- question transition
- back navigation
- progress movement
- accordions
- tabs
- timeline expansion
- drawer opening
- evidence panels
- modal opening
- confirmation state
- warning state
- success state
- OCR progress
- camera state
- microphone state
- listening state
- transcript state
- TTS speaking state
- document extraction
- timeline insertion
- physician confirmation
- FHIR success
- loading skeletons
- empty states

Animations should feel smooth, responsive, subtle, premium and purposeful.

Avoid unnecessary looping animation.

Support `prefers-reduced-motion`.

---

# Patient-Side Experience

The patient side should feel:

- calm
- premium
- simple
- guided
- friendly
- immersive
- extremely easy to understand

Do not make the patient see a dense dashboard.

Do not make the experience look like chat bubbles.

The patient journey should feel like a sequence of beautiful guided states.

---

# Patient Home / Clinical Memory

Create a premium patient home screen.

It should clearly show:

- patient identity
- previous visits
- prescriptions
- reports
- medications
- recent timeline
- last visit
- start new visit

The main visual message should be:

> This patient already has a health history here.

Possible high-level sections:

```text
Patient
Clinical Memory
Recent History
Documents
Medications
Start New Visit
```

Use elegant timeline previews and animated cards.

Do not make it look like an admin dashboard.

---

# Start New Visit

The transition from patient memory to new visit should feel deliberate and immersive.

Use a transition that visually communicates:

```text
Existing history
→ New encounter begins
```

Avoid abrupt page replacement.

---

# Consent Screen

Completely redesign the current consent screen.

The current version is too bulky and hard to understand.

Use a compact permission experience.

Structure:

```text
Before we begin

Required
✓ Today's health history

Optional
[ toggle ] Use microphone
[ toggle ] Scan prescriptions/reports
[ toggle ] Save doctor-approved record
[ toggle ] AYUSH extended questions

[ Hear this page ]

[ Start intake ]
```

Make it visually simple.

Avoid giant Yes/No cards, repeated oversized “Read aloud” buttons, long paragraphs, confusing toggles and clutter.

The user should understand the page in seconds.

---

# Intake Experience

Redesign the intake experience completely.

It should not resemble a chatbot, WhatsApp, a support bot or a giant form.

Use:

- strong central question
- clear visual options
- section progress
- subtle background context
- voice interaction state
- single primary action area

Example conceptual structure:

```text
Current section
──────●────────

What brings you here today?

[ option ]
[ option ]
[ option ]

🎤 Speak
⌨ Type

← Back
```

---

# Question Interaction

For normal single-choice questions:

```text
Tap option
→ save immediately
→ animate transition
→ next question
```

There should be **no Continue button** after selecting a normal single-choice option.

For multi-select:

```text
select several
→ Done
```

For free text:

```text
Enter / Send
→ submit
```

Add a visible **Back** button.

Back should:

- show previous answer
- allow changing it
- resubmit immediately
- recalculate branching safely
- animate backwards naturally

---

# Progress

Do not show `Question 7 of 28`.

Use section-based progress:

```text
Concern
Symptoms
History
Medicines
Allergies
Records
Review
```

Use animated progress movement.

---

# Voice Interaction

Voice must look and feel like a premium feature.

Create distinct visual states:

```text
Idle
Listening
Processing
Transcript ready
Speaking
Retry
Error
```

Use visual treatments such as:

- waveform
- soft pulse
- reactive ring
- animated microphone
- subtle audio visualization

Do not create overly flashy audio visualizers.

For TTS:

- clearly show when the system is speaking
- provide replay
- make “Hear question” visually clear

If voice fails:

- graceful fallback to text/touch
- no technical error exposure

---

# OCR / Previous Records Experience

Make the document flow one of the strongest parts of the app.

The patient should see:

```text
Previous Records

[ Take Photo ]
[ Upload Image ]
[ Upload PDF ]

[ Skip for now ]
```

---

# Camera Flow

Create a polished camera flow:

```text
Open camera
→ live preview
→ alignment guide
→ capture
→ preview
→ Retake / Use Photo
→ processing
```

Use a premium document-scanner style UI.

Make sure the full prescription is visible and not cropped.

Use clean guidance like:

> Place the full document inside the frame.

---

# OCR Processing Animation

When OCR starts, do not show a spinner alone.

Create a richer processing state that visually communicates stages:

```text
Reading document
→ Extracting information
→ Organizing medications
→ Preparing review
```

Use tasteful motion.

Do not expose backend names, Tesseract, MIME-type errors, environment variables or stack traces.

---

# OCR Verification

Create a polished verification screen.

Show extracted data as editable structured cards.

Example:

```text
Metformin
500 mg
Twice daily
High confidence

[ Edit ] [ Remove ]
```

For uncertain text:

```text
Needs verification
```

Use animated warning states.

Do not make low-confidence OCR visually look identical to verified data.

---

# Physician Side

The physician side should feel completely different from the patient side.

It should feel like:

> a premium clinical intelligence workspace.

It should be:

- information-dense
- clean
- fast
- professional
- evidence-driven
- visually structured
- highly interactive

Do not make it decorative.

---

# Physician Dashboard

Design a premium doctor workspace with clear sections such as:

```text
Overview
Current Visit
Timeline
Medications
Investigations
Documents
Similar Visits
Alerts
Summary
```

Use a layout optimized for laptop/desktop.

---

# Physician Overview

The doctor should immediately see:

- patient identity
- current encounter
- relevant historical context
- alerts
- contradictions
- medications
- similar previous encounter
- latest documents

Do not force the doctor to hunt through tabs for basic context.

---

# Longitudinal Timeline

Make the timeline one of the visual highlights of the product.

It should support:

- filters
- year grouping
- expandable events
- animated expansion
- smooth hover/select
- event-type differentiation
- document events
- encounter events
- medications
- labs
- AYUSH
- alerts

Clicking an event should open details/evidence elegantly.

---

# Medication History

Create a premium longitudinal medication view.

Show:

- medicine
- date first seen
- historical/current/uncertain state
- source
- contradictions
- event history

Use a timeline/list hybrid if helpful.

---

# Similar Previous Encounters

Make this visually impressive but clinically restrained.

Show:

- prior encounter date
- shared structured features
- reason for similarity
- source evidence
- open encounter action

Do not visually present similarity as diagnosis probability.

---

# Evidence and Provenance

Click-to-source should feel premium.

Use a side drawer or floating evidence panel.

For patient speech:

- original transcript
- language
- source type
- timestamp
- confidence if real

For documents:

- document preview
- highlighted OCR region
- page number
- extracted text
- confidence

Make evidence exploration smooth and visually strong.

---

# Contradictions

Design contradictions as a clear review state.

Example:

```text
Current patient statement
vs
Historical document

Needs reconciliation
```

Use elegant side-by-side comparison.

Do not use ugly red error boxes unless truly necessary.

---

# Red Flags and Alerts

Red flags need strong hierarchy but should not make the app look frightening.

Use:

- semantic icon
- clear title
- evidence
- subtle animated emphasis
- priority tag

Avoid aggressive flashing.

---

# Summary

Keep summary as one physician view, not the entire product.

Visually show:

```text
DRAFT
Requires physician confirmation
```

Support:

- source-linked lines
- edit
- verify
- confirm
- evidence drawer

---

# Success / Confirmation Flow

When physician confirms, create a polished confirmation sequence.

Example:

```text
Review complete
→ Encounter confirmed
→ Record stored
→ FHIR prepared
→ Done
```

Use subtle success animation.

Do not make it cheesy.

---

# Error Handling

No technical/raw errors in the normal UI.

Never show:

- stack traces
- API payloads
- environment variables
- backend names
- raw database errors
- OCR backend configuration
- console-like messages

Patient errors should be simple.

Doctor errors should be informative but polished.

---

# Loading States

Every major data state should have a designed loading experience.

Use:

- skeletons
- staged loading
- transition states
- progress states

Avoid `Loading...` as the only treatment.

---

# Empty States

Design premium empty states for:

- no previous visits
- no medications
- no documents
- no similar encounters
- no alerts
- no lab history

Make them informative and visually coherent.

---

# Responsive Design

Ensure quality across:

- laptop
- desktop
- tablet
- kiosk display
- mobile where practical

Patient side should be touch-first.

Doctor side should optimize for desktop/laptop.

---

# Accessibility

Maintain:

- strong contrast
- readable typography
- large touch targets
- keyboard navigation
- focus indicators
- screen-reader semantics
- reduced-motion support
- accessible forms
- accessible modal focus
- accessible alert semantics

Premium UI should not reduce usability.

---

# Performance

Do not destroy performance with excessive motion.

Keep:

- route transitions smooth
- animations lightweight
- code splitting sensible
- image loading optimized
- large components lazy-loaded when useful
- no unnecessary animation libraries if one motion system is enough

---

# Architecture

Create reusable frontend primitives.

Suggested conceptual groups:

```text
design-system/
motion/
patient/
physician/
documents/
voice/
timeline/
evidence/
alerts/
shared/
```

Use the current project structure intelligently rather than forcing these exact folders.

---

# Frontend Cleanup

After the new frontend is stable:

- remove obsolete old components
- remove unused CSS
- remove dead frontend routes
- remove duplicated styling
- remove legacy chatbot UI
- remove unnecessary dependencies

Do not delete anything until the replacement works.

---

# Do Not Change

Do not modify these product rules during the UI redesign:

- no diagnosis
- no treatment recommendation
- provenance-backed facts
- deterministic red flags
- physician confirmation
- validated terminology
- consent gating
- synthetic demo data

---

# Testing

After redesign, actually run and inspect the frontend.

Test:

- landing
- patient memory
- start visit
- consent
- every question type
- auto-submit
- back navigation
- text input
- voice idle
- voice listening
- voice error
- TTS
- document upload
- camera
- OCR processing
- OCR verification
- patient review
- physician dashboard
- timeline
- medications
- documents
- similar visits
- contradictions
- alerts
- evidence drawer
- summary
- confirmation
- responsive layouts
- loading states
- empty states
- error states

Do not mark the redesign complete based only on build success.

Visually inspect it.

---

# Final Standard

When someone opens MediKiosk, they should immediately feel that this is a serious, premium, next-generation health-tech product.

The UI should create a strong first impression before any explanation is given.

The design should be good enough that:

> the product itself explains the ambition.

Do not make it look like a government website.

Do not make it look like a hospital ERP.

Do not make it look like a chatbot.

Do not make it look like a generic template.

Create a visual identity that is distinctly MediKiosk.

Use the connected design/Motion/Figma/UI tools to make it genuinely exceptional.

Start by making a git checkpoint, inspect the current frontend architecture and API contracts, then rebuild the frontend in controlled stages while keeping all existing functionality working.
