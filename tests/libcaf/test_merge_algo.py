import pytest
from pathlib import Path

from libcaf import Tree, TreeRecord, TreeRecordType
from libcaf.merge_algo import merge_trees, MergeConflict


@pytest.fixture
def mock_repo(monkeypatch: pytest.MonkeyPatch) -> dict[str, Tree]:
    """
    Mocks the disk I/O 'load_tree' function to return Tree objects from an in-memory dictionary.
    This allows pure algorithmic testing without touching the file system.
    """
    fake_db: dict[str, Tree] = {}

    def mock_load_tree(objects_dir: Path, tree_hash: str) -> Tree:
        if tree_hash not in fake_db:
            raise ValueError(f"Tree hash {tree_hash} not found in mock DB")
        return fake_db[tree_hash]

    monkeypatch.setattr("libcaf.merge_algo.load_tree", mock_load_tree)
    return fake_db



def test_identical_roots(mock_repo: dict[str, Tree]) -> None:
    mock_repo["base_root"] = Tree({"file.txt": TreeRecord(TreeRecordType.BLOB, "h1", "file.txt")})
    result = merge_trees(Path("fake"), "base_root", "base_root", "base_root")
    assert result == {"file.txt": ("h1", TreeRecordType.BLOB)}


def test_fast_forward_ours_root(mock_repo: dict[str, Tree]) -> None:
    mock_repo["base_root"] = Tree({"file.txt": TreeRecord(TreeRecordType.BLOB, "h1", "file.txt")})
    mock_repo["ours_root"] = Tree({"file.txt": TreeRecord(TreeRecordType.BLOB, "h2", "file.txt")})
    result = merge_trees(Path("fake"), "base_root", "ours_root", "base_root")
    
    assert result == {"file.txt": ("h2", TreeRecordType.BLOB)}


def test_fast_forward_theirs_root(mock_repo: dict[str, Tree]) -> None:
    mock_repo["base_root"] = Tree({"file.txt": TreeRecord(TreeRecordType.BLOB, "h1", "file.txt")})
    mock_repo["theirs_root"] = Tree({"file.txt": TreeRecord(TreeRecordType.BLOB, "h2", "file.txt")})
    result = merge_trees(Path("fake"), "base_root", "base_root", "theirs_root")
    
    assert result == {"file.txt": ("h2", TreeRecordType.BLOB)}


def test_mutual_deletion(mock_repo: dict[str, Tree]) -> None:
    mock_repo["base_root"] = Tree({"file.txt": TreeRecord(TreeRecordType.BLOB, "h1", "file.txt")})
    mock_repo["ours_root"] = Tree({})
    mock_repo["theirs_root"] = Tree({})

    result = merge_trees(Path("fake"), "base_root", "ours_root", "theirs_root")
    
    assert result == {}


def test_content_conflict(mock_repo: dict[str, Tree]) -> None:
    mock_repo["base_root"] = Tree({"file.txt": TreeRecord(TreeRecordType.BLOB, "h1", "file.txt")})
    mock_repo["ours_root"] = Tree({"file.txt": TreeRecord(TreeRecordType.BLOB, "h2", "file.txt")})
    mock_repo["theirs_root"] = Tree({"file.txt": TreeRecord(TreeRecordType.BLOB, "h3", "file.txt")})

    result = merge_trees(Path("fake"), "base_root", "ours_root", "theirs_root")

    assert result == {"file.txt": MergeConflict("h1", "h2", "h3", "content")}
    
   


def test_modify_delete_conflict(mock_repo: dict[str, Tree]) -> None:
    mock_repo["base_root"] = Tree({"file.txt": TreeRecord(TreeRecordType.BLOB, "h1", "file.txt")})
    mock_repo["ours_root"] = Tree({"file.txt": TreeRecord(TreeRecordType.BLOB, "h2", "file.txt")})
    mock_repo["theirs_root"] = Tree({})

    result = merge_trees(Path("fake"), "base_root", "ours_root", "theirs_root")
    
    assert result == {"file.txt": MergeConflict("h1", "h2", None, "modify/delete")}


def test_file_dir_conflict(mock_repo: dict[str, Tree]) -> None:
    mock_repo["base_root"] = Tree({})
    mock_repo["ours_root"] = Tree({"logger": TreeRecord(TreeRecordType.BLOB, "h_file", "logger")})
    mock_repo["theirs_root"] = Tree({"logger": TreeRecord(TreeRecordType.TREE, "h_dir", "logger")})

    result = merge_trees(Path("fake"), "base_root", "ours_root", "theirs_root")
    
    assert result == {"logger": MergeConflict(None, "h_file", "h_dir", "type")}


def test_directory_recursion(mock_repo: dict[str, Tree]) -> None:
    mock_repo["base_src"] = Tree({
        "a.txt": TreeRecord(TreeRecordType.BLOB, "h_a", "a.txt"),
        "b.txt": TreeRecord(TreeRecordType.BLOB, "h_b", "b.txt")
    })
    mock_repo["ours_src"] = Tree({
        "a.txt": TreeRecord(TreeRecordType.BLOB, "h_a_mod", "a.txt"),
        "b.txt": TreeRecord(TreeRecordType.BLOB, "h_b", "b.txt")
    })
    mock_repo["theirs_src"] = Tree({
        "a.txt": TreeRecord(TreeRecordType.BLOB, "h_a", "a.txt"),
        "b.txt": TreeRecord(TreeRecordType.BLOB, "h_b_mod", "b.txt")
    })
    
    mock_repo["base_root"] = Tree({"src": TreeRecord(TreeRecordType.TREE, "base_src", "src")})
    mock_repo["ours_root"] = Tree({"src": TreeRecord(TreeRecordType.TREE, "ours_src", "src")})
    mock_repo["theirs_root"] = Tree({"src": TreeRecord(TreeRecordType.TREE, "theirs_src", "src")})

    result = merge_trees(Path("fake"), "base_root", "ours_root", "theirs_root")

    assert result == {"src": {"a.txt": ("h_a_mod", TreeRecordType.BLOB), "b.txt": ("h_b_mod", TreeRecordType.BLOB)}}