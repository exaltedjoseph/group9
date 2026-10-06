# Version Control with Git

## Git basics
A commit is a snapshot with a message and an author. The working tree is what you edit. The index is what you stage.

```text
git init
git add notes.md
git commit -m "Add Git notes"
git log --oneline
```

## Branching and merging
A branch is a movable pointer to a commit. Work on a branch so main stays stable. Merge brings that work back.

```text
git switch -c branch1
# edit files that nobody else is editing
git commit -am "Add Git materials"
git switch main
git merge --no-ff branch1
```

Editing different files on each branch keeps the merge automatic.

## Collaboration and pull requests
Push the branch and open a pull request. Reviewers read the diff, then the branch is merged into main.
