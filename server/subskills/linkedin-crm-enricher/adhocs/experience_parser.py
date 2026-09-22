import re

def parse_experience_text(raw_text_lines):
    """
    Robust parser for LinkedIn experience section lines.
    Handles:
    - Standard single-role entries: Title, Company · Type, Dates · Duration, Location
    - Multi-role company entries: Company, Total Duration, Location -> Sub-roles: Title, Dates · Duration
    """
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
        if s.lower() == "more profiles for you" or s.lower() == "people also viewed" or s.lower() == "education":
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
            
            # Inspect previous lines
            if i >= 2:
                prev1 = clean_lines[i-1]
                prev2 = clean_lines[i-2]
                
                # Check if prev1 has company info with '·' e.g. "Infomineo · Full-time"
                if '·' in prev1 and not date_regex.search(prev1):
                    company = prev1.split('·')[0].strip()
                    title = prev2
                    current_company = company
                # Check if prev2 was a company header e.g. "Jumia Egypt" followed by prev1 "Head of Accounting"
                elif current_company and not ('·' in prev1):
                    title = prev1
                    company = current_company
                else:
                    # Generic case: prev1 is company, prev2 is title or vice versa
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
                # Clean title if it contains bullets
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
            # Check if this line looks like a standalone company header (e.g. followed by "Full-time · 2 yrs")
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
