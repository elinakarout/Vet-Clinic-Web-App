# Documentation Index

This folder contains the handover documentation for the Vet Clinic Web App
(internally, "Paws & Claws"). There are three documents, each written for a
different reader. Start with whichever matches who you are.

## [`client-user-manual.md`](./client-user-manual.md)

**Who should read this:** pet owners using the app to manage their pets and
book appointments — clinic clients.

**What it covers:** creating an account and signing in, finding your way
around, managing your pets, booking and cancelling appointments, updating your
contact details, using the clinic assistant chat, and a troubleshooting table
for the problems clients run into most often.

Written in plain language with no technical or programming terms. If you are
a client, or you're training clients how to use the system, this is the only
document you need.

## [`administrator-guide.md`](./administrator-guide.md)

**Who should read this:** clinic staff — vets and practice administrators —
who use the app day to day and are responsible for running the clinic side of
it.

**What it covers:** the difference between the Admin and Vet roles, the
staff-facing dashboard and schedule views, managing patients and appointments
across the whole clinic, and — because these particular tasks don't have a
dedicated screen yet — step-by-step instructions for creating staff accounts
and setting a vet's working hours through the system's technical API-docs
page. Also plain language, aimed at practice staff rather than developers,
with a troubleshooting table for common admin issues.

## [`technical-handover.md`](./technical-handover.md)

**Who should read this:** a developer, engineer, or technical contractor
taking over or maintaining the codebase.

**What it covers:** the technology stack, system architecture, database
schema, authentication model, full API surface, the AI assistant's design,
every environment variable, Docker and deployment setup (including the Render
blueprint), how to run migrations and tests, the project's folder structure,
and a maintenance/troubleshooting reference for the failure modes that have
actually been seen in this codebase.

This is the only one of the three documents that assumes programming
knowledge. It also flags one detail worth knowing up front: an early design
intention for this project was a different AI provider than what actually
shipped — see its opening note before making assumptions about that part of
the system.

---

## How these were produced

All three documents were written by directly inspecting this repository's
code, database migrations, configuration files, and automated tests, rather
than assumed from any design intentions that didn't end up matching what was
actually built.

If the application changes, these documents should be revisited — particularly
the administrator guide's notes on features that don't yet have a dedicated
screen (staff account creation, vet schedule editing), which are the most
likely areas to gain a proper UI in a future update.
