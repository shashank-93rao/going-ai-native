# References: module 17

Each entry says what to take from the source. "Verified" means the claim was checked against the page while writing this module (October 2026). Items marked *secondary* were seen only through coverage.

## Code review at agent volume
- **Addy Osmani, Morgan Westlee Lunt, Qing Wang, "How the Claude Code team does code review"** (claude.dev, 2026-10-15). https://claude.dev/blog/solving-code-review-at-anthropic/
  The primary source for this module. Take: the goal of "minimum human review time that doesn't raise reverts or incidents"; the seven review layers; the low/medium/high tier table with 0/1/2 approvals; "an agent's approval never counts as a person's"; approvals per commit; REVIEW.md contents; round cap of three; the daily eval built from incident PRs; the numbers (~90% Claude-written, PRs more than doubled, reverts down more than 40%, 16% to 54% substantive comments, 65% to 78% one-round pass, 2.08 to 1.32 mean reviews). Verified. Note it does **not** publish the verifier count, the voting threshold, or the style A/B result; the course's 3/5 verifiers and strict majority are our own defaults.
- **Anthropic, "Redesigning source control at Anthropic"** (2026-10). https://www.anthropic.com/engineering/redesigning-source-control
  Take: merge volume of about 2,500 per day in May 2026 to more than 30,000 in September; replacing human-scale gates; "the role of the engineers was to tell Claude 'no'". From course research notes.
- **Anthropic, Claude Code best practices** (living doc). https://code.claude.com/docs/en/best-practices
  Take: the writer/reviewer split; "Report gaps, not style preferences"; the warning that reviewers asked to find gaps always find some.
- **Anthropic, Prompting best practices.** https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices
  Take: review prompts that say "only report high-severity" are followed literally; ask for everything and filter in a separate pass.
- **Alistair Gray (Stripe), "Minions: Stripe's one-shot, end-to-end coding agents"** (2026-02-09). https://stripe.dev/blog/minions-stripes-one-shot-end-to-end-coding-agents
  Take: 1,000+ fully minion-produced PRs merged per week, all human-reviewed; the launching engineer opens the PR and requests review; at most two CI runs; Slack-thread launch; isolated devboxes; curated tool subsets. Verified.
- **Max Charas and Marc Bruggmann (Spotify), Honk series parts 1-3** (2025-11 to 2025-12). https://engineering.atspotify.com/2025/11/spotifys-background-coding-agent-part-1 , https://engineering.atspotify.com/2025/12/feedback-loops-background-coding-agents-part-3
  Take: the three failure modes (most serious: passes CI but wrong, part 3); verifiers in a Stop hook; the LLM judge vetoing about a quarter of sessions with about half recovering; "We have yet to invest in evals for our judge". Part 3 verified.
- **Walden Yan (Cognition), "Multi-Agents: What's Actually Working"** (2026-04-22). https://cognition.com/blog/multi-agents-working
  Take: clean-context Devin Review catches about 2 bugs per PR, about 58% severe; writes stay single-threaded. Verified.

## Cognitive debt and shared understanding
- **Margaret-Anne Storey, "Cognitive debt"** (2026-02-09). https://margaretstorey.com/blog/2026/02/09/cognitive-debt/
  Take: Naur's theory-building view; the student-team story; warning signs; practices. Quotes verified.
- **Thoughtworks Technology Radar, "Codebase cognitive debt"** (Vol. 34, April 2026, Caution). https://www.thoughtworks.com/radar/techniques/codebase-cognitive-debt
  Take: the definition, and the recommendation of fitness functions and feedback sensors for coding agents. Verified.
- **Armin Ronacher, "The Final Bottleneck"** (2026-02-13). https://lucumr.pocoo.org/2026/2/13/the-final-bottleneck/
  Take: review is now the constraint; accountability stays human; machine review of machine output invites rubber-stamping. Verified.
