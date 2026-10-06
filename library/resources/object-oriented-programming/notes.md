# Object-Oriented Programming

## Classes and objects
A class is a blueprint. An object is one instance of that class. `__init__` sets up the instance. `self` is the instance the method is running on.

```python
class Resource:
    def __init__(self, title, module):
        self.title = title
        self.module = module

    def label(self):
        return f"{self.title} ({self.module})"
```

## Inheritance and polymorphism
A subclass reuses and extends a parent. Overriding a method lets each class behave differently through the same call.

```python
class Notes(Resource):
    def label(self):
        return "Notes: " + super().label()
```

## Design principles
- Encapsulation: keep details on the object and expose a small set of methods.
- One job: a class should have a single reason to change.
- Prefer composition when a type *has* another type, and inheritance when it *is* that type.
