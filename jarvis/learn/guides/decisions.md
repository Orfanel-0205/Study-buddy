---
title: Making real decisions (business and tech)
summary: Practical tools for deciding - a weighted decision matrix, reversible vs irreversible decisions, pre-mortems, small experiments with stop rules, unit economics and break-even, and common thinking traps.
tags: decision, decisions, choose, compare, options, decision matrix, pre-mortem, experiment, break-even, unit economics, pricing, profit, risk, sunk cost, startup, business
order: 10
---

# Making real decisions (business and tech)

Most decisions feel big because they're vague. These tools make them concrete. Jarvis has the matrix and
the calculator built in (**Build → Decide** and **Build → Numbers**).

## 1. Is it a one-way door or a two-way door?

Jeff Bezos (Amazon's 2015 shareholder letter) split decisions into:
- **Two-way doors**, reversible: try a price, a tool or a design; you can undo it. **Decide fast**, then learn.
- **One-way doors**, hard to undo: quitting school or a job, signing a long contract, a big loan. **Slow down**,
  get advice, and test cheaply first.

Most startup decisions are two-way doors. Treat them that way.

## 2. A weighted decision matrix

1. List the options (2-5).
2. List what matters (criteria): cost, time to first money, how much you'd learn, risk, how much you enjoy it, fit with your skills.
3. Give each criterion a **weight** (1-5): how much it matters to you right now.
4. Score each option on each criterion (1-5).
5. Multiply and add. The highest total is your starting point, not an order.

| Option | Cost (w3) | Time to first ₱ (w5) | Learning (w2) | Risk (w4) | Total |
|---|---|---|---|---|---|
| Restaurant websites (service) | 5 → 15 | 4 → 20 | 4 → 8 | 4 → 16 | **59** |
| Build a SaaS first | 3 → 9 | 1 → 5 | 5 → 10 | 2 → 8 | 32 |

If the top two are close (within about 10%), the matrix is telling you: **test both cheaply**, or choose
the more reversible one.

## 3. Pre-mortem (Gary Klein)

Imagine it's 3 months from now and the plan **failed**. Write down every reason why: "owners never
answered", "we built for 2 months and nobody paid", "the free host went down during a demo". Then
prevent or test the top 3 reasons this week.

## 4. Run small experiments with a stop rule

Write an experiment before you start:
> **We believe** restaurant owners want an up-to-date menu online.
> **We'll test it by** showing a sample page to 15 owners this week.
> **We're right if** at least 3 agree to set it up (even for free).
> **If not,** we change the offer (Google listing only) or the customer type.

Time-box it (one or two weeks). A clear "if not" protects you from the **sunk cost** trap: continuing
only because you've already spent time.

## 5. Know your numbers (unit economics)

| Term | Meaning |
|---|---|
| Price | What one client pays per month (or once) |
| Cost to serve | Hosting, domain, tools and your time per client |
| Margin | Price − cost to serve |
| Fixed costs | Monthly costs no matter how many clients (tools, internet, transport) |
| Break-even clients | Fixed costs ÷ margin per client (round up) |
| CAC | Cost to get one client (transport, printing, ads ÷ new clients) |
| Payback | CAC ÷ monthly margin: months until a client has paid back what you spent to win them |

Example: fixed costs ₱1,500/month, price ₱800/month, cost to serve ₱200 → margin ₱600 → break-even
= 1,500 ÷ 600 = 2.5, so **3 clients**. Use your own real numbers.

## 6. Thinking traps to watch for

- **Sunk cost:** "We already spent a month, we can't stop." The month is gone either way. Decide on what happens next.
- **Shiny object:** a new idea every week. Finish one experiment before starting another.
- **Confirmation bias:** only hearing the "yes". Ask "what would make you *not* use this?"
- **Analysis paralysis:** for two-way doors, a decent decision today beats a perfect one next month.
- **Doing it alone:** ask two people who know the area (a teacher, a business owner) before a one-way door.

## 7. The 10/10/10 test (Suzy Welch)

How will you feel about this decision in 10 minutes, 10 months and 10 years? It separates today's
stress from what really matters.
