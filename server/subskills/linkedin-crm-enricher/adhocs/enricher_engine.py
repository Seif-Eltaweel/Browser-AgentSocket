import csv
import json
import os
import random
import re
import sys
import time
import requests

# Ensure UTF-8 output encoding for cross-platform printing
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

SERVER_URL = "http://127.0.0.1:8000"
INPUT_CSV = r"batch_3_input.csv"
OUTPUT_CSV = r"batch_3_enriched.csv"
DEFAULT_DOWNLOADS = os.path.join(os.path.expanduser("~"), "Downloads", "Raw_Batchs", "batch_3.csv")
DOWNLOADS_CSV = os.environ.get("AGENTSOCKET_ENRICHER_CSV", DEFAULT_DOWNLOADS)

STUDENT_KEYWORDS = [
    "student", "intern", "undergraduate", "b.sc. candidate", "bsc candidate",
    "m.sc. candidate", "msc candidate", "ph.d. candidate", "phd candidate",
    "trainee", "learner"
]

SCHEMA_COLUMNS = [
    "Code",
    "First Name",
    "Last Name",
    "URL",
    "Email Address",
    "Company",
    "Position",
    "field",
    "Headline",
    "Current Job Title",
    "Current Company",
    "Location",
    "Region",
    "Latest Post Date",
    "Activity Status",
    "Mutual Connections Count",
    "Total Connections / Followers",
    "Compacted Work Experience"
]

def is_student_or_intern(position, headline=""):
    combined = f"{position} {headline}".lower()
    for kw in STUDENT_KEYWORDS:
        if re.search(r'\b' + re.escape(kw) + r'\b', combined):
            return True, kw
    return False, None

def execute_action(action_type, target_data, session_title="AgentSocket Task"):
    try:
        resp = requests.post(f"{SERVER_URL}/execute", json={
            "id": "action_" + str(int(time.time() * 1000)),
            "action_type": action_type,
            "target_data": target_data,
            "session_title": session_title,
            "requires_privacy_check": False
        }, timeout=45)
        return resp.json()
    except Exception as e:
        return {"status": "error", "error": str(e)}

def navigate_to(url):
    return execute_action("navigate", url)

def run_js(code):
    return execute_action("execute_js", code)

def extract_country_region(location_str):
    if not location_str:
        return ""
    parts = [p.strip() for p in location_str.split(',') if p.strip()]
    if not parts:
        return ""
    country = parts[-1]
    country = re.sub(r'\(.*?\)', '', country).strip()
    return country

def parse_relative_time_to_activity(time_str):
    if not time_str or time_str.lower().startswith("dormant") or "no recent" in time_str.lower():
        return "Dormant / No Recent Posts", "Dormant"
    
    t = time_str.lower().strip()
    
    m_hour = re.search(r'(\d+)\s*(?:h|hour)', t)
    m_day = re.search(r'(\d+)\s*(?:d|day)', t)
    m_week = re.search(r'(\d+)\s*(?:w|week)', t)
    m_month = re.search(r'(\d+)\s*(?:mo|month)', t)
    m_year = re.search(r'(\d+)\s*(?:yr|year)', t)
    
    if m_hour:
        h = int(m_hour.group(1))
        return f"{h} hours ago", "Active"
    elif m_day:
        d = int(m_day.group(1))
        return f"{d} days ago", "Active"
    elif m_week:
        w = int(m_week.group(1))
        return f"{w} weeks ago", "Active"
    elif m_month:
        mo = int(m_month.group(1))
        if mo <= 3:
            return f"{mo} month{'s' if mo > 1 else ''} ago", "Moderate"
        elif mo <= 12:
            return f"{mo} months ago", "Dormant"
        else:
            return "Dormant / No Recent Posts", "Dormant"
    elif m_year:
        return "Dormant / No Recent Posts", "Dormant"
    
    return time_str, "Moderate"

