import subprocess
from unittest.mock import Mock

import pytest

from scripts.steering_fidelity_cleanup_a2 import retrieval_run


@pytest.mark.parametrize("command,timeout,expected", [
    (["ssh", "owned", "manifest"], 60, 300),
    (["rsync", "-rt", "owned:out/", "local/"], 300, 900),
    (["ssh", "owned", "different"], 60, 60),
    (["python", "fixture"], 60, 60),
])
def test_only_retrieval_timeouts_change(command, timeout, expected):
    run = Mock(return_value="done")
    assert retrieval_run(command, manifest_command="manifest", run=run,
                         timeout=timeout, input=b"synthetic") == "done"
    run.assert_called_once_with(command, timeout=expected, input=b"synthetic")


def test_wrong_inherited_timeout_fails_closed():
    with pytest.raises(ValueError):
        retrieval_run(["ssh", "owned", "manifest"], manifest_command="manifest", timeout=61)


def test_timeout_diagnostic_does_not_print_command(capsys):
    command = ["ssh", "private-host", "manifest"]
    run = Mock(side_effect=subprocess.TimeoutExpired(command, 300))
    with pytest.raises(subprocess.TimeoutExpired):
        retrieval_run(command, manifest_command="manifest", run=run, timeout=60)
    assert "private-host" not in capsys.readouterr().out
