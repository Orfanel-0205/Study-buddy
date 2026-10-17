---
title: DevNet Module 3: Software development and design
summary: Exam-focused notes for DevNet Associate Module 3 - the SDLC phases, Waterfall vs Agile vs Lean, Scrum, design patterns (Observer, MVC), version control, coding basics, code review and unit testing, and parsing XML/JSON/YAML in Python.
tags: devnet, cisco, sdlc, waterfall, agile, scrum, lean, design patterns, observer, mvc, git, unittest, tdd, json, xml, yaml, python, venv
order: 6
---

# DevNet Module 3: Software development and design

Module goal: **use software development and design best practices.**

## 3.1 Software development

### The SDLC (Software Development Life Cycle)
The process from an idea to delivered software. It's more than coding: requirements, proofs of concept,
testing and bug fixing are all part of it. **Six phases**, each using the output of the previous one:

| Phase | What happens | Output |
|---|---|---|
| 1. **Requirements & analysis** | explore stakeholders' situation, needs, constraints, infrastructure; decide the problem to solve. Analyse: feasible on budget? schedule risks? how to test? when/how to deliver? | **SRS** (Software Requirement Specification) |
| 2. **Design** | architects and developers design the software from the SRS | **HLD** (High-Level Design) and **LLD** (Low-Level Design) |
| 3. **Implementation** | coding/development; all components are built. **The longest phase** | working code ready to test |
| 4. **Testing** | code installed in a test environment: **functional, integration, performance, security** testing until it passes | high-quality software ready for production |
| 5. **Deployment** | installed in **production**; released to end users | released product |
| 6. **Maintenance** | support customers, fix production bugs, improve, gather new requests | the next iteration/version |

### Methodologies (SDLC models)
The three most popular: **Waterfall, Agile, Lean**. Which to use depends on the **type of project, its length and the team size**.

**Waterfall** (Winston W. Royce; his original model had **seven** phases): each phase is finished completely
before the next starts, like water flowing down steps. Predictable, heavy documentation, but changes late in the
project are expensive. Still used, but being replaced by Agile.

**Agile**: flexible and **customer-focused**. The **Agile Manifesto** (2001, **17 developers**) values:
- **Individuals and interactions** over processes and tools
- **Working software** over comprehensive documentation
- **Customer collaboration** over contract negotiation
- **Responding to change** over following a plan

It has **12 principles**, e.g. customer focus, embrace change, frequent delivery of working software,
collaboration, motivated teams, face-to-face conversation, working software as the measure of progress,
**sustainable pace**, technical excellence, simplicity, self-organizing teams, continuous improvement.

**Agile methods:**
- **Scrum:** small, self-organizing teams; short daily meetings; work in iterative **sprints**.
- **Lean:** eliminate wasted effort; reduce programmers' cognitive load.
- **Extreme Programming (XP):** addresses the quality-of-life issues of software teams (pair programming, TDD, frequent releases).
- **Feature-Driven Development (FDD):** build from an overall model, broken down, planned, designed and built **feature by feature**.

**Scrum vocabulary:**
- **Sprint:** a fixed period, usually **2–4 weeks**; the team takes on the user stories it can finish; at the end the software
  should be **working and deliverable**. Duration is set beforehand and rarely changes.
- **Backlog:** all features of the software, as a **prioritized list**.
- **User story:** what a user/role needs and why, small enough to finish in one sprint:
  **"As a \<user|role\>, I would like to \<action\>, so that \<value|benefit\>."**
- **Scrum team:** cross-functional, self-managed, **no larger than 10 people**.
- **Daily stand-up:** led by the **scrum master**, same time every day, **no more than 15 minutes**: what's
  finished, in progress, about to start.

**Lean software development** (from Lean Manufacturing: minimize waste, maximize customer value). Seven principles
(book *Lean Software Development: An Agile Toolkit*):
1. **Eliminate waste**: the most fundamental. The **seven wastes**: partially done work, extra processes,
   extra features, task switching, waiting, motion, defects.
