# Software Testing

## Unit testing
A unit test calls one function with a known input and checks the result. Name the test after the behavior.

```python
def test_average_of_two_scores():
    assert average([80, 100]) == 90
```

Run the file with `pytest`. A failed assertion is the test doing its job.

## Test-driven development
1. Write a test that fails because the behavior does not exist yet.
2. Write the smallest code that makes it pass.
3. Clean up the code without changing what the test checks.

## Debugging
Reproduce the bug with one input. Read the traceback from the last frame you own. Print or inspect the value just before the failure. Fix the cause, then keep the failing case as a test.