- **Armin Ronacher, "The Coming Loop"** (2026-06-23). https://lucumr.pocoo.org/2026/6/23/the-coming-loop/
  Take: loops erode understanding of code you care about; defensive code; "I want to understand the code I ship." Verified. Ronacher does not use the term "cognitive debt" in these posts; the course applies the term to his argument.
- **Kent Beck, "Augmented Coding: Beyond the Vibes"** (2025-06-25). https://newsletter.kentbeck.com/p/augmented-coding-beyond-the-vibes
  Take: the three warning signs (loops, functionality nobody requested, cheating on tests).
- **Simon Willison, Agentic Engineering Patterns** (guide). https://simonwillison.net/guides/agentic-engineering-patterns/
  Take: linear walkthroughs for understanding agent-written code; the anti-pattern of handing unreviewed agent code to collaborators.
- **Dex Horthy (HumanLayer), Advanced context engineering for coding agents.** https://github.com/humanlayer/advanced-context-engineering-for-coding-agents/blob/main/ace-fca.md
  Take: review leverage is highest at research and plan.

## Measuring productivity
- **METR, "Measuring the Impact of Early-2025 AI on Experienced Open-Source Developer Productivity"** (2025-07-10). https://metr.org/blog/2025-07-10-early-2025-ai-experienced-os-dev-study/
  Take: 19% slower; forecast +24%, perceived +20%; the caveats. 
- **METR, uplift update** (2026-02-24). https://metr.org/blog/2026-02-24-uplift-update/
  Take: point estimates of speedup with wide intervals, and why the design broke (refusals, withheld tasks, concurrent agents). Verified.
- **DORA, software delivery metrics.** https://dora.dev/guides/dora-metrics/
  Take: the five current metrics, including deployment rework rate. Verified.
- **InfoQ, coverage of the 2025 DORA State of AI-assisted Software Development report.** https://www.infoq.com/news/2025/09/dora-state-of-ai-in-dev-2025
  Take: AI as an amplifier; throughput up while instability keeps rising. *Secondary*; read the full report on dora.dev before quoting numbers.
- **Shopify memo, April 2025** (coverage). https://www.digitalcommerce360.com/2025/04/08/internal-memo-shopify-ceo-declares-ai-non-optional/
  *Secondary.* Used only as an example of a mandate, which is not a measurement.

## Operating model
- **Anthropic, "Building effective agent automations"** (2026-10-08). https://claude.dev/blog/building-effective-agent-automations/
  Take: scheduled agents fail quietly; bookmarks not time windows; ledgers and "maybe posted"; unreadable is not quiet; budgets of 3 to 5x a normal run that pause.
- **Harrison Chase, "Introducing ambient agents"** (2025-01-14). https://www.langchain.com/blog/introducing-ambient-agents
  Take: notify / question / review; the Agent Inbox.
- **Mitchell Hashimoto, "My AI Adoption Journey"** (2026-02-05). https://mitchellh.com/writing/my-ai-adoption-journey
  Take: end-of-day agents; reproducing your own past commits; notifications off; every agent mistake becomes an AGENTS.md line or a tool.

## Hiring and career
- **Andrej Karpathy, Sequoia AI Ascent 2026 talk summary** (2026-04-30). https://karpathy.bearblog.dev/sequoia-ascent-2026/
  Take: big-project hiring and adversarial agents; "You are still responsible for your software"; the "outsource your thinking" line, which he cites from a tweet. Verified.
- **Andrej Karpathy, "Vibe coding MenuGen"** (2025-04-27). https://karpathy.bearblog.dev/vibe-coding-menugen/
  Take: the email-vs-user-ID payment bug as the design-judgment probe.
- **Tristan Hume (Anthropic), "Designing AI-resistant technical evaluations"** (2026-01-21). https://www.anthropic.com/engineering/AI-resistant-technical-evaluations
  Take: the saturated take-home, the redesign, and AI use allowed. Quote verified.
- **Simon Willison, "Vibe engineering"** (2025-10-07). https://simonwillison.net/2025/Oct/7/vibe-engineering/
  Take: agentic engineering needs more skill; AI amplifies expertise.
