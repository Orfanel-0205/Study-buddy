---
title: Business rules: from policy to tested code
summary: How to turn a company's policies into clear, testable business rules - rule types, writing them well, decision tables, where they belong in code, examples in Python, PHP, JavaScript and TypeScript, and how to test and change them safely.
tags: business rules, requirements, decision table, validation, domain logic, policy, rule engine, authorization, testing, python, php, laravel, javascript, typescript
order: 8
---

# Business rules: from policy to tested code

A **business rule** is a statement of how the business works that software must respect:
*"Orders of ₱5,000 or more ship free."* *"A student with 3 unexcused absences gets a warning."*
*"Only a manager can approve a refund over ₱10,000."* Most real bugs at work aren't syntax errors;
they're a rule implemented slightly wrong, in only one place, or not at all.

## The kinds of business rules

| Kind | What it does | Example |
|---|---|---|
| **Constraint** | what must or must not be true | "A customer may have at most 3 unpaid invoices." |
| **Computation** | how a value is calculated | "VAT is 12% of the taxable amount." |
| **Inference** | derives a fact from other facts | "A customer with ₱100,000+ purchases this year is Gold." |
| **Action enabler / trigger** | when something happens, do something | "After 3 failed logins, lock the account for 15 minutes." |
| **Authorization** | who may do what | "Only HR can see salaries." |

**Validation vs business rule:** "the email looks like an email" is input validation (format).
"a member can borrow at most 5 books" is a business rule (policy). Both must be checked on the server.

## Writing rules well

- **One rule per statement**, with an ID (`BR-07`) so code, tests and tickets can point to it.
- **Testable, not vague:** "large orders" → "orders of ₱5,000 or more"; "recently" → "in the last 30 days".
- **Say the boundary:** "₱5,000 or more" vs "more than ₱5,000" is a real difference. Ask when it's unclear.
- **Name the owner and source:** who decides the rule (finance, HR, the professor) and where it's written.
- **Templates that work:**
  - `<subject> must / must not <condition>`: "A refund must not exceed the amount paid."
  - `WHEN <event> IF <conditions> THEN <outcome>`: "WHEN an order is placed IF the total is ₱5,000 or more THEN shipping is free."
  - Acceptance criteria: `Given / When / Then` (one scenario per important case).

## Decision tables

When several conditions combine, write a **decision table** before writing code. Example: shipping fee.

| Rule | Member? | Order total | Region | Shipping fee |
|---|---|---|---|---|
| R1 | any | ≥ ₱5,000 | any | ₱0 |
| R2 | yes | < ₱5,000 | Metro Manila | ₱0 |
| R3 | yes | < ₱5,000 | Province | ₱80 |
| R4 | no | < ₱5,000 | Metro Manila | ₱100 |
| R5 | no | < ₱5,000 | Province | ₱180 |

Check the table before coding:
- **Complete:** every combination has an answer (here: 2 member values × 2 totals × 2 regions are covered).
- **No conflicts:** two rules never give different answers for the same input (if they overlap, define a **priority**: here R1 wins).
- **Boundaries:** exactly ₱5,000 → R1. Write that down; it's the case people disagree about.

The table becomes your **tests**, one test per row plus the boundary.

## Where rules belong in code

- **On the server, in one place.** Put rules in the domain/service layer (a function or class such as
  `ShippingPolicy`), not scattered across controllers, the UI and SQL. The UI may *also* check, for a
  better experience, but the server is the one that must enforce it.
- **Pure functions when possible:** input in, decision out, no database calls inside. Easy to test and to
  reuse from an API endpoint, a scheduled job or an import script.
- **Return the reason**, not just yes/no: `{"allowed": false, "rule": "BR-12", "reason": "3 unpaid invoices"}`.
  Users and support staff need to know *why*.
- **Database constraints as the last line of defense:** `NOT NULL`, `UNIQUE`, `CHECK (quantity > 0)`,
  foreign keys. They protect the data even if a bug skips the code.
- **Configurable values** (rates, limits, thresholds) belong in configuration or a settings table with
  an *effective date*, not hard-coded, when they change every year (tax rates, fees).
