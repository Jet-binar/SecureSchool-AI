# SecureSchool AI

Controlled academic prototype for MSIT 5910 Capstone Project (University of the People).

**Project:** Design and Evaluation of an Intelligent Facial Recognition Security Prototype for Controlled School Access  
**Student:** Marsida Mania  
**Course:** MSIT 5910 — Capstone Project  
**Instructor:** Dr. Stella Tonye Whyte

## Purpose

SecureSchool AI investigates whether a limited facial-recognition prototype can distinguish authorized from unauthorized individuals under documented test conditions while protecting biometric privacy, measuring fairness, and keeping a human reviewer in the decision loop.

This repository is a research prototype. It is **not** a live school security product. Minors are not enrolled. The system does not support continuous surveillance, automated discipline, or law-enforcement integration.

## Repository Layout

```
src/        prototype source code (capture, recognition, access, dashboard)
docs/       project documentation, requirements, and progress notes
design/     architecture diagrams and module specifications
tests/      evaluation scripts and test-scenario notes
```

## Branching

- `main` — reviewed documentation, approved design artifacts, and stable snapshots
- `development` — active implementation, experimental code, and in-progress notes

## GitHub

https://github.com/Jet-binar/SecureSchool-AI

Clone:

`git clone https://github.com/Jet-binar/SecureSchool-AI.git`

## Run on this PC

From the project folder:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe run.py
```

Open http://127.0.0.1:5000 and sign in as `admin`. The first launch writes the password to `data/initial_admin_password.txt`. That folder stays on this computer and is not committed.

Face detection uses OpenCV YuNet. Matching uses OpenCV SFace. Templates are encrypted locally. Optional email is text only and is configured in `.env` (see `.env.example`).

## License

Academic use for the University of the People MSIT 5910 capstone only.
