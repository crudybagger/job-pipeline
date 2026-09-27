# Product Context

## Overview
This document describes the context in which the product exists, the problems it solves, intended functionality, and user experience goals.

## Problem Statement
Manually searching job boards, filtering postings against personal criteria, tailoring a resume and cover letter for every application, and keeping track of what was sent/applied is repetitive, slow, and error-prone for a job-seeking candidate.

## Solution
A 4-stage automated pipeline (defined in `./plan.md`):
1. **Stage 1 — Job Scraping and Filtering**: config-driven scraping of job boards; computes a configurable match score from candidate experience, future prospects, and correlation with ongoing education; separates jobs into accepted/rejected persistent queues; collects title, description, company name/website, contact details, plus metadata (base resume path, notes).
2. **Stage 2 — Matching Resume Generation**: minimally edits an existing LaTeX resume to naturally weave job keywords into experience/summary; an independent ATS-like substage scores the resume, returns improvement notes, and loops until the entry is marked ready (own queue).
3. **Stage 3 — Matching Cover Letter Generation**: researches company/department/hiring manager, then builds a cover letter following a repeatable pattern: Story Hook → Candidate Background → Experience → Skills → Story → Fitment → Interest → Closing. Human-sounding, job- and company-specific, in a format acceptable to the company/job board.
4. **Stage 4 — Candidate Delivery Package**: compiles job link, description, resume, and cover letter into one text message sent to the candidate via a messaging platform (WhatsApp/Telegram/Signal); tracks sent/applied status and stores candidate notes in job metadata.

## Target Audience
A single job-seeking candidate (the repository owner) who wants automation of discovery and material preparation while keeping final review and application in their own hands.

## User Experience Goals
- Candidate reviews a single, complete message per job — easy, one-place application
- Human-sounding resume and cover letter output (not generic AI/templated tone)
- Configurable thresholds (match score, ATS acceptance) so the human can re-tune after reviewing rejected jobs
- Simple interfaces to view accepted/rejected/sent queues and update statuses with notes

## Key Features
- Config-driven scraping with adjustable keywords and sources
- Persistent queues with interactive tooling (accept rejected jobs, view accepted jobs, view sent jobs and status)
- ATS feedback loop that iterates resumes until ready
- Sent/applied tracking with candidate notes persisted per job entry

## Use Cases
- Run Stage 1 ingestion against a job board URL (`POST /ingest` on the FastAPI app) and review the filtered queues
- Let Stage 2 + ATS loop produce an ATS-ready tailored resume for each accepted job
- Generate matching cover letters (Stage 3) for resume-ready jobs
- Receive a consolidated application package message (Stage 4), then mark it applied/not applied with notes

## Assumptions
- Base resume exists as LaTeX at a pre-configured path
- Messaging platform credentials available via config
- One candidate; no multi-tenancy

## Constraints
- Match score threshold must remain reconfigurable based on manual review of rejected jobs
- Cover letters must be consistent across runs and follow the fixed narrative pattern
- Resume edits must be minimal and confined to required sections of the LaTeX source

## Dependencies
- External job-board sources (scraping/API)
- External messaging platform for Stage 4 delivery
- Python package stack (see `techContext.md`)

## Version History
- **Version 1.0**: Initialized from repository context and `plan.md`

## Notes
- Implementation status: all stage logic is currently placeholder (`TODO`) scaffolding in `job-pipeline/src/`; the FastAPI app only exposes `/` (health) and `POST /ingest` (returns count from a placeholder fetcher).