2. **Amplify learning** (short iterations, faster feedback)
3. **Decide as late as possible** (decide on facts, not speculation)
4. **Deliver as fast as possible**
5. **Empower the team** (people decide in their area of expertise)
6. **Build integrity in** (the software keeps meeting the customer's needs)
7. **Optimize the whole** (experts must consider the effect of their decisions on the whole product)

**Lab: Python development tools.** Check Python (`python --version`), use **pip** and **virtual environments**:
```bash
python -m venv devfun          # create
source devfun/bin/activate     # macOS/Linux     (Windows: devfun\Scripts\activate)
pip install requests
pip freeze > requirements.txt  # share your environment
pip install -r requirements.txt   # recreate it elsewhere
deactivate
```

## 3.2 Software design patterns

**Design patterns** are proven, language-independent solutions to common design problems. The **Gang of Four
(GoF)**, Gamma, Helm, Johnson, Vlissides, 1994, *Design Patterns: Elements of Reusable Object-Oriented Software*:
- Key ideas: **program to an interface, not an implementation**; **favor object composition over class inheritance**.
- **23 patterns** in three categories: **Creational** (how objects are created, e.g. Singleton, Factory),
  **Structural** (how objects are composed, e.g. Adapter, Decorator), **Behavioral** (how objects communicate, e.g. Observer, Strategy).

### Observer (behavioral)
A **subscription** mechanism: observers get notified when the **subject** they watch changes.
- The subject stores a **list of observers** and has methods to **add and remove** them (subscribe/unsubscribe).
- Benefit: observers get **real-time** updates; subscription performs better than **polling**.
- (Webhooks are the Observer pattern over HTTP.)

```python
class Subject:
    def __init__(self):
        self._observers = []
    def attach(self, observer):
        self._observers.append(observer)
    def detach(self, observer):
        self._observers.remove(observer)
    def notify(self, event):
        for observer in self._observers:
            observer.update(event)

class EmailAlert:
    def update(self, event):
        print("email:", event)

interface_status = Subject()
interface_status.attach(EmailAlert())
interface_status.notify("Gi0/1 is down")
```

### MVC (Model-View-Controller)
Separates an application with a user interface into three components:
- **Model:** the data structure, data, logic and rules; gets input from the controller.
- **View:** the visual representation of the data.
- **Controller:** the middleman; takes user input and converts it for the model or view.
Benefit: **each component can be built in parallel** (and changed independently).
Frameworks: Laravel (PHP), Django (calls it MTV), Ruby on Rails, ASP.NET MVC; on the frontend, React is mostly the "V".

## 3.3 Version control systems

See the **Git** guide for commands and team workflow. Exam points:
- Types: **local, centralized, distributed** (Git is distributed: every clone has the full history).
- Git file states: **untracked, modified, staged, committed**; areas: **working directory, staging area, repository**.
- Local vs remote repositories; `clone`, `pull`, `push`; **branches** for parallel work; **merge** and **merge conflicts**;
  GitHub adds **fork** and **pull requests**.
- `git diff` compares changes (working directory vs staging, or between commits).

## 3.4 Coding basics

**Clean code** is easy to read, understand and change:
- Clear, consistent **names**; consistent formatting (PEP 8 in Python).
- Small **functions/methods** that do one thing; **DRY** (Don't Repeat Yourself): reuse instead of copy-paste.
- **Modules** group related code in files you can import; **classes** bundle data (attributes) with behavior (methods).
- Comments explain **why**, not what.

```python
# A module (devices.py) with a function and a class
def normalize_mac(mac: str) -> str:
    """Return a MAC address as lowercase aa:bb:cc:dd:ee:ff."""
    digits = "".join(c for c in mac.lower() if c in "0123456789abcdef")
    return ":".join(digits[i:i + 2] for i in range(0, 12, 2))

class Device:
    def __init__(self, hostname, mac):
        self.hostname = hostname
        self.mac = normalize_mac(mac)

    def label(self):
        return f"{self.hostname} ({self.mac})"
```

## 3.5 Code review and testing

**Code review:** another developer reads your change before it's merged. Benefits: catches bugs early, shares
knowledge, keeps style consistent, improves security. Forms: pull-request review, pair programming, over-the-shoulder.

**Testing levels:**
- **Unit testing:** tests one small piece (a function/class) in isolation. Fast; run constantly.
- **Integration testing:** tests that pieces work **together** (code + database + API).
- (Plus functional/end-to-end, performance and security testing in the Testing phase.)

**TDD (Test-Driven Development):** write a failing test first (**red**), write just enough code to pass
(**green**), then clean up (**refactor**). Repeat.

**Python `unittest`** (in the standard library, used in the DevNet lab):
```python
import unittest
from devices import normalize_mac

class TestNormalizeMac(unittest.TestCase):
    def test_dashes(self):
        self.assertEqual(normalize_mac("AA-BB-CC-DD-EE-FF"), "aa:bb:cc:dd:ee:ff")

    def test_cisco_format(self):
        self.assertEqual(normalize_mac("aabb.ccdd.eeff"), "aa:bb:cc:dd:ee:ff")

if __name__ == "__main__":
    unittest.main()
```
Run with `python -m unittest` (discovers `test*.py`). `pytest` runs these too, and also plain `assert` tests.
Common assertions: `assertEqual`, `assertTrue`, `assertIn`, `assertRaises`, `assertIsNone`.

## 3.6 Understanding data formats

APIs exchange data as **XML, JSON or YAML**. All three represent the same kinds of structures (objects/maps,
lists, strings, numbers, booleans).

| | XML | JSON | YAML |
|---|---|---|---|
| Looks like | tags `<name>R1</name>` | `{"name": "R1"}` | `name: R1` |
| Used by | SOAP, NETCONF, older APIs | **most REST APIs**, RESTCONF | configs (Ansible, Kubernetes, CI) |
| Notes | attributes, namespaces; verbose | strict: double quotes, no comments, no trailing commas | **indentation matters** (spaces, never tabs); supports comments `#` |

```python
import json
data = json.loads('{"hostname": "R1", "interfaces": [{"name": "Gi0/1", "up": true}]}')   # str → dict
print(data["interfaces"][0]["name"])            # Gi0/1
text = json.dumps(data, indent=2)                # dict → str  (json.load/json.dump for files)

import xml.etree.ElementTree as ET              # standard library
root = ET.fromstring("<device><hostname>R1</hostname><up>true</up></device>")
print(root.find("hostname").text)               # R1
# (the DevNet labs also use: import xmltodict; xmltodict.parse(xml_text) → dict)

import yaml                                     # pip install pyyaml
config = yaml.safe_load("hostname: R1\ninterfaces:\n  - name: Gi0/1\n    up: true\n")
print(config["interfaces"][0]["up"])            # True
print(yaml.dump(config))                        # dict → YAML text
```
Use `yaml.safe_load` (not `yaml.load`) so a YAML file can't create arbitrary Python objects.

## Exam traps

- SDLC has **6 phases**; Royce's original waterfall had **7**.
- The **implementation** phase is the **longest**.
- SRS comes out of **requirements**; HLD/LLD out of **design**.
- Agile Manifesto: **4 values, 12 principles, 17 authors, 2001**.
- Sprints: **2–4 weeks**; stand-ups **≤ 15 min**; Scrum team **≤ 10**.
- Lean's most fundamental principle: **eliminate waste**; know the **7 wastes**.
- GoF: **23 patterns, 3 categories**; Observer is **behavioral**.
- **Unit** = one piece in isolation; **integration** = pieces together.
- JSON keys need **double quotes**; YAML forbids **tabs** for indentation.
