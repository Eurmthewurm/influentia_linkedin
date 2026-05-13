# ─────────────────────────────────────────────────────────────────────────────
# config.py  —  Fill in your credentials and settings before running
# ─────────────────────────────────────────────────────────────────────────────

# ── 1. Claude API key ─────────────────────────────────────────────────────────
#    Get yours at: https://console.anthropic.com
ANTHROPIC_API_KEY = ""  # Set via .env or the app settings UI

# ── 2. LinkedIn session cookie ────────────────────────────────────────────────
#    How to get it:
#    1. Open LinkedIn in Chrome/Firefox
#    2. Press F12 → Application tab → Cookies → linkedin.com
#    3. Copy the value of the cookie named "li_at"
LINKEDIN_LI_AT_COOKIE = ""  # Set via the app's LinkedIn connect flow

# ── 3. Your LinkedIn profile info (used to personalise outreach) ──────────────
YOUR_NAME       = "Ermo"               # your first name
YOUR_COMPANY    = "Authentik Studio"         # your company name
YOUR_GOAL       = "book a quick call"  # what you want prospects to do
YOUR_GOAL_LINK  = "https://calendly.com/ermo/discoverycall"         # e.g. Calendly link

# ── 4. What you're selling (your "offering" — be specific!) ──────────────────
#    Follow the Kakiyo rule: one offering = one product + one audience.
#    Include: problem solved, how, proof, differentiator.
YOUR_OFFERING = """
# Bridge the Credibility Gap With Strategic Video Content

Expert-led business owners excel in the real world — visiting job sites, demonstrating genuine niche authority, and driving meaningful results for their clients. However, their content often fails to reflect this expertise. Most AI-driven tools like Descript and Opus produce generic, low-impact clips that neither capture the depth of their work nor build the trust required by high-value clients. 

**Our offer bridges this gap, elevating your content to match the exceptional quality of your services.**

---

## Key Problems We Solve

### **The Credibility Gap**

Many founders and business owners have a substantial disconnect between the work they do and how it’s perceived online. Your expertise and authority in your field are not converting into visible, trust-inducing content. Our solutions ensure the market sees the true value you bring.

### **The Time Trap**

Time is your most valuable resource. Founders and their teams are losing countless hours editing their own footage — time that could be better spent on business development, deepening client relationships, or increasing sales. By taking over creative direction and post-production, we free you from tasks that are outside your core strengths and passions.

### **No Content System**

Posting inconsistently and lacking a strategic structure leads to a weak online presence. Most clients have no repeatable system or clear content pillars. We address this by:

- Building a reliable content framework
- Producing weekly talking-head episodes for consistent visibility
- Creating anchor pieces (mini-documentaries) that deepen credibility
- Mapping all content for effective LinkedIn distribution

### **Story Left on the Table**

Your lived experiences — field visits, personal stories, and niche expertise — are your most valuable content assets. Without an expert’s eye, these stories often go untold or get minimized to uninspiring selfie videos. With our Tier 2 offering, we unlock the full documentary potential of your unique journey, ensuring your story resonates.

### **Proof Problem**

B2B buyers often hesitate without visible evidence of results. Concrete case studies and proof points are missing. Our proven track record — like the J-Griff project, which grew from 2M to 8M views in just 18 months — demonstrates how a well-built content system can compound results over time.

---

## Our Promise in a Line

**We solve the gap between what an expert knows and what the market sees through strategic video content.**

---

## Core Benefits

- **Creative Partnership:** Gain a partner who handles your entire video content system, from strategy and storytelling to production and editing.
- **Expertise Amplified:** Your unique skills and knowledge become content that inspires, moves people, and authentically grows your business.
- **Consistent Output:** Transition from sporadic posting to a robust, systematized content engine aligned with your business goals.

---

## Measurable Results

- Clients transition from being invisible to recognized industry authorities.
- Example: One creator expanded from 2M to 8M views in just 18 months.
- For B2B clients, results include:
  - More inbound leads
  - Stronger market positioning
  - Shorter sales cycles, as trust is built before the first call

---

## Who We Serve

Ideal for expert-led B2B service businesses and personal brands, including:

- Consultants
- Agency owners
- Niche recruiters
- Coaches

If you are already delivering remarkable work but your content does not yet reflect your authority, and you are active on LinkedIn and ready to invest in a scalable system, our service is built for you.

---

## What Sets Us Apart

- **Film-Grade Storytelling:** We combine documentary-level storytelling with strategic content planning.
- **Comprehensive System:** Unlike most editors who just cut footage, or strategists who do not shoot, we provide both full-spectrum strategy and hands-on filmmaking.
- **World-Class Talent:** When your story demands it, we bring in documentary filmmakers to unlock its full potential.
- **Narrative First:** You get a creative partner who thinks in stories, not just deliverables, ensuring your brand voice and expertise shine through every piece.

---
```

"""

# ── 5. Safety settings (do NOT lower these — LinkedIn will ban you) ───────────
MAX_CONNECTION_REQUESTS_PER_DAY = 15   # LinkedIn soft limit is ~20-25/day
DELAY_BETWEEN_REQUESTS_SECONDS  = 90   # min gap between each action (seconds)
POLL_INTERVAL_HOURS             = 4    # how often to check for new acceptances

# ── 6. File paths ─────────────────────────────────────────────────────────────
LEADS_EXCEL_PATH = "AU_Mining_Staffing_Leads.xlsx"  # must be in same folder
STATE_FILE_PATH  = "state.json"
LOG_FILE_PATH    = "outreach_log.txt"
