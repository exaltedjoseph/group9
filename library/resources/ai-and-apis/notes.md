# AI and APIs

## Working with APIs
An API is a contract over HTTP. You send a method, a URL, headers, and sometimes a JSON body. You read the status code and the response body. Keep the API key out of the repository and pass it in from the environment.

```python
import os
key = os.environ["GEMINI_API_KEY"]
```

## Prompt design
Say the task, the input, and the shape of the answer. Ask for only what you need. For tagging, ask for a module id that already exists instead of inviting the model to invent one.

## Gemini API
The app sends library text to Gemini and asks for suggested tags. A person confirms the suggestion before it is saved. Treat the model output as untrusted text: parse it, check the ids against the syllabus, and discard anything that does not match.
