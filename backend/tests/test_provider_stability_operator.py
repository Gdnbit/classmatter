"""Operator opt-in must fail closed without reaching a provider or local instance."""
import importlib.util
from pathlib import Path
from uuid import uuid4

import pytest


def module():
    spec = importlib.util.spec_from_file_location('provider_stability_operator', Path(__file__).resolve().parents[1] / 'provider_stability.py')
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def test_live_is_explicit_and_default_calls_no_provider(capsys):
    assert module().main(['--fixture', str(uuid4())]) == 2
    assert '"requests": 0' in capsys.readouterr().out


@pytest.mark.parametrize('args', [['--rounds', '100'], ['--interval', '0'], ['--fixture', '../normal-instance']])
def test_bounded_options(args):
    with pytest.raises(SystemExit):
        module().parse_args(['--fixture', str(uuid4()), *args])


def test_accidental_credential_argument_is_not_echoed(capsys):
    with pytest.raises(SystemExit):
        module().parse_args(['--key', 'private-canary'])
    assert 'private-canary' not in capsys.readouterr().err
