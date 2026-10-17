"""Evaluation cases with answers that can be checked automatically.

* PROJECT: multiple-choice questions about evals/fixtures/calculator (a tiny project
  with one failing test). Asked with project context only, and again with the real
  test output added, to measure how much "evidence" helps.
* GENERAL: multiple-choice programming knowledge.
* CODE: write a function; graded by running hidden tests against it.
* RETRIEVAL: does project search find the right file for a question about Jarvis itself?
"""

PROJECT = [
    {"id": "avg-empty", "q": "What happens when average([]) is called?",
     "options": ["It returns 0", "It returns None", "It raises ZeroDivisionError", "It returns 0.0"], "answer": "C"},
    {"id": "avg-test", "q": "Does the test test_average_of_empty_list currently pass?",
     "options": ["Yes, it passes", "No, it fails", "It is skipped", "It cannot be collected"], "answer": "B"},
    {"id": "divide-zero", "q": "What does divide(10, 0) do?",
     "options": ["Returns 0", "Raises ZeroDivisionError with the message 'b must not be zero'",
                 "Returns float('inf')", "Returns None"], "answer": "B"},
    {"id": "fail-count", "q": "If you run the project's test suite, how many tests fail?",
     "options": ["0", "1", "2", "3"], "answer": "B"},
    {"id": "fix", "q": "Which change to src/calculator.py makes every existing test pass?",
     "options": ["Make average return 0 when the list is empty", "Make average raise ValueError when the list is empty",
                 "Make average divide by len(numbers) + 1", "Make average return None when the list is empty"],
     "answer": "A"},
    {"id": "add-strings", "q": 'What does add("2", "3") return?',
     "options": ["5", '"23"', "It raises TypeError", '"5"'], "answer": "B"},
    {"id": "divide-float", "q": "What does divide(7, 2) return?",
     "options": ["3", "3.5", "4", "It raises an error"], "answer": "B"},
    {"id": "where-average", "q": "Which file defines the average function?",
     "options": ["tests/test_calculator.py", "src/calculator.py", "README.md", "src/__init__.py"], "answer": "B"},
]

GENERAL = [
    {"id": "py-or", "q": 'In Python, what does the expression [] or "x" evaluate to?',
     "options": ["[]", '"x"', "True", "It raises an error"], "answer": "B"},
    {"id": "http-404", "q": "Which HTTP status code means the resource was not found?",
     "options": ["200", "301", "404", "500"], "answer": "C"},
    {"id": "git-diff", "q": "Which git command shows changes you have not staged yet?",
     "options": ["git log", "git diff", "git push", "git clone"], "answer": "B"},
    {"id": "js-null", "q": "In JavaScript, what is typeof null?",
     "options": ['"null"', '"undefined"', '"object"', '"number"'], "answer": "C"},
    {"id": "py-mutable-default", "q": "In Python, why is `def f(items=[]):` usually a bug?",
     "options": ["Lists can't be default values", "The same list is shared between calls",
                 "It makes f a generator", "It is slower than None"], "answer": "B"},
    {"id": "sql-injection", "q": "What is the standard way to prevent SQL injection?",
     "options": ["Escape quotes by hand", "Use parameterized queries", "Use shorter queries", "Use NoSQL"],
     "answer": "B"},
]

