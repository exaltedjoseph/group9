# Study Library

A desktop **Resource Database Study System** for the internship program (Group 9 project proposal).
Facilitators upload notes, slides and exercises, tag them by module and log every classwork session.
Interns browse by module, search by keyword and download what they need. Gemini only *suggests*
modules, topics and keywords, and the facilitator always confirms them. Every change is committed to Git.
A **Home** dashboard summarizes the library, and the Gemini-powered **Assistant** explains topics and
resources using what's in the library.

The interface follows Apple's design language: a translucent sidebar, unified toolbar, SF-style typography
and symbols, sheets, and System Settings-style forms. The window uses the native Windows 11 minimize,
maximize and close buttons, including Snap Layouts. Light and dark appearance are both supported.

## Quick start

```powershell
pip install -r requirements.txt
python main.py        # or: python run.py
```

On first launch, choose **Facilitator** or **Intern**. You can switch at any time from the bottom of the
sidebar or in Settings.

### Gemini API key
AI tagging and the Assistant need a Gemini API key ([get one free](https://aistudio.google.com/apikey)). Use any one of these:

1. Paste it in **Settings > Gemini AI > API Key**, or paste it straight into the Add Resource sheet the
   first time you click *Suggest Tags with AI*. It is saved only on this computer, in
   `%LOCALAPPDATA%\StudyLibrary\settings.db`.
2. Put it in a `.env` file next to `main.py` (see `.env.example`): `GEMINI_API_KEY=...`
3. Set the `GEMINI_API_KEY` environment variable.

The environment variable takes priority, then `.env`, then the key saved in Settings.

## Where everything is stored (local only)

```
library/                    the shared, Git-versioned library
  syllabus.json             modules and topics
  data/resources.json       resource metadata (title, module, topic, keywords, uploader, date, ...)
  data/classwork.json       classwork log
  resources/<module>/...    uploaded files
  classwork/<module>/...    classwork attachments
  .index/index.db           local SQLite index for fast browsing and full-text search (git-ignored)
```

SQLite is the working database. After every change it is mirrored to the JSON files, which Git can diff
and merge. When the JSON changes (for example after `git pull`, or in a fresh clone), the SQLite index
rebuilds itself automatically. Your personal settings and API key never go into the library folder.
To keep settings somewhere other than `%LOCALAPPDATA%\StudyLibrary` (for a portable copy, say), set the
`STUDY_LIBRARY_DATA` environment variable to a folder path.

## Git
If the library folder isn't already inside a Git repository, the app creates one with an initial commit.
Each upload, edit, deletion, syllabus change or classwork entry becomes a commit
(for example `Add resource: Loops (Python Fundamentals)`). Changes made within a fraction of a second of
each other share one commit, whose message lists every change. Facilitators can see the **History** in the
sidebar. To share the library with the next cohort, add a remote in **Settings > Library & Git** and use
**Push Now**, or turn on *Push after each change*. **Pull Latest** brings in other facilitators' changes.

## Keyboard shortcuts
| Shortcut | Action |
| --- | --- |
| Ctrl+F | Search |
| Ctrl+N | Add resource (facilitator) |
| Ctrl+L | Log classwork (facilitator) |
| Ctrl+1 / 2 / 3 / 4 | Home / All Resources / Recently Added / Classwork |
| Ctrl+K | Assistant |
| Ctrl+, | Settings |
| F5 | Reload the library from disk |

## Fonts
Apple's SF Pro fonts can't be redistributed, so the app uses them automatically if they're installed
(or dropped into `assets/fonts/`). Otherwise it falls back to Segoe UI Variable.

## Project layout
```
main.py / run.py         entry points
app/constants.py         app-wide constants (models, resource kinds, colors)
app/theme.py             Apple system colors, typography, global stylesheet
app/icons.py             SF Symbols-style vector icons, document icons, app icon
app/effects.py           Windows DWM helpers (backdrop blur, frameless window)
app/core/                models, library (SQLite + JSON + files), settings, git, text extraction, Gemini
app/ui/                  window, sidebar, views, inspector, sheets, shared controls
tests/                   pytest unit tests (AI calls are mocked)
```

## Tests
```powershell
python -m pytest -q
```
