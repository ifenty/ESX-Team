# Provenance of the kit

This document states where the kit came from. It follows ASD-STE100. See [WRITING_STANDARD.md](WRITING_STANDARD.md).

## Origin

ESX-Team grew out of the repository [three-man-team](https://github.com/russelleNVy/three-man-team) by Russell Aaron (MIT license).
That repository describes a small team of 3 agents: an architect, a builder and a reviewer.
See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for the license text.

## Adaptation from ADX

ESX adapts the contracts and the tested workflow tools of the ADX team into a portable kit.
Each project sets up the kit with its own configuration.
The template contains no import from ADX and no personal path.
The loop state, the configuration and the scientific verification of a project belong to that project.

## Source files of the first adaptation

The table lists the ADX files that the authors read for the first adaptation.
The hash is the SHA-256 of the bytes of each file in the working tree at that time.

| Source | SHA-256 |
|---|---|
| `tools/agent_runtime.py` | `76016008b168692552b978b2b915f576b2d721665b771758142892a0abb090f1` |
| `tools/ralph_stop.py` | `e170e65c3499d319fe8ac8f62b787384fa270e676fe70fc73ecc88765eb72075` |
| `tools/check_ralph_hook.py` | `3f9fe0a8c488e3041a272334aa2cf663e7cdb7bb7dac342aa6968e51958e9dd5` |
| `tools/issue_candidates.py` | `a6c3103cb03348f40e0f5fc41a0e862d62def1a2e73190e3a7e6491da69ccd8f` |
| `tools/workflow_records.py` | `ec1230ef3dbf5d5706467f5429461d906c456ec16c642274bc8ec0d61a6c5caf` |
| `tools/final_verification.py` | `1340efa470912c6e67f2867dca539329484053caf2dda3858ac9663af1da7678` |
| `tools/doc_contract.py` | `89c4d1e95b26cd25cddc3505215efbb5579432baa6b5288166e18f9a18b7b75c` |
| `tools/adx_workflow.py` | `9eecedf2f6abdf8cdf0a1af9e642dcec581a8f09721fc6518722f0ca6b9ec2c6` |
| `tools/loop_gate.py` | `7b135ffcaa0b7fd13a8bf5d1f0f894f5871b418cb5e8266ba7aeb3c19e7db02d` |

The hashes identify the inputs of the adaptation. They do not certify the kit.

## Later changes from field use

Projects that use the kit send back fixes. The history is in [CHANGELOG.md](CHANGELOG.md).
These are the main sources:

- The sparse-runoff project `MITgcm_new_runoff` was the pilot project. Release 1.7.2 moved its framework fixes
  into the kit. The file `self-improvement/reconcile_1.7.2.md` lists each change and the decision for it.
- Release 1.7.3 and later releases came from the same project. They fix the permission mode of the role sessions
  and the frontmatter of the `/esx-loop` command.

## What the provenance does not show

The test results of ADX do not certify this kit or a project that uses it.
The kit has its own tests and its own validation record. See [VALIDATION.md](VALIDATION.md).