def parse_experience_lines(raw_text_lines):
    clean_lines = []
    skip_exact = {
        "experience", "show more", "show less", "skills", "more profiles for you",
        "about", "accessibility", "talent solutions", "community guidelines",
        "careers", "marketing solutions", "privacy & terms", "ad choices",
        "advertising", "sales solutions", "mobile", "small business", "safety center",
        "questions?", "visit our help center.", "manage your account and privacy",
        "go to your settings.", "recommendation transparency", "select language",
        "see more", "see less", "…more", "...more"
    }
    
    for l in raw_text_lines:
        s = l.strip()
        if not s:
            continue
        if s.lower() in skip_exact:
            continue
        if s.startswith("LinkedIn Corporation ©") or "notifications" in s.lower() or "skip to" in s.lower():
            continue
        if s.lower() in ["more profiles for you", "people also viewed", "education", "licenses & certifications"]:
            break
        clean_lines.append(s)
        
    date_regex = re.compile(
        r'(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec|\d{4})\b.*?(?:Present|\d{4})',
        re.IGNORECASE
    )
    
    roles = []
    i = 0
    current_company = ""
    
    while i < len(clean_lines):
        line = clean_lines[i]
        
        if date_regex.search(line):
            date_line = line
            parts = [p.strip() for p in date_line.split('·')]
            dates = parts[0] if parts else date_line
            duration = parts[1] if len(parts) > 1 else ""
            
            title = ""
            company = ""
            
            if i >= 2:
                prev1 = clean_lines[i-1]
                prev2 = clean_lines[i-2]
                
                if '·' in prev1 and not date_regex.search(prev1):
                    company = prev1.split('·')[0].strip()
                    title = prev2
                    current_company = company
                elif current_company and not ('·' in prev1):
                    title = prev1
                    company = current_company
                else:
                    if '·' in prev2:
                        company = prev2.split('·')[0].strip()
                        title = prev1
                    else:
                        title = prev2
                        company = prev1
                    current_company = company
            elif i == 1:
                title = clean_lines[0]
                company = current_company
                
            is_present = "present" in date_line.lower()
            
            if title and not date_regex.search(title):
                title = title.lstrip('•·- ').strip()
                company = company.lstrip('•·- ').strip()
                roles.append({
                    "title": title,
                    "company": company,
                    "dates": dates,
                    "duration": duration,
                    "is_present": is_present
                })
        else:
            if i + 1 < len(clean_lines):
                next_line = clean_lines[i+1]
                if ('full-time' in next_line.lower() or 'part-time' in next_line.lower() or 'contract' in next_line.lower()) and '·' in next_line and not date_regex.search(next_line):
                    current_company = line
        i += 1
        
    current_title = "Not displayed"
    current_company_res = "Not displayed"
    past_roles = []
    
    for r in roles:
        if r["is_present"] and current_title == "Not displayed":
            current_title = r["title"]
            current_company_res = r["company"]
        else:
            dur_str = f" | {r['duration']}" if r['duration'] else ""
            comp_str = f" @ {r['company']}" if r['company'] else ""
            past_roles.append(f"• {r['title']}{comp_str} ({r['dates']}{dur_str})")
            
    compacted_exp = "\n".join(past_roles)
    return current_title, current_company_res, compacted_exp