- **Rule engines** (Drools, json-rules-engine, Laravel policies for authorization) are worth it only when
  rules change very often or non-developers must edit them. For most projects, well-tested code is simpler.

## The same rule in four languages

```python
# Python: a pure function that follows the decision table, with the reason
FREE_FROM = 5000

def shipping_fee(total: float, member: bool, region: str) -> tuple[int, str]:
    if total >= FREE_FROM:
        return 0, "R1: orders of 5,000 or more ship free"
    if member:
        return (0, "R2: members in Metro Manila") if region == "metro" else (80, "R3: members in the provinces")
    return (100, "R4: Metro Manila") if region == "metro" else (180, "R5: provinces")
```

```php
<?php
// PHP: a small policy class used by the controller (Laravel: app/Services/ShippingPolicy.php)
final class ShippingPolicy
{
    public const FREE_FROM = 5000;

    public function fee(float $total, bool $member, string $region): array
    {
        if ($total >= self::FREE_FROM) return ['fee' => 0, 'rule' => 'R1'];
        if ($member) return $region === 'metro' ? ['fee' => 0, 'rule' => 'R2'] : ['fee' => 80, 'rule' => 'R3'];
        return $region === 'metro' ? ['fee' => 100, 'rule' => 'R4'] : ['fee' => 180, 'rule' => 'R5'];
    }
}
// Authorization rules in Laravel go in a Policy: Gate::allows('approve', $refund)
```

```ts
// TypeScript: types make impossible states impossible
type Region = "metro" | "province";
interface Decision { fee: number; rule: "R1" | "R2" | "R3" | "R4" | "R5" }

export function shippingFee(total: number, member: boolean, region: Region): Decision {
  if (total >= 5000) return { fee: 0, rule: "R1" };
  if (member) return region === "metro" ? { fee: 0, rule: "R2" } : { fee: 80, rule: "R3" };
  return region === "metro" ? { fee: 100, rule: "R4" } : { fee: 180, rule: "R5" };
}
```

```js
// JavaScript: a rule table instead of nested ifs (first matching row wins)
const RULES = [
  { id: "R1", when: (o) => o.total >= 5000, fee: 0 },
  { id: "R2", when: (o) => o.member && o.region === "metro", fee: 0 },
  { id: "R3", when: (o) => o.member, fee: 80 },
  { id: "R4", when: (o) => o.region === "metro", fee: 100 },
  { id: "R5", when: () => true, fee: 180 },
];
export const shippingFee = (order) => RULES.find((r) => r.when(order));
```

## Testing business rules

- **Table-driven tests:** one row per decision-table row, plus every boundary (4,999.99 / 5,000 / 5,000.01).
- Test the **reason** too, not only the value.
- **Given / When / Then** acceptance criteria for the important scenarios, reviewed with the person who owns the rule.

```python
import pytest
from shipping import shipping_fee

@pytest.mark.parametrize("total, member, region, fee", [
    (5000, False, "province", 0),     # boundary: exactly 5,000 ships free
    (4999.99, True, "metro", 0),
    (4999.99, True, "province", 80),
    (100, False, "metro", 100),
    (100, False, "province", 180),
])
def test_shipping_fee(total, member, region, fee):
    assert shipping_fee(total, member, region)[0] == fee
```

## Changing rules safely

- Rules change (new tax rate, new promo). Keep the **effective date**: orders before 1 January use the old rate.
- **Log decisions** that matter ("order 1042 got free shipping by R1") so you can answer "why?" later.
- When a rule changes, change the **test first**, see it fail, then change the code.
- Communicate: a rule change is a product change. Write it in the release notes.

## A checklist for your next feature

- [ ] Every policy written as a numbered, testable rule, with boundaries spelled out.
- [ ] A decision table for any rule with 2+ conditions, checked for gaps and conflicts.
- [ ] The rule implemented once, on the server, in a service/policy function that returns the reason.
- [ ] Database constraints for the rules that protect data integrity.
- [ ] Table-driven tests covering every row and boundary.
- [ ] Values that change often in configuration, with effective dates.

Use the **Business rules analyst** mode in Chat to turn a policy you've been given into rules, a decision
table, edge cases, tests and starter code, then check the result with whoever owns the policy.
