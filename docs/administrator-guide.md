# Administrator Guide — Paws & Claws Veterinary Clinic

This guide is for **clinic staff** — administrators and vets — who manage the
clinic's day-to-day operations through the application. It assumes no
programming knowledge, but a few tasks (creating staff accounts, and editing a
vet's working hours) currently have to be done through a technical screen
called the **API docs page**, and this guide walks through those step by step
in plain language.

---

## Table of contents

1. [Staff roles: Admin vs. Vet](#1-staff-roles-admin-vs-vet)
2. [Logging in as staff](#2-logging-in-as-staff)
3. [The staff dashboard](#3-the-staff-dashboard)
4. [Managing patients (pets)](#4-managing-patients-pets)
5. [Managing the clinic's schedule](#5-managing-the-clinics-schedule)
6. [Managing appointments](#6-managing-appointments)
7. [Managing your own profile](#7-managing-your-own-profile)
8. [Creating staff accounts (vets and admins)](#8-creating-staff-accounts-vets-and-admins)
9. [Setting a vet's working hours and time off](#9-setting-a-vets-working-hours-and-time-off)
10. [Deactivating an account](#10-deactivating-an-account)
11. [The clinic assistant, from a staff point of view](#11-the-clinic-assistant-from-a-staff-point-of-view)
12. [Common admin problems and solutions](#12-common-admin-problems-and-solutions)

---

## 1. Staff roles: Admin vs. Vet

The system has three account types:

| Role | Who | Can see |
|---|---|---|
| **Client** | Pet owners | Only their own pets and appointments |
| **Vet** | Clinical staff | Every patient's record; only **their own** appointment diary |
| **Admin** | Practice management | Everything — every patient, every vet's diary, every appointment |

A **vet** can look up any pet's record (a colleague's patient may need
attention), but can only see and manage appointments on **their own** schedule
— reading a colleague's diary is treated as unnecessary for clinical care.

An **admin** has no pet-owner profile of their own (no phone number or address
on file) and sees the whole clinic — every pet, every vet's schedule, every
appointment.

---

## 2. Logging in as staff

Staff sign in exactly the way clients do, using the email and password the
practice set up for them (see [Section 8](#8-creating-staff-accounts-vets-and-admins)
if you need to create one). There is no separate staff sign-in screen — the
app shows you the right things automatically once you're signed in, based on
your account type.

---

## 3. The staff dashboard

The dashboard looks different for staff than for clients:

- **Stat tiles** across the top: how many appointments are booked **today**,
  how many are still to come today, the total number of patients on file, and
  the number of vets at the clinic.
- **Today's appointments** — the day's full list, in order.
- **Patients** — a quick list of pets recently on file, with a link to manage
  them in full.

A vet's "today's appointments" list shows only **their own** bookings. An admin
sees the whole clinic's.

---

## 4. Managing patients (pets)

Go to **Pets** in the navigation bar. As staff, this page shows **every pet
registered with the clinic**, not just one client's, and includes a search box
to filter by name or species.

### Adding a pet for a client (a walk-in, or registering on their behalf)

1. Click **Add a pet**.
2. Fill in the pet's details as usual (name, species, breed, sex, date of
   birth, weight, notes).
3. Because staff have no pets of their own, you must also specify **which
   client** the pet belongs to, using their **client profile ID number**
   (shown next to their name in the suggestions list that appears as you type,
   based on clients who already have a pet on file).

> **Known limitation:** there is currently no searchable client directory in
> the app — the owner suggestions you see are only the clients who already
> have at least one pet on file. **A brand-new client must create their own
> account first** (via the ordinary sign-up screen) before staff can register a
> pet for them; at that point, ask the client for their email so you can look
> up their client profile ID if needed (see
> [Section 12](#12-common-admin-problems-and-solutions) for how, via the API
> docs page).

### Editing or deleting a pet

Works the same as for a client (see the
[Client User Manual](./client-user-manual.md#5-managing-your-pets)), with one
difference: staff can edit or delete **any** pet, not just ones they added.
The same protection applies — a pet with any appointment or medical history on
file cannot be deleted, to protect clinical records.

---

## 5. Managing the clinic's schedule

Go to **Schedule** in the navigation bar (visible to vets and admins only).

- **Today / Next 7 days** tabs let you switch the view.
- Stat tiles show how many appointments are booked, confirmed, completed, and
  cancelled in the selected range.
- A vet sees only their **own** appointments here; an admin sees **every**
  vet's.

This page is for viewing and actioning appointments that are already booked
(see [Section 6](#6-managing-appointments)). To change a vet's **working
hours** or block out time off, see [Section 9](#9-setting-a-vets-working-hours-and-time-off) —
that currently requires the API docs page, described below.

---

## 6. Managing appointments

From the **Schedule** page (or the **Appointments** page, which any account
type can also use to see the same information in a different layout), staff
can:

- **Confirm** an appointment.
- **Mark an appointment as completed**, once the visit has happened.
- **Cancel** an appointment. Unlike a client, staff can cancel **at any time**
  — even inside the 2-hour window that blocks a client from self-cancelling —
  because a same-day change phoned in to reception needs to be actionable
  immediately.

Only the actions that make sense for an appointment's current status are shown
— for example, a completed or already-cancelled appointment has no further
actions, because the clinic considers those final.

**Note:** cancelling an appointment from the Schedule page does **not**
automatically notify the client — the app does not currently send emails or
texts. If a client needs to be told about a change, contact them directly.

---

## 7. Managing your own profile

Go to **Profile** to update your own details:

- **Vets** can update their full name, specialty, and licence number (shown to
  clients when they choose who to book with).
- **Admins** see a message explaining that administrator accounts have no
  profile — there is no phone number, address, specialty, or licence for an
  admin account, by design.

---

## 8. Creating staff accounts (vets and admins)

**Staff cannot self-register** — only an existing administrator can create a
vet or admin account, and there is currently no page in the app for this. It's
done through the interactive **API docs** page, which is safe to use for this
purpose and is explained step by step below.

1. Make sure you are signed in to the app as an **administrator**.
2. In the same browser, open the API docs page. In development this is
   `http://localhost:8000/docs`; ask your technical contact for the address of
   the live/production system if different.
3. You need your access token first. The simplest way: open your browser's
   developer tools while signed in to the main app, or ask your technical
   contact to retrieve it for you — this step is the one genuinely technical
   part of the process. Alternatively, ask a developer to create the account
   for you using the same form described below.
4. On the docs page, find **`POST /auth/staff`** and click **Try it out**.
5. Click **Authorize** (top of the page) and paste in your access token, or use
   the padlock icon next to the `POST /auth/staff` entry.
6. Fill in the request body, for example, to create a new vet:

   ```json
   {
     "email": "dr.newvet@vetclinic.test",
     "password": "a-strong-temporary-password",
     "role": "VET",
     "full_name": "Dr. Jordan Lee",
     "specialty": "Dermatology",
     "license_no": "VET-1234"
   }
   ```

   To create another **admin** instead, set `"role": "ADMIN"` and remove
   `full_name`, `specialty` and `license_no` — admin accounts don't have those.

7. Click **Execute**. A successful response shows the new account's details.
8. Give the new staff member their email and temporary password through a
   secure channel (not email, ideally) and ask them to sign in and — once they
   can — change it with the clinic's usual process for that.

**Rules enforced automatically:**
- `role` must be exactly `"VET"` or `"ADMIN"` — `"CLIENT"` is rejected, because
  clients always register themselves.
- A `VET` account requires a `full_name`.
- Duplicate email addresses and duplicate licence numbers are rejected.

---

## 9. Setting a vet's working hours and time off

Like staff creation, this is not yet available as a page in the app and is
done through the same **API docs** page (`/docs`), signed in as an
administrator or as the vet themselves.

### Setting weekly working hours

Find **`PUT /vets/{vet_id}/availability`**, supply the vet's ID, and provide
the **whole week's** schedule as a list — this replaces everything for that
vet, so leaving a day out means the vet has no bookable hours that day.
Example, for a vet working 9am–5pm Monday to Friday in 30-minute slots:

```json
[
  { "weekday": 0, "start_time": "09:00:00", "end_time": "17:00:00", "slot_minutes": 30 },
  { "weekday": 1, "start_time": "09:00:00", "end_time": "17:00:00", "slot_minutes": 30 },
  { "weekday": 2, "start_time": "09:00:00", "end_time": "17:00:00", "slot_minutes": 30 },
  { "weekday": 3, "start_time": "09:00:00", "end_time": "17:00:00", "slot_minutes": 30 },
  { "weekday": 4, "start_time": "09:00:00", "end_time": "17:00:00", "slot_minutes": 30 }
]
```

`weekday` is `0` for Monday through `6` for Sunday. Times are the clinic's own
local time (not UTC). Changing these hours does **not** cancel any appointment
already booked outside the new hours — those bookings simply stop being
re-bookable if cancelled.

### Blocking out time off (holidays, surgery lists, etc.)

Find **`POST /vets/{vet_id}/time-off`** and provide a start and end time (with
a date and time zone offset), for example:

```json
{ "starts_at": "2026-09-01T06:00:00Z", "ends_at": "2026-09-01T09:00:00Z", "reason": "Surgery list" }
```

That block of time will no longer show up as available to book. Any
appointment already booked inside that window is **left alone** — cancel it
separately if needed.

To remove a time-off block, use **`DELETE /vets/{vet_id}/time-off/{time_off_id}`**
with the id shown when the block was created (or listed via
`GET /vets/{vet_id}/availability`).

---

## 10. Deactivating an account

There is currently no page for this either. An administrator with direct
database or developer access can set a user's account to inactive, which:

- Signs them out immediately, even if they have an active, unexpired session.
- Blocks them from logging back in until reactivated.

Ask your technical contact to perform this if you need to suspend an account
(for example, a staff member who has left).

---

## 11. The clinic assistant, from a staff point of view

Any signed-in staff member can use the chat assistant (the round button,
bottom-right of the screen), the same way a client would — see the
[Client User Manual, Section 9](./client-user-manual.md#9-the-clinic-assistant-chat).

A few differences worth knowing:
- If you ask it something about "my pets" or "my appointments" as a vet or
  admin, it correctly answers about **your own** account, not the whole
  clinic's — it does not use your staff access to dump every patient's record
  into a chat reply.
- Each staff member's conversation history is private to them — even an
  administrator cannot read another staff member's or client's chat
  transcript through the app. If a transcript is genuinely needed for a
  complaint or safeguarding reason, that requires direct developer/database
  access.
- The assistant's knowledge is limited to what is in the clinic's written
  knowledge base (opening hours, prices, policies, vaccination schedules, etc.)
  — it does not know anything beyond that, and is deliberately built not to
  guess at medical advice or invent details such as a phone number that isn't
  written down anywhere.

---

## 12. Common admin problems and solutions

| Problem | What's happening | What to do |
|---|---|---|
| Can't find a page to add a new vet or admin account | Not built into the app yet | Use the API docs page — see [Section 8](#8-creating-staff-accounts-vets-and-admins) |
| Can't find a page to change a vet's hours | Not built into the app yet | Use the API docs page — see [Section 9](#9-setting-a-vets-working-hours-and-time-off) |
| A new client's pet can't be added because you don't know their client profile ID | No client directory exists yet in the app | Ask the client to register first; if you have API/developer access, `GET /pets` as an admin lists every pet with its `owner_id` alongside |
| Cancelling an appointment doesn't seem to notify the client | The app doesn't send emails or texts | Contact the client directly by phone |
| A vet's new working hours didn't remove an already-booked appointment from their diary | This is intentional — changing hours never cancels existing bookings | Cancel that appointment separately if it truly needs to go |
| Two clients tried to book the exact same time and only one succeeded | This is the double-booking protection working correctly | No action needed — this is expected behaviour, not a bug |
| A staff account can log in but nothing appears in the Schedule page | The new vet may have no working hours set yet | Set their weekly hours — see [Section 9](#9-setting-a-vets-working-hours-and-time-off) |
| An account you deactivated is still able to browse without refreshing | Sessions are checked on every action but a page already open may not immediately notice | The next action they take (loading data, changing pages) will sign them out |

For anything not covered here, or a problem in the underlying system rather
than day-to-day use, see the [Technical Handover](./technical-handover.md) or
contact your developer/technical support contact.
