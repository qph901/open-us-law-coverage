from __future__ import annotations

from open_us_law_coverage.cli import main, package_version


def test_cli_without_a_subcommand_prints_useful_help(capsys):
    assert main([]) == 0
    output = capsys.readouterr().out
    assert "identity-manifest" in output
    assert "ca-probe" in output
    assert "Hello" not in output


def test_package_version_is_available():
    assert package_version() != "0+unknown"
