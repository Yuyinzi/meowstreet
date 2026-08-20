import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _load_bootstrap_script():
    path = ROOT / "scripts" / "bootstrap_local_data.py"
    spec = importlib.util.spec_from_file_location("bootstrap_local_data", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


bootstrap_script = _load_bootstrap_script()


def test_main_bootstraps_default_reference_into_requested_database(tmp_path, capsys):
    db_path = tmp_path / "market_data.sqlite"

    assert bootstrap_script.main(["--db-path", str(db_path)]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["db_path"] == str(db_path)
    assert payload["industries"] == 69
    assert payload["aliases"] == 151
    assert payload["market_observations"] == 0


def test_main_reports_validation_error_without_partial_database(tmp_path, capsys):
    reference_path = tmp_path / "invalid.csv"
    reference_path.write_text("bad,header\n", encoding="utf-8")
    db_path = tmp_path / "market_data.sqlite"

    assert (
        bootstrap_script.main(
            [
                "--db-path",
                str(db_path),
                "--reference-path",
                str(reference_path),
            ]
        )
        == 1
    )

    assert "gics reference csv headers are invalid" in capsys.readouterr().err
    assert not db_path.exists()
