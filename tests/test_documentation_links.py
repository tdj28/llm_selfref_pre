from scripts.check_documentation_links import broken_references


def test_local_links_are_relative_to_document(tmp_path):
    directory = tmp_path / "docs"
    directory.mkdir()
    (tmp_path / "target.md").write_text("content")
    document = directory / "README.md"
    document.write_text("[ok](../target.md#heading) [bad](missing.md)")
    assert broken_references(tmp_path, document) == ["missing.md"]


def test_external_and_heading_links_need_no_network(tmp_path):
    document = tmp_path / "README.md"
    document.write_text("[web](https://example.com/missing) [heading](#heading)")
    assert broken_references(tmp_path, document) == []


def test_explicit_repo_paths_checked_at_root(tmp_path):
    (tmp_path / "paper").mkdir()
    (tmp_path / "paper/main.tex").write_text("content")
    document = tmp_path / "README.md"
    document.write_text("`paper/main.tex` and `paper/missing.tex`")
    assert broken_references(tmp_path, document) == ["paper/missing.tex"]


def test_documented_pdf_output_needs_build_sources_not_a_built_pdf(tmp_path):
    (tmp_path / "paper").mkdir()
    document = tmp_path / "README.md"
    document.write_text("Build output: `paper/main.pdf`")
    assert broken_references(tmp_path, document) == ["paper/main.pdf"]
    (tmp_path / "paper/main.tex").write_text("content")
    assert broken_references(tmp_path, document) == ["paper/main.pdf"]
    (tmp_path / "Makefile").write_text("paper:\n\tlatexmk paper/main.tex\n")
    assert broken_references(tmp_path, document) == []


def test_generated_path_exception_does_not_hide_broken_links_or_other_outputs(tmp_path):
    (tmp_path / "paper").mkdir()
    (tmp_path / "paper/main.tex").write_text("content")
    (tmp_path / "Makefile").write_text("paper:\n\tlatexmk paper/main.tex\n")
    document = tmp_path / "README.md"
    document.write_text("[PDF](paper/main.pdf) and `paper/other.pdf`")
    assert broken_references(tmp_path, document) == ["paper/main.pdf", "paper/other.pdf"]
