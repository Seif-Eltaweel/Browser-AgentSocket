# 📖 Subskills Playbook Guide: Authoring High-Accuracy Browser Skills

AgentSocket's **Subskills Engine** allows developers and AI agents to transform ad-hoc automation runs into reusable, versioned, and proven browser automation playbooks.

---

## 1. Why Subskills?

Traditional AI web automation often fails because agents repeatedly "rediscover" brittle DOM selectors, trip bot protections, or struggle with complex single-page apps (SPAs). 

AgentSocket solves this by isolating every run into a structured directory and compiling a **Playbook Contract (`sub_skill.md`)** that records:
* Exact working CSS/XPath selector fallbacks.
* Proven JavaScript extraction snippets tested with CDP.
* Anti-bot delay profiles and pagination rules.
* Strict input and output data schemas.

---

## 2. Directory Layout of a Subskill Workspace

When a subskill is borrowed or generated, it occupies an isolated session workspace:

```
server/logs/YYYY-MM-DD/<Session_Title>_<time>_gid<ID>/
├── SESSION_DOCUMENT.md     # Auto-generated executive report of run
├── session.jsonl           # Exact step-by-step event stream
├── sub_skill.md            # Reusable playbook rules and selector hierarchy
├── input/                  # Target URLs, CSV inputs, and implementation_plan.md
│   └── implementation_plan.md # Mandatory task plan with atomic checklist steps & progress bar
├── output/                 # Extracted deliverables, CSVs, JSON data
├── adhocs/                 # Ad-hoc Python scripts and one-off scrapers
└── artifacts/              # Screenshots and large offloaded payloads
```

---

## 3. The `sub_skill.md` Playbook Specification

Every subskill must include a `sub_skill.md` file following this standard schema:

```markdown
# 🎯 Subskill Playbook: <Human Readable Name>

## 1. Metadata
* **Name:** `unique-kebab-case-identifier`
* **Version:** `1.0.0`
* **Target Domain:** `example.com`
* **Category:** `lead-gen` | `data-extraction` | `form-automation` | `monitoring`
* **Author:** <Name / Agent>
* **Created:** YYYY-MM-DD

## 2. Objective & Automation SLA
* **Primary Objective:** Extract product details (name, price, stock status, ratings).
* **Target Accuracy:** 99%+ on verified selectors.
* **Failure Condition:** If login/captcha modal appears, trigger `requires_privacy_check=True`.

## 3. Selector Hierarchy & Resilience Rules
| Element | Primary CSS Selector | Fallback Selector | Type |
|:---|:---|:---|:---|
| **Title** | `h1.product-title` | `[data-testid="product-name"]` | Text |
| **Price** | `span.price-tag-amount` | `div.pricing-current span` | Currency |
| **Stock** | `div.availability-badge` | `p.stock-status` | Enum |

## 4. Extraction Snippet (CDP Execution)
```javascript
(() => {
    const getText = (sel) => document.querySelector(sel)?.innerText?.trim() || "N/A";
    const getAttr = (sel, attr) => document.querySelector(sel)?.getAttribute(attr) || null;

    return {
        url: window.location.href,
        title: getText('h1.product-title') || getText('[data-testid="product-name"]'),
        price: getText('span.price-tag-amount'),
        in_stock: !document.querySelector('.out-of-stock-alert'),
        extracted_at: new Date().toISOString()
    };
})();
```

## 5. Anti-Detection & Jitter Strategy
* **Navigation Delay:** 1.5s to 3.0s random delay between page loads.
* **Scroll Profile:** Smooth scroll `window.scrollBy({ top: 400, behavior: 'smooth' })` before extraction to trigger lazy-loaded images.
* **Rate Limits:** Maximum 30 page extractions per session.

## 6. Input / Output Schema Contract

### Expected Input (`input/targets.csv`):
```csv
product_id,product_url
P101,https://example.com/item/101
P102,https://example.com/item/102
```

### Generated Output (`output/results.json`):
```json
[
  {
    "product_id": "P101",
    "title": "Example Gadget",
    "price": "$29.99",
    "in_stock": true
  }
]
```
```

---

## 4. Managing Subskills via CLI

### 4.1 Registering a Completed Session as a Subskill
Once you or an agent has completed a successful browser session, register it in the central registry (`server/logs/subskills_index.json`):

```bash
python server/socket_launcher.py subskills register \
  --session server/logs/2026-08-21/Product_Scraper_14-30_gid101 \
  --name product-catalog-extractor \
  --title "E-Commerce Product Catalog Extractor" \
  --tags "ecommerce,scraping,pricing"
```

### 4.2 Listing Available Subskills
```bash
python server/socket_launcher.py subskills list
```

### 4.3 Borrowing a Subskill for a New Task
When starting a new task, borrow the playbook into a fresh session folder with custom inputs:

```bash
python server/socket_launcher.py subskills borrow product-catalog-extractor \
  --title "Run 2 - Summer Catalog Pricing" \
  --input ./new_product_urls.csv
```

---

## 5. Best Practices for High-Accuracy Automation

1. **Avoid Brittle Generated Classes**: Stay away from auto-generated hashed CSS class names (e.g. `._2jX9_`) which change across web deployments. Prefer semantic attributes like `data-testid`, `aria-label`, `name`, or stable ID selectors.
2. **Handle Dynamic SPAs**: Always use `waitForSelector` or evaluate predicates via CDP promises rather than fixed arbitrary sleeps.
3. **Trigger Human Takeover for MFA/Bot Checks**: If Cloudflare turnstiles or MFA screens appear, let the human operator take control via `requires_privacy_check=True` instead of getting IP blocked.
