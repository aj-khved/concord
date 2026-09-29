from concord import main


def test_main_runs(capsys):
    main()
    assert "concord" in capsys.readouterr().out.lower()
