# Co-existence gate verdict (expert round-table, 2026-10-23)

Options on the table when this task hit the cross-repo release deadlock:

1. temporarily shrink the `ffmpeg-over-ip` co-existence matrix to two plugins,
   ship, then restore the three-plugin matrix in a follow-up commit;
2. move the co-existence job out of `ci.yml` permanently;
2+. same split, and `release.yml` also requires the co-existence run to be green;
3. pull peers from sibling CI artifacts;
4. build the missing sibling inside the job, from its pinned commit, with the
   same digest-pinned SDK image;
5. make the contract repo the release unit (bundle all three, then release).

## Converged

- Option 3 is dead. Cross-repo `download-artifact` needs a `repo`-scoped token;
  `github.token` cannot read another repository's artifacts.
- Option 2 and 2+ are dead. The co-existence job downloads *released* peers
  wherever the job file lives. Moving it changes which workflow is authoritative,
  not the dependency that produces the deadlock. Conway's framing: the assertion
  measures a combination, the combination belongs to the contract repo, so
  moving the file is not returning the assertion to its object.
- Conway's own fix (contract-repo mock fixtures) is dead by its own admission. A
  fixture that satisfies `abi_id` / `lock_digest` / `platform` / `plugin_sha256`
  plus the shared module-identity comparison has to be built with the same SDK
  image, the same lock and the same plugin source - that is option 4 with the
  build relocated, and the contract repo output is again either "already
  released" or "from source". The deadlock mirrors.
- All three frameworks ranked option 4 first, and two of them independently put
  the same precondition in front of it: the `plugin_sha256` equality assertion
  rests on "same inputs imply same bytes", which has never been observed. Deming
  called it the single observation that would overturn his ranking. Conway asked
  for the reproducibility experiment on both architectures before claiming option
  4 is strictly stronger than downloading.
- Perrow's "order luck" verdict. In this batch the coverage came from
  indexed-media happening to release second. Deming's ruling: that can be
  written as a falsifiable constraint (audit whether the last releaser of each
  batch ran all three), but with no required status checks a written ordering is
  advice, not a control. Option 4 makes ordering irrelevant, which retires the
  fence.

## Remaining disagreement, settled by facts rather than another round

Deming ranks 1 above 5 because `release.yml` only accepts a run of its own
repository, so a contract-repo bundle cannot enter the gate without editing the
gate. Conway and Perrow rank 5 above 1 because the steady state should be the
contract repo as release unit, with the expected peer set declared in
`compatibility.json`. Both are right about different things: 5 is the correct
steady state, 1 is the correct migration move. Adopting 5 changes release gate
semantics, which is not approved for this batch.

## Chosen implementation for this batch

> Status note (2026-10-23): this section is a decision, written in the present
> tense; the FF workflow still contains the two peer downloads and no sibling
> source build (`rulego-ffmpeg-over-ip/.github/workflows/ci.yml:196-197`), and
> `implement.md` step 2.4 is unchecked. Two further facts belong with it:
> building `indexed-media` from its pinned commit registers `indexedMedia`, while
> the smoke step at `ci.yml:294` asks for `indexedVod`, so the step cannot go
> green until that string is migrated too. `indexedVod` is the pre-rename name of
> the same component (`rulego-indexed-media/README.md:168-173`), so "no assertion
> is removed" holds only literally - nothing is deleted, but one assertion's
> operand changes identity, and its peer artifact changes with it. See
> `coexistence-ownership-first-principles.md` for the residue inventory.

`ffmpeg-over-ip` co-existence peers become three sources instead of two
downloads:

- `resource-origin v0.2.0` - downloaded from the release, `sha256sum --check` and
  sidecar comparison, unchanged;
- the same `resource-origin v0.2.0` also rebuilt from its pinned commit in the
  digest-pinned SDK image, and its `.so.sha256` compared with the published
  value. That is the reproducibility experiment both reviewers demanded, paid for
  with one extra `docker run` in a job that already builds twice, and it checks
  the shipped bytes rather than a candidate;
- `indexed-media` - built from its pinned commit, because no new-ABI release of
  it exists yet. This is the one residual that cannot be removed: the artifact
  does not exist yet. The residual is recorded in the release notes instead of
  being papered over.

