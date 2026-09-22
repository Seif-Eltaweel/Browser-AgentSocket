import requests
import json
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

def run_js(code):
    resp = requests.post("http://127.0.0.1:8000/execute", json={
        "id": "test_1",
        "action_type": "execute_js",
        "target_data": code,
        "session_title": "AgentSocket Task",
        "requires_privacy_check": False
    })
    return resp.json()

js = """
(() => {
    // Scroll down and back up to trigger lazy-loaded sections
    window.scrollBy(0, 800);
    
    const h1 = document.querySelector('h1');
    const name = h1 ? h1.innerText.trim() : '';
    
    // Headline
    const headlineEl = document.querySelector('.text-body-medium') || document.querySelector('[data-generated-suggestion-target]');
    const headline = headlineEl ? headlineEl.innerText.trim() : '';
    
    // Location
    const locEl = document.querySelector('.text-body-small.inline.t-black--light.break-words') 
        || Array.from(document.querySelectorAll('span, div')).find(el => el.classList && el.classList.contains('text-body-small') && el.innerText && el.innerText.includes(',') && !el.innerText.includes('connection'));
    const location = locEl ? locEl.innerText.trim() : '';
    
    // Connections & Mutuals
    let totalConnections = '';
    let mutuals = 0;
    
    const allSpans = Array.from(document.querySelectorAll('span, a, p, li'));
    for (const el of allSpans) {
        const txt = el.innerText ? el.innerText.trim() : '';
        if (txt.includes('connections') && !totalConnections) {
            totalConnections = txt;
        }
        if (txt.includes('mutual connection')) {
            // e.g. "11 mutual connections" or "Mohamed, Ali and 9 other mutual connections"
            const m = txt.match(/(\\d+)\\s+other\\s+mutual/i);
            if (m) {
                // name1, name2 and X other -> 2 + X
                const names = txt.split('and')[0].split(',').length;
                mutuals = names + parseInt(m[1], 10);
            } else {
                const m2 = txt.match(/(\\d+)\\s+mutual/i);
                if (m2) mutuals = parseInt(m2[1], 10);
                else {
                    // count names
                    mutuals = txt.split(',').length;
                }
            }
        }
    }
    
    return {
        name,
        headline,
        location,
        totalConnections,
        mutuals
    };
})()
"""

res = run_js(js)
print(json.dumps(res, indent=2, ensure_ascii=False))
