# Trend research playbook

Goal: in 10–20 searches, learn what the episode's audience is discussing in the
last ~30 days and how they phrase it. Search each angle separately — one combined
query gives shallow results.

## If available, use these first

- **last30days skill** (github.com/mvanhorn/last30days-skill): Reddit, X, YouTube, TikTok,
  HN, Polymarket in one engagement-ranked brief. Run `/last30days <episode topic>`.
- **ScrapeCreators social-media-research-skills** (`trend-discovery`, `outlier-post-finder`,
  `transcript-intelligence`): needs a ScrapeCreators API key; great for hooks that beat
  a creator's baseline.
- **Podwise CLI / MCP** (`popular`, `search_episode`): what podcast episodes in the niche are trending.
- Otherwise: the built-in web search + fetch tools, using the queries below.

## Query angles (replace TOPIC; add the current year/month; run in the audience's language too)

1. News: `TOPIC news`, `TOPIC <month year>`, `TOPIC controversy`
2. Community: `TOPIC reddit`, `site:reddit.com TOPIC`, `TOPIC opinions`, `TOPIC unpopular opinion`
3. Questions: `TOPIC how to`, `why TOPIC`, `TOPIC worth it`, `TOPIC vs` (autocomplete-style)
4. Creators: `TOPIC podcast episode`, `TOPIC youtube` — note the titles with outsized views
5. Short-form: `TOPIC tiktok`, `TOPIC viral`
6. Demand: Google Trends for 2–3 core terms (rising queries), "People also ask" phrasing
7. Local market (e.g. Polish audience): `TOPIC po polsku`, Polish-language versions of 1–3, wykop.pl, Polish YouTube

Record for each finding: source, date, engagement signal (upvotes/views/comments), and the
exact phrasing people use (short quote, paraphrase the rest).

## trends_brief.md template

```markdown
# Trends brief — <episode / topic> — <date>
Audience: <who> · Market/language: <pl/en> · Clip platforms: <...>

## Top trends right now (ranked by relevance × momentum)
1. **<trend>** — what's happening, why people care. Signal: <e.g. 3 Reddit threads, 2k+ upvotes; YT video 400k views>. [source]
2. ...

## How the audience talks about it
- "<short phrase people actually use>" — [source]
- Pain points / desires: ...

## Open questions nobody answers well
- ...

## Contrarian / under-covered angles
- ...

## Hook angles this episode can own
| # | Angle | Matching moment in the episode (fill after transcript) | Trend link |
|---|---|---|---|
| 1 | | | |

## Title ideas (3)
- curiosity: ...
- number/specific: ...
- contrarian: ...

## Sources
- [Title](URL) — date
```

## keywords.txt

One per line; `#` lines are comments. Include: trend terms, named entities (people,
products, companies), audience phrases, and translations if the episode is in another
language than the research. Lowercase is fine — matching is case-insensitive and substring-based,
so prefer stems for inflected languages (e.g. Polish `sztuczn` matches sztuczna/sztucznej/sztucznej).

```
# trends
ai agents
agent
vibe coding
# polish stems
sztuczn
inteligencj
```