CODE = [
    {"id": "slugify", "fn": "slugify", "prompt": "Write a Python function `slugify(text)` that lowercases the text, replaces every run of "
     "characters that are not letters or digits with a single hyphen, and strips hyphens from both ends.",
     "tests": """
assert slugify("Hello, World!") == "hello-world"
assert slugify("  Many   spaces  ") == "many-spaces"
assert slugify("Already-slug") == "already-slug"
assert slugify("a__b--c") == "a-b-c"
assert slugify("!!!") == ""
"""},
    {"id": "palindrome", "fn": "is_palindrome", "prompt": "Write a Python function `is_palindrome(s)` that returns True if s reads the same "
     "forwards and backwards, ignoring case and any character that is not a letter or digit.",
     "tests": """
assert is_palindrome("A man, a plan, a canal: Panama")
assert is_palindrome("")
assert is_palindrome("No 'x' in Nixon")
assert not is_palindrome("hello")
assert not is_palindrome("ab")
"""},
    {"id": "merge-intervals", "fn": "merge_intervals", "prompt": "Write a Python function `merge_intervals(intervals)` that takes a list of "
     "[start, end] pairs (in any order) and returns a new list of merged, non-overlapping pairs sorted by start. "
     "Pairs that touch, like [1, 3] and [3, 5], must be merged.",
     "tests": """
assert merge_intervals([[1, 3], [2, 6], [8, 10], [15, 18]]) == [[1, 6], [8, 10], [15, 18]]
assert merge_intervals([[5, 7], [1, 3], [3, 4]]) == [[1, 4], [5, 7]]
assert merge_intervals([]) == []
assert merge_intervals([[1, 10], [2, 3]]) == [[1, 10]]
"""},
    {"id": "parse-duration", "fn": "parse_duration", "prompt": "Write a Python function `parse_duration(text)` that converts strings like "
     "'1h30m', '45s', '2h' or '1h2m3s' into a number of seconds (int). Raise ValueError for an empty string or any "
     "other format.",
     "tests": """
assert parse_duration("1h30m") == 5400
assert parse_duration("45s") == 45
assert parse_duration("2h") == 7200
assert parse_duration("1h2m3s") == 3723
for bad in ["", "abc", "10", "5x"]:
    try:
        parse_duration(bad)
    except ValueError:
        pass
    else:
        raise AssertionError(f"accepted {bad!r}")
"""},
    {"id": "word-count", "fn": "top_words", "prompt": "Write a Python function `top_words(text, n)` that returns the n most common words "
     "as a list of (word, count) tuples, most common first; ties are broken alphabetically. Words are runs of letters "
     "and apostrophes, compared case-insensitively and returned in lowercase.",
     "tests": """
assert top_words("the cat and the hat", 2) == [("the", 2), ("and", 1)]
assert top_words("B a b A c", 3) == [("a", 2), ("b", 2), ("c", 1)]
assert top_words("Don't stop. don't!", 1) == [("don't", 2)]
assert top_words("", 3) == []
"""},
    {"id": "fix-average", "fn": "average", "prompt": "Here is a function with a bug:\n\n```python\ndef average(numbers):\n    return "
     "sum(numbers) / len(numbers)\n```\n\nRewrite `average(numbers)` so it returns 0 for an empty list and otherwise "
     "behaves the same.",
     "tests": """
assert average([]) == 0
assert average([2, 4]) == 3
assert average([5]) == 5
"""},
]

RETRIEVAL = [
    {"q": "where do we hide passwords and API keys before sending text to the model", "files": ["jarvis/project/secrets.py"]},
    {"q": "how are phone pairing codes checked and limited", "files": ["jarvis/phone/devices.py"]},
    {"q": "which shell commands need extra approval because they are dangerous", "files": ["jarvis/project/commands.py"]},
    {"q": "restore the original file after an applied change", "files": ["jarvis/project/changes.py"]},
    {"q": "stream the reply tokens from the Ollama server", "files": ["jarvis/llm/ollama.py"]},
    {"q": "create the HTTPS certificate for the phone connection", "files": ["jarvis/phone/certs.py"]},
    {"q": "order tasks so overdue ones come first", "files": ["jarvis/tasks.py"]},
    {"q": "render model answers safely without allowing script injection", "files": ["jarvis/static/markdown.js"]},
    {"q": "what instructions does the model get in requirements mode", "files": ["jarvis/assistant/prompts.py"]},
    {"q": "where is the settings file saved on Windows", "files": ["jarvis/paths.py", "jarvis/config.py"]},
    {"q": "keep working on tasks when the computer cannot be reached from the phone", "files": ["jarvis/static/mobile.js"]},
    {"q": "Android app trusts only the certificate authority of this computer", "files": [
        "android/app/src/local/jarvis/assistant/MainActivity.java", "android/app/res/xml/network_security_config.xml"]},
    {"q": "stop a command that runs too long", "files": ["jarvis/project/commands.py"]},
    {"q": "which files did the model see when answering", "files": ["jarvis/assistant/context.py"]},
]
