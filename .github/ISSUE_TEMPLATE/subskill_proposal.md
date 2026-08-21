---
name: Subskill Playbook Proposal
about: Propose or contribute a reusable browser automation subskill playbook
title: '[SUBSKILL] <Website / Workflow Name>'
labels: ['subskill', 'playbook']
assignees: ''
---

## 🎯 Playbook Overview
* **Subskill Name:** `[e.g. twitter-profile-extractor]`
* **Target Website / Domain:** `[e.g. x.com, linkedin.com, github.com]`
* **Category / Tags:** `[e.g. social-media, lead-gen, data-extraction]`

## 📋 Objective & Automation SLA
Describe what this playbook automates and expected success rate:
* *Extracts verified public profile info, latest 5 tweets, follower counts.*

## 🧩 Selector & DOM Strategy
List the primary and fallback CSS/XPath selectors:
* **Primary Selectors:** `div[data-testid="UserDescription"]`
* **Fallback Selectors:** `meta[property="og:description"]`
* **Dynamic Rendering / Infinite Scroll Handling:** `[e.g. window.scrollBy(0, 800) with 1.5s wait]`

## 📥 Required Input Format (`input/`)
Describe the required input files:
```csv
username,profile_url
sama,https://x.com/sama
```

## 📤 Expected Output Deliverables (`output/`)
Describe the structured output schema:
```json
{
  "handle": "sama",
  "name": "Sam Altman",
  "bio": "...",
  "follower_count": 3200000
}
```

## 🛡️ Anti-Detection & Rate-Limiting Rules
* Recommended request jitter: `[e.g. 2.0s - 4.5s]`
* Login wall handling: `[e.g. triggers human takeover via requires_privacy_check=True]`