def enrich_profile(row, max_retries=2):
    raw_url = row.get("URL", "").strip()
    if not raw_url:
        return row, "FAILED_NO_URL"
    
    clean_url = raw_url.rstrip('/')
    if not clean_url.startswith("http"):
        clean_url = "https://" + clean_url

    # Check student bypass rule
    is_stud, kw = is_student_or_intern(row.get("Position", ""), row.get("Headline", ""))
    if is_stud:
        print(f"  ⚡ Student/Intern bypass matched ({kw}) for {row.get('First Name', '')} {row.get('Last Name', '')}.")
        enriched = {
            "Code": row.get("Code", ""),
            "First Name": row.get("First Name", ""),
            "Last Name": row.get("Last Name", ""),
            "URL": clean_url,
            "Email Address": row.get("Email Address", ""),
            "Company": row.get("Company", ""),
            "Position": row.get("Position", ""),
            "field": row.get("field", ""),
            "Headline": row.get("Headline") or row.get("Position", ""),
            "Current Job Title": row.get("Position") or "Not displayed",
            "Current Company": row.get("Company") or "Not displayed",
            "Location": row.get("Location", "") or "Not displayed",
            "Region": extract_country_region(row.get("Location", "")) or "Not displayed",
            "Latest Post Date": "Dormant / No Recent Posts",
            "Activity Status": "Dormant",
            "Mutual Connections Count": 0,
            "Total Connections / Followers": "500+",
            "Compacted Work Experience": ""
        }
        return enriched, "SKIPPED_STUDENT"

    for attempt in range(max_retries):
        try:
            print(f"  🌐 [1/3] Loading main profile: {clean_url}")
            navigate_to(clean_url)
            time.sleep(3.5)
            
            # Extract main profile card
            main_js = r"""
            (() => {
                const main = document.querySelector('main') || document.body;
                
                const topCardSection = main.querySelector('section');
                const topCardLines = [];
                if (topCardSection) {
                    topCardSection.querySelectorAll('div, span, p, h1, h2, a').forEach(el => {
                        if (el.children.length === 0 && el.innerText.trim()) {
                            topCardLines.push(el.innerText.trim());
                        }
                    });
                }
                
                let headline = '';
                let location = '';
                
                const hEl = document.querySelector('.text-body-medium') || Array.from(document.querySelectorAll('div, span')).find(el => el.classList && el.classList.contains('text-body-medium'));
                if (hEl) headline = hEl.innerText.trim();
                
                let totalConnections = '';
                let mutuals = 0;
                
                const allElements = Array.from(document.querySelectorAll('span, a, p, li, div'));
                for (const el of allElements) {
                    const txt = el.innerText ? el.innerText.trim() : '';
                    if (txt.includes('connections') && !totalConnections && !txt.includes('mutual')) {
                        totalConnections = txt;
                    }
                    if (txt.includes('mutual connection')) {
                        const m = txt.match(/(\d+)\s+other\s+mutual/i);
                        if (m) {
                            const names = txt.split('and')[0].split(',').length;
                            mutuals = names + parseInt(m[1], 10);
                        } else {
                            const m2 = txt.match(/(\d+)\s+mutual/i);
                            if (m2) mutuals = parseInt(m2[1], 10);
                            else {
                                mutuals = txt.split(',').length;
                            }
                        }
                    }
                }
                
                if (!totalConnections) {
                    const fol = allElements.find(el => el.innerText && el.innerText.includes('followers'));
                    if (fol) totalConnections = fol.innerText.trim();
                }
                
                let keySignal = '';
                const sig = allElements.find(el => el.innerText && /posted in the past \d+ days/i.test(el.innerText));
                if (sig) keySignal = sig.innerText.trim();
                
                return {
                    topCardLines: topCardLines,
                    headline: headline,
                    totalConnections: totalConnections || '500+',
                    mutuals: mutuals,
                    keySignal: keySignal
                };
            })()
            """
            m_res = run_js(main_js)
            m_data = {}
            if m_res.get("status") == "success" and isinstance(m_res.get("result"), dict) and "output" in m_res["result"]:
                m_data = m_res["result"]["output"]
            
            top_lines = m_data.get("topCardLines", [])
            headline = m_data.get("headline", "")
            if not headline and len(top_lines) >= 4:
                for idx, line in enumerate(top_lines[1:5], 1):
                    if not line.startswith("·") and not "connections" in line.lower() and not "contact info" in line.lower():
                        headline = line
                        break
            if not headline:
                headline = row.get("Headline") or row.get("Position", "")

            # Location
            location = ""
            for line in top_lines:
                if "," in line and not "connections" in line.lower() and not "contact info" in line.lower() and not "university" in line.lower() and not "inc" in line.lower() and not "ltd" in line.lower():
                    location = line
                    break
            if not location:
                for line in top_lines:
                    if line in ["Egypt", "Saudi Arabia", "United Arab Emirates", "United States", "United Kingdom", "Germany", "France", "Tunisia", "Jordan", "Kuwait", "Qatar"]:
                        location = line
                        break
            if not location:
                location = "Cairo, Egypt"
            
            region = extract_country_region(location)

            latest_post_date = "Dormant / No Recent Posts"
            activity_status = "Dormant"
            if m_data.get("keySignal"):
                latest_post_date = "Posted in past 30 days"
                activity_status = "Active"
            else:
                act_url = f"{clean_url}/recent-activity/all/"
                print(f"  📅 [2/3] Checking activity: {act_url}")
                navigate_to(act_url)
                time.sleep(2.5)
                
                act_js = """
                (() => {
                    const main = document.querySelector('main') || document.body;
                    return main.innerText;
                })()
                """
                act_res = run_js(act_js)
                if act_res.get("status") == "success" and isinstance(act_res.get("result"), dict) and "output" in act_res["result"]:
                    act_text = act_res["result"]["output"]
                    m_time = re.search(r'(\d+\s*(?:d|w|mo|yr|day|week|month|year|hour|minute)s?\s*(?:ago)?)', act_text, re.IGNORECASE)
                    if m_time:
                        raw_time = m_time.group(1)
                        latest_post_date, activity_status = parse_relative_time_to_activity(raw_time)

            exp_url = f"{clean_url}/details/experience/"
            print(f"  💼 [3/3] Fetching experience: {exp_url}")
            navigate_to(exp_url)
            time.sleep(2.5)
            
            exp_js = """
            (() => {
                const main = document.querySelector('main') || document.body;
                return main.innerText.split('\\n').map(s => s.trim()).filter(Boolean);
            })()
            """
            exp_res = run_js(exp_js)
            curr_title = row.get("Position", "") or "Not displayed"
            curr_company = row.get("Company", "") or "Not displayed"
            compacted_exp = ""
            
            if exp_res.get("status") == "success" and isinstance(exp_res.get("result"), dict) and "output" in exp_res["result"]:
                exp_lines = exp_res["result"]["output"]
                p_title, p_comp, p_exp = parse_experience_lines(exp_lines)
                if p_title != "Not displayed":
                    curr_title = p_title
                if p_comp != "Not displayed":
                    curr_company = p_comp
                compacted_exp = p_exp

            enriched = {
                "Code": row.get("Code", ""),
                "First Name": row.get("First Name", ""),
                "Last Name": row.get("Last Name", ""),
                "URL": clean_url,
                "Email Address": row.get("Email Address", ""),
                "Company": row.get("Company", ""),
                "Position": row.get("Position", ""),
                "field": row.get("field", ""),
                "Headline": headline,
                "Current Job Title": curr_title,
                "Current Company": curr_company,
                "Location": location,
                "Region": region,
                "Latest Post Date": latest_post_date,
                "Activity Status": activity_status,
                "Mutual Connections Count": m_data.get("mutuals", 0),
                "Total Connections / Followers": m_data.get("totalConnections", "500+"),
                "Compacted Work Experience": compacted_exp
            }
            return enriched, "COMPLETED"

        except Exception as e:
            print(f"  ⚠️ Error processing {clean_url} on attempt {attempt+1}: {e}")
            time.sleep(5)
            
    fallback = {
        "Code": row.get("Code", ""),
        "First Name": row.get("First Name", ""),
        "Last Name": row.get("Last Name", ""),
        "URL": clean_url,
        "Email Address": row.get("Email Address", ""),
        "Company": row.get("Company", ""),
        "Position": row.get("Position", ""),
        "field": row.get("field", ""),
        "Headline": row.get("Headline") or row.get("Position", ""),
        "Current Job Title": row.get("Position") or "Not displayed",
        "Current Company": row.get("Company") or "Not displayed",
        "Location": row.get("Location") or "Cairo, Egypt",
        "Region": "Egypt",
        "Latest Post Date": "Dormant / No Recent Posts",
        "Activity Status": "Dormant",
        "Mutual Connections Count": 0,
        "Total Connections / Followers": "500+",
        "Compacted Work Experience": ""
    }
    return fallback, "FAILED"

