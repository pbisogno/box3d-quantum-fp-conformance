# C17 fixed-point compatibility laboratory

Experimental, laboratory-authored C fixed-point kernels checked against frozen
observations of the public APIs of Quantum 3.1.0.2189. The four C files in `src/`
are byte-identical to the sources inside the authenticated test payload. The C
implementation does not call the Quantum assembly.

The first corpus contains 83,290 distinct requests covering 34 operations,
including exact raw results and expected exception statuses. The original
payload manifest is pinned to SHA-256
`8d7708a1b7aeb04d2c91955d95392b77a8d7dd86762b7a34a8d3ed08efaf59ab`.
Native execution results have not yet been established for this initial revision.

The manual workflow uses the standard GitHub-hosted `ubuntu-24.04` Linux x64
runner and preinstalled Node, Python, GCC and Clang. Profiles are GCC O0,
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

These experiments concern the selected scalar C kernels and corpus. They do not
establish exhaustive compatibility, physical accuracy, a complete Box3D FP port,
snapshot/rollback support or behavior on another CPU architecture.

Existing provenance and SPDX notices are retained. This repository does not
grant a redistribution license to the third-party SDK assets or assign a new
blanket license to all files. Licensed fixtures are not made available in
plaintext by this repository.
