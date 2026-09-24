# Discovery Questionnaire — AI Sylhet documentary site

> **Phase 0, step 0.1.** Send in one message to the DYD Sylhet side.
> Record answers in the table at the bottom, then copy them into `plan.md` §22 (step 0.2).
>
> **Before sending:** have the Bangla copy reviewer localise this document. The questions below are
> written in English for our own record; the department will answer them more reliably in Bangla.

**Why we are asking.** Every question here removes an unknown that would otherwise be discovered on
launch week. Two of them — **Q6** and **Q2** — can stop the site going live at all.

---

## The questions

### Q6 — Consent for publication ⚠️ *the project gate*

**Does written consent to publish already exist for this batch, or must it be collected?**

Specifically: for each of the Batch 1 trainees, is there a record — a form, an SMS, an email, an
attendance sheet clause — that says their **name** may appear on a public website as part of this
programme?

- If **yes**: please describe what the record is, who holds it, and in what form.
- If **no**: the site launches with the trainee register **empty**. No name is published until
  consent is recorded for that individual. We can prepare a one-page consent form for the department
  to collect.
- If **partly**: tell us which ones, and we will publish only those.

> We ask because publishing a named private individual on a government page is a different act from
> enrolling them in a training course. We will not publish a name on an assumption — see `plan.md`
> §5.3.

**Answer:**

---

### Q2 — The institution's full legal name and address

Our record currently says **"Sylhet BUTTC"**. Is that the correct full legal name?

- Should "BUTTC" be expanded? If so, to what?
- What is the full postal address, in Bangla?
- Is this the same entity that will appear as the training partner? (see Q3)

> "BUTTC" as supplied is used exactly as written and is not expanded or guessed at. This name appears
> on the Course page, the About page, **every** trainee profile and the site footer.

**Answer:**

---

### Q3 — The Sylhet training partner

The national site names the delivery partner as:

> Service Engines Ltd., Dot Com Systems Ltd. & Wizard Software Technology Bangladesh Ltd. (JV)

Is this the correct partner entity for **Sylhet**? If the Sylhet arrangement differs, what is the
correct name?

**Answer:**

---

### Q1 — Batch 1 dates

- Start date:
- End date:
- Has the batch completed? (yes / no / in progress)

> Used on the Course page and the Batch 1 page. If unknown, we build with placeholders and you edit
> them in the CMS later.

**Answer:**

---

### Q5 — The trainee roster

- Approximately how many trainees are in Batch 1?
- In what form does the list exist today — Excel, Google Sheet, paper register, something else?
- Can you send a **sample** with the columns you have? (Please remove phone numbers, ID numbers and
  dates of birth before sending — we do not store them, and the sample is easier to review without
  them.)

> We specifically need to know whether the source has a **consent** column, because that determines
> whether the import can publish anything (see Q6).

**Answer:**

---

### Q7 — Who owns the data, and who handles a withdrawal request?

If a trainee later asks to be removed from the site, who do they contact?

- Name / designation:
- Phone or email to publish on the privacy page:

> The privacy page has to name a route and a person. We commit to acting on a withdrawal request
> within 24 hours, so this must be someone who will actually receive the message.

**Answer:**

---

### Q4 — Government identity assets

May we use the DYD logo and the government identity block on this site?

- If yes, please send the files (SVG or high-resolution PNG preferred).
- If no, we will use a typographic wordmark and our own drawn roundel instead.

**Answer:**

---

### Q8 — Training photographs

The design deliberately shows **no portraits of trainees**. Do you have photographs of the training
sessions themselves — the room, the equipment, the class in progress — that we may use in the
gallery?

> These would be captioned by activity, never with a trainee's full name. If none are available, the
> site launches without the gallery and no redesign is needed.

**Answer:**

---

### Q9 — Outcome tracking

Do you want the site to show what trainees have done **since** the course — a job, freelancing,
further study, a business?

- If yes: who keeps that up to date after launch? It only stays accurate if someone owns it.
- If no: we show only the course and the register, with no outcome column.

**Answer:**

---

### Q10 — The domain

We are planning `sylhet.dydaiproject.com`. Is that correct, or should it be something else?

**Answer:**

---

### Q11 — A Bangla reviewer

Is there someone on the DYD side who can review the site's Bangla text before launch?

> Every user-facing string needs a Bangla speaker's sign-off. We do not ship machine-translated copy.

**Answer:**

---

## Answer record

Fill this in and we will transfer it into `plan.md` §22.

| # | Question | Answer | Answered by | Date |
|---|---|---|---|---|
| Q1 | Batch 1 dates | | | |
| Q2 | Institution legal name + address | | | |
| Q3 | Partner entity | | | |
| Q4 | DYD logo assets | | | |
| Q5 | Roster count + format | | | |
| **Q6** | **Consent for publication** | | | |
| Q7 | Data owner + withdrawal contact | | | |
| Q8 | Training photographs | | | |
| Q9 | Outcome tracking + owner | | | |
| Q10 | Domain | | | |
| Q11 | Bangla reviewer | | | |

---

## What is blocked until each is answered

| # | Blocks | Can we build around it? |
|---|---|---|
| **Q6** | Launching with any trainee name at all | **No.** This is the gate. |
| **Q2** | Course, About, every profile, the footer | Build with "Sylhet BUTTC"; correct in the CMS |
| **Q3** | Legal accuracy on Course and About | Build with the national site's wording; correct in the CMS |
| Q1 | Course and Batch 1 dates | Yes — placeholders |
| Q5 | Pagination tuning, import shape | Yes — assume 100–400 records |
| Q4 | Header, footer, OG image | Yes — typographic fallback |
| Q7 | The privacy page | **Partly** — the page needs the contact before launch |
| Q8 | The gallery | Yes — launch without it |
| Q9 | Participant field set | Yes — keep the fields, populate what is known |
| Q10 | Deploy topology | Yes — assume the subdomain |
| Q11 | Bangla sign-off | No — but it is a review step, not a build step |

> **Q6 and Q7 must be answered before go-live.** Everything else can be corrected in the CMS after
> launch, which is exactly why the CMS exists.
