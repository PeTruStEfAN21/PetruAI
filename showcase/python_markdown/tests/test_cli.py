from mdconv.cli import main


def test_writes_output_file(tmp_path):
    src = tmp_path / "in.md"
    src.write_text("# Hi\n\ntext", encoding="utf-8")
    out = tmp_path / "out" / "page.html"
    assert main([str(src), "-o", str(out)]) == 0
    assert out.read_text(encoding="utf-8") == "<h1>Hi</h1>\n<p>text</p>\n"


def test_prints_to_stdout(tmp_path, capsys):
    src = tmp_path / "in.md"
    src.write_text("*x*", encoding="utf-8")
    assert main([str(src)]) == 0
    assert capsys.readouterr().out == "<p><em>x</em></p>\n"


def test_full_page_option(tmp_path, capsys):
    src = tmp_path / "in.md"
    src.write_text("# T", encoding="utf-8")
    assert main([str(src), "--title", "My <page>"]) == 0
    assert capsys.readouterr().out == (
        "<!DOCTYPE html>\n<html>\n<head>\n<meta charset=\"utf-8\">\n<title>My &lt;page&gt;</title>\n"
        "</head>\n<body>\n<h1>T</h1>\n</body>\n</html>\n"
    )


def test_missing_input(tmp_path, capsys):
    assert main([str(tmp_path / "nope.md")]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "nope.md" in captured.err
