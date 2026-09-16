# 🕹️ Specification 31: Pure Model-Driven OODA Browser Operation (The Manus AI Standard)

**Version:** 1.0.0  
**Status:** Approved Standard for Batch 10+  
**Scope:** Elimination of Monolithic & Ad-Hoc Scraper Scripts, Direct Interactive OODA Execution (Observe-Orient-Decide-Act), ARIA Tree Interpretation, Fast-Track Student Bypass, and Master 19-Column Schema Validation.

---

## 1. Executive Summary & Paradigm Shift

Past batch runs (Batch 8 & 9) suffered from a recurring architectural anti-pattern:
Instead of utilizing model intelligence to operate the browser interactively, the agent generated 650-line monolithic Python scripts (`adhocs/enricher_engine_batchX.py`) filled with hardcoded DOM selectors and brittle regex.
* **Why this broke**: When an engineer's profile contained credentials (`AbdelRahman Bahieldin, MSc`), naive regex parsed `"MSc"` as a location. When an individual held successive promotions at one company, cumulative duration headers (`"7 yrs 9 mos"`) were parsed as job titles.
* **The Manus AI Standard**: In a true agentic browser operator (Manus AI), the model **never** delegates work to a monolithic background scraper script. Instead, the model itself drives the browser directly through the **Observe-Orient-Decide-Act (OODA)** loop using atomic browser tools.

---

## 2. The Model-Driven OODA Execution Loop

Every profile in a batch is processed through direct, interactive OODA cycles:

```
                  ┌─────────────────────────────────────────┐
                  │ 1. INSPECT RECORD IN INPUT QUEUE        │
                  └────────────────────┬────────────────────┘
                                       │
                      Is Student / Intern / Trainee?
                       ┌───────────────┴───────────────┐
                       ▼ YES                           ▼ NO
          ┌─────────────────────────┐     ┌─────────────────────────┐
          │ Fast-Track Bypass:      │     │ 2. NAVIGATE             │
          │ Set Dormant & Defaults  │     │ socket_launcher.py      │
          │ Instant 0.1s proceed    │     │ navigate(url)           │
          └─────────────────────────┘     └────────────┬────────────┘
                                                       │
                                                       ▼
                                          ┌─────────────────────────┐
                                          │ 3. OBSERVE              │
                                          │ browser_observe()       │
                                          │ (ARIA Tree + Badges)    │
                                          └────────────┬────────────┘
                                                       │
                                                       ▼
                                          ┌─────────────────────────┐
                                          │ 4. ORIENT & DECIDE      │
                                          │ LLM interprets ARIA:    │
                                          │ - Identifies Headline   │
                                          │ - Reads True Location   │
                                          │ - Locates [Contact info]│
                                          └────────────┬────────────┘
                                                       │
                                                       ▼
                                          ┌─────────────────────────┐
                                          │ 5. ACT: CONTACT INFO    │
                                          │ browser_click([Badge])  │
                                          │ browser_observe()       │
                                          │ Extract public details  │
                                          │ Close modal / Esc       │
                                          └────────────┬────────────┘
                                                       │
                                                       ▼
                                          ┌─────────────────────────┐
                                          │ 6. EXPERIENCE TIMELINE  │
                                          │ Inspect Experience      │
                                          │ LLM structures bullets: │
                                          │ • Role @ Co (Date | Dur)│
                                          └────────────┬────────────┘
                                                       │
                                                       ▼
                                          ┌─────────────────────────┐
                                          │ 7. RECORD & CHECKPOINT  │
                                          │ Append 19-col row       │
                                          │ Update live HUD ticker  │
                                          └─────────────────────────┘
```

---

## 3. Strict Elimination of Ad-Hoc Scripts

### 3.1 Zero-Waste Session Hierarchy
No `.py` files shall ever be created in an `adhocs/` directory or inside session logs.
All session workspaces must remain clean and lean:
```
server/logs/YYYY-MM-DD/<Session_Title>_<time>_gid<ID>/
├── SESSION_DOCUMENT.md     # Consolidated markdown report
├── session.jsonl           # Append-only chronological event stream
├── sub_skill.md            # Borrowed SOP playbook
├── input/                  # Input dataset (e.g. batch_10.csv)
└── output/                 # Output deliverables (batch_10_enriched.csv)
```

---

## 4. LLM Extraction Intelligence over ARIA

Because the agent reads the structured accessibility tree rather than raw HTML strings:

1. **Post-Nominal Degrees vs Locations**:
   The LLM recognizes that `"MSc"`, `"Ph.D."`, or `"LSSGB"` are credentials and certifications, not cities or regions. The genuine geographical location is extracted from the profile location node.
2. **Company Duration Headers vs Role Titles**:
   The LLM discerns cumulative headers (e.g. `"Verb Biotics LLC" ➔ "5 yrs"`) from actual roles, correctly preserving the true title (e.g. `"Head of Biotechnology"`) and compiling past positions into bullet points.
3. **Contact Overlay Extraction**:
   When the Contact Info modal opens, the LLM parses visible emails, mobile phone numbers, and portfolio/company websites, delimiting multiple items with `; `.
4. **Student / Intern Bypass Rule**:
   Matches keywords (`Student`, `Intern`, `Undergraduate`, `B.Sc. Candidate`, `M.Sc. Candidate`, `Ph.D. Candidate`, `Trainee`, `Learner`). Records dormant status and bypasses deep navigation in $0.1$ seconds.

---

## 5. Master 19-Column CRM Output Schema

All 19 columns are mandatory and must appear in this exact order:

| # | Column Name | Format / Requirements |
|---|-------------|-----------------------|
| 1 | `Code` | Sequential identifier (e.g. `CONN-0226`) |
| 2 | `First Name` | Given name from source queue |
| 3 | `Last Name` | Surname from source queue |
| 4 | `URL` | Normalized LinkedIn profile URL (`https://www.linkedin.com/in/...`) |
| 5 | `Email Address` | Source email (if available) |
| 6 | `Company` | Initial company name from source queue |
| 7 | `Contact Info` | Public details from profile modal; `Not displayed` if empty |
| 8 | `Position` | Initial role title from source queue |
| 9 | `field` | Industry / sector from source queue |
| 10 | `Headline` | Current profile tagline |
| 11 | `Current Job Title` | Enriched active role title; `Not displayed` if hidden |
| 12 | `Current Company` | Enriched active employer; `Not displayed` if hidden |
| 13 | `Location` | City and country (e.g. `Cairo, Egypt` or `Johannesburg, South Africa`) |
| 14 | `Region` | Clean country name (e.g. `Egypt`, `South Africa`, `Nigeria`) |
| 15 | `Latest Post Date` | Exact or relative post date; `Dormant / No Recent Posts` if none |
| 16 | `Activity Status` | `Active` (<30 days), `Moderate` (1-3 mos), `Dormant` (3+ mos) |
| 17 | `Mutual Connections Count` | Integer display value |
| 18 | `Total Connections / Followers` | Display total (e.g. `500+` or follower count) |
| 19 | `Compacted Work Experience` | Single-cell bulleted past roles: `• Role @ Company (Dates | Duration)` |

---

## 6. Verification & Automated Test Matrix

Spec 31 is verified by `tests/test_spec31_ooda_operation.py`:
1. `test_zero_adhocs_invariant`: Verifies no temporary Python scripts are created in session directories.
2. `test_student_bypass_schema`: Verifies instant bypass produces a complete 19-column row with valid dormant values.
3. `test_master_19_column_schema`: Verifies column order and non-null guarantees.
