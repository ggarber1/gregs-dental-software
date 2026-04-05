# Greg's Dental Software

Building a modern, all-in-one dental practice management platform targeting solo and small group practices (Vector A: The All-In-One Disruptor).

---

## The Opportunity

The dental PMS market is dominated by legacy, server-based software with outdated UX, opaque pricing, and fragmented toolchains. The target: replace 8–12 separate tools with one flat-rate, cloud-native product.

**First customer:** Dad's single-office practice, currently on Eaglesoft.

**Why now:** Eaglesoft is forcing all practices off perpetual licenses onto subscriptions in 2026 — a forced price increase with no modernization in return. This is the switching moment.

---

## Build Strategy

### Phase 0 — Discovery (current)
Talk to the practice before writing any code. Understand the real workflow, the real pain, and what would actually make them switch.

### Phase 1 — Full Replacement (MVP Core)
Build the real thing from the start. A supplement layer was considered but ruled out — Eaglesoft is a closed system (no public API), so any booking tool built alongside it has no reliable path to read or write the schedule. That means double-booking risk, manual reconciliation, and front desk overhead. Not worth it.

Instead: Dad runs Eaglesoft for existing data while the new system goes live for new patients. Migrate when feature parity is sufficient.

**MVP scope (defined after discovery):** Scheduling + patient records + patient comms. No insurance billing yet.

- Full schedule ownership — no double-booking risk
- Online booking, automated reminders, digital intake forms
- Cloud-native: no server required at the practice (optional server)
- Defined precisely after discovery sessions

### Phase 2 — Clinical Core
- Patient records and charting (tooth chart, perio probing, clinical notes)
- Treatment planning
- Requires deep domain knowledge from Dad and staff

### Phase 3 — Billing & Insurance
- Electronic claims via clearinghouse (Office Ally, DentalXChange)
- Insurance eligibility verification
- ERA/payment posting
- This is the hardest module — tackle last

### Phase 4 — Full Replacement
- Feature parity with Eaglesoft + modern UX
- Migration tooling for Eaglesoft data export
- Position as the switch

---

## Pricing Target
- **$299–$399/month flat** — everything included, no add-ons, month-to-month
- Public pricing from day one
- Free data export (no lock-in)
- Target savings: ~$8,000/year vs. current Eaglesoft stack

---

## Key Differentiators to Build Toward
- Cloud-native (no server required)
- Native mobile app (check schedule from anywhere)
- Built-in AI: ambient clinical notes, insurance verification, scheduling optimization
- Consumer-grade UX — same-day onboarding, no IT overhead
- HIPAA compliance dashboard built-in
- Transparent benchmarking ("how does your recare rate compare to similar practices?")

---

## Technical Constraints (Non-Negotiable)
- HIPAA-compliant hosting from day one (AWS HIPAA-eligible services)
- Encryption at rest and in transit
- Audit logs on all PHI access
- BAAs with every vendor that touches patient data
- Idempotent operations — safe to retry without side effects
- Crash-only components — designed to fail gracefully, not degrade silently
- Incremental progress — no big-bang operations; every step leaves the system in a valid state

---

## Discovery: Questions to Ask Dad

Run these as a conversation, not an interrogation. Best done in two sessions: one with Dad (clinical + business owner perspective), one with his front desk staff separately — they will have completely different answers.

---

### Session 1: With Dad (Owner + Clinician)

**About the business:**
1. What does a typical day look like from when you walk in to when you leave?
2. Where do you feel like you lose the most time that isn't actually treating patients?
3. If you could fix one thing about how the practice runs tomorrow, what would it be?

**About Eaglesoft specifically:**
4. How long have you been on Eaglesoft, and has Patterson told you about the 2026 pricing change to subscription-only?
5. What are you paying all-in right now — software, server maintenance, IT support, any add-ons like YAPI or Demandforce?
6. What do you actually use Eaglesoft for day-to-day vs. what features exist that nobody touches?
7. What breaks or frustrates you the most about it?

**About patients:**
8. How do most patients book appointments — phone, online, or something else?
9. What do patients complain about most?
10. How are you sending appointment reminders right now? Is it working?
11. Do patients still fill out paper forms when they arrive?

**About money:**
12. What percentage of claims get denied or come back needing corrections?
13. Do you have a sense of what your no-show rate is? What does a no-show actually cost you?
14. Are there patients with open treatment plans who never scheduled? How do you follow up with them?

**About switching:**
15. What would have to be true for you to consider switching software?
16. What's the one thing that would make you say "absolutely not" to a new system?

---

### Session 2: With Front Desk Staff (Separately from Dad)

The front desk lives in the software all day. Their answers will be more operational and often more honest.

**Daily workflow:**
1. Walk me through what you do from when the first patient calls to when they leave after their appointment.
2. What takes the most time in your day that feels like it shouldn't?
3. What do you have to do manually that you wish was automatic?

**Phone and scheduling:**
4. How many calls do you get in a day? How many do you miss?
5. What are most calls about — booking, questions, insurance?
6. How do you handle patients who want to book online?
7. How long does it take to schedule a new patient from scratch?

**Insurance:**
8. How do you verify insurance before appointments? How long does that take per patient?
9. How many claims does the practice submit per week? How many come back rejected?
10. What's the most confusing or annoying part of the billing process?

**Patient intake:**
11. Are new patients filling out paper forms or digital forms? If paper, how long does it take to enter that into Eaglesoft?
12. What information do you wish you had before a patient arrived that you don't have?

**General pain:**
13. What's the thing about Eaglesoft that makes you want to throw your computer?
14. If you could wave a magic wand and change one thing about how the office runs, what would it be?

---

## What to Do With the Answers

After both sessions, identify:

1. **The single biggest pain point** — not the list, the one thing that costs the most time or money
2. **Whether that pain is in scheduling, comms, billing, or charting** — this determines Phase 1 scope
3. **What Dad is currently paying for add-ons** — anything he pays separately (YAPI, Demandforce, a VoIP system) is a displacement opportunity
4. **The switching blocker** — what would make him say no, so you can plan around it

Bring the answers back and Phase 1 scope gets defined from there.
