# Project Brief

## Overview
This repository implements the **Job Finder and Application Pipeline** described in `plan.md` (repo root). The goal is a 4-stage pipeline that discovers jobs on the web, prepares tailored application material, and sends a review-ready package to the candidate.

- Product blueprint / source of truth: `./plan.md`
- Main Python project: `./job-pipeline/`
- Plan-driven root README: `./README.md`

## Purpose
Scrape jobs from the web, filter them against candidate criteria, generate tailored resume and cover letter material, and compile everything into a single reviewable message delivered to the candidate.

## Goals
- **Stage 1 — Job Scraping and Filtering**: collect postings from job boards (config-driven keywords), compute a configurable match score, and maintain accepted/rejected queues in persistent storage with interactive tooling.
- **Stage 2 — Matching Resume Generation**: adapt a base LaTeX resume per job description with an ATS-like feedback substage that loops until the entry is marked ready (stored in a separate queue).
- **Stage 3 — Matching Cover Letter Generation**: generate company/job-specific cover letters following a repeatable narrative pattern (Story Hook → Background → Experience → Skills → Story → Fitment → Interest → Closing).
- **Stage 4 — Candidate Delivery Package**: compile job link, description, resume, and cover letter into one text message, send via an external messaging platform (WhatsApp/Telegram/Signal), and track sent/applied states.

## Scope
### In Scope
- Web scraping of job boards governed by a simple config (keywords, sources, thresholds)
- Match scoring based on candidate experience, future job prospects, and correlation with current education
- Persistent queues (accepted / rejected / resume-ready / sent) with tooling to view and accept/reject entries
- Per-job data collection: title, job description, company name + website, contact details; plus metadata (base resume path, notes)
- Minimal-edit LaTeX resume generation with human-sounding language
- ATS-style resume scoring substage with improvement-feedback notes loop
- Cover letter generation with configurable story-building context
- External messaging integration for delivery and sent/applied status tracking with candidate notes feedback

### Out of Scope
- Automatic submission of applications without candidate review (Stage 4 is review-oriented delivery)
- A hosted multi-user service — this is a single-candidate pipeline
- Building a full ATS product; the ATS is an internal substage of Stage 2

## Key Requirements
- Match score must be configurable and expected to be re-tuned after manual analysis of the rejected jobs list
- All queue data must be in persistent storage with proper interactive tooling
- Cover letter must follow the defined repeatable pattern and not sound generic
- Jobs sent to the candidate are marked as sent, stored in a separate tracking queue, and the candidate can mark applied/not applied with notes stored in job metadata

## Assumptions
- A single candidate with a pre-configured base resume (LaTeX) path
- Job-board sources are scrapeable or expose APIs; config can be adjusted per source
- Messaging platform credentials are provided by the candidate via configuration

## Dependencies
- Python 3.12 with FastAPI, uvicorn, httpx, pydantic, pandas, python-dotenv (see `job-pipeline/requirements.txt`)
- External messaging platform integration (Stage 4, to be selected)
- Git (used by the automation issue tracker for commit/push)

## Success Criteria
- End-to-end run: scraped job → filtered → tailored resume (ATS-ready) → tailored cover letter → single delivery message with tracked status
- Tests pass (`pytest -q` in `job-pipeline/`); CI green on `main`

## Stakeholders
- The candidate (sole end user, reviews/approves delivered packages)
- Automation/implementation agents (scaffold, implement, and maintain the pipeline)

## Timeline
- Milestone 1: Repository scaffolding + issue tracker automation — **done**
- Milestone 2: Stage 1–4 implementation — **pending**

## Review and Updates
This document should be reviewed and updated regularly to reflect changes in project scope, goals, or requirements.

## Version History
- **Version 1.0**: Initialized from repository context and `plan.md`

## Notes
- The repo currently contains scaffolding and placeholders; all stage logic is `TODO`.
- `issues.md` (in `job-pipeline/`) is a local markdown issue tracker processed by the automation loop; Issues #1–#3 (HLD, LLD, scaffolding) are marked Done.