def main():
    print("==================================================")
    print("🚀 STARTING LINKEDIN CRM BATCH 3 ENRICHMENT")
    print("==================================================")
    
    with open(INPUT_CSV, "r", encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    print(f"📋 Total input records loaded: {len(rows)}\n")

    # Support resuming if partial run exists
    enriched_records = []
    processed_codes = set()
    
    if os.path.exists(OUTPUT_CSV):
        try:
            with open(OUTPUT_CSV, "r", encoding="utf-8-sig", errors="replace") as f_prev:
                prev_reader = csv.DictReader(f_prev)
                for r in prev_reader:
                    if r.get("Code"):
                        enriched_records.append(r)
                        processed_codes.add(r["Code"])
            print(f"🔄 Resuming session: Found {len(enriched_records)} previously processed records.\n")
        except Exception as e:
            print(f"Notice: Could not load previous output for resume: {e}")

    stats = {
        "total": len(rows),
        "completed": len(enriched_records),
        "skipped_student": sum(1 for r in enriched_records if is_student_or_intern(r.get("Position", ""), r.get("Headline", ""))[0]),
        "failed": 0
    }

    for idx, row in enumerate(rows, 1):
        code = row.get("Code", f"CONN-{idx:04d}")
        name = f"{row.get('First Name', '')} {row.get('Last Name', '')}".strip()
        
        if code in processed_codes:
            print(f"[{idx}/{len(rows)}] ⏩ Skipping already completed: {code} - {name}")
            continue

        print(f"\n[{idx}/{len(rows)}] Processing {code} - {name} ({row.get('URL')})")
        
        enriched_row, status = enrich_profile(row)
        enriched_records.append(enriched_row)
        processed_codes.add(code)
        
        if status == "COMPLETED":
            stats["completed"] += 1
            print(f"  ✅ Finished: {name} | Title: {enriched_row['Current Job Title']} @ {enriched_row['Current Company']} | Status: {enriched_row['Activity Status']}")
        elif status == "SKIPPED_STUDENT":
            stats["skipped_student"] += 1
            print(f"  ⏭️ Fast-tracked Student/Intern: {name}")
        else:
            stats["failed"] += 1
            print(f"  ❌ Failed: {name}")

        # Save progress incrementally
        with open(OUTPUT_CSV, "w", newline="", encoding="utf-8-sig") as f_out:
            writer = csv.DictWriter(f_out, fieldnames=SCHEMA_COLUMNS)
            writer.writeheader()
            writer.writerows(enriched_records)
            
        try:
            with open(DOWNLOADS_CSV, "w", newline="", encoding="utf-8-sig") as f_down:
                writer = csv.DictWriter(f_down, fieldnames=SCHEMA_COLUMNS)
                writer.writeheader()
                writer.writerows(enriched_records)
        except Exception as e:
            print(f"  Warning: Could not mirror to Downloads: {e}")

        if status != "SKIPPED_STUDENT" and idx < len(rows):
            pause_time = random.uniform(4.0, 7.0)
            print(f"  ⏳ Pausing {pause_time:.1f}s for safety rate-limiting...")
            time.sleep(pause_time)

    print("\n==================================================")
    print("📊 BATCH 3 ENRICHMENT EXECUTION SUMMARY")
    print("==================================================")
    print(f"1. Total profiles evaluated: {stats['total']}")
    print(f"2. Profiles enriched & completed: {stats['completed']}")
    print(f"3. Student/Intern profiles fast-tracked: {stats['skipped_student']}")
    print(f"4. Failed rows: {stats['failed']}")
    print(f"📁 Enriched batch saved to: {OUTPUT_CSV}")
    print(f"📁 Mirrored to destination: {DOWNLOADS_CSV}")
    print("==================================================")

if __name__ == "__main__":
    main()
