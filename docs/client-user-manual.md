# Client User Manual — Paws & Claws Veterinary Clinic

Welcome! This guide explains how to use the clinic's online booking system as a
pet owner. It covers signing up, managing your pets, booking and cancelling
appointments, and using the clinic assistant chat.

No technical knowledge is needed to follow this guide.

---

## Table of contents

1. [What this application does](#1-what-this-application-does)
2. [Signing up and logging in](#2-signing-up-and-logging-in)
3. [Getting around the app](#3-getting-around-the-app)
4. [Your dashboard](#4-your-dashboard)
5. [Managing your pets](#5-managing-your-pets)
6. [Booking an appointment](#6-booking-an-appointment)
7. [Viewing and cancelling appointments](#7-viewing-and-cancelling-appointments)
8. [Your profile](#8-your-profile)
9. [The clinic assistant (chat)](#9-the-clinic-assistant-chat)
10. [Common problems and solutions](#10-common-problems-and-solutions)

---

## 1. What this application does

This application lets you, as a pet owner ("client"), manage your relationship
with the clinic online:

- Create an account and keep your contact details up to date.
- Add and manage records for each of your pets.
- See a vet's free appointment times and book a visit yourself, any time of
  day, without phoning the clinic.
- View your upcoming and past appointments, and cancel one if your plans
  change.
- Chat with the clinic's assistant for general questions (opening hours,
  prices, vaccination schedules, what to bring to a first visit) and to be
  offered an appointment time you can confirm with one click.

All appointment times you see are shown in the **clinic's own time zone**, not
necessarily the time zone your computer or phone is set to. The bottom of every
page reminds you of this, and says so explicitly if your device appears to be
in a different zone.

> **This system is not for emergencies.** If your pet is having a medical
> emergency, call the clinic directly rather than booking online or asking the
> chat assistant. See [Section 9](#9-the-clinic-assistant-chat) for the exact
> warning signs the assistant watches for.

---

## 2. Signing up and logging in

### Creating an account

1. Open the application in your browser and click **Create an account** on the
   sign-in screen.
2. Fill in:
   - **Full name** (required)
   - **Email address** (required) — this is what you will log in with
   - **Password** (required) — at least 8 characters
   - **Phone** (optional, but recommended so the clinic can reach you)
   - **Address** (optional)
3. Click **Create account**. You are signed in immediately and taken to your
   dashboard.

Self-service sign-up always creates a pet-owner ("client") account. If you are
clinic staff (a vet or an administrator), the clinic creates that kind of
account for you — see the [Administrator Guide](./administrator-guide.md).

**A note on passwords:** the password field has an upper limit as well as a
lower one. If you use a very long password with special characters or emoji,
the form will tell you if it is too long — this is a technical safety limit,
not a bug.

### Logging in

1. Enter your email address and password on the sign-in screen.
2. Click **Sign in**.

If your email or password is wrong, you will see a generic "could not sign in"
message. For security, the app does not tell you which of the two was wrong.

### Staying signed in

Your sign-in session lasts **one hour**. After that, the app will ask you to
sign in again — you'll see a message explaining that your session expired. This
is a normal security measure and does not affect any of your saved
information; simply log back in and continue where you left off.

### Signing out

Use the **Sign out** button in the top-right of the screen (or in the mobile
menu). Signing out clears your session from that browser/device, including any
open chat conversation view — so if you share a computer, always sign out when
you're done.

---

## 3. Getting around the app

Once signed in, you'll see a navigation bar across the top with:

| Link | What it takes you to |
|---|---|
| **Dashboard** | A summary of what's coming up |
| **Pets** | Your pets' records |
| **Book** | The appointment booking flow |
| **Appointments** | Everything booked for your pets, past and upcoming |
| **Profile** | Your contact details |

On a phone or narrow screen, these links collapse into a menu button (☰) in the
top-right corner.

A round blue button in the bottom-right corner of every screen opens the
**clinic assistant** — see [Section 9](#9-the-clinic-assistant-chat).

---

## 4. Your dashboard

The dashboard is the first thing you see after signing in. For a pet owner, it
shows:

- A short greeting, personalised with your name.
- **Next appointments** — your soonest upcoming visits (up to three), with a
  link to see the full list.
- **My pets** — a quick list of your pets, with a one-click **Book** link next
  to each one, and a link to manage them in full.

If you have no pets on file yet, you'll see a prompt to add your first one. If
you have no appointments booked, you'll see a prompt to book one.

---

## 5. Managing your pets

Go to **Pets** in the navigation bar.

### Adding a pet

1. Click **Add a pet**.
2. Fill in the form:
   - **Name** and **Species** (e.g. "Dog", "Cat", "Rabbit") — required
   - **Breed** — optional
   - **Sex** — Male, Female, or Not known
   - **Date of birth** — optional; used to show your pet's age. It cannot be a
     future date.
   - **Weight (kg)** — optional
   - **Notes for the vet** — anything useful for the vet to know (e.g. "Nervous
     around clippers")
3. Click **Add pet**.

### Editing a pet

Click the edit option on a pet's card, change what you need (for example, an
updated weight after a check-up), and save. Only the fields you change are
updated — everything else stays as it was.

### Deleting a pet

Click the delete option on a pet's card and confirm.

**Important:** a pet that already has any appointments or medical history on
file **cannot be deleted** — you'll see a message explaining that their record
must stay. This is deliberate: it protects the clinic's medical records from
being accidentally erased. If you genuinely need a pet's record removed (for
example, they have sadly passed away), contact the clinic directly.

You will only ever see and manage your own pets — there is no way to view or
change another client's pet records.

---

## 6. Booking an appointment

Go to **Book** in the navigation bar, or click **Book** next to a pet on your
dashboard.

The booking screen walks you through four steps:

1. **Who is the visit for?** Choose the pet and the vet. If you only have one
   pet, or the clinic only has one vet, that choice is made for you
   automatically.
2. **When suits you?** Pick a week to look at (you can move forward and back a
   week at a time — starting from today, you cannot look at past weeks), then
   choose a free time slot from the grid shown. Only genuinely available times
   are shown — the system has already excluded times the vet is closed, on
   leave, or already booked.
3. A short **reason for the visit** field — optional, but it helps the vet
   prepare (e.g. "Vaccination", "Limping", "Annual check-up").
4. **Confirm** — review the pet, vet, date/time and length of the appointment,
   then click **Confirm booking**.

All times shown are in the clinic's own time zone, which is stated on the
booking screen.

**If someone else books the same slot a moment before you:** you'll see a
message that the time was just taken, and the list of available times
refreshes automatically so you can pick another. This can happen because two
people can be looking at the same open slot at once — the system always gives
the slot to whoever confirms first, and never double-books a vet.

An emergency reminder is shown on the booking screen: if your pet is
struggling to breathe, has collapsed, is having a seizure, is bleeding heavily,
or may have swallowed something toxic, **call the clinic instead of booking
online.**

---

## 7. Viewing and cancelling appointments

Go to **Appointments** in the navigation bar to see everything booked for your
pets, split into two tabs:

- **Upcoming** — visits that haven't happened yet.
- **Past** — completed and cancelled visits.

Each appointment shows the pet, the vet, the date and time, its status
(Requested, Confirmed, Cancelled, or Completed), and the reason you gave when
booking, if any.

### Cancelling an appointment

Click **Cancel** on an upcoming appointment and confirm. The time slot becomes
available for someone else to book, and you can always book a new time if your
plans change again.

**Cancellation cutoff:** you cannot cancel online within **2 hours** of the
appointment's start time. If you're inside that window, the Cancel button is
replaced with a note asking you to call the clinic directly — this gives the
clinic a chance to react to a last-minute change.

---

## 8. Your profile

Go to **Profile** in the navigation bar to see and update:

- **Full name**
- **Phone number**
- **Address**

Click **Save changes** after editing. Your email address, password, and
account type cannot be changed from this page — contact the clinic if you need
to update your login email.

---

## 9. The clinic assistant (chat)

Click the round chat button in the bottom-right corner of any page to open the
**clinic assistant**. It's a conversational helper that can:

- Answer general questions using the clinic's own knowledge base — opening
  hours, prices, vaccination schedules, post-surgery care, what to bring to a
  first visit, and the clinic's booking and cancellation policy.
- Look up your own pets and appointments to answer personal questions (e.g.
  "when is Luna due for her booster?").
- Suggest a specific, bookable appointment time as a **card** you can confirm
  with one click, or suggest cancelling an existing appointment as a card you
  can confirm.

### How to use it

1. Click the chat button to open the panel.
2. Type a question, or click one of the suggested starter questions.
3. The assistant's reply streams in as it's written. If it needs to look
   something up (like your pets or a vet's free times), you'll briefly see a
   status line saying what it's checking.
4. If it proposes a booking or a cancellation, you'll see a card with the
   details (pet, vet, date and time). Nothing is booked or cancelled until you
   click to confirm the card — the assistant never changes your calendar on
   its own.
5. Use the **history** icon (clock) to see and reopen past conversations, or
   the **new conversation** icon to start fresh.

### What the assistant will not do

- **It will not diagnose your pet, recommend medication or dosages, or offer
  reassurance about symptoms.** It is an information and booking helper, not a
  substitute for veterinary judgement.
- **It will not book or cancel anything without your confirmation.** Every
  proposal is a suggestion; clicking it uses the exact same booking process as
  the ordinary **Book** page.
- If you describe something that sounds like an emergency (difficulty
  breathing, collapse, seizures, heavy bleeding, suspected poisoning, and
  similar), the assistant is designed to tell you to call the clinic
  immediately rather than offer you a routine appointment slot.
- If it doesn't know something (it isn't in the clinic's knowledge base), it
  will say so and suggest calling the clinic, rather than guess.

### If the assistant seems slow or unavailable

The assistant depends on an external AI service. Occasionally it may:

- Take up to a minute to reply to a complex question — this is normal for
  questions that require it to check several things (like pet ownership and a
  vet's diary) before answering.
- Show "the assistant is busy right now" if it's receiving a lot of requests —
  wait a minute and try again.
- Show "the assistant is unavailable" if the service is temporarily switched
  off — everything else in the app (booking, pets, appointments) keeps working
  normally regardless.

---

## 10. Common problems and solutions

| Problem | What's happening | What to do |
|---|---|---|
| "Could not sign in" | Wrong email or password | Double-check both; for security, the app won't say which one is wrong |
| Signed out unexpectedly, with "your session expired" | Sessions last one hour for security | Sign in again — nothing is lost |
| Can't delete a pet — get a message about appointments or medical history | The pet has clinic history on file | This is intentional, to protect medical records; contact the clinic if you believe the pet's record should be removed |
| A time slot disappears just as you try to book it | Someone else booked it a moment earlier | Pick another time from the refreshed list |
| Can't cancel an appointment — see a note instead of a Cancel button | You're within 2 hours of the start time | Call the clinic directly to change or cancel |
| Times on screen look "off" by a few hours | You may be viewing from a different time zone than the clinic | This is expected — the footer of every page states the clinic's time zone; the app always shows clinic time, not your device's local time |
| The chat assistant says it doesn't know something | The answer isn't in the clinic's knowledge base | Ask at the clinic directly, or check with reception |
| A form won't submit and shows a red error message | A required field is missing, or a value is out of range (e.g. a negative weight, or a date of birth in the future) | Correct the highlighted field and try again |
| Nothing happens when you click a button that changes data | Check your internet connection | Refresh the page; anything already saved to the clinic's system will still be there |

If a problem isn't listed here or doesn't go away, contact the clinic directly
rather than continuing to retry.
