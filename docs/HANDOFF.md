# Handoff — 2026-05-12/13

## Where We Are

### Demo Video (IN PROGRESS)
- File: `landing/demo.html` — open in browser to preview the live version
- Renderer: `landing/render_demo.py` — Playwright frame capture → ffmpeg MP4
- Output: `landing/demo.mp4` (1MB, 30fps, 1280x720, 32s)

**User feedback:** Pacing feels a bit fast. Needs to be slowed down before publishing.

**TODO for tomorrow:**
- Slow down scene transitions and overall pacing
- Consider lengthening to 35-40s
- Scene 3 typewriter might need to be slower
- Test on influentia.io background (the HTML is portable — just needs hosting)
- Optional: add background music, add logo watermark

**Scene breakdown (current timing):**
- Scene 1 (0-6s): Problem — "Your next customer is complaining online right now" + 3 floating cards
- Scene 2 (6-16s): How it works — 3 steps with fade-up animations
- Scene 3 (16-24s): Product console — Draft queue with typewriter animation
- Scene 4 (24-28s): Social proof — "3 calls in 10 days" + testimonial
- Scene 5 (28-32s): CTA — Logo, pricing, button

**To re-render after changes:**
```bash
cd ~/Desktop/linkedin_outreach/landing && python render_demo.py
```

### Influentia Project Status
- Landing page: DONE, deployed at influentia.io
- Success page + setup guide: DONE
- Beta tier (50K tokens/day): DONE in worker code
- 10 beta keys: Generated, NOT yet inserted into D1
- Reddit post: Drafted in `REDDIT_POST.md`, NOT yet posted
- Stripe/Resend: All 5 secrets confirmed set

### Daily Cron Jobs (NEW)
- 08:00 — Morning AI News Digest (job: 47cb6575fb65)
- 08:05 — Morning Check-In (job: 8dbb917513e8)
