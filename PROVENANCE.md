# Framework provenance

ESX adapts the ADX team contracts and tested workflow mechanisms into a portable
project-configured kit. The deployed template contains no ADX imports or personal
paths. Project-owned loop state, configuration and scientific verification are
implemented locally in the deployment.

Source files inspected for this adaptation (SHA-256 of working-tree bytes):

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

The source digests identify adaptation inputs. ESX has its own regression suite
and qualification record; the originating project’s test result does not certify
this kit or any receiving project. See [VALIDATION.md](VALIDATION.md).
