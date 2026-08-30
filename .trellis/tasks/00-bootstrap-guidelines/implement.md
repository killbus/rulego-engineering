# Implementation plan

1. Replace generic backend/frontend spec indexes with explicit
   documentation-only boundaries and remove their unused placeholder guides.
2. Add the RuleGo engineering entry guide and five single-owner specialized
   guides under `.trellis/spec/guides/`.
3. Update the guides index, append the project-local AGENTS routing block, and
   add the root README without duplicating normative content.
4. Add root ignore rules for repository-local temporary/Python cache files, a
   dependency-free document validator, and a minimal GitHub Actions CI workflow.
5. Run the validator, search for credentials/placeholders/volatile copied ABI
   values, and verify all links and repository boundaries.
6. Dispatch an independent Trellis check agent under an explicit goal and fix
   only mechanical defects within the approved scope.
7. Run the full validator again, update the reusable spec if the check uncovers
   a missing rule, and create one coherent bootstrap commit.
8. After repository visibility is selected, create/push
   `killbus/rulego-engineering`, monitor CI, and read the remote commit/check
   state back.

## Validation commands

```bash
python3 scripts/validate.py
rg -n 'TO''DO' README.md AGENTS.md .trellis/spec scripts .github
rg -n 'github_''pat_|gh''p_' README.md AGENTS.md .trellis/spec .trellis/tasks scripts .github
git diff --check -- .gitignore .github AGENTS.md README.md scripts .trellis/spec .trellis/tasks/00-bootstrap-guidelines
```

After Git initialization:

```bash
git status --short
git diff --cached --check -- .gitignore .github AGENTS.md README.md scripts .trellis/spec .trellis/tasks/00-bootstrap-guidelines
```

## Change boundary

Expected changes are limited to root entry documentation and ignore rules,
RuleGo Trellis guides and layer indexes, the generated irrelevant placeholder
guides, one validator, one CI workflow, and this Bootstrap task's records. No
sibling RuleGo repository or deployed service is modified.
