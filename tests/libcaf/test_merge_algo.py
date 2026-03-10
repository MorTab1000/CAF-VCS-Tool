
from libcaf import Tree, TreeRecord, TreeRecordType
from libcaf.plumbing import load_tree
from libcaf.repository import Repository
from libcaf.merge_algo import merge_trees, MergeConflict, execute_merge
from pathlib import Path




def test_identical_roots() -> None:
    fake_db ={"base_root" : Tree({"file.txt": TreeRecord(TreeRecordType.BLOB, "h1", "file.txt")})}
    
    result = merge_trees("base_root", "base_root", "base_root", lambda h: fake_db[h])
    assert result == {"file.txt": TreeRecord(TreeRecordType.BLOB, "h1", "file.txt")}


def test_fast_forward_ours_root() -> None:
    fake_db = { "base_root" : Tree({"file.txt": TreeRecord(TreeRecordType.BLOB, "h1", "file.txt")}),
                "ours_root" :  Tree({"file.txt": TreeRecord(TreeRecordType.BLOB, "h2", "file.txt")})
    }       
    result = merge_trees("base_root", "ours_root", "base_root", lambda h: fake_db[h])
    
    assert result == {"file.txt": TreeRecord(TreeRecordType.BLOB, "h2", "file.txt")}


def test_fast_forward_theirs_root() -> None:
    fake_db = { "base_root" : Tree({"file.txt": TreeRecord(TreeRecordType.BLOB, "h1", "file.txt")}),
                "theirs_root" :  Tree({"file.txt": TreeRecord(TreeRecordType.BLOB, "h2", "file.txt")})
    }
    result = merge_trees("base_root", "base_root", "theirs_root", lambda h: fake_db[h])
    
    assert result == {"file.txt": TreeRecord(TreeRecordType.BLOB, "h2", "file.txt")}


def test_mutual_deletion() -> None:
    fake_db = {
        "base_root": Tree({"file.txt": TreeRecord(TreeRecordType.BLOB, "h1", "file.txt")}),
        "ours_root": Tree({}),
        "theirs_root": Tree({})
    }

    result = merge_trees("base_root", "ours_root", "theirs_root", lambda h: fake_db[h])
    
    assert result == {}


def test_content_conflict() -> None:
    fake_db = {
        "base_root": Tree({"file.txt": TreeRecord(TreeRecordType.BLOB, "h1", "file.txt")}),
        "ours_root": Tree({"file.txt": TreeRecord(TreeRecordType.BLOB, "h2", "file.txt")}),
        "theirs_root": Tree({"file.txt": TreeRecord(TreeRecordType.BLOB, "h3", "file.txt")})
    }

    result = merge_trees("base_root", "ours_root", "theirs_root", lambda h: fake_db[h])

    assert result == {"file.txt": MergeConflict("h1", "h2", "h3", "content")}
    
   


def test_modify_delete_conflict() -> None:
    fake_db = {
        "base_root": Tree({"file.txt": TreeRecord(TreeRecordType.BLOB, "h1", "file.txt")}),
        "ours_root": Tree({"file.txt": TreeRecord(TreeRecordType.BLOB, "h2", "file.txt")}),
        "theirs_root": Tree({})
    }

    result = merge_trees("base_root", "ours_root", "theirs_root", lambda h: fake_db[h])
    
    assert result == {"file.txt": MergeConflict("h1", "h2", None, "modify/delete")}


def test_file_dir_conflict() -> None:
    fake_db = {
        "base_root": Tree({}),
        "ours_root": Tree({"logger": TreeRecord(TreeRecordType.BLOB, "h_file", "logger")}),
        "theirs_root": Tree({"logger": TreeRecord(TreeRecordType.TREE, "h_dir", "logger")})
    }

    result = merge_trees("base_root", "ours_root", "theirs_root", lambda h: fake_db[h])
    
    assert result == {"logger": MergeConflict(None, "h_file", "h_dir", "type")}


