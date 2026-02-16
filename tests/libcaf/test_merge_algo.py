import pytest
from pathlib import Path

from libcaf import Tree, TreeRecord, TreeRecordType
from libcaf.merge_algo import resolve_merge_tree, MergeAction, ConflictType


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


def test_identical_roots() -> None:
    node = resolve_merge_tree(Path("fake"), "base_hash", "base_hash", "base_hash")
    
    assert node.action == MergeAction.TAKE_OURS
    assert node.children == []


def test_fast_forward_ours_root() -> None:
    node = resolve_merge_tree(Path("fake"), "base_hash", "ours_hash", "base_hash")
    
    assert node.action == MergeAction.TAKE_OURS
    assert node.children == []


def test_fast_forward_theirs_root() -> None:
    node = resolve_merge_tree(Path("fake"), "base_hash", "base_hash", "theirs_hash")
    
    assert node.action == MergeAction.TAKE_THEIRS
    assert node.children == []


def test_mutual_deletion(mock_repo: dict[str, Tree]) -> None:
    mock_repo["base_root"] = Tree({"file.txt": TreeRecord(TreeRecordType.BLOB, "h1", "file.txt")})
    mock_repo["ours_root"] = Tree({})
    mock_repo["theirs_root"] = Tree({})

    root_node = resolve_merge_tree(Path("fake"), "base_root", "ours_root", "theirs_root")
    
    assert root_node.action == MergeAction.MERGE_DIRECTORY
    assert len(root_node.children) == 1
    
    child = root_node.children[0]
    assert child.name == "file.txt"
    assert child.action == MergeAction.DELETE


def test_content_conflict(mock_repo: dict[str, Tree]) -> None:
    mock_repo["base_root"] = Tree({"file.txt": TreeRecord(TreeRecordType.BLOB, "h1", "file.txt")})
    mock_repo["ours_root"] = Tree({"file.txt": TreeRecord(TreeRecordType.BLOB, "h2", "file.txt")})
    mock_repo["theirs_root"] = Tree({"file.txt": TreeRecord(TreeRecordType.BLOB, "h3", "file.txt")})

    root_node = resolve_merge_tree(Path("fake"), "base_root", "ours_root", "theirs_root")
    
    assert root_node.action == MergeAction.MERGE_DIRECTORY
    assert len(root_node.children) == 1
    
    child = root_node.children[0]
    assert child.name == "file.txt"
    assert child.action == MergeAction.MERGE_CONTENT
    assert child.record_type == TreeRecordType.BLOB
    assert child.base_hash == "h1"
    assert child.ours_hash == "h2"
    assert child.theirs_hash == "h3"


def test_modify_delete_conflict(mock_repo: dict[str, Tree]) -> None:
    mock_repo["base_root"] = Tree({"file.txt": TreeRecord(TreeRecordType.BLOB, "h1", "file.txt")})
    mock_repo["ours_root"] = Tree({"file.txt": TreeRecord(TreeRecordType.BLOB, "h2", "file.txt")})
    mock_repo["theirs_root"] = Tree({})

    root_node = resolve_merge_tree(Path("fake"), "base_root", "ours_root", "theirs_root")
    
    child = root_node.children[0]
    assert child.name == "file.txt"
    assert child.action == MergeAction.CONFLICT
    assert child.conflict_type == ConflictType.MODIFY_DELETE


def test_file_dir_conflict(mock_repo: dict[str, Tree]) -> None:
    mock_repo["base_root"] = Tree({})
    mock_repo["ours_root"] = Tree({"logger": TreeRecord(TreeRecordType.BLOB, "h_file", "logger")})
    mock_repo["theirs_root"] = Tree({"logger": TreeRecord(TreeRecordType.TREE, "h_dir", "logger")})

    root_node = resolve_merge_tree(Path("fake"), "base_root", "ours_root", "theirs_root")
    
    child = root_node.children[0]
    assert child.name == "logger"
    assert child.action == MergeAction.CONFLICT
    assert child.conflict_type == ConflictType.FILE_DIR


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

    root_node = resolve_merge_tree(Path("fake"), "base_root", "ours_root", "theirs_root")
    
    assert root_node.action == MergeAction.MERGE_DIRECTORY
    
    src_node = root_node.children[0]
    assert src_node.name == "src"
    assert src_node.action == MergeAction.MERGE_DIRECTORY
    assert len(src_node.children) == 2
    
    a_node = next(c for c in src_node.children if c.name == "a.txt")
    b_node = next(c for c in src_node.children if c.name == "b.txt")
    
    assert a_node.action == MergeAction.TAKE_OURS
    assert b_node.action == MergeAction.TAKE_THEIRS