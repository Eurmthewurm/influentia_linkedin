---
title: "Influentia Daily Distribution Engine"
trigger: "Daily distribution automation for Influentia"
version: "1.0.0"
---

# Distribution Engine Architecture

## Component 1: `generate-seo-pages.py`
Generates programmatic SEO landing pages for 25 long-tail keywords. Each page has unique content, structured data, internal linking. Saves to `landing/seo/[keyword].html`.

## Component 2: `generate-blog-post.py`  
Creates one blog post per day on rotating topics. Each post is 1500+ words, targets real keywords, includes author schema. Saves to `landing/blog/[slug].html`.

## Component 3: `generate-social-drafts.py`
Produces daily social content drafts:
- 1 Reddit post/comment (with 3 target thread suggestions)  
- 1 X/Twitter thread (3-5 tweets)
- 1 LinkedIn founder post (5-8 paragraphs)
All saved to `distribution/YYYY-MM-DD-[platform].md`

## Component 4: `find-reddit-opportunities.py`
Scans r/SaaS, r/entrepreneur, r/startups for active threads about outreach/lead gen/AI tools. Finds 3 high-traffic posts where Influentia mention would be valuable. Drafts helpful responses.

## Component 5: `ai-directory-tracker.py`
Tracks submissions to AI directories. Generates submission content for each. Maintains status (submitted pending, live).

## Execution Schedule
- **SEO Pages:** 5/day until all 25 done
- **Blog Post:** 1/day
- **Social Drafts:** 1/day (all 3 formats)
- **Reddit Scan:** 1/day
- **AI Directory Submissions:** 2/day until 10 done