No assertion is removed, `release.yml` is not touched, no new secret is needed.
Cross-repository read access already works: the same job uses
`gh release download --repo ...` today with `github.token` against public
repositories, and checking out a sibling commit needs nothing more.

## Kahneman's closing objection (still open, deliberately)

He also ranked 4 first, then named two things the other three did not:

- Under option 4 the "restore commit never happened" premortem goes to zero -
  that commit no longer exists - but "a green light nobody looks at" survives
  unchanged unless a `plugin_sha256` mismatch can actually block a release.
  Renaming the step "built from source" does not make anyone read it.
- He caught himself cheating a second time, on the same axis: he read option 4's
  alarm at its best ("a mismatch will be seen") and option 2+'s at its worst
  ("a green light nobody watches"). The double standard lives in the reader, not
  in the options. He also insists the cost of the two-architecture reproducibility
  run belongs in option 4's price, not outside it.
- His warning about consensus: three frameworks pushing 4 while sharing one
  unverified premise is itself a signal. That premise is exactly the thing the
  added build step measures, which is why the extra `docker run` is not optional.

The surviving requirement from this objection: the reproducibility comparison has
to fail the job, not annotate it. A mismatch must exit non-zero inside `ci.yml`,
so it withholds the `CI:success` run that `release.yml` demands. Recording it in
the release notes would be the green light nobody reads.

Revisit 5 when the three plugins need to move on independent schedules; that
change should arrive together with branch protection and required status checks,
which none of the three plugin repositories have today.

## Second round (2026-10-24), after the first-principles correction

`coexistence-ownership-first-principles.md` corrected the deadlock premise
(the cross-repo "cycle" is CI placement, not source dependency) and left the
location of the fleet-level assertion open. The table was reconvened with
that fact on it. Deming, Kahneman and Conway answered; Perrow was not present.

Converged:

- Deming and Conway both moved their top pick to a new shape, 2'': the
  co-existence job moves into the contract repo as the integration owner;
  member gates keep only member evidence. Deming: composition evidence is
  batch-shaped and had always been "wearing other repos' output as its own
  test". Conway: integration assertions belong to the integration owner; no
  single member repo ever had qualification to assert the three-piece
  combination.
- Both demoted the currently recorded three-source implementation to the
  bottom of their rankings, for a reason round 1 did not contain: pinning an
  unpublished sibling's `main` SHA into `ci.yml` is "pre-paying your release
  for you" - social structure leaking into a pipeline constant, rots on PR
  rebase (Conway), and it grows the gate on another repo's drift point, held
  up by hand (Deming).
- All three agree the steady state is the contract repo owning the set; the
  disagreement is only over this batch's carrier. The table had never named which
  repository "the contract repo" is: the candidate is
  `killbus/rulego-server-docker` - it owns `plugin-abi.lock`, the five-field
  contract every member embeds, and it publishes the `-plugin` runtime image
  the co-existence evidence must load in. It has no `compatibility.json` of its
  own and its release chain is image-only (`plugin-abi-publish.yml` /
  `publish.yml`, verified 2026-10-24); it has never carried a plugin release.

Not converged:

- Kahneman holds 4 first (4 > 5 > 1 > 2+ > 2), having admitted the double
  standard: he priced 4's alarm at its best day and 2's at its worst. His
  conditions for 4: the sha assertion must actually run, and the two-arch
  reproducibility cost belongs in 4's price. His flip condition: if the build
  is not reproducible (Go version or CGO off by one byte), 4 falls below 1.
- Deming: 2'' > 5 > 1 > three-source. Conway: 2'' > 5 > three-source > 1.
  Conway's minimal step for 2'': contract repo declares the three-source
  coordinates, the co-existence job moves in, the three member repos drop
  their peer downloads and release individually green; the fixture is the
  three artifacts loading in one process inside the contract repo.
- The unverified premise now sits on both sides: 4 stands on "same inputs
  imply same bytes"; 2'' stands on "the contract repo can enter the release
  chain" - `release.yml` accepts only a run of its own repository, option 5's
  old wall. Deming's test for 2'': its evidence is re-verifiable by reading
  back the three releases, so try 2'' first.

Decision state: two of the three R2 respondents rank 2'' first; the surviving
objection to 2'' is factual (gate reachability), not framing. The recorded
three-source implementation (option 4) remains this batch's plan until an
explicit decision changes it; changing it is a release-gate change and needs
approval.