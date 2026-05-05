from __future__ import annotations

from unittest.mock import patch

from src.sources.cli.main import main


def test_complete_separator_is_not_treated_as_command_line(capsys):
    with patch("src.sources.cli.retrieve.run_complete", return_value="--env staging") as run_complete:
        main(["complete", "--", "python .tmp-demo/cli_dummy.py ", ""])

    run_complete.assert_called_once()
    assert run_complete.call_args.args[:2] == ("python .tmp-demo/cli_dummy.py ", "")
    assert "--env staging" in capsys.readouterr().out
