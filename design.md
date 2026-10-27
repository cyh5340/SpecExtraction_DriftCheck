This project will take an entire codebase as input then verify if the codebase matches the original requirements based on:
1, existing documentations (considering timestamp)
2, existing comments (considering timestamp)
3, git history of which function was modified.

Cases:
When a function was created without any documentation, its first appearance structure should be the baselinke of its original functionality.
When a function was created while the existing documentation predates it and their functionality has a mismatch, then the code is considered implemented wrong.
When a function was modified (based on git logs) while its related documentation was not modified, and the modified functionality no longer matches the original documentation (of desired input/output/functionality), this is considered a drift.

Spec Extraction:
documentation first, if no documentation exist, look for the first appearance of the function for its related pull request, jira tickets, first completed version merged to main branch.

Decisions made during implementation (details in tasks.md, usage in README.md):
- Any codebase: functions are parsed with tree-sitter for any language it supports (Python with the stdlib ast parser).
- "First appearance" means the first version merged to main. Work-in-progress commits on feature branches don't count.
- A function whose first merged version doesn't match docs that existed at the time is flagged as drift (DRIFT, reason first_version_mismatch), rather than a separate "implemented wrong" verdict.
- Finding and linking specs is deterministic (exact name matches). One model call, TypeSafe Jev answering yes/no, decides whether code still behaves as its spec describes.
- The current code is compared against the current docs, so docs updated with the code become the new spec.
- Pull request and Jira text are not used yet (planned).