from __future__ import annotations

import json

from shinkai_api.eval.cases import load_eval_cases, main, run_eval_cases


def test_eval_cases_cover_golden_and_adversarial_paths() -> None:
    result = run_eval_cases()

    assert result.passed
    assert {case.case_id for case in load_eval_cases()} == {
        "golden_source_backed",
        "adversarial_source_gap",
        "adversarial_refute",
        "adversarial_bad_invest_dossier",
    }
    assert all(not case_result.failures for case_result in result.results)


def test_eval_case_cli_outputs_json(capsys) -> None:
    exit_code = main()

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert output["passed"] is True
    assert output["results"][0]["case_id"] == "golden_source_backed"
