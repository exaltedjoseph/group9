# Python Fundamentals

## Variables and data types
A variable is a name bound to an object. Python decides the type from the value.

```python
course = "Python Fundamentals"
weeks = 8
passing = True
score = 91.5
```

Common types: `int`, `float`, `str`, `bool`, and `None`. Check a type with `type(value)` and convert with `int()`, `float()`, and `str()`.

## Control flow
`if`, `elif`, and `else` choose a path. `for` walks a sequence. `while` repeats until a condition fails.

```python
for n in range(1, 6):
    if n % 2 == 0:
        print(n, "even")
```

## Functions
Define reusable behavior with `def`. Parameters can have defaults. Return a value with `return`.

```python
def grade(score, pass_mark=50):
    return "pass" if score >= pass_mark else "fail"
```

## Data structures
- `list` keeps an ordered, changeable sequence
- `tuple` keeps an ordered sequence that should not change
- `dict` maps keys to values
- `set` keeps unique items

```python
intern = {"name": "Intern", "modules": ["python", "git"]}
intern["modules"].append("sql")
```

## Files and exceptions
Open files with a `with` block so they close even when something fails. Catch expected problems with `try` and `except`.

```python
try:
    with open("notes.txt", encoding="utf-8") as handle:
        text = handle.read()
except FileNotFoundError:
    text = ""
```
