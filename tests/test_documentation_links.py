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