def test_directory_recursion() -> None:
    fake_db = {
        "base_src": Tree({
            "a.txt": TreeRecord(TreeRecordType.BLOB, "h_a", "a.txt"),
            "b.txt": TreeRecord(TreeRecordType.BLOB, "h_b", "b.txt")
        }),
        "ours_src": Tree({
            "a.txt": TreeRecord(TreeRecordType.BLOB, "h_a_mod", "a.txt"),
            "b.txt": TreeRecord(TreeRecordType.BLOB, "h_b", "b.txt")
        }),
        "theirs_src": Tree({
            "a.txt": TreeRecord(TreeRecordType.BLOB, "h_a", "a.txt"),
            "b.txt": TreeRecord(TreeRecordType.BLOB, "h_b_mod", "b.txt")
        }),
        "base_root": Tree({"src": TreeRecord(TreeRecordType.TREE, "base_src", "src")}),
        "ours_root": Tree({"src": TreeRecord(TreeRecordType.TREE, "ours_src", "src")}),
        "theirs_root": Tree({"src": TreeRecord(TreeRecordType.TREE, "theirs_src", "src")})
    }

    result = merge_trees("base_root", "ours_root", "theirs_root", lambda h: fake_db[h])

    assert result == {"src": {"a.txt": TreeRecord(TreeRecordType.BLOB, "h_a_mod", "a.txt"), "b.txt": TreeRecord(TreeRecordType.BLOB, "h_b_mod", "b.txt")}}


def test_execute_merge_clean_files(temp_repo: Repository) -> None:
    plan = {
    "main.py": TreeRecord(TreeRecordType.BLOB, "hash_main", "main.py"),
    "README.md": TreeRecord(TreeRecordType.BLOB, "hash_readme", "README.md")
    }

    new_tree_hash, conflicts, auto_merged = execute_merge(temp_repo.working_dir, plan)
    
    assert new_tree_hash is not None
    assert conflicts == []
    assert auto_merged == {}

    folder_prefix = new_tree_hash[:2]
    
    assert (temp_repo.objects_dir() / folder_prefix / new_tree_hash).exists()

def test_execute_merge_nested_directories(temp_repo: Repository) -> None:
    plan = {
        "README.md": TreeRecord(TreeRecordType.BLOB, "hash_readme", "README.md"),
        "src": {
            "main.py": TreeRecord(TreeRecordType.BLOB, "hash_main", "main.py"),
            "utils.py": TreeRecord(TreeRecordType.BLOB, "hash_utils", "utils.py")
        }
    }

    root_tree_hash, conflicts, auto_merged = execute_merge(temp_repo.working_dir, plan)

    assert root_tree_hash is not None
    assert conflicts == []
    assert auto_merged == {}
    
    root_folder_prefix = root_tree_hash[:2]
    assert (temp_repo.objects_dir() / root_folder_prefix / root_tree_hash).exists()
    
    new_tree = load_tree(temp_repo.objects_dir(), root_tree_hash)
    src_record = new_tree.records.get("src")
    assert src_record is not None and src_record.type == TreeRecordType.TREE

    src_tree_hash = src_record.hash
    src_folder_prefix = src_tree_hash[:2]
    assert (temp_repo.objects_dir() / src_folder_prefix / src_tree_hash).exists()


def test_execute_merge_with_structural_conflict(temp_repo: Repository) -> None:
    conflict_obj = MergeConflict(
        conflict_type="modify/delete", 
        base_hash="hash_base", 
        ours_hash="hash_ours", 
        theirs_hash=None)
    plan = {
        "clean_file.txt": TreeRecord(TreeRecordType.BLOB, "hash_clean", "clean_file.txt"),
        "nested": {
            "broken_file.txt": conflict_obj
        }
    }
    root_tree_hash, conflicts, auto_merged = execute_merge(temp_repo.working_dir, plan)

    assert root_tree_hash is None
    assert conflicts == [("nested/broken_file.txt", conflict_obj)]
    assert auto_merged == {}


def test_execute_merge_empty_plan(temp_repo: Repository) -> None:
    plan = {}
    root_tree_hash, conflicts, auto_merged = execute_merge(temp_repo.working_dir, plan)

    assert root_tree_hash is not None
    assert len(conflicts) == 0
    assert len(auto_merged) == 0
    
    root_folder_prefix = root_tree_hash[:2]
    assert (temp_repo.objects_dir() / root_folder_prefix / root_tree_hash).exists()