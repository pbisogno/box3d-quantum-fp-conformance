# C17 fixed-point compatibility laboratory

Experimental, laboratory-authored C fixed-point kernels checked against frozen
observations of the public APIs of Quantum 3.1.0.2189. The four C files in `src/`
are byte-identical to the sources inside the authenticated test payload. The C
implementation does not call the Quantum assembly.

The first corpus contains 83,290 distinct requests covering 34 operations,
including exact raw results and expected exception statuses. The original
payload manifest is pinned to SHA-256
`8d7708a1b7aeb04d2c91955d95392b77a8d7dd86762b7a34a8d3ed08efaf59ab`.
The [first Linux x64 execution](https://github.com/pbisogno/box3d-quantum-fp-conformance/actions/runs/38975982905)
passed all four profiles: 83,290 cases per profile, 333,160 comparisons and zero
mismatches. All four complete output files have the same SHA-256. The full
outputs were authenticated, decrypted and independently rechecked with the frozen
Python comparator. See the [aggregate result](results/linux-x64-38975982905.json).
GCC 13.3 emitted existing misleading-indentation warnings; Clang 18.1.3 emitted
no compiler diagnostics. Runtime stdout/stderr were empty in all four profiles,
including UBSan. The tested C sources were not changed after the run.

The [native Linux ARM64 execution](https://github.com/pbisogno/box3d-quantum-fp-conformance/actions/runs/38978967819)
passed the same four profiles and 333,160 comparisons with zero mismatches.
The authenticated complete ARM64 outputs were rechecked with the frozen Python
comparator and compared byte for byte against the complete x64 outputs. All
eight response files are identical, with SHA-256
`5269ffdd06240e5cbaa73fa1d9a3898ed9546c3dc3cc5b7b495cf810ddc4f037`.
The corpus still contains 83,290 unique requests; repeated profiles and
architectures do not add unique cases. See the
[ARM64 and architecture comparison result](results/linux-arm64-38978967819.json).

The [first scalar engine physics run](https://github.com/pbisogno/box3d-quantum-fp-conformance/actions/runs/38982104117)
compiled and completed all eight native profiles. All eight complete observed
state traces and metrics files are byte-identical. Physical acceptance remains
failed: four of six scenarios passed and two failed in every profile, under
criteria frozen before execution. Repeated profiles do not add unique scenarios.
A [separate CMake library build](https://github.com/pbisogno/box3d-quantum-fp-conformance/actions/runs/38982521342)
subsequently passed on both architectures after a packaging-only correction;
it did not rerun or approve the failed physics criteria. See the
[sanitized aggregate result](results/physics-smoke-x64-arm64-v1.json).
New engine sources, fixtures and detailed diagnostics remain encrypted.

The manual workflows use standard GitHub-hosted `ubuntu-24.04` Linux x64 and
`ubuntu-24.04-arm` Linux ARM64 runners and preinstalled Node, Python, GCC and
Clang. The ARM64 gate checks the native host, compiler target and ELF64 AArch64
machine before executing C, without emulation. Profiles are GCC O0,
GCC O2, Clang O2 and GCC UBSan, all in strict C17 with pedantic errors.
The job has a 12-minute limit. It installs no software, uses no cache and uploads
no Actions artifacts. Standard runners in public repositories are
[free of runner-minute charges](https://docs.github.com/en/billing/concepts/product-billing/github-actions).

The original SDK lookup-table files and the frozen test data remain in an
AES-256-GCM envelope. They are restored only into temporary storage by an
authorized manual run using a dedicated Actions Secret. This follows GitHub's
[large-secret mechanism](https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/use-secrets#storing-large-secrets).
Every payload file and the public C sources are checked before compilation.
Public logs expose counts, status and hashes; full diagnostics are encrypted.
The key is absent from the repository and from the native subprocess environment.

The kernel experiment concerns its selected scalar operations and corpus; the
engine experiment concerns six initial scalar physics scenarios. Equal observed
state traces do not establish equality of every hidden state field or a complete
world checksum. These results do not establish exhaustive compatibility, general
physical accuracy, production readiness, snapshot/rollback support, CCD,
concurrency or behavior beyond the tested Linux x64 and ARM64 configurations.
CI step durations are not physics performance benchmarks.

Existing provenance and SPDX notices are retained. This repository does not
grant a redistribution license to the third-party SDK assets or assign a new
blanket license to all files. Licensed fixtures are not made available in
plaintext by this repository.
