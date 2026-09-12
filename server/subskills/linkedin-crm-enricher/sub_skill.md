---
name: linkedin-crm-enricher
display_title: "LinkedIn Personal CRM Profile Enricher"
description: "Enriches LinkedIn profiles with 17-column CRM schema, experience trees, mutual connections, and activity status."
version: "1.2"
platform: "linkedin.com"
rate_limit_pause_range: [4.0, 7.5]
tags: ["linkedin", "crm", "enrichment", "lead-gen", "experience", "profile", "connections"]
---

# LinkedIn CRM Enrichment Subskill Playbook

## 1. Tested Navigation Routes
* Main Profile: `https://www.linkedin.com/in/{username}/`
* Experience Details: `https://www.linkedin.com/in/{username}/details/experience/`
* Recent Activity Feed: `https://www.linkedin.com/in/{username}/recent-activity/all/`

## 2. Verified DOM Selectors & Extraction Rules
* **Headline:** `.text-body-medium` or first non-badge text line in Top Card.
* **Mutual Connections:** Scan text for `(\\d+)\\s+other\\s+mutual` or `(\\d+)\\s+mutual`.
* **Followers / Connections:** Scan text for `connections` or `followers`.
* **Activity Status:**
  * `<30 days` -> `Active`
  * `1–3 months` -> `Moderate`
  * `3+ months or no posts in 12 mo` -> `Dormant` (`Dormant / No Recent Posts`)

## 3. Data Schema & Contracts (17 Columns)
| Column | Type | Rules |
|---|---|---|
| `Code` | String | Sequential ID (`CONN-0001`) |
| `First Name` | String | Extracted / Source first name |
| `Last Name` | String | Extracted / Source last name |
| `URL` | String | Clean `https://www.linkedin.com/in/...` link |
| `Email Address` | String | Contact email if available |
| `Company` | String | Initial company name |
| `Position` | String | Initial job position |
| `field` | String | Industry field / domain |
| `Headline` | String | Full headline tagline |
| `Current Job Title` | String | Current role |
| `Current Company` | String | Current organization |
| `Location` | String | `City, Country` |
| `Region` | String | Country name only (e.g. `Egypt`) |
| `Latest Post Date` | String | Date or relative time (e.g. `3 days ago`) |
| `Activity Status` | String | `Active` \| `Moderate` \| `Dormant` |
| `Mutual Connections Count` | Integer | Count of shared mutual connections |
| `Total Connections / Followers` | String | Displayed count (`500+`) |
| `Compacted Work Experience` | Text | `• Role @ Company (Dates \| Duration)` |

## 4. Student / Intern Fast-Track Rule
If `Position` / `Headline` contains `Student`, `Intern`, `Undergraduate`, `Trainee`, `Learner`:
* Skip deep loads.
* Set `Latest Post Date` = `Dormant / No Recent Posts`, `Activity Status` = `Dormant`, `Compacted Work Experience` = `""`.
